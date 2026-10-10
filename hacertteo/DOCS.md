# HACertTeo – by TeodorTeo.com

Gets and **auto-renews a free Let's Encrypt SSL certificate** for Home Assistant and writes it to `/ssl`.
**Private by design:** no network ports are published and nothing is exposed to the internet. Validation uses the **DNS-01** challenge (a TXT record in your DNS zone), so ports 80/443 never need to be opened. The panel (sidebar “Certificates”) is reachable only through Home Assistant.

## Setup
1. Point a DNS name at Home Assistant (e.g. `ha.example.com` → your HA's LAN or Tailscale IP, or your public IP – it does not matter for the certificate). The name only has to exist in a zone you control.
2. Pick a provider in *Configuration*:
   - **cloudflare** – create an API token (My Profile → API Tokens → *Edit zone DNS* template) with permission **Zone:DNS:Edit** for the zone; paste it into `cloudflare_api_token`. Wildcards (`*.example.com`) work.
   - **duckdns** – use `name.duckdns.org` domains and paste your token into `duckdns_token`. DuckDNS keeps one TXT record per name, so do not request both `name.duckdns.org` and `*.name.duckdns.org`.
3. Set `domains`, `email`, keep `staging: true` first, start the add-on and press **Test (dry-run, staging)**. When it works set `staging: false`, restart and press **Issue / Renew now**.
4. Add to Home Assistant's `configuration.yaml` and restart HA once:
   ```yaml
   http:
     ssl_certificate: /ssl/fullchain.pem
     ssl_key: /ssl/privkey.pem
   ```

## Renewal
The add-on checks twice a day and renews when fewer than `renew_days_before` days (default 30) are left, the domain list changed, or the staging setting changed. Home Assistant reads the files only at start, so restart HA (e.g. a monthly automation) after a renewal. Other add-ons can read the same files from `/ssl`.

## Sensors
`sensor.hacertteo_days_left` (days; attributes `expiry`, `domains`, `issuer`) and `sensor.hacertteo_status` (`valid` / `expiring` / `expired` / `none` / `issuing` / `error`). With `notify_on_failure` a persistent notification appears when issuing fails.

## Notes
- Tokens are stored in the add-on options (managed by Home Assistant), written to private (0600) files / environment of the short-lived certbot process, never logged and never shown in the panel.
- Domains are validated strictly before being passed to certbot; certbot runs only for the duration of a job, so the add-on idles at a few tens of MB.
- Existing files `fullchain.pem` / `privkey.pem` in `/ssl` are overwritten; change `certfile` / `keyfile` to avoid that.
