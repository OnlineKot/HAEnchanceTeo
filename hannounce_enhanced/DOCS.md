# HAnnounce Enhanced – by [TeodorTeo.com](https://teodorteo.com)

Panel **HAnnounce** pojawia się w bocznym menu Home Assistanta (ingress).

## Co potrafi
- **Mów (TTS)** – używa silników TTS **już dodanych w Home Assistancie** (Piper, Google, Nabu Casa, …): wybierasz silnik, język i głos (listy pobierane z HA), ogłaszasz w trybie *announce*, robisz podgląd albo zapisujesz wygenerowaną wypowiedź w bibliotece.
- **Nagraj** – własne nagranie z mikrofonu przeglądarki (wymaga HTTPS) lub z nagrywarki telefonu.
- **Wgraj** – dowolny plik audio (mp3, wav, ogg, m4a, webm…), konwertowany do mp3.
- **Generuj** – ton, piski, dzwonek „ding-dong”, gong, powiadomienie, syrena, alarm (częstotliwość, czas, powtórzenia).
- **Jednorazowo** – dźwięk jest odtworzony i automatycznie usuwany, albo **zapisz w bibliotece** i używaj wielokrotnie.
- Opcjonalna **zmiana głośności** na czas ogłoszenia (potem przywracana).

## Głośniki: wykrywanie, kalibracja, duplikaty, ulubione
Zakładka **Głośniki** skanuje wszystkie odtwarzacze z HA i pokazuje: integrację (np. sonos, cast), producenta/model,
stan, czy obsługują `announce`, czy są niedostępne.
- **★ Ulubione** – ulubione głośniki są pierwsze na liście, przycisk „★ Ulubione” zaznacza je jednym kliknięciem.
  Ulubione mają też dźwięki w Bibliotece (są na górze).
- **Kalibruj** – odtwarza cicho krótki dźwięk testowy na głośniku, mierzy opóźnienie startu i „zawyżony” czas
  odtwarzania, wykrywa obsługę `announce` i na tej podstawie sam ustawia profil (tryb wznawiania, opóźnienie po,
  ewentualnie włączanie/wyłączanie zasilania). Wynik możesz poprawić w *Ustawienia* głośnika.
- **Duplikaty głośników** – ten sam fizyczny głośnik widoczny jako kilka encji (to samo urządzenie, ta sama nazwa albo
  `_2`). „Ukryj duplikaty” zostawia najlepszą encję (dostępną, z `announce`).
- **Usuń / Przywróć** – ręczne ukrycie głośnika na listach (nie usuwa encji z Home Assistanta; „Pokaż ukryte” przywraca).
- **Duplikaty w Bibliotece** – „Usuń duplikaty” kasuje identyczne dźwięki, zostawiając ulubiony lub najstarszy.

## Skrypt lub scena przed / po ogłoszeniu
Nad zakładkami są dwie listy: **Uruchom przed** i **Uruchom po** – wybierasz skrypt lub scenę z Home Assistanta
(np. przyciemnij światło przed, przywróć po). W API: `before_action`, `after_action` (np. `scene.salon`, `script.xyz`).

## Wysyłanie z aplikacji (iPhone / Android)
Zakładka **📱 Aplikacja** zawiera instrukcje: skrót otwierający interfejs, osobna aplikacja, Siri / Skróty z własnym tekstem (gotowy JSON i adres Twojego add-onu).

## Pamięć i ustawienia każdego urządzenia
Zakładka **Urządzenia**: profil domyślny + osobne ustawienia dla każdego głośnika (przycisk „Kopiuj do wszystkich”).
- **Głośność ogłoszenia** i **przywrócenie głośności** po ogłoszeniu.
- **Po ogłoszeniu**: *Zostaw odtwarzaczowi* (flaga `announce`, np. Sonos/Cast same wznawiają) /
  *Przywróć to, co grało* (add-on zapamiętuje utwór i pozycję, po ogłoszeniu włącza go z powrotem i przewija) / *Nic nie rób*.
- **Czekaj po zakończeniu** (np. 2 s) zanim wróci poprzedni stan; **czekaj przed odtworzeniem** dla głośników, które muszą się „obudzić”.
- **Włącz jeśli wyłączony, potem wyłącz**; **wyłącz wyciszenie** na czas ogłoszenia (potem wraca).
- **Godziny ciszy** (czas lokalny HA): w tym czasie głośnik jest pomijany albo gra ciszej.
Profile działają dla panelu, API i automatyzacji.

