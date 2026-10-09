#!/usr/bin/env python3
"""HAnnounce Enhanced - Home Assistant add-on by TeodorTeo.com (https://teodorteo.com)."""
import asyncio
import collections
import hashlib
import secrets
import hmac
import json
import logging
import math
import os
import re
import shutil
import struct
import zlib
import time
import uuid
import wave
from pathlib import Path
from urllib.parse import quote

from aiohttp import ClientSession, ClientTimeout, web

CREDIT = "TeodorTeo.com"
CREDIT_URL = "https://teodorteo.com"

DATA = Path(os.environ.get("HAE_DATA", "/data"))
LIB = DATA / "library"
ONCE = Path(os.environ.get("HAE_TMP", "/tmp/hae_once"))
META = DATA / "library.json"
STATIC = Path(__file__).parent / "static"

INGRESS_PORT = int(os.environ.get("HAE_INGRESS_PORT", 8099))
MEDIA_PORT = int(os.environ.get("HAE_MEDIA_PORT", 8765))
INGRESS_PEERS = {"172.30.32.2", "127.0.0.1", "::1"}
DEV = bool(os.environ.get("HAE_DEV"))

HA = os.environ.get("HAE_HA_URL", "http://supervisor/core/api")
SUPERVISOR = os.environ.get("HAE_SUPERVISOR_URL", "http://supervisor")
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")

FILE_RE = re.compile(r"^[a-f0-9]{32}\.(mp3|wav)$")
ONCE_KEEP = 15 * 60  # unannounced one-time sounds are discarded after this many seconds
RATE = 22050

log = logging.getLogger("hannounce")
library: list = []
once: dict = {}
session: ClientSession = None
_base_url_cache = None


def load_options():
    try:
        return json.loads(Path("/data/options.json").read_text())
    except (OSError, ValueError):
        return {}


OPTIONS = load_options()


def _json_error(status, message):
    cls = {
        400: web.HTTPBadRequest,
        401: web.HTTPUnauthorized,
        403: web.HTTPForbidden,
        404: web.HTTPNotFound,
        413: web.HTTPRequestEntityTooLarge,
        429: web.HTTPTooManyRequests,
        502: web.HTTPBadGateway,
    }[status]
    return cls(text=json.dumps({"error": message}), content_type="application/json")


# ---------------------------------------------------------------- library storage
def save_meta():
    tmp = META.with_suffix(".tmp")
    tmp.write_text(json.dumps(library, indent=1))
    tmp.replace(META)


def load_meta():
    global library
    try:
        library = json.loads(META.read_text())
    except (OSError, ValueError):
        library = []
    library = [i for i in library if (LIB / i["file"]).exists()]


def file_hash(item):
    if not item.get("hash"):
        try:
            item["hash"] = hashlib.sha1(item_path(item).read_bytes()).hexdigest()
        except OSError:
            item["hash"] = ""
    return item["hash"]


def public(item):
    out = {k: item[k] for k in ("id", "name", "kind", "file", "duration", "created", "saved")}
    out["favorite"] = bool(item.get("favorite"))
    return out


def find_item(ref):
    """Find a sound by id or (case-insensitive) library name."""
    if not ref:
        return None
    ref = str(ref)
    if ref in once:
        return once[ref]
    for i in library:
        if i["id"] == ref:
            return i
    for i in library:
        if i["name"].lower() == ref.lower():
            return i
    return None


def item_path(item):
    return (LIB if item["saved"] else ONCE) / item["file"]


def register(name, kind, ext, saved, duration):
    iid = uuid.uuid4().hex
    item = {
        "id": iid, "name": name, "kind": kind, "file": f"{iid}.{ext}",
        "duration": round(duration, 2), "created": int(time.time()), "saved": saved,
    }
    return item


def commit(item):
    if item["saved"]:
        file_hash(item)
        library.append(item)
        save_meta()
    else:
        once[item["id"]] = item


def drop(item):
    try:
        item_path(item).unlink()
    except OSError:
        pass
    if item["saved"]:
        if item in library:
            library.remove(item)
            save_meta()
    else:
        once.pop(item["id"], None)


async def drop_later(item, delay):
    await asyncio.sleep(delay)
    drop(item)


async def janitor():
    while True:
        await asyncio.sleep(60)
        now = time.time()
        for item in [i for i in once.values() if now - i["created"] > ONCE_KEEP]:
            drop(item)


# ---------------------------------------------------------------- audio
async def run(*cmd):
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    return proc.returncode, out.decode(), err.decode()


async def probe_duration(path):
    rc, out, _ = await run("ffprobe", "-v", "error", "-show_entries", "format=duration",
                           "-of", "default=nw=1:nk=1", str(path))
    try:
        return float(out.strip())
    except ValueError:
        return 0.0


def _sine(freq, dur, vol=0.7, fade=0.01):
    n = int(RATE * dur)
    f = max(1, int(RATE * fade))
    out = []
    for i in range(n):
        env = min(1.0, i / f, (n - i) / f)
        out.append(vol * env * math.sin(2 * math.pi * freq * i / RATE))
    return out


def _silence(dur):
    return [0.0] * int(RATE * dur)


def _bell(freq, dur, vol=0.7):
    partials = ((1.0, 1.0, 1.0), (2.0, 0.45, 1.5), (2.76, 0.25, 2.2), (4.1, 0.12, 3.0))
    k = 5.0 / dur
    out = []
    for i in range(int(RATE * dur)):
        t = i / RATE
        s = sum(a * math.sin(2 * math.pi * freq * r * t) * math.exp(-t * k * d)
                for r, a, d in partials)
        out.append(vol * min(1.0, t / 0.004) * s / 1.8)
    return out


def _mix(base, extra, offset):
    start = int(RATE * offset)
    if len(base) < start + len(extra):
        base = base + [0.0] * (start + len(extra) - len(base))
    for i, v in enumerate(extra):
        base[start + i] += v
    return base


GENERATORS = {
    "tone": "Pure tone", "beep": "Beeps", "chime": "Ding-dong chime", "gong": "Gong",
    "notify": "Notification", "siren": "Siren", "alarm": "Alarm",
}


def synth(kind, freq=None, duration=None, repeat=1):
    repeat = max(1, min(int(repeat or 1), 10))
    dur = duration if duration and duration > 0 else None
    dur = min(dur, 20) if dur else None
    freq = max(50, min(float(freq), 8000)) if freq else None
    if kind == "tone":
        unit = _sine(freq or 800, dur or 1.0)
    elif kind == "beep":
        d = min(dur or 0.2, 2)
        unit = _sine(freq or 1000, d) + _silence(d)
    elif kind == "chime":
        f = freq or 659.25
        unit = _mix(_bell(f, dur or 1.2), _bell(f * 0.794, dur or 1.2), 0.55)
    elif kind == "gong":
        unit = _bell(freq or 196, dur or 3.0)
    elif kind == "notify":
        f = freq or 523.25
        unit = []
        for n, ratio in enumerate((1.0, 1.26, 1.5)):
            unit = _mix(unit, _bell(f * ratio, dur or 0.6), 0.18 * n)
    elif kind == "siren":
        total = dur or 4.0
        lo = freq or 600
        phase, unit = 0.0, []
        for i in range(int(RATE * total)):
            t = i / RATE
            f = lo + lo * (0.5 - 0.5 * math.cos(2 * math.pi * t / 2.0))
            phase += 2 * math.pi * f / RATE
            unit.append(0.6 * math.sin(phase))
    elif kind == "alarm":
        total = dur or 3.0
        hi = freq or 880
        unit = []
        step = 0
        while len(unit) < RATE * total:
            f = hi if step % 2 == 0 else hi * 0.75
            seg = _sine(f, 0.25, 0.5)
            unit += [s + 0.25 * math.sin(3 * math.asin(max(-1, min(1, s / 0.5)))) for s in seg]
            step += 1
    else:
        raise ValueError(f"unknown sound type: {kind}")
    samples = []
    for _ in range(repeat):
        samples += unit
    if len(samples) > RATE * 60:
        samples = samples[: RATE * 60]
    peak = max((abs(s) for s in samples), default=1) or 1
    gain = 0.85 / peak
    return [s * gain for s in samples]


def write_wav(path, samples):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, s)) * 32767)) for s in samples))


# ---------------------------------------------------------------- home assistant
def ha_headers():
    return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


async def ha_get(path):
    async with session.get(f"{HA}{path}", headers=ha_headers()) as r:
        if r.status >= 400:
            raise _json_error(502, f"Home Assistant: {r.status} {await r.text()}")
        return await r.json()


async def ha_service(domain, service, data):
    async with session.post(f"{HA}/services/{domain}/{service}", headers=ha_headers(),
                            json=data) as r:
        if r.status >= 400:
            raise _json_error(502, f"{domain}.{service}: {r.status} {await r.text()}")


