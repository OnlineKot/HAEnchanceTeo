#!/usr/bin/env python3
"""HARemindTeo - reminders and timers for Home Assistant. By TeodorTeo.com (https://teodorteo.com)."""
import asyncio
import collections
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web

import nlptime as nlp

CREDIT, CREDIT_URL = "TeodorTeo.com", "https://teodorteo.com"
DATA = Path(os.environ.get("HAR_DATA", "/data"))
STATIC = Path(__file__).parent / "static"
REM_FILE, SET_FILE, TOK_FILE = DATA / "reminders.json", DATA / "settings.json", DATA / "tokens.json"
INGRESS_PORT = int(os.environ.get("HAR_INGRESS_PORT", 8099))
PUBLIC_PORT = int(os.environ.get("HAR_PUBLIC_PORT", 8767))
INGRESS_PEERS = {"172.30.32.2", "127.0.0.1", "::1"}
DEV = bool(os.environ.get("HAR_DEV"))
HA = os.environ.get("HAR_HA_URL", "http://supervisor/core/api")
HA_WS = (HA[:-4] if HA.endswith("/api") else HA).replace("http", "ws", 1) + "/websocket"
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
PHONE_RE = re.compile(r"^mobile_app_[a-z0-9_]{1,60}$")

log = logging.getLogger("haremindteo")
session: ClientSession = None
reminders: list = []
tokens: list = []
tz = timezone.utc
live_started: dict = {}      # reminder id -> set(phones) with an active Live Activity
_rate: dict = {}
DEFAULTS = {"phones": [], "speakers": [], "tts_entity": "", "language": "", "notify": True, "announce": False, "live": True,
            "snooze_minutes": 10, "keep_done_days": 7}
settings: dict = dict(DEFAULTS)


def load_options():
    try:
        return json.loads(Path("/data/options.json").read_text())
    except (OSError, ValueError):
        return {}


OPTIONS = load_options()


def err(status, message):
    cls = {400: web.HTTPBadRequest, 401: web.HTTPUnauthorized, 403: web.HTTPForbidden, 404: web.HTTPNotFound,
           429: web.HTTPTooManyRequests, 502: web.HTTPBadGateway}[status]
    return cls(text=json.dumps({"error": message}), content_type="application/json")


