#!/usr/bin/env python3
"""HAWatchTeo - entity watchdog for Home Assistant. By TeodorTeo.com (https://teodorteo.com)."""
import asyncio
import collections
import fnmatch
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web

CREDIT, CREDIT_URL = "TeodorTeo.com", "https://teodorteo.com"
DATA = Path(os.environ.get("HAW_DATA", "/data"))
STATIC = Path(__file__).parent / "static"
SETTINGS_FILE, EVENTS_FILE = DATA / "settings.json", DATA / "events.jsonl"
INGRESS_PORT = int(os.environ.get("HAW_INGRESS_PORT", 8099))
INGRESS_PEERS = {"172.30.32.2", "127.0.0.1", "::1"}
DEV = bool(os.environ.get("HAW_DEV"))
HA = os.environ.get("HAW_HA_URL", "http://supervisor/core/api")
HA_WS = (HA[:-4] if HA.endswith("/api") else HA).replace("http", "ws", 1) + "/websocket"
SUPERVISOR = os.environ.get("HAW_SUPERVISOR_URL", "http://supervisor")
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")

log = logging.getLogger("hawatchteo")
session: ClientSession = None
states: dict = {}            # entity_id -> {"s", "a", "changed", "updated"}
registry_cache = (0.0, {}, {}, {})
active: dict = {}            # "entity|type" -> problem currently open
events = collections.deque(maxlen=300)
_last_published = None
phone_cache = (0.0, [])

DEFAULTS = {
    "unavailable_minutes": 15, "check_unknown": False,
    "stale_enabled": False, "stale_hours": 48, "stale_domains": ["sensor", "binary_sensor"],
    "battery_enabled": True, "battery_threshold": 15,
    "exclude_domains": ["update", "button", "scene", "script", "automation", "person", "zone", "sun", "tts", "stt", "event",
                        "conversation", "todo", "calendar", "weather", "input_button", "number", "select", "text"],
    "ignore": [],
    "notify": False, "phones": [], "notify_recovered": True, "renotify_hours": 24,
    "sensors": True,
}
cfg: dict = dict(DEFAULTS)


def load_options():
    try:
        return json.loads(Path("/data/options.json").read_text())
    except (OSError, ValueError):
        return {}


OPTIONS = load_options()


def err(status, message):
    cls = {400: web.HTTPBadRequest, 403: web.HTTPForbidden, 404: web.HTTPNotFound, 502: web.HTTPBadGateway}[status]
    return cls(text=json.dumps({"error": message}), content_type="application/json")


# ---------------------------------------------------------------- settings
def clean_cfg(raw, base):
    out = dict(base)
    raw = raw if isinstance(raw, dict) else {}

    def num(k, lo, hi, cast=float):
        if k in raw:
            try:
                out[k] = cast(max(lo, min(hi, float(raw[k]))))
            except (TypeError, ValueError):
                pass

    num("unavailable_minutes", 1, 10080, int)
    num("stale_hours", 1, 8760, int)
    num("battery_threshold", 1, 100, int)
    num("renotify_hours", 1, 720, int)
    for k in ("check_unknown", "stale_enabled", "battery_enabled", "notify", "notify_recovered", "sensors"):
        if k in raw:
            out[k] = bool(raw[k])
    for k in ("stale_domains", "exclude_domains", "ignore"):
        if k in raw:
            items = raw[k] if isinstance(raw[k], list) else str(raw[k]).replace("\n", ",").split(",")
            out[k] = [str(x).strip().lower()[:100] for x in items if str(x).strip()][:300]
    if "phones" in raw:
        out["phones"] = [p for p in (str(x).removeprefix("notify.") for x in (raw["phones"] or []))
                         if re.match(r"^mobile_app_[a-z0-9_]{1,60}$", p)][:8]
    return out


