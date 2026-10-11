#!/usr/bin/env python3
"""HAMcpTeo - a remote MCP server for Claude, limited to the entities you pick.
Public side (HTTPS on your DDNS name): OAuth 2.1 sign-in that verifies the Home Assistant account AND its 2FA, then /mcp.
Panel side (ingress, admin only): choose what Claude may see / control, review sessions and the audit log.
Low memory: aiohttp only, no background polling. By TeodorTeo.com (https://teodorteo.com)."""
import asyncio
import base64
import hashlib
import hmac
import html
import ipaddress
import json
import logging
import os
import re
import secrets
import ssl
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web

CREDIT, CREDIT_URL, VERSION = "TeodorTeo.com", "https://teodorteo.com", "1.0.0"
DATA = Path(os.environ.get("HMT_DATA", "/data"))
OPTIONS_FILE = Path(os.environ.get("HMT_OPTIONS", "/data/options.json"))
SSL_DIR = Path(os.environ.get("HMT_SSL", "/ssl"))
STATIC = Path(__file__).parent / "static"
INGRESS_PORT = int(os.environ.get("HMT_INGRESS_PORT", 8099))
PUBLIC_PORT = int(os.environ.get("HMT_PUBLIC_PORT", 8443))
INGRESS_PEERS = {"172.30.32.2", "127.0.0.1", "::1"}
DEV = bool(os.environ.get("HMT_DEV"))
HA = os.environ.get("HMT_HA_URL", "http://supervisor/core/api")
HA_WS = os.environ.get("HMT_HA_WS") or (HA[:-4] if HA.endswith("/api") else HA).replace("http", "ws", 1) + "/websocket"
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
STATE_FILE, AUDIT_FILE = DATA / "state.json", DATA / "audit.jsonl"

ACCESS_TTL, REFRESH_TTL, CODE_TTL, FLOW_TTL = 3600, 30 * 86400, 300, 600
MAX_CLIENTS, MAX_SESSIONS, AUDIT_MAX = 50, 20, 1_000_000
APPROVAL_WAIT = 60
PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")

log = logging.getLogger("hamcpteo")

# ---------------------------------------------------------------- what can be exposed
READ_DOMAINS = {"light", "switch", "cover", "climate", "fan", "media_player", "scene", "input_boolean", "input_number", "input_select", "input_button",
                "button", "humidifier", "vacuum", "lock", "sensor", "binary_sensor", "weather", "person", "sun", "device_tracker", "water_heater",
                "number", "select", "valve", "automation", "script", "alarm_control_panel", "update", "zone", "calendar", "todo"}
SERVICES = {  # the ONLY services Claude may call (per domain), on entities with "control" access
    "light": {"turn_on", "turn_off", "toggle"}, "switch": {"turn_on", "turn_off", "toggle"}, "input_boolean": {"turn_on", "turn_off", "toggle"},
    "cover": {"open_cover", "close_cover", "stop_cover", "set_cover_position", "toggle"},
    "climate": {"set_temperature", "set_hvac_mode", "set_preset_mode", "set_fan_mode", "turn_on", "turn_off"},
    "fan": {"turn_on", "turn_off", "toggle", "set_percentage", "set_preset_mode"},
    "media_player": {"media_play", "media_pause", "media_stop", "media_next_track", "media_previous_track", "volume_set", "volume_mute", "turn_on", "turn_off", "select_source"},
    "scene": {"turn_on"}, "input_number": {"set_value"}, "input_select": {"select_option"}, "input_button": {"press"}, "button": {"press"},
    "humidifier": {"turn_on", "turn_off", "set_humidity"}, "vacuum": {"start", "pause", "stop", "return_to_base", "locate"},
    "lock": {"lock", "unlock"}, "script": {"turn_on"}, "automation": {"trigger", "turn_on", "turn_off"}, "number": {"set_value"}, "select": {"select_option"},
    "water_heater": {"set_temperature", "turn_on", "turn_off"}, "valve": {"open_valve", "close_valve"},
}
FORBIDDEN_DATA = {"entity_id", "device_id", "area_id", "floor_id", "label_id", "target"}
NEG_ATTR = {"entity_picture", "access_token", "token", "ip_address", "mac", "mac_address", "latitude", "longitude", "gps_accuracy"}

state = {"enabled": True, "exposure": {}, "clients": {}, "refresh": {}, "secret": ""}
OPT = {}
access = {}          # sha(token) -> {sid, client_id, user, exp, ip}
codes = {}           # code -> {client_id, redirect_uri, challenge, user, exp}
flows = {}           # flow token -> pending login (HA flow id, ctx, ...)
used_refresh = {}    # sha(old refresh) -> sid  (replay detection)
fails = {}           # ip -> [timestamps]
global_fails = []
rate = {}            # key -> [timestamps]
approvals = {}       # nonce -> {fut, ts}
session = None
listener_task = None


def err(status, message, **extra):
    cls = {400: web.HTTPBadRequest, 401: web.HTTPUnauthorized, 403: web.HTTPForbidden, 404: web.HTTPNotFound,
           409: web.HTTPConflict, 429: web.HTTPTooManyRequests, 502: web.HTTPBadGateway, 503: web.HTTPServiceUnavailable}[status]
    return cls(text=json.dumps({"error": message, **extra}), content_type="application/json")


