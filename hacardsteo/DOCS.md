# HACardsTeo

Beautiful, dependency-free Lovelace cards (vanilla Web Components, one file, no build step, no external requests) plus an add-on that installs them for you. By [TeodorTeo.com](https://teodorteo.com).

## Installation
1. Start the add-on. With **Install automatically** on (default) it copies `teodorteo-cards.js` to `/config/www/hacardsteo/` and registers `/local/hacardsteo/teodorteo-cards.js?v=<version>` as a Lovelace resource (module). When the add-on is updated the resource URL is updated, which busts the browser cache.
2. Open the **TeoCards** panel: it shows the installed version, whether the resource is registered and has **Install / Reinstall / Remove** buttons, plus a gallery with live previews (fake data) and a **Copy YAML** button per example.
3. Refresh the browser (Ctrl+F5) or the app. The cards appear in the card picker as *Teo Card*, *Teo Media*, ...

* **YAML dashboards**: the resources list cannot be edited by the add-on. The panel shows the exact line; add it yourself:
  ```yaml
  lovelace:
    resources:
      - url: /local/hacardsteo/teodorteo-cards.js?v=1.0.0
        type: module
  ```
* If `/config/www` did not exist before, Home Assistant must be restarted once so that `/local/` is served.
* Resource registration needs the add-on's `homeassistant_api` access (granted automatically); the add-on talks to Home Assistant only briefly during installation and keeps no connection open.

## Common options
All cards support light/dark mode and custom themes (they only use Home Assistant CSS variables). Entities can be coloured with `color:` (`red`, `amber`, `#ff8800`, ...). Actions are the standard ones: `more-info`, `toggle`, `navigate`, `url`, `perform-action` (or `call-service`), `fire-dom-event`, `none`.

## teo-card - any entity
Options: `entity` (required), `name`, `icon`, `color`, `layout` (`tile` default, `compact`, `big`), `graph` (24 h sparkline for numeric sensors, automatic in `big`), `secondary_info` (attribute name or `last-changed`), `animate: false`, `tap_action` (default more-info), `icon_tap_action` (default toggle/run), `hold_action`, `double_tap_action`.

Adapts to: light (brightness, colour temperature, hue, glow in the light's colour), switch, input_boolean, fan, humidifier, cover, climate, lock, vacuum, alarm_control_panel, sensor, binary_sensor, weather, person, device_tracker, button, scene, script, automation, media_player, update, camera, timer, select, number and anything else (generic).

```yaml
type: custom:teo-card
entity: light.living_room
name: Living room
```
```yaml
type: custom:teo-card
entity: climate.living_room
layout: big
```
```yaml
type: custom:teo-card
entity: sensor.living_temperature
graph: true
color: state
tap_action:
  action: navigate
  navigation_path: /lovelace/climate
```

## teo-chips
`entities` is a list of entity ids or objects. Item options: `entity`, `type` (`entity`, `weather`, `alarm`, `person`, `people` = persons at home, `battery` = low-battery count, `lights` = lights on, `label`), `icon`, `name`, `show_name`, `show_state`, `color`, actions. `battery` has `threshold` (default 20) and `show_zero`; `lights` has `hide_if_zero`. Tapping the lights chip turns the lights off. `alignment`: `start|center|end`.

```yaml
type: custom:teo-chips
entities:
  - entity: weather.home
  - entity: alarm_control_panel.home
  - type: people
  - type: battery
    threshold: 20
  - type: lights
  - entity: person.ola
    show_name: true
```

## teo-title
`title` (placeholders `{greeting}` and `{name}`), `greeting: true` (= "{greeting}, {name}"; good morning/afternoon/evening/night, English or Polish), `name` (default: first name of the logged-in user), `subtitle`, `show_date`, `align` (`left|center|right`), `size` (`large|medium|small`).

```yaml
type: custom:teo-title
greeting: true
subtitle: Welcome home
show_date: true
```

## teo-room
Area-aware: with `area` the card uses the entities of that area (entity registry, with the device's area as fallback) - temperature and humidity badges, lights-on count with a one-tap all-off/all-on button, and a row of main entity buttons (tap = toggle or more-info, hold = more-info). Everything can be overridden: `entities`, `buttons`, `temperature_entity`, `humidity_entity`, `name`, `icon`, `color`, `max_buttons`, `navigation_path`, `tap_action`.

```yaml
type: custom:teo-room
area: living_room
```
```yaml
type: custom:teo-room
name: Kitchen
icon: mdi:countertop
temperature_entity: sensor.kitchen_temperature
entities:
  - light.kitchen
  - switch.coffee_machine
```

## teo-media
Cover-art backdrop, title/artist, progress (seek when supported), play/pause/previous/next, volume + mute, source select, speaker-group chips and a **Library** button that opens a media browser inside the card (breadcrumbs, filter box, grid with thumbnails, tap an item to play it, tap a folder to open it). Nothing is fetched until you open the Library.

Options: `entity` (media_player), `name`, `speakers` (list of media_player entities to group with `media_player.join` / `unjoin`), `start_path` (media content id, default `media-source://media_source`; or `{media_content_id, media_content_type}`), `library: false|true` (default: shown when the player supports browsing), `color`, actions.

To browse a QNAP: mount it in Home Assistant (Settings -> System -> Storage -> Add network storage, usage *Media*, e.g. name `qnap`), then:

```yaml
type: custom:teo-media
entity: media_player.living_room
speakers:
  - media_player.kitchen
  - media_player.bedroom
start_path: media-source://media_source/qnap
```
The media player has to support `media_player/browse_media` and playing media-source items (most do: Sonos, Cast, DLNA, Music Assistant, ...).

## teo-stats
Row of big number tiles with a tiny 24 h sparkline. `entities` (ids or `{entity, name, icon, color, decimals, unit, graph}`), `title`, `columns`, `graph: false` to disable all sparklines.

```yaml
type: custom:teo-stats
title: Energy
entities:
  - sensor.house_power
  - sensor.energy_today
  - entity: sensor.living_temperature
    decimals: 0
```

## Performance notes
The bundle is ~90 KB unminified. Cards re-render only when one of their entities changed, run no timers while idle (a 1 s tick only runs for an active timer or a playing media player and stops when the card is removed), fetch history only for sparklines they show (cached 10 min, 24 entries max) and load the media library on demand. The add-on keeps no data in memory and no Home Assistant connection open.

## Grid / layout
Cards implement `getGridOptions` for sections dashboards and `getCardSize` for masonry. They work in a single mobile column.
