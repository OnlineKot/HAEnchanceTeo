# Changelog

## 1.1.0
- Mount the whole QNAP share as a read-only HA media source (Supervisor CIFS mount `qnap_media`) from the Media tab - stream without copying. Role raised to `manager` for the Supervisor mounts API.

## 1.0.0
- Initial release: backups to QNAP over SMB with retention and schedule, media download, remote backup list/fetch/delete, sensors, ingress-only panel (no published ports).
