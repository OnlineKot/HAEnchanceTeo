# HAQnapTeo – by TeodorTeo.com

Back up Home Assistant to your **QNAP** and download media from it. **Private by design:** the add-on publishes **no network ports**.
The panel is reachable only through Home Assistant (sidebar “QNAP”); the add-on only connects *outward* to the QNAP over SMB.

## Setup
1. On the QNAP create a **dedicated user** with access to **one share** only (e.g. share `Backup`, user `ha`). Enable SMB (Control Panel → Network & File Services → Win/Mac/NFS).
2. Add-on → *Configuration*: `host`, `share`, `username`, `password`. Save, start, open the panel and press **Test connection**.

## Backups
- Uploads Home Assistant backups (`*.tar`) to `backup_dir` on the share, skipping ones already there.
- `backup_time` (HH:MM) = daily upload; empty = manual only. `create_backup` asks HA for a fresh full backup before each scheduled upload.
- `backup_keep` = how many backups stay on the QNAP; older ones are deleted after a successful upload.
- Panel → *Backups on QNAP*: list, **Fetch to HA** (copies it into HA's backup folder so you can restore it from Settings → System → Backups), delete.

## Media
- `media_enabled` + `media_remote_dir`: new/changed files are downloaded into `/media/<media_local_dir>` (visible in HA Media, usable by HAnnounce etc.).
- One-way and non-destructive: nothing is deleted locally or on the QNAP. `media_every_hours` = 0 → manual only.

## Sensors
`sensor.haqnapteo_backup` and `sensor.haqnapteo_media` (`ok` / `error` / `unknown`, with `last_success`) – use them in automations to be told when a backup fails.

## Notes
- Password is stored in the add-on options (managed by Home Assistant) and passed to `smbclient` through a private auth file – never on the command line, never shown in the panel.
- Use SMB 3 unless your QNAP is very old.

## QNAP as a media source (streaming)
Panel → *Media* → **Mount QNAP as media source**. The share appears in HA *Media* (`media-source://media_source/qnap_media`), works with any player card, TeoCards `teo-media` and HAnnounce.
This uses the Supervisor mounts API, so the add-on has the `manager` role. The mount is read-only. Remove it with the same panel at any time.
