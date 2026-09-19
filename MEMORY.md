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

## Promoted From Short-Term Memory (2026-08-30)

<!-- openclaw-memory-promotion:memory:memory/2026-08-25.md:5:8 -->
- Dauerhafte fachliche Entscheidungen: Fuer jeden Uebergang ist vollstaendiges Beatmatching ein hartes Gueltigkeitskriterium: Track A und B muessen auf dasselbe effektive Tempo gebracht und in der Beatphase so ausgerichtet werden, dass die Kick-Transienten zeitgleich uebereinanderliegen und wie ein einzelner Kickbass wirken. Doppelschlaege, Flattern, Galoppieren oder Drift machen einen Kandidaten technisch ungueltig und duerfen nicht nur als Geschmacksfrage bewertet werden.; Das Rekordbox-Beatgrid ist nicht ungeprueft vertrauenswuerdig.... [score=0.812 recalls=0 avg=0.620 source=memory/2026-08-25.md:5-8]
<!-- openclaw-memory-promotion:memory:memory/2026-08-25.md:9:9 -->
- Dauerhafte fachliche Entscheidungen: Vor dem erneuten Rendern moechte David eine vollstaendige, nachvollziehbare Uebersicht aller Parameter, Werte, Gewichte, Gates und Kriterien sehen, welche die Playlist-Reihenfolge und die passenden Mixpunkte bestimmen. [score=0.812 recalls=0 avg=0.620 source=memory/2026-08-25.md:9-9]
<!-- openclaw-memory-promotion:memory:memory/2026-08-25.md:13:14 -->
- Fortsetzungsstand: Die Umsetzung der Beatgrid-Validierung und Beatphasen-/Kick-Synchronisation wurde begonnen, ist aber noch nicht abschliessend verifiziert. Keine Erfolgsmeldung geben, bevor fokussierte Tests, die volle Suite mit `venv312\\Scripts\\python.exe` und die unabhaengige schreibgeschuetzte `hpg-waechter`-Pruefung erfolgreich sind.; Vor weiterer Facharbeit den aktuellen Git-Diff sorgfaeltig pruefen und vorhandene fremde Aenderungen bewahren. Keine Clips erzeugen und keine reale Musikbibliothek, Rekordbox-Daten oder Benutzer-Cache-Datei veraendern. [score=0.812 recalls=0 avg=0.620 source=memory/2026-08-25.md:13-14]
<!-- openclaw-memory-promotion:memory:memory/2026-08-25.md:18:21 -->
- Python- und Laufzeitumgebung: HPG verwendet fuer Entwicklung, Tests und Builds weiterhin die bestehende Projektumgebung `venv312` mit Python 3.12.10. Es war keine neue Python-Version erforderlich; Python 3.13+ bleibt wegen `numba` ausgeschlossen.; Ein zuvor gemeldetes `No Python at ...Python312` entstand beim Start von `venv312` innerhalb der Sandbox, die den installierten Basisinterpreter nicht sehen konnte. Das war kein belastbarer Nachweis fuer eine fehlende Installation.... [score=0.812 recalls=0 avg=0.620 source=memory/2026-08-25.md:18-21]

## Promoted From Short-Term Memory (2026-08-31)

