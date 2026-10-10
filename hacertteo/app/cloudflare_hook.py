#!/usr/bin/env python3
"""certbot --manual hook for Cloudflare DNS TXT records (auth|cleanup). Token comes from the environment, never printed.
Stdlib only (no certbot plugin needed). By TeodorTeo.com."""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = os.environ.get("HCT_CF_URL", "https://api.cloudflare.com/client/v4")
WAIT = int(os.environ.get("HCT_PROPAGATION", 40))
DOMAIN_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def call(method, path, body=None):
    token = os.environ.get("HCT_CF_TOKEN", "")
    if not token:
        sys.exit("Cloudflare hook: token missing")
    req = urllib.request.Request(f"{API}{path}", method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read(2 * 1024 * 1024).decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:   # never echo the request (it carries the token)
        sys.exit(f"Cloudflare API error {exc.code} - check the token (needs Zone:DNS:Edit and Zone:Zone:Read) and the domain")
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"Cloudflare request failed: {exc.__class__.__name__}")
    if not data.get("success"):
        sys.exit("Cloudflare refused the request: " + "; ".join(str(e.get("message", ""))[:80] for e in data.get("errors", [])[:2]))
    return data.get("result")


def zone_id(domain):
    parts = domain.split(".")
    for i in range(len(parts) - 1):
        cand = ".".join(parts[i:])
        res = call("GET", "/zones?" + urllib.parse.urlencode({"name": cand, "status": "active"}))
        if res:
            return res[0]["id"]
    sys.exit("Cloudflare hook: no zone for this domain in the account of the token")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    domain = os.environ.get("CERTBOT_DOMAIN", "").lower().lstrip("*.").rstrip(".")
    val = os.environ.get("CERTBOT_VALIDATION", "")
    if not DOMAIN_RE.match(domain) or not re.fullmatch(r"[A-Za-z0-9_-]{10,100}", val):
        sys.exit("Cloudflare hook: bad domain or validation value")
    name = f"_acme-challenge.{domain}"
    zid = zone_id(domain)
    if mode == "auth":
        call("POST", f"/zones/{zid}/dns_records", {"type": "TXT", "name": name, "content": val, "ttl": 60})
        print(f"Cloudflare TXT record set for {name}, waiting {WAIT}s", flush=True)
        time.sleep(WAIT)
    elif mode == "cleanup":
        recs = call("GET", f"/zones/{zid}/dns_records?" + urllib.parse.urlencode({"type": "TXT", "name": name})) or []
        for r in recs:
            if str(r.get("content", "")).strip('"') == val:
                call("DELETE", f"/zones/{zid}/dns_records/{r['id']}")
        print("Cloudflare TXT record removed", flush=True)
    else:
        sys.exit("usage: cloudflare_hook.py auth|cleanup")


if __name__ == "__main__":
    main()
