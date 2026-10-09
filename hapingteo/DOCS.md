# HAPingTeo – by [TeodorTeo.com](https://teodorteo.com)

**Monitor dostępności i opóźnień** internetu, routera i urządzeń w domu.

## Typy monitorów
- **Ping** (ICMP) – host lub IP. Jeśli ICMP nie jest dozwolony w kontenerze, add-on przechodzi na sprawdzanie TCP (443/80) i o tym informuje.
- **TCP** – host i port (np. NAS, kamera, serwer MQTT).
- **HTTP** – URL, oczekiwany kod (domyślnie dowolny poniżej 400), opcjonalnie **słowo, które musi być na stronie**, opcjonalnie bez weryfikacji SSL.
- **DNS** – czy nazwa się rozwiązuje.

Interwał od 10 s, limit czasu, **ponowienia** (monitor jest „down” dopiero po N kolejnych niepowodzeniach, więc jedna zgubiona paczka nie budzi alarmu).

## Gotowe zestawy
„Internet” (1.1.1.1, 8.8.8.8, DNS google.com, WWW), „Router” (brama domyślna wykryta automatycznie), „Home Assistant”.

## Co widzisz
Kafelki z opóźnieniem, **dostępnością 24 h**, wykresem i paskiem ostatnich sprawdzeń; szczegóły z średnią / min / max / p95 i historią 24 h (zapisywane 48 h).

## Powiadomienia i sensory
- Powiadomienia na telefon, gdy coś przestaje odpowiadać i gdy wraca (z czasem przestoju).
- Sensory: `binary_sensor.hapingteo_<nazwa>` (łączność, z opóźnieniem i dostępnością w atrybutach), `sensor.hapingteo_<nazwa>_latency` (ms),
  `sensor.hapingteo_status` i `binary_sensor.hapingteo_problem` – do dashboardów i automatyzacji.

Panel dostępny tylko przez Home Assistant (ingress). Limit 50 monitorów.

---
Created by **TeodorTeo.com** · MIT License
