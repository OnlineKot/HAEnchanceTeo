#!/usr/bin/env python3
"""HACertTeo - obtain and auto-renew a Let's Encrypt certificate for Home Assistant (DNS-01, nothing exposed).
Panel only through Home Assistant ingress - no network ports are published.
By TeodorTeo.com (https://teodorteo.com)."""
import asyncio
import json
import logging
import os
import re
import signal
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from urllib.parse import urlsplit

CREDIT, CREDIT_URL = "TeodorTeo.com", "https://teodorteo.com"
DATA = Path(os.environ.get("HCT_DATA", "/data"))
OPTIONS_FILE = Path(os.environ.get("HCT_OPTIONS", "/data/options.json"))
SSL_DIR = Path(os.environ.get("HCT_SSL", "/ssl"))
CERTBOT = os.environ.get("HCT_CERTBOT", "certbot")
OPENSSL = os.environ.get("HCT_OPENSSL", "openssl")
HOOK_DIR = Path(os.environ.get("HCT_HOOK_DIR", str(Path(__file__).parent)))
STATE_FILE = DATA / "state.json"
LE_DIR = DATA / "letsencrypt"
STATIC = Path(__file__).parent / "static"
INGRESS_PORT = int(os.environ.get("HCT_INGRESS_PORT", 8099))
INGRESS_PEERS = {"172.30.32.2", "127.0.0.1", "::1"}
DEV = bool(os.environ.get("HCT_DEV"))
HA = os.environ.get("HCT_HA_URL", "http://supervisor/core/api")
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
PROPAGATION = int(os.environ.get("HCT_PROPAGATION", 40))
JOB_TIMEOUT = int(os.environ.get("HCT_JOB_TIMEOUT", 1200))
CHECK_EVERY = int(os.environ.get("HCT_CHECK_EVERY", 12 * 3600))
FIRST_CHECK = int(os.environ.get("HCT_FIRST_CHECK", 60))

DOMAIN_RE = re.compile(r"^(\*\.)?([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}$")
FILE_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
LOG_LINES, LOG_LINE_LEN, LOG_BYTES = 300, 300, 64 * 1024
HISTORY = 20

log = logging.getLogger("hacertteo")
OPT = {}
state = {"history": [], "last_check": 0, "last_success": 0, "last_failure": 0}
job = {"running": False, "kind": "", "started": 0, "step": ""}
logbuf = deque(maxlen=LOG_LINES)
logseq = 0
lock = asyncio.Lock()
current_proc = None
cancelled = False


class CertError(Exception):
    pass


class HttpError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


def err(status, message):
    return HttpError(status, message)


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


def history(kind, ok, text):
    state["history"].insert(0, {"ts": int(time.time()), "kind": kind, "ok": ok, "text": text[:300]})
    del state["history"][HISTORY:]
    write_state()


# ---------------------------------------------------------------- config
def clean_domains():
    """Return (domains, errors). Strict validation: these go to certbot (list args, never a shell)."""
    out, errors = [], []
    for d in o("domains", []) or []:
        d2 = str(d).strip().lower().rstrip(".")
        if len(d2) > 253 or not DOMAIN_RE.match(d2):
            errors.append(f"Invalid domain: {str(d)[:60]!r}")
        elif d2 not in out:
            out.append(d2)
    return out, errors


def config_errors():
    domains, errors = clean_domains()
    if not domains and not errors:
        errors.append("No domains configured - add at least one domain in the add-on Configuration tab.")
    if not EMAIL_RE.match(str(o("email"))):
        errors.append("Enter a valid e-mail address (Let's Encrypt sends expiry warnings there).")
    prov = o("provider", "cloudflare")
    if prov == "cloudflare" and not o("cloudflare_api_token"):
        errors.append("Cloudflare provider needs cloudflare_api_token (scope Zone:DNS:Edit).")
    elif prov == "duckdns":
        if not o("duckdns_token"):
            errors.append("DuckDNS provider needs duckdns_token.")
        if any(not d.endswith(".duckdns.org") for d in domains):
            errors.append("With DuckDNS every domain must end with .duckdns.org.")
    elif prov not in ("cloudflare", "duckdns"):
        errors.append("Unknown provider.")
    for k in ("certfile", "keyfile"):
        if not FILE_RE.match(str(o(k, "x"))) or o(k) in (".", ".."):
            errors.append(f"Invalid {k}.")
    return errors


