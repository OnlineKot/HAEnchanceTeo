# Changelog

## 1.1.1
- Tokens can be copied again at any time (new "Copy token" button). Tokens created before this update can't be recovered - regenerate them once. Note: the token is now stored in the add-on's private data folder (tokens.json) instead of only as a hash.

## 1.1.0
- Lock screen: optional token-protected endpoint (`shortcut_enabled`, port 8770) for iPhone Shortcuts / Siri / Action Button / lock-screen widget, answers short enough to be read aloud; never more than confirm_changes; approvals arrive as phone notifications with Approve / Reject buttons (`notify_service`), handled through a short-lived WebSocket. Tokens are hashed, rate-limited, revocable in the panel.

## 1.0.0
- Initial release: AI panel with Claude or Gemini, tools to read/control Home Assistant, staged config changes with diff, approval, backup and undo, audit log, ingress-only (no published ports).