def load_cfg():
    global cfg
    try:
        cfg = clean_cfg(json.loads(SETTINGS_FILE.read_text()), dict(DEFAULTS))
    except (OSError, ValueError):
        cfg = dict(DEFAULTS)
    try:
        for line in EVENTS_FILE.read_text().splitlines()[-300:]:
            events.append(json.loads(line))
    except (OSError, ValueError):
        pass


def save_cfg():
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=1))
    tmp.replace(SETTINGS_FILE)


def add_event(kind, entity_id, detail, name=""):
    ev = {"ts": time.time(), "kind": kind, "entity_id": entity_id, "name": name, "detail": detail}
    events.append(ev)
    try:
        with open(EVENTS_FILE, "a") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        if EVENTS_FILE.stat().st_size > 500_000:
            EVENTS_FILE.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events))
    except OSError:
        pass


# ---------------------------------------------------------------- Home Assistant
def ha_headers():
    return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


async def ha_post(path, data):
    async with session.post(f"{HA}{path}", headers=ha_headers(), json=data) as r:
        if r.status >= 400:
            raise err(502, f"Home Assistant {r.status}")


async def ha_get(path):
    async with session.get(f"{HA}{path}", headers=ha_headers()) as r:
        if r.status >= 400:
            raise err(502, f"Home Assistant {r.status}")
        return await r.json()


