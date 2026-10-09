#!/usr/bin/env python3
"""HAPingTeo - uptime and latency monitor for Home Assistant. By TeodorTeo.com (https://teodorteo.com)."""
import asyncio
import collections
import json
import logging
import os
import re
import socket
import time
import uuid
from pathlib import Path

from aiohttp import ClientSession, ClientTimeout, TCPConnector, web

CREDIT, CREDIT_URL = "TeodorTeo.com", "https://teodorteo.com"
DATA = Path(os.environ.get("HAP_DATA", "/data"))
STATIC = Path(__file__).parent / "static"
MON_FILE, SET_FILE, HIST_FILE = DATA / "monitors.json", DATA / "settings.json", DATA / "history.json"
INGRESS_PORT = int(os.environ.get("HAP_INGRESS_PORT", 8099))
INGRESS_PEERS = {"172.30.32.2", "127.0.0.1", "::1"}
DEV = bool(os.environ.get("HAP_DEV"))
HA = os.environ.get("HAP_HA_URL", "http://supervisor/core/api")
SUPERVISOR = os.environ.get("HAP_SUPERVISOR_URL", "http://supervisor")
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.\-]{0,251}[A-Za-z0-9])?$|^[0-9a-fA-F:]{2,45}$")
PHONE_RE = re.compile(r"^mobile_app_[a-z0-9_]{1,60}$")
HISTORY_POINTS = 2880          # per monitor (48 h at 1 check/min)
MAX_MONITORS = 50

log = logging.getLogger("hapingteo")
session: ClientSession = None
monitors: list = []
state: dict = {}               # monitor id -> runtime: ring, status, fails, since, last_post, task
settings = {"phones": [], "notify_down": True, "notify_up": True, "sensors": True}
ping_works = True


def load_options():
    try:
        return json.loads(Path("/data/options.json").read_text())
    except (OSError, ValueError):
        return {}


OPTIONS = load_options()


def err(status, message):
    cls = {400: web.HTTPBadRequest, 403: web.HTTPForbidden, 404: web.HTTPNotFound, 502: web.HTTPBadGateway}[status]
    return cls(text=json.dumps({"error": message}), content_type="application/json")


# ---------------------------------------------------------------- storage
def write_json(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower().replace("ł", "l")).strip("_")[:40] or "monitor"


def clean_monitor(raw, old=None):
    old = old or {}
    typ = raw.get("type", old.get("type", "ping"))
    if typ not in ("ping", "tcp", "http", "dns"):
        raise err(400, "type must be ping, tcp, http or dns")
    name = str(raw.get("name", old.get("name", "")) or "").strip()[:40]
    target = str(raw.get("target", old.get("target", "")) or "").strip()[:300]
    if not name or not target:
        raise err(400, "name and target are required")
    if typ == "http" and not re.match(r"^https?://[^\s]+$", target):
        raise err(400, "HTTP target must be a URL starting with http:// or https://")
    if typ != "http" and not HOST_RE.match(target):
        raise err(400, "target must be a hostname or IP address")
    def num(k, d, lo, hi):
        try:
            return int(max(lo, min(hi, float(raw.get(k, old.get(k, d))))))
        except (TypeError, ValueError):
            return d
    return {"id": old.get("id") or uuid.uuid4().hex[:8], "name": name, "type": typ, "target": target,
            "port": num("port", 443, 1, 65535), "interval": num("interval", 60, 10, 3600), "timeout": num("timeout", 5, 1, 30),
            "retries": num("retries", 2, 1, 10), "expect_status": num("expect_status", 0, 0, 599),
            "keyword": str(raw.get("keyword", old.get("keyword", "")) or "")[:100],
            "verify_ssl": bool(raw.get("verify_ssl", old.get("verify_ssl", True))),
            "enabled": bool(raw.get("enabled", old.get("enabled", True))), "notify": bool(raw.get("notify", old.get("notify", True)))}