async def ws_call(msg):
    """One-shot call to the Home Assistant WebSocket API."""
    url = HA.replace("http", "ws", 1)
    url = (url[:-4] if url.endswith("/api") else url) + "/websocket"
    async with session.ws_connect(url) as ws:
        await ws.receive_json()
        await ws.send_json({"type": "auth", "access_token": TOKEN})
        if (await ws.receive_json()).get("type") != "auth_ok":
            raise _json_error(502, "Home Assistant websocket auth failed")
        await ws.send_json({"id": 1, **msg})
        reply = await ws.receive_json()
        if not reply.get("success"):
            raise _json_error(502, str((reply.get("error") or {}).get("message", "websocket error")))
        return reply.get("result")


async def tts_engines(states=None):
    """TTS engines configured in Home Assistant, with their supported languages."""
    names = {s["entity_id"]: s["attributes"].get("friendly_name", s["entity_id"])
             for s in (states if states is not None else await ha_get("/states"))
             if s["entity_id"].startswith("tts.")}
    langs = {}
    try:
        res = await ws_call({"type": "tts/engine/list"})
        for prov in (res or {}).get("providers", []):
            langs[prov["engine_id"]] = prov.get("supported_languages") or []
    except Exception as exc:  # noqa: BLE001
        log.warning("tts/engine/list failed (%s), using entity list only", exc)
    return [{"entity_id": e, "name": n, "languages": langs.get(e, [])} for e, n in names.items()]


def tts_media_id(tts, message, language=None, voice=None):
    mcid = f"media-source://tts/{tts}?message={quote(str(message))}"
    if language:
        mcid += f"&language={quote(str(language))}"
    if voice:
        mcid += f"&voice={quote(str(voice))}"
    return mcid



# ---------------------------------------------------------------- network: local + external (public) IP
# The external IP is looked up on a public "what is my IP" service (api.ipify.org, icanhazip.com, ifconfig.me) at most every
# 10 minutes - turn it off with the option check_external_ip. A DDNS/hostname can be set with external_host.
IP_SOURCES = ("https://api.ipify.org", "https://icanhazip.com", "https://ifconfig.me/ip")
IP_RE = re.compile(r"^(?:\d{1,3}(?:\.\d{1,3}){3}|[0-9a-fA-F:]{3,45})$")
CHECK_EXTERNAL = bool(OPTIONS.get("check_external_ip", True))
EXTERNAL_HOST = re.sub(r"[^A-Za-z0-9.\-:\[\]]", "", str(OPTIONS.get("external_host") or "").strip())[:120]
net = {"external_ip": "", "previous": "", "changed": 0, "checked": 0, "error": "", "source": ""}
_local_ip_cache = ""


async def local_ip():
    global _local_ip_cache
    if _local_ip_cache:
        return _local_ip_cache
    try:
        async with session.get(f"{SUPERVISOR}/network/info", headers={"Authorization": f"Bearer {TOKEN}"}) as r:
            ifaces = (await r.json()).get("data", {}).get("interfaces", [])
        ifaces.sort(key=lambda i: not i.get("primary"))
        for iface in ifaces:
            addrs = (iface.get("ipv4") or {}).get("address") or []
            if addrs:
                _local_ip_cache = addrs[0].split("/")[0]
                return _local_ip_cache
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not detect the local IP: %s", exc)
    return ""


async def check_external_ip(force=False):
    if not CHECK_EXTERNAL:
        return net
    if not force and time.time() - net["checked"] < 600:
        return net
    net["checked"] = time.time()
    for url in IP_SOURCES:
        try:
            async with session.get(url, timeout=ClientTimeout(total=6)) as r:
                ip = (await r.text()).strip() if r.status == 200 else ""
        except Exception:  # noqa: BLE001
            continue
        if IP_RE.match(ip):
            if net["external_ip"] and ip != net["external_ip"]:
                net.update(previous=net["external_ip"], changed=time.time())
                log.info("External IP changed: %s -> %s", net["previous"], ip)
            net.update(external_ip=ip, error="", source=url.split("//")[1].split("/")[0])
            return net
    net["error"] = "could not reach any IP lookup service"
    return net


async def net_info(port):
    await check_external_ip()
    host = EXTERNAL_HOST or net["external_ip"]
    host = f"[{host}]" if ":" in host and not host.startswith("[") and EXTERNAL_HOST == "" else host
    lip = await local_ip()
    return {"enabled": CHECK_EXTERNAL, "local_ip": lip, "local_base": f"http://{lip}:{port}" if lip else "",
            "external_ip": net["external_ip"], "external_host": EXTERNAL_HOST,
            "external_base": f"http://{host}:{port}" if host else "", "previous": net["previous"],
            "changed": net["changed"], "checked": net["checked"], "error": net["error"], "source": net["source"]}


async def publish_ip_sensor(entity_id):
    from datetime import datetime, timezone
    if not net["external_ip"]:
        return
    attrs = {"friendly_name": "External IP", "icon": "mdi:ip-network", "previous": net["previous"], "source": net["source"],
             "checked_at": datetime.fromtimestamp(net["checked"], timezone.utc).isoformat()}
    if net["changed"]:
        attrs["changed_at"] = datetime.fromtimestamp(net["changed"], timezone.utc).isoformat()
    try:
        async with session.post(f"{HA}/states/{entity_id}", headers=ha_headers(),
                                json={"state": net["external_ip"], "attributes": attrs}) as r:
            if r.status >= 400:
                log.warning("external IP sensor failed: %s", r.status)
    except Exception as exc:  # noqa: BLE001
        log.warning("external IP sensor failed: %s", exc)


async def net_loop(entity_id):
    """Check on start and every 10 minutes; publish the sensor (state changes show up in history and automations)."""
    while CHECK_EXTERNAL:
        before = net["external_ip"]
        await check_external_ip(force=True)
        if net["external_ip"] and (net["external_ip"] != before or not before):
            await publish_ip_sensor(entity_id)
        await asyncio.sleep(600)


async def base_url():
    global _base_url_cache
    custom = (OPTIONS.get("base_url") or "").strip().rstrip("/")
    if custom:
        return custom
    if _base_url_cache:
        return _base_url_cache
    try:
        async with session.get(f"{SUPERVISOR}/network/info",
                               headers={"Authorization": f"Bearer {TOKEN}"}) as r:
            info = (await r.json()).get("data", {})
        ifaces = info.get("interfaces", [])
        ifaces.sort(key=lambda i: not i.get("primary"))
        for iface in ifaces:
            addrs = (iface.get("ipv4") or {}).get("address") or []
            if addrs:
                _base_url_cache = f"http://{addrs[0].split('/')[0]}:{MEDIA_PORT}"
                return _base_url_cache
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not detect host IP: %s", exc)
    return f"http://homeassistant.local:{MEDIA_PORT}"


SPEAKERS_FILE = DATA / "speakers.json"
speakers: dict = {}
FEATURES = {1: "pause", 2: "seek", 4: "volume_set", 8: "volume_mute", 128: "turn_on", 256: "turn_off",
            512: "play_media", 2048: "select_source", 16384: "play", 131072: "browse", 1048576: "announce"}
_registry = (0.0, {}, {})


def load_speakers():
    global speakers
    try:
        speakers = json.loads(SPEAKERS_FILE.read_text())
    except (OSError, ValueError):
        speakers = {}


def save_speakers():
    tmp = SPEAKERS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(speakers, indent=1))
    tmp.replace(SPEAKERS_FILE)


def decode_features(mask):
    return [name for bit, name in FEATURES.items() if int(mask or 0) & bit]


async def registry():
    """Entity + device registry (platform, manufacturer, model). Cached, best effort."""
    global _registry
    if time.time() - _registry[0] < 60:
        return _registry[1], _registry[2]
    ents, devs = {}, {}
    try:
        for e in await ws_call({"type": "config/entity_registry/list"}) or []:
            ents[e["entity_id"]] = e
        for d in await ws_call({"type": "config/device_registry/list"}) or []:
            devs[d["id"]] = d
    except Exception as exc:  # noqa: BLE001
        log.info("Registry not available (%s) - detection is limited to states", exc)
    _registry = (time.time(), ents, devs)
    return ents, devs


def mark_duplicates(players):
    """Flag speakers that are the same physical device exposed more than once."""
    parent = {p["entity_id"]: p["entity_id"] for p in players}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)
    by_dev, by_name = {}, {}
    ids = set(parent)
    for p in players:
        if p["device_id"]:
            by_dev.setdefault(p["device_id"], []).append(p["entity_id"])
        by_name.setdefault(p["name"].strip().lower(), []).append(p["entity_id"])
        m = re.fullmatch(r"(media_player\..+?)_\d+", p["entity_id"])
        if m and m.group(1) in ids:
            union(p["entity_id"], m.group(1))
    for group in list(by_dev.values()) + list(by_name.values()):
        for other in group[1:]:
            union(group[0], other)
    groups = {}
    for p in players:
        groups.setdefault(find(p["entity_id"]), []).append(p)
    for members in groups.values():
        if len(members) < 2:
            continue
        best = max(members, key=lambda p: ((p["state"] != "unavailable") * 10 + p["announce"] * 5
                                           + (not re.search(r"_\d+$", p["entity_id"])) * 2
                                           - len(p["entity_id"]) * 0.01))
        for p in members:
            if p is not best:
                p["duplicate_of"] = best["entity_id"]


