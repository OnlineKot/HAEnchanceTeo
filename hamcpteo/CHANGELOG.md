# Changelog

## 1.2.1
- Lighter image build for Raspberry Pi (no bytecode pre-compile, single install job) after a 1.2.0 build that never finished.

## 1.2.0
- AI access levels per category (alarms, locks, security, covers, climate, lights, switches, media, automations, sensors, other, system): none / read / full, colour-coded page `Access` in the panel, one-click "everything" row. Alarms, locks and security default to read-only.

## 1.1.0
- Public address auto-detect (`public_url` option or Home Assistant External URL); the log prints a ready address for claude.ai.

## 1.0.0
- First TeodorTeo.com release, based on ha-mcp 9.1.1.
- Removed PyPI update check and the public demo token; OpenTelemetry exporters disabled by default.
- Local image build (no external registry), TeodorTeo.com branding.
