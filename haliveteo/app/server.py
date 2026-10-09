#!/usr/bin/env python3
"""HALiveTeo - live, customizable actions from many devices for Home Assistant.
By TeodorTeo.com (https://teodorteo.com)."""
import asyncio
import collections
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import struct
import time
import uuid
import zlib
from pathlib import Path

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web

CREDIT = "TeodorTeo.com"
CREDIT_URL = "https://teodorteo.com"

DATA = Path(os.environ.get("HAL_DATA", "/data"))
STATIC = Path(__file__).parent / "static"
DEVICES_FILE = DATA / "devices.json"
FEED_FILE = DATA / "feed.jsonl"

INGRESS_PORT = int(os.environ.get("HAL_INGRESS_PORT", 8099))
PUBLIC_PORT = int(os.environ.get("HAL_PUBLIC_PORT", 8766))
INGRESS_PEERS = {"172.30.32.2", "127.0.0.1", "::1"}
DEV = bool(os.environ.get("HAL_DEV"))

HA = os.environ.get("HAL_HA_URL", "http://supervisor/core/api")
HA_WS = (HA[:-4] if HA.endswith("/api") else HA).replace("http", "ws", 1) + "/websocket"
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")

log = logging.getLogger("haliveteo")
session: ClientSession = None
devices: list = []
states: dict = {}
feed = collections.deque(maxlen=500)
clients: set = set()
_rate: dict = {}


def load_options():
    try:
        return json.loads(Path("/data/options.json").read_text())
    except (OSError, ValueError):
        return {}


OPTIONS = load_options()
PREFIX = re.sub(r"[^a-z0-9_]", "", str(OPTIONS.get("event_prefix") or "haliveteo").lower()) or "haliveteo"


def err(status, message):
    cls = {400: web.HTTPBadRequest, 401: web.HTTPUnauthorized, 403: web.HTTPForbidden,
           404: web.HTTPNotFound, 429: web.HTTPTooManyRequests, 502: web.HTTPBadGateway}[status]
    return cls(text=json.dumps({"error": message}), content_type="application/json")


# ---------------------------------------------------------------- storage
def save_devices():
    tmp = DEVICES_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(devices, indent=1))
    tmp.replace(DEVICES_FILE)


def load_all():
    global devices
    try:
        devices = json.loads(DEVICES_FILE.read_text())
    except (OSError, ValueError):
        devices = []
    try:
        for line in FEED_FILE.read_text().splitlines()[-500:]:
            feed.append(json.loads(line))
    except (OSError, ValueError):
        pass