def secrets():
    return [s for s in (o("cloudflare_api_token"), o("duckdns_token"), TOKEN) if s and len(str(s)) >= 4]


def scrub(line):
    for s in secrets():
        line = line.replace(str(s), "***")
    return line


def add_log(line):
    global logseq
    line = scrub(line.rstrip())[:LOG_LINE_LEN]
    logseq += 1
    logbuf.append((logseq, line))
    while sum(len(x[1]) + 8 for x in logbuf) > LOG_BYTES and len(logbuf) > 1:
        logbuf.popleft()


# ---------------------------------------------------------------- certificate info
async def run_capture(*cmd, timeout=15):
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return 1, ""
    return proc.returncode, out.decode("utf-8", "replace")


def parse_cert(text, now=None):
    m = re.search(r"notAfter=(.+)", text)
    if not m:
        return None
    try:
        exp = datetime.strptime(re.sub(r"\s+", " ", m.group(1).strip()), "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    now = now or datetime.now(timezone.utc)
    im = re.search(r"issuer\s*=\s*(.+)", text)
    issuer_raw = im.group(1) if im else ""
    parts = dict(re.findall(r"(?:^|,\s*)(CN|O)\s*=\s*([^,]+)", issuer_raw))
    issuer = ", ".join(x.strip() for x in (parts.get("O"), parts.get("CN")) if x) or issuer_raw.strip()
    domains = sorted(set(re.findall(r"DNS:([^,\s]+)", text)))
    secs = (exp - now).total_seconds()
    return {"expiry": exp.isoformat(), "days_left": int(secs // 86400), "domains": domains, "issuer": issuer,
            "staging": "STAGING" in issuer_raw.upper() or "FAKE" in issuer_raw.upper()}


async def read_cert(path=None):
    path = Path(path or SSL_DIR / o("certfile", "fullchain.pem"))
    if not path.is_file():
        return None
    rc, out = await run_capture(OPENSSL, "x509", "-in", str(path), "-noout", "-enddate", "-issuer", "-ext", "subjectAltName")
    return parse_cert(out) if rc == 0 else None


def decide(info, domains, days_before, staging):
    """Return (renew?, reason)."""
    if not info:
        return True, "no certificate yet"
    if set(domains) != set(info["domains"]):
        return True, "domain list changed"
    if bool(staging) != bool(info["staging"]):
        return True, "staging setting changed"
    if info["days_left"] < days_before:
        return True, f"{info['days_left']} days left (< {days_before})"
    return False, f"{info['days_left']} days left, no renewal needed"


def status_of(info, running=False, failed=False):
    if running:
        return "issuing"
    if not info:
        return "error" if failed else "none"
    if info["days_left"] < 0:
        return "expired"
    if info["days_left"] < int(o("renew_days_before", 30)):
        return "expiring"
    return "valid"


# ---------------------------------------------------------------- HA helpers
def ha_headers():
    return {"Authorization": f"Bearer {TOKEN}"}


async def ha_post(path, body):
    """Tiny HTTP/1.0 POST over asyncio streams (plain http to the Supervisor proxy) - avoids importing a full HTTP client."""
    try:
        u = urlsplit(f"{HA}/{path}")
        payload = json.dumps(body).encode()
        rd, wr = await asyncio.wait_for(asyncio.open_connection(u.hostname, u.port or 80), 10)
        try:
            wr.write(f"POST {u.path} HTTP/1.0\r\nHost: {u.netloc}\r\nAuthorization: Bearer {TOKEN}\r\nContent-Type: application/json\r\n"
                     f"Content-Length: {len(payload)}\r\n\r\n".encode() + payload)
            await wr.drain()
            await asyncio.wait_for(rd.read(2048), 10)
        finally:
            wr.close()
    except Exception as exc:  # noqa: BLE001
        log.debug("HA call failed: %s", exc)


async def publish():
    info = await read_cert()
    last = state["history"][0] if state["history"] else None
    st = status_of(info, job["running"], bool(last and not last["ok"] and last["kind"] != "check"))
    base = {"icon": "mdi:certificate", "attribution": "HACertTeo by TeodorTeo.com"}
    await ha_post("states/sensor.hacertteo_days_left", {"state": info["days_left"] if info else "unknown", "attributes": {
        **base, "friendly_name": "Certificate days left", "unit_of_measurement": "d", "expiry": info["expiry"] if info else None,
        "domains": info["domains"] if info else [], "issuer": info["issuer"] if info else None}})
    await ha_post("states/sensor.hacertteo_status", {"state": st, "attributes": {
        **base, "friendly_name": "Certificate status", "last_success": datetime.fromtimestamp(state["last_success"], timezone.utc).isoformat() if state["last_success"] else None,
        "detail": last["text"] if last else ""}})
    return info, st


async def notify(title, message):
    if o("notify_on_failure", True):
        await ha_post("services/persistent_notification/create", {"title": title, "message": scrub(message), "notification_id": "hacertteo_failure"})


# ---------------------------------------------------------------- certbot
def write_credentials():
    """Tokens travel only in the certbot environment (see run env below); nothing is written to disk."""


def lineage():
    return "hacertteo-staging" if o("staging", False) else "hacertteo"


def build_cmd(domains, dry_run=False, force=False):
    staging = bool(o("staging", False)) or dry_run
    cmd = [CERTBOT, "certonly", "--non-interactive", "--agree-tos", "--no-eff-email", "--email", str(o("email")),
           "--config-dir", str(LE_DIR), "--work-dir", str(DATA / "le-work"), "--logs-dir", str(DATA / "le-logs"),
           "--cert-name", lineage(), "--expand", "--key-type", "rsa" if o("key_type", "ecdsa") == "rsa" else "ecdsa"]
    hook = HOOK_DIR / ("duckdns_hook.py" if o("provider", "cloudflare") == "duckdns" else "cloudflare_hook.py")
    cmd += ["--manual", "--preferred-challenges", "dns", "--manual-auth-hook", f"python3 {hook} auth",
            "--manual-cleanup-hook", f"python3 {hook} cleanup"]
    if staging:
        cmd.append("--staging")
    if dry_run:
        cmd.append("--dry-run")
    if force or dry_run:
        cmd.append("--force-renewal")
    for d in domains:
        cmd += ["-d", d]
    return cmd


def install_files():
    src = LE_DIR / "live" / lineage()
    SSL_DIR.mkdir(parents=True, exist_ok=True)
    for name, out, mode in (("fullchain.pem", o("certfile", "fullchain.pem"), 0o644), ("privkey.pem", o("keyfile", "privkey.pem"), 0o600)):
        data = (src / name).read_bytes()
        tmp = SSL_DIR / (out + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, mode)
        tmp.replace(SSL_DIR / out)


async def stream_certbot(cmd):
    global current_proc
    env = {k: v for k, v in os.environ.items() if k != "SUPERVISOR_TOKEN"}
    env["LC_ALL"] = "C.UTF-8"
    if o("provider") == "duckdns":
        env["HCT_DUCKDNS_TOKEN"] = str(o("duckdns_token"))
    else:
        env["HCT_CF_TOKEN"] = str(o("cloudflare_api_token"))
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                                                env=env, start_new_session=True, limit=64 * 1024)
    current_proc = proc

    async def pump():
        async for raw in proc.stdout:
            add_log(raw.decode("utf-8", "replace"))
    try:
        await asyncio.wait_for(asyncio.gather(pump(), proc.wait()), JOB_TIMEOUT)
    except asyncio.TimeoutError:
        kill_proc()
        await proc.wait()
        raise CertError("certbot timed out")
    finally:
        current_proc = None
    return proc.returncode


def kill_proc():
    p = current_proc
    if p and p.returncode is None:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except Exception:  # noqa: BLE001
            p.kill()


async def run_job(kind):
    """kind: issue (obtain/renew now), test (dry-run against staging), auto (scheduled, only if due)."""
    global cancelled
    if lock.locked():
        raise err(409, "Another job is running - wait or cancel it.")
    async with lock:
        cancelled = False
        job.update(running=True, kind=kind, started=int(time.time()), step="Preparing")
        logbuf.clear()
        ok, text = False, ""
        try:
            load_options()
            problems = config_errors()
            if problems:
                raise CertError(problems[0])
            domains, _ = clean_domains()
            if kind == "auto":
                renew, reason = decide(await read_cert(), domains, int(o("renew_days_before", 30)), o("staging", False))
                add_log(f"Check: {reason}")
                if not renew:
                    state["last_check"] = int(time.time())
                    write_state()
                    ok, text = True, reason
                    return
            DATA.mkdir(parents=True, exist_ok=True)
            write_credentials()
            job["step"] = "Running certbot (DNS-01 challenge)"
            add_log(f"Starting certbot for {', '.join(domains)}" + (" [dry-run, staging]" if kind == "test" else ""))
            rc = await stream_certbot(build_cmd(domains, dry_run=(kind == "test"), force=(kind == "issue")))
            if cancelled:
                raise CertError("Cancelled")
            if rc != 0:
                raise CertError(f"certbot failed (exit {rc}) - see the log")
            if kind == "test":
                ok, text = True, "Dry-run OK - DNS challenge works, nothing was saved"
            else:
                job["step"] = "Installing files"
                install_files()
                state["last_success"] = int(time.time())
                ok, text = True, f"Certificate installed in {SSL_DIR}"
                add_log(text)
                await ha_post("services/persistent_notification/dismiss", {"notification_id": "hacertteo_failure"})
        except Exception as exc:  # noqa: BLE001
            text = scrub(str(getattr(exc, "text", "") or exc) or exc.__class__.__name__)
            add_log("ERROR: " + text)
            log.error("%s failed: %s", kind, text)
            state["last_failure"] = int(time.time())
            await notify("HACertTeo: certificate " + ("test" if kind == "test" else "renewal") + " failed", text + "\nOpen the Certificates panel for the log.")
        finally:
            if not (kind == "auto" and ok and text.endswith("no renewal needed")):
                history(kind, ok, text or "failed")
            state["last_check"] = int(time.time())
            write_state()
            job.update(running=False, step="")
            await publish()


def start(kind):
    asyncio.create_task(run_job(kind))


async def scheduler():
    await asyncio.sleep(FIRST_CHECK)
    last_pub = 0
    while True:
        try:
            if not lock.locked():
                load_options()
                if time.time() - state["last_check"] >= CHECK_EVERY:
                    if config_errors():
                        state["last_check"] = int(time.time())
                    else:
                        start("auto")
                elif time.time() - last_pub > 3600:
                    last_pub = time.time()
                    await publish()
        except Exception:  # noqa: BLE001
            log.exception("scheduler")
        await asyncio.sleep(60)


# ---------------------------------------------------------------- web (minimal asyncio HTTP server: keeps idle RAM low)
MIME = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8", ".svg": "image/svg+xml",
        ".png": "image/png", ".woff2": "font/woff2", ".json": "application/json"}


