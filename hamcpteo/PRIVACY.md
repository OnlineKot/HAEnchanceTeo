# Privacy – HAMcpTeo (TeodorTeo.com)

This build sends **nothing** to TeodorTeo.com or to any analytics service.

- No usage statistics, no telemetry, no crash reporting, no tracking pixels or scripts.
- No automatic update check against PyPI or any other server (`HA_MCP_DISABLE_UPDATE_CHECK` is on by default; the
  PyPI lookup is removed from the code). Update the add-on from the Home Assistant store.
- OpenTelemetry export is switched off in the image (`OTEL_SDK_DISABLED=true`).
- The public demo server shortcut (`demo` token) was removed.

## What it talks to
- **Your Home Assistant** (Supervisor API / WebSocket) with the credentials of the add-on.
- **Your MCP client** (for example Claude) that you connect to the server URL.
- Only when *you* ask a tool for it: GitHub (add-on / HACS release notes, optional bug-report issue text that is shown to
  you first and is never sent automatically).

Your Home Assistant data is passed to the AI client you connect. Its own privacy policy applies to that part.

Upstream project: https://github.com/homeassistant-ai/ha-mcp (MIT, © Julien).
