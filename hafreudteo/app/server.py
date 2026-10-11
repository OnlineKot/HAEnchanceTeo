#!/usr/bin/env python3
"""HAFreudTeo - a small cat-care companion for Home Assistant (feeding, water, litter, health reminders, weight).
Panel only through ingress; optional token endpoint for Shortcuts. Low memory: aiohttp only, no background polling of HA.
By TeodorTeo.com (https://teodorteo.com)."""
import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web

CREDIT, CREDIT_URL = "TeodorTeo.com", "https://teodorteo.com"
DATA = Path(os.environ.get("HFT_DATA", "/data"))
OPTIONS_FILE = Path(os.environ.get("HFT_OPTIONS", "/data/options.json"))
STATIC = Path(__file__).parent / "static"
INGRESS_PORT = int(os.environ.get("HFT_INGRESS_PORT", 8099))
API_PORT = int(os.environ.get("HFT_API_PORT", 8771))
INGRESS_PEERS = {"172.30.32.2", "127.0.0.1", "::1"}
DEV = bool(os.environ.get("HFT_DEV"))
HA = os.environ.get("HFT_HA_URL", "http://supervisor/core/api")
HA_WS = os.environ.get("HFT_HA_WS") or (HA[:-4] if HA.endswith("/api") else HA).replace("http", "ws", 1) + "/websocket"
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
STORE, TOK_FILE, AVATAR = DATA / "freud.json", DATA / "tokens.json", DATA / "avatar.bin"
MAX_EVENTS, DUP_MIN = 3000, 20
BEH_KINDS = ["vomit", "appetite", "limp", "hiding", "thirst", "litter", "night", "sneeze", "other"]
NEG = {"unavailable", "unknown", "off", "none", "clear", "idle", "0", "", "not_home", "no_motion", "false"}
TICK = int(os.environ.get("HFT_TICK", 60))

log = logging.getLogger("hafreudteo")

DEFAULT_CFG = {
    "name": "", "birthday": "", "birthday_approx": False, "senior_applied": False, "bday_notified": 0, "portion_g": 40, "quiet": ["22:00", "07:00"], "repeat_min": 60, "who": "",
    "cams": {"entities": [], "cooldown_min": 10},
    "tasks": {
        "feed": {"enabled": True, "remind": True, "times": ["07:00", "18:00"], "grace_min": 30},
        "water": {"enabled": True, "remind": False, "every_h": 24},
        "litter": {"enabled": True, "remind": True, "every_h": 48},
        "litter_full": {"enabled": True, "remind": False, "every_h": 336},
        "flea": {"enabled": True, "remind": True, "every_h": 720},
        "deworm": {"enabled": True, "remind": True, "every_h": 2160},
        "vaccine": {"enabled": True, "remind": True, "every_h": 8760},
        "vet": {"enabled": True, "remind": True, "every_h": 8760},
    },
}
TASK_IDS = list(DEFAULT_CFG["tasks"])
LABELS = {
    "pl": {"feed": "Karmienie", "water": "Woda", "garden_cat": "Kot w ogrodzie", "behavior": "Zachowanie", "litter": "Kuweta", "litter_full": "Kuweta - pełna wymiana", "flea": "Pchły i kleszcze",
           "deworm": "Odrobaczanie", "vaccine": "Szczepienie", "vet": "Wizyta u weterynarza", "weight": "Waga",
           "done": "Zrobione", "remind": "{cat}: {task}", "fed_today": "dziś {n}/{m}", "ago": "{x} temu", "never": "brak wpisów",
           "recent": "{cat} był karmiony {m} min temu ({who}).", "ok": "Wszystko w porządku."},
    "en": {"feed": "Feeding", "water": "Water", "garden_cat": "Cat in the garden", "behavior": "Behaviour", "litter": "Litter box", "litter_full": "Litter box - full change", "flea": "Flea and tick",
           "deworm": "Deworming", "vaccine": "Vaccination", "vet": "Vet visit", "weight": "Weight",
           "done": "Done", "remind": "{cat}: {task}", "fed_today": "today {n}/{m}", "ago": "{x} ago", "never": "no entries",
           "recent": "{cat} was fed {m} min ago ({who}).", "ok": "All good."},
}

session = None
tz = timezone.utc
lang = "en"
cfg = json.loads(json.dumps(DEFAULT_CFG))
events = []                 # {id, ts, task, who, note, value}
tokens = []                 # {id, name, hash, secret, created, last}
notif = {}                  # nonce -> {task, svc, ts}
sent = {}                   # task -> {"ts": last notification time, "n": count}
OPT = {}
tok_rate = {}
listener_task = None
_pub_lock = asyncio.Lock()