async def build_players(states):
    ents, devs = await registry()
    out = []
    for s in states:
        eid = s["entity_id"]
        if not eid.startswith("media_player."):
            continue
        a = s["attributes"]
        reg = ents.get(eid, {})
        dev = devs.get(reg.get("device_id"), {})
        feats = decode_features(a.get("supported_features", 0))
        meta = speakers.get(eid, {})
        out.append({
            "entity_id": eid, "state": s["state"], "name": a.get("friendly_name", eid),
            "platform": reg.get("platform", ""), "device_id": reg.get("device_id") or "",
            "manufacturer": dev.get("manufacturer") or "", "model": dev.get("model") or "",
            "device_class": a.get("device_class", ""), "features": feats, "announce": "announce" in feats,
            "favorite": bool(meta.get("favorite")), "hidden": bool(meta.get("hidden")),
            "calibration": meta.get("calibration"), "duplicate_of": None,
        })
    mark_duplicates(out)
    return sorted(out, key=lambda p: (not p["favorite"], p["name"].lower()))


def slugify(text):
    text = re.sub(r"[^a-z0-9]+", "_", text.lower().replace("ł", "l")).strip("_")
    return text[:40] or "sound"


async def save_script(sid, cfg):
    """Create/update a script in Home Assistant; fall back to YAML for manual pasting."""
    result = {"entity_id": f"script.{sid}", "created": False,
              "yaml": f"{sid}: {json.dumps(cfg, ensure_ascii=False)}"}
    try:
        async with session.post(f"{HA}/config/script/config/{sid}", headers=ha_headers(),
                                json=cfg) as r:
            if r.status < 300:
                await ha_service("script", "reload", {})
                result["created"] = True
            else:
                log.warning("Script create refused: %s %s", r.status, (await r.text())[:200])
    except Exception as exc:  # noqa: BLE001
        log.warning("Script create failed: %s", exc)
    return result


_slug_cache = None


async def self_slug():
    global _slug_cache
    if _slug_cache is None:
        _slug_cache = os.environ.get("HAE_SLUG", "")
        if not _slug_cache:
            try:
                async with session.get(f"{SUPERVISOR}/addons/self/info",
                                       headers={"Authorization": f"Bearer {TOKEN}"}) as r:
                    _slug_cache = (await r.json()).get("data", {}).get("slug", "")
            except Exception as exc:  # noqa: BLE001
                log.warning("Could not read add-on slug: %s", exc)
    return _slug_cache


async def launcher_info():
    slug = await self_slug()
    path = f"/hassio/ingress/{slug}" if slug else ""
    notify = []
    try:
        for dom in await ha_get("/services"):
            if dom["domain"] == "notify":
                notify = sorted(n for n in dom["services"] if n.startswith("mobile_app_"))
    except web.HTTPException:
        pass
    return {"slug": slug, "path": path,
            "deeplink": f"homeassistant://navigate{path}" if path else "",
            "standalone": f"{await base_url()}/?quick=1", "notify": notify,
            "api_enabled": bool(OPTIONS.get("api_key") or tokens)}


async def make_script(body):
    """Create a Home Assistant script that plays a sound/TTS on the chosen speakers."""
    targets = body.get("targets") or []
    if not targets or not all(str(t).startswith("media_player.") for t in targets):
        raise _json_error(400, "select at least one speaker")
    data = {"media_content_type": "music", "announce": True}
    if body.get("item"):
        item = find_item(body["item"])
        if not item or not item["saved"]:
            raise _json_error(404, "save the sound to the library first")
        data["media_content_id"] = f"{await base_url()}/media/{item['file']}"
        name = item["name"]
        duration = item["duration"]
    elif body.get("message"):
        tts = body.get("tts_entity")
        if not tts:
            raise _json_error(400, "tts_entity required")
        msg = str(body["message"])
        data["media_content_id"] = tts_media_id(tts, msg, body.get("language"), body.get("voice"))
        name = msg[:30]
        duration = 2 + len(msg) * 0.075
    else:
        raise _json_error(400, "give 'item' or 'message'")
    before, after = body.get("before_action") or "", body.get("after_action") or ""
    if not valid_action(before) or not valid_action(after):
        raise _json_error(400, "actions must be script.* or scene.* entities")
    sid = "hannounce_" + slugify(name)
    sequence = []
    if before:
        sequence += [{"action": f"{before.split('.')[0]}.turn_on", "target": {"entity_id": before}}, {"delay": 1}]
    sequence.append({"action": "media_player.play_media", "target": {"entity_id": targets}, "data": data})
    if after:
        sequence += [{"delay": round(duration + 2.5, 1)},
                     {"action": f"{after.split('.')[0]}.turn_on", "target": {"entity_id": after}}]
    cfg = {
        "alias": f"Announce: {name}", "icon": "mdi:bullhorn", "mode": "single",
        "description": f"Created by HAnnounce Enhanced - {CREDIT} ({CREDIT_URL})",
        "sequence": sequence,
    }
    return await save_script(sid, cfg)


# ---------------------------------------------------------------- per-device memory/profiles
DEVICES_FILE = DATA / "devices.json"
DEFAULT_PROFILE = {
    "volume": None,           # announce volume 0..1 (None = leave as is)
    "restore_volume": True,   # put the volume back afterwards
    "resume_mode": "auto",    # auto = player handles announce | manual = we restore playback | none
    "before_delay": 0.0,      # seconds to wait before playing (speakers that need to wake up)
    "after_delay": 2.0,       # seconds after the announcement ends before restoring the old state
    "power_cycle": False,     # turn on if off, turn off again afterwards
    "unmute": False,          # unmute during the announcement, restore mute afterwards
    "quiet_from": "",         # "HH:MM" quiet hours start
    "quiet_to": "",           # "HH:MM" quiet hours end
    "quiet_volume": None,     # volume during quiet hours (None = skip this speaker)
}
devices: dict = {}
_tz_cache = None


def clean_profile(raw):
    p = dict(DEFAULT_PROFILE)

    def num(key, lo, hi, scale=1.0):
        v = raw.get(key)
        if v in (None, ""):
            return None
        return max(lo, min(hi, float(v) * scale))
    for key in ("volume", "quiet_volume"):
        p[key] = num(key, 0.0, 1.0)
    p["before_delay"] = num("before_delay", 0, 15) or 0.0
    p["after_delay"] = num("after_delay", 0, 60) or 0.0
    for key in ("restore_volume", "power_cycle", "unmute"):
        p[key] = bool(raw.get(key, DEFAULT_PROFILE[key]))
    if raw.get("resume_mode") in ("auto", "manual", "none"):
        p["resume_mode"] = raw["resume_mode"]
    for key in ("quiet_from", "quiet_to"):
        v = str(raw.get(key) or "")
        p[key] = v if re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v) else ""
    return p


def load_devices():
    global devices
    try:
        devices = json.loads(DEVICES_FILE.read_text())
    except (OSError, ValueError):
        devices = {}


def save_devices():
    tmp = DEVICES_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(devices, indent=1))
    tmp.replace(DEVICES_FILE)


def profile_for(entity):
    return clean_profile(devices.get(entity) or devices.get("_default") or {})


async def local_minutes():
    global _tz_cache
    if _tz_cache is None:
        try:
            from zoneinfo import ZoneInfo
            _tz_cache = ZoneInfo((await ha_get("/config")).get("time_zone", "UTC"))
        except Exception:  # noqa: BLE001
            _tz_cache = False
    from datetime import datetime
    now = datetime.now(_tz_cache or None)
    return now.hour * 60 + now.minute


def in_quiet(cfg, now_min):
    if not cfg["quiet_from"] or not cfg["quiet_to"]:
        return False
    f = int(cfg["quiet_from"][:2]) * 60 + int(cfg["quiet_from"][3:])
    t = int(cfg["quiet_to"][:2]) * 60 + int(cfg["quiet_to"][3:])
    if f == t:
        return False
    return f <= now_min < t if f < t else (now_min >= f or now_min < t)


def _position_now(attrs, state):
    pos = attrs.get("media_position")
    if pos is None:
        return None
    if state == "playing" and attrs.get("media_position_updated_at"):
        from datetime import datetime, timezone
        try:
            upd = datetime.fromisoformat(attrs["media_position_updated_at"])
            pos += (datetime.now(timezone.utc) - upd).total_seconds()
        except ValueError:
            pass
    return pos


