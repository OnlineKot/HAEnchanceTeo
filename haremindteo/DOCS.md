# HARemindTeo – by [TeodorTeo.com](https://teodorteo.com)

**Przypomnienia i timery** pisane po ludzku, z powiadomieniem, głosem na głośniku i **odliczaniem na Dynamic Island**.

## Jak pisać
Czas względny: „za 15 min”, „za 1h 30m”, „za pół godziny”. Godzina: „o 18:30”, „o 7”, „at 6pm”. Dzień: „jutro”, „pojutrze”,
„w poniedziałek”. Powtarzanie: „codziennie o 7:30”, „w dni robocze o 8:15”, „co tydzień w piątek o 17:00”, „co 2 godziny”.
Reszta zdania to treść. Działa po polsku i angielsku. Podgląd zrozumianego terminu pojawia się już podczas pisania.

## Co się dzieje, gdy nadejdzie czas
- **Powiadomienie** na telefon (czasowo-pilne) z przyciskami **✅ Gotowe** i **⏰ +10 min** (drzemka; długość ustawisz w Ustawieniach).
- **Głos** na wybranych głośnikach (TTS z HA, tryb *announce*), opcjonalnie **skrypt** HA.
- **Zdarzenie** `haremindteo_fired` w HA (do własnych automatyzacji).
- **Dynamic Island / ekran blokady:** po utworzeniu przypomnienia (do 8 h naprzód) telefon pokazuje **odliczanie** do terminu, a w chwili
  odpalenia „czas minął” (potem znika). Wymaga iOS 17.2+, Home Assistant Core 2026.7+ i włączonych Live Activities w aplikacji Companion.
- **Sensory:** `sensor.haremindteo_next` (czas najbliższego) i `sensor.haremindteo_pending` (liczba).

## Ze Skrótów iPhone'a („Hej Siri, przypomnij…”)
Zakładka **Skróty (tokeny)** → utwórz token → skopiuj adres i nagłówki. W Skrótach: *Zapytaj o dane wejściowe* (lub *Dyktuj tekst*) →
*Pobierz zawartość URL*: `POST http://<HA>:8767/api/remind`, nagłówki `Authorization: Bearer TOKEN`, `Content-Type: application/json`,
treść `{"text": "<wynik poprzedniej akcji>"}`. Token widzi i może anulować **tylko własne** przypomnienia (`GET/DELETE /api/reminders`),
ma limit 20 żądań/min i domyślne telefony/głośniki zapisane przy tokenie.

Uwaga: port 8767 to zwykłe HTTP – używaj w sieci domowej albo przez VPN/HTTPS.

---
Created by **TeodorTeo.com** · MIT License