def load_all():
    global monitors, settings
    try:
        monitors = json.loads(MON_FILE.read_text())
    except (OSError, ValueError):
        monitors = []
    try:
        settings.update(json.loads(SET_FILE.read_text()))
    except (OSError, ValueError):
        pass
    try:
        hist = json.loads(HIST_FILE.read_text())
    except (OSError, ValueError):
        hist = {}
    for m in monitors:
        rt = runtime(m["id"])
        for p in hist.get(m["id"], [])[-HISTORY_POINTS:]:
            rt["ring"].append(tuple(p))


def runtime(mid):
    return state.setdefault(mid, {"ring": collections.deque(maxlen=HISTORY_POINTS), "status": "unknown", "fails": 0,
                                  "since": time.time(), "last_post": 0.0, "task": None, "last_error": ""})


def save_history():
    write_json(HIST_FILE, {mid: list(rt["ring"]) for mid, rt in state.items()})


# ---------------------------------------------------------------- Home Assistant
def ha_headers():
    return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


async def ha_post(path, data):
    async with session.post(f"{HA}{path}", headers=ha_headers(), json=data) as r:
        if r.status >= 400:
            raise err(502, f"Home Assistant {r.status}")


async def safe_post(path, data):
    try:
        await ha_post(path, data)
    except Exception as exc:  # noqa: BLE001
        log.debug("%s failed: %s", path, exc)


async def notify(title, message):
    for phone in settings["phones"]:
        await safe_post(f"/services/notify/{phone}", {"title": title, "message": message, "data": {"tag": "hapingteo", "group": "hapingteo"}})


# ---------------------------------------------------------------- checks
async def check_ping(host, timeout):
    global ping_works
    if ping_works:
        t0 = time.perf_counter()
        try:
            proc = await asyncio.create_subprocess_exec("ping", "-c", "1", "-W", str(timeout), host,
                                                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            out, errb = await asyncio.wait_for(proc.communicate(), timeout + 3)
        except FileNotFoundError:
            ping_works = False
            log.warning("ping binary not found - using TCP checks instead")
            return await check_tcp(host, 443, timeout, fallback=True)
        except asyncio.TimeoutError:
            return False, None, "timeout"
        text = (out + errb).decode(errors="ignore")
        if "permitted" in text or "Operation not" in text:
            ping_works = False
            log.warning("ICMP ping is not permitted in this container - falling back to TCP checks on port 443/80")
            return await check_tcp(host, 443, timeout, fallback=True)
        m = re.search(r"time[=<]([\d.]+)\s*ms", text)
        if proc.returncode == 0:
            return True, float(m.group(1)) if m else (time.perf_counter() - t0) * 1000, ""
        return False, None, "no reply" if "100% packet loss" in text or "unreachable" in text.lower() else "failed"
    return await check_tcp(host, 443, timeout, fallback=True)


async def check_tcp(host, port, timeout, fallback=False):
    t0 = time.perf_counter()
    try:
        r, w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        ms = (time.perf_counter() - t0) * 1000
        w.close()
        return True, ms, ""
    except asyncio.TimeoutError:
        return False, None, "timeout"
    except OSError as exc:
        if fallback and port == 443 and exc.errno == 111:          # ping fallback: refused on 443 still proves the host is up -> try 80
            return await check_tcp(host, 80, timeout)
        return False, None, {111: "connection refused", 113: "no route to host", 101: "network unreachable", 110: "timeout"}.get(
            exc.errno, os.strerror(exc.errno) if exc.errno else "connection failed")


async def check_http(m):
    t0 = time.perf_counter()
    try:
        conn = TCPConnector(ssl=None if m["verify_ssl"] else False)
        async with ClientSession(connector=conn, timeout=ClientTimeout(total=m["timeout"])) as s:
            async with s.get(m["target"], allow_redirects=True) as r:
                body = await r.content.read(262144) if m["keyword"] else b""
                ms = (time.perf_counter() - t0) * 1000
                ok = (r.status == m["expect_status"]) if m["expect_status"] else (r.status < 400)
                if not ok:
                    return False, ms, f"HTTP {r.status}"
                if m["keyword"] and m["keyword"].lower().encode() not in body.lower():
                    return False, ms, "keyword not found"
                return True, ms, ""
    except asyncio.TimeoutError:
        return False, None, "timeout"
    except Exception as exc:  # noqa: BLE001
        return False, None, type(exc).__name__


async def check_dns(host, timeout):
    t0 = time.perf_counter()
    try:
        await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM), timeout)
        return True, (time.perf_counter() - t0) * 1000, ""
    except asyncio.TimeoutError:
        return False, None, "timeout"
    except OSError:
        return False, None, "no such host"


