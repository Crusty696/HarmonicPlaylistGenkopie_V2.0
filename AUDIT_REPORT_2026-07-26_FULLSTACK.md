# Consulting Team Review

> Auftrag: Gesamte HPG-App anhand von `ARBEITSPLAN_2026-07-26.md` untersuchen, Verdrahtungen, Datenfluss, Pipelines, SQLite/Cache, Schemas, Ressourcen, Security, Dead Code und CI prüfen; belegte Probleme autonom beheben und verifizieren.
> Reversibilität: Code-/Dokumentationsänderungen sind per Git revertierbar. Produktive Audio-, Rekordbox- und Benutzerdaten wurden nicht verändert. Der Produktivcache wurde nur lesend inspiziert; der Installer löscht ihn ausdrücklich nicht.

## Executive Summary

Der End-to-End-Datenfluss ist belastbar: Scan → Sicherheitsfilter → Parallel-Analyse → Cache → Playlist/Scoring → Transition-Plan → Renderer/Exporter ist durch Tests und einen echten AIFF-Lauf abgedeckt. Der Abschlussstand ist 1.384/1.384 Tests, 74,18 % Coverage, 39/39 Verify-Checks und 17/17 E2E-Checks.

Die wichtigsten zuvor belegten Risiken wurden behoben: Mix-In-Grenzen, Rekordbox-Zeitsemantik, Cache-Versionierung und Metadaten-Invalidierung, stale GUI-Worker/Playlist-Zustände, Preview-Temp-Dateien, Pfad-Containment sowie CI-Python-/xdist-Vertrag. Der Restlauf schloss außerdem den echten Einzel-Task-Timeout, den Score-Vertrag, die Mixpoint-Sentinel-Semantik, die aktive/historische Dokumentationsdrift und nachgewiesen toten Code.

## Findings

### Teamrollen und falsifizierbare Beiträge

- **Engagement Manager:** MECE-Schnitt in Wiring, Daten-/Persistenzvertrag, Ressourcen/Security, CI und UX; falsifizierbar über die separaten Test-/Verify-Gates.
- **Senior Partner:** Release ist technisch GO; musikalische Präferenz bleibt eine Produktentscheidung, während die reale technische Audio-/ANLZ-Abnahme bestanden ist.
- **Analyst:** Die externe ANLZ-Dokumentation bestätigt Millisekunden für Beatgrid-Zeitwerte; ein echter lokaler ANLZ-Fixture-Test bestätigt die Umsetzung.
- **Domain Expert:** ProcessPool-Cancel, Cache-Key und TransitionPlan waren die engsten Architekturkopplungen; falsifizierbar durch Pool-/Cache-/Renderer-Regressionen.
- **Risk Officer:** Größtes verbleibendes Risiko ist eine native Bibliotheksvariante außerhalb der getesteten Decoder-/ANLZ-Fixtures; der Einzel-Task-Hard-Timeout wird durch einen absichtlich blockierenden Worker-Test falsifiziert.
- **Devil's Advocate:** 1.381 grüne Tests beweisen keine musikalische Qualität und keine vollständige RB-Varianz; falsifizierbar durch reale Library-/ANLZ-/Hörtests.
- **Synthesizer/Teamleiter:** Empfehlung GO: technische Gates und die lokale reale Audio-/ANLZ-Abnahme sind erfüllt; subjektive Hörkalibrierung bleibt optional.

### Critical

Keine ungepatchte Critical-Lücke bestätigt. Der zuvor geprüfte Code enthält keine SQL-Injection, kein `shell=True`, keine ungesicherten Pickle-Pfade und keine Secrets im Repository.

### High

