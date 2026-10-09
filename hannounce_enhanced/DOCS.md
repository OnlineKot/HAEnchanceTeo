# HAnnounce Enhanced – by [TeodorTeo.com](https://teodorteo.com)

Panel **HAnnounce** pojawia się w bocznym menu Home Assistanta (ingress).

## Co potrafi
- **Mów (TTS)** – dowolny tekst przez wybrany silnik TTS, w trybie *announce* (przerywa i wznawia odtwarzanie).
- **Nagraj** – własne nagranie z mikrofonu przeglądarki (wymaga HTTPS) lub z nagrywarki telefonu.
- **Wgraj** – dowolny plik audio (mp3, wav, ogg, m4a, webm…), konwertowany do mp3.
- **Generuj** – ton, piski, dzwonek „ding-dong”, gong, powiadomienie, syrena, alarm (częstotliwość, czas, powtórzenia).
- **Jednorazowo** – dźwięk jest odtworzony i automatycznie usuwany, albo **zapisz w bibliotece** i używaj wielokrotnie.
- Opcjonalna **zmiana głośności** na czas ogłoszenia (potem przywracana).

## Własny interfejs (bez wchodzenia w HA)
Ten sam panel działa samodzielnie pod adresem **`http://<IP_HA>:8765/`**. Wymaga ustawienia `api_key` w konfiguracji –
przy pierwszym wejściu poprosi o klucz i go zapamięta.
Na iPhonie: otwórz adres w Safari → *Udostępnij* → *Do ekranu początkowego* – dostaniesz osobną aplikację „HAnnounce”
(pełny ekran, własna ikona). Mikrofon w przeglądarce wymaga HTTPS (np. Nabu Casa / reverse proxy); przez zwykłe HTTP
użyj „Nagrywarka urządzenia” lub wgraj plik.

## Ekran blokady iPhone'a
W zakładce **Biblioteka** (zapisany dźwięk) lub **Mów (TTS)** zaznacz głośniki i kliknij **📱 Utwórz skrypt**.
Add-on tworzy w HA skrypt `script.hannounce_...`, który odtwarza ogłoszenie na wybranych głośnikach.
Potem na iPhonie (aplikacja Home Assistant Companion): przytrzymaj ekran blokady → *Dostosuj* → dodaj widżet
Home Assistant → wybierz skrypt. Skrypt możesz też podpiąć pod Centrum sterowania (iOS 18), Skróty/Siri albo Back Tap.
Jeśli add-on nie może sam zapisać skryptu, pokaże gotowy YAML do wklejenia w `scripts.yaml`.
Uwaga: skrypt zapamiętuje adres dźwięku (`base_url`/IP hosta) – po zmianie IP utwórz go ponownie.

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
{"targets": ["media_player.kuchnia"], "message": "Obiad gotowy", "language": "pl", "tts_entity": "tts.google_translate_en_com"}
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
