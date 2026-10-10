#!/usr/bin/env python3
"""certbot --manual hook for DuckDNS TXT records (auth|cleanup). Token comes from the environment, never printed.
Stdlib only. By TeodorTeo.com."""
import os
import re
import sys
import time
import urllib.parse
import urllib.request

URL = os.environ.get("HCT_DUCKDNS_URL", "https://www.duckdns.org/update")
WAIT = int(os.environ.get("HCT_PROPAGATION", 40))


def sub_name(domain):
    d = domain.lower().lstrip("*.").rstrip(".")
    if not d.endswith(".duckdns.org"):
        sys.exit("DuckDNS hook: domain must end with .duckdns.org")
    name = d[: -len(".duckdns.org")].split(".")[-1]
    if not re.fullmatch(r"[a-z0-9-]{1,63}", name):
        sys.exit("DuckDNS hook: invalid sub-domain")
    return name


def call(params):
    token = os.environ.get("HCT_DUCKDNS_TOKEN", "")
    if not token:
        sys.exit("DuckDNS hook: token missing")
    q = urllib.parse.urlencode({**params, "token": token, "verbose": "true"})
    try:
        with urllib.request.urlopen(f"{URL}?{q}", timeout=20) as r:
            body = r.read(512).decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 - never echo the URL (it carries the token)
        sys.exit(f"DuckDNS request failed: {exc.__class__.__name__}")
    if not body.startswith("OK"):
        sys.exit("DuckDNS update refused (check token and domain)")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    name = sub_name(os.environ.get("CERTBOT_DOMAIN", ""))
    if mode == "auth":
        val = os.environ.get("CERTBOT_VALIDATION", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{10,100}", val):
            sys.exit("DuckDNS hook: bad validation value")
        call({"domains": name, "txt": val})
        print(f"DuckDNS TXT record set for {name}.duckdns.org, waiting {WAIT}s", flush=True)
        time.sleep(WAIT)
    elif mode == "cleanup":
        call({"domains": name, "txt": "removed", "clear": "true"})
        print("DuckDNS TXT record cleared", flush=True)
    else:
        sys.exit("usage: duckdns_hook.py auth|cleanup")


if __name__ == "__main__":
    main()
