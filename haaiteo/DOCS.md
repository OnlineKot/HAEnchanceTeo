# HAAITeo – by TeodorTeo.com

An AI assistant panel inside Home Assistant. Pick **Claude (Anthropic)** or **Gemini (Google)**; the AI can look at your home, control devices and propose changes to automations, scripts and scenes.
**Private by design:** no network ports are published; the panel is reachable only through Home Assistant (sidebar “AI”). The add-on only connects *outward* to the AI provider you chose.

## Setup
1. Get an API key: Anthropic (console.anthropic.com) and/or Google AI Studio (aistudio.google.com).
2. Add-on → *Configuration*: set `provider`, the matching `*_api_key` (and optionally the model). Start, open the panel.
3. If both keys are set you can switch provider with the chip at the top of the chat.

## Modes
- `read_only` – the AI can only look. Write tools are not even offered to the model.
- `confirm_changes` (default) – device control and config edits are staged as cards; nothing happens until you press **Approve**.
- `auto` – service calls on allowed domains run immediately. Automation/script/scene edits **always** need approval.

## Safety
- `blocked_domains` / `blocked_services` are enforced **in the add-on**, regardless of what the model says (also inside proposed automations). `homeassistant.*` services must name explicit entities.
- Config changes are never applied by the AI. Each shows a diff; on Approve the previous config is saved to `/data/backups/<kind>_<id>_<timestamp>.json` and the change is written through Home Assistant's config API, followed by a reload. **Undo** restores it.
- Entity ids and services are validated before anything is staged or executed.
- Tool results are treated as untrusted data (prompt-injection guard in the system prompt, output size caps, max 40 search results).
- Every tool call, approval and result is written to an audit log (Log tab, rotated at ~1 MB). API keys are never logged and never sent to the browser. Note: a script/automation you approve can itself call anything, so review diffs.
- Rate limit 30 messages/minute, 32 KB request bodies, per-request timeouts.

## What is sent to the provider
Your messages and the tool results (entity states/attributes, history, config YAML with secret-like values hidden). Nothing else. Token counters (in/out) come from the API responses; no cost is estimated.

## Low resource use
No SDKs, no background polling, nothing cached beyond a short service-name list; only ~20 recent steps are sent to the model; the last 20 conversations are stored in `/data`.

## Config reference
`provider`, `anthropic_api_key`, `anthropic_model`, `gemini_api_key`, `gemini_model`, `mode`, `blocked_domains`, `blocked_services`, `max_tool_rounds` (1-30), `language` (auto or a code), `log_level`.