async def snapshot(entity):
    try:
        st = await ha_get(f"/states/{entity}")
    except web.HTTPException:
        return {"state": "unknown"}
    a = st["attributes"]
    return {"state": st["state"], "volume": a.get("volume_level"), "muted": a.get("is_volume_muted"),
            "content_id": a.get("media_content_id"), "content_type": a.get("media_content_type"),
            "position": _position_now(a, st["state"]), "duration": a.get("media_duration")}


async def safe_service(domain, service, data):
    try:
        await ha_service(domain, service, data)
    except web.HTTPException as exc:
        log.warning("%s.%s failed: %s", domain, service, exc.text)


async def wait_finished(entity, estimate, poll):
    """Wait until the announcement is over: poll the player state, or just wait the known duration."""
    if not poll:
        await asyncio.sleep(estimate + 1.5)
        return
    await asyncio.sleep(1.5)
    deadline = time.time() + estimate + 20
    while time.time() < deadline:
        try:
            if (await ha_get(f"/states/{entity}"))["state"] not in ("playing", "buffering"):
                return
        except web.HTTPException:
            return
        await asyncio.sleep(0.7)


async def after_announcement(entity, snap, cfg, changed, estimate, poll):
    """Give the speaker its memory back: volume, mute, playback position, power."""
    await wait_finished(entity, estimate, poll)
    await asyncio.sleep(cfg["after_delay"])
    if "volume" in changed and cfg["restore_volume"] and snap.get("volume") is not None:
        await safe_service("media_player", "volume_set", {"entity_id": entity, "volume_level": snap["volume"]})
    if "mute" in changed and snap.get("muted") is not None:
        await safe_service("media_player", "volume_mute", {"entity_id": entity, "is_volume_muted": snap["muted"]})
    resumed = False
    if cfg["resume_mode"] == "manual" and snap["state"] == "playing" and snap.get("content_id"):
        await safe_service("media_player", "play_media", {
            "entity_id": entity, "media_content_id": snap["content_id"],
            "media_content_type": snap.get("content_type") or "music"})
        resumed = True
        pos = snap.get("position")
        if pos and 3 < pos < (snap.get("duration") or 0) - 3:
            await asyncio.sleep(2)
            await safe_service("media_player", "media_seek", {"entity_id": entity, "seek_position": pos})
    if "power" in changed and not resumed:
        await safe_service("media_player", "turn_off", {"entity_id": entity})


async def run_action(entity):
    """Run a Home Assistant script or scene."""
    domain = str(entity).split(".")[0]
    if domain in ("script", "scene"):
        await safe_service(domain, "turn_on", {"entity_id": entity})


def valid_action(entity):
    return not entity or str(entity).startswith(("script.", "scene."))


async def run_after(entity, delay):
    await asyncio.sleep(delay)
    await run_action(entity)


slots: dict = {}  # entity -> time until which an announcement is still running


async def wait_slot(entity):
    """Queue: a new announcement waits for the previous one on the same speaker instead of cutting it."""
    wait = slots.get(entity, 0) - time.time()
    if wait > 30:
        raise _json_error(400, f"{entity} is busy for another {int(wait)} s - press Stop to cancel")
    if wait > 0:
        await asyncio.sleep(wait)
    return max(wait, 0.0)


async def announce_on(entity, cfg, snap, media, volume, estimate):
    queued = await wait_slot(entity)
    if snap is None:
        snap = await snapshot(entity)
    changed = set()
    if cfg["power_cycle"] and snap["state"] in ("off", "standby"):
        await safe_service("media_player", "turn_on", {"entity_id": entity})
        changed.add("power")
        await asyncio.sleep(max(cfg["before_delay"], 1.5))
    elif cfg["before_delay"]:
        await asyncio.sleep(cfg["before_delay"])
    if cfg["unmute"] and snap.get("muted"):
        await safe_service("media_player", "volume_mute", {"entity_id": entity, "is_volume_muted": False})
        changed.add("mute")
    if volume is not None:
        await ha_service("media_player", "volume_set", {"entity_id": entity, "volume_level": volume})
        changed.add("volume")
    manual = cfg["resume_mode"] == "manual"
    await ha_service("media_player", "play_media", {
        "entity_id": entity, "media_content_type": "music", "announce": not manual, **media})
    slots[entity] = time.time() + estimate + 1.5 + ((cfg["after_delay"] + 3) if (changed or manual) else 0)
    if changed or manual:
        poll = manual or snap["state"] not in ("playing", "buffering")
        asyncio.create_task(after_announcement(entity, snap, cfg, changed, estimate, poll))
    return queued


# ---------------------------------------------------------------- sessions + Live Activity (Dynamic Island)
# A "session" is one announcement from request to the end of playback. Sessions are visible in the panel / API, mirrored in
# sensor.hannounce_status and (optionally) shown as a Live Activity on iPhone (Dynamic Island + Lock Screen) through the
# Home Assistant Companion app (notify.mobile_app_* with live_update + tag, ended with clear_notification).
LIVE_FILE = DATA / "live.json"
PHONE_RE = re.compile(r"^mobile_app_[a-z0-9_]{1,60}$")
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
LIVE_DEFAULT = {
    "enabled": False, "phones": [], "only_sources": [], "title": "Ogłoszenie", "message": "{text}",
    "critical_text": "📣", "hide_text": False, "countdown": True, "end_delay": 3.0,
    "icon": "mdi:bullhorn", "color": "#03A9F4", "background_color": "", "text_color": "", "relevance": 1.0, "url": "",
}
live_cfg: dict = dict(LIVE_DEFAULT)
sessions: dict = {}
recent_sessions = collections.deque(maxlen=10)
live_run = {"phones": set(), "active": False, "clear": None}
STATUS_SENSOR = bool(OPTIONS.get("status_sensor", True))


def clean_phones(v):
    return [p for p in (str(x).removeprefix("notify.") for x in (v or [])) if PHONE_RE.match(p)][:8]


def clean_live(raw, base=None):
    out = dict(base or LIVE_DEFAULT)
    raw = raw if isinstance(raw, dict) else {}
    def txt(k, n): 
        if k in raw: out[k] = str(raw[k] or "")[:n]
    for k, n in (("title", 80), ("message", 200), ("critical_text", 20), ("url", 200)):
        txt(k, n)
    for k in ("enabled", "hide_text", "countdown"):
        if k in raw: out[k] = bool(raw[k])
    if "phones" in raw: out["phones"] = clean_phones(raw["phones"])
    if "only_sources" in raw: out["only_sources"] = [str(x)[:60] for x in (raw["only_sources"] or [])][:30]
    for k in ("color", "background_color", "text_color"):
        if k in raw: out[k] = str(raw[k]) if HEX_RE.match(str(raw[k] or "")) else ("" if k != "color" else out[k])
    if "icon" in raw: out["icon"] = str(raw["icon"]) if re.match(r"^mdi:[a-z0-9-]{1,60}$", str(raw["icon"])) else out["icon"]
    if "relevance" in raw:
        try: out["relevance"] = max(0.0, min(1.0, float(raw["relevance"])))
        except (TypeError, ValueError): out["relevance"] = None
    if "end_delay" in raw:
        try: out["end_delay"] = max(0.0, min(60.0, float(raw["end_delay"])))
        except (TypeError, ValueError): pass
    return out


def load_live():
    global live_cfg
    try:
        live_cfg = clean_live(json.loads(LIVE_FILE.read_text()))
    except (OSError, ValueError):
        live_cfg = dict(LIVE_DEFAULT)


def save_live():
    tmp = LIVE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(live_cfg, indent=1))
    tmp.replace(LIVE_FILE)


def public_session(x):
    return {k: x[k] for k in ("id", "kind", "said", "targets", "names", "source", "user", "state", "created",
                              "started", "ends", "duration", "hidden")}


def fill(tpl, sess, hide):
    names = ", ".join(sess["names"]) or "—"
    text = "" if hide else sess["said"]
    return (str(tpl).replace("{text}", text or sess["kind"].upper()).replace("{speakers}", names)
            .replace("{source}", sess["source"]).replace("{user}", sess["user"]))


async def publish_status():
    if not STATUS_SENSOR:
        return
    from datetime import datetime, timezone
    act = [x for x in sessions.values() if x["state"] in ("queued", "playing")]
    head = max((x for x in act if x["state"] == "playing"), key=lambda x: x["started"], default=None)
    attrs = {"friendly_name": "HAnnounce status", "icon": "mdi:bullhorn", "active": len(act),
             "queued": sum(1 for x in act if x["state"] == "queued")}
    if head:
        attrs.update(text="" if head["hidden"] else head["said"], speakers=head["names"], source=head["source"],
                     user=head["user"], duration=head["duration"],
                     ends_at=datetime.fromtimestamp(head["ends"], timezone.utc).isoformat())
    try:
        async with session.post(f"{HA}/states/sensor.hannounce_status", headers=ha_headers(),
                                json={"state": "announcing" if head else "idle", "attributes": attrs}) as r:
            if r.status >= 400:
                log.warning("status sensor failed: %s", r.status)
    except Exception as exc:  # noqa: BLE001
        log.warning("status sensor failed: %s", exc)


