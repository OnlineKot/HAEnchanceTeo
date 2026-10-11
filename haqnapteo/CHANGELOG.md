# Changelog

## 1.2.1
- Fix: the media source is shown at `media-source://media_source/local/qnap_media` (HA Media → My media → qnap_media) - the panel/docs showed a wrong path. Mounting now waits for the Supervisor result and reports a failed mount (with hints) instead of claiming success.

## 1.2.0
- Connect wizard in the panel: scan the network for the QNAP (SMB on the HA host's /24, QNAP detection), enter user/password, list the shares, pick one, browse folders for backups and media, then save and mount as an HA media source in one click. Saved details live in the add-on's private data (0600) and take precedence over Configuration.

## 1.1.1
- Panel explicitly admin-only (`panel_admin: true`): only Home Assistant administrators can open it, change settings and read logs.

## 1.1.0
- Mount the whole QNAP share as a read-only HA media source (Supervisor CIFS mount `qnap_media`) from the Media tab - stream without copying. Role raised to `manager` for the Supervisor mounts API.

## 1.0.0
- Initial release: backups to QNAP over SMB with retention and schedule, media download, remote backup list/fetch/delete, sensors, ingress-only panel (no published ports).
