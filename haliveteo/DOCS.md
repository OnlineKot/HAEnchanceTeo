# HALiveTeo – by [TeodorTeo.com](https://teodorteo.com)

Akcje **na żywo** z różnych urządzeń do Home Assistanta – w pełni konfigurowalne.
Panel **HALiveTeo** (menu boczne) służy do tworzenia urządzeń i układania ich kafelków.

## Jak to działa
- **Urządzenie** = telefon, tablet, panel ścienny, skrót, ESP… Każde ma własny **token** i własny **układ kafelków**.
- **Kafelki** (na żywo, przez WebSocket):
  - **Przycisk** – wywołuje usługę HA, skrypt, scenę albo wysyła zdarzenie.
  - **Przełącznik** – przełącza encję i pokazuje jej stan na żywo.
  - **Suwak** – jasność światła, głośność odtwarzacza, `input_number` / `number`.
  - **Stan** – dowolna encja lub atrybut (temperatura, drzwi…).
  - Własna nazwa, ikona (emoji), kolor, szerokość (1×/2×), opcjonalne potwierdzenie.
- **Feed na żywo** – wszystkie akcje ze wszystkich urządzeń w czasie rzeczywistym (panel + opcjonalnie na urządzeniach).
- **Zdarzenia w HA** – każda akcja wysyła `haliveteo_action`, a zdarzenia z urządzeń `haliveteo_event`
  (prefiks zmienisz w konfiguracji) – możesz na nich budować automatyzacje.

## Szybki start
1. Panel HALiveTeo → **+ Nowe urządzenie** → skopiuj **link** (token pokazuje się tylko raz).
2. Otwórz link na telefonie/tablecie → Safari: *Udostępnij → Do ekranu początkowego* (działa jak aplikacja, pełny ekran).
   Menu ⋯: „Nie wygaszaj ekranu” i „Pełny ekran” (idealne na panel ścienny).
3. **Edytuj** urządzenie: dodaj kafelki ręcznie, **Auto z encji** (zaznacz światła, sceny, skrypty…) albo edytuj **JSON**.
   Podgląd po prawej pokazuje stany na żywo. Zmiany po **Zapisz** pojawiają się na urządzeniu natychmiast.

## Bezpieczeństwo
- Urządzenie może wywołać **tylko akcje zdefiniowane w jego układzie** – nie ma dostępu do reszty Home Assistanta.
- Tokeny są przechowywane jako skróty (hash); można je wygenerować na nowo lub wyłączyć urządzenie.
- Limit 25 akcji / 10 s na urządzenie. Panel administracyjny jest dostępny tylko przez Home Assistant (ingress).
- Port urządzeń `8766` jest nieszyfrowany (HTTP) – używaj w sieci domowej albo za HTTPS (Nabu Casa / reverse proxy).

## API dla urządzeń bez ekranu (Skróty iOS, ESP, skrypty)
```
POST http://<HA>:8766/api/device/action   Authorization: Bearer TOKEN   {"tile": "ID_KAFELKA"}
POST http://<HA>:8766/api/device/event    Authorization: Bearer TOKEN   {"event": "dzwonek", "data": {...}}
GET  http://<HA>:8766/api/device/layout   Authorization: Bearer TOKEN
```
(`ID_KAFELKA` zobaczysz w JSON układu.)

## Automatyzacja
```yaml
trigger:
  - platform: event
    event_type: haliveteo_action
    event_data: { device: "Tablet w kuchni", label: "Dzwonek" }
action:
  - service: notify.notify
    data: { message: "Ktoś nacisnął dzwonek" }
```

---
Created by **TeodorTeo.com** · MIT License
