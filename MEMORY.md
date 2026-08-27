# MEMORY.md

## Dauerhafte Projektfakten

- OpenClaw-Agent: `hpg`; Workspace ist dieses Repository. Die Coding-Runtime
  ist der native Codex-Harness mit `openai/gpt-5.6-sol`.
- Vor Facharbeit `hpg-orientation`, danach den passenden Skill aus
  `.agents/skills/` laden. Die Rollen liegen in `.agents/agents/`.
- Pflichtinterpreter: `venv312\Scripts\python.exe` mit Python 3.12.
  Python 3.13+ ist wegen numba nicht zulaessig.
- Abschlussbeleg:
  `venv312\Scripts\python.exe -m pytest tests/ --tb=short -q`.
  Die Suite verwendet bereits `-n auto`; keine parallelen vollen Testlaeufe.
- Geschuetzt sind Cache-/DB-/Lock-/Coverage-Dateien, reale Musikbibliotheken,
  Rekordbox-Daten und vorhandene `Claude-Autopilot-*`-Artefakte.

## Technische Invarianten

- Cache-Lookup vor der Audioanalyse. Rekordbox-Fast-Path und Vollanalyse bei
  relevanten Aenderungen gemeinsam betrachten.
- Mixpunkte: `0 <= mix_in < mix_out <= duration`; Phrasenraster und mindestens
  zwei Phrasen beachten. `MIX_POINT_UNSET = -1.0`; `0.0` ist gueltig.
- Aenderungen am Analyse-Output erfordern eine begruendete Pruefung der
  `CACHE_VERSION`.
- `main.py` enthaelt die PyQt6-GUI; UI-Updates nur im Main-Thread.

## Betriebswissen

- Vor und nach nichttrivialen Aenderungen prueft `hpg-waechter` unabhaengig
  und schreibgeschuetzt. Nur mit `DURCHGEWUNKEN` abschliessen; Auflagen zuerst
  erledigen.
- In Memory gehoeren nur stabile, wiederverwendbare Fakten, Entscheidungen und
  bewaehrte Reparaturwege. Keine Zugangsdaten, personenbezogenen Details oder
  fluechtigen Debug-Ausgaben speichern.

## Promoted From Short-Term Memory (2026-08-26)

<!-- openclaw-memory-promotion:memory:memory/2026-08-25.md:8:19 -->
- Die bereits abgegebene Bewertung des ersten Clips soll erhalten und spaeter fuer die Auswertung verwendet werden; alle anderen Hoerproben werden erst nach der technischen Korrektur neu erzeugt. - Vor dem erneuten Rendern moechte David eine vollstaendige, nachvollziehbare Uebersicht aller Parameter, Werte, Gewichte, Gates und Kriterien sehen, welche die Playlist-Reihenfolge und die passenden Mixpunkte bestimmen. ## Fortsetzungsstand - Die Umsetzung der Beatgrid-Validierung und Beatphasen-/Kick-Synchronisation wurde begonnen, ist aber noch nicht abschliessend verifiziert.... [score=0.852 recalls=10 avg=0.506 source=memory/2026-08-25.md:8-19]
<!-- openclaw-memory-promotion:memory:memory/2026-08-25.md:1:12 -->
- # 2026-08-25 ## Dauerhafte fachliche Entscheidungen - Fuer jeden Uebergang ist vollstaendiges Beatmatching ein hartes Gueltigkeitskriterium: Track A und B muessen auf dasselbe effektive Tempo gebracht und in der Beatphase so ausgerichtet werden, dass die Kick-Transienten zeitgleich uebereinanderliegen und wie ein einzelner Kickbass wirken. Doppelschlaege, Flattern, Galoppieren oder Drift machen einen Kandidaten technisch ungueltig und duerfen nicht nur als Geschmacksfrage bewertet werden. - Das Rekordbox-Beatgrid ist nicht ungeprueft vertrauenswuerdig.... [score=0.827 recalls=8 avg=0.517 source=memory/2026-08-25.md:1-12]