class Conflict(Exception):
    pass


def err(status, message, **extra):
    cls = {400: web.HTTPBadRequest, 401: web.HTTPUnauthorized, 403: web.HTTPForbidden, 404: web.HTTPNotFound, 409: web.HTTPConflict,
           413: web.HTTPRequestEntityTooLarge, 429: web.HTTPTooManyRequests, 502: web.HTTPBadGateway}[status]
    return cls(text=json.dumps({"error": message, **extra}), content_type="application/json")


def L(key, **kw):
    return LABELS.get(lang, LABELS["en"]).get(key, LABELS["en"].get(key, key)).format(**kw)


def options():
    global OPT
    try:
        OPT = json.loads(OPTIONS_FILE.read_text())
    except (OSError, ValueError):
        OPT = {}
    return OPT


def notify_services():
    out = []
    for s in OPT.get("notify_services") or []:
        s = str(s).strip().removeprefix("notify.")
        if re.fullmatch(r"[a-z0-9_]{1,60}", s):
            out.append(s)
    return out[:6]


def cat_name():
    return (cfg.get("name") or OPT.get("cat_name") or "Freud").strip()[:30] or "Freud"


def slug():
    s = unicodedata.normalize("NFKD", cat_name()).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_") or "cat"


# ---------------------------------------------------------------- storage
def write_json(path, obj, private=False):
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600 if private else 0o644)
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    tmp.replace(path)


def save():
    write_json(STORE, {"cfg": cfg, "events": events})


def load():
    global cfg, events, tokens
    try:
        d = json.loads(STORE.read_text())
        merged = json.loads(json.dumps(DEFAULT_CFG))
        c = d.get("cfg", {})
        for k in ("name", "birthday", "birthday_approx", "senior_applied", "bday_notified", "portion_g", "quiet", "repeat_min", "who"):
            if k in c:
                merged[k] = c[k]
        merged["cams"].update({k: v for k, v in (c.get("cams") or {}).items() if k in merged["cams"]})
        for t in TASK_IDS:
            merged["tasks"][t].update({k: v for k, v in (c.get("tasks", {}).get(t) or {}).items() if k in merged["tasks"][t]})
        cfg, events = merged, [e for e in d.get("events", []) if isinstance(e, dict) and "ts" in e and "task" in e][-MAX_EVENTS:]
    except (OSError, ValueError):
        pass
    try:
        tokens = json.loads(TOK_FILE.read_text())
    except (OSError, ValueError):
        tokens = []


# ---------------------------------------------------------------- logic
def hm(s):
    h, m = str(s).split(":")
    return int(h), int(m)


def at(day, hhmm):
    h, m = hm(hhmm)
    return day.replace(hour=h, minute=m, second=0, microsecond=0)


def in_quiet(now):
    try:
        a, b = at(now, cfg["quiet"][0]), at(now, cfg["quiet"][1])
    except (ValueError, IndexError):
        return False
    return (a <= now or now < b) if a > b else a <= now < b


def last_of(task):
    for e in reversed(events):
        if e["task"] == task:
            return e
    return None


def status_of(tid, now):
    t = cfg["tasks"][tid]
    last = last_of(tid)
    out = {"id": tid, "enabled": t["enabled"], "remind": t["remind"], "last": last["ts"] if last else None, "who": last["who"] if last else "", "state": "ok"}
    if tid == "feed":
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        fed = sum(1 for e in events if e["task"] == "feed" and e["ts"] >= midnight.timestamp())
        times = t["times"]
        passed = sum(1 for x in times if at(now, x) + timedelta(minutes=t["grace_min"]) <= now)
        nxt = next((at(now, x) for x in times if at(now, x) > now), None) or (at(now + timedelta(days=1), times[0]) if times else None)
        out.update(fed_today=fed, meals=len(times), passed=passed, next=nxt.timestamp() if nxt else None, state="due" if fed < passed else "ok")
    else:
        if last is None:
            out["state"] = "new"
        else:
            due = last["ts"] + t["every_h"] * 3600
            out.update(due_at=due, state="due" if now.timestamp() >= due else "ok")
    return out


def all_status(now=None):
    now = now or datetime.now(tz)
    return [status_of(t, now) for t in TASK_IDS if cfg["tasks"][t]["enabled"]]


def age_years(now=None):
    b = cfg.get("birthday")
    if not b:
        return None
    try:
        d = datetime.strptime(b, "%Y-%m-%d")
    except ValueError:
        return None
    n = now or datetime.now(tz)
    return n.year - d.year - ((n.month, n.day) < (d.month, d.day))


