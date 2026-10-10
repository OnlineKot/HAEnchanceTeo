#!/usr/bin/env python3
"""HACardsTeo - installs the TeodorTeo Lovelace cards (teodorteo-cards.js) into /config/www and registers them
as a Lovelace resource over a short-lived Home Assistant WebSocket. Ingress panel only - no network ports.
By TeodorTeo.com (https://teodorteo.com)."""
import asyncio
import contextlib
import json
import logging
import os
import re
import shutil
from pathlib import Path

from aiohttp import ClientSession, ClientTimeout, web

CREDIT = "TeodorTeo.com"
STATIC = Path(__file__).parent / "static"
BUNDLE = STATIC / "teodorteo-cards.js"
DATA = Path(os.environ.get("HCC_DATA", "/data"))
OPTIONS_FILE = Path(os.environ.get("HCC_OPTIONS", "/data/options.json"))
STATE_FILE = DATA / "state.json"
INGRESS_PORT = int(os.environ.get("HCC_INGRESS_PORT", 8099))
INGRESS_PEERS = {"172.30.32.2", "127.0.0.1", "::1"}
DEV = bool(os.environ.get("HCC_DEV"))
HA_WS = os.environ.get("HCC_HA_WS", "ws://supervisor/core/websocket")
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
SUBDIR, FILENAME = "hacardsteo", "teodorteo-cards.js"
BASE_URL = f"/local/{SUBDIR}/{FILENAME}"
VER_RE = re.compile(r'(?:const VERSION|TEO_CARDS_VERSION)\s*=\s*"([^"]+)"')

log = logging.getLogger("hacardsteo")
lock = asyncio.Lock()


def config_dir():
    env = os.environ.get("HCC_CONFIG")
    if env:
        return Path(env)
    for p in ("/homeassistant", "/config"):
        if Path(p).is_dir():
            return Path(p)
    return Path("/config")


def options():
    try:
        return json.loads(OPTIONS_FILE.read_text())
    except Exception:  # noqa: BLE001
        return {}


def read_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:  # noqa: BLE001
        return {}


def write_state(s):
    DATA.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s))


