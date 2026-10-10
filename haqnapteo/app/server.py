#!/usr/bin/env python3
"""HAQnapTeo - back up Home Assistant to a QNAP (SMB) and download media from it.
Panel only through Home Assistant ingress - no network ports are published.
By TeodorTeo.com (https://teodorteo.com)."""
import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from aiohttp import ClientSession, ClientTimeout, web

CREDIT, CREDIT_URL = "TeodorTeo.com", "https://teodorteo.com"
DATA = Path(os.environ.get("HQT_DATA", "/data"))
OPTIONS_FILE = Path(os.environ.get("HQT_OPTIONS", "/data/options.json"))
BACKUP_DIR = Path(os.environ.get("HQT_BACKUP", "/backup"))
MEDIA_DIR = Path(os.environ.get("HQT_MEDIA", "/media"))
SMBCLIENT = os.environ.get("HQT_SMBCLIENT", "smbclient")
STATE_FILE = DATA / "state.json"
AUTH_FILE = DATA / "smb.auth"
STATIC = Path(__file__).parent / "static"
INGRESS_PORT = int(os.environ.get("HQT_INGRESS_PORT", 8099))
INGRESS_PEERS = {"172.30.32.2", "127.0.0.1", "::1"}
DEV = bool(os.environ.get("HQT_DEV"))
HA = os.environ.get("HQT_HA_URL", "http://supervisor/core/api")
SUP = os.environ.get("HQT_SUP_URL", "http://supervisor")
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")

LS_RE = re.compile(r"^\s{2}(.+?)\s+([A-Za-z]+)\s+(\d+)\s+(\w{3} \w{3}\s+\d{1,2} \d\d:\d\d:\d\d \d{4})\s*$")
FREE_RE = re.compile(r"(\d+) blocks of size (\d+)\. (\d+) blocks available")
BAD_CHARS = re.compile(r'["\\;\r\n\x00]')
MAX_DEPTH = 8
HISTORY = 40

log = logging.getLogger("haqnapteo")
session = None
tz = timezone.utc
OPT = {}
state = {"history": [], "media_index": {}, "last_backup": 0, "last_media": 0, "last_backup_day": ""}
job = {"running": False, "kind": "", "started": 0, "step": "", "files_done": 0, "files_total": 0, "bytes_done": 0, "cancel": False}
lock = asyncio.Lock()
current_proc = None


class QnapError(Exception):
    pass


def err(status, message):
    cls = {400: web.HTTPBadRequest, 403: web.HTTPForbidden, 404: web.HTTPNotFound, 409: web.HTTPConflict, 502: web.HTTPBadGateway}[status]
    return cls(text=json.dumps({"error": message}), content_type="application/json")


def load_options():
    global OPT
    try:
        OPT = json.loads(OPTIONS_FILE.read_text())
    except Exception:  # noqa: BLE001
        OPT = {}
    return OPT


def o(key, default=""):
    v = OPT.get(key, default)
    return default if v is None else v


def write_state():
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(STATE_FILE)


def clean_rel(path):
    """Sanitize a path inside the share: forward slashes, no '..', no characters that could break an smbclient command."""
    parts = [p for p in str(path or "").replace("\\", "/").split("/") if p and p != "."]
    if any(p == ".." or BAD_CHARS.search(p) for p in parts):
        raise QnapError(f"Invalid folder name: {path!r}")
    return "/".join(parts)


def configured():
    return bool(o("host") and o("share") and o("username"))