def session_style(sess):
    return clean_live(sess.get("live") or {}, dict(live_cfg))


async def live_refresh():
    """One Live Activity ('hannounce_live') mirrors the newest playing session; it ends shortly after the last one."""
    active = [x for x in sessions.values() if x["state"] == "playing" and x["phones"]]
    task = live_run["clear"]
    if not active:
        if live_run["active"] and not task:
            live_run["clear"] = asyncio.create_task(live_end_later())
        return
    if task:
        task.cancel(); live_run["clear"] = None
    head = max(active, key=lambda x: x["started"])
    st = session_style(head)
    phones = set().union(*(x["phones"] for x in active))
    hide = st["hide_text"] or head["hidden"]
    data = {"tag": "hannounce_live", "live_update": True, "notification_icon": st["icon"],
            "notification_icon_color": st["color"], "color": st["color"]}
    if st["countdown"]:
        data.update(chronometer=True, when=int(head["ends"]), when_relative=False)
    if st["critical_text"]:
        data["critical_text"] = st["critical_text"]
    for k in ("background_color", "text_color", "url"):
        if st[k]: data[k] = st[k]
    if st["relevance"] is not None:
        data["relevance_score"] = st["relevance"]
    if live_run["active"]:
        data["silent"], data["alert_once"] = True, True
    payload = {"title": fill(st["title"], head, hide), "message": fill(st["message"], head, hide), "data": data}
    for phone in phones:
        await safe_service("notify", phone, payload)
    live_run["phones"] |= phones
    live_run["active"] = True


async def live_end_now():
    for phone in list(live_run["phones"]):
        await safe_service("notify", phone, {"message": "clear_notification", "data": {"tag": "hannounce_live"}})
    live_run.update(phones=set(), active=False, clear=None)


async def live_end_later():
    await asyncio.sleep(max(0.0, live_cfg["end_delay"]))
    live_run["clear"] = None
    if not any(x["state"] == "playing" and x["phones"] for x in sessions.values()):
        await live_end_now()


async def finish_session(sess, wait):
    await asyncio.sleep(max(0.2, wait))
    if sess["state"] == "playing":
        sess["state"] = "done"
    sessions.pop(sess["id"], None)
    recent_sessions.append(public_session(sess))
    await live_refresh()
    await publish_status()


def phones_for(source, token_phones, override):
    phones = set(clean_phones(token_phones))
    if live_cfg["enabled"] and (not live_cfg["only_sources"] or source in live_cfg["only_sources"]):
        phones |= set(live_cfg["phones"])
    if isinstance(override, dict):
        if override.get("enabled") is False:
            return set()
        phones |= set(clean_phones(override.get("phones")))
    return phones


async def stop_sessions(targets):
    for sess in list(sessions.values()):
        if not targets or set(targets) & set(sess["targets"]):
            sess["state"] = "done"
            sessions.pop(sess["id"], None)
            recent_sessions.append(public_session(sess))
    await live_refresh()
    await publish_status()


async def announce(body):
    targets = body.get("targets") or body.get("target") or []
    if isinstance(targets, str):
        targets = [t.strip() for t in targets.split(",") if t.strip()]
    if not targets or not all(str(t).startswith("media_player.") for t in targets):
        raise _json_error(400, "targets must be a list of media_player entities")
    source, user_name = str(body.get("_source") or "api"), str(body.get("_user") or "")
    token_phones, live_override = body.get("_live_phones") or [], body.get("live")

    item = None
    media = {}
    prepared = False
    if body.get("item") or body.get("sound"):
        ref = body.get("item") or body.get("sound")
        item = find_item(ref)
        if not item:
            raise _json_error(404, f"sound not found: {ref}")
        media["media_content_id"] = f"{await base_url()}/media/{item['file']}"
        duration = item["duration"]
    elif body.get("message"):
        tts = body.get("tts_entity")
        if not tts:
            states = await ha_get("/states")
            ents = [s["entity_id"] for s in states if s["entity_id"].startswith("tts.")]
            if not ents:
                raise _json_error(400, "no tts entity available in Home Assistant")
            tts = ents[0]
        msg = str(body["message"])
        try:  # render first: the speaker then only has to fetch a ready file = no surprise delay
            item = await render_tts(tts, msg, body.get("language"), body.get("voice"))
            media["media_content_id"] = f"{await base_url()}/media/{item['file']}"
            duration = item["duration"]
            prepared = True
        except web.HTTPException as exc:
            log.info("TTS pre-render failed (%s) - falling back to media-source", exc.text)
            media["media_content_id"] = tts_media_id(tts, msg, body.get("language"), body.get("voice"))
            duration = 2 + len(msg) * 0.075
    else:
        raise _json_error(400, "give 'item'/'sound' or 'message'")

    before, after = body.get("before_action") or "", body.get("after_action") or ""
    if not valid_action(before) or not valid_action(after):
        raise _json_error(400, "actions must be script.* or scene.* entities")
    override = body.get("volume")
    override = None if override in (None, "") else max(0.0, min(1.0, float(override)))
    now_min = await local_minutes()
    skipped, jobs = [], []
    for entity in targets:
        cfg = profile_for(entity)
        volume = override if override is not None else cfg["volume"]
        if in_quiet(cfg, now_min):
            if cfg["quiet_volume"] is None:
                skipped.append(entity)
                continue
            volume = cfg["quiet_volume"] if override is None else min(override, cfg["quiet_volume"])
        jobs.append(announce_on(entity, cfg, None, media, volume, duration))
    if before and jobs:
        await run_action(before)
        await asyncio.sleep(max(0.0, min(30.0, float(body.get("before_wait", 1)))))
    queued = 0.0
    sess = None
    if jobs:
        said = str(body["message"]) if body.get("message") else (item["name"] if item else "")
        playing = [t for t in targets if t not in skipped]
        players = {p["entity_id"]: p["name"] for p in await build_players(await ha_get("/states"))}
        sess = {"id": uuid.uuid4().hex[:8], "kind": "tts" if body.get("message") else "sound", "said": said,
                "targets": playing, "names": [players.get(t, t) for t in playing], "source": source, "user": user_name,
                "state": "queued", "created": time.time(), "started": None, "ends": None, "duration": round(duration, 2),
                "hidden": False, "phones": phones_for(source, token_phones, live_override),
                "live": live_override if isinstance(live_override, dict) else None}
        sessions[sess["id"]] = sess
        await publish_status()
    if jobs:
        try:
            queued = max(await asyncio.gather(*jobs))
        except BaseException:
            sessions.pop(sess["id"], None)
            await publish_status()
            raise
        sess.update(state="playing", started=time.time(), ends=time.time() + duration)
        asyncio.create_task(finish_session(sess, duration + 1.0))
        await live_refresh()
        await publish_status()
    if after and jobs:
        extra = max(profile_for(t)["after_delay"] for t in targets if t not in skipped)
        asyncio.create_task(run_after(after, duration + 2.5 + extra))
    log.info("Announced %s on %s (skipped: %s)", item["name"] if item else "TTS",
             [t for t in targets if t not in skipped], skipped)
    if item and not item["saved"] and not item.get("cache"):
        asyncio.create_task(drop_later(item, duration + 40 + queued))
    return {"ok": True, "duration": round(duration, 2), "skipped": skipped,
            "queued": round(queued, 1), "prepared": prepared, "session": sess["id"] if sess else None}


# ---------------------------------------------------------------- tokens + audit log
TOKENS_FILE = DATA / "tokens.json"
LOG_FILE = DATA / "log.jsonl"
tokens: list = []
audit = collections.deque(maxlen=1000)
_rate: dict = {}
RATE_PER_MIN = 30


def load_tokens():
    global tokens
    try:
        tokens = json.loads(TOKENS_FILE.read_text())
    except (OSError, ValueError):
        tokens = []
    audit.clear()
    try:
        for line in LOG_FILE.read_text().splitlines()[-1000:]:
            audit.append(json.loads(line))
    except (OSError, ValueError):
        pass


def save_tokens():
    tmp = TOKENS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(tokens, indent=1))
    tmp.replace(TOKENS_FILE)


def token_hash(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def find_token(raw):
    if not raw:
        return None
    digest, found = token_hash(raw), None
    for tok in tokens:  # no early exit: constant-ish time
        if hmac.compare_digest(tok["hash"], digest):
            found = tok
    return found


def public_token(tok):
    return {k: v for k, v in tok.items() if k != "hash"}


def write_log(entry):
    entry["ts"] = int(time.time())
    audit.append(entry)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if LOG_FILE.stat().st_size > 1_000_000:
            LOG_FILE.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in audit))
    except OSError as exc:
        log.warning("Could not write log: %s", exc)


