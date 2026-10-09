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
        data["media_content_id"] = f"media-source://tts/{tts}?message={quote(msg)}"
        if body.get("language"):
            data["media_content_id"] += f"&language={quote(str(body['language']))}"
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


async def restore_volume(levels, delay):
    await asyncio.sleep(delay)
    for entity, level in levels.items():
        try:
            await ha_service("media_player", "volume_set",
                             {"entity_id": entity, "volume_level": level})
        except web.HTTPException as exc:
            log.warning("Could not restore volume of %s: %s", entity, exc.text)


async def announce(body):
    targets = body.get("targets") or body.get("target") or []
    if isinstance(targets, str):
        targets = [t.strip() for t in targets.split(",") if t.strip()]
    if not targets or not all(str(t).startswith("media_player.") for t in targets):
        raise _json_error(400, "targets must be a list of media_player entities")

    item = None
    play = {"entity_id": targets, "media_content_type": "music", "announce": True}
    if body.get("item") or body.get("sound"):
        ref = body.get("item") or body.get("sound")
        item = find_item(ref)
        if not item:
            raise _json_error(404, f"sound not found: {ref}")
        play["media_content_id"] = f"{await base_url()}/media/{item['file']}"
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
        mcid = f"media-source://tts/{tts}?message={quote(msg)}"
        if body.get("language"):
            mcid += f"&language={quote(str(body['language']))}"
        play["media_content_id"] = mcid
        duration = 2 + len(msg) * 0.075
    else:
        raise _json_error(400, "give 'item'/'sound' or 'message'")

    levels = {}
    volume = body.get("volume")
    if volume not in (None, ""):
        volume = max(0.0, min(1.0, float(volume)))
        for entity in targets:
            try:
                state = await ha_get(f"/states/{entity}")
                level = state["attributes"].get("volume_level")
                if level is not None:
                    levels[entity] = level
            except web.HTTPException:
                pass
        await ha_service("media_player", "volume_set",
                         {"entity_id": targets, "volume_level": volume})

    await ha_service("media_player", "play_media", play)
    log.info("Announced %s on %s", item["name"] if item else "TTS", targets)

    if levels:
        asyncio.create_task(restore_volume(levels, duration + 3))
    if item and not item["saved"]:
        asyncio.create_task(drop_later(item, duration + 30))
    return {"ok": True, "duration": round(duration, 2)}


# ---------------------------------------------------------------- handlers
async def h_index(request):
    return web.Response(text=(STATIC / "index.html").read_text(), content_type="text/html")


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
        "tts": [{"entity_id": s["entity_id"], "name": s["attributes"].get("friendly_name", s["entity_id"])}
                for s in states if s["entity_id"].startswith("tts.")],
        "library": [public(i) for i in library],
        "generators": GENERATORS,
        "base_url": await base_url(),
        "api_enabled": bool(OPTIONS.get("api_key")),
        "credit": {"name": CREDIT, "url": CREDIT_URL},
    })


async def h_sounds(request):
    return web.json_response([public(i) for i in library])


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
        saved = fields.get("save") == "1"
        item = register((fields.get("name") or "").strip() or time.strftime("Recording %Y-%m-%d %H:%M"),
                        fields.get("kind") or "upload", "mp3", saved, 0)
        dest = item_path(item)
        rc, _, err = await run("ffmpeg", "-y", "-i", str(tmp), "-vn", "-map_metadata", "-1",
                               "-codec:a", "libmp3lame", "-q:a", "4", str(dest))
        if rc != 0:
            log.warning("ffmpeg failed: %s", err[-300:])
            raise _json_error(400, "cannot decode this audio file")
        item["duration"] = round(await probe_duration(dest), 2)
        commit(item)
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


def build_apps():
    ui = web.Application(middlewares=[ingress_guard], client_max_size=2 * 1024 * 1024)
    ui.add_routes([
        web.get("/", h_index),
        web.get("/media/{file}", h_media),
        web.get("/api/state", h_state),
        web.get("/api/sounds", h_sounds),
        web.post("/api/upload", h_upload),
        web.post("/api/generate", h_generate),
        web.post("/api/announce", h_announce),
        web.post("/api/script", h_script),
        web.post("/api/library/{id}", h_rename),
        web.delete("/api/library/{id}", h_delete),
    ])
    ext = web.Application(middlewares=[key_guard], client_max_size=64 * 1024)
    ext.add_routes([
        web.get("/media/{file}", h_media),
        web.get("/api/sounds", h_sounds),
        web.post("/api/announce", h_announce),
    ])
    return ui, ext


async def main():
    global session
    logging.basicConfig(level=getattr(logging, str(OPTIONS.get("log_level", "info")).upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(message)s")
    LIB.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(ONCE, ignore_errors=True)
    ONCE.mkdir(parents=True, exist_ok=True)
    load_meta()
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
