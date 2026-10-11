# HAFreudTeo – by TeodorTeo.com

A small, calm companion for a cat (made for Freud). Open **Freud** in the sidebar.

## What it does
- **Feeding** with a log of who fed and when – tapping *Fed* twice within 20 minutes asks first, so the cat is not fed twice by two people. Meal times are planned; if nobody fed after a meal time (+ grace) you get a reminder.
- **Water, litter box, full litter change, flea/tick, deworming, vaccination, vet visit** – each task has an interval in days and optional reminders. *Done* resets the timer (use “…” to log a past time).
- **Weight** with a simple chart and a flag when it changes by 7 % or more compared with the last weeks.
- **History** of everything, with delete.
- Works for the whole household: the panel is open to every Home Assistant user (not only admins). Set *Who is logging on this device* so entries carry a name.

## Behaviour log
*Behaviour → Add* on the Today tab: pick a kind (vomiting, poor appetite, limping, hiding, drinking a lot, litter box problem, night yowling, sneezing, other), add a note, save. Entries appear in History and `sensor.<name>_behavior` counts the last 7 days – handy to show the vet.

## Cat in the garden
Settings → *Cat in the garden*: choose the entity of your camera (animal / cat / motion detection – a binary sensor, an event entity, a counter...). Whenever it triggers, the add-on immediately logs "a cat was seen" with the camera's name. It does **not** say it is Freud – the camera only knows it was a cat. A cooldown (default 10 min) avoids repeated entries. `sensor.<name>_garden_cat` holds the last time and how many times today.

## Reminders on the phone
Set `notify_services` (e.g. `mobile_app_iphone`) in the add-on Configuration. Reminders arrive in the Companion app with a **Done** button (also on the lock screen); pressing it logs the task and clears the notification on the other phones. Quiet hours (default 22:00–07:00) and the repeat interval are in Settings.

## Shortcuts / Siri
Turn on `api_enabled` (opens port 8771, token required), create a token in Settings → *Shortcuts and Siri*. Shortcut: *Get Contents of URL* → `http://<HA-IP>:8771/api/log`, POST, JSON `{"task":"feed"}`, header `Authorization: Bearer <token>` → *Get Dictionary Value* `reply` → *Speak Text*. `GET /api/status` returns a short sentence about the cat. Away from home use Nabu Casa or a VPN; do not port-forward.
Tasks: `feed`, `water`, `litter`, `litter_full`, `flea`, `deworm`, `vaccine`, `vet`, `weight` (with `"value": 4.6`).

## Home Assistant entities
`sensor.<name>_last_fed`, `sensor.<name>_water`, `_litter`, `_litter_full`, `_flea`, `_deworm`, `_vaccine`, `_vet` (timestamps with `due_at`), `sensor.<name>_weight`, `binary_sensor.<name>_needs_attention`, and the event `hafreudteo_logged` (`task`, `who`). Use them in automations and dashboards (e.g. light the kitchen blue when the cat has not been fed).

## Senior cat
Freud is 15, so `cat_age_years` defaults to 15: the add-on sets an approximate birthday on first start (replace it with the real one in Settings). From 11 years it uses gentler defaults – a vet check-up every 6 months and a weight alert at 5 %, because unexplained weight loss or a change in drinking is worth a call to the vet in older cats. This is a reminder tool, not medical advice.

## Photo
The default photo is Freud. *Change photo* in Settings uploads another one (cropped to a square on the phone, stored privately in the add-on).

## Privacy
Panel only through Home Assistant. Nothing leaves your network. Tokens are stored in the add-on's private folder.