def is_senior():
    a = age_years()
    return a is not None and a >= 11


def apply_age_option():
    """First start: turn the 'cat_age_years' option into an approximate birthday, and apply gentle senior defaults once."""
    changed = False
    try:
        yrs = int(OPT.get("cat_age_years") or 0)
    except (TypeError, ValueError):
        yrs = 0
    md = re.fullmatch(r"(\d{2})-(\d{2})", str(OPT.get("cat_birthday") or ""))
    if (not cfg.get("birthday") or cfg.get("birthday_approx")) and yrs > 0:
        n = datetime.now(tz)
        mo, dy = (int(md.group(1)), int(md.group(2))) if md else (n.month, min(n.day, 28))
        year = n.year - yrs - (1 if md and (mo, dy) > (n.month, n.day) else 0)   # age today == yrs, birthday still ahead this year
        try:
            datetime(year, mo, dy)
            b = f"{year:04d}-{mo:02d}-{dy:02d}"
        except ValueError:
            b = f"{year:04d}-{n.month:02d}-{min(n.day, 28):02d}"
        if b != cfg.get("birthday"):
            cfg["birthday"], changed = b, True
        cfg["birthday_approx"] = not md      # only the year is a guess when the real day and month are known
        changed = True
    if is_senior() and not cfg.get("senior_applied"):
        cfg["tasks"]["vet"]["every_h"] = min(cfg["tasks"]["vet"]["every_h"], 4368)   # senior cats: check-up every 6 months
        cfg["senior_applied"], changed = True, True
    if changed:
        save()


def weights():
    return [(e["ts"], e["value"]) for e in events if e["task"] == "weight" and isinstance(e.get("value"), (int, float))]


def birthday_info(now=None):
    b = cfg.get("birthday")
    if not b:
        return None
    n = now or datetime.now(tz)
    try:
        d = datetime.strptime(b, "%Y-%m-%d")
        nxt = datetime(n.year, d.month, d.day, tzinfo=n.tzinfo)
    except ValueError:
        return None
    if nxt.date() < n.date():
        nxt = datetime(n.year + 1, d.month, d.day, tzinfo=n.tzinfo)
    return {"in_days": (nxt.date() - n.date()).days, "turns": nxt.year - d.year}


def weight_alert_pct():
    return 5 if is_senior() else 7


