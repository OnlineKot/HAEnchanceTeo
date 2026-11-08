# HAMcpTeo

Full-featured **Home Assistant MCP server** (87+ tools: entities, automations, scripts, dashboards, backups,
history, calendars, todo, cameras, system) for Claude and other AI clients – packaged by
**[TeodorTeo.com](https://teodorteo.com)**.

Based on [ha-mcp](https://github.com/homeassistant-ai/ha-mcp) by Julien (MIT).

## What is different in this build
- **No telemetry, no analytics, no phone-home.** The PyPI update check is removed, the OpenTelemetry exporters are
  disabled in the image, and the only traffic is to *your* Home Assistant and your MCP client.
- **No public demo server.** The built-in `demo` token that pointed at a third-party server is gone.
- **Built locally.** No external image registry: Home Assistant builds the add-on from the bundled source.
- **TeodorTeo.com branding** in the add-on, the settings panel and the landing page.

See [DOCS.md](DOCS.md) for setup and [PRIVACY.md](PRIVACY.md) for the data policy.