## Własny interfejs (bez wchodzenia w HA)
Ten sam panel działa samodzielnie pod adresem **`http://<IP_HA>:8765/`**. Wymaga ustawienia `api_key` w konfiguracji –
przy pierwszym wejściu poprosi o klucz i go zapamięta.
Na iPhonie: otwórz adres w Safari → *Udostępnij* → *Do ekranu początkowego* – dostaniesz osobną aplikację „HAnnounce”
(pełny ekran, własna ikona). Mikrofon w przeglądarce wymaga HTTPS (np. Nabu Casa / reverse proxy); przez zwykłe HTTP
użyj „Nagrywarka urządzenia” lub wgraj plik.

## Otwieranie interfejsu z ekranu blokady (jeden skrypt, nie wiele)
Nie ma już skryptów do pojedynczych dźwięków/głośników. Zamiast tego **jeden** skrypt/skrót otwiera pełnoekranowy
interfejs, a głośniki i dźwięki wybierasz na miejscu w widoku **⚡ Szybkie** (ulubione dźwięki jako duże kafelki, pole tekstu,
ostatnie wiadomości).
- **Skrót iOS (bez powiadomienia):** *Skróty → Otwórz URL →* `homeassistant://navigate/hassio/ingress/<slug>`
  (gotowy adres jest w zakładce 📱 Aplikacja). Dodaj do ekranu blokady, przycisku Action, Stuknięcia w tył lub Siri.
- **Skrypt w HA:** w zakładce 📱 Aplikacja wybierz telefon i kliknij „Utwórz skrypt”. Powstaje jeden skrypt
  `script.hannounce_open`, który wysyła na telefon powiadomienie „dotknij, by otworzyć” (Android otwiera od razu).
  Skrypt niczego nie odtwarza. Uruchom go widżetem „Skrypty” aplikacji HA.
- **Wszystkie trzy naraz:** po kliknięciu „Utwórz skrypt” dostajesz skrypt oraz gotowe do skopiowania adresy skrótu iOS i osobnej aplikacji.
- **Osobna aplikacja:** `http://<IP_HA>:8765/?quick=1` → Udostępnij → Do ekranu początkowego (tryb pełnoekranowy, tylko widok Szybkie).

## Tokeny dla skrótów i dziennik (nadzór)
Zakładka **🔑 Tokeny**: dla każdego skrótu / osoby tworzysz osobny token – nie musisz podawać klucza administratora.
- Token pokazuje się **tylko raz** – skopiuj go. Zapisywany jest wyłącznie jego skrót (hash); można go w każdej chwili **odwołać**.
- Ograniczenia tokenu: wybrane głośniki, zgoda na TTS / dźwięki / skrypty i sceny, **maksymalna głośność**, limit 30 ogłoszeń na minutę.
- Domyślne ustawienia: głośniki oraz silnik TTS / język / głos (z zakładki Mów) – skrót wysyła tylko `{"message": "Obiad gotowy"}`.
- Token działa tylko na `/api/announce`, `/api/sounds` i `/api/stop` – nie ma dostępu do ustawień ani tokenów.
- **👁 Token nadzorowany:** w dzienniku zapisywane jest wszystko, co mówi (pełny tekst, kto, kiedy, na jakich głośnikach, także odrzucone próby).
  Token nienadzorowany zostawia w dzienniku tylko ślad (kto/kiedy/gdzie), bez treści. Ogłoszenia z panelu są zapisywane z treścią.
- **Dziennik ogłoszeń** (na dole zakładki): filtr po tokenie, „Wyczyść dziennik”. Przechowywane jest do 1000 ostatnich wpisów (`/data/log.jsonl`).
- Po utworzeniu dostajesz gotowe pola do skopiowania do aplikacji **Skróty**: adres, nagłówki i treść JSON.
Uwaga: adres `http://<IP>:8765` jest nieszyfrowany – token wysyłany w sieci domowej jest widoczny dla urządzeń w tej sieci. Do dostępu spoza domu użyj HTTPS (Nabu Casa / reverse proxy).

## Czy się ogłasza? Sesje i Live Activity na Dynamic Island
- **Pasek „Teraz ogłaszam”** u góry panelu: co jest ogłaszane (albo „w kolejce”), na których głośnikach, skąd (panel / token), odliczanie
  i przycisk **■ Stop**. Każde ogłoszenie to **sesja** od żądania do końca odtwarzania. Stan zwraca też `GET /api/status`.
- **Sensor** `sensor.hannounce_status` (`idle` / `announcing` + atrybuty: tekst, głośniki, źródło, `ends_at`) – do automatyzacji i historii
  (opcja `status_sensor`).