def write_auth():
    fd = os.open(AUTH_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(f"username = {o('username')}\npassword = {o('password')}\n")
        if o("domain"):
            f.write(f"domain = {o('domain')}\n")


def history(kind, ok, text, **extra):
    state["history"].insert(0, {"ts": int(time.time()), "kind": kind, "ok": ok, "text": text, **extra})
    del state["history"][HISTORY:]
    write_state()


# ---------------------------------------------------------------- smbclient
async def smb(*commands, check=True, timeout=None):
    """Run smbclient commands (list of command strings) against the share. Returns stdout."""
    global current_proc
    if not configured():
        raise QnapError("QNAP is not configured - fill in host, share and username in the add-on Configuration tab.")
    for c in commands:
        if "\n" in c:
            raise QnapError("Invalid command")
    cmd = [SMBCLIENT, f"//{o('host')}/{o('share')}", "-A", str(AUTH_FILE), "-m", "SMB" + str(o("smb_version", "3")), "-c", "; ".join(commands)]
    env = {**os.environ, "LC_ALL": "C"}
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env)
    current_proc = proc
    try:
        out, errb = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise QnapError("QNAP did not answer in time")
    finally:
        current_proc = None
    text = out.decode("utf-8", "replace")
    etext = errb.decode("utf-8", "replace")
    bad = [l for l in (text + "\n" + etext).splitlines() if "NT_STATUS" in l or "tree connect failed" in l or "Connection to" in l and "failed" in l]
    if job["cancel"]:
        raise QnapError("Cancelled")
    if check and (proc.returncode != 0 or bad):
        msg = (bad[0] if bad else etext.strip() or f"smbclient exit {proc.returncode}")[:200]
        if "LOGON_FAILURE" in msg:
            msg = "Login failed - check username/password (NT_STATUS_LOGON_FAILURE)"
        raise QnapError(msg)
    return text


def parse_ls(text):
    items, free = [], None
    for line in text.splitlines():
        m = LS_RE.match(line)
        if m:
            name, attrs, size, date = m.groups()
            if name in (".", ".."):
                continue
            try:
                mtime = datetime.strptime(date, "%a %b %d %H:%M:%S %Y").replace(tzinfo=tz).timestamp()
            except ValueError:
                mtime = 0
            items.append({"name": name, "dir": "D" in attrs.upper(), "size": int(size), "mtime": int(mtime)})
            continue
        m = FREE_RE.search(line)
        if m:
            free = int(m.group(2)) * int(m.group(3))
    return items, free


async def ls(rel):
    rel = clean_rel(rel)
    text = await smb(f'ls "{rel}/*"' if rel else "ls")
    return parse_ls(text)


async def mkdirs(rel):
    cur = ""
    for part in clean_rel(rel).split("/"):
        if not part:
            continue
        cur = f"{cur}/{part}" if cur else part
        await smb(f'mkdir "{cur}"', check=False)