# ---------------------------------------------------------------- storage
def write_json(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(path)


def load_all():
    global reminders, tokens, settings
    for name, path, default in (("reminders", REM_FILE, []), ("tokens", TOK_FILE, [])):
        try:
            globals()[name] = json.loads(path.read_text())
        except (OSError, ValueError):
            globals()[name] = default
    try:
        settings = clean_settings(json.loads(SET_FILE.read_text()), dict(DEFAULTS))
    except (OSError, ValueError):
        settings = dict(DEFAULTS)


def save():
    write_json(REM_FILE, reminders)


def clean_phones(v):
    return [p for p in (str(x).removeprefix("notify.") for x in (v or [])) if PHONE_RE.match(p)][:8]


def clean_list(v, prefix):
    return [str(x) for x in (v or []) if str(x).startswith(prefix) and re.match(r"^[a-z0-9_.]+$", str(x))][:20]


def clean_settings(raw, base):
    out = dict(base)
    raw = raw if isinstance(raw, dict) else {}
    out["phones"] = clean_phones(raw["phones"]) if "phones" in raw else out["phones"]
    out["speakers"] = clean_list(raw["speakers"], "media_player.") if "speakers" in raw else out["speakers"]
    for k in ("notify", "announce", "live"):
        if k in raw:
            out[k] = bool(raw[k])
    for k, lo, hi in (("snooze_minutes", 1, 1440), ("keep_done_days", 1, 365)):
        if k in raw:
            try:
                out[k] = int(max(lo, min(hi, float(raw[k]))))
            except (TypeError, ValueError):
                pass
    for k in ("tts_entity", "language"):
        if k in raw:
            out[k] = str(raw[k] or "")[:60] if re.match(r"^[A-Za-z0-9_.\-]*$", str(raw[k] or "")) else ""
    return out


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


async def safe_post(path, data):
    try:
        await ha_post(path, data)
        return True
    except web.HTTPException as exc:
        log.warning("%s failed: %s", path, exc.text)
        return False


async def load_timezone():
    global tz
    try:
        tz = ZoneInfo((await ha_get("/config")).get("time_zone", "UTC"))
    except Exception:  # noqa: BLE001
        tz = timezone.utc


def now_local():
    return datetime.now(tz)


# ---------------------------------------------------------------- Live Activity (Dynamic Island countdown)
async def live_start(rem):
    phones = set(rem["phones"])
    if not (rem["live"] and phones) or rem["due"] - time.time() > 8 * 3600 or rem["due"] <= time.time():
        return
    data = {"tag": f"haremind_{rem['id']}", "live_update": True, "notification_icon": "mdi:alarm", "notification_icon_color": "#FF9800",
            "color": "#FF9800", "chronometer": True, "when": int(rem["due"]), "when_relative": False, "critical_text": "⏰"}
    for phone in phones:
        await safe_post(f"/services/notify/{phone}", {"title": rem["title"] or "Reminder", "message": rem["message"] or rem["title"] or "⏰", "data": data})
    live_started[rem["id"]] = phones


async def live_end(rem, delay=0.0):
    phones = live_started.pop(rem["id"], None)
    if not phones:
        return
    if delay:
        await asyncio.sleep(delay)
    for phone in phones:
        await safe_post(f"/services/notify/{phone}", {"message": "clear_notification", "data": {"tag": f"haremind_{rem['id']}"}})


async def live_alarm(rem):
    """When it is due: show 'time is up' on the island for a minute, then clear it."""
    phones = live_started.get(rem["id"])
    if not phones:
        return
    data = {"tag": f"haremind_{rem['id']}", "live_update": True, "notification_icon": "mdi:alarm-check", "notification_icon_color": "#4CAF50",
            "color": "#4CAF50", "critical_text": "✅", "relevance_score": 1.0}
    for phone in phones:
        await safe_post(f"/services/notify/{phone}", {"title": rem["title"] or "Reminder", "message": "⏰ " + (rem["message"] or rem["title"] or ""), "data": data})
    asyncio.create_task(live_end(rem, 60.0))


# ---------------------------------------------------------------- reminders
def public(rem):
    return {k: v for k, v in rem.items() if k != "_x"}


def describe(due):
    d = datetime.fromtimestamp(due, tz)
    return d.strftime("%Y-%m-%d %H:%M")


def make_reminder(title, message, due, repeat, opts, created_by):
    rid = uuid.uuid4().hex[:8]
    phones = clean_phones(opts.get("phones")) if opts.get("phones") is not None else settings["phones"]
    return {"id": rid, "title": str(title or "")[:80], "message": str(message or "")[:300], "due": float(due), "repeat": repeat,
            "state": "pending", "created": time.time(), "created_by": created_by, "fired_at": None, "snoozed": 0,
            "notify": bool(opts.get("notify", settings["notify"])), "phones": phones,
            "announce": bool(opts.get("announce", settings["announce"])),
            "speakers": clean_list(opts["speakers"], "media_player.") if opts.get("speakers") is not None else settings["speakers"],
            "script": (str(opts.get("script") or "") if str(opts.get("script") or "").startswith("script.") else ""),
            "live": bool(opts.get("live", settings["live"]))}


async def add_reminder(rem):
    reminders.append(rem)
    save()
    await live_start(rem)
    await publish_sensors()
    return rem


async def speak(rem):
    text = (rem["title"] + ". " + rem["message"]).strip(". ") if rem["message"] and rem["message"] != rem["title"] else (rem["title"] or rem["message"])
    if not rem["speakers"]:
        return
    tts = settings["tts_entity"]
    if not tts:
        try:
            tts = next(s["entity_id"] for s in await ha_get("/states") if s["entity_id"].startswith("tts."))
        except (StopIteration, web.HTTPException):
            return
    from urllib.parse import quote
    mid = f"media-source://tts/{tts}?message={quote(text)}" + (f"&language={quote(settings['language'])}" if settings["language"] else "")
    await safe_post("/services/media_player/play_media", {"entity_id": rem["speakers"], "media_content_id": mid,
                                                          "media_content_type": "music", "announce": True})


async def fire(rem):
    rem["fired_at"] = time.time()
    title, msg = rem["title"] or "⏰", rem["message"] or rem["title"]
    await safe_post(f"/events/haremindteo_fired", {"id": rem["id"], "title": rem["title"], "message": rem["message"], "created_by": rem["created_by"]})
    if rem["notify"]:
        for phone in rem["phones"]:
            await safe_post(f"/services/notify/{phone}", {"title": title, "message": msg, "data": {
                "tag": f"haremind_fire_{rem['id']}", "push": {"interruption-level": "time-sensitive"},
                "actions": [{"action": f"HAREMIND_DONE_{rem['id']}", "title": "✅ Done"},
                            {"action": f"HAREMIND_SNOOZE_{rem['id']}", "title": f"⏰ +{settings['snooze_minutes']} min"}]}})
    if rem["announce"]:
        await speak(rem)
    if rem["script"]:
        await safe_post("/services/script/turn_on", {"entity_id": rem["script"]})
    await live_alarm(rem)
    if rem["repeat"]:
        rem["due"] = nlp.next_due(datetime.fromtimestamp(rem["due"], tz), rem["repeat"], now_local()).timestamp()
        rem["state"] = "pending"
        await live_start(rem)
    else:
        rem["state"] = "fired"
    save()
    await publish_sensors()


async def snooze(rem, minutes=None):
    rem["due"] = time.time() + 60 * (minutes or settings["snooze_minutes"])
    rem["state"] = "pending"
    rem["snoozed"] = rem.get("snoozed", 0) + 1
    await live_end(rem)
    await live_start(rem)
    save()
    await publish_sensors()


async def finish(rem, cancelled=False):
    await live_end(rem)
    if rem["repeat"] and not cancelled and rem["state"] != "pending":
        rem["due"] = nlp.next_due(datetime.fromtimestamp(rem["due"], tz), rem["repeat"], now_local()).timestamp()
        rem["state"] = "pending"
        await live_start(rem)
    else:
        rem["state"] = "cancelled" if cancelled else "done"
    save()
    await publish_sensors()


async def scheduler():
    """Fire what is due (checked every second); drop old finished reminders."""
    await asyncio.sleep(2)
    last_clean = 0.0
    while True:
        now = time.time()
        for rem in [r for r in reminders if r["state"] == "pending" and r["due"] <= now]:
            try:
                await fire(rem)
            except Exception as exc:  # noqa: BLE001
                log.warning("fire failed: %s", exc)
                rem["state"] = "fired"
        if now - last_clean > 3600:
            last_clean = now
            keep = settings["keep_done_days"] * 86400
            reminders[:] = [r for r in reminders if r["state"] == "pending" or now - (r["fired_at"] or r["created"]) < keep]
            save()
        await asyncio.sleep(1)


async def publish_sensors():
    pending = sorted((r for r in reminders if r["state"] == "pending"), key=lambda r: r["due"])
    nxt = pending[0] if pending else None
    attrs = {"friendly_name": "Next reminder", "icon": "mdi:alarm", "device_class": "timestamp"}
    if nxt:
        attrs.update(title=nxt["title"], message=nxt["message"], id=nxt["id"])
    await safe_post("/states/sensor.haremindteo_next", {"state": datetime.fromtimestamp(nxt["due"], timezone.utc).isoformat() if nxt else "unknown", "attributes": attrs})
    await safe_post("/states/sensor.haremindteo_pending", {"state": len(pending), "attributes": {"friendly_name": "Pending reminders", "icon": "mdi:alarm-multiple", "unit_of_measurement": "reminders"}})


async def event_listener():
    """Done / Snooze buttons of the notification (mobile_app_notification_action events)."""
    while True:
        try:
            async with session.ws_connect(HA_WS, heartbeat=30) as ws:
                await ws.receive_json()
                await ws.send_json({"type": "auth", "access_token": TOKEN})
                if (await ws.receive_json()).get("type") != "auth_ok":
                    raise RuntimeError("auth failed")
                await ws.send_json({"id": 1, "type": "subscribe_events", "event_type": "mobile_app_notification_action"})
                async for msg in ws:
                    if msg.type != WSMsgType.TEXT:
                        continue
                    data = json.loads(msg.data)
                    action = ((data.get("event") or {}).get("data") or {}).get("action", "")
                    m = re.match(r"^HAREMIND_(DONE|SNOOZE)_([a-f0-9]{8})$", action)
                    if m:
                        rem = next((r for r in reminders if r["id"] == m.group(2)), None)
                        if rem:
                            await (snooze(rem) if m.group(1) == "SNOOZE" else finish(rem))
        except Exception as exc:  # noqa: BLE001
            log.warning("event stream lost (%s) - retrying in 5 s", exc)
        await asyncio.sleep(5)


# ---------------------------------------------------------------- tokens (shortcuts)
def token_hash(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def find_token(raw):
    if not raw:
        return None
    digest, found = token_hash(raw), None
    for t in tokens:
        if hmac.compare_digest(t["hash"], digest):
            found = t
    return found


def public_token(t):
    return {k: v for k, v in t.items() if k != "hash"}


@web.middleware
async def token_guard(request, handler):
    if request.path.startswith("/api/"):
        raw = request.headers.get("Authorization", "").removeprefix("Bearer ").strip() or request.query.get("key", "")
        tok = find_token(raw)
        if not tok:
            raise err(401, "invalid or missing token")
        hits = _rate.setdefault(tok["id"], collections.deque())
        while hits and time.time() - hits[0] > 60:
            hits.popleft()
        if len(hits) >= 20:
            raise err(429, "too many requests - slow down")
        hits.append(time.time())
        request["token"] = tok
    return await handler(request)


@web.middleware
async def ingress_guard(request, handler):
    if not DEV and request.remote not in INGRESS_PEERS:
        raise err(403, "ingress only")
    return await handler(request)


def parse_request(text, extra=None):
    r = nlp.parse(text, now_local())
    if r["error"]:
        raise err(400, r["error"])
    return r


async def create_from_text(text, opts, created_by):
    r = parse_request(text)
    msg = r["text"] or str(text).strip()
    rem = make_reminder(msg, "", r["due"].timestamp(), r["repeat"], opts, created_by)
    await add_reminder(rem)
    return rem


# ----- token API (public port)
async def api_remind(request):
    tok, body = request["token"], await request.json()
    text = str(body.get("text") or "").strip()
    if not text:
        raise err(400, "text required")
    d = tok.get("defaults", {})
    opts = {"phones": d.get("phones"), "speakers": d.get("speakers"), "notify": d.get("notify", True),
            "announce": d.get("announce", False), "live": d.get("live", True)}
    rem = await create_from_text(text, opts, tok["name"])
    tok["last_used"] = int(time.time())
    write_json(TOK_FILE, tokens)
    return web.json_response({"ok": True, "id": rem["id"], "title": rem["title"], "due": describe(rem["due"]), "in_seconds": int(rem["due"] - time.time()), "repeat": rem["repeat"]})


async def api_list(request):
    tok = request["token"]
    return web.json_response([public(r) | {"due_text": describe(r["due"])} for r in reminders if r["created_by"] == tok["name"] and r["state"] == "pending"])


async def api_cancel(request):
    tok = request["token"]
    rem = next((r for r in reminders if r["id"] == request.match_info["id"] and r["created_by"] == tok["name"]), None)
    if not rem:
        raise err(404, "not found")
    await finish(rem, cancelled=True)
    return web.json_response({"ok": True})


# ----- admin API (ingress)
async def h_state(request):
    states = await ha_get("/states")
    try:
        services = await ha_get("/services")
    except web.HTTPException:
        services = []
    notify = sorted(n for d in services if d["domain"] == "notify" for n in d["services"] if PHONE_RE.match(n))
    ent = lambda dom: sorted(({"id": s["entity_id"], "name": s["attributes"].get("friendly_name", s["entity_id"])} for s in states if s["entity_id"].startswith(dom + ".")), key=lambda x: x["name"].lower())
    rows = sorted((public(r) | {"due_text": describe(r["due"])} for r in reminders), key=lambda r: (r["state"] != "pending", r["due"] if r["state"] == "pending" else -(r["fired_at"] or r["created"])))
    return web.json_response({"reminders": rows, "settings": settings, "now": time.time(), "tz": str(tz), "notify": notify,
                              "speakers": ent("media_player"), "tts": ent("tts"), "scripts": ent("script"), "tokens": [public_token(t) for t in tokens],
                              "public_port": PUBLIC_PORT, "credit": {"name": CREDIT, "url": CREDIT_URL}})


async def h_parse(request):
    r = nlp.parse((await request.json()).get("text", ""), now_local())
    return web.json_response({"error": r["error"], "due": r["due"].timestamp() if r["due"] else None,
                              "due_text": describe(r["due"].timestamp()) if r["due"] else "", "title": r["text"], "repeat": r["repeat"]})


async def h_create(request):
    body = await request.json()
    opts = {k: body[k] for k in ("notify", "announce", "live", "phones", "speakers", "script") if k in body}
    if body.get("text") and not body.get("due"):
        rem = await create_from_text(body["text"], opts, "panel")
    else:
        due = float(body.get("due") or 0)
        if due <= time.time():
            raise err(400, "due must be in the future")
        rem = await add_reminder(make_reminder(body.get("title"), body.get("message"), due, None, opts, "panel"))
    return web.json_response(public(rem))


def get_rem(request):
    rem = next((r for r in reminders if r["id"] == request.match_info["id"]), None)
    if not rem:
        raise err(404, "not found")
    return rem


async def h_snooze(request):
    body = await request.json() if request.can_read_body else {}
    await snooze(get_rem(request), body.get("minutes"))
    return web.json_response({"ok": True})


async def h_done(request):
    rem = get_rem(request)
    await finish(rem)
    return web.json_response({"ok": True})


async def h_cancel(request):
    await finish(get_rem(request), cancelled=True)
    return web.json_response({"ok": True})


async def h_delete(request):
    rem = get_rem(request)
    await live_end(rem)
    reminders.remove(rem)
    save()
    await publish_sensors()
    return web.json_response({"ok": True})


async def h_settings(request):
    global settings
    settings = clean_settings(await request.json(), settings)
    write_json(SET_FILE, settings)
    return web.json_response(settings)


async def h_token_create(request):
    body = await request.json()
    name = str(body.get("name") or "").strip()[:40]
    if not name:
        raise err(400, "name required")
    raw = "hr_" + secrets.token_urlsafe(24)
    d = {"phones": clean_phones(body.get("phones")), "speakers": clean_list(body.get("speakers"), "media_player."),
         "notify": bool(body.get("notify", True)), "announce": bool(body.get("announce", False)), "live": bool(body.get("live", True))}
    tok = {"id": uuid.uuid4().hex[:10], "name": name, "hash": token_hash(raw), "prefix": raw[:8], "created": int(time.time()), "last_used": None, "defaults": d}
    tokens.append(tok)
    write_json(TOK_FILE, tokens)
    return web.json_response({**public_token(tok), "token": raw})


async def h_token_delete(request):
    tok = next((t for t in tokens if t["id"] == request.match_info["id"]), None)
    if not tok:
        raise err(404, "not found")
    tokens.remove(tok)
    write_json(TOK_FILE, tokens)
    return web.json_response({"ok": True})


async def h_test(request):
    if not settings["phones"]:
        raise err(400, "pick at least one phone in Settings")
    rem = make_reminder("Test", "HARemindTeo ✅", time.time() + 60, None, {}, "panel")
    for phone in rem["phones"]:
        await safe_post(f"/services/notify/{phone}", {"title": "HARemindTeo", "message": "Test notification ✅"})
    await live_start(rem)
    asyncio.create_task(live_end(rem, 8.0))
    return web.json_response({"ok": True})


async def h_index(request):
    return web.Response(text=(STATIC / "index.html").read_text(), content_type="text/html")


def build_apps():
    ui = web.Application(middlewares=[ingress_guard], client_max_size=256 * 1024)
    ui.add_routes([web.get("/", h_index), web.static("/static", STATIC), web.get("/api/state", h_state), web.post("/api/parse", h_parse),
                   web.post("/api/reminders", h_create), web.post("/api/reminders/{id}/snooze", h_snooze), web.post("/api/reminders/{id}/done", h_done),
                   web.post("/api/reminders/{id}/cancel", h_cancel), web.delete("/api/reminders/{id}", h_delete),
                   web.post("/api/settings", h_settings), web.post("/api/tokens", h_token_create), web.delete("/api/tokens/{id}", h_token_delete),
                   web.post("/api/test", h_test)])
    pub = web.Application(middlewares=[token_guard], client_max_size=64 * 1024)
    pub.add_routes([web.post("/api/remind", api_remind), web.get("/api/reminders", api_list), web.delete("/api/reminders/{id}", api_cancel)])
    return ui, pub


async def main():
    global session
    logging.basicConfig(level=getattr(logging, str(OPTIONS.get("log_level", "info")).upper(), logging.INFO), format="%(asctime)s %(levelname)s %(message)s")
    DATA.mkdir(parents=True, exist_ok=True)
    load_all()
    session = ClientSession(timeout=ClientTimeout(total=30))
    ui, pub = build_apps()
    bound = 0
    for name, app, port in (("panel", ui, INGRESS_PORT), ("token API", pub, PUBLIC_PORT)):
        try:
            runner = web.AppRunner(app)
            await runner.setup()
            await web.TCPSite(runner, "0.0.0.0", port).start()
            bound += 1
        except OSError as exc:
            log.error("Cannot listen on port %s for the %s: %s - change the port in the add-on Network settings.", port, name, exc)
    if not bound:
        raise SystemExit(1)
    log.info("HARemindTeo by %s (%s) - panel :%s, token API :%s", CREDIT, CREDIT_URL, INGRESS_PORT, PUBLIC_PORT)
    await load_timezone()
    for rem in reminders:
        if rem["state"] == "pending":
            asyncio.create_task(live_start(rem))
    asyncio.create_task(scheduler())
    asyncio.create_task(event_listener())
    asyncio.create_task(publish_sensors())
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