<!-- openclaw-memory-promotion:memory:memory/2026-08-25.md:29:32 -->
- Aktueller Arbeitsstand Beatgrid und Kick-Synchronisation: David hat die vollstaendige Liste der aktuell in Playlist-Reihenfolge und Mixpunktwahl einfliessenden Parameter, Gewichte, Faktoren, Analysen, Gates und Werte erhalten. Aktuell bestehen keine gelernten Gewichtsüberschreibungen, Kandidatenpraeferenzen oder gespeicherten Paarwahlen.; Die Beatgrid-/Kick-Synchronisationsaenderung ist weiterhin eine grosse, unvollstaendig verifizierte Arbeitskopie: geaendert sind Kernmodule fuer Analyse, Cache, Downbeat, Modelle, Paarkandidaten, Playlist, Rekordbox-Import, Rendering und GUI sowie zugehoerige Tests und... [score=0.812 recalls=0 avg=0.620 source=memory/2026-08-25.md:29-32]
<!-- openclaw-memory-promotion:memory:memory/2026-08-25.md:34:34 -->
- Aktueller Arbeitsstand Beatgrid und Kick-Synchronisation: Klarstellung zum ersten Punkt dieses Abschnitts: Aktuell bestehen keine gelernten Gewichts-Ueberschreibungen, Kandidatenpraeferenzen oder gespeicherten Paarwahlen. [score=0.812 recalls=0 avg=0.620 source=memory/2026-08-25.md:34-34]
<!-- openclaw-memory-promotion:memory:memory/2026-08-25.md:25:25 -->
- Kommunikationspraeferenz: Jede an David gerichtete Nachricht muss mit `:-)` enden. [score=0.812 recalls=0 avg=0.620 source=memory/2026-08-25.md:25-25]
<!-- openclaw-memory-promotion:memory:memory/2026-08-25.md:42:43 -->
- Verifizierter Mixpunkt-Vertrag: Die Umsetzung erhoehte die Cache-Version auf 36. Der Abschlussbeleg vom 25.08.2026 umfasst 1958 bestandene Tests bei 81,67 Prozent Coverage und die unabhaengige Bewertung `DURCHGEWUNKEN`.; Fuer diese Aenderung wurden keine neuen Hoerclips erzeugt. [score=0.812 recalls=0 avg=0.620 source=memory/2026-08-25.md:42-43]
<!-- openclaw-memory-promotion:memory:memory/2026-08-25.md:47:50 -->
- Aktualisierte Entscheidung fuer neue Hoerproben: Fuer die jetzt zu erstellenden Hoerproben ist nicht der Rekordbox-Beatgrid-Status das Auswahl-Gate. Entscheidend ist das tatsaechliche Audio: Track B wird auf das effektive Tempo von Track A gebracht und so gestartet beziehungsweise zeitlich versetzt, dass die echten Kick-/Taktschlaege beider Tracks phasengleich uebereinanderliegen und waehrend des Uebergangs nicht driften.... [score=0.812 recalls=0 avg=0.620 source=memory/2026-08-25.md:47-50]
<!-- openclaw-memory-promotion:memory:memory/2026-08-25.md:38:41 -->
- Verifizierter Mixpunkt-Vertrag: Bei erkanntem Intro muss `Mix-In` immer strikt nach dem Intro-Ende liegen.; Bei erkanntem Outro muss `Mix-Out` immer strikt vor dem Outro-Beginn liegen.; Auch manuelle Rekordbox-Cues duerfen diese beiden Strukturgrenzen nicht umgehen. Wenn innerhalb der gueltigen Grenzen kein Mixpunkt gefunden werden kann, wird der Uebergang abgelehnt.; Die zuvor genannte Regel einer verbleibenden Mindestlaufzeit von zwei Phrasen fuer `Mix-In` gehoert nicht zum gewuenschten Vertrag und wurde entfernt. [score=0.812 recalls=0 avg=0.620 source=memory/2026-08-25.md:38-41]
<!-- openclaw-memory-promotion:memory:memory/2026-08-25.md:51:51 -->
- Aktualisierte Entscheidung fuer neue Hoerproben: Letzte kommunizierte Zeitschaetzung fuer Tests, Aktualisierung, Commit/Push, Analyse und Rendering: typischerweise 2 bis 5 Stunden, bei umfangreicher Neuanalyse bis zu 6 Stunden. Diese Schaetzung ist kein Abschlussnachweis. [score=0.812 recalls=0 avg=0.620 source=memory/2026-08-25.md:51-51]
<!-- openclaw-memory-promotion:memory:memory/2026-08-25.md:64:65 -->
- Abgeschlossener Psytrance-Hoerprobenlauf: Die lokale Bewertungsseite wurde fuer diesen Lauf unter `http://127.0.0.1:8767/` gestartet. Der Serverstatus ist fluechtig und muss bei einer spaeteren Fortsetzung erneut geprueft werden.; Die fruehere Aussage in dieser Datei, es seien noch keine neuen Hoerclips erzeugt worden, ist damit ueberholt. Ob Commit, Push und Vault-Aktualisierung vollstaendig abgeschlossen wurden, ist durch den letzten Abschlussbeleg nicht bestaetigt und muss separat anhand von Git- und Vault-Status verifiziert werden. [score=0.812 recalls=0 avg=0.620 source=memory/2026-08-25.md:64-65]
<!-- openclaw-memory-promotion:memory:memory/2026-08-25.md:55:56 -->
- Offener Fortsetzungsauftrag: Der Arbeitsbaum ist stark veraendert und noch nicht als abgeschlossen belegt. Vor Commit zuerst den gesamten Diff auditieren, fokussierte Tests und die volle Suite mit `venv312\\Scripts\\python.exe -m pytest tests/ --tb=short -q` ausfuehren und bei der grossen Aenderung `hpg-waechter` schreibgeschuetzt pruefen lassen. Erst danach gezielt stagen, committen und pushen.; Anschliessend 30 Psytrance-Paare anhand der neuen Logik aus dem groesseren Trackbestand waehlen, je Paar maximal fuenf phasensynchronisierte Hoerproben rendern und die erzeugten Dateien technisch pruefen.... [score=0.812 recalls=0 avg=0.620 source=memory/2026-08-25.md:55-56]
<!-- openclaw-memory-promotion:memory:memory/2026-08-25.md:60:63 -->
- Abgeschlossener Psytrance-Hoerprobenlauf: Der zuerst angeforderte Hoerprobenlauf wurde abgeschlossen: 30 Psytrance-Trackpaare mit insgesamt 47 erfolgreich gerenderten Varianten. Pro Paar entstanden hoechstens drei Varianten und damit weniger als das erlaubte Maximum von fuenf.; Die strenge Audio-Synchronpruefung blieb beim Rendern aktiv. Fuer Hoerproben ist weiterhin die reale, phasengleiche Kick-/Taktschlag-Ueberlagerung nach Tempoangleichung massgeblich; der Rekordbox-Beatgrid-Status ist nur ein Hilfsmittel und fuer diesen Lauf kein Auswahl-Gate.; Alle erzeugten WAV-Dateien wurden als lesbare Stereo-Dateien mit 44,1 kHz technisch... [score=0.812 recalls=0 avg=0.620 source=memory/2026-08-25.md:60-63]
