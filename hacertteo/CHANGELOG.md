# Changelog

## 1.0.2
- Fix: the add-on could not be built/started because the Alpine package `py3-certbot-dns-cloudflare` does not exist in Alpine 3.19. Cloudflare DNS-01 now uses a built-in hook (stdlib only, like DuckDNS) with plain `certbot`. Cloudflare token needs Zone:DNS:Edit and Zone:Zone:Read. The token is no longer written to disk at all.

## 1.0.1
- Panel explicitly admin-only (`panel_admin: true`): only Home Assistant administrators can open it, change settings and read logs.

## 1.0.0
- Initial release: free Let's Encrypt certificate for Home Assistant via DNS-01 (Cloudflare or DuckDNS), automatic renewal, files written to /ssl, sensors, failure notification, ingress-only panel (no published ports).