def jresp(obj, status=200):
    return status, "application/json", json.dumps(obj).encode()


async def h_index(req):
    return 200, "text/html; charset=utf-8", (STATIC / "index.html").read_bytes()


async def h_static(req):
    p = (STATIC / req["path"][len("/static/"):]).resolve()
    if STATIC.resolve() not in p.parents or not p.is_file():
        raise err(404, "not found")
    return 200, MIME.get(p.suffix, "application/octet-stream"), p.read_bytes()


async def h_state(req):
    load_options()
    info = await read_cert()
    last = state["history"][0] if state["history"] else None
    domains, _ = clean_domains()
    renew, reason = decide(info, domains, int(o("renew_days_before", 30)), o("staging", False)) if domains else (False, "")
    return jresp({
        "status": status_of(info, job["running"], bool(last and not last["ok"])), "cert": info, "job": job, "errors": config_errors(),
        "history": state["history"], "last_check": state["last_check"], "last_success": state["last_success"], "next_action": reason, "due": renew,
        "options": {"domains": domains, "email": o("email"), "provider": o("provider", "cloudflare"), "key_type": o("key_type", "ecdsa"),
                    "staging": bool(o("staging", False)), "renew_days_before": o("renew_days_before", 30), "certfile": o("certfile", "fullchain.pem"),
                    "keyfile": o("keyfile", "privkey.pem"), "token_set": bool(o("cloudflare_api_token") if o("provider") == "cloudflare" else o("duckdns_token")),
                    "notify_on_failure": bool(o("notify_on_failure", True))}})


