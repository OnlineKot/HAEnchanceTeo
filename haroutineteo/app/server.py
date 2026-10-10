#!/usr/bin/env python3
"""HARoutineTeo - step-based routines for Home Assistant with live progress on the Dynamic Island.
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
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web

CREDIT, CREDIT_URL = "TeodorTeo.com", "https://teodorteo.com"
DATA = Path(os.environ.get("HRT_DATA", "/data"))
STATIC = Path(__file__).parent / "static"
ROUTINES_FILE, SET_FILE, TOK_FILE, RUNS_FILE = DATA / "routines.json", DATA / "settings.json", DATA / "tokens.json", DATA / "runs.json"
INGRESS_PORT = int(os.environ.get("HRT_INGRESS_PORT", 8099))
PUBLIC_PORT = int(os.environ.get("HRT_PUBLIC_PORT", 8768))
INGRESS_PEERS = {"172.30.32.2", "127.0.0.1", "::1"}
DEV = bool(os.environ.get("HRT_DEV"))
HA = os.environ.get("HRT_HA_URL", "http://supervisor/core/api")
HA_WS = (HA[:-4] if HA.endswith("/api") else HA).replace("http", "ws", 1) + "/websocket"
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")

ENTITY_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
SERVICE_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
PHONE_RE = re.compile(r"^mobile_app_[a-z0-9_]{1,60}$")
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
STEP_TYPES = ("service", "scene", "script", "announce", "notify", "wait", "wait_state", "fade", "stop_if")
MAX_STEPS = 60

log = logging.getLogger("haroutineteo")
session: ClientSession = None
routines: list = []
tokens: list = []
states: dict = {}
tz = timezone.utc
runs: dict = {}                         # run id -> live run
history = collections.deque(maxlen=60)  # finished runs (public view)
settings = {"phones": [], "speakers": [], "tts_entity": "", "language": "", "live": True}
_fired: dict = {}                       # time-trigger de-duplication
_state_timers: dict = {}                # (routine id, trigger idx) -> pending "for" timer
_rate: dict = {}


def load_options():
    try:
        return json.loads(Path("/data/options.json").read_text())
    except (OSError, ValueError):
        return {}


OPTIONS = load_options()


class StopRoutine(Exception):
    pass


def err(status, message):
    cls = {400: web.HTTPBadRequest, 401: web.HTTPUnauthorized, 403: web.HTTPForbidden, 404: web.HTTPNotFound,
           429: web.HTTPTooManyRequests, 502: web.HTTPBadGateway}[status]
    return cls(text=json.dumps({"error": message}), content_type="application/json")


# ---------------------------------------------------------------- storage / validation
def write_json(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(path)


def s_(v, n=80):
    return str(v or "")[:n]


def ent(v):
    v = str(v or "").strip().lower()
    return v if ENTITY_RE.match(v) else ""


def fnum(v, default=None, lo=None, hi=None):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    if lo is not None:
        x = max(lo, x)
    if hi is not None:
        x = min(hi, x)
    return x


def clean_phones(v):
    return [p for p in (str(x).removeprefix("notify.") for x in (v or [])) if PHONE_RE.match(p)][:8]


def clean_cond(c):
    if not isinstance(c, dict) or not ent(c.get("entity_id")):
        return None
    op = c.get("op") if c.get("op") in ("=", "!=", ">", "<", "in") else "="
    return {"entity_id": ent(c["entity_id"]), "attribute": s_(c.get("attribute"), 40), "op": op, "value": s_(c.get("value"), 80)}


def clean_step(raw):
    t = raw.get("type")
    if t not in STEP_TYPES:
        return None
    st = {"id": re.sub(r"[^a-z0-9]", "", s_(raw.get("id"), 12).lower()) or uuid.uuid4().hex[:8], "type": t, "label": s_(raw.get("label"), 60),
          "when": clean_cond(raw.get("when"))}
    if t == "service":
        svc = s_(raw.get("service"), 80).lower()
        if not SERVICE_RE.match(svc):
            return None
        data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
        st.update(service=svc, entity_id=ent(raw.get("entity_id")), data=data if len(json.dumps(data)) < 3000 else {})
    elif t in ("scene", "script"):
        e = ent(raw.get("entity_id"))
        if not e.startswith(t + "."):
            return None
        st["entity_id"] = e
    elif t == "announce":
        text = s_(raw.get("text"), 400).strip()
        if not text:
            return None
        st.update(text=text, speakers=[x for x in (str(y) for y in (raw.get("speakers") or [])) if x.startswith("media_player.") and ENTITY_RE.match(x)][:20],
                  volume=fnum(raw.get("volume"), None, 0, 100))
    elif t == "notify":
        text = s_(raw.get("text"), 300).strip()
        if not text:
            return None
        st.update(text=text, title=s_(raw.get("title"), 80), phones=clean_phones(raw.get("phones")))
    elif t == "wait":
        st["seconds"] = fnum(raw.get("seconds"), None, 1, 86400)
        if st["seconds"] is None:
            return None
    elif t == "wait_state":
        e = ent(raw.get("entity_id"))
        if not e:
            return None
        st.update(entity_id=e, state=s_(raw.get("state"), 60), timeout=fnum(raw.get("timeout"), 600, 1, 86400),
                  on_timeout="stop" if raw.get("on_timeout") == "stop" else "continue")
    elif t == "fade":
        e = ent(raw.get("entity_id"))
        to = fnum(raw.get("to"), None, 0, 100)
        if not e or to is None:
            return None
        st.update(entity_id=e, kind="volume" if raw.get("kind") == "volume" else "light", to=to, seconds=fnum(raw.get("seconds"), 60, 2, 7200),
                  **{"from": fnum(raw.get("from"), None, 0, 100)})
    elif t == "stop_if":
        st["when"] = clean_cond(raw.get("cond") or raw.get("when"))
        if not st["when"]:
            return None
    return st


def clean_trigger(raw):
    t = raw.get("type")
    if t == "time":
        at = s_(raw.get("at"), 5)
        if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", at):
            return None
        days = sorted({int(d) for d in (raw.get("days") or [0, 1, 2, 3, 4, 5, 6]) if str(d).isdigit() and 0 <= int(d) <= 6}) or [0, 1, 2, 3, 4, 5, 6]
        return {"type": "time", "at": at, "days": days}
    if t == "state":
        e = ent(raw.get("entity_id"))
        if not e:
            return None
        return {"type": "state", "entity_id": e, "to": s_(raw.get("to"), 60), "from": s_(raw.get("from"), 60), "for": fnum(raw.get("for"), 0, 0, 86400)}
    return None


def clean_routine(raw, old=None):
    old = old or {}
    name = s_(raw.get("name"), 40).strip()
    if not name:
        raise err(400, "name required")
    steps = [x for x in (clean_step(s) for s in (raw.get("steps") or [])[:MAX_STEPS] if isinstance(s, dict)) if x]
    seen = set()
    for st in steps:
        while st["id"] in seen:
            st["id"] = uuid.uuid4().hex[:8]
        seen.add(st["id"])
    color = s_(raw.get("color"), 7)
    icon = s_(raw.get("icon"), 60)
    return {"id": old.get("id") or uuid.uuid4().hex[:8], "name": name, "icon": icon if re.match(r"^mdi:[a-z0-9-]{1,60}$", icon) else "mdi:play-circle",
            "color": color if HEX_RE.match(color) else "#03A9F4", "enabled": bool(raw.get("enabled", True)),
            "mode": "restart" if raw.get("mode") == "restart" else "single", "live": bool(raw.get("live", True)),
            "phones": clean_phones(raw.get("phones")), "steps": steps,
            "triggers": [x for x in (clean_trigger(t) for t in (raw.get("triggers") or [])[:20] if isinstance(t, dict)) if x],
            "created": old.get("created") or time.time(), "last_run": old.get("last_run"), "runs": old.get("runs", 0)}


def load_all():
    global routines, tokens, settings
    for var, path in (("routines", ROUTINES_FILE), ("tokens", TOK_FILE)):
        try:
            globals()[var] = json.loads(path.read_text())
        except (OSError, ValueError):
            globals()[var] = []
    try:
        settings.update(json.loads(SET_FILE.read_text()))
    except (OSError, ValueError):
        pass
    try:
        for r in json.loads(RUNS_FILE.read_text()):
            history.append(r)
    except (OSError, ValueError):
        pass


# ---------------------------------------------------------------- Home Assistant
def ha_headers():
    return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


async def ha_post(path, data):
    async with session.post(f"{HA}{path}", headers=ha_headers(), json=data) as r:
        if r.status >= 400:
            raise err(502, f"Home Assistant {r.status}: {(await r.text())[:150]}")


async def ha_get(path):
    async with session.get(f"{HA}{path}", headers=ha_headers()) as r:
        if r.status >= 400:
            raise err(502, f"Home Assistant {r.status}")
        return await r.json()


async def safe_post(path, data):
    try:
        await ha_post(path, data)
    except web.HTTPException as exc:
        log.warning("%s failed: %s", path, exc.text)


def put_state(st):
    states[st["entity_id"]] = {"s": st["state"], "a": st.get("attributes") or {}}


def now_local():
    return datetime.now(tz)


async def ha_listener():
    """One WebSocket to HA: live state cache + entity triggers."""
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
                        new, old = ev.get("new_state"), ev.get("old_state")
                        if new is None:
                            states.pop(ev["entity_id"], None)
                            continue
                        put_state(new)
                        await on_state_change(ev["entity_id"], (old or {}).get("state"), new["state"])
        except Exception as exc:  # noqa: BLE001
            log.warning("HA stream lost (%s) - retrying in 5 s", exc)
        await asyncio.sleep(5)


# ---------------------------------------------------------------- conditions
def cond_true(c):
    st = states.get(c["entity_id"])
    if st is None:
        return False
    cur = st["a"].get(c["attribute"]) if c.get("attribute") else st["s"]
    cur, val, op = str(cur), str(c["value"]), c["op"]
    if op == "=":
        return cur == val
    if op == "!=":
        return cur != val
    if op == "in":
        return cur in [x.strip() for x in val.split(",")]
    a, b = fnum(cur), fnum(val)
    if a is None or b is None:
        return False
    return a > b if op == ">" else a < b


# ---------------------------------------------------------------- Live Activity (step progress)
def phones_of(r):
    return r["phones"] or settings["phones"]


def step_text(st):
    if st.get("label"):
        return st["label"]
    t = st["type"]
    return {"service": st.get("service", ""), "scene": st.get("entity_id", ""), "script": st.get("entity_id", ""),
            "announce": "📣 " + st.get("text", "")[:40], "notify": "🔔 " + st.get("text", "")[:40], "wait": f"⏳ {int(st.get('seconds', 0))} s",
            "wait_state": f"⏳ {st.get('entity_id', '')} → {st.get('state', '')}", "fade": f"🌅 {st.get('entity_id', '')} → {st.get('to', '')}%",
            "stop_if": "⛔ stop-if"}.get(t, t)


async def live_update(run, r, message, done=False, wait_until=None, failed=False):
    if not (r["live"] and settings["live"]) or not phones_of(r):
        return
    total = max(1, len(r["steps"]))
    data = {"tag": f"routine_{r['id']}", "live_update": True, "notification_icon": r["icon"], "notification_icon_color": "#F44336" if failed else r["color"],
            "color": "#F44336" if failed else r["color"], "progress": total if done else min(run["step"], total), "progress_max": total,
            "critical_text": "✅" if done and not failed else "⚠" if failed else f"{run['step'] + 1}/{total}", "relevance_score": 0.8}
    if wait_until:
        data.update(chronometer=True, when=int(wait_until), when_relative=False)
    if run.get("live_started"):
        data["silent"], data["alert_once"] = True, True
    for phone in phones_of(r):
        await safe_post(f"/services/notify/{phone}", {"title": r["name"], "message": message, "data": data})
    run["live_started"] = True


async def live_clear(run, r, delay=0.0):
    if not run.get("live_started"):
        return
    if delay:
        await asyncio.sleep(delay)
    for phone in phones_of(r):
        await safe_post(f"/services/notify/{phone}", {"message": "clear_notification", "data": {"tag": f"routine_{r['id']}"}})


# ---------------------------------------------------------------- steps
async def speak(st, r):
    speakers = st["speakers"] or settings["speakers"]
    if not speakers:
        return
    if st.get("volume") is not None:
        await safe_post("/services/media_player/volume_set", {"entity_id": speakers, "volume_level": round(st["volume"] / 100, 3)})
    tts = settings["tts_entity"] or next((e for e in states if e.startswith("tts.")), "")
    if not tts:
        raise err(400, "no TTS engine available")
    mid = f"media-source://tts/{tts}?message={quote(st['text'])}" + (f"&language={quote(settings['language'])}" if settings["language"] else "")
    await ha_post("/services/media_player/play_media", {"entity_id": speakers, "media_content_id": mid, "media_content_type": "music", "announce": True})


def level_of(eid, kind):
    st = states.get(eid)
    if not st:
        return 0.0
    if kind == "light":
        return round((st["a"].get("brightness") or (255 if st["s"] == "on" else 0)) / 255 * 100, 1) if st["s"] == "on" else 0.0
    return round(float(st["a"].get("volume_level") or 0) * 100, 1)


async def do_fade(st):
    eid, kind = st["entity_id"], st["kind"]
    start = st.get("from")
    if start is None:
        start = level_of(eid, kind)
    n = max(1, int(st["seconds"] / 2))
    for i in range(1, n + 1):
        v = start + (st["to"] - start) * i / n
        if kind == "light":
            if v < 1 and i == n:
                await ha_post("/services/light/turn_off", {"entity_id": eid, "transition": 2})
            else:
                await ha_post("/services/light/turn_on", {"entity_id": eid, "brightness_pct": max(1, int(round(v))), "transition": 2})
        else:
            await ha_post("/services/media_player/volume_set", {"entity_id": eid, "volume_level": round(max(0, min(100, v)) / 100, 3)})
        await asyncio.sleep(st["seconds"] / n)


async def do_step(st, run, r):
    t = st["type"]
    if t == "service":
        domain, service = st["service"].split(".", 1)
        data = dict(st.get("data") or {})
        if st.get("entity_id"):
            data["entity_id"] = st["entity_id"]
        await ha_post(f"/services/{domain}/{service}", data)
    elif t in ("scene", "script"):
        await ha_post(f"/services/{t}/turn_on", {"entity_id": st["entity_id"]})
    elif t == "announce":
        await speak(st, r)
    elif t == "notify":
        for phone in st["phones"] or phones_of(r):
            await ha_post(f"/services/notify/{phone}", {"title": st["title"] or r["name"], "message": st["text"]})
    elif t == "wait":
        until = time.time() + st["seconds"]
        run["waiting_until"] = until
        await live_update(run, r, f"{run['step'] + 1}/{len(r['steps'])} · {step_text(st)}", wait_until=until if st["seconds"] >= 15 else None)
        await asyncio.sleep(st["seconds"])
        run["waiting_until"] = None
    elif t == "wait_state":
        deadline = time.time() + st["timeout"]
        run["waiting_until"] = deadline
        while states.get(st["entity_id"], {}).get("s") != st["state"]:
            if time.time() > deadline:
                run["log"].append({"ts": time.time(), "msg": f"timeout waiting for {st['entity_id']} = {st['state']}"})
                if st["on_timeout"] == "stop":
                    raise StopRoutine()
                break
            await asyncio.sleep(0.5)
        run["waiting_until"] = None
    elif t == "fade":
        await do_fade(st)
    elif t == "stop_if":
        if cond_true(st["when"]):
            raise StopRoutine()


# ---------------------------------------------------------------- runs
def public_run(run):
    return {k: run[k] for k in ("id", "routine_id", "name", "source", "started", "status", "step", "total", "ended", "log", "waiting_until", "current")}


async def execute(run, r):
    run["status"] = "running"
    final_msg, failed = "✅ Done", False
    st = {}
    try:
        steps = r["steps"]
        for i, st in enumerate(steps):
            run["step"], run["current"] = i, step_text(st)
            if st.get("when") and not cond_true(st["when"]):
                run["log"].append({"ts": time.time(), "msg": f"skipped: {step_text(st)}"})
                continue
            if st["type"] != "wait":                      # waits post their own update (with a countdown)
                await live_update(run, r, f"{i + 1}/{len(steps)} · {step_text(st)}")
            try:
                await do_step(st, run, r)
                run["log"].append({"ts": time.time(), "msg": f"ok: {step_text(st)}"})
            except web.HTTPException as exc:
                run["log"].append({"ts": time.time(), "msg": f"ERROR {step_text(st)}: {json.loads(exc.text).get('error', exc.reason)}"})
                raise
        run["step"] = len(steps)
        run["status"] = "done"
    except StopRoutine:
        run["status"], final_msg = "stopped", "⛔ " + (st.get("label") or "Stopped")
        run["log"].append({"ts": time.time(), "msg": "stopped by condition"})
    except asyncio.CancelledError:
        run["status"], final_msg = "cancelled", "⛔ Stopped"
        raise
    except Exception as exc:  # noqa: BLE001
        run["status"], failed, final_msg = "error", True, "⚠ " + str(exc)[:80]
        log.warning("routine %s failed: %s", r["name"], exc)
    finally:
        run["ended"] = time.time()
        run["current"] = ""
        runs.pop(run["id"], None)
        history.append(public_run(run))
        r["last_run"], r["runs"] = run["ended"], r.get("runs", 0) + 1
        write_json(ROUTINES_FILE, routines)
        write_json(RUNS_FILE, list(history))
        asyncio.create_task(finish_up(run, r, final_msg, failed))


async def finish_up(run, r, msg, failed):
    await live_update(run, r, msg, done=True, failed=failed)
    await safe_post("/events/haroutineteo_finished", {"id": r["id"], "name": r["name"], "status": run["status"], "source": run["source"]})
    await publish()
    await live_clear(run, r, delay=6.0)


async def publish():
    running = [x for x in runs.values()]
    await safe_post("/states/sensor.haroutineteo_running", {"state": len(running), "attributes": {
        "friendly_name": "HARoutine running", "icon": "mdi:play-circle", "routines": [x["name"] for x in running]}})
    for r in routines:
        on = any(x["routine_id"] == r["id"] for x in running)
        await safe_post(f"/states/binary_sensor.haroutineteo_{re.sub(r'[^a-z0-9]+', '_', r['name'].lower())[:30].strip('_') or r['id']}", {
            "state": "on" if on else "off", "attributes": {"friendly_name": f"{r['name']} (routine)", "icon": r["icon"], "routine_id": r["id"]}})


async def start_run(r, source):
    existing = next((x for x in runs.values() if x["routine_id"] == r["id"]), None)
    if existing:
        if r["mode"] == "single":
            return None
        existing["task"].cancel()
        await asyncio.sleep(0)
    run = {"id": uuid.uuid4().hex[:8], "routine_id": r["id"], "name": r["name"], "source": source, "started": time.time(), "status": "starting",
           "step": 0, "total": len(r["steps"]), "ended": None, "log": [], "waiting_until": None, "current": "", "task": None}
    runs[run["id"]] = run
    run["task"] = asyncio.create_task(execute(run, r))
    await publish()
    return run


# ---------------------------------------------------------------- triggers
async def on_state_change(eid, old, new):
    for r in routines:
        if not r["enabled"]:
            continue
        for i, t in enumerate(r["triggers"]):
            if t["type"] != "state" or t["entity_id"] != eid:
                continue
            key = (r["id"], i)
            timer = _state_timers.pop(key, None)
            if timer:
                timer.cancel()
            if old == new or (t["to"] and new != t["to"]) or (t["from"] and old != t["from"]):
                continue
            if t["for"]:
                _state_timers[key] = asyncio.create_task(delayed_trigger(r, t, key))
            else:
                await start_run(r, f"state:{eid}")


async def delayed_trigger(r, t, key):
    await asyncio.sleep(t["for"])
    if not t["to"] or states.get(t["entity_id"], {}).get("s") == t["to"]:
        _state_timers.pop(key, None)
        await start_run(r, f"state:{t['entity_id']}")


async def time_loop():
    while True:
        now = now_local()
        stamp = now.strftime("%Y-%m-%d %H:%M")
        for r in routines:
            if not r["enabled"]:
                continue
            for i, t in enumerate(r["triggers"]):
                if t["type"] == "time" and t["at"] == now.strftime("%H:%M") and now.weekday() in t["days"] and _fired.get((r["id"], i)) != stamp:
                    _fired[(r["id"], i)] = stamp
                    await start_run(r, f"time:{t['at']}")
        await asyncio.sleep(10)


# ---------------------------------------------------------------- tokens (Shortcuts)
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


@web.middleware
async def token_guard(request, handler):
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


def find_routine(ref):
    ref = str(ref or "").strip().lower()
    return next((r for r in routines if r["id"] == ref or r["name"].lower() == ref), None)


def allowed(tok, r):
    return not tok.get("routines") or r["id"] in tok["routines"]


async def api_run(request):
    tok, body = request["token"], await request.json()
    r = find_routine(body.get("routine"))
    if not r or not allowed(tok, r):
        raise err(404, "routine not found")
    if not r["enabled"]:
        raise err(400, "routine is disabled")
    run = await start_run(r, f"token:{tok['name']}")
    tok["last_used"] = int(time.time())
    write_json(TOK_FILE, tokens)
    return web.json_response({"ok": True, "started": bool(run), "run": run["id"] if run else None, "note": "" if run else "already running"})


async def api_stop(request):
    tok, body = request["token"], await request.json()
    r = find_routine(body.get("routine"))
    if not r or not allowed(tok, r):
        raise err(404, "routine not found")
    n = 0
    for run in [x for x in runs.values() if x["routine_id"] == r["id"]]:
        run["task"].cancel()
        n += 1
    return web.json_response({"ok": True, "stopped": n})


async def api_list(request):
    tok = request["token"]
    return web.json_response([{"id": r["id"], "name": r["name"], "enabled": r["enabled"], "running": any(x["routine_id"] == r["id"] for x in runs.values())}
                              for r in routines if allowed(tok, r)])


# ---------------------------------------------------------------- admin API
async def h_state(request):
    sts = await ha_get("/states")
    try:
        services = await ha_get("/services")
    except web.HTTPException:
        services = []
    notify = sorted(n for d in services if d["domain"] == "notify" for n in d["services"] if PHONE_RE.match(n))
    svc = sorted(f"{d['domain']}.{n}" for d in services for n in d["services"] if d["domain"] not in ("notify",))
    pick = lambda dom: sorted(({"id": s["entity_id"], "name": s["attributes"].get("friendly_name", s["entity_id"])} for s in sts if s["entity_id"].startswith(dom + ".")), key=lambda x: x["name"].lower())
    ents = sorted(({"id": s["entity_id"], "name": s["attributes"].get("friendly_name", s["entity_id"])} for s in sts), key=lambda x: x["id"])[:4000]
    return web.json_response({"routines": [r | {"running": any(x["routine_id"] == r["id"] for x in runs.values())} for r in routines],
                              "runs": [public_run(x) for x in runs.values()], "history": list(reversed(history))[:25], "settings": settings, "now": time.time(),
                              "tz": str(tz), "notify": notify, "speakers": pick("media_player"), "tts": pick("tts"), "entities": ents, "services": svc,
                              "tokens": [{k: v for k, v in t.items() if k not in ("hash", "secret")} | {"can_copy": bool(t.get("secret"))} for t in tokens], "public_port": PUBLIC_PORT,
                              "credit": {"name": CREDIT, "url": CREDIT_URL}})


async def h_save(request):
    raw = await request.json()
    old = next((r for r in routines if r["id"] == raw.get("id")), None)
    r = clean_routine(raw, old)
    if old:
        routines[routines.index(old)] = r
    else:
        routines.append(r)
    write_json(ROUTINES_FILE, routines)
    await publish()
    return web.json_response(r)


def get_routine(request):
    r = next((x for x in routines if x["id"] == request.match_info["id"]), None)
    if not r:
        raise err(404, "not found")
    return r


async def h_delete(request):
    r = get_routine(request)
    for run in [x for x in runs.values() if x["routine_id"] == r["id"]]:
        run["task"].cancel()
    routines.remove(r)
    write_json(ROUTINES_FILE, routines)
    return web.json_response({"ok": True})


async def h_run(request):
    r = get_routine(request)
    run = await start_run(r, "panel")
    return web.json_response({"ok": True, "started": bool(run)})


async def h_stop(request):
    r = get_routine(request)
    n = 0
    for run in [x for x in runs.values() if x["routine_id"] == r["id"]]:
        run["task"].cancel()
        n += 1
    return web.json_response({"ok": True, "stopped": n})


async def h_step_test(request):
    """Run a single step right now (to try it out while editing)."""
    raw = await request.json()
    st = clean_step(raw.get("step") or {})
    if not st:
        raise err(400, "invalid step")
    if st["type"] in ("wait", "fade", "wait_state"):
        raise err(400, "waits and fades cannot be tested on their own")
    r = {"name": "test", "phones": [], "steps": [st], "live": False, "icon": "mdi:play-circle", "color": "#03A9F4", "id": "test"}
    await do_step(st, {"step": 0, "log": []}, r)
    return web.json_response({"ok": True})


async def h_settings(request):
    raw = await request.json()
    settings["phones"] = clean_phones(raw.get("phones", settings["phones"]))
    settings["speakers"] = [x for x in raw.get("speakers", settings["speakers"]) if str(x).startswith("media_player.") and ENTITY_RE.match(str(x))][:20]
    for k in ("tts_entity", "language"):
        if k in raw:
            settings[k] = str(raw[k] or "")[:60] if re.match(r"^[A-Za-z0-9_.\-]*$", str(raw[k] or "")) else ""
    if "live" in raw:
        settings["live"] = bool(raw["live"])
    write_json(SET_FILE, settings)
    return web.json_response(settings)


async def h_token_create(request):
    body = await request.json()
    name = s_(body.get("name"), 40).strip()
    if not name:
        raise err(400, "name required")
    raw = "hrt_" + secrets.token_urlsafe(24)
    tok = {"id": uuid.uuid4().hex[:10], "name": name, "hash": token_hash(raw), "secret": raw, "prefix": raw[:8], "created": int(time.time()), "last_used": None,
           "routines": [x for x in (body.get("routines") or []) if any(r["id"] == x for r in routines)]}
    tokens.append(tok)
    write_json(TOK_FILE, tokens)
    return web.json_response({**{k: v for k, v in tok.items() if k not in ("hash", "secret")}, "token": raw})


async def h_token_secret(request):
    tok = next((t for t in tokens if t["id"] == request.match_info["id"]), None)
    if not tok or not tok.get("secret"):
        raise err(404, "token was created before copying was possible - revoke it and create a new one")
    return web.json_response({"token": tok["secret"]})


async def h_token_delete(request):
    tok = next((t for t in tokens if t["id"] == request.match_info["id"]), None)
    if not tok:
        raise err(404, "not found")
    tokens.remove(tok)
    write_json(TOK_FILE, tokens)
    return web.json_response({"ok": True})


TEMPLATES = {
    "goodnight": {"name": "Dobranoc", "icon": "mdi:weather-night", "color": "#5C6BC0", "steps": [
        {"type": "announce", "text": "Dobranoc. Za chwilę wygaszam światła."}, {"type": "wait", "seconds": 5},
        {"type": "fade", "entity_id": "light.salon", "kind": "light", "to": 0, "seconds": 60, "label": "Wygaszam salon"},
        {"type": "service", "service": "light.turn_off", "entity_id": "light.korytarz", "label": "Gaszę korytarz"}]},
    "leaving": {"name": "Wychodzę", "icon": "mdi:door", "color": "#FF9800", "steps": [
        {"type": "stop_if", "cond": {"entity_id": "binary_sensor.drzwi", "op": "=", "value": "on"}, "label": "Stop, jeśli drzwi otwarte"},
        {"type": "service", "service": "light.turn_off", "entity_id": "light.salon", "label": "Gaszę światła"},
        {"type": "announce", "text": "Do zobaczenia!"}]},
    "movie": {"name": "Seans", "icon": "mdi:movie-open", "color": "#E91E63", "steps": [
        {"type": "fade", "entity_id": "light.salon", "kind": "light", "from": None, "to": 15, "seconds": 20, "label": "Przyciemniam"},
        {"type": "notify", "text": "Seans zaczyna się 🍿"}]},
}


async def h_template(request):
    name = (await request.json()).get("template")
    t = TEMPLATES.get(name)
    if not t:
        raise err(400, "unknown template")
    r = clean_routine({**t, "enabled": True, "live": True})
    routines.append(r)
    write_json(ROUTINES_FILE, routines)
    return web.json_response(r)


async def h_index(request):
    return web.Response(text=(STATIC / "index.html").read_text(), content_type="text/html")


def build_apps():
    ui = web.Application(middlewares=[ingress_guard], client_max_size=512 * 1024)
    ui.add_routes([web.get("/", h_index), web.static("/static", STATIC), web.get("/api/state", h_state), web.post("/api/routines", h_save),
                   web.delete("/api/routines/{id}", h_delete), web.post("/api/routines/{id}/run", h_run), web.post("/api/routines/{id}/stop", h_stop),
                   web.post("/api/step/test", h_step_test), web.post("/api/settings", h_settings), web.post("/api/tokens", h_token_create),
                   web.get("/api/tokens/{id}/secret", h_token_secret), web.delete("/api/tokens/{id}", h_token_delete), web.post("/api/templates", h_template)])
    pub = web.Application(middlewares=[token_guard], client_max_size=64 * 1024)
    pub.add_routes([web.post("/api/run", api_run), web.post("/api/stop", api_stop), web.get("/api/routines", api_list)])
    return ui, pub


async def main():
    global session, tz
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
    try:
        tz = ZoneInfo((await ha_get("/config")).get("time_zone", "UTC"))
    except Exception:  # noqa: BLE001
        tz = timezone.utc
    log.info("HARoutineTeo by %s (%s) - panel :%s, token API :%s, %d routines", CREDIT, CREDIT_URL, INGRESS_PORT, PUBLIC_PORT, len(routines))
    asyncio.create_task(ha_listener())
    asyncio.create_task(time_loop())
    asyncio.create_task(publish())
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