def ts(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return time.time()


def put_state(st):
    states[st["entity_id"]] = {"s": st["state"], "a": st.get("attributes") or {},
                               "changed": ts(st.get("last_changed")), "updated": ts(st.get("last_updated"))}


async def ws_call(msg):
    async with session.ws_connect(HA_WS, max_msg_size=0) as ws:
        await ws.receive_json()
        await ws.send_json({"type": "auth", "access_token": TOKEN})
        if (await ws.receive_json()).get("type") != "auth_ok":
            raise RuntimeError("ws auth failed")
        await ws.send_json({"id": 1, **msg})
        reply = await ws.receive_json()
        return reply.get("result") if reply.get("success") else None


async def registry():
    """Entity -> platform / device / area (cached 5 min, best effort)."""
    global registry_cache
    if time.time() - registry_cache[0] < 300:
        return registry_cache[1:]
    ents, devs, areas = {}, {}, {}
    try:
        for e in await ws_call({"type": "config/entity_registry/list"}) or []:
            ents[e["entity_id"]] = e
        for d in await ws_call({"type": "config/device_registry/list"}) or []:
            devs[d["id"]] = d
        for a in await ws_call({"type": "config/area_registry/list"}) or []:
            areas[a["area_id"]] = a.get("name", a["area_id"])
    except Exception as exc:  # noqa: BLE001
        log.info("registry unavailable: %s", exc)
    registry_cache = (time.time(), ents, devs, areas)
    return ents, devs, areas


async def ha_listener():
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
                            put_state(st)
                    elif data.get("type") == "event":
                        ev = data["event"]["data"]
                        if ev.get("new_state") is None:
                            states.pop(ev["entity_id"], None)
                        else:
                            put_state(ev["new_state"])
        except Exception as exc:  # noqa: BLE001
            log.warning("HA stream lost (%s) - retrying in 5 s", exc)
        await asyncio.sleep(5)


# ---------------------------------------------------------------- detection
def ignored(eid):
    return any(fnmatch.fnmatchcase(eid, pat) for pat in cfg["ignore"])


def detect(now):
    out = {}
    th = cfg["unavailable_minutes"] * 60
    for eid, st in states.items():
        dom = eid.split(".")[0]
        if dom in cfg["exclude_domains"] or ignored(eid):
            continue
        s = st["s"]
        a = st["a"]
        if s == "unavailable" or (cfg["check_unknown"] and s == "unknown"):
            if now - st["changed"] >= th:
                out[f"{eid}|unavailable"] = {"type": "unavailable", "entity_id": eid, "since": st["changed"], "detail": s}
            continue
        if cfg["battery_enabled"]:
            level = None
            if dom == "sensor" and a.get("device_class") == "battery":
                level = st["s"]
            elif a.get("battery_level") is not None:
                level = a.get("battery_level")
            try:
                if level is not None and float(level) < cfg["battery_threshold"]:
                    out[f"{eid}|battery"] = {"type": "battery", "entity_id": eid, "since": st["updated"], "detail": f"{float(level):g}%"}
                    continue
            except (TypeError, ValueError):
                pass
        if cfg["stale_enabled"] and dom in cfg["stale_domains"] and now - st["updated"] >= cfg["stale_hours"] * 3600:
            out[f"{eid}|stale"] = {"type": "stale", "entity_id": eid, "since": st["updated"], "detail": ""}
    return out


def name_of(eid):
    return ((states.get(eid) or {}).get("a") or {}).get("friendly_name", eid)


async def enrich(p):
    ents, devs, areas = await registry()
    reg = ents.get(p["entity_id"], {})
    dev = devs.get(reg.get("device_id"), {})
    area = areas.get(reg.get("area_id") or dev.get("area_id"), "")
    return {**p, "name": name_of(p["entity_id"]), "platform": reg.get("platform", ""),
            "device": dev.get("name_by_user") or dev.get("name") or "", "area": area}


async def notify_phones(title, message):
    for phone in cfg["phones"]:
        try:
            await ha_post(f"/services/notify/{phone}", {"title": title, "message": message,
                                                       "data": {"tag": "hawatchteo", "group": "hawatchteo"}})
        except web.HTTPException as exc:
            log.warning("notify %s failed: %s", phone, exc.text)


async def publish(problems):
    global _last_published
    if not cfg["sensors"]:
        return
    counts = collections.Counter(p["type"] for p in problems.values())
    names = [name_of(p["entity_id"]) for p in sorted(problems.values(), key=lambda x: x["since"])][:25]
    sig = (len(problems), tuple(sorted(counts.items())), tuple(names))
    if sig == _last_published:
        return
    _last_published = sig
    attrs = {"friendly_name": "HAWatch problems", "icon": "mdi:shield-search", "unavailable": counts["unavailable"],
             "stale": counts["stale"], "battery": counts["battery"], "entities": names}
    for sid, body in (("sensor.hawatchteo_problems", {"state": len(problems), "attributes": {**attrs, "unit_of_measurement": "problems"}}),
                      ("binary_sensor.hawatchteo_problem", {"state": "on" if problems else "off", "attributes": {
                          "friendly_name": "HAWatch problem", "device_class": "problem", "count": len(problems)}})):
        try:
            await ha_post(f"/states/{sid}", body)
        except web.HTTPException:
            pass


async def scan():
    """Compare current problems with the previous scan: log events, notify about new / recovered ones."""
    now = time.time()
    current = detect(now)
    new = [k for k in current if k not in active]
    gone = [k for k in active if k not in current]
    for k in new:
        p = await enrich(current[k])
        active[k] = {**current[k], "first_seen": now, "notified": 0}
        add_event(p["type"], p["entity_id"], p["detail"], p["name"])
    recovered = []
    for k in gone:
        p = active.pop(k)
        add_event("recovered", p["entity_id"], p["type"], name_of(p["entity_id"]))
        recovered.append(p)
    for k, p in current.items():
        active[k].update(since=p["since"], detail=p["detail"])
    if cfg["notify"] and cfg["phones"]:
        due = [active[k] for k in current if now - active[k]["notified"] >= (cfg["renotify_hours"] * 3600 if active[k]["notified"] else 0)]
        fresh = [p for p in due if not p["notified"]]
        if fresh:
            lines = [f"{'🔴' if p['type'] == 'unavailable' else '🔋' if p['type'] == 'battery' else '🕒'} {name_of(p['entity_id'])}"
                     f"{' ' + p['detail'] if p['type'] == 'battery' else ''}" for p in fresh[:6]]
            more = f" (+{len(fresh) - 6})" if len(fresh) > 6 else ""
            await notify_phones(f"HAWatchTeo: {len(fresh)} " + ("new problem" if len(fresh) == 1 else "new problems"), "\n".join(lines) + more)
        elif due:
            await notify_phones("HAWatchTeo", f"{len(current)} problems still open")
        for p in due:
            p["notified"] = now
        if recovered and cfg["notify_recovered"]:
            await notify_phones("HAWatchTeo ✅", ", ".join(name_of(p["entity_id"]) for p in recovered[:6]) + " recovered")
    await publish(current)
    return current


async def scan_loop():
    await asyncio.sleep(8)
    while True:
        try:
            if states:
                await scan()
        except Exception as exc:  # noqa: BLE001
            log.warning("scan failed: %s", exc)
        await asyncio.sleep(60)


# ---------------------------------------------------------------- API
async def h_status(request):
    current = await scan() if request.query.get("fresh") else {k: v for k, v in active.items()}
    rows = [await enrich(p) for p in sorted(current.values(), key=lambda x: x["since"])]
    counts = collections.Counter(p["type"] for p in rows)
    return web.json_response({"problems": rows, "counts": {k: counts.get(k, 0) for k in ("unavailable", "stale", "battery")},
                              "total_entities": len(states), "ignored": sum(1 for e in states if ignored(e)),
                              "settings": cfg, "now": time.time(), "credit": {"name": CREDIT, "url": CREDIT_URL}})


async def h_settings(request):
    global cfg
    cfg = clean_cfg(await request.json(), cfg)
    save_cfg()
    asyncio.create_task(scan())
    return web.json_response(cfg)


async def h_ignore(request):
    body = await request.json()
    pat = str(body.get("pattern") or "").strip().lower()[:100]
    if not pat:
        raise err(400, "pattern required")
    if body.get("remove"):
        cfg["ignore"] = [x for x in cfg["ignore"] if x != pat]
    elif pat not in cfg["ignore"]:
        cfg["ignore"].append(pat)
    save_cfg()
    asyncio.create_task(scan())
    return web.json_response({"ignore": cfg["ignore"]})


async def h_events(request):
    return web.json_response(list(reversed(events))[:200])


async def h_events_clear(request):
    events.clear()
    EVENTS_FILE.unlink(missing_ok=True)
    return web.json_response({"ok": True})


async def h_phones(request):
    try:
        names = sorted(n for d in await ha_get("/services") if d["domain"] == "notify" for n in d["services"]
                       if re.match(r"^mobile_app_[a-z0-9_]{1,60}$", n))
    except web.HTTPException:
        names = []
    return web.json_response(names)


async def h_test(request):
    if not cfg["phones"]:
        raise err(400, "pick at least one phone")
    await notify_phones("HAWatchTeo", "Test notification ✅")
    return web.json_response({"ok": True})


async def h_index(request):
    return web.Response(text=(STATIC / "index.html").read_text(), content_type="text/html")


@web.middleware
async def ingress_guard(request, handler):
    if not DEV and request.remote not in INGRESS_PEERS:
        raise err(403, "ingress only")
    return await handler(request)


def build_app():
    app = web.Application(middlewares=[ingress_guard], client_max_size=256 * 1024)
    app.add_routes([web.get("/", h_index), web.static("/static", STATIC), web.get("/api/status", h_status),
                    web.post("/api/settings", h_settings), web.post("/api/ignore", h_ignore),
                    web.get("/api/events", h_events), web.delete("/api/events", h_events_clear),
                    web.get("/api/phones", h_phones), web.post("/api/test", h_test)])
    return app


async def main():
    global session
    logging.basicConfig(level=getattr(logging, str(OPTIONS.get("log_level", "info")).upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(message)s")
    DATA.mkdir(parents=True, exist_ok=True)
    load_cfg()
    session = ClientSession(timeout=ClientTimeout(total=30))
    runner = web.AppRunner(build_app())
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", INGRESS_PORT).start()
    log.info("HAWatchTeo by %s (%s) - panel :%s", CREDIT, CREDIT_URL, INGRESS_PORT)
    asyncio.create_task(ha_listener())
    asyncio.create_task(scan_loop())
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