async def h_run(req):
    kind = req["path"].rsplit("/", 1)[-1]
    if kind not in ("issue", "test"):
        raise err(404, "unknown job")
    load_options()
    if lock.locked():
        raise err(409, "Another job is running")
    if config_errors():
        raise err(400, config_errors()[0])
    start(kind)
    await asyncio.sleep(0.05)
    return jresp({"ok": True})


async def h_cancel(req):
    global cancelled
    cancelled = True
    kill_proc()
    return jresp({"ok": True})


async def h_log(req):
    try:
        since = int(req["query"].get("since", 0))
    except ValueError:
        since = 0
    return jresp({"lines": [[n, t] for n, t in logbuf if n > since], "seq": logseq, "running": job["running"]})


ROUTES = {("GET", "/"): h_index, ("GET", "/api/state"): h_state, ("POST", "/api/cancel"): h_cancel, ("GET", "/api/log"): h_log}
REASONS = {200: "OK", 400: "Bad Request", 403: "Forbidden", 404: "Not Found", 405: "Method Not Allowed", 409: "Conflict", 413: "Payload Too Large", 500: "Internal Server Error"}


async def serve(reader, writer):
    status, ctype, body = 500, "application/json", b'{"error":"internal"}'
    try:
        peer = (writer.get_extra_info("peername") or ("",))[0]
        if not DEV and peer not in INGRESS_PEERS:  # ingress guard
            raise err(403, "ingress only")
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
        lines = head.decode("latin-1").split("\r\n")
        method, target, _ = lines[0].split(" ", 2)
        hdr = {k.strip().lower(): v.strip() for k, _, v in (l.partition(":") for l in lines[1:] if ":" in l)}
        if int(hdr.get("content-length", 0) or 0) > 4096:
            raise err(413, "body too large")
        if hdr.get("content-length", "0") != "0":
            await asyncio.wait_for(reader.readexactly(int(hdr["content-length"])), 10)  # bodies are not used; read and drop
        u = urlsplit(target)
        req = {"method": method, "path": u.path, "query": dict(q.partition("=")[::2] for q in u.query.split("&") if q)}
        handler = ROUTES.get((method, u.path))
        if not handler and method == "GET" and u.path.startswith("/static/"):
            handler = h_static
        if not handler and method == "POST" and u.path.startswith("/api/run/"):
            handler = h_run
        if not handler:
            raise err(404, "not found")
        status, ctype, body = await handler(req)
    except HttpError as exc:
        status, ctype, body = exc.status, "application/json", json.dumps({"error": exc.message}).encode()
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, asyncio.TimeoutError, ValueError, ConnectionError):
        status, ctype, body = 400, "application/json", b'{"error":"bad request"}'
    except Exception:  # noqa: BLE001
        log.exception("request failed")
    try:
        writer.write(f"HTTP/1.1 {status} {REASONS.get(status, 'Error')}\r\nContent-Type: {ctype}\r\nContent-Length: {len(body)}\r\n"
                     f"Cache-Control: no-store\r\nConnection: close\r\n\r\n".encode() + body)
        await writer.drain()
    except ConnectionError:
        pass
    finally:
        writer.close()


async def main():
    load_options()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    DATA.mkdir(parents=True, exist_ok=True)
    try:
        state.update(json.loads(STATE_FILE.read_text()))
    except Exception:  # noqa: BLE001
        pass
    try:
        await asyncio.start_server(serve, "0.0.0.0", INGRESS_PORT, limit=16384)
    except OSError as exc:
        log.error("Cannot listen on port %s: %s", INGRESS_PORT, exc)
        raise SystemExit(1)
    for p in config_errors()[:1]:
        log.warning("Not configured yet: %s", p)
    log.info("HACertTeo by %s (%s) - panel via ingress only, no network ports published", CREDIT, CREDIT_URL)
    asyncio.create_task(scheduler())
    await publish()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