def sha(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def options():
    global OPT
    try:
        OPT = json.loads(OPTIONS_FILE.read_text())
    except (OSError, ValueError):
        OPT = {}
    return OPT


def public_url():
    return str(OPT.get("public_url") or "").strip().rstrip("/")


def allowed_users():
    return {str(u).strip().lower() for u in (OPT.get("allowed_users") or []) if str(u).strip()}


def lst(key):
    return [str(x).strip() for x in (OPT.get(key) or []) if str(x).strip()]


def write_private(path, obj):
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    tmp.replace(path)


def save():
    write_private(STATE_FILE, state)


def load():
    try:
        d = json.loads(STATE_FILE.read_text())
        for k in state:
            if k in d:
                state[k] = d[k]
    except (OSError, ValueError):
        pass
    if not state["secret"]:
        state["secret"] = secrets.token_hex(32)
        save()


def audit(user, client, tool, args, outcome, note=""):
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        if AUDIT_FILE.exists() and AUDIT_FILE.stat().st_size > AUDIT_MAX:
            AUDIT_FILE.replace(AUDIT_FILE.with_suffix(".jsonl.1"))
        with AUDIT_FILE.open("a") as f:
            f.write(json.dumps({"ts": time.time(), "user": user, "client": client, "tool": tool, "args": json.dumps(args, default=str)[:400],
                                "outcome": outcome, "note": str(note)[:200]}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read_audit(limit=200):
    rows = []
    for p in (AUDIT_FILE.with_suffix(".jsonl.1"), AUDIT_FILE):
        try:
            rows += [json.loads(x) for x in p.read_text().splitlines()[-limit:] if x.strip()]
        except (OSError, ValueError):
            pass
    return rows[-limit:][::-1]


# ---------------------------------------------------------------- rate limits / fails
def hit(key, limit, window):
    now = time.time()
    h = [t for t in rate.get(key, []) if now - t < window]
    if len(h) >= limit:
        rate[key] = h
        return False
    rate[key] = h + [now]
    if len(rate) > 5000:
        for k in [k for k, v in rate.items() if not v or now - v[-1] > 3600]:
            rate.pop(k, None)
    return True


def login_blocked(ip):
    now = time.time()
    fails[ip] = [t for t in fails.get(ip, []) if now - t < 900]
    global_fails[:] = [t for t in global_fails if now - t < 3600]
    return len(fails[ip]) >= 5 or len(global_fails) >= 30


def login_failed(ip):
    fails.setdefault(ip, []).append(time.time())
    global_fails.append(time.time())


def client_ip(request):
    return request.remote or "?"


def ip_allowed(request):
    nets = lst("allowed_ips")
    if not nets:
        return True
    try:
        ip = ipaddress.ip_address(client_ip(request))
        return any(ip in ipaddress.ip_network(n, strict=False) for n in nets)
    except ValueError:
        return False


# ---------------------------------------------------------------- Home Assistant (REST, WS, login flow)
def hdr():
    return {"Authorization": f"Bearer {TOKEN}"}


async def ha(method, path, body=None, timeout=15):
    try:
        async with session.request(method, f"{HA}{path}", headers=hdr(), json=body, timeout=ClientTimeout(total=timeout)) as r:
            raw = await r.read()
            if len(raw) > 4_000_000:
                raise err(502, "response too large")
            try:
                data = json.loads(raw)
            except ValueError:
                data = None
            return r.status, data
    except web.HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise err(502, f"Home Assistant unreachable: {type(exc).__name__}")


async def ha_auth(path, body):
    """HA login flow (public endpoints of Home Assistant Core) - used to verify the account AND its 2FA."""
    base = str(OPT.get("ha_url") or "http://homeassistant:8123").rstrip("/")
    bases = [base] + (["https://" + base[7:]] if base.startswith("http://") else [])
    for b in bases:
        try:
            async with session.post(b + path, json=body, timeout=ClientTimeout(total=15), ssl=False if b.startswith("https://") else None) as r:
                if r.status >= 500:
                    continue
                return r.status, await r.json(content_type=None)
        except Exception:  # noqa: BLE001
            continue
    raise err(502, "Home Assistant login is unreachable")


def origin():
    u = urlsplit(public_url())
    return f"{u.scheme}://{u.netloc}/"


async def ha_flow_start():
    st, d = await ha_auth("/auth/login_flow", {"client_id": origin(), "handler": ["homeassistant", None], "redirect_uri": origin() + "ha-callback"})
    if st != 200 or not isinstance(d, dict) or "flow_id" not in d:
        raise err(502, "Home Assistant refused to start the login")
    return d["flow_id"]


async def ha_flow_step(flow_id, data):
    st, d = await ha_auth(f"/auth/login_flow/{flow_id}", {**data, "client_id": origin()})
    if not isinstance(d, dict):
        raise err(502, "unexpected reply from Home Assistant")
    return d


# ---------------------------------------------------------------- tools
def trim_attrs(a):
    out = {}
    for k, v in list((a or {}).items())[:40]:
        if k in NEG_ATTR:
            continue
        if isinstance(v, str):
            v = v[:200]
        elif isinstance(v, (list, dict)):
            v = json.loads(json.dumps(v, default=str)[:300]) if len(json.dumps(v, default=str)) <= 300 else "(long)"
        out[k] = v
    return out


def level(eid):
    return state["exposure"].get(eid, "none")


def is_risky(domain, service, st):
    if domain == "script" or (domain == "lock" and service == "unlock"):
        return True
    if domain == "cover" and (st.get("attributes") or {}).get("device_class") in ("garage", "gate", "door") and service != "stop_cover":
        return True
    return False


TOOLS = [
    {"name": "list_entities", "description": "List the Home Assistant entities you are allowed to see (with state and whether you may control them). Optional filters: domain, query.",
     "inputSchema": {"type": "object", "properties": {"domain": {"type": "string"}, "query": {"type": "string"}}}},
    {"name": "get_state", "description": "Get the current state and attributes of one allowed entity.",
     "inputSchema": {"type": "object", "properties": {"entity_id": {"type": "string"}}, "required": ["entity_id"]}},
    {"name": "get_history", "description": "State changes of one allowed entity during the last N hours (max 72, at most 100 changes).",
     "inputSchema": {"type": "object", "properties": {"entity_id": {"type": "string"}, "hours": {"type": "number"}}, "required": ["entity_id"]}},
    {"name": "call_service", "description": "Control allowed entities (turn on/off, set temperature, ...). Only entities with 'control' access and a short list of safe services work. "
     "Risky actions (unlock, garage/door/gate, scripts) wait for approval on the owner's phone.",
     "inputSchema": {"type": "object", "properties": {"domain": {"type": "string"}, "service": {"type": "string"},
                                                       "entity_id": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                                                       "data": {"type": "object"}}, "required": ["domain", "service", "entity_id"]}},
]


def ent_ok(eid):
    return isinstance(eid, str) and re.fullmatch(r"[a-z0-9_]+\.[a-z0-9_]+", eid) is not None


async def tool_call(name, args, ctx):
    if not isinstance(args, dict):
        raise ValueError("arguments must be an object")
    if name == "list_entities":
        want, q = str(args.get("domain") or ""), str(args.get("query") or "").lower()
        _, states = await ha("GET", "/states")
        rows = []
        for st in states if isinstance(states, list) else []:
            eid = st.get("entity_id", "")
            lv = level(eid)
            if lv == "none" or (want and not eid.startswith(want + ".")):
                continue
            nm = (st.get("attributes") or {}).get("friendly_name", "")
            if q and q not in (eid + " " + nm).lower():
                continue
            rows.append({"entity_id": eid, "name": nm, "state": st.get("state"), "control": lv == "control"})
        return {"entities": rows[:200], "count": len(rows)}
    eid = args.get("entity_id")
    if name == "get_state":
        if not ent_ok(eid) or level(eid) == "none":
            raise PermissionError("entity not available")
        st, d = await ha("GET", f"/states/{eid}")
        if st != 200 or not isinstance(d, dict):
            raise ValueError("entity not found")
        return {"entity_id": eid, "state": d.get("state"), "attributes": trim_attrs(d.get("attributes")), "last_changed": d.get("last_changed")}
    if name == "get_history":
        if not ent_ok(eid) or level(eid) == "none":
            raise PermissionError("entity not available")
        hrs = max(1, min(72, float(args.get("hours") or 24)))
        start = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() - hrs * 3600))
        st, d = await ha("GET", f"/history/period/{start}?filter_entity_id={eid}&minimal_response&no_attributes", timeout=30)
        rows = d[0] if isinstance(d, list) and d else []
        return {"entity_id": eid, "changes": [{"state": r.get("state"), "at": r.get("last_changed")} for r in rows[-100:]]}
    if name == "call_service":
        dom, svc = str(args.get("domain", "")), str(args.get("service", ""))
        ids = eid if isinstance(eid, list) else [eid]
        if not ids or len(ids) > 10 or not all(ent_ok(e) for e in ids):
            raise ValueError("entity_id: 1-10 entity ids required")
        if svc not in SERVICES.get(dom, ()):
            raise PermissionError(f"service {dom}.{svc} is not allowed")
        for e in ids:
            if not e.startswith(dom + ".") or level(e) != "control":
                raise PermissionError(f"{e} is not available for control")
        data = args.get("data") or {}
        if not isinstance(data, dict) or len(json.dumps(data, default=str)) > 2000 or FORBIDDEN_DATA & set(data):
            raise ValueError("invalid data")
        risky = False
        for e in ids:
            _, cur = await ha("GET", f"/states/{e}")
            risky = risky or is_risky(dom, svc, cur if isinstance(cur, dict) else {})
        if risky:
            if not OPT.get("approve_risky", True) or not str(OPT.get("notify_service") or "").strip():
                raise PermissionError("risky action refused: set notify_service and keep approve_risky on to allow it with phone approval")
            if not await ask_phone(f"Claude wants: {dom}.{svc} on {', '.join(ids)}"):
                raise PermissionError("not approved on the phone (rejected or timed out)")
        st, _ = await ha("POST", f"/services/{dom}/{svc}", {**data, "entity_id": ids if len(ids) > 1 else ids[0]}, timeout=30)
        if st >= 400:
            raise ValueError(f"Home Assistant returned {st}")
        return {"ok": True, "called": f"{dom}.{svc}", "entities": ids, "approved_on_phone": risky}
    raise ValueError("unknown tool")


# ---------------------------------------------------------------- phone approval (Companion app notification actions)
async def ask_phone(text):
    svc = str(OPT.get("notify_service") or "").strip().removeprefix("notify.")
    if not re.fullmatch(r"[a-z0-9_]{1,60}", svc):
        return False
    nonce = secrets.token_hex(8)
    fut = asyncio.get_running_loop().create_future()
    approvals[nonce] = {"fut": fut, "ts": time.time()}
    st, _ = await ha("POST", f"/services/notify/{svc}", {"title": "HAMcpTeo", "message": text, "data": {
        "tag": f"hamcp_{nonce}", "push": {"interruption-level": "time-sensitive"},
        "actions": [{"action": f"HMCP_A_{nonce}", "title": "Approve"}, {"action": f"HMCP_R_{nonce}", "title": "Reject", "destructive": True}]}})
    if st >= 400:
        approvals.pop(nonce, None)
        return False
    ensure_listener()
    try:
        return bool(await asyncio.wait_for(fut, APPROVAL_WAIT))
    except asyncio.TimeoutError:
        return False
    finally:
        approvals.pop(nonce, None)
        await ha("POST", f"/services/notify/{svc}", {"message": "clear_notification", "data": {"tag": f"hamcp_{nonce}"}})


def ensure_listener():
    global listener_task
    if not listener_task or listener_task.done():
        listener_task = asyncio.create_task(action_listener())


async def action_listener():
    try:
        async with session.ws_connect(HA_WS, heartbeat=30, timeout=15) as ws:
            await ws.receive_json(timeout=10)
            await ws.send_json({"type": "auth", "access_token": TOKEN})
            if (await ws.receive_json(timeout=10)).get("type") != "auth_ok":
                return
            await ws.send_json({"id": 1, "type": "subscribe_events", "event_type": "mobile_app_notification_action"})
            while approvals:
                try:
                    msg = await ws.receive(timeout=5)
                except asyncio.TimeoutError:
                    continue
                if msg.type != WSMsgType.TEXT:
                    break
                d = json.loads(msg.data)
                act = str(((d.get("event") or {}).get("data") or {}).get("action", "")) if d.get("type") == "event" else ""
                m = re.fullmatch(r"HMCP_([AR])_([0-9a-f]{16})", act)
                entry = approvals.get(m.group(2)) if m else None
                if entry and not entry["fut"].done():
                    entry["fut"].set_result(m.group(1) == "A")
    except Exception as exc:  # noqa: BLE001
        log.debug("approval listener: %s", type(exc).__name__)


# ---------------------------------------------------------------- OAuth helpers
def sign(payload):
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    mac = hmac.new(bytes.fromhex(state["secret"]), raw.encode(), hashlib.sha256).hexdigest()[:43]
    return f"{raw}.{mac}"


def unsign(token):
    try:
        raw, mac = str(token).rsplit(".", 1)
        good = hmac.new(bytes.fromhex(state["secret"]), raw.encode(), hashlib.sha256).hexdigest()[:43]
        if not hmac.compare_digest(mac, good):
            return None
        p = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        return p if p.get("exp", 0) > time.time() else None
    except Exception:  # noqa: BLE001
        return None


def redirect_ok(uri):
    u = urlsplit(str(uri))
    if u.fragment or u.scheme not in ("https", "http") or not u.netloc:
        return False
    if u.scheme == "http" and u.hostname not in ("localhost", "127.0.0.1", "::1"):
        return False
    return any(str(uri).startswith(p) for p in lst("allowed_redirects"))


def esc(s):
    return html.escape(str(s), quote=True)


SEC_HEADERS = {"Strict-Transport-Security": "max-age=31536000", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
               "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'"}

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>HAMcpTeo</title>
<style>:root{color-scheme:light dark}body{font:16px/24px system-ui,sans-serif;margin:0;padding:24px;max-width:420px;margin:0 auto}h1{font-size:20px;font-weight:500;margin:24px 0 8px}
p{margin:8px 0;opacity:.8}label{display:block;margin:16px 0 4px;font-size:13px;opacity:.7}input{width:100%;box-sizing:border-box;font:inherit;padding:12px;border:1px solid #8885;border-radius:8px;background:transparent;color:inherit}
button{font:inherit;font-weight:500;border:0;border-radius:24px;padding:12px 24px;margin:20px 8px 0 0;background:#03a9f4;color:#fff;cursor:pointer}button.alt{background:transparent;color:inherit;border:1px solid #8885}
.err{color:#d33;opacity:1}.box{border:1px solid #8885;border-radius:8px;padding:12px;margin:16px 0}small{opacity:.6}</style></head><body>__BODY__</body></html>"""


def page(body, status=200):
    return web.Response(text=PAGE.replace("__BODY__", body), content_type="text/html", status=status, headers=SEC_HEADERS)


def exposure_summary():
    ctl = sum(1 for v in state["exposure"].values() if v == "control")
    rd = sum(1 for v in state["exposure"].values() if v == "read")
    return rd, ctl


# ---------------------------------------------------------------- OAuth endpoints (public)
def meta_as():
    u = public_url()
    return {"issuer": u, "authorization_endpoint": f"{u}/authorize", "token_endpoint": f"{u}/token", "registration_endpoint": f"{u}/register",
            "revocation_endpoint": f"{u}/revoke", "response_types_supported": ["code"], "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"], "token_endpoint_auth_methods_supported": ["none"], "scopes_supported": ["mcp"]}


async def h_meta_as(request):
    return web.json_response(meta_as(), headers=SEC_HEADERS)


async def h_meta_pr(request):
    u = public_url()
    return web.json_response({"resource": f"{u}/mcp", "authorization_servers": [u], "bearer_methods_supported": ["header"], "scopes_supported": ["mcp"],
                              "resource_name": "Home Assistant (HAMcpTeo)"}, headers=SEC_HEADERS)


async def h_register(request):
    if not state["enabled"]:
        raise err(503, "disabled")
    if not hit(("reg", client_ip(request)), 10, 3600):
        raise err(429, "too many registrations")
    try:
        b = await request.json()
    except ValueError:
        raise err(400, "invalid_client_metadata")
    uris = b.get("redirect_uris")
    if not isinstance(uris, list) or not uris or len(uris) > 5 or not all(isinstance(x, str) and redirect_ok(x) for x in uris):
        return web.json_response({"error": "invalid_redirect_uri", "error_description": "redirect_uri is not on the allowed list (add-on option allowed_redirects)"}, status=400)
    if len(state["clients"]) >= MAX_CLIENTS:
        oldest = sorted(state["clients"].items(), key=lambda kv: kv[1].get("created", 0))[0][0]
        state["clients"].pop(oldest, None)
    cid = "c_" + secrets.token_urlsafe(18)
    name = re.sub(r"[^\w .:/@()+-]", "", str(b.get("client_name") or "MCP client"))[:60] or "MCP client"
    state["clients"][cid] = {"name": name, "redirect_uris": uris, "created": int(time.time())}
    save()
    return web.json_response({"client_id": cid, "client_name": name, "redirect_uris": uris, "grant_types": ["authorization_code", "refresh_token"],
                              "response_types": ["code"], "token_endpoint_auth_method": "none", "client_id_issued_at": int(time.time())}, status=201, headers=SEC_HEADERS)


def login_form(ctx, error="", user=""):
    c = state["clients"].get(unsign(ctx)["client_id"], {}) if unsign(ctx) else {}
    return page(f"""<h1>Sign in to Home Assistant</h1><p><b>{esc(c.get('name', 'An app'))}</b> asks for access to your Home Assistant. Sign in with your Home Assistant account; two-factor authentication is required.</p>
    {f'<p class="err">{esc(error)}</p>' if error else ''}
    <form method="post" action="/authorize/login"><input type="hidden" name="ctx" value="{esc(ctx)}">
    <label>Username</label><input name="username" value="{esc(user)}" autocomplete="username" autocapitalize="off" required>
    <label>Password</label><input name="password" type="password" autocomplete="current-password" required><button>Continue</button></form>""")


async def h_authorize(request):
    if not state["enabled"] or not public_url():
        return page("<h1>Unavailable</h1><p>This connection is switched off.</p>", 503)
    q = request.query
    c = state["clients"].get(q.get("client_id", ""))
    ru = q.get("redirect_uri", "")
    if not c or ru not in c["redirect_uris"] or not redirect_ok(ru):
        return page("<h1>Invalid request</h1><p>Unknown application or redirect address.</p>", 400)
    ch = q.get("code_challenge", "")
    if q.get("response_type") != "code" or q.get("code_challenge_method") != "S256" or not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", ch):
        return page("<h1>Invalid request</h1><p>PKCE (S256) is required.</p>", 400)
    ctx = sign({"cid": q["client_id"], "client_id": q["client_id"], "ru": ru, "ch": ch, "st": q.get("state", "")[:500], "exp": time.time() + FLOW_TTL})
    return login_form(ctx)


async def h_login(request):
    form = await request.post()
    ip = client_ip(request)
    p = unsign(form.get("ctx", ""))
    if not p or not state["enabled"]:
        return page("<h1>Expired</h1><p>Start again from the app.</p>", 400)
    ctx = form["ctx"]
    if login_blocked(ip):
        return login_form(ctx, "Too many attempts. Try again in 15 minutes.")
    username = str(form.get("username", "")).strip()
    if username.lower() not in allowed_users() or not form.get("password"):
        login_failed(ip)
        audit(username[:40], p["client_id"], "login", {}, "denied", "user not allowed or empty")
        return login_form(ctx, "Sign-in failed.", username)
    try:
        fid = await ha_flow_start()
        d = await ha_flow_step(fid, {"username": username, "password": str(form["password"])})
    except web.HTTPException:
        return login_form(ctx, "Home Assistant is not reachable. Try again later.", username)
    if d.get("type") == "create_entry":
        if OPT.get("require_mfa", True):
            login_failed(ip)
            audit(username, p["client_id"], "login", {}, "denied", "account has no 2FA")
            return login_form(ctx, "Two-factor authentication is not enabled on this Home Assistant account. Enable it first (profile page).", username)
        return consent_page(p, username)
    if d.get("type") == "form" and d.get("step_id") in ("mfa", "select_mfa_module"):
        if d.get("step_id") == "select_mfa_module":
            opts = [o[0] if isinstance(o, list) else o for o in ((d.get("data_schema") or [{}])[0].get("options") or [])]
            d = await ha_flow_step(fid, {"multi_factor_auth_module": "totp" if "totp" in opts else (opts[0] if opts else "totp")})
        tok = secrets.token_urlsafe(24)
        flows[tok] = {"fid": fid, "p": p, "user": username, "exp": time.time() + FLOW_TTL}
        return mfa_form(tok)
    login_failed(ip)
    audit(username, p["client_id"], "login", {}, "denied", "bad credentials")
    return login_form(ctx, "Sign-in failed.", username)


def mfa_form(tok, error=""):
    return page(f"""<h1>Two-factor code</h1><p>Enter the 6-digit code from your authenticator app.</p>{f'<p class="err">{esc(error)}</p>' if error else ''}
    <form method="post" action="/authorize/mfa"><input type="hidden" name="ft" value="{esc(tok)}"><label>Code</label>
    <input name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="8" required autofocus><button>Verify</button></form>""")


async def h_mfa(request):
    form = await request.post()
    ip = client_ip(request)
    fl = flows.get(form.get("ft", ""))
    if not fl or fl["exp"] < time.time():
        return page("<h1>Expired</h1><p>Start again from the app.</p>", 400)
    if login_blocked(ip):
        return mfa_form(form["ft"], "Too many attempts. Try again in 15 minutes.")
    try:
        d = await ha_flow_step(fl["fid"], {"code": str(form.get("code", "")).strip()})
    except web.HTTPException:
        return mfa_form(form["ft"], "Home Assistant is not reachable.")
    if d.get("type") == "create_entry":
        flows.pop(form["ft"], None)
        return consent_page(fl["p"], fl["user"])
    login_failed(ip)
    if d.get("type") == "abort":
        flows.pop(form["ft"], None)
        audit(fl["user"], fl["p"]["client_id"], "login", {}, "denied", "2FA aborted (too many retries)")
        return page("<h1>Locked</h1><p>Too many wrong codes. Start again from the app later.</p>", 403)
    audit(fl["user"], fl["p"]["client_id"], "login", {}, "denied", "wrong 2FA code")
    return mfa_form(form["ft"], "Wrong code.")


def consent_page(p, user):
    c = state["clients"].get(p["client_id"], {})
    rd, ctl = exposure_summary()
    tok = sign({**p, "user": user, "exp": time.time() + FLOW_TTL, "kind": "consent"})
    return page(f"""<h1>Allow access?</h1><p>Signed in as <b>{esc(user)}</b>.</p><div class="box"><b>{esc(c.get('name', 'An app'))}</b> will be able to read <b>{rd + ctl}</b> and control <b>{ctl}</b>
    Home Assistant entities you chose. Risky actions need approval on your phone. You can revoke this any time in the add-on panel.</div>
    <form method="post" action="/authorize/consent"><input type="hidden" name="ct" value="{esc(tok)}">
    <button name="decision" value="allow">Allow</button><button class="alt" name="decision" value="deny">Cancel</button></form>""")


async def h_consent(request):
    form = await request.post()
    p = unsign(form.get("ct", ""))
    if not p or p.get("kind") != "consent" or not state["enabled"]:
        return page("<h1>Expired</h1><p>Start again from the app.</p>", 400)
    ru = p["ru"]
    if form.get("decision") != "allow":
        q = urlencode({"error": "access_denied", **({"state": p["st"]} if p["st"] else {})})
        raise web.HTTPFound(f"{ru}{'&' if '?' in ru else '?'}{q}")
    code = secrets.token_urlsafe(32)
    codes[sha(code)] = {"client_id": p["client_id"], "ru": ru, "ch": p["ch"], "user": p["user"], "exp": time.time() + CODE_TTL}
    for k in [k for k, v in codes.items() if v["exp"] < time.time()]:
        codes.pop(k, None)
    audit(p["user"], p["client_id"], "authorize", {}, "ok")
    q = urlencode({"code": code, **({"state": p["st"]} if p["st"] else {})})
    raise web.HTTPFound(f"{ru}{'&' if '?' in ru else '?'}{q}")


def issue(client_id, user, sid=None, refresh_old=None):
    sid = sid or uuid.uuid4().hex[:10]
    at, rt = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    now = time.time()
    access[sha(at)] = {"sid": sid, "client_id": client_id, "user": user, "exp": now + ACCESS_TTL}
    created = state["refresh"].get(refresh_old, {}).get("created", int(now)) if refresh_old else int(now)
    for h in [h for h, v in access.items() if v["exp"] < now]:
        access.pop(h, None)
    if len(used_refresh) > 500:
        used_refresh.pop(next(iter(used_refresh)))
    if refresh_old:
        used_refresh[refresh_old] = sid
        state["refresh"].pop(refresh_old, None)
    state["refresh"][sha(rt)] = {"sid": sid, "client_id": client_id, "user": user, "exp": now + REFRESH_TTL, "created": created, "last": int(now)}
    mine = [(h, v) for h, v in state["refresh"].items() if v["client_id"] == client_id and v["user"] == user]
    for h, v in sorted(mine, key=lambda kv: kv[1]["created"])[:-MAX_SESSIONS]:
        state["refresh"].pop(h, None)
    save()
    return {"access_token": at, "token_type": "Bearer", "expires_in": ACCESS_TTL, "refresh_token": rt, "scope": "mcp"}


def revoke_sid(sid):
    for h in [h for h, v in state["refresh"].items() if v["sid"] == sid]:
        state["refresh"].pop(h, None)
    for h in [h for h, v in access.items() if v["sid"] == sid]:
        access.pop(h, None)
    save()


def oauth_err(code, desc="", status=400):
    return web.json_response({"error": code, "error_description": desc}, status=status, headers=SEC_HEADERS)


async def h_token(request):
    if not state["enabled"]:
        return oauth_err("temporarily_unavailable", status=503)
    if not ip_allowed(request) or not hit(("tok", client_ip(request)), 60, 60):
        return oauth_err("access_denied", "not allowed", 403)
    f = await request.post()
    cid = f.get("client_id", "")
    if cid not in state["clients"]:
        return oauth_err("invalid_client", status=401)
    gt = f.get("grant_type")
    if gt == "authorization_code":
        c = codes.pop(sha(f.get("code", "")), None)
        if not c or c["exp"] < time.time() or c["client_id"] != cid or c["ru"] != f.get("redirect_uri"):
            return oauth_err("invalid_grant")
        ver = str(f.get("code_verifier", ""))
        want = base64.urlsafe_b64encode(hashlib.sha256(ver.encode()).digest()).decode().rstrip("=")
        if not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", ver) or not hmac.compare_digest(want, c["ch"]):
            return oauth_err("invalid_grant", "PKCE verification failed")
        audit(c["user"], cid, "token", {"grant": "authorization_code"}, "ok")
        return web.json_response(issue(cid, c["user"]), headers=SEC_HEADERS)
    if gt == "refresh_token":
        h = sha(f.get("refresh_token", ""))
        if h in used_refresh:   # replay of an already used token: assume theft, kill the whole session
            revoke_sid(used_refresh[h])
            audit("", cid, "token", {}, "denied", "refresh token replay - session revoked")
            return oauth_err("invalid_grant")
        r = state["refresh"].get(h)
        if not r or r["client_id"] != cid or r["exp"] < time.time() or r["user"].lower() not in allowed_users():
            return oauth_err("invalid_grant")
        return web.json_response(issue(cid, r["user"], r["sid"], h), headers=SEC_HEADERS)
    return oauth_err("unsupported_grant_type")


async def h_revoke(request):
    f = await request.post()
    h = sha(f.get("token", ""))
    r = state["refresh"].get(h) or access.get(h)
    if r:
        revoke_sid(r["sid"])
    return web.Response(status=200, headers=SEC_HEADERS)


# ---------------------------------------------------------------- MCP endpoint (public)
def www_auth():
    return {"WWW-Authenticate": f'Bearer realm="HAMcpTeo", resource_metadata="{public_url()}/.well-known/oauth-protected-resource"', **SEC_HEADERS}


async def h_mcp(request):
    if not state["enabled"]:
        raise err(503, "disabled")
    if not ip_allowed(request):
        raise err(403, "address not allowed")
    raw = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    a = access.get(sha(raw)) if raw else None
    if not a or a["exp"] < time.time() or a["user"].lower() not in allowed_users():
        return web.json_response({"error": "unauthorized"}, status=401, headers=www_auth())
    if not hit(("mcp", a["sid"]), 90, 60):
        raise err(429, "rate limit")
    try:
        body = await request.json()
    except ValueError:
        return web.json_response({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}, headers=SEC_HEADERS)
    ctx = {"user": a["user"], "client": state["clients"].get(a["client_id"], {}).get("name", "?")}
    msgs = body if isinstance(body, list) else [body]
    out = [r for r in [await rpc(m, ctx) for m in msgs[:20]] if r is not None]
    if not out:
        return web.Response(status=202, headers=SEC_HEADERS)
    return web.json_response(out if isinstance(body, list) else out[0], headers=SEC_HEADERS)


async def h_mcp_get(request):
    return web.Response(status=405, headers={"Allow": "POST", **SEC_HEADERS})


def rpc_err(i, code, msg):
    return {"jsonrpc": "2.0", "id": i, "error": {"code": code, "message": msg}}


async def rpc(m, ctx):
    if not isinstance(m, dict) or m.get("jsonrpc") != "2.0":
        return rpc_err(None, -32600, "invalid request")
    i, method, params = m.get("id"), m.get("method", ""), m.get("params") or {}
    if "id" not in m:
        return None                     # notification
    if method == "initialize":
        want = str(params.get("protocolVersion", ""))
        return {"jsonrpc": "2.0", "id": i, "result": {"protocolVersion": want if want in PROTOCOLS else PROTOCOLS[0], "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "HAMcpTeo", "version": VERSION},
                "instructions": "Home Assistant, limited to the entities the owner selected. Use list_entities first. Control needs 'control' access; risky actions wait for approval on the owner's phone."}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": i, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": i, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name, args = str(params.get("name", "")), params.get("arguments") or {}
        if name not in {t["name"] for t in TOOLS}:
            return rpc_err(i, -32602, "unknown tool")
        try:
            res = await tool_call(name, args, ctx)
            audit(ctx["user"], ctx["client"], name, args, "ok")
            return {"jsonrpc": "2.0", "id": i, "result": {"content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False, default=str)[:60000]}], "isError": False}}
        except (PermissionError, ValueError) as e:
            audit(ctx["user"], ctx["client"], name, args, "denied", e)
            return {"jsonrpc": "2.0", "id": i, "result": {"content": [{"type": "text", "text": f"Refused: {e}"}], "isError": True}}
        except web.HTTPException as e:
            audit(ctx["user"], ctx["client"], name, args, "error", e.reason)
            return {"jsonrpc": "2.0", "id": i, "result": {"content": [{"type": "text", "text": "Home Assistant error"}], "isError": True}}
    return rpc_err(i, -32601, "method not found")


# ---------------------------------------------------------------- panel (ingress, admin)
@web.middleware
async def ingress_guard(request, handler):
    if not DEV and request.remote not in INGRESS_PEERS:
        raise err(403, "ingress only")
    return await handler(request)


def cert_info():
    f = SSL_DIR / str(OPT.get("certfile") or "fullchain.pem")
    return f.exists()


def warnings():
    w = []
    if not public_url().startswith("https://"):
        w.append("public_url must be an https:// address (your DDNS name, e.g. https://name.duckdns.org:8443).")
    if not allowed_users():
        w.append("allowed_users is empty - nobody can sign in. Add your Home Assistant username in the add-on Configuration.")
    if OPT.get("tls", "auto") == "auto" and not cert_info():
        w.append("No certificate found in /ssl - issue one (e.g. with HACertTeo) and restart the add-on.")
    if not OPT.get("require_mfa", True):
        w.append("require_mfa is off: anyone with your HA password could authorize Claude. Turn it on.")
    if OPT.get("approve_risky", True) and not str(OPT.get("notify_service") or "").strip():
        w.append("No notify_service: risky actions (unlock, garage, scripts) are refused. Set one to approve them on your phone.")
    return w


async def h_index(request):
    return web.Response(text=(STATIC / "index.html").read_text(), content_type="text/html", headers={"Cache-Control": "no-store"})


async def h_state(request):
    options()
    now = time.time()
    sess = [{"id": v["sid"], "client": state["clients"].get(v["client_id"], {}).get("name", "?"), "user": v["user"], "created": v["created"], "last": v["last"], "exp": v["exp"]}
            for v in state["refresh"].values() if v["exp"] > now]
    rd, ctl = exposure_summary()
    return web.json_response({"enabled": state["enabled"], "public_url": public_url(), "mcp_url": public_url() + "/mcp" if public_url() else "", "port": PUBLIC_PORT,
                              "tls": OPT.get("tls", "auto"), "cert": cert_info(), "users": sorted(allowed_users()), "require_mfa": bool(OPT.get("require_mfa", True)),
                              "notify": bool(str(OPT.get("notify_service") or "").strip()), "approve_risky": bool(OPT.get("approve_risky", True)),
                              "ips": lst("allowed_ips"), "sessions": sess, "read": rd, "control": ctl, "warnings": warnings(), "version": VERSION})


async def h_entities(request):
    q = request.query.get("q", "").strip().lower()[:40]
    dom = request.query.get("domain", "")
    only = request.query.get("exposed") == "1"
    st, states = await ha("GET", "/states")
    rows = []
    for s in states if isinstance(states, list) else []:
        eid = s.get("entity_id", "")
        d = eid.split(".")[0]
        if d not in READ_DOMAINS or (dom and d != dom) or (only and level(eid) == "none"):
            continue
        nm = (s.get("attributes") or {}).get("friendly_name", "")
        if q and q not in (eid + " " + nm).lower():
            continue
        rows.append({"id": eid, "name": nm, "level": level(eid), "can_control": d in SERVICES})
    rows.sort(key=lambda r: r["id"])
    return web.json_response({"items": rows[:150], "total": len(rows), "domains": sorted(READ_DOMAINS)})


async def h_exposure(request):
    b = await request.json()
    ch = b.get("changes")
    if not isinstance(ch, dict) or len(ch) > 500:
        raise err(400, "bad request")
    for eid, lv in ch.items():
        if not ent_ok(eid) or lv not in ("none", "read", "control") or eid.split(".")[0] not in READ_DOMAINS:
            continue
        if lv == "control" and eid.split(".")[0] not in SERVICES:
            lv = "read"
        if lv == "none":
            state["exposure"].pop(eid, None)
        else:
            state["exposure"][eid] = lv
    save()
    audit("panel", "", "exposure", {"changed": len(ch)}, "ok")
    return web.json_response({"ok": True})


async def h_import_assist(request):
    """Add everything exposed to Assist as read-only (a convenient starting point)."""
    try:
        async with session.ws_connect(HA_WS, timeout=15) as ws:
            await ws.receive_json(timeout=10)
            await ws.send_json({"type": "auth", "access_token": TOKEN})
            await ws.receive_json(timeout=10)
            await ws.send_json({"id": 1, "type": "homeassistant/expose_entity/list"})
            d = await ws.receive_json(timeout=15)
    except Exception:  # noqa: BLE001
        raise err(502, "could not read the Assist exposure list")
    n = 0
    for eid, v in ((d.get("result") or {}).get("exposed_entities") or {}).items():
        if ent_ok(eid) and eid.split(".")[0] in READ_DOMAINS and isinstance(v, dict) and any(x is True for x in v.values()):
            if eid not in state["exposure"]:
                state["exposure"][eid] = "read"
                n += 1
    save()
    return web.json_response({"ok": True, "added": n})


async def h_sessions_del(request):
    revoke_sid(request.match_info["id"])
    audit("panel", "", "revoke", {"sid": request.match_info["id"]}, "ok")
    return web.json_response({"ok": True})


async def h_revoke_all(request):
    state["refresh"].clear()
    access.clear()
    save()
    audit("panel", "", "revoke-all", {}, "ok")
    return web.json_response({"ok": True})


async def h_enabled(request):
    state["enabled"] = bool((await request.json()).get("enabled"))
    if not state["enabled"]:
        state["refresh"].clear()
        access.clear()
    save()
    audit("panel", "", "enabled", {"enabled": state["enabled"]}, "ok")
    return web.json_response({"ok": True})


async def h_log(request):
    return web.json_response({"rows": read_audit(200)})


def build_apps():
    ui = web.Application(middlewares=[ingress_guard], client_max_size=256 * 1024)
    ui.add_routes([web.get("/", h_index), web.static("/static", STATIC), web.get("/api/state", h_state), web.get("/api/entities", h_entities), web.post("/api/exposure", h_exposure),
                   web.post("/api/exposure/import-assist", h_import_assist), web.delete("/api/sessions/{id}", h_sessions_del), web.post("/api/revoke-all", h_revoke_all),
                   web.post("/api/enabled", h_enabled), web.get("/api/log", h_log)])
    pub = web.Application(client_max_size=64 * 1024)
    pub.add_routes([web.get("/.well-known/oauth-authorization-server", h_meta_as), web.get("/.well-known/oauth-authorization-server/mcp", h_meta_as),
                    web.get("/.well-known/oauth-protected-resource", h_meta_pr), web.get("/.well-known/oauth-protected-resource/mcp", h_meta_pr),
                    web.post("/register", h_register), web.get("/authorize", h_authorize), web.post("/authorize/login", h_login), web.post("/authorize/mfa", h_mfa),
                    web.post("/authorize/consent", h_consent), web.post("/token", h_token), web.post("/revoke", h_revoke),
                    web.post("/mcp", h_mcp), web.get("/mcp", h_mcp_get)])
    async def _hide(request, response):
        response.headers["Server"] = "HAMcpTeo"
    pub.on_response_prepare.append(_hide)
    return ui, pub


def ssl_context():
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(SSL_DIR / str(OPT.get("certfile") or "fullchain.pem"), SSL_DIR / str(OPT.get("keyfile") or "privkey.pem"))
    return ctx


async def serve_public(pub):
    """Public HTTPS listener; the certificate is re-read when it changes (renewal) without restarting the add-on."""
    runner, site, stamp = None, None, None
    while True:
        try:
            options()
            want_tls = OPT.get("tls", "auto") == "auto"
            f = SSL_DIR / str(OPT.get("certfile") or "fullchain.pem")
            cur = (f.stat().st_mtime if f.exists() else None, public_url())
            ready = bool(public_url()) and (not want_tls or f.exists())
            if ready and (site is None or cur != stamp):
                if runner:
                    await runner.cleanup()
                runner = web.AppRunner(pub, access_log=None)
                await runner.setup()
                site = web.TCPSite(runner, "0.0.0.0", PUBLIC_PORT, ssl_context=ssl_context() if want_tls else None)
                await site.start()
                stamp = cur
                log.info("Public endpoint %s on port %s (%s)", public_url(), PUBLIC_PORT, "HTTPS" if want_tls else "HTTP behind your own proxy")
            elif not ready and site is not None:
                await runner.cleanup()
                runner = site = None
                log.warning("Public endpoint stopped (public_url or certificate missing)")
        except Exception as exc:  # noqa: BLE001
            log.error("public listener: %s", exc)
        await asyncio.sleep(3600 if site else 60)


async def main():
    global session
    options()
    logging.basicConfig(level=getattr(logging, str(OPT.get("log_level", "info")).upper(), logging.INFO), format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
    DATA.mkdir(parents=True, exist_ok=True)
    load()
    session = ClientSession(timeout=ClientTimeout(total=30))
    ui, pub = build_apps()
    r1 = web.AppRunner(ui, access_log=None)
    await r1.setup()
    try:
        await web.TCPSite(r1, "0.0.0.0", INGRESS_PORT).start()
    except OSError as exc:
        log.error("Cannot listen on port %s: %s", INGRESS_PORT, exc)
        raise SystemExit(1)
    for w in warnings():
        log.warning(w)
    log.info("HAMcpTeo %s by %s (%s)", VERSION, CREDIT, CREDIT_URL)
    asyncio.create_task(serve_public(pub))
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
