# Changelog

## 1.1.1
- Fix: the layout editor preview no longer ping-pongs watch/states messages endlessly (could freeze the browser and flood the add-on). Server ignores unchanged watch requests.
- The add-on keeps running (and logs why) when a port is already in use.

## 1.1.0
- Live Activities / Live Updates (Dynamic Island, Lock Screen) via the Companion app: bound to entities, start/end states, progress, countdown, templates, throttling, presets, manual start/end, "Live Activity" tile.
- Home Assistant look: theme variables, tile cards, ha-control-slider style, MDI icons, dialogs, filled fields, switches.

## 1.0.0
- First release by TeodorTeo.com: devices with tokens, customizable live tiles (button, toggle, slider, state),
  live state stream from Home Assistant, live action feed, HA events, device PWA, device REST API, layout editor
  with auto-generation from entities and JSON editor.
