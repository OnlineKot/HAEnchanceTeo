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

### Komu i jak dać Live Activity (admin / użytkownik)
- **Admin daje komuś aktywność:** w formularzu aktywności zaznacz **Dla kogo** (urządzenia/użytkownicy). Każde urządzenie ma w edytorze pole
  **Telefon użytkownika** (`notify.mobile_app_*`) – tam trafia jego Live Activity. Aktywność może mieć też telefony „na sztywno”.
- **Użytkownik sam:** w edytorze urządzenia ustawiasz **uprawnienia**: *brak*, *może włączać/wyłączać przydzielone* albo
  *może tworzyć własne z dozwolonych encji*. Na stronie urządzenia, menu ⋯ → **Live Activities**: przełączniki dla aktywności od admina
  oraz (przy uprawnieniu „tworzyć”) formularz „+ Nowa” z gotowymi szablonami.
- **Bezpieczeństwo własnych aktywności:** tylko encje z kafelków tego urządzenia + lista „dodatkowe encje” od admina, maks. 10 na urządzenie,
  **szablony HA są wyłączone** (tylko `{state}` `{name}` `{attr.x}`), więc użytkownik nie odczyta niczego spoza dozwolonych encji.
  Admin widzi i może edytować/usunąć każdą aktywność (oznaczone jako „własna, utworzona przez użytkownika”).
- Wyłączenie aktywności przez użytkownika kończy ją od razu na jego telefonie (`clear_notification`).

## Wygląd 1:1 jak Home Assistant
Interfejs używa zmiennych motywu Home Assistanta (kolory, tryb jasny/ciemny), kart „tile” z okrągłą ikoną i kolorami
stanów (żółte światła, niebieskie odtwarzacze…), suwaka w stylu `ha-control-slider`, przełączników i okien dialogowych Material 3,
pola „filled”, czcionki Roboto oraz **ikon Material Design Icons** (tych samych co w HA; `mdi:nazwa`). Długie dotknięcie
kafelka otwiera okno „więcej informacji” (atrybuty encji).

## Przypięcie do ekranu
- **iPhone / iPad:** otwórz link urządzenia w **Safari** → *Udostępnij → Do ekranu początkowego → Dodaj*. Ikona ma nazwę urządzenia
  i otwiera się na pełnym ekranie. Token jest w adresie **celowo** – aplikacje z ekranu głównego iOS mają własną, odizolowaną pamięć
  (nie widzą tego, co zapamiętał Safari), więc inaczej nie znałyby tokenu.
- **Android:** Chrome → menu ⋮ → *Zainstaluj aplikację*.
- **Ekran blokady iPhone'a:** *Skróty → nowy skrót → Otwórz URL* (link urządzenia) → widżet Skrótów na ekranie blokady albo przycisk Action.
- Menu ⋯ na urządzeniu: **Dodaj do ekranu głównego** (kroki + kopiowanie adresu). Na iOS pokazuje się też jednorazowa podpowiedź.

## Kto czego używał – logowanie
Każdemu urządzeniu możesz przypisać **Użytkownika** (np. „Kasia”). Każda akcja (przycisk, przełącznik, suwak, zdarzenie) jest zapisywana:
- w **Logbooku** Home Assistanta, np. „Kasia (Tablet kuchnia) toggled "Salon"” – przy encji, której dotyczy akcja,
- w **sensorach** `sensor.haliveteo_<urządzenie>_last_action` i `sensor.haliveteo_last_action` (atrybuty: użytkownik, urządzenie,
  encja, wartość, czas, licznik) – widać je w historii i można na nich budować automatyzacje,
- w zakładce **Użycie** – ile razy każde urządzenie/użytkownik użył każdej encji.
Opcje `logbook` i `sensors` w konfiguracji add-onu wyłączają Logbook lub sensory. Sensory tworzone są przez API stanów HA
(nie mają „unique id”, więc po restarcie HA znikają, dopóki nie pojawi się nowa akcja).

## Adres zewnętrzny (IP) i dostęp spoza domu
Add-on sprawdza **publiczny adres IP** (api.ipify.org → icanhazip.com → ifconfig.me; maks. co 10 min) i pokazuje go obok lokalnego
na karcie **Urządzenia**. Zewnętrzny adres jest też w generowanych linkach („spoza domu”), a zmiana IP jest zapisywana w logu i w sensorze
`sensor.haliveteo_external_ip` (atrybuty: poprzedni adres, czas zmiany, źródło) – możesz na niej zbudować automatyzację (np. aktualizację DDNS).
- Opcja **`check_external_ip`** wyłącza sprawdzanie (add-on nie łączy się wtedy z żadną z tych usług).
- Opcja **`external_host`** – własna nazwa (DDNS, np. `mojdom.duckdns.org`) używana w linkach zamiast wykrytego IP.
- Spoza domu potrzebujesz **przekierowania portu** `8766` na routerze albo **VPN** (Tailscale/WireGuard). Adres to zwykłe HTTP – token
  wysłany przez internet można podsłuchać, więc woli się VPN albo reverse proxy z HTTPS. Nie wystawiaj portu bez klucza API/tokenów.
- Informacja o sieci jest dostępna tylko dla administratora (panel / klucz API), nie dla tokenów.

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