def weight_change():
    w = weights()
    if len(w) < 2:
        return None
    last = w[-1]
    ref = [v for ts, v in w if last[0] - 45 * 86400 <= ts <= last[0] - 14 * 86400]
    if not ref:
        return None
    base = sorted(ref)[len(ref) // 2]
    return round((last[1] - base) / base * 100, 1)


def log_event(task, who, note="", value=None, ts=None, force=False, kind=None):
    special = ("weight", "behavior", "garden_cat")
    if task not in special and task not in TASK_IDS:
        raise err(400, "unknown task")
    if task == "behavior" and kind not in BEH_KINDS:
        raise err(400, "unknown behaviour kind")
    if task not in special and not cfg["tasks"][task]["enabled"]:
        raise err(400, "task is disabled")
    now = time.time()
    ts = float(ts) if ts else now
    if ts > now + 60 or ts < now - 3650 * 86400:
        raise err(400, "bad time")
    if task == "weight":
        try:
            value = round(float(value), 2)
        except (TypeError, ValueError):
            raise err(400, "weight must be a number (kg)")
        if not 0.3 <= value <= 25:
            raise err(400, "weight must be between 0.3 and 25 kg")
    else:
        value = None
    if task == "feed" and not force and ts >= now - 60:
        prev = last_of("feed")
        if prev and now - prev["ts"] < DUP_MIN * 60:
            raise Conflict(json.dumps({"minutes": int((now - prev["ts"]) / 60), "who": prev["who"]}))
    ev = {"id": uuid.uuid4().hex[:8], "ts": ts, "task": task, "who": str(who or "")[:40], "note": str(note or "")[:200], "value": value}
    if kind:
        ev["kind"] = kind
    events.append(ev)
    events.sort(key=lambda e: e["ts"])
    del events[:-MAX_EVENTS]
    save()
    sent.pop(task, None)
    asyncio.get_running_loop().create_task(after_log(ev))
    return ev


async def after_log(ev):
    await ha_call("POST", "/events/hafreudteo_logged", {"task": ev["task"], "who": ev["who"], "value": ev["value"]})
    await clear_notifications(ev["task"])
    await publish()


# ---------------------------------------------------------------- Home Assistant
def hdr():
    return {"Authorization": f"Bearer {TOKEN}"}


async def ha_call(method, path, body=None, timeout=15):
    try:
        async with session.request(method, f"{HA}{path}", headers=hdr(), json=body, timeout=ClientTimeout(total=timeout)) as r:
            await r.read()
            return r.status < 400
    except Exception as exc:  # noqa: BLE001
        log.debug("HA call failed: %s", exc)
        return False


async def publish():
    async with _pub_lock:
        now = datetime.now(tz)
        st = {s["id"]: s for s in all_status(now)}
        base = {"attribution": "HAFreudTeo by TeodorTeo.com"}
        iso = lambda ts: datetime.fromtimestamp(ts, tz).isoformat() if ts else None  # noqa: E731
        name, sl = cat_name(), slug()
        for tid, s in st.items():
            if tid == "feed":
                await ha_call("POST", f"/states/sensor.{sl}_last_fed", {"state": iso(s["last"]) or "unknown", "attributes": {
                    **base, "friendly_name": f"{name} last fed", "device_class": "timestamp", "icon": "mdi:food-drumstick", "by": s["who"],
                    "fed_today": s["fed_today"], "meals_planned": s["meals"], "meals_passed": s["passed"], "needs_attention": s["state"] == "due"}})
            else:
                await ha_call("POST", f"/states/sensor.{sl}_{tid}", {"state": iso(s["last"]) or "unknown", "attributes": {
                    **base, "friendly_name": f"{name} {L(tid).lower()}", "device_class": "timestamp", "by": s["who"], "due_at": iso(s.get("due_at")),
                    "needs_attention": s["state"] == "due"}})
        seen = [e for e in events if e["task"] == "garden_cat"]
        if cfg["cams"]["entities"]:
            today0 = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            await ha_call("POST", f"/states/sensor.{sl}_garden_cat", {"state": iso(seen[-1]["ts"]) if seen else "unknown", "attributes": {
                **base, "friendly_name": f"{name} garden - a cat was seen", "device_class": "timestamp", "icon": "mdi:cat", "seen_today": sum(1 for e in seen if e["ts"] >= today0),
                "camera": seen[-1]["who"] if seen else None}})
        beh = [e for e in events if e["task"] == "behavior"]
        if beh:
            await ha_call("POST", f"/states/sensor.{sl}_behavior", {"state": sum(1 for e in beh if e["ts"] >= time.time() - 7 * 86400), "attributes": {
                **base, "friendly_name": f"{name} unusual behaviour (7 days)", "icon": "mdi:alert-circle-outline", "last": iso(beh[-1]["ts"]), "last_kind": beh[-1].get("kind"), "last_note": beh[-1]["note"]}})
        w = weights()
        if w:
            await ha_call("POST", f"/states/sensor.{sl}_weight", {"state": w[-1][1], "attributes": {
                **base, "friendly_name": f"{name} weight", "unit_of_measurement": "kg", "state_class": "measurement", "icon": "mdi:scale",
                "change_pct": weight_change()}})
        due = [t for t, s in st.items() if s["state"] == "due"]
        await ha_call("POST", f"/states/binary_sensor.{sl}_needs_attention", {"state": "on" if due else "off", "attributes": {
            **base, "friendly_name": f"{name} needs attention", "icon": "mdi:cat", "tasks": due}})


async def notify(task, text):
    now = time.time()
    for svc in notify_services():
        nonce = secrets.token_hex(8)
        notif[nonce] = {"task": task, "svc": svc, "ts": now}
        ok = await ha_call("POST", f"/services/notify/{svc}", {"title": cat_name(), "message": text, "data": {
            "tag": f"freud_{task}", "push": {"interruption-level": "time-sensitive"}, "actions": [{"action": f"FREUD_{nonce}", "title": L("done")}]}})
        if not ok:
            notif.pop(nonce, None)
    if notify_services():
        ensure_listener()


async def clear_notifications(task):
    for n in [n for n, v in notif.items() if v["task"] == task]:
        notif.pop(n, None)
    for svc in notify_services():
        await ha_call("POST", f"/services/notify/{svc}", {"message": "clear_notification", "data": {"tag": f"freud_{task}"}})


def ensure_listener():
    global listener_task
    if not listener_task or listener_task.done():
        listener_task = asyncio.create_task(action_listener())


async def action_listener():
    """One WebSocket (only while notifications exist) that turns the 'Done' button of a notification into a log entry."""
    delay = 5
    while notify_services():
        try:
            async with session.ws_connect(HA_WS, heartbeat=30, timeout=15) as ws:
                await ws.receive_json(timeout=10)
                await ws.send_json({"type": "auth", "access_token": TOKEN})
                if (await ws.receive_json(timeout=10)).get("type") != "auth_ok":
                    return
                await ws.send_json({"id": 1, "type": "subscribe_events", "event_type": "mobile_app_notification_action"})
                delay = 5
                while True:
                    for n in [n for n, v in notif.items() if time.time() - v["ts"] > 86400]:
                        notif.pop(n, None)
                    if not notif:
                        return
                    try:
                        msg = await ws.receive(timeout=120)
                    except asyncio.TimeoutError:
                        continue
                    if msg.type != WSMsgType.TEXT:
                        break
                    d = json.loads(msg.data)
                    act = str(((d.get("event") or {}).get("data") or {}).get("action", "")) if d.get("type") == "event" else ""
                    m = re.fullmatch(r"FREUD_([0-9a-f]{16})", act)
                    entry = notif.pop(m.group(1), None) if m else None
                    if entry:
                        who = entry["svc"].removeprefix("mobile_app_").replace("_", " ")
                        try:
                            log_event(entry["task"], who, "phone", force=True)
                        except web.HTTPException:
                            pass
        except Exception as exc:  # noqa: BLE001
            log.debug("listener: %s", type(exc).__name__)
        await asyncio.sleep(delay)
        delay = min(delay * 2, 300)


def detection(entity, old, new):
    """Does this state change mean 'the camera saw a cat'? Works for binary sensors, event entities, counters and text states."""
    n = str(new or "").strip().lower()
    o = str(old or "").strip().lower()
    if n in NEG or n == o and not entity.startswith("event."):
        return False
    dom = entity.split(".")[0]
    if dom == "event":
        return True
    try:
        return float(n) > 0 and (o in NEG or float(n) > float(o))
    except ValueError:
        pass
    return n == "on" if dom == "binary_sensor" else True


def sight(entity, name):
    cool = int(cfg["cams"].get("cooldown_min", 10)) * 60
    prev = next((e for e in reversed(events) if e["task"] == "garden_cat"), None)
    if prev and time.time() - prev["ts"] < cool:
        return
    ev = log_event("garden_cat", name or entity, entity)
    log.info("cat seen by %s", entity)
    return ev


async def cam_listener():
    """One WebSocket with a server-side state trigger on the chosen camera entities (no state_changed firehose)."""
    delay = 5
    while cfg["cams"]["entities"]:
        ents = list(cfg["cams"]["entities"])
        try:
            async with session.ws_connect(HA_WS, heartbeat=30, timeout=15) as ws:
                await ws.receive_json(timeout=10)
                await ws.send_json({"type": "auth", "access_token": TOKEN})
                if (await ws.receive_json(timeout=10)).get("type") != "auth_ok":
                    return
                await ws.send_json({"id": 1, "type": "subscribe_trigger", "trigger": {"platform": "state", "entity_id": ents}})
                delay = 5
                while True:
                    msg = await ws.receive()
                    if msg.type != WSMsgType.TEXT:
                        break
                    d = json.loads(msg.data)
                    tr_ = (((d.get("event") or {}).get("variables") or {}).get("trigger") or {}) if d.get("type") == "event" else {}
                    ns, os_ = tr_.get("to_state") or {}, tr_.get("from_state") or {}
                    ent = tr_.get("entity_id") or ns.get("entity_id") or ""
                    if ent in ents and detection(ent, os_.get("state"), ns.get("state")):
                        try:
                            sight(ent, (ns.get("attributes") or {}).get("friendly_name"))
                        except web.HTTPException:
                            pass
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.debug("camera listener: %s", type(exc).__name__)
        await asyncio.sleep(delay)
        delay = min(delay * 2, 300)


cam_task = None


def restart_cams():
    global cam_task
    if cam_task and not cam_task.done():
        cam_task.cancel()
    cam_task = asyncio.create_task(cam_listener()) if cfg["cams"]["entities"] else None


async def scheduler():
    while True:
        await asyncio.sleep(TICK)
        try:
            now = datetime.now(tz)
            options()
            if in_quiet(now):
                continue
            rep = int(cfg.get("repeat_min", 60)) * 60
            for s in all_status(now):
                tid = s["id"]
                if s["state"] != "due" or not s["remind"]:
                    sent.pop(tid, None)
                    continue
                rec = sent.get(tid)
                if rec and (rec["n"] >= 3 or time.time() - rec["ts"] < rep):
                    continue
                sent[tid] = {"ts": time.time(), "n": (rec["n"] + 1) if rec else 1}
                await notify(tid, L("remind", cat=cat_name(), task=L(tid)))
            bi = birthday_info(now)
            if bi and bi["in_days"] == 0 and cfg.get("bday_notified") != now.year and now.hour >= 8:
                cfg["bday_notified"] = now.year
                save()
                for svc in notify_services():
                    await ha_call("POST", f"/services/notify/{svc}", {"title": cat_name(), "message": (f"{cat_name()} ma dziś urodziny - {bi['turns']} lat" if lang == "pl" else f"{cat_name()}'s birthday today - {bi['turns']} years")})
            if now.minute % 10 == 0:
                await publish()
        except Exception:  # noqa: BLE001
            log.exception("scheduler")


# ---------------------------------------------------------------- summary text (Shortcuts / Siri)
def human_ago(ts):
    s = max(0, time.time() - ts)
    if s < 90:
        return "1 min" if lang != "pl" else "1 min"
    if s < 5400:
        return f"{round(s / 60)} min"
    if s < 172800:
        return f"{round(s / 3600)} h"
    return f"{round(s / 86400)} {'dni' if lang == 'pl' else 'days'}"


def summary_text():
    now = datetime.now(tz)
    parts = []
    for s in all_status(now):
        if s["id"] == "feed":
            tail = f", {L('ago', x=human_ago(s['last']))}" if s["last"] else ""
            parts.append(f"{L('feed')}: {L('fed_today', n=s['fed_today'], m=s['meals'])}{tail}")
        elif s["state"] == "due":
            parts.append(f"{L(s['id'])}: {'do zrobienia' if lang == 'pl' else 'due'}")
    return ". ".join(parts) or L("ok")


# ---------------------------------------------------------------- web
@web.middleware
async def ingress_guard(request, handler):
    if not DEV and request.remote not in INGRESS_PEERS:
        raise err(403, "ingress only")
    return await handler(request)


def request_who(request, body):
    w = str(body.get("who") or "").strip()[:30]
    return w or request.headers.get("X-Remote-User-Display-Name") or request.headers.get("X-Remote-User-Name") or "panel"


def view_state():
    now = datetime.now(tz)
    return {"name": cat_name(), "cfg": cfg, "status": all_status(now), "now": now.timestamp(), "weight_change": weight_change(), "weight_alert": weight_alert_pct(), "birthday": birthday_info(now), "senior": is_senior(),
            "events": events[-400:][::-1], "has_avatar": AVATAR.exists(), "notify": notify_services(), "api_enabled": bool(OPT.get("api_enabled")),
            "api_port": API_PORT, "lang": lang, "sensors": slug(), "summary": summary_text(), "kinds": BEH_KINDS}


async def h_index(request):
    return web.Response(text=(STATIC / "index.html").read_text(), content_type="text/html", headers={"Cache-Control": "no-store"})


async def h_state(request):
    options()
    return web.json_response(view_state())


async def h_log(request):
    try:
        b = await request.json()
    except ValueError:
        raise err(400, "bad json")
    who = request_who(request, b)
    try:
        ev = log_event(str(b.get("task", "")), who, b.get("note"), b.get("value"), b.get("ts"), bool(b.get("force")), b.get("kind"))
    except Conflict as c:
        raise err(409, L("recent", cat=cat_name(), m=max(1, json.loads(str(c))["minutes"]), who=json.loads(str(c))["who"] or "?"), duplicate=json.loads(str(c)))
    return web.json_response({"ok": True, "event": ev})


async def h_event_delete(request):
    i = request.match_info["id"]
    before = len(events)
    events[:] = [e for e in events if e["id"] != i]
    if len(events) == before:
        raise err(404, "not found")
    save()
    asyncio.create_task(publish())
    return web.json_response({"ok": True})


def clean_cfg(b):
    new = json.loads(json.dumps(cfg))
    if "name" in b:
        new["name"] = str(b["name"]).strip()[:30]
    if "birthday" in b:
        v = str(b["birthday"]).strip()
        if v and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            raise err(400, "birthday must be YYYY-MM-DD")
        if v != cfg.get("birthday"):
            new["birthday_approx"] = False
        new["birthday"] = v
    if "who" in b:
        new["who"] = str(b["who"]).strip()[:30]
    if "portion_g" in b:
        new["portion_g"] = max(1, min(500, int(b["portion_g"] or 0) or 40))
    if "repeat_min" in b:
        new["repeat_min"] = max(10, min(720, int(b["repeat_min"] or 60)))
    tm = lambda s: bool(re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(s)))  # noqa: E731
    if "quiet" in b:
        q = b["quiet"]
        if not (isinstance(q, list) and len(q) == 2 and all(tm(x) for x in q)):
            raise err(400, "quiet hours must be two HH:MM values")
        new["quiet"] = q
    if "cams" in b and isinstance(b["cams"], dict):
        ents = [str(e) for e in (b["cams"].get("entities") or [])]
        if len(ents) > 10 or not all(re.fullmatch(r"[a-z0-9_]+\.[a-z0-9_]+", e) for e in ents):
            raise err(400, "up to 10 valid entity ids")
        new["cams"]["entities"] = list(dict.fromkeys(ents))
        new["cams"]["cooldown_min"] = max(1, min(720, int(b["cams"].get("cooldown_min") or 10)))
    for tid, v in (b.get("tasks") or {}).items():
        if tid not in TASK_IDS or not isinstance(v, dict):
            continue
        t = new["tasks"][tid]
        for k in ("enabled", "remind"):
            if k in v:
                t[k] = bool(v[k])
        if tid == "feed":
            if "times" in v:
                times = sorted(set(str(x) for x in v["times"]))
                if not times or len(times) > 8 or not all(tm(x) for x in times):
                    raise err(400, "feed times: 1-8 values HH:MM")
                t["times"] = times
            if "grace_min" in v:
                t["grace_min"] = max(0, min(240, int(v["grace_min"])))
        elif "every_h" in v:
            t["every_h"] = max(1, min(87600, int(float(v["every_h"]))))
    return new