- **Live Activity (iPhone: Dynamic Island + ekran blokady, Android: Live Update)** przez aplikację Home Assistant Companion
  (`notify.mobile_app_*` z `live_update` i `tag`, koniec przez `clear_notification`). Wymaga iOS 17.2+, Home Assistant Core 2026.7+
  i włączonych Live Activities w aplikacji. Zakładka **🏝️ Live**: włącz, wybierz telefony, ewentualnie „tylko dla ogłoszeń z…” (panel albo token),
  tytuł/treść z symbolami `{text}` `{speakers}` `{source}` `{user}`, ikona, kolory, licznik odliczający, **ukrycie mówionego tekstu**
  (prywatność), czas zostawienia po końcu, przycisk **Test (6 s)**.
- **Dostosowanie na sesję / komuś:** admin może dać Live Activity konkretnej osobie
  - **per token** (zakładka Tokeny → „Status na żywo na tych telefonach”) – osoba widzi na swojej wyspie ogłoszenia ze swojego skrótu,
  - **per ogłoszenie** (tylko panel/administrator): pole `live` w `POST /api/announce`, np.
    `{"message":"…","targets":[…],"live":{"phones":["mobile_app_kasia"],"title":"Dla Kasi","hide_text":true,"icon":"mdi:bell","color":"#ff5722"}}`.
  Tokeny nie mogą same ustawiać pola `live`, a pola wewnętrzne (zaczynające się od `_`) są ignorowane.
- Kilka równoległych ogłoszeń = jedna aktywność pokazująca najnowsze; kończy się po ostatnim.

## Opóźnienia, kolejka i Stop
- **TTS jest przygotowywany z góry** (silnikiem z HA) i dopiero wtedy wysyłany na głośnik jako gotowy plik – dzięki temu nie ma
  niespodziewanego opóźnienia przy odtwarzaniu. Panel pokazuje „Przygotowuję głos…” a potem „Gra ♪”. Ta sama wiadomość
  wysłana ponownie jest natychmiastowa (pamięć podręczna).
- **Kolejka:** kolejne ogłoszenie na tym samym głośniku czeka, aż poprzednie się skończy (zamiast je przerywać lub nakładać się).
  Panel pokazuje „W kolejce – zagra za N s”.
- **■ Stop** (przy głośnikach i w widoku Szybkie, oraz `POST /api/stop`) natychmiast zatrzymuje odtwarzanie na zaznaczonych
  głośnikach (bez zaznaczenia – na wszystkich, które grają) i czyści kolejkę.

## Aktualizacje
- **Interfejs odświeża się sam** co kilka sekund (stany głośników, ulubione, biblioteka) – zmiany z innego telefonu
  lub z automatyzacji widać bez przeładowania strony.
- **Nowa wersja add-onu:** u góry pojawia się żółty baner z numerem nowej wersji i przyciskiem do strony dodatku
  (tam klikasz *Aktualizuj*). W stopce widać zainstalowaną wersję i stan automatycznej aktualizacji.
- **Automatyczne aktualizacje:** włącz przełącznik „Aktualizuj automatycznie” na stronie dodatku
  (Ustawienia → Dodatki → HAnnounce Enhanced). Sklep odświeża repozytorium cyklicznie; wymusisz to przez ⋮ → *Sprawdź aktualizacje*.

## Konfiguracja
| Opcja | Opis |
|---|---|
| `base_url` | Adres, z którego głośniki pobierają dźwięk, **z portem**, np. `http://192.168.1.10:8765`. Puste = automatyczne wykrycie IP hosta. |
| `api_key` | Klucz do zewnętrznego API (port 8765). Puste = API wyłączone. |
| `max_upload_mb` | Limit rozmiaru pliku (domyślnie 20). |
| `log_level` | `debug` / `info` / `warning`. |

Głośnik musi mieć dostęp do portu **8765** hosta HA (sieć lokalna).

## API dla automatyzacji
Wymaga ustawionego `api_key`. Nagłówek `Authorization: Bearer <klucz>` (lub `?key=`).

```
GET  http://<ha>:8765/api/sounds
POST http://<ha>:8765/api/announce
{"targets": ["media_player.kuchnia"], "sound": "Dzwonek", "volume": 0.6}
{"targets": ["media_player.kuchnia"], "message": "Obiad gotowy", "language": "pl", "tts_entity": "tts.google_translate_en_com", "voice": "opcjonalnie"}
```
`sound` to nazwa lub id z biblioteki.

Przykład `configuration.yaml`:
```yaml
rest_command:
  hannounce:
    url: "http://localhost:8765/api/announce"
    method: POST
    headers:
      Authorization: "Bearer TWOJ_KLUCZ"
      Content-Type: application/json
    payload: '{"targets": {{ targets | tojson }}, "sound": "{{ sound }}"}'
```

---
Created by **TeodorTeo.com** · MIT License