def human(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024


# ---------------------------------------------------------------- HA helpers
def ha_headers():
    return {"Authorization": f"Bearer {TOKEN}"}


async def set_sensor(entity, value, attrs):
    try:
        async with session.post(f"{HA}/states/sensor.{entity}", headers=ha_headers(), json={"state": value, "attributes": attrs}) as r:
            await r.read()
    except Exception as exc:  # noqa: BLE001
        log.debug("sensor update failed: %s", exc)


async def publish():
    iso = lambda ts: datetime.fromtimestamp(ts, tz).isoformat() if ts else None  # noqa: E731
    base = {"friendly_name": "", "icon": "mdi:nas", "attribution": "HAQnapTeo by TeodorTeo.com"}
    last = next((h for h in state["history"] if h["kind"] == "backup"), None)
    await set_sensor("haqnapteo_backup", "ok" if last and last["ok"] else ("error" if last else "unknown"),
                     {**base, "friendly_name": "QNAP backup", "last_success": iso(state["last_backup"]), "detail": last["text"] if last else ""})
    last = next((h for h in state["history"] if h["kind"] == "media"), None)
    await set_sensor("haqnapteo_media", "ok" if last and last["ok"] else ("error" if last else "unknown"),
                     {**base, "friendly_name": "QNAP media", "last_success": iso(state["last_media"]), "detail": last["text"] if last else ""})


async def sup_new_backup():
    name = "HAQnapTeo " + datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    async with session.post(f"{SUP}/backups/new/full", headers=ha_headers(), json={"name": name}, timeout=ClientTimeout(total=3600)) as r:
        if r.status >= 400:
            raise QnapError(f"Could not create a backup in Home Assistant ({r.status}): {(await r.text())[:120]}")


# ---------------------------------------------------------------- jobs
async def run_backup(create=False):
    kind = "backup"
    job.update(kind=kind, step="Connecting", files_done=0, files_total=0, bytes_done=0)
    d = clean_rel(o("backup_dir", "HA-Backups"))
    if create:
        job["step"] = "Creating a Home Assistant backup"
        await sup_new_backup()
    local = sorted((p for p in BACKUP_DIR.glob("*.tar") if p.is_file()), key=lambda p: p.stat().st_mtime)
    await mkdirs(d)
    remote, _ = await ls(d)
    have = {i["name"]: i["size"] for i in remote if not i["dir"]}
    todo = [p for p in local if have.get(p.name) != p.stat().st_size and not BAD_CHARS.search(p.name)]
    job["files_total"] = len(todo)
    sent = 0
    for p in todo:
        job.update(step=f"Uploading {p.name}")
        await smb(f'put "{p}" "{d}/{p.name}"')
        job["files_done"] += 1
        job["bytes_done"] += p.stat().st_size
        sent += 1
    deleted = 0
    keep = int(o("backup_keep", 10))
    remote, _ = await ls(d)
    tars = sorted((i for i in remote if not i["dir"] and i["name"].endswith(".tar")), key=lambda i: i["mtime"], reverse=True)
    for old in tars[keep:]:
        if BAD_CHARS.search(old["name"]):
            continue
        job["step"] = f"Removing old {old['name']}"
        await smb(f'del "{d}/{old["name"]}"')
        deleted += 1
    state["last_backup"] = int(time.time())
    state["last_backup_day"] = datetime.now(tz).strftime("%Y-%m-%d")
    history(kind, True, f"{sent} uploaded, {deleted} old removed, {len(tars) - deleted} kept", bytes=job["bytes_done"])


async def walk(rel, depth=0):
    if depth > MAX_DEPTH:
        return
    items, _ = await ls(rel)
    for it in items:
        if BAD_CHARS.search(it["name"]):
            continue
        path = f"{rel}/{it['name']}" if rel else it["name"]
        if it["dir"]:
            async for sub in walk(path, depth + 1):
                yield sub
        else:
            yield {"path": path, **it}


async def run_media():
    kind = "media"
    job.update(kind=kind, step="Scanning the QNAP folder", files_done=0, files_total=0, bytes_done=0)
    src = clean_rel(o("media_remote_dir", "Multimedia"))
    dst_root = (MEDIA_DIR / clean_rel(o("media_local_dir", "qnap"))).resolve()
    if MEDIA_DIR.resolve() not in dst_root.parents and dst_root != MEDIA_DIR.resolve():
        raise QnapError("Invalid local media folder")
    dst_root.mkdir(parents=True, exist_ok=True)
    index = state["media_index"]
    todo = []
    async for f in walk(src):
        key = f["path"]
        prev = index.get(key)
        rel_local = key[len(src) + 1:] if src else key
        target = (dst_root / rel_local).resolve()
        if dst_root not in target.parents:
            continue
        if prev and prev["size"] == f["size"] and prev["mtime"] == f["mtime"] and target.exists():
            continue
        todo.append((f, target))
        job["files_total"] = len(todo)
    got = 0
    for f, target in todo:
        job["step"] = f"Downloading {f['name']}"
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(target.name + ".part")
        await smb(f'get "{f["path"]}" "{part}"')
        part.replace(target)
        if f["mtime"]:
            os.utime(target, (f["mtime"], f["mtime"]))
        index[f["path"]] = {"size": f["size"], "mtime": f["mtime"]}
        job["files_done"] += 1
        job["bytes_done"] += f["size"]
        got += 1
        if got % 10 == 0:
            write_state()
    state["last_media"] = int(time.time())
    history(kind, True, f"{got} new files downloaded ({human(job['bytes_done'])}), {len(index)} tracked", bytes=job["bytes_done"])


async def run_job(kind, create=False):
    if lock.locked():
        raise err(409, "Another job is running - wait or cancel it.")
    async with lock:
        job.update(running=True, cancel=False, started=int(time.time()), kind=kind)
        try:
            await (run_backup(create) if kind == "backup" else run_media())
        except Exception as exc:  # noqa: BLE001
            text = str(exc) or exc.__class__.__name__
            log.error("%s failed: %s", kind, text)
            history(kind, False, text)
        finally:
            job.update(running=False, step="", cancel=False)
            await publish()


def start(kind, create=False):
    asyncio.create_task(run_job(kind, create))


async def scheduler():
    while True:
        await asyncio.sleep(30)
        try:
            if not configured() or lock.locked():
                continue
            now = datetime.now(tz)
            bt = str(o("backup_time", "")).strip()
            if o("backup_enabled", True) and re.fullmatch(r"\d{1,2}:\d\d", bt):
                h, m = map(int, bt.split(":"))
                if (now.hour, now.minute) >= (h, m) and state.get("last_backup_day") != now.strftime("%Y-%m-%d"):
                    state["last_backup_day"] = now.strftime("%Y-%m-%d")
                    write_state()
                    start("backup", bool(o("create_backup", False)))
                    continue
            hrs = int(o("media_every_hours", 0) or 0)
            if o("media_enabled", False) and hrs > 0 and time.time() - state["last_media"] > hrs * 3600:
                state["last_media"] = int(time.time())  # avoid retry storms after failures
                start("media")
        except Exception:  # noqa: BLE001
            log.exception("scheduler")


# ---------------------------------------------------------------- web
@web.middleware
async def ingress_guard(request, handler):
    if not DEV and request.remote not in INGRESS_PEERS:
        raise err(403, "ingress only")
    return await handler(request)


async def h_index(request):
    return web.Response(text=(STATIC / "index.html").read_text(), content_type="text/html")


def public_options():
    load_options()
    return {k: o(k) for k in ("host", "share", "username", "domain", "smb_version", "backup_enabled", "backup_dir", "backup_keep", "backup_time",
                              "create_backup", "media_enabled", "media_remote_dir", "media_local_dir", "media_every_hours")} | {"password_set": bool(o("password"))}


async def h_state(request):
    return web.json_response({"configured": configured(), "options": public_options(), "job": job, "last_backup": state["last_backup"],
                              "last_media": state["last_media"], "history": state["history"], "media_tracked": len(state["media_index"]),
                              "local_backups": len(list(BACKUP_DIR.glob("*.tar"))) if BACKUP_DIR.exists() else 0})


async def h_test(request):
    load_options()
    write_auth()
    try:
        _, free = await ls("")
        info = {"ok": True, "free": free}
        if o("backup_enabled", True):
            try:
                await ls(clean_rel(o("backup_dir", "HA-Backups")))
                info["backup_dir"] = "exists"
            except QnapError:
                info["backup_dir"] = "will be created"
        if o("media_enabled", False):
            try:
                await ls(clean_rel(o("media_remote_dir", "Multimedia")))
                info["media_dir"] = "exists"
            except QnapError:
                info["media_dir"] = "NOT FOUND"
        return web.json_response(info)
    except QnapError as exc:
        return web.json_response({"ok": False, "error": str(exc)})


async def h_run(request):
    kind = request.match_info["kind"]
    if kind not in ("backup", "media"):
        raise err(404, "unknown job")
    load_options()
    if not configured():
        raise err(400, "QNAP is not configured")
    write_auth()
    body = await request.json() if request.can_read_body else {}
    start(kind, bool(body.get("create")))
    await asyncio.sleep(0.05)
    return web.json_response({"ok": True})


async def h_cancel(request):
    job["cancel"] = True
    if current_proc and current_proc.returncode is None:
        current_proc.kill()
    return web.json_response({"ok": True})


async def h_remote(request):
    load_options()
    write_auth()
    try:
        items, free = await ls(clean_rel(o("backup_dir", "HA-Backups")))
    except QnapError as exc:
        raise err(502, str(exc))
    items = sorted((i for i in items if not i["dir"]), key=lambda i: i["mtime"], reverse=True)
    local = {p.name for p in BACKUP_DIR.glob("*.tar")} if BACKUP_DIR.exists() else set()
    for i in items:
        i["local"] = i["name"] in local
    return web.json_response({"items": items, "free": free})


async def h_fetch(request):
    """Copy a backup from the QNAP into HA's backup folder so it can be restored from the HA UI."""
    name = (await request.json()).get("name", "")
    if BAD_CHARS.search(name) or "/" in name or not name.endswith(".tar"):
        raise err(400, "invalid name")
    load_options()
    write_auth()
    if lock.locked():
        raise err(409, "Another job is running")
    async with lock:
        job.update(running=True, kind="fetch", started=int(time.time()), step=f"Downloading {name}", files_done=0, files_total=1, cancel=False)
        try:
            part = BACKUP_DIR / (name + ".part")
            await smb(f'get "{clean_rel(o("backup_dir", "HA-Backups"))}/{name}" "{part}"')
            part.replace(BACKUP_DIR / name)
            history("fetch", True, f"{name} copied to Home Assistant backups")
        except Exception as exc:  # noqa: BLE001
            history("fetch", False, str(exc))
            raise err(502, str(exc))
        finally:
            job.update(running=False, step="")
    return web.json_response({"ok": True})


async def h_delete_remote(request):
    name = (await request.json()).get("name", "")
    if BAD_CHARS.search(name) or "/" in name or not name.endswith(".tar"):
        raise err(400, "invalid name")
    load_options()
    write_auth()
    try:
        await smb(f'del "{clean_rel(o("backup_dir", "HA-Backups"))}/{name}"')
    except QnapError as exc:
        raise err(502, str(exc))
    history("backup", True, f"{name} deleted from the QNAP by hand")
    return web.json_response({"ok": True})


async def h_reset_media(request):
    state["media_index"] = {}
    write_state()
    return web.json_response({"ok": True})


def build_app():
    app = web.Application(middlewares=[ingress_guard], client_max_size=64 * 1024)
    app.add_routes([web.get("/", h_index), web.static("/static", STATIC), web.get("/api/state", h_state), web.post("/api/test", h_test),
                    web.post("/api/run/{kind}", h_run), web.post("/api/cancel", h_cancel), web.get("/api/remote", h_remote),
                    web.post("/api/fetch", h_fetch), web.post("/api/delete", h_delete_remote), web.post("/api/media/reset", h_reset_media)])
    return app


async def main():
    global session, tz
    load_options()
    logging.basicConfig(level=getattr(logging, str(o("log_level", "info")).upper(), logging.INFO), format="%(asctime)s %(levelname)s %(message)s")
    DATA.mkdir(parents=True, exist_ok=True)
    try:
        state.update(json.loads(STATE_FILE.read_text()))
    except Exception:  # noqa: BLE001
        pass
    write_auth()
    session = ClientSession(timeout=ClientTimeout(total=30))
    runner = web.AppRunner(build_app())
    await runner.setup()
    try:
        await web.TCPSite(runner, "0.0.0.0", INGRESS_PORT).start()
    except OSError as exc:
        log.error("Cannot listen on port %s: %s", INGRESS_PORT, exc)
        raise SystemExit(1)
    try:
        async with session.get(f"{HA}/config", headers=ha_headers()) as r:
            tz = ZoneInfo((await r.json()).get("time_zone", "UTC"))
    except Exception:  # noqa: BLE001
        tz = timezone.utc
    if not configured():
        log.warning("QNAP is not configured yet - open the add-on Configuration tab and fill in host, share, username, password.")
    log.info("HAQnapTeo by %s (%s) - panel via ingress only, no network ports published", CREDIT, CREDIT_URL)
    asyncio.create_task(scheduler())
    await publish()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
