# Changelog

## 1.4.1
- Tokens can be copied again at any time (new "Copy token" button). Tokens created before this update can't be recovered - regenerate them once. Note: the token is now stored in the add-on's private data folder (tokens.json) instead of only as a hash.

## 1.4.0
- External (public) IP check, external device links, sensor.haliveteo_external_ip with change detection; options check_external_ip, external_host.

## 1.3.0
- Live Activities can be given to devices/users (audience + per-device phone), users can switch them on/off and (with permission) create their own from allowed entities with safe placeholder templates.

## 1.2.0
- Pin to the home screen: per-device manifest (name + start_url with token, needed because iOS home-screen apps have isolated storage), install dialog/hint, Lock Screen steps.
- Who used what: device "user", every action written to the HA Logbook + sensor.haliveteo_*_last_action sensors, "Usage" tab with per-entity counters; options logbook/sensors.

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
