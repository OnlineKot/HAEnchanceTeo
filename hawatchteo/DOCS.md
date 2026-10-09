# HAWatchTeo – by [TeodorTeo.com](https://teodorteo.com)

**Strażnik encji** Home Assistanta: znajduje encje, które przestały działać, zanim ktoś to zauważy.

## Co wykrywa
- **Niedostępne** (`unavailable`, opcjonalnie też `unknown`) dłużej niż N minut (domyślnie 15) – świeże, krótkie zaniki są pomijane.
- **Słaba bateria** – sensory z `device_class: battery` oraz encje z atrybutem `battery_level` poniżej progu (domyślnie 15%).
- **Nieaktualne** (opcjonalnie) – encje bez żadnej aktualizacji dłużej niż N godzin w wybranych domenach (domyślnie `sensor`, `binary_sensor`).

Każdy problem pokazuje nazwę, czas trwania, **integrację, urządzenie i obszar** (z rejestrów HA) oraz przyciski **Otwórz w HA** i **Ignoruj**.

## Ignorowanie i hałas
- **Ignoruj encje** – lista id lub wzorców z `*` (np. `sensor.*_rssi`, `light.test_*`), jedna w linii.
- **Pomijaj domeny** – domyślnie m.in. `update`, `button`, `scene`, `script`, `automation`, `person`, `weather`.

## Powiadomienia i sensory
- Powiadomienia na telefon (aplikacja Companion): **jedno zbiorcze** o nowych problemach, opcjonalnie o naprawionych, plus przypomnienie o nierozwiązanych co N godzin.
- Sensory (opcja): `sensor.hawatchteo_problems` (liczba + lista w atrybutach) i `binary_sensor.hawatchteo_problem` – do dashboardów i automatyzacji.
- **Dziennik** zdarzeń: kiedy problem się pojawił i kiedy zniknął.

Skan odbywa się co 60 s oraz na żądanie („Skanuj teraz”). Panel dostępny tylko przez Home Assistant (ingress).

---
Created by **TeodorTeo.com** · MIT License
