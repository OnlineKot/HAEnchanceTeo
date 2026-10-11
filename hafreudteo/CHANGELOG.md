# Changelog

## 1.3.0
- Behaviour log: note anything unusual (vomiting, poor appetite, limping, hiding, drinking a lot, litter box problem, night yowling, sneezing, other) with an optional note; shown in History; sensor `<name>_behavior` counts the last 7 days.
- Cat in the garden: pick one or more camera entities (binary sensor, event, counter...) in Settings; when one triggers, the add-on logs immediately that a cat was seen by that camera - it never claims it is Freud. Cooldown (default 10 min) avoids duplicates. Sensor `<name>_garden_cat`.
- Smoother panel: taps show their result instantly (reverted if the server refuses), open rows and forms survive refreshes.

## 1.2.0
- Birthday: new option `cat_birthday` (MM-DD, default 12-03). With the age it gives the exact date (Freud: 2010-12-03, 15 years now, 16 on 3 December). The panel shows "birthday in N days" in the last 60 days and a notification arrives on the day. An earlier approximate birthday is replaced automatically.

## 1.1.0
- Freud is 15: new option `cat_age_years` (default 15) sets an approximate birthday on first start (shown as "~15 lat"); for cats of 11+ years the vet check-up default becomes every 6 months and the weight alert 5 % instead of 7 %. Editing the birthday in the panel replaces the approximation.

## 1.0.0
- Initial release: feeding log with double-feed protection, water / litter / flea / deworming / vaccine / vet reminders, weight chart, history, phone reminders with a Done button, Shortcuts / Siri endpoint, HA sensors and event.