async def run_check(m):
    t = m["type"]
    if t == "ping":
        return await check_ping(m["target"], m["timeout"])
    if t == "tcp":
        return await check_tcp(m["target"], m["port"], m["timeout"])
    if t == "http":
        return await check_http(m)
    return await check_dns(m["target"], m["timeout"])


def stats(rt, hours=24):
    since = time.time() - hours * 3600
    pts = [p for p in rt["ring"] if p[0] >= since]
    ok = [p for p in pts if p[1]]
    lat = sorted(p[2] for p in ok if p[2] is not None)
    return {"checks": len(pts), "uptime": round(100 * len(ok) / len(pts), 2) if pts else None,
            "avg": round(sum(lat) / len(lat), 1) if lat else None, "min": round(lat[0], 1) if lat else None,
            "max": round(lat[-1], 1) if lat else None, "p95": round(lat[int(len(lat) * .95) - 1], 1) if len(lat) >= 5 else None}


async def publish(m, rt, force=False):
    if not settings["sensors"] or (not force and time.time() - rt["last_post"] < 60):
        return
    rt["last_post"] = time.time()
    s24 = stats(rt)
    last = rt["ring"][-1] if rt["ring"] else None
    sid = slug(m["name"])
    await safe_post(f"/states/binary_sensor.hapingteo_{sid}", {"state": "on" if rt["status"] == "up" else "off", "attributes": {
        "friendly_name": f"{m['name']} (ping)", "device_class": "connectivity", "icon": "mdi:lan-connect", "target": m["target"], "type": m["type"],
        "latency_ms": round(last[2], 1) if last and last[2] is not None else None, "uptime_24h": s24["uptime"], "error": rt["last_error"]}})
    if last and last[2] is not None:
        await safe_post(f"/states/sensor.hapingteo_{sid}_latency", {"state": round(last[2], 1), "attributes": {
            "friendly_name": f"{m['name']} latency", "unit_of_measurement": "ms", "icon": "mdi:speedometer", "state_class": "measurement"}})


async def publish_summary():
    if not settings["sensors"]:
        return
    down = [m["name"] for m in monitors if m["enabled"] and state.get(m["id"], {}).get("status") == "down"]
    await safe_post("/states/sensor.hapingteo_status", {"state": f"{len(down)} down" if down else "all up", "attributes": {
        "friendly_name": "HAPing status", "icon": "mdi:lan-connect", "down": down, "monitors": sum(1 for m in monitors if m["enabled"])}})
    await safe_post("/states/binary_sensor.hapingteo_problem", {"state": "on" if down else "off", "attributes": {
        "friendly_name": "HAPing problem", "device_class": "problem", "down": down}})