async def h_settings(request):
    global cfg
    try:
        cfg = clean_cfg(await request.json())
    except (ValueError, TypeError):
        raise err(400, "invalid settings")
    save()
    restart_cams()
    asyncio.create_task(publish())
    return web.json_response({"ok": True})


async def h_entities(request):
    """Candidates for the camera/detection picker (fetched on demand, nothing cached)."""
    q = request.query.get("q", "").strip().lower()[:40]
    try:
        async with session.get(f"{HA}/states", headers=hdr(), timeout=ClientTimeout(total=15)) as r:
            states = await r.json()
    except Exception:  # noqa: BLE001
        raise err(502, "Home Assistant unreachable")
    pref = ("cat", "animal", "pet", "motion", "person", "camera", "detect", "garden", "ogrod", "kot", "frigate", "reolink")
    out = []
    for st in states if isinstance(states, list) else []:
        eid = st.get("entity_id", "")
        if eid.split(".")[0] not in ("binary_sensor", "event", "image_processing", "sensor"):
            continue
        name = (st.get("attributes") or {}).get("friendly_name", "")
        hay = (eid + " " + name).lower()
        if q and q not in hay:
            continue
        if not q and not any(p in hay for p in pref):
            continue
        out.append({"id": eid, "name": name})
    return web.json_response(sorted(out, key=lambda x: x["id"])[:60])


