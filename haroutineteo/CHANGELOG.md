# Changelog

## 1.0.3
- Minimalist pass: decorative emoji removed from the interface and notification texts (plain labels, calmer look). Functional symbols (check, star, arrows) stay.

## 1.0.2
- Panel explicitly admin-only (`panel_admin: true`): only Home Assistant administrators can open it, change settings and read logs.

## 1.0.1
- Tokens can be copied again at any time (new "Copy token" button). Tokens created before this update can't be recovered - regenerate them once. Note: the token is now stored in the add-on's private data folder (tokens.json) instead of only as a hash.

## 1.0.0
- First release by TeodorTeo.com: step-based routines (service, scene, script, announce, notify, wait, wait for state, fade, stop-if, per-step conditions),
  triggers (time, entity state), run from the panel / Shortcuts, live step progress on the Dynamic Island, sensors, run history.