def apply_token(tok, body):
    """Enforce a token's limits and fill in its defaults (so a shortcut can send just a message)."""
    now = time.time()
    hits = _rate.setdefault(tok["id"], collections.deque())
    while hits and now - hits[0] > 60:
        hits.popleft()
    if len(hits) >= RATE_PER_MIN:
        raise _json_error(429, "too many announcements - slow down")
    hits.append(now)
    body = dict(body)
    is_sound = bool(body.get("item") or body.get("sound"))
    if is_sound and not tok.get("allow_sounds", True):
        raise _json_error(403, "this token may not play sounds")
    if body.get("message") and not tok.get("allow_tts", True):
        raise _json_error(403, "this token may not use text-to-speech")
    if len(str(body.get("message") or "")) > 500:
        raise _json_error(400, "message too long (max 500 characters)")
    targets = body.get("targets") or body.get("target") or tok.get("targets") or []
    if isinstance(targets, str):
        targets = [t.strip() for t in targets.split(",") if t.strip()]
    if not tok.get("allow_all_speakers"):
        allowed = set(tok.get("targets") or [])
        targets = [t for t in targets if t in allowed]
    if not targets:
        raise _json_error(403, "no speaker allowed for this token")
    body["targets"] = targets
    body.pop("target", None)
    for key in ("tts_entity", "language", "voice"):
        if not body.get(key) and tok.get(key):
            body[key] = tok[key]
    if not tok.get("allow_actions"):
        body.pop("before_action", None)
        body.pop("after_action", None)
    if tok.get("max_volume") is not None:
        vol = body.get("volume")
        body["volume"] = min(float(vol), tok["max_volume"]) if vol not in (None, "") else tok["max_volume"]
    return body


def log_entry(request, tok, body, result=None, error=None):
    """Supervised tokens (and the panel / admin key) are recorded in full; other tokens only as metadata."""
    full = tok is None or tok.get("supervised")
    said = body.get("message") if body.get("message") else (
        (find_item(body.get("item") or body.get("sound")) or {}).get("name") or str(body.get("item") or body.get("sound") or ""))
    write_log({
        "source": "panel/admin" if tok is None else tok["name"], "token_id": tok["id"] if tok else "",
        "supervised": bool(tok and tok.get("supervised")), "ip": request.remote,
        "kind": "tts" if body.get("message") else "sound",
        "said": said if full else ("(text not recorded)" if body.get("message") else said),
        "targets": body.get("targets") or [], "ok": error is None, "error": error or "",
        "skipped": (result or {}).get("skipped", [])})


# ---------------------------------------------------------------- handlers
async def h_index(request):
    return web.Response(text=(STATIC / "index.html").read_text(), content_type="text/html")


def make_icon(size):
    """Simple megaphone icon as PNG (no image libraries needed)."""
    def inside(x, y):
        x, y = x / size, y / size
        if 0.18 <= x <= 0.34 and 0.40 <= y <= 0.60:  # body
            return True
        if 0.34 < x <= 0.74:  # cone
            half = 0.10 + (x - 0.34) * 0.55
            if abs(y - 0.5) <= half:
                return True
        return 0.80 <= x <= 0.86 and 0.35 <= y <= 0.65  # sound bar
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            row += b"\xff\xff\xff" if inside(x, y) else bytes((3, 169, 244))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


ICONS = {}


async def h_icon(request):
    size = 512 if "512" in request.match_info["name"] else 192
    if size not in ICONS:
        ICONS[size] = await asyncio.to_thread(make_icon, size)
    return web.Response(body=ICONS[size], content_type="image/png")


async def h_manifest(request):
    return web.json_response({
        "name": "HAnnounce Enhanced", "short_name": "HAnnounce", "start_url": ".", "scope": ".",
        "display": "standalone", "background_color": "#111318", "theme_color": "#03a9f4",
        "icons": [{"src": f"icon-{n}.png", "sizes": f"{n}x{n}", "type": "image/png"} for n in (192, 512)],
    }, content_type="application/manifest+json")


async def h_media(request):
    name = request.match_info["file"]
    if not FILE_RE.match(name):
        raise _json_error(404, "not found")
    for folder in (LIB, ONCE):
        path = folder / name
        if path.exists():
            return web.FileResponse(path)
    raise _json_error(404, "not found")


async def h_state(request):
    states = await ha_get("/states")
    return web.json_response({
        "players": await build_players(states),
        "tts": await tts_engines(states),
        "library": [public(i) for i in library],
        "actions": sorted(({"entity_id": x["entity_id"], "name": x["attributes"].get("friendly_name", x["entity_id"])}
                           for x in states if x["entity_id"].startswith(("script.", "scene."))),
                          key=lambda a: (a["entity_id"].split(".")[0], a["name"].lower())),
        "generators": GENERATORS,
        "base_url": await base_url(),
        "api_enabled": bool(OPTIONS.get("api_key") or tokens),
        "credit": {"name": CREDIT, "url": CREDIT_URL},
    })


async def h_sounds(request):
    return web.json_response([public(i) for i in library])


async def convert_to_item(src, name, kind, saved):
    item = register(name, kind, "mp3", saved, 0)
    dest = item_path(item)
    rc, _, err = await run("ffmpeg", "-y", "-i", str(src), "-vn", "-map_metadata", "-1",
                           "-codec:a", "libmp3lame", "-q:a", "4", str(dest))
    if rc != 0:
        log.warning("ffmpeg failed: %s", err[-300:])
        raise _json_error(400, "cannot decode this audio file")
    item["duration"] = round(await probe_duration(dest), 2)
    commit(item)
    return item


tts_cache: dict = {}


async def render_tts(tts, msg, language=None, voice=None, save=False, name=None):
    """Render TTS with a Home Assistant engine into a local sound, so playback starts instantly.
    Unsaved renders are cached (same engine/text/language/voice = no new delay)."""
    key = (tts, msg, language or "", voice or "")
    if not save:
        cached = tts_cache.get(key)
        if cached and cached["id"] in once and item_path(cached).exists():
            return cached
    req = {"engine_id": tts, "message": msg}
    if language:
        req["language"] = language
    if voice:
        req["options"] = {"voice": voice}
    async with session.post(f"{HA}/tts_get_url", headers=ha_headers(), json=req) as r:
        if r.status >= 400:
            raise _json_error(502, f"tts_get_url: {r.status} {await r.text()}")
        path = (await r.json()).get("path", "")
    core = HA[:-4] if HA.endswith("/api") else HA
    tmp = ONCE / f"tts_{uuid.uuid4().hex}"
    try:
        async with session.get(core + path, headers=ha_headers()) as r:
            if r.status >= 400:
                raise _json_error(502, f"tts download failed: {r.status}")
            tmp.write_bytes(await r.read())
        item = await convert_to_item(tmp, (name or "").strip() or msg[:40], "tts", save)
    finally:
        tmp.unlink(missing_ok=True)
    if not save:
        item["cache"] = True
        tts_cache[key] = item
    return item


async def h_tts_item(request):
    """Render a TTS message into a sound (preview or library)."""
    body = await request.json()
    msg, tts = str(body.get("message") or "").strip(), body.get("tts_entity")
    if not msg or not tts:
        raise _json_error(400, "message and tts_entity required")
    item = await render_tts(tts, msg, body.get("language"), body.get("voice"),
                            bool(body.get("save")), body.get("name"))
    return web.json_response(public(item))


async def h_status(request):
    act = sorted((public_session(x) for x in sessions.values()), key=lambda x: x["created"])
    return web.json_response({"active": act, "recent": list(recent_sessions)[-5:], "now": time.time()})


async def notify_services():
    try:
        return sorted(n for d in await ha_get("/services") if d["domain"] == "notify" for n in d["services"] if PHONE_RE.match(n))
    except web.HTTPException:
        return []


async def h_live_get(request):
    return web.json_response({"settings": live_cfg, "notify": await notify_services(),
                              "sources": ["panel/admin"] + [t["name"] for t in tokens]})


async def h_live_set(request):
    global live_cfg
    live_cfg = clean_live(await request.json(), dict(live_cfg))
    save_live()
    return web.json_response(live_cfg)


async def h_live_test(request):
    """Show the configured Live Activity for ~6 seconds without playing anything."""
    body = await request.json() if request.can_read_body else {}
    phones = set(clean_phones(body.get("phones"))) or set(live_cfg["phones"])
    if not phones:
        raise _json_error(400, "pick at least one phone")
    sess = {"id": "test" + uuid.uuid4().hex[:4], "kind": "tts", "said": "Test ogłoszenia / test announcement",
            "targets": [], "names": ["Test"], "source": "panel/admin", "user": "", "state": "playing", "created": time.time(),
            "started": time.time(), "ends": time.time() + 6, "duration": 6, "hidden": False, "phones": phones,
            "live": body.get("live") if isinstance(body.get("live"), dict) else None}
    sessions[sess["id"]] = sess
    asyncio.create_task(finish_session(sess, 6.0))
    await live_refresh()
    return web.json_response({"ok": True})


