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

## 🏝️ Live Activities – Dynamic Island i ekran blokady
HALiveTeo steruje **Live Activities** (iPhone: Dynamic Island + ekran blokady) i **Live Updates** (Android) przez aplikację
Home Assistant Companion – sam wysyła `notify.mobile_app_*` z `live_update: true`, więc **nie musisz pisać automatyzacji**.
Strona internetowa nie może sama utworzyć Live Activity (to wymaga natywnej aplikacji), dlatego korzystamy z Companion.

**Wymagania:** iOS 17.2+ (iPhone; iPad nie obsługuje), Home Assistant Core **2026.7+**, aplikacja Companion z włączonymi
Live Activities (*Ustawienia → Live Activities*). Telefon musi mieć stabilne połączenie z HA (wymiana tokenów).

Zakładka **Live Activities** → **+ Nowa aktywność**:
- wybierasz **telefon(y)** i **encję**, która steruje aktywnością,
- **start** gdy stan ∈ lista (puste = każdy poza końcowymi), **koniec** gdy stan ∈ lista (wysyła `clear_notification`),
- **tytuł** (stały), **treść** (tekst albo szablon HA, np. `{{ states('sensor.pralka') }}`), tekst na wyspie (`critical_text`),
- **pasek postępu** z wartości encji (min–max → %), **odliczanie** (`chronometer`) z atrybutu z czasem końca, np. `finishes_at` timera,
- ikona MDI i kolor, `background_color`, `text_color`, otwarcie strony po dotknięciu (`url`), `relevance_score` (kolejność na wyspie).
- Gotowe szablony: status urządzenia, pasek postępu %, odliczanie `timer.*`, odtwarzacz (tytuł).
- **Podgląd ładunku** pokazuje dokładnie, co zostanie wysłane; **Start/Zakończ** uruchamiają ręcznie.
- Kafelek-przycisk typu **Live Activity** na urządzeniu włącza/kończy aktywność dotknięciem.

Zgodnie z zaleceniami Apple/Companion HALiveTeo **ogranicza częstotliwość**: aktualizacje są ciche (`silent`), zwijane do jednej
najnowszej wartości w minimalnym odstępie (domyślnie 30 s) i wysyłane tylko gdy treść/postęp się zmienią. Aktywność
jest odnawiana przed limitem ~8 h. Nie testuj w kółko start/stop – iOS ma budżet na uruchamianie nowych aktywności.

## Wygląd 1:1 jak Home Assistant
Interfejs używa zmiennych motywu Home Assistanta (kolory, tryb jasny/ciemny), kart „tile” z okrągłą ikoną i kolorami
stanów (żółte światła, niebieskie odtwarzacze…), suwaka w stylu `ha-control-slider`, przełączników i okien dialogowych Material 3,
pola „filled”, czcionki Roboto oraz **ikon Material Design Icons** (tych samych co w HA; `mdi:nazwa`). Długie dotknięcie
kafelka otwiera okno „więcej informacji” (atrybuty encji).

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