async def h_avatar_get(request):
    if AVATAR.exists():
        data = AVATAR.read_bytes()
        kind = "image/png" if data[:4] == b"\x89PNG" else "image/webp" if data[8:12] == b"WEBP" else "image/jpeg"
        return web.Response(body=data, content_type=kind, headers={"Cache-Control": "no-cache"})
    return web.FileResponse(STATIC / "freud.jpg", headers={"Cache-Control": "no-cache"})


async def h_avatar_set(request):
    data = await request.read()
    if len(data) > 1_500_000:
        raise err(413, "image too large (max 1.5 MB)")
    if not (data[:3] == b"\xff\xd8\xff" or data[:4] == b"\x89PNG" or data[8:12] == b"WEBP"):
        raise err(400, "JPEG, PNG or WebP only")
    AVATAR.write_bytes(data)
    return web.json_response({"ok": True})


async def h_avatar_del(request):
    AVATAR.unlink(missing_ok=True)
    return web.json_response({"ok": True})


async def h_test(request):
    svcs = notify_services()
    if not svcs:
        raise err(400, "no notify service configured (add-on option notify_services)")
    await notify("feed", L("remind", cat=cat_name(), task=L("feed")))
    return web.json_response({"ok": True, "sent_to": svcs})


# ---- Shortcuts / Siri token API
def find_token(raw):
    d = hashlib.sha256(raw.encode()).hexdigest()
    found = None
    for t in tokens:
        if hmac.compare_digest(t["hash"], d):
            found = t
    return found