async def do_check(m):
    rt = runtime(m["id"])
    ok, ms, error = await run_check(m)
    rt["ring"].append((round(time.time(), 1), bool(ok), round(ms, 1) if ms is not None else None))
    rt["last_error"] = "" if ok else error
    prev = rt["status"]
    if ok:
        rt["fails"] = 0
        if prev != "up":
            down_for = time.time() - rt["since"]
            rt["status"], rt["since"] = "up", time.time()
            if prev == "down":
                log.info("%s is back UP", m["name"])
                if settings["notify_up"] and m["notify"]:
                    await notify("✅ " + m["name"] + " is back", f"Down for {int(down_for // 60)} min {int(down_for % 60)} s · {round(ms)} ms")
                await publish(m, rt, force=True)
                await publish_summary()
    else:
        rt["fails"] += 1
        if rt["fails"] >= m["retries"] and prev != "down":
            rt["status"], rt["since"] = "down", time.time()
            log.info("%s is DOWN (%s)", m["name"], error)
            if settings["notify_down"] and m["notify"]:
                await notify("🔴 " + m["name"] + " is down", f"{m['target']} · {error}")
            await publish(m, rt, force=True)
            await publish_summary()
    if prev == "unknown" and rt["status"] == "unknown" and ok is not None:
        rt["status"] = "up" if ok else "unknown"
        if ok:
            await publish_summary()
    await publish(m, rt)
    return ok, ms, error


async def monitor_loop(m):
    await asyncio.sleep(0.5 + (hash(m["id"]) % 20) / 10)       # spread the checks
    while True:
        cur = next((x for x in monitors if x["id"] == m["id"]), None)
        if cur is None:
            return
        if cur["enabled"]:
            try:
                await do_check(cur)
            except Exception as exc:  # noqa: BLE001
                log.warning("check %s failed: %s", cur["name"], exc)
        await asyncio.sleep(cur["interval"])


def start_monitor(m):
    rt = runtime(m["id"])
    if rt["task"]:
        rt["task"].cancel()
    rt["task"] = asyncio.create_task(monitor_loop(m))


async def history_saver():
    while True:
        await asyncio.sleep(300)
        save_history()


# ---------------------------------------------------------------- API
def view(m):
    rt = runtime(m["id"])
    recent = list(rt["ring"])[-90:]
    return {**m, "status": rt["status"] if m["enabled"] else "paused", "since": rt["since"], "fails": rt["fails"], "error": rt["last_error"],
            "stats24": stats(rt, 24), "stats1": stats(rt, 1), "recent": recent}


async def gateway():
    try:
        async with session.get(f"{SUPERVISOR}/network/info", headers={"Authorization": f"Bearer {TOKEN}"}) as r:
            ifaces = (await r.json()).get("data", {}).get("interfaces", [])
        ifaces.sort(key=lambda i: not i.get("primary"))
        for i in ifaces:
            gw = (i.get("ipv4") or {}).get("gateway")
            if gw:
                return gw
    except Exception:  # noqa: BLE001
        pass
    return ""


async def h_state(request):
    names = []
    try:
        async with session.get(f"{HA}/services", headers=ha_headers()) as r:
            names = sorted(n for d in await r.json() if d["domain"] == "notify" for n in d["services"] if PHONE_RE.match(n))
    except Exception:  # noqa: BLE001
        pass
    mons = [view(m) for m in monitors]
    down = sum(1 for m in mons if m["status"] == "down")
    ups = [m["stats24"]["uptime"] for m in mons if m["stats24"]["uptime"] is not None]
    avgs = [m["stats1"]["avg"] for m in mons if m["stats1"]["avg"] is not None]
    return web.json_response({"monitors": mons, "settings": settings, "notify": names, "now": time.time(), "ping_works": ping_works,
                              "summary": {"total": len(mons), "down": down, "uptime": round(sum(ups) / len(ups), 2) if ups else None,
                                          "avg": round(sum(avgs) / len(avgs), 1) if avgs else None},
                              "credit": {"name": CREDIT, "url": CREDIT_URL}})


async def h_save(request):
    raw = await request.json()
    old = next((m for m in monitors if m["id"] == raw.get("id")), None)
    if not old and len(monitors) >= MAX_MONITORS:
        raise err(400, f"limit of {MAX_MONITORS} monitors reached")
    m = clean_monitor(raw, old)
    if old:
        monitors[monitors.index(old)] = m
    else:
        monitors.append(m)
    write_json(MON_FILE, monitors)
    start_monitor(m)
    return web.json_response(view(m))