def file_version(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            m = VER_RE.search(f.read(4096))
        return m.group(1) if m else "?"
    except OSError:
        return None


def bundle_version():
    return file_version(BUNDLE) or "?"


def err(status, message):
    cls = {400: web.HTTPBadRequest, 403: web.HTTPForbidden, 404: web.HTTPNotFound, 409: web.HTTPConflict, 502: web.HTTPBadGateway}[status]
    return cls(text=json.dumps({"error": message}), content_type="application/json")


# ---------------------------------------------------------------- Home Assistant WebSocket (opened per operation, closed right after)
class HAError(Exception):
    def __init__(self, code, message=""):
        super().__init__(f"{code}: {message}")
        self.code, self.message = code, message


class WS:
    def __init__(self, ws):
        self.ws, self.n = ws, 0

    async def call(self, type_, **kw):
        self.n += 1
        await self.ws.send_json({"id": self.n, "type": type_, **kw})
        while True:
            m = await self.ws.receive_json()
            if m.get("id") == self.n:
                break
        if not m.get("success"):
            e = m.get("error") or {}
            raise HAError(e.get("code", "error"), e.get("message", ""))
        return m.get("result")


@contextlib.asynccontextmanager
async def ha_ws():
    async with ClientSession(timeout=ClientTimeout(total=20)) as s:
        async with s.ws_connect(HA_WS, max_msg_size=8 * 1024 * 1024) as ws:
            await ws.receive_json()
            await ws.send_json({"type": "auth", "access_token": TOKEN})
            r = await ws.receive_json()
            if r.get("type") != "auth_ok":
                raise HAError("auth_failed", "Home Assistant rejected the token")
            yield WS(ws)


async def resource_status(ws=None):
    """Returns dict(mode, items) for resources that belong to this add-on."""
    async def run(w):
        mode = None
        with contextlib.suppress(HAError):
            mode = (await w.call("lovelace/info")).get("mode")
        items = await w.call("lovelace/resources")
        return mode, [i for i in items if str(i.get("url", "")).split("?")[0] == BASE_URL]
    if ws:
        return await run(ws)
    async with ha_ws() as w:
        return await run(w)


async def register(version):
    target = f"{BASE_URL}?v={version}"
    out = {"checked": True, "registered": False, "url": "", "mode": "storage", "manual": target, "action": "", "error": ""}
    try:
        async with ha_ws() as ws:
            mode, mine = await resource_status(ws)
            out["mode"] = mode or "storage"
            for extra in mine[1:]:
                with contextlib.suppress(HAError):
                    await ws.call("lovelace/resources/delete", resource_id=extra["id"])
            if mine:
                cur = mine[0]
                if cur["url"] == target:
                    out.update(registered=True, url=target, action="unchanged")
                else:
                    try:
                        await ws.call("lovelace/resources/update", resource_id=cur["id"], res_type="module", url=target)
                        out.update(registered=True, url=target, action="updated")
                    except HAError as e:
                        out.update(registered=True, url=cur["url"], mode="yaml", error=e.message or e.code)
            else:
                try:
                    await ws.call("lovelace/resources/create", res_type="module", url=target)
                    out.update(registered=True, url=target, action="created")
                except HAError as e:
                    out.update(mode="yaml", error=e.message or e.code)
    except HAError as e:
        out["error"] = e.message or e.code
    except Exception as e:  # noqa: BLE001
        out["error"] = f"Cannot reach Home Assistant: {e}"
    return out


async def unregister():
    try:
        async with ha_ws() as ws:
            _, mine = await resource_status(ws)
            for i in mine:
                await ws.call("lovelace/resources/delete", resource_id=i["id"])
            return {"removed": len(mine), "error": ""}
    except Exception as e:  # noqa: BLE001
        return {"removed": 0, "error": getattr(e, "message", "") or str(e)}


# ---------------------------------------------------------------- install
def target_path():
    return config_dir() / "www" / SUBDIR / FILENAME


def copy_bundle():
    dest = target_path()
    www = dest.parent.parent
    created = not www.exists()
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    shutil.copyfile(BUNDLE, tmp)
    os.replace(tmp, dest)
    if created:
        s = read_state()
        s["www_created"] = True
        write_state(s)
    return created


async def do_install():
    async with lock:
        created = await asyncio.to_thread(copy_bundle)
        res = await register(bundle_version())
        log.info("Installed v%s to %s; resource: %s%s", bundle_version(), target_path(), res["action"] or "not registered", f" ({res['error']})" if res["error"] else "")
        return {"copied": True, "www_created": created, "resource": res}


async def do_remove():
    async with lock:
        res = await unregister()
        removed = False
        p = target_path()
        if p.exists():
            p.unlink()
            removed = True
            with contextlib.suppress(OSError):
                p.parent.rmdir()
        log.info("Removed (file=%s, resources=%s)", removed, res["removed"])
        return {"file_removed": removed, **res}


async def get_status(check_ha=True):
    p = target_path()
    v = file_version(p)
    out = {"version": bundle_version(), "installed_version": v, "file_present": v is not None, "path": str(p), "url": f"{BASE_URL}?v={bundle_version()}",
           "needs_restart": bool(read_state().get("www_created")), "auto_install": bool(options().get("auto_install", True)),
           "resource": {"checked": False, "registered": False, "url": "", "mode": "unknown", "error": "", "manual": f"{BASE_URL}?v={bundle_version()}"}}
    if check_ha:
        r = out["resource"]
        try:
            mode, mine = await resource_status()
            r.update(checked=True, mode=mode or "storage", registered=bool(mine), url=mine[0]["url"] if mine else "")
            if mine:
                r["current"] = mine[0]["url"] == out["url"]
        except Exception as e:  # noqa: BLE001
            r["error"] = getattr(e, "message", "") or str(e)
    return out


# ---------------------------------------------------------------- web
@web.middleware
async def ingress_guard(request, handler):
    if not DEV and request.remote not in INGRESS_PEERS:
        raise err(403, "ingress only")
    return await handler(request)


async def h_index(request):
    return web.Response(text=(STATIC / "index.html").read_text(), content_type="text/html", headers={"Cache-Control": "no-store"})


async def h_status(request):
    return web.json_response(await get_status())


async def h_install(request):
    return web.json_response({**await do_install(), "status": await get_status()})


async def h_remove(request):
    return web.json_response({**await do_remove(), "status": await get_status()})


async def h_ack(request):
    s = read_state()
    s.pop("www_created", None)
    write_state(s)
    return web.json_response({"ok": True})


def build_app():
    app = web.Application(middlewares=[ingress_guard], client_max_size=16 * 1024)
    app.add_routes([web.get("/", h_index), web.static("/static", STATIC), web.get("/api/status", h_status), web.post("/api/install", h_install),
                    web.post("/api/remove", h_remove), web.post("/api/ack", h_ack)])
    return app


async def auto_install():
    """Copy now; register with a few retries (Home Assistant may still be starting). The task ends afterwards."""
    for n in range(8):
        try:
            r = await do_install()
            if r["resource"]["registered"] or r["resource"]["mode"] == "yaml":
                return
        except Exception:  # noqa: BLE001
            log.exception("auto install")
        await asyncio.sleep(15 * (n + 1))
    log.warning("Could not register the Lovelace resource automatically - use the panel (Install) or add it manually.")


async def main():
    logging.basicConfig(level=getattr(logging, str(options().get("log_level", "info")).upper(), logging.INFO), format="%(asctime)s %(levelname)s %(message)s")
    runner = web.AppRunner(build_app())
    await runner.setup()
    try:
        await web.TCPSite(runner, "0.0.0.0", INGRESS_PORT).start()
    except OSError as exc:
        log.error("Cannot listen on port %s: %s", INGRESS_PORT, exc)
        raise SystemExit(1)
    log.info("HACardsTeo v%s by %s - panel via ingress only, no network ports published", bundle_version(), CREDIT)
    if options().get("auto_install", True):
        asyncio.create_task(auto_install())
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