@web.middleware
async def token_guard(request, handler):
    raw = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    tok = find_token(raw) if raw else None
    if not tok:
        raise err(401, "invalid or missing token")
    now = time.time()
    hits = [t for t in tok_rate.get(tok["id"], []) if now - t < 60]
    if len(hits) >= 30:
        raise err(429, "too many requests")
    tok_rate[tok["id"]] = hits + [now]
    request["tok"] = tok
    return await handler(request)


async def api_log(request):
    try:
        b = await request.json()
    except ValueError:
        raise err(400, "bad json")
    tok = request["tok"]
    try:
        log_event(str(b.get("task", "feed")), tok["name"], b.get("note"), b.get("value"), None, bool(b.get("force")))
    except Conflict as c:
        info = json.loads(str(c))
        return web.json_response({"ok": False, "duplicate": True, "reply": L("recent", cat=cat_name(), m=max(1, info["minutes"]), who=info["who"] or "?")})
    tok["last"] = int(time.time())
    write_json(TOK_FILE, tokens, private=True)
    return web.json_response({"ok": True, "reply": summary_text()})


async def api_status(request):
    return web.json_response({"reply": summary_text(), "status": all_status()})


async def h_tokens(request):
    return web.json_response([{"id": t["id"], "name": t["name"], "created": t["created"], "last": t.get("last", 0)} for t in tokens])


