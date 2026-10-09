# Changelog

## 1.11.0
- Home Assistant look (theme variables, Roboto, pill buttons, filled fields, switches, tabs).

## 1.10.0
- Tokens for shortcuts (hashed, revocable, per-token speakers/limits/defaults, rate limit) and supervised tokens with a full announcement log.

## 1.9.0
- TTS is pre-rendered (no surprise delay, cached), honest "preparing/playing/queued" status, per-speaker queue, Stop button + /api/stop.

## 1.8.0
- Live auto-refresh of the interface, "new version available" banner + version in footer, one-click set-up of all three launch methods with copy buttons.

## 1.7.0
- One generic launcher script/shortcut that opens the interface full screen (replaces per-sound scripts); new ⚡ Quick view with favorite sounds as tiles, recent messages; ?quick=1 kiosk mode.

## 1.6.0
- New interface; speaker detection (platform, model, announce support), calibration, duplicate detection/hiding, manual remove/restore, favorites for speakers and sounds, library search and duplicate removal.

## 1.5.0
- Run a script or scene before/after an announcement (pickers, API, generated scripts); in-app "App" tab with phone instructions.

## 1.4.0
- Per-speaker profiles: volume memory, resume playback (media + position), before/after delays, power cycle, unmute, quiet hours.

## 1.3.0
- TTS uses the engines configured in Home Assistant: engine, language and voice pickers, preview, save TTS to library.

## 1.2.0
- Standalone interface on port 8765 (API-key protected), installable on iPhone home screen (PWA).

## 1.1.0
- "Create script" button: makes an HA script for iPhone lock screen widget / Shortcuts.

## 1.0.0
- First release by TeodorTeo.com: TTS announcements, browser recording, file upload,
  generated sounds (tone, beep, chime, gong, notify, siren, alarm), one-time or saved,
  sound library, optional volume override + restore, external API.