async def h_stop(request):
    """Stop playback right now on the given speakers (or on everything that is playing)."""
    try:
        targets = (await request.json()).get("targets") or []
    except ValueError:
        targets = []
    tok = request.get("token")
    if tok and not tok.get("allow_all_speakers"):
        allowed = set(tok.get("targets") or [])
        targets = [t for t in (targets or allowed) if t in allowed]
        if not targets:
            raise _json_error(403, "no speaker allowed for this token")
    if not targets:
        targets = [p["entity_id"] for p in await build_players(await ha_get("/states"))
                   if p["state"] in ("playing", "buffering")]
    targets = [t for t in targets if str(t).startswith("media_player.")]
    if targets:
        await safe_service("media_player", "media_stop", {"entity_id": targets})
        for t in targets:
            slots.pop(t, None)
        await stop_sessions(targets)
    return web.json_response({"ok": True, "stopped": targets})


async def h_tts_voices(request):
    q = request.query
    try:
        res = await ws_call({"type": "tts/engine/voices", "engine_id": q.get("engine", ""),
                             "language": q.get("language", "")})
    except web.HTTPException:
        res = None
    voices = (res or {}).get("voices") or []
    return web.json_response([{"id": v["voice_id"], "name": v.get("name", v["voice_id"])} for v in voices])


async def h_upload(request):
    max_bytes = int(OPTIONS.get("max_upload_mb", 20)) * 1024 * 1024
    fields, tmp = {}, None
    reader = await request.multipart()
    try:
        async for part in reader:
            if part.name == "file":
                tmp = ONCE / f"up_{uuid.uuid4().hex}"
                size = 0
                with open(tmp, "wb") as f:
                    while chunk := await part.read_chunk():
                        size += len(chunk)
                        if size > max_bytes:
                            raise _json_error(413, "file too large")
                        f.write(chunk)
            else:
                fields[part.name] = await part.text()
        if tmp is None:
            raise _json_error(400, "no file")
        item = await convert_to_item(
            tmp, (fields.get("name") or "").strip() or time.strftime("Recording %Y-%m-%d %H:%M"),
            fields.get("kind") or "upload", fields.get("save") == "1")
        return web.json_response(public(item))
    finally:
        if tmp:
            tmp.unlink(missing_ok=True)


async def h_generate(request):
    body = await request.json()
    try:
        samples = await asyncio.to_thread(
            synth, body.get("type", "chime"), body.get("freq") or None,
            body.get("duration") or None, body.get("repeat") or 1)
    except (ValueError, TypeError) as exc:
        raise _json_error(400, str(exc))
    kind = body.get("type", "chime")
    item = register((body.get("name") or "").strip() or GENERATORS.get(kind, kind),
                    "generated", "wav", bool(body.get("save")), len(samples) / RATE)
    await asyncio.to_thread(write_wav, item_path(item), samples)
    commit(item)
    return web.json_response(public(item))


async def h_announce(request):
    try:
        body = await request.json()
    except ValueError:
        raise _json_error(400, "invalid JSON")
    tok = request.get("token")
    body = {k: v for k, v in body.items() if not str(k).startswith("_")}   # internal keys cannot be set from outside
    try:
        if tok:
            body = apply_token(tok, body)
            body.pop("live", None)                                         # per-announcement Live Activity override: admin only
            body["_source"], body["_user"], body["_live_phones"] = tok["name"], tok["name"], tok.get("live_phones") or []
        else:
            body["_source"], body["_user"] = "panel/admin", ""
        result = await announce(body)
    except web.HTTPException as exc:
        try:
            msg = json.loads(exc.text).get("error", exc.reason)
        except (ValueError, TypeError):
            msg = exc.reason
        log_entry(request, tok, body if isinstance(body, dict) else {}, error=msg)
        raise
    if tok:
        tok["last_used"] = int(time.time())
        tok["uses"] = tok.get("uses", 0) + 1
        save_tokens()
    log_entry(request, tok, body, result)
    return web.json_response(result)


async def h_tokens(request):
    return web.json_response([public_token(t) for t in tokens])


async def h_token_create(request):
    body = await request.json()
    name = str(body.get("name") or "").strip()[:60]
    speakers_ = [x for x in (body.get("targets") or []) if str(x).startswith("media_player.")]
    if not name or not speakers_:
        raise _json_error(400, "name and at least one speaker are required")
    raw = "hae_" + secrets.token_urlsafe(24)
    mv = body.get("max_volume")
    tok = {
        "id": uuid.uuid4().hex[:12], "name": name, "hash": token_hash(raw), "prefix": raw[:8],
        "created": int(time.time()), "last_used": None, "uses": 0,
        "supervised": bool(body.get("supervised", True)),
        "targets": speakers_, "allow_all_speakers": bool(body.get("allow_all_speakers")),
        "allow_tts": bool(body.get("allow_tts", True)), "allow_sounds": bool(body.get("allow_sounds", True)),
        "allow_actions": bool(body.get("allow_actions")),
        "max_volume": None if mv in (None, "") else max(0.0, min(1.0, float(mv))),
        "live_phones": clean_phones(body.get("live_phones")),
        "tts_entity": body.get("tts_entity") or "", "language": body.get("language") or "",
        "voice": body.get("voice") or ""}
    tokens.append(tok)
    save_tokens()
    return web.json_response({**public_token(tok), "token": raw})


async def h_token_delete(request):
    tok = next((t for t in tokens if t["id"] == request.match_info["id"]), None)
    if not tok:
        raise _json_error(404, "not found")
    tokens.remove(tok)
    save_tokens()
    return web.json_response({"ok": True})


async def h_log(request):
    limit = max(1, min(int(request.query.get("limit", 100)), 1000))
    who = request.query.get("token", "")
    rows = [e for e in audit if not who or e.get("token_id") == who]
    return web.json_response(list(reversed(rows))[:limit])


async def h_log_clear(request):
    audit.clear()
    LOG_FILE.unlink(missing_ok=True)
    return web.json_response({"ok": True})


async def h_version(request):
    """Installed vs. latest add-on version, as reported by the Supervisor."""
    info = {}
    try:
        async with session.get(f"{SUPERVISOR}/addons/self/info",
                               headers={"Authorization": f"Bearer {TOKEN}"}) as r:
            info = (await r.json()).get("data", {})
    except Exception as exc:  # noqa: BLE001
        log.info("Version info unavailable: %s", exc)
    slug = info.get("slug", "")
    return web.json_response({
        "version": info.get("version"), "latest": info.get("version_latest"),
        "update_available": bool(info.get("update_available")),
        "auto_update": bool(info.get("auto_update")),
        "addon_path": f"/hassio/addon/{slug}/info" if slug else ""})


async def h_network(request):
    return web.json_response(await net_info(MEDIA_PORT))


async def h_network_refresh(request):
    await check_external_ip(force=True)
    await publish_ip_sensor("sensor.hannounce_external_ip")
    return web.json_response(await net_info(MEDIA_PORT))


async def h_launcher_info(request):
    return web.json_response(await launcher_info())


async def h_launcher_create(request):
    """One generic script that opens the HAnnounce interface on the phone (not tied to any sound/speaker)."""
    body = await request.json()
    service = str(body.get("notify") or "")
    if not re.fullmatch(r"(notify\.)?mobile_app_[a-z0-9_]+", service):
        raise _json_error(400, "pick a mobile_app notify service")
    service = service.removeprefix("notify.")
    info = await launcher_info()
    url = info["standalone"] if body.get("target") == "standalone" else info["path"]
    if not url:
        raise _json_error(400, "could not determine the interface address")
    if body.get("platform") == "android" and url.startswith("/"):
        data = {"message": "command_webview", "data": {"command": url}}
    else:
        data = {"title": "HAnnounce", "message": "Tap to open announcements",
                "data": {"url": url, "clickAction": url, "tag": "hannounce_open"}}
    cfg = {"alias": "HAnnounce: open interface", "icon": "mdi:bullhorn", "mode": "single",
           "description": f"Opens the HAnnounce interface on the phone - {CREDIT} ({CREDIT_URL})",
           "sequence": [{"action": f"notify.{service}", "data": data}]}
    return web.json_response(await save_script("hannounce_open", cfg))


async def h_script(request):
    return web.json_response(await make_script(await request.json()))


async def h_devices(request):
    return web.json_response({"default": DEFAULT_PROFILE, "profiles": {
        k: clean_profile(v) for k, v in devices.items()}})


async def h_device_set(request):
    body = await request.json()
    entity = body.get("entity_id", "")
    if entity != "_default" and not entity.startswith("media_player."):
        raise _json_error(400, "entity_id must be a media_player or _default")
    if body.get("reset"):
        devices.pop(entity, None)
    else:
        devices[entity] = clean_profile(body.get("profile") or {})
        for other in body.get("copy_to") or []:
            if str(other).startswith("media_player."):
                devices[other] = dict(devices[entity])
    save_devices()
    return await h_devices(request)