| Befund | Status | Evidenz / Lösung |
|---|---|---|
| Quantisierter Mix-In konnte hinter Track B liegen | behoben | `hpg_core/dj_brain.py` begrenzt den finalen Fallback auf die Trackdauer; Verify-/DJ-Tests decken kurze Tracks und Grid-Grenzen ab. |
| Rekordbox-Zeitwert `120` wurde heuristisch als 120 s statt 120 ms behandelt | behoben | Cues und ANLZ-PQTZ nutzen explizite Millisekunden-Normalisierung. Maßgeblich ist der pyrekordbox-ANLZ-Vertrag: [ANLZ-Format](https://pyrekordbox.readthedocs.io/en/stable/formats/anlz.html). |
| Audio-Cache ignorierte geänderte Rekordbox-BPM/Key/Cues | behoben | `rekordbox_signature` wird in `Track` persistiert und in den Cache-Key aufgenommen; Cache-Version auf 24 erhöht. |
| Abbruch erreichte den Analyse-ProcessPool nicht | verbessert/behoben für kooperative Abbrüche | `AnalysisWorker` reicht `cancel_callback` weiter; der Pool pollt in kurzen Intervallen und terminiert bei Cancel. |
| Analyse-Timeout war nur ein wirkungsloser `Future.result(timeout=...)`-Aufruf auf bereits fertigen Futures | behoben | Der Pool reiht höchstens ein Future pro Worker ein, misst die Laufzeit jedes aktiven Futures und terminiert bei Überschreitung; Recovery bleibt explizit pro Datei. Das folgt dem `ProcessPoolExecutor`-/`Future`-Vertrag von [concurrent.futures](https://docs.python.org/3/library/concurrent.futures.html). |
| Fehlerlauf ließ eine alte Playlist exportierbar | behoben | Neuer Analyse-Lauf leert Playlist, Panels, Metriken und Exportstatus vor Worker-Start. |
| CI kontrahierte Python 3.11, App/Build aber Python 3.12 | behoben | Workflows nutzen Python 3.12.10; `pytest-xdist` wird installiert und Testfehler werden nicht mehr mit `continue-on-error` verdeckt. Siehe [setup-python](https://github.com/actions/setup-python). |

Gegenmaßnahme für High-Befunde: Jede Änderung wurde durch gezielte Tests, den Volltest und E2E gegen echte AIFF-Dateien geprüft; Produktionsdateien blieben außerhalb des Schreibumfangs.

Counter-Proposals: harte Fehler statt Mixpoint-Fallback; explizite Unit-Typen statt zentraler Millisekunden-Konvention; Rekordbox-Metadaten gar nicht cachen; Einzelprozess-Isolation je Track; alte Playlist nur sichtbar, aber nicht exportierbar; zusätzlich eine Python-Version-Matrix.

### Medium

| Befund | Status | Evidenz / Lösung |
|---|---|---|
| Relative Cache-Konfiguration konnte CWD-abhängige Split-Brain-DBs erzeugen | behoben | Cache-Verzeichnisse werden absolut aufgelöst; SQLite-Verbindungen setzen `PRAGMA foreign_keys=ON`. Siehe [SQLite PRAGMA](https://www.sqlite.org/pragma.html). |
| Alte/ungültige Cache-Rows konnten gelesen werden | behoben | Version wird beim Read gefiltert; fehlende Marker und stale Rows werden bereinigt; numerische/finite Felder werden validiert und fehlerhafte Rows quarantänisiert. |
| Installer löschte unter `{app}` statt `%LOCALAPPDATA%\HPG` und suggerierte falsche Cache-Bereinigung | behoben | Uninstaller entfernt keinen Benutzer-Cache mehr; nur App-Logs bleiben im App-Verzeichnis löschbar. |
| Manifest- und Blindtest-Pfade konnten aus erlaubten Roots ausbrechen | behoben | `--audio-root`/`--source-root` plus `Path.is_relative_to()` nach `resolve()`, inklusive Symlink-Containment. Siehe [pathlib](https://docs.python.org/3.14/library/pathlib.html). |
| GUI-Scan war symlink- und mengenmäßig riskant | behoben | Realpath-Containment und `SECURITY_MAX_PLAYLIST_SIZE` greifen bereits beim Scan; Datei-/Dauerlimits greifen vor Decoder/LUFS. |
| Preview-Dateien lagen im globalen Temp-Verzeichnis | behoben | Jeder Render-Worker nutzt ein privates `mkdtemp`-Verzeichnis und entfernt nur den eigenen Inhalt. Siehe [tempfile](https://docs.python.org/3/library/tempfile.html). |
| Qualitätsanzeige nutzte einfache Harmonik, Empfehlungen den erweiterten Transition-Score | behoben | `calculate_playlist_quality()` mittelt jetzt denselben erweiterten und auf die angezeigte 0–100-Skala gerundeten Transition-Score; ein Golden Test vergleicht Quality und Empfehlung. |
| `mix_in_point == 0.0` war zwischen gültigem Trackstart und „nicht bestimmt“ ambivalent | behoben | `-1.0` ist ab Cache-Version 24 der explizite Nicht-gesetzt-Sentinel; `0.0` wird in Fallbacks, Export, UI und Validierung als gültig behandelt. |

Counter-Proposals: Cache ausschließlich bei Migration komplett neu aufbauen; Benutzerdaten über einen separaten „Daten entfernen“-Schalter löschen; absolute Manifest-Pfade verbieten; Symlinks vollständig ignorieren; exklusive `NamedTemporaryFile`-Handles verwenden; getrennte Qualitäts- und Empfehlungswerte zusätzlich sichtbar machen.

### Low

- Historische Dokumente und archivierte Pläne enthalten weiterhin alte Cache-Versionen/Pfade; sie sind jetzt durch `docs/archive/README.md` bzw. den Snapshot-Hinweis als nicht-normativ markiert. Aktive Dokumente nennen Cache-Version 24.
- Nachgewiesen ungenutzte Symbole wurden entfernt: `AI_AUTO_APPLY_MIXPOINTS`-Block, `ANALYSIS_FIELD_CONSUMERS`, `GenreMixProfile.intro_bars`, zwei unreferenzierte Mixpoint-Section-Wrapper, mehrere ungenutzte Konfigurations-/Theme-Konstanten sowie eine tote Downbeat-Variable. Öffentliche/aktive Felder wurden nicht spekulativ entfernt.

## Datenfluss- und Schema-Mapping

```text
Folder / Manifest
  -> Realpath-Containment + Größen-/Mengenlimit
  -> Rekordbox-Signatur + Audio-Stat-Key
  -> SQLite v24 (WAL, Lock, Version/Schema-Validierung)
  -> ParallelAnalyzer / AnalysisWorker / Cancel-Polling
  -> Track-Dataclass + Sections/Phrase/Provenienz
  -> Playlist-Strategie + Scoring-Kontext
  -> TransitionPlan (ein Timing-Vertrag)
  -> Preview-Renderer / M3U8 / Rekordbox XML
```

Produktive Cache-Inspektion: vorhandene Datenbanken unter `%LOCALAPPDATA%\HPG` waren lesbar und `integrity_check=ok`; keine produktive Migration wurde ausgeführt. SQLite dokumentiert, dass Foreign Keys pro Verbindung aktiviert werden müssen; das ist nun verdrahtet.

## Abgleich mit `ARBEITSPLAN_2026-07-26.md`

- Phase 0: erledigt/verifiziert; Equal-Power-DSP, Worker-Lifecycle, Phrase-Gates, Cancel, AI-Guards und Restart-Cleanup sind im aktiven Code und durch Verify-/GUI-Tests abgedeckt.
- Phase 1: Kern-Grid-/Phrasen- und Paar-Timing umgesetzt; Mixpoint-Grenzen, Bar-Konstanten, XML-Downbeat-Gate und der explizite Mixpoint-Sentinel wurden geschlossen.
- Phase 2: Feature-/LUFS-/Cache-/Pool-/Preview-/GUI-Sicherheitsmaßnahmen umgesetzt; der Einzel-Task-Timeout ist durch begrenztes In-Flight-Submitting und Prozess-Termination geschlossen.
- Phase 3: Reale Audio-/ANLZ-Abnahme durchgeführt; der E2E-/Render-Lauf bestätigt technische Invarianten, musikalische Präferenz bleibt ein bewusster Produktentscheid.
- Phase 4: aktive Doku/CI/Installer-Schnittstellen und historische Snapshot-Kennzeichnung aktualisiert; nachgewiesen toter Code wurde entfernt. Die große `main.py`-Modulzerlegung bleibt als rein strukturelle, nicht notwendige Folgearbeit bestehen.

## Steel-Man Gegenposition

„Grüne Tests beweisen nicht, dass die Anwendung musikalisch korrekt ist; insbesondere echte Rekordbox-ANLZ-Dateien, große Libraries, Windows-Dateisperren und subjektive Transition-Qualität können außerhalb der Testfixtures liegen.“ Das ist berechtigt. Deshalb wurden zwei lokale Rekordbox-Tracks bis zum Render geprüft, ein echter ANLZ-Beatgrid-Rohwert gegen Importer und Analyse abgeglichen und Peak/Pegel/Kanal-/Sample-Invarianten gemessen. Eine subjektive Hörsession bleibt als Präferenztest optional.

## Pre-mortem

Angenommen, der nächste Release scheitert: Am wahrscheinlichsten wären (1) ein neuer Cache-/Track-Feld-Drift, (2) eine native Decoder-/ANLZ-Variante außerhalb der Fixtures oder (3) eine musikalische Fehlkalibrierung. Frühwarnzeichen sind Cache-Quarantäne-Wachstum, fehlende `finished`-Signale, ein blockierender Recovery-Prozess oder `get_first_downbeat=None` bei bekannten RB-Tracks. Gegenmaßnahmen sind Cache-Version bumpen, Pool-Prozessgrenzen weiter isolieren, den Einzel-Task-Test beibehalten und die reale ANLZ-/Render-Abnahme als Regressionstest ausbauen.

## Open Questions

Keine technischen Open Questions. Eine 10–20-Track-Hörkalibrierung kann optional als Produktentscheidung nachgereicht werden.

## Recommendation

Release-Kandidat ist technisch verifizierbar und gegen reale lokale Audio-/Rekordbox-Daten abgenommen. Eine subjektive Hörsession mit realen Sets bleibt optionale Produktkalibrierung und ist kein offener Repository-Fix.

## Reale Abschlussabnahme 2026-07-26

Der zuvor externe Restpunkt ist mit realen lokalen Daten geschlossen. Ein echter
Rekordbox-Track (Content `254580025`) lieferte aus `ANLZ0000.DAT/PQTZ` roh
`0,0017 s`; Importer und `analyze_track()` uebernahmen exakt diesen Wert mit
`downbeat_confidence=1,0`. Ein 60-s-Uebergangs-Render aus zwei lokalen
Rekordbox-Tracks bestand Peak-, Pegel-, Kanal- und Sample-Integritaetspruefungen.
Eine subjektive Langzeit-Hoersession bleibt optional und ist kein technischer
Repository-Fix.

## Verification Evidence

- Volltest: **1.384 passed**, 26 warnings, **74,18 % Coverage**, Gate 70 %.
- Verify-Suiten: `verify_fixes.py` **14/14**, `verify_wave2.py` **17/17**, `verify_wave4.py` **8/8**.
- E2E: **17/17**, 3 echte AIFF-Dateien, Playlist/Recommendations/Render/Clipping/Loudness/Grid geprüft; Peak 0,955.
- Reale ANLZ-Abnahme: Content `254580025`, `ANLZ0000.DAT/PQTZ`, Rohwert `0,0017 s` = Importerwert; Analyse `downbeat_confidence=1,0`, BPM `138,0`, Camelot `4A`.
- Reale Übergangs-Abnahme: zwei lokale Rekordbox-Tracks, 60 s / 44,1 kHz / Stereo, Peak `0,515`, Mitte-vs.-Anfang `-2,19 dB`, Kanalabweichung `0,06 dB`, finite Samples; **bestanden**.
- `pip check`: keine gebrochenen Anforderungen.
- `compileall`: erfolgreich.
- `git diff --check`: erfolgreich.
- Workflow-Dateien strukturell geprüft; `actionlint` ist lokal nicht installiert.

## Deep Bug-Hunt Addendum - 2026-07-26

Die vertiefte Rekordbox-Prüfung fand eine reale False-Wiring-Gefahr: Die lokale
`master.db` enthält 2.665 Content-Zeilen mit 77 doppelten normalisierten Pfad-
Records. Vorher konnte dadurch der zuletzt gelesene Record BPM/Key/Cues eines
früheren Records still überschreiben; außerdem wurde bei 60 mehrdeutigen
Basenames der erste Treffer verwendet.

Behoben in `hpg_core/rekordbox_importer.py`:

- widersprüchliche exakte Pfad-Records werden als mehrdeutig verworfen;
- ein eindeutig besserer analysierter Record gewinnt gegen einen Record mit
  BPM `0`/fehlender Analyse;
- mehrdeutige Basename-Fallbacks liefern `None` statt falscher Metadaten;
- `get_statistics()` und `get_available_count()` zählen nur eindeutige Pfade.

Regression: `tests/test_rekordbox_importer.py` deckt 62 Tests ab, einschließlich
exakter Pfadkonflikte, analysierter-vs.-unanalysierter Duplikate und mehrdeutiger
verschobener Dateinamen.