async def h_token_new(request):
    name = str((await request.json()).get("name", "")).strip()[:30] or "iPhone"
    if len(tokens) >= 10:
        raise err(400, "max 10 tokens")
    raw = "hft_" + secrets.token_urlsafe(24)
    tokens.append({"id": uuid.uuid4().hex[:8], "name": name, "hash": hashlib.sha256(raw.encode()).hexdigest(), "secret": raw, "created": int(time.time()), "last": 0})
    write_json(TOK_FILE, tokens, private=True)
    return web.json_response({"token": raw})


async def h_token_secret(request):
    t = next((x for x in tokens if x["id"] == request.match_info["id"]), None)
    if not t:
        raise err(404, "not found")
    return web.json_response({"token": t["secret"]})


async def h_token_del(request):
    tokens[:] = [t for t in tokens if t["id"] != request.match_info["id"]]
    write_json(TOK_FILE, tokens, private=True)
    return web.json_response({"ok": True})


def build_apps():
    ui = web.Application(middlewares=[ingress_guard], client_max_size=2 * 1024 * 1024)
    ui.add_routes([web.get("/", h_index), web.static("/static", STATIC), web.get("/avatar", h_avatar_get), web.post("/api/avatar", h_avatar_set),
                   web.delete("/api/avatar", h_avatar_del), web.get("/api/state", h_state), web.get("/api/entities", h_entities), web.post("/api/log", h_log),
                   web.delete("/api/event/{id}", h_event_delete), web.post("/api/settings", h_settings), web.post("/api/test", h_test),
                   web.get("/api/tokens", h_tokens), web.post("/api/tokens", h_token_new), web.get("/api/tokens/{id}/secret", h_token_secret),
                   web.delete("/api/tokens/{id}", h_token_del)])
    api = web.Application(middlewares=[token_guard], client_max_size=16 * 1024)
    api.add_routes([web.post("/api/log", api_log), web.get("/api/status", api_status)])
    return ui, api


async def main():
    global session, tz, lang
    options()
    logging.basicConfig(level=getattr(logging, str(OPT.get("log_level", "info")).upper(), logging.INFO), format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
    DATA.mkdir(parents=True, exist_ok=True)
    load()
    session = ClientSession(timeout=ClientTimeout(total=30))
    try:
        async with session.get(f"{HA}/config", headers=hdr()) as r:
            c = await r.json()
            tz = ZoneInfo(c.get("time_zone", "UTC"))
            lang = "pl" if str(c.get("language", "en")).startswith("pl") else "en"
    except Exception:  # noqa: BLE001
        pass
    apply_age_option()
    ui, api = build_apps()
    r1 = web.AppRunner(ui, access_log=None)
    await r1.setup()
    try:
        await web.TCPSite(r1, "0.0.0.0", INGRESS_PORT).start()
    except OSError as exc:
        log.error("Cannot listen on port %s: %s", INGRESS_PORT, exc)
        raise SystemExit(1)
    if OPT.get("api_enabled"):
        try:
            r2 = web.AppRunner(api, access_log=None)
            await r2.setup()
            await web.TCPSite(r2, "0.0.0.0", API_PORT).start()
            log.info("Shortcuts endpoint on port %s (token required)", API_PORT)
        except OSError as exc:
            log.error("Cannot listen on port %s for the Shortcuts endpoint: %s", API_PORT, exc)
    log.info("HAFreudTeo by %s (%s) - panel via ingress; notifications to: %s", CREDIT, CREDIT_URL, ", ".join(notify_services()) or "none")
    asyncio.create_task(scheduler())
    restart_cams()
    await publish()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
