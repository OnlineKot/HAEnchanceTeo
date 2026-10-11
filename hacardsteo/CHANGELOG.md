# Changelog

## 1.0.4
- Media card: the QNAP example / default path is `media-source://media_source/local/qnap_media` (the QNAP mount of HAQnapTeo lives under HA "My media").

## 1.0.3
- Speed: taps show their result instantly (optimistic state for on/off, toggle, open/close, lock/unlock, brightness) and are corrected as soon as Home Assistant reports the real state; sliders now send while dragging (every 150 ms) so the device follows the finger; transitions cut from 250-400 ms to ~100 ms; slider fill no longer lags; climate +/- applies after 450 ms instead of 700 ms.

## 1.0.2
- Design: removed the glow and gradient effects (light glow behind cards, gradient tints, gradient heading, blurred cover backdrop, drop shadows on cover/buttons, pulsing light icon). Cards are flat and use only the HA theme colours; an active card gets a flat 10% tint of its colour.

## 1.0.1
- Panel explicitly admin-only (`panel_admin: true`).

## 1.0.0
- Initial release: six Lovelace cards (teo-card, teo-chips, teo-title, teo-room, teo-media, teo-stats), automatic install into /config/www/hacardsteo and Lovelace resource registration, gallery panel with live previews and YAML examples. Ingress only, no network ports.
