# HAMcpTeo – by TeodorTeo.com

Lets **Claude** (claude.ai and the iPhone app, through a *custom connector*) read and control **only the entities you pick**, over an MCP server on **your own DDNS name** via HTTPS. Sign-in uses your **Home Assistant account and its 2FA**; the panel (Home Assistant sidebar → *Claude MCP*, admins only) manages what Claude may do.

## How it is protected
- **Nothing is exposed by default.** Panel → *Access*: per entity *None / Read / Control*. Alarm panels are read-only. Only a short allow-list of safe services works (turn on/off, set temperature, cover position, media controls, scenes, ...). No area/device targets, no config editing, no templates, no shell.
- **Sign-in = your HA password + HA two-factor code.** The add-on checks them against Home Assistant's own login (`/auth/login_flow`), so the account must have 2FA (TOTP) enabled (HA profile page). Accounts without 2FA are refused (`require_mfa`). Only usernames in `allowed_users` can sign in. A consent screen shows what Claude will get.
- **OAuth 2.1 with PKCE (S256)**, dynamic client registration limited to Claude's callback addresses (`allowed_redirects`), single-use authorization codes, access tokens valid 1 hour, rotating refresh tokens (30 days) with replay detection (a replayed token kills the session). Tokens are stored hashed; sessions can be revoked one by one or all at once, and a kill switch switches everything off.
- **Risky actions need your phone:** unlock, garage / gate / door covers and scripts wait for **Approve / Reject** in the Companion app (`notify_service`, 60 s). Without a notify service they are refused.
- Throttling of sign-ins (5 failures / 15 min per address, 30 / hour overall), rate limit on MCP calls, optional IP allow-list (`allowed_ips`) for the MCP endpoint, full **audit log** (panel → *Log*).

## Set-up
1. **DDNS + HTTPS:** point a DDNS name (DuckDNS, No-IP, ...) at your home IP, issue a certificate for it (the **HACertTeo** add-on writes it to `/ssl`) and **forward one router port to this host's port `8443`**. Put the address in `public_url`, e.g. `https://freud.duckdns.org:8443`.
   Behind your own reverse proxy (Nginx Proxy Manager, ...) set `tls: off` and proxy to port 8443; `public_url` stays the https address.
2. **Home Assistant:** profile page → enable **multi-factor authentication** (TOTP). Put your login name in `allowed_users`. Set `notify_service` (e.g. `mobile_app_iphone`).
3. **Panel → Access:** choose entities (or *Add from Assist* as a start: it adds what is exposed to Assist as read-only).
4. **Claude:** claude.ai → Settings → Connectors → *Add custom connector* → name it, paste `https://<your-name>:8443/mcp`. Press *Connect*: a sign-in page of your own server opens – username, password, 2FA code, *Allow*. The connector then appears in the iPhone app after the account syncs.

## Things to know (please read)
- You are opening a port to the internet. Keep Home Assistant and this add-on updated, use a strong password, and keep 2FA on. The public endpoint serves only OAuth and `/mcp`; the HA UI is not exposed by this add-on.
- Everything Claude reads (states you exposed) is sent to Anthropic when you ask something. Expose what you are comfortable with.
- Home Assistant's own login protection (IP bans) sees the add-on's address, so this add-on throttles failures itself first.
- Revoking: panel → *Sessions*, or change/remove `allowed_users` (refresh then stops working).

## Troubleshooting
- Warnings are listed at the top of the *Status* tab (missing `public_url`, no certificate, empty `allowed_users`, 2FA off, no phone).
- "Home Assistant is not reachable": set `ha_url` (use `https://homeassistant:8123` if your HA serves HTTPS).
- Claude cannot connect: check that `https://<name>:<port>/.well-known/oauth-protected-resource` opens from outside your network.