async def h_rename(request):
    item = next((i for i in library if i["id"] == request.match_info["id"]), None)
    if not item:
        raise _json_error(404, "not found")
    body = await request.json()
    if "name" in body:
        name = (body.get("name") or "").strip()
        if not name:
            raise _json_error(400, "name required")
        item["name"] = name
    if "favorite" in body:
        item["favorite"] = bool(body["favorite"])
    save_meta()
    return web.json_response(public(item))


async def h_library_dedupe(request):
    """Remove library sounds with identical audio, keeping the favorite (else the oldest)."""
    groups = {}
    for item in library:
        groups.setdefault(file_hash(item), []).append(item)
    removed = []
    for h, items in groups.items():
        if not h or len(items) < 2:
            continue
        keep = sorted(items, key=lambda i: (not i.get("favorite"), i["created"]))[0]
        for item in items:
            if item is not keep:
                removed.append(item["name"])
                if item.get("favorite"):
                    keep["favorite"] = True
                drop(item)
    return web.json_response({"removed": removed, "library": [public(i) for i in library]})


async def h_speaker_set(request):
    body = await request.json()
    entity = body.get("entity_id", "")
    if not entity.startswith("media_player."):
        raise _json_error(400, "entity_id must be a media_player")
    meta = speakers.setdefault(entity, {})
    for key in ("favorite", "hidden"):
        if key in body:
            meta[key] = bool(body[key])
    save_speakers()
    return web.json_response({"ok": True})


async def h_speakers_dedupe(request):
    """Hide speakers that duplicate another entity of the same physical device."""
    players = await build_players(await ha_get("/states"))
    hidden = []
    for p in players:
        if p["duplicate_of"] and not p["hidden"]:
            speakers.setdefault(p["entity_id"], {})["hidden"] = True
            hidden.append(p["entity_id"])
    save_speakers()
    return web.json_response({"hidden": hidden})


async def h_speaker_calibrate(request):
    """Play a short test sound, measure how the speaker behaves, store a recommended profile."""
    entity = (await request.json()).get("entity_id", "")
    if not entity.startswith("media_player."):
        raise _json_error(400, "entity_id must be a media_player")
    snap = await snapshot(entity)
    if snap["state"] in ("unavailable", "unknown"):
        raise _json_error(400, "speaker is unavailable")
    state = await ha_get(f"/states/{entity}")
    feats = decode_features(state["attributes"].get("supported_features", 0))
    if "play_media" not in feats:
        raise _json_error(400, "this speaker cannot play media")
    announce_ok = "announce" in feats
    cfg = profile_for(entity)
    cfg["resume_mode"] = "auto" if announce_ok else "manual"

    samples = await asyncio.to_thread(synth, "chime", None, 0.9, 1)
    item = register("calibration", "generated", "wav", False, len(samples) / RATE)
    await asyncio.to_thread(write_wav, item_path(item), samples)
    commit(item)
    url = f"{await base_url()}/media/{item['file']}"
    media = {"media_content_id": url}
    volume = cfg["volume"] if cfg["volume"] is not None else 0.3
    t0 = time.time()
    await announce_on(entity, cfg, snap, media, volume, item["duration"])

    started = ended = None
    while time.time() - t0 < item["duration"] + 20:
        st = await ha_get(f"/states/{entity}")
        playing_ours = st["attributes"].get("media_content_id") == url
        active = st["state"] in ("playing", "buffering")
        if started is None and active and (playing_ours or snap["state"] not in ("playing", "buffering")):
            started = time.time() - t0
        elif started is not None and (not active or not playing_ours):
            ended = time.time() - t0
            break
        await asyncio.sleep(0.25)
    drop_task = asyncio.create_task(drop_later(item, 30))  # noqa: F841

    result = {"announce_supported": announce_ok, "features": feats, "measured": ended is not None,
              "start_latency": round(started, 2) if started is not None else None,
              "end_overshoot": None, "recommended": {"resume_mode": cfg["resume_mode"]}}
    if ended is not None:
        overshoot = max(0.0, (ended - started) - item["duration"])
        result["end_overshoot"] = round(overshoot, 2)
        result["recommended"]["after_delay"] = round(min(8.0, max(1.0, overshoot + 1.0)), 1)
    if snap["state"] in ("off", "standby") and "turn_on" in feats and "turn_off" in feats:
        result["recommended"]["power_cycle"] = True
    devices[entity] = clean_profile({**profile_for(entity), **result["recommended"]})
    save_devices()
    result["profile"] = devices[entity]
    result["at"] = int(time.time())
    speakers.setdefault(entity, {})["calibration"] = {k: result[k] for k in (
        "announce_supported", "measured", "start_latency", "end_overshoot", "at")}
    save_speakers()
    return web.json_response(result)


async def h_delete(request):
    item = next((i for i in library if i["id"] == request.match_info["id"]), None)
    if not item:
        raise _json_error(404, "not found")
    drop(item)
    return web.json_response({"ok": True})


@web.middleware
async def ingress_guard(request, handler):
    if not DEV and request.remote not in INGRESS_PEERS:
        raise _json_error(403, "ingress only")
    return await handler(request)


SCOPED_PATHS = {"/api/announce", "/api/sounds", "/api/stop", "/api/status"}


@web.middleware
async def key_guard(request, handler):
    if request.path.startswith("/api/"):
        key = OPTIONS.get("api_key") or ""
        supplied = (request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
                    or request.query.get("key", ""))
        if key and supplied and hmac.compare_digest(supplied.encode(), key.encode()):
            request["token"] = None  # admin key: full access
        else:
            tok = find_token(supplied)
            if not tok:
                raise _json_error(401, "invalid or missing API key / token")
            if request.path not in SCOPED_PATHS:
                raise _json_error(403, "this token may only announce")
            request["token"] = tok
    return await handler(request)


def routes(with_index=True):
    return [
        web.get("/", h_index),
        web.get("/manifest.webmanifest", h_manifest),
        web.get("/icon-{name}.png", h_icon),
        web.get("/media/{file}", h_media),
        web.get("/api/state", h_state),
        web.get("/api/sounds", h_sounds),
        web.post("/api/upload", h_upload),
        web.post("/api/tts/item", h_tts_item),
        web.post("/api/stop", h_stop),
        web.get("/api/status", h_status),
        web.get("/api/live", h_live_get),
        web.post("/api/live", h_live_set),
        web.post("/api/live/test", h_live_test),
        web.get("/api/tokens", h_tokens),
        web.post("/api/tokens", h_token_create),
        web.delete("/api/tokens/{id}", h_token_delete),
        web.get("/api/log", h_log),
        web.delete("/api/log", h_log_clear),
        web.get("/api/tts/voices", h_tts_voices),
        web.post("/api/generate", h_generate),
        web.post("/api/announce", h_announce),
        web.post("/api/script", h_script),
        web.get("/api/version", h_version),
        web.get("/api/network", h_network),
        web.post("/api/network/refresh", h_network_refresh),
        web.get("/api/launcher", h_launcher_info),
        web.post("/api/launcher", h_launcher_create),
        web.post("/api/library/dedupe", h_library_dedupe),
        web.post("/api/speaker", h_speaker_set),
        web.post("/api/speakers/dedupe", h_speakers_dedupe),
        web.post("/api/speaker/calibrate", h_speaker_calibrate),
        web.get("/api/devices", h_devices),
        web.post("/api/devices", h_device_set),
        web.post("/api/library/{id}", h_rename),
        web.delete("/api/library/{id}", h_delete),
    ]


def build_apps():
    # Home Assistant sidebar panel (ingress, only reachable through HA)
    ui = web.Application(middlewares=[ingress_guard], client_max_size=2 * 1024 * 1024)
    ui.add_routes(routes())
    # Standalone interface on the public port: same UI, API protected by api_key
    ext = web.Application(middlewares=[key_guard], client_max_size=2 * 1024 * 1024)
    ext.add_routes(routes())
    return ui, ext


async def main():
    global session
    logging.basicConfig(level=getattr(logging, str(OPTIONS.get("log_level", "info")).upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(message)s")
    LIB.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(ONCE, ignore_errors=True)
    ONCE.mkdir(parents=True, exist_ok=True)
    load_meta()
    load_devices()
    load_speakers()
    load_tokens()
    load_live()
    session = ClientSession(timeout=ClientTimeout(total=30))
    ui, ext = build_apps()
    for app, port in ((ui, INGRESS_PORT), (ext, MEDIA_PORT)):
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", port).start()
    log.info("HAnnounce Enhanced by %s (%s) - UI :%s, media/API :%s",
             CREDIT, CREDIT_URL, INGRESS_PORT, MEDIA_PORT)
    asyncio.create_task(janitor())
    asyncio.create_task(net_loop("sensor.hannounce_external_ip"))
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