def token_hash(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def find_device(raw):
    if not raw:
        return None
    digest, found = token_hash(raw), None
    for dev in devices:
        if hmac.compare_digest(dev["hash"], digest):
            found = dev
    return found


def public_device(dev):
    return {k: v for k, v in dev.items() if k != "hash"}


# ---------------------------------------------------------------- layout validation
ENTITY_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
SERVICE_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
TILE_TYPES = ("button", "toggle", "slider", "state")
SLIDER_MODES = ("light", "volume", "number")
ACTION_KINDS = ("service", "script", "scene", "event")


def s(value, n=80):
    return str(value or "")[:n]


def entity(value):
    v = str(value or "").strip().lower()
    return v if ENTITY_RE.match(v) else ""


def num(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def clean_tile(raw):
    typ = raw.get("type")
    if typ not in TILE_TYPES:
        return None
    color = s(raw.get("color"), 7)
    tile = {"id": re.sub(r"[^a-z0-9]", "", s(raw.get("id"), 12).lower()) or uuid.uuid4().hex[:8],
            "type": typ, "label": s(raw.get("label"), 40), "icon": s(raw.get("icon"), 8),
            "color": color if re.fullmatch(r"#[0-9a-fA-F]{6}", color) else "",
            "width": 2 if raw.get("width") == 2 else 1, "confirm": bool(raw.get("confirm")),
            "entity_id": entity(raw.get("entity_id"))}
    if typ == "button":
        a = raw.get("action") or {}
        kind = a.get("kind") if a.get("kind") in ACTION_KINDS else "service"
        data = a.get("data") if isinstance(a.get("data"), dict) else {}
        if len(json.dumps(data)) > 2000:
            data = {}
        action = {"kind": kind, "service": s(a.get("service"), 80).lower(), "entity_id": entity(a.get("entity_id")),
                  "data": data, "event_type": re.sub(r"[^a-z0-9_]", "", s(a.get("event_type"), 60).lower())}
        if kind == "service" and not SERVICE_RE.match(action["service"]):
            return None
        if kind in ("script", "scene") and not action["entity_id"].startswith(kind + "."):
            return None
        if kind == "event" and not action["event_type"]:
            return None
        tile["action"] = action
    elif typ in ("toggle", "slider", "state") and not tile["entity_id"]:
        return None
    if typ == "slider":
        tile["mode"] = raw.get("mode") if raw.get("mode") in SLIDER_MODES else "light"
        lo, hi = num(raw.get("min"), 0), num(raw.get("max"), 100)
        tile["min"], tile["max"] = (lo, hi) if lo < hi else (0, 100)
        tile["step"] = max(0.01, num(raw.get("step"), 1))
    if typ == "state":
        tile["attribute"] = s(raw.get("attribute"), 40)
        tile["unit"] = s(raw.get("unit"), 12)
    return tile


def clean_layout(raw):
    raw = raw if isinstance(raw, dict) else {}
    tiles = [t for t in (clean_tile(x) for x in (raw.get("tiles") or [])[:100] if isinstance(x, dict)) if t]
    seen = set()
    for t in tiles:
        while t["id"] in seen:
            t["id"] = uuid.uuid4().hex[:8]
        seen.add(t["id"])
    return {"cols": max(1, min(6, int(num(raw.get("cols"), 2)))), "tiles": tiles}


def layout_entities(layout):
    out = set()
    for t in layout.get("tiles", []):
        if t["type"] != "button" and t.get("entity_id"):
            out.add(t["entity_id"])
        elif t["type"] == "button" and t["action"].get("entity_id") and t["action"]["kind"] in ("script", "scene"):
            out.add(t["action"]["entity_id"])
    return out


# ---------------------------------------------------------------- Home Assistant
def ha_headers():
    return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


async def ha_post(path, data):
    async with session.post(f"{HA}{path}", headers=ha_headers(), json=data) as r:
        if r.status >= 400:
            raise err(502, f"Home Assistant {r.status}: {(await r.text())[:200]}")


async def ha_get(path):
    async with session.get(f"{HA}{path}", headers=ha_headers()) as r:
        if r.status >= 400:
            raise err(502, f"Home Assistant {r.status}")
        return await r.json()


async def send(client, msg):
    try:
        await client.ws.send_json(msg)
    except Exception:  # noqa: BLE001
        pass


async def ha_listener():
    """Keep one WebSocket to Home Assistant: live state cache + fan-out to connected devices."""
    while True:
        try:
            async with session.ws_connect(HA_WS, heartbeat=30, max_msg_size=0) as ws:
                await ws.receive_json()
                await ws.send_json({"type": "auth", "access_token": TOKEN})
                if (await ws.receive_json()).get("type") != "auth_ok":
                    raise RuntimeError("auth failed")
                await ws.send_json({"id": 1, "type": "get_states"})
                await ws.send_json({"id": 2, "type": "subscribe_events", "event_type": "state_changed"})
                log.info("Connected to Home Assistant live stream")
                async for msg in ws:
                    if msg.type != WSMsgType.TEXT:
                        continue
                    data = json.loads(msg.data)
                    if data.get("id") == 1 and data.get("success"):
                        states.clear()
                        for st in data["result"]:
                            states[st["entity_id"]] = {"s": st["state"], "a": st["attributes"]}
                    elif data.get("type") == "event":
                        ev = data["event"]["data"]
                        eid, new = ev["entity_id"], ev.get("new_state")
                        if new is None:
                            states.pop(eid, None)
                        else:
                            states[eid] = {"s": new["state"], "a": new["attributes"]}
                        for c in list(clients):
                            if eid in c.watch:
                                asyncio.create_task(send(c, {"t": "state", "e": eid, "st": states.get(eid)}))
        except Exception as exc:  # noqa: BLE001
            log.warning("HA stream lost (%s) - retrying in 5 s", exc)
        await asyncio.sleep(5)


# ---------------------------------------------------------------- actions
class Client:
    def __init__(self, ws, device, admin):
        self.ws, self.device, self.admin, self.watch = ws, device, admin, set()


async def push_feed(entry):
    entry["ts"] = time.time()
    feed.append(entry)
    try:
        with open(FEED_FILE, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if FEED_FILE.stat().st_size > 800_000:
            FEED_FILE.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in feed))
    except OSError:
        pass
    for c in list(clients):
        if c.admin or (c.device and c.device.get("show_feed")):
            asyncio.create_task(send(c, {"t": "feed", "entry": entry}))


async def exec_tile(tile, value=None):
    """Run what a tile is configured to do. Devices can only trigger actions defined in their own layout."""
    typ = tile["type"]
    if typ == "button":
        a = tile["action"]
        if a["kind"] == "service":
            domain, service = a["service"].split(".", 1)
            data = dict(a.get("data") or {})
            if a.get("entity_id"):
                data["entity_id"] = a["entity_id"]
            await ha_post(f"/services/{domain}/{service}", data)
        elif a["kind"] in ("script", "scene"):
            await ha_post(f"/services/{a['kind']}/turn_on", {"entity_id": a["entity_id"]})
        else:
            await ha_post(f"/events/{a['event_type']}", {"source": "haliveteo"})
    elif typ == "toggle":
        await ha_post("/services/homeassistant/toggle", {"entity_id": tile["entity_id"]})
    elif typ == "slider":
        v = max(tile["min"], min(tile["max"], num(value, tile["min"])))
        eid, domain = tile["entity_id"], tile["entity_id"].split(".")[0]
        if tile["mode"] == "light":
            await ha_post("/services/light/turn_on", {"entity_id": eid, "brightness_pct": int(v)}) if v > 0 \
                else await ha_post("/services/light/turn_off", {"entity_id": eid})
        elif tile["mode"] == "volume":
            await ha_post("/services/media_player/volume_set", {"entity_id": eid, "volume_level": round(v / 100, 3)})
        else:
            await ha_post(f"/services/{domain}/set_value", {"entity_id": eid, "value": v})
    else:
        raise err(400, "this tile has no action")


async def run_action(device, tile_id, value=None, source="device"):
    now = time.time()
    hits = _rate.setdefault(device["id"], collections.deque())
    while hits and now - hits[0] > 10:
        hits.popleft()
    if len(hits) >= 25:
        return {"ok": False, "error": "too many actions - slow down"}
    hits.append(now)
    tile = next((t for t in device["layout"]["tiles"] if t["id"] == tile_id), None)
    if not tile:
        return {"ok": False, "error": "unknown tile"}
    ok, error = True, ""
    try:
        await exec_tile(tile, value)
    except web.HTTPException as exc:
        ok, error = False, json.loads(exc.text).get("error", exc.reason)
    entry = {"device": device["name"], "device_id": device["id"], "tile": tile["id"], "label": tile["label"],
             "icon": tile["icon"], "type": tile["type"], "value": value, "ok": ok, "error": error, "source": source,
             "entity_id": tile.get("entity_id") or (tile.get("action") or {}).get("entity_id", "")}
    await push_feed(entry)
    if ok:
        try:
            await ha_post(f"/events/{PREFIX}_action", {k: entry[k] for k in (
                "device", "device_id", "tile", "label", "type", "value", "entity_id", "source")})
        except web.HTTPException:
            pass
    device["last_seen"] = int(time.time())
    return {"ok": ok, "error": error}


async def run_event(device, name, payload):
    name = re.sub(r"[^a-z0-9_]", "", str(name or "").lower())[:40]
    if not name:
        return {"ok": False, "error": "event name required"}
    payload = payload if isinstance(payload, dict) and len(json.dumps(payload)) < 2000 else {}
    entry = {"device": device["name"], "device_id": device["id"], "tile": "", "label": name, "icon": "📡",
             "type": "event", "value": payload or None, "ok": True, "error": "", "source": "device", "entity_id": ""}
    await push_feed(entry)
    try:
        await ha_post(f"/events/{PREFIX}_event", {"device": device["name"], "device_id": device["id"],
                                                  "event": name, "data": payload})
    except web.HTTPException as exc:
        return {"ok": False, "error": json.loads(exc.text)["error"]}
    device["last_seen"] = int(time.time())
    return {"ok": True, "error": ""}


# ---------------------------------------------------------------- websocket
def hello_for(device):
    watch = layout_entities(device["layout"])
    return {"t": "hello", "device": public_device(device), "states": {e: states.get(e) for e in watch},
            "feed": list(feed)[-30:] if device.get("show_feed") else []}


async def ws_handler(request):
    admin = request.get("admin", False)
    device = None
    if not admin:
        device = find_device(request.query.get("t", ""))
        if not device or not device.get("enabled", True):
            raise err(401, "invalid or disabled device token")
    ws = web.WebSocketResponse(heartbeat=25)
    await ws.prepare(request)
    client = Client(ws, device, admin)
    clients.add(client)
    try:
        if device:
            client.watch = layout_entities(device["layout"])
            device["last_seen"] = int(time.time())
            await ws.send_json(hello_for(device))
        else:
            await ws.send_json({"t": "hello", "admin": True, "feed": list(feed)[-50:]})
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            try:
                data = json.loads(msg.data)
            except ValueError:
                continue
            kind = data.get("t")
            if kind == "action" and device:
                result = await run_action(device, data.get("tile"), data.get("value"))
                await ws.send_json({"t": "ack", "id": data.get("id"), **result})
            elif kind == "event" and device:
                result = await run_event(device, data.get("event"), data.get("data"))
                await ws.send_json({"t": "ack", "id": data.get("id"), **result})
            elif kind == "watch" and admin:
                client.watch = {e for e in (entity(x) for x in (data.get("entities") or [])[:300]) if e}
                await ws.send_json({"t": "states", "states": {e: states.get(e) for e in client.watch}})
    finally:
        clients.discard(client)
    return ws


async def refresh_device_clients(device):
    for c in list(clients):
        if c.device is device or (c.device and c.device["id"] == device["id"]):
            c.device = device
            c.watch = layout_entities(device["layout"])
            asyncio.create_task(send(c, hello_for(device) | {"t": "hello"}))


# ---------------------------------------------------------------- device REST (Shortcuts, ESP, scripts)
def bearer_device(request):
    raw = request.headers.get("Authorization", "").removeprefix("Bearer ").strip() or request.query.get("t", "")
    device = find_device(raw)
    if not device or not device.get("enabled", True):
        raise err(401, "invalid or disabled device token")
    return device


async def h_device_layout(request):
    dev = bearer_device(request)
    return web.json_response({"device": public_device(dev), "states": {e: states.get(e) for e in layout_entities(dev["layout"])}})


async def h_device_action(request):
    dev = bearer_device(request)
    body = await request.json()
    return web.json_response(await run_action(dev, body.get("tile"), body.get("value"), source="api"))


async def h_device_event(request):
    dev = bearer_device(request)
    body = await request.json()
    return web.json_response(await run_event(dev, body.get("event"), body.get("data")))


async def h_device_feed(request):
    dev = bearer_device(request)
    return web.json_response(list(feed)[-50:] if dev.get("show_feed") else [])


# ---------------------------------------------------------------- admin REST (ingress only)
def new_token():
    raw = "hl_" + secrets.token_urlsafe(24)
    return raw, token_hash(raw), raw[:8]


async def h_bootstrap(request):
    try:
        services = await ha_get("/services")
    except web.HTTPException:
        services = []
    svc = sorted(f"{d['domain']}.{n}" for d in services for n in d["services"])
    ents = sorted(({"id": e, "name": (v["a"] or {}).get("friendly_name", e), "state": v["s"]}
                   for e, v in states.items()), key=lambda x: x["id"])
    online = collections.Counter(c.device["id"] for c in clients if c.device)
    return web.json_response({"devices": [public_device(d) | {"online": online.get(d["id"], 0)} for d in devices],
                              "entities": ents, "services": svc,
                              "feed": list(feed)[-50:], "prefix": PREFIX,
                              "public_port": PUBLIC_PORT, "credit": {"name": CREDIT, "url": CREDIT_URL}})


async def h_dev_create(request):
    body = await request.json()
    name = s(body.get("name"), 40).strip()
    if not name:
        raise err(400, "name required")
    raw, digest, prefix = new_token()
    dev = {"id": uuid.uuid4().hex[:8], "name": name, "icon": s(body.get("icon"), 8) or "📱", "hash": digest,
           "prefix": prefix, "created": int(time.time()), "last_seen": None, "enabled": True,
           "show_feed": bool(body.get("show_feed", True)), "layout": clean_layout(body.get("layout"))}
    devices.append(dev)
    save_devices()
    return web.json_response({**public_device(dev), "token": raw})


def get_dev(request):
    dev = next((d for d in devices if d["id"] == request.match_info["id"]), None)
    if not dev:
        raise err(404, "device not found")
    return dev


async def h_dev_update(request):
    dev, body = get_dev(request), await request.json()
    if "name" in body and s(body["name"], 40).strip():
        dev["name"] = s(body["name"], 40).strip()
    if "icon" in body:
        dev["icon"] = s(body["icon"], 8) or "📱"
    for key in ("enabled", "show_feed"):
        if key in body:
            dev[key] = bool(body[key])
    if "layout" in body:
        dev["layout"] = clean_layout(body["layout"])
    save_devices()
    await refresh_device_clients(dev)
    return web.json_response(public_device(dev))


async def h_dev_token(request):
    dev = get_dev(request)
    raw, dev["hash"], dev["prefix"] = new_token()
    save_devices()
    for c in list(clients):
        if c.device and c.device["id"] == dev["id"]:
            asyncio.create_task(c.ws.close())
    return web.json_response({**public_device(dev), "token": raw})


async def h_dev_delete(request):
    dev = get_dev(request)
    devices.remove(dev)
    save_devices()
    for c in list(clients):
        if c.device and c.device["id"] == dev["id"]:
            asyncio.create_task(c.ws.close())
    return web.json_response({"ok": True})


async def h_admin_test(request):
    body = await request.json()
    dev = next((d for d in devices if d["id"] == body.get("device_id")), None)
    if not dev:
        raise err(404, "device not found")
    return web.json_response(await run_action(dev, body.get("tile"), body.get("value"), source="admin-test"))


async def h_feed_clear(request):
    feed.clear()
    FEED_FILE.unlink(missing_ok=True)
    return web.json_response({"ok": True})


# ---------------------------------------------------------------- pages
def page(name):
    async def handler(request):
        return web.Response(text=(STATIC / name).read_text(), content_type="text/html")
    return handler


def make_icon(size):
    cx = cy = size / 2

    def px(x, y):
        d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 / size
        if d < 0.13 or 0.27 < d < 0.34 or 0.42 < d < 0.47:
            return b"\xff\xff\xff"
        return bytes((0, 150, 136))
    raw = b"".join(b"\x00" + b"".join(px(x, y) for x in range(size)) for y in range(size))

    def chunk(tag, body):
        c = struct.pack(">I", len(body)) + tag + body
        return c + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


_icons = {}


async def h_icon(request):
    size = 512 if "512" in request.match_info["name"] else 192
    if size not in _icons:
        _icons[size] = await asyncio.to_thread(make_icon, size)
    return web.Response(body=_icons[size], content_type="image/png")


async def h_manifest(request):
    return web.json_response({"name": "HALiveTeo", "short_name": "HALiveTeo", "start_url": ".", "scope": ".",
                              "display": "standalone", "background_color": "#0e1116", "theme_color": "#009688",
                              "icons": [{"src": f"icon-{n}.png", "sizes": f"{n}x{n}", "type": "image/png"}
                                        for n in (192, 512)]},
                             content_type="application/manifest+json")


@web.middleware
async def ingress_guard(request, handler):
    if not DEV and request.remote not in INGRESS_PEERS:
        raise err(403, "ingress only")
    request["admin"] = True
    return await handler(request)


def build_apps():
    common = [web.get("/ws", ws_handler), web.get("/manifest.webmanifest", h_manifest),
              web.get("/icon-{name}.png", h_icon), web.static("/static", STATIC)]
    ui = web.Application(middlewares=[ingress_guard])
    ui.add_routes(common + [
        web.get("/", page("admin.html")),
        web.get("/api/admin/bootstrap", h_bootstrap),
        web.post("/api/admin/devices", h_dev_create),
        web.post("/api/admin/devices/{id}", h_dev_update),
        web.post("/api/admin/devices/{id}/token", h_dev_token),
        web.delete("/api/admin/devices/{id}", h_dev_delete),
        web.post("/api/admin/test", h_admin_test),
        web.delete("/api/admin/feed", h_feed_clear)])
    pub = web.Application(client_max_size=256 * 1024)
    pub.add_routes(common + [
        web.get("/", page("device.html")),
        web.get("/api/device/layout", h_device_layout),
        web.post("/api/device/action", h_device_action),
        web.post("/api/device/event", h_device_event),
        web.get("/api/device/feed", h_device_feed)])
    return ui, pub


async def main():
    global session
    logging.basicConfig(level=getattr(logging, str(OPTIONS.get("log_level", "info")).upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(message)s")
    DATA.mkdir(parents=True, exist_ok=True)
    load_all()
    session = ClientSession(timeout=ClientTimeout(total=30))
    ui, pub = build_apps()
    for app, port in ((ui, INGRESS_PORT), (pub, PUBLIC_PORT)):
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", port).start()
    log.info("HALiveTeo by %s (%s) - admin :%s, devices :%s, events %s_action/%s_event",
             CREDIT, CREDIT_URL, INGRESS_PORT, PUBLIC_PORT, PREFIX, PREFIX)
    asyncio.create_task(ha_listener())
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
