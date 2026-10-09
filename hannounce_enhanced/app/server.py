#!/usr/bin/env python3
"""HAnnounce Enhanced - Home Assistant add-on by TeodorTeo.com (https://teodorteo.com)."""
import asyncio
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


def public(item):
    return {k: item[k] for k in ("id", "name", "kind", "file", "duration", "created", "saved")}


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


def players_list(states):
    out = []
    for s in states:
        if s["entity_id"].startswith("media_player."):
            out.append({"entity_id": s["entity_id"], "state": s["state"],
                        "name": s["attributes"].get("friendly_name", s["entity_id"])})
    return sorted(out, key=lambda p: p["name"].lower())


def slugify(text):
    text = re.sub(r"[^a-z0-9]+", "_", text.lower().replace("ł", "l")).strip("_")
    return text[:40] or "sound"


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
    elif body.get("message"):
        tts = body.get("tts_entity")
        if not tts:
            raise _json_error(400, "tts_entity required")
        msg = str(body["message"])
        data["media_content_id"] = tts_media_id(tts, msg, body.get("language"), body.get("voice"))
        name = msg[:30]
    else:
        raise _json_error(400, "give 'item' or 'message'")
    sid = "hannounce_" + slugify(name)
    cfg = {
        "alias": f"Announce: {name}", "icon": "mdi:bullhorn", "mode": "single",
        "description": f"Created by HAnnounce Enhanced - {CREDIT} ({CREDIT_URL})",
        "sequence": [{"action": "media_player.play_media",
                      "target": {"entity_id": targets}, "data": data}],
    }
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


async def announce_on(entity, cfg, snap, media, volume, estimate):
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
    if changed or manual:
        poll = manual or snap["state"] not in ("playing", "buffering")
        asyncio.create_task(after_announcement(entity, snap, cfg, changed, estimate, poll))


async def announce(body):
    targets = body.get("targets") or body.get("target") or []
    if isinstance(targets, str):
        targets = [t.strip() for t in targets.split(",") if t.strip()]
    if not targets or not all(str(t).startswith("media_player.") for t in targets):
        raise _json_error(400, "targets must be a list of media_player entities")

    item = None
    media = {}
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
        media["media_content_id"] = tts_media_id(tts, msg, body.get("language"), body.get("voice"))
        duration = 2 + len(msg) * 0.075
    else:
        raise _json_error(400, "give 'item'/'sound' or 'message'")

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
        snap = await snapshot(entity)
        jobs.append(announce_on(entity, cfg, snap, media, volume, duration))
    if jobs:
        await asyncio.gather(*jobs)
    log.info("Announced %s on %s (skipped: %s)", item["name"] if item else "TTS",
             [t for t in targets if t not in skipped], skipped)
    if item and not item["saved"]:
        asyncio.create_task(drop_later(item, duration + 40))
    return {"ok": True, "duration": round(duration, 2), "skipped": skipped}


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
        "players": players_list(states),
        "tts": await tts_engines(states),
        "library": [public(i) for i in library],
        "generators": GENERATORS,
        "base_url": await base_url(),
        "api_enabled": bool(OPTIONS.get("api_key")),
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


async def h_tts_item(request):
    """Render a TTS message with a Home Assistant engine into a sound (preview or library)."""
    body = await request.json()
    msg, tts = str(body.get("message") or "").strip(), body.get("tts_entity")
    if not msg or not tts:
        raise _json_error(400, "message and tts_entity required")
    req = {"engine_id": tts, "message": msg}
    if body.get("language"):
        req["language"] = body["language"]
    if body.get("voice"):
        req["options"] = {"voice": body["voice"]}
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
        item = await convert_to_item(tmp, (body.get("name") or "").strip() or msg[:40],
                                     "tts", bool(body.get("save")))
    finally:
        tmp.unlink(missing_ok=True)
    return web.json_response(public(item))


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
    return web.json_response(await announce(body))


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
    name = ((await request.json()).get("name") or "").strip()
    if not name:
        raise _json_error(400, "name required")
    item["name"] = name
    save_meta()
    return web.json_response(public(item))


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


@web.middleware
async def key_guard(request, handler):
    if request.path.startswith("/api/"):
        key = OPTIONS.get("api_key") or ""
        supplied = (request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
                    or request.query.get("key", ""))
        if not key or not hmac.compare_digest(supplied.encode(), key.encode()):
            raise _json_error(401, "invalid or missing API key")
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
        web.get("/api/tts/voices", h_tts_voices),
        web.post("/api/generate", h_generate),
        web.post("/api/announce", h_announce),
        web.post("/api/script", h_script),
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
    session = ClientSession(timeout=ClientTimeout(total=30))
    ui, ext = build_apps()
    for app, port in ((ui, INGRESS_PORT), (ext, MEDIA_PORT)):
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", port).start()
    log.info("HAnnounce Enhanced by %s (%s) - UI :%s, media/API :%s",
             CREDIT, CREDIT_URL, INGRESS_PORT, MEDIA_PORT)
    asyncio.create_task(janitor())
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