async def h_delete(request):
    m = next((x for x in monitors if x["id"] == request.match_info["id"]), None)
    if not m:
        raise err(404, "not found")
    monitors.remove(m)
    rt = state.pop(m["id"], None)
    if rt and rt["task"]:
        rt["task"].cancel()
    write_json(MON_FILE, monitors)
    save_history()
    await publish_summary()
    return web.json_response({"ok": True})


async def h_check(request):
    m = next((x for x in monitors if x["id"] == request.match_info["id"]), None)
    if not m:
        raise err(404, "not found")
    ok, ms, error = await do_check(m)
    return web.json_response({"ok": bool(ok), "ms": round(ms, 1) if ms is not None else None, "error": error, "monitor": view(m)})


async def h_history(request):
    m = next((x for x in monitors if x["id"] == request.match_info["id"]), None)
    if not m:
        raise err(404, "not found")
    hours = max(1, min(48, int(request.query.get("hours", 24))))
    since = time.time() - hours * 3600
    return web.json_response({"points": [p for p in runtime(m["id"])["ring"] if p[0] >= since], "stats": stats(runtime(m["id"]), hours)})


async def h_presets(request):
    which = (await request.json()).get("preset")
    sets = {"internet": [("Internet (Cloudflare)", "ping", "1.1.1.1"), ("Internet (Google)", "ping", "8.8.8.8"), ("DNS (google.com)", "dns", "google.com"),
                         ("Web (Google 204)", "http", "https://www.google.com/generate_204")]}
    items = sets.get(which, [])
    if which == "router":
        gw = await gateway()
        if not gw:
            raise err(400, "could not detect the router (gateway) address")
        items = [("Router", "ping", gw)]
    if which == "ha":
        items = [("Home Assistant", "tcp", "homeassistant")]
    if not items:
        raise err(400, "unknown preset")
    added = []
    for name, typ, target in items:
        if any(m["target"] == target and m["type"] == typ for m in monitors) or len(monitors) >= MAX_MONITORS:
            continue
        m = clean_monitor({"name": name, "type": typ, "target": target, "port": 8123 if which == "ha" else 443})
        monitors.append(m)
        start_monitor(m)
        added.append(m["name"])
    write_json(MON_FILE, monitors)
    return web.json_response({"added": added})


async def h_settings(request):
    raw = await request.json()
    settings["phones"] = [p for p in (str(x).removeprefix("notify.") for x in raw.get("phones", settings["phones"])) if PHONE_RE.match(p)][:8]
    for k in ("notify_down", "notify_up", "sensors"):
        if k in raw:
            settings[k] = bool(raw[k])
    write_json(SET_FILE, settings)
    return web.json_response(settings)


async def h_test(request):
    if not settings["phones"]:
        raise err(400, "pick at least one phone")
    await notify("HAPingTeo", "Test notification ✅")
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
    app.add_routes([web.get("/", h_index), web.static("/static", STATIC), web.get("/api/state", h_state), web.post("/api/monitors", h_save),
                    web.delete("/api/monitors/{id}", h_delete), web.post("/api/monitors/{id}/check", h_check), web.get("/api/history/{id}", h_history),
                    web.post("/api/presets", h_presets), web.post("/api/settings", h_settings), web.post("/api/test", h_test)])
    return app


async def main():
    global session
    logging.basicConfig(level=getattr(logging, str(OPTIONS.get("log_level", "info")).upper(), logging.INFO), format="%(asctime)s %(levelname)s %(message)s")
    DATA.mkdir(parents=True, exist_ok=True)
    load_all()
    session = ClientSession(timeout=ClientTimeout(total=30))
    runner = web.AppRunner(build_app())
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", INGRESS_PORT).start()
    log.info("HAPingTeo by %s (%s) - panel :%s, %d monitors", CREDIT, CREDIT_URL, INGRESS_PORT, len(monitors))
    for m in monitors:
        start_monitor(m)
    asyncio.create_task(history_saver())
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
