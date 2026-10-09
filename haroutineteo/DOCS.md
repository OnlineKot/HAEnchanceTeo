# HARoutineTeo – by [TeodorTeo.com](https://teodorteo.com)

**Rutyny z krokami** – wygodniejsza alternatywa dla skryptów w YAML: układasz kroki w panelu, uruchamiasz je ze Skrótu iPhone'a,
o godzinie albo po zmianie encji, a postęp widzisz **na żywo na Dynamic Island**.

## Kroki
| Krok | Co robi |
|---|---|
| **Wywołaj usługę** | dowolna usługa HA z encją i danymi JSON |
| **Scena / Script** | uruchamia scenę lub skrypt |
| **Powiedz na głośniku** | TTS z HA (tryb *announce*), opcjonalnie z ustawieniem głośności |
| **Powiadomienie** | na telefon(y) |
| **Czekaj** | sekundy / minuty / godziny (z odliczaniem na wyspie) |
| **Czekaj na stan** | czeka, aż encja przyjmie stan (np. drzwi zamknięte), z limitem czasu: kontynuuj albo zatrzymaj rutynę |
| **Płynna zmiana** | płynnie zmienia jasność światła lub głośność (np. „ściemniaj przez 5 minut do zera”) |
| **Zatrzymaj, jeśli…** | przerywa rutynę, gdy warunek jest spełniony (np. ktoś jest w domu) |

Każdy krok może mieć warunek **„wykonaj tylko, jeśli…”** (encja, atrybut, `=`, `!=`, `>`, `<`, `in`), własny opis (widoczny na wyspie)
i przycisk **Wypróbuj krok**. Kroki można przesuwać, kopiować i usuwać.

## Wyzwalacze
- **Godzina** + dni tygodnia.
- **Zmiana stanu encji** (na wskazany stan, z wskazanego stanu, opcjonalnie **trzymany przez N sekund** – krótsze zaniki nie uruchamiają rutyny).
- **Ręcznie** z panelu lub **ze Skrótu** (token) – „Hej Siri, Dobranoc”.

Tryb: ponowne uruchomienie podczas działania jest **ignorowane** albo **restartuje** rutynę.

## Dynamic Island
Podczas działania telefon pokazuje nazwę rutyny, **„Krok 3/7 · Wygaszam salon”**, pasek postępu, a przy czekaniu **odliczanie**. Na końcu „✅ Done” lub błąd, potem znika.
Wymaga iOS 17.2+, Home Assistant Core 2026.7+ i włączonych Live Activities w aplikacji Companion (telefony wybierasz w Ustawieniach lub per rutyna).

## Skróty (token API, port 8768)
Zakładka **Skróty (tokeny)** → token (opcjonalnie ograniczony do wybranych rutyn). W aplikacji Skróty: *Pobierz zawartość URL*,
`POST http://<HA>:8768/api/run`, nagłówki `Authorization: Bearer TOKEN` i `Content-Type: application/json`, treść `{"routine": "Dobranoc"}`.
Dodatkowo `POST /api/stop` i `GET /api/routines`. Limit 20 żądań/min. Port 8768 to zwykłe HTTP – używaj w sieci domowej lub przez VPN.

## HA
Zdarzenie `haroutineteo_finished` (nazwa, status, źródło), sensor `sensor.haroutineteo_running` i `binary_sensor.haroutineteo_<nazwa>` (włączony, gdy rutyna działa).
Zakładka **Aktywność** pokazuje trwające uruchomienia (z przyciskiem Stop) i historię ze szczegółowym logiem kroków.

---
Created by **TeodorTeo.com** · MIT License
