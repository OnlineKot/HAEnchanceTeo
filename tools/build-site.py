#!/usr/bin/env python3
"""Buduje site/index.html (biblioteka dodatkow) z config.yaml kazdego dodatku: nazwa, wersja, slug. Opisy PL/EN sa w tym pliku.
Uruchom po zmianie wersji lub dodaniu dodatku:  python3 tools/build-site.py"""
import re, html, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO = 'https://github.com/OnlineKot/HAEnchanceTeo'
BRANCH = 'claude/hannounce-enhanced'
REPO_URL = REPO + '#' + BRANCH
MY_HA = 'https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=' + REPO_URL.replace(':', '%3A').replace('/', '%2F').replace('#', '%23')

ADDONS = [
 ('hannounce_enhanced', 'Ogłoszenia na głośnikach: TTS dowolnego silnika HA, własne nagrania, wgrywane i generowane dźwięki, jednorazowe lub zapisane. Pamięć każdego głośnika (wznawianie, głośność, opóźnienia, godziny ciszy), ulubione, kalibracja, tokeny API dla Skrótów z nadzorowanym logiem.',
  'Announce on your speakers with TTS (any HA TTS engine), your own recordings, uploads and generated sounds, one-time or saved. Per-speaker memory (resume playback, volume, delays, quiet hours), favorites, calibration, API tokens for Shortcuts with a supervised log.'),
 ('haliveteo', 'Akcje na żywo z wielu urządzeń. Każdy telefon, tablet i panel ścienny dostaje własny token i własny układ kafelków (przyciski, przełączniki, suwaki, stany), akcje w czasie rzeczywistym, Live Activities na Dynamic Island, zdarzenia dla automatyzacji i REST API.',
  'Live actions from many devices. Every phone, tablet or wall panel gets its own token and its own layout of live tiles (buttons, toggles, sliders, states), a real-time action feed, Live Activities on the Dynamic Island, events for automations and a REST API.'),
 ('haroutineteo', 'Rutyny z krokami zamiast skryptów YAML: ogłoszenia, ściszanie świateł przez minuty, sceny, czekanie, warunki. Uruchamiane ze Skrótu na iPhonie, o czasie albo przez encję, z postępem kroków na Dynamic Island.',
  'Routines with steps instead of YAML scripts: announce, fade lights over minutes, scenes, waits, conditions. Run from an iPhone Shortcut, by time or by an entity, with live step progress on the Dynamic Island.'),
 ('hacertteo', 'Darmowy certyfikat Let’s Encrypt dla Home Assistanta przez DNS-01 (Cloudflare lub DuckDNS). Bez otwartych portów, z automatycznym odnawianiem, czujnikiem dni do końca i powiadomieniem o błędzie.',
  'A free Let’s Encrypt certificate for Home Assistant via DNS-01 (Cloudflare or DuckDNS). No open ports, automatic renewal, a days-left sensor and a failure notification.'),
 ('hacardsteo', 'Karty Lovelace w stylu Mushroom dla każdego typu encji: karta uniwersalna, chipy, pokój, statystyki, tytuł oraz karta mediów z przeglądarką biblioteki. Dodatek sam je instaluje i rejestruje.',
  'Mushroom-style Lovelace cards for every entity type: a universal card, chips, room, stats, title and a media card with a library browser. The add-on installs and registers them for you.'),
 ('haaiteo', 'Claude albo Gemini w Home Assistancie: pytania, sterowanie i zmiany. Zmiany czekają na Twoje zatwierdzenie (z podglądem różnic i cofaniem), groźne domeny są blokowane po stronie serwera. Opcjonalny skrót z ekranu blokady albo Siri.',
  'Claude or Gemini inside Home Assistant: ask, control and modify. Changes are staged with a diff and need your approval (with undo); dangerous domains are blocked server-side. Optional lock-screen / Siri shortcut.'),
 ('hafreudteo', 'Spokojna pomoc w opiece nad kotem (dla Freuda): kto i kiedy nakarmił, z ochroną przed podwójnym karmieniem, woda, żwirek, przypomnienia o pchłach, odrobaczaniu i szczepieniach, wykres wagi, przypomnienia na telefonie z przyciskiem Zrobione.',
  'A calm cat companion (for Freud): who fed the cat and when, with protection against double feeding, plus water, litter, flea / deworming / vaccine reminders, a weight chart and phone reminders with a Done button.'),
 ('hamcpteo', 'Pełny zestaw narzędzi HA-MCP (ponad 87) dla Claude i innych klientów AI, budowany lokalnie z dołączonych źródeł (na bazie ha-mcp, MIT). Bez telemetrii, bez analityki, bez zapytań o aktualizacje.',
  'The full HA-MCP toolbox (87+ tools) for Claude and other AI clients, built locally from the bundled source (based on ha-mcp, MIT). No telemetry, no analytics, no update phone-home.'),
 ('haqnapteo', 'Kopie zapasowe Home Assistanta na QNAP przez SMB (harmonogram i retencja) oraz pobieranie multimediów z dysku do HA. Lista, pobieranie i kasowanie kopii na NAS. Bez otwartych portów, panel tylko przez Home Assistanta.',
  'Back up Home Assistant to your QNAP over SMB with schedule and retention, and download media from it into HA. List, fetch and delete backups on the NAS. No open ports, the panel is reachable only through Home Assistant.'),
]

def meta(slug):
    f = ROOT / slug / 'config.yaml'
    t = f.read_text(encoding='utf-8')
    name = re.search(r'^name:\s*"?([^"\n]+)"?', t, re.M).group(1).strip()
    ver = re.search(r'^version:\s*"?([^"\n]+)"?', t, re.M).group(1).strip()
    return name, ver

cards = []
for slug, pl, en in ADDONS:
    name, ver = meta(slug)
    base = '%s/blob/%s/%s/' % (REPO, BRANCH, slug)
    cards.append('''      <article class="item" data-q="%s">
        <div class="item-head"><h3>%s</h3><span class="ver">v%s</span></div>
        <p class="lang-pl">%s</p>
        <p class="lang-en">%s</p>
        <div class="links">
          <a href="%sDOCS.md" target="_blank" rel="noopener"><span class="lang-pl">Dokumentacja</span><span class="lang-en">Documentation</span></a>
          <a href="%sCHANGELOG.md" target="_blank" rel="noopener"><span class="lang-pl">Lista zmian</span><span class="lang-en">Changelog</span></a>
        </div>
      </article>''' % (html.escape((name + ' ' + pl + ' ' + en).lower()), html.escape(name), html.escape(ver), html.escape(pl), html.escape(en), base, base))

PAGE = (ROOT / 'tools' / 'site-template.html').read_text(encoding='utf-8')
out = (PAGE.replace('{{CARDS}}', '\n'.join(cards)).replace('{{COUNT}}', str(len(ADDONS))).replace('{{REPO}}', REPO)
       .replace('{{REPO_URL}}', REPO_URL).replace('{{MY_HA}}', MY_HA))
(ROOT / 'site').mkdir(exist_ok=True)
(ROOT / 'site' / 'index.html').write_text(out, encoding='utf-8')
print('site/index.html: %d dodatkow' % len(ADDONS))
