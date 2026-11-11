# HPG Entwicklungs- und Lagebericht

**Stand:** 11.11.2026

**Branch:** `codex/gesamtrefaktorierung`
**GitHub-/CI-Abgleich (11.11.2026, Snapshot direkt vor diesem Berichtupdate):** Lokaler Branch und `origin/codex/gesamtrefaktorierung` standen beide auf `c8ca7558bb74d493e3722138810a25a1e038fd02`; `origin/main` ist Vorfahr. Dieser Statusbericht- und Teststand wurde anschließend auf den Feature-Branch gepusht. Letzter Produktcode-Commit: `604db5542c66774cf71b9766763c099b9ff86c40`; danach folgten Test- und Dokumentationscommits, keine Produktquellenänderung. `gh run list --branch codex/gesamtrefaktorierung` lieferte keine Branch-Runs; `gh pr list --head codex/gesamtrefaktorierung --state open` lieferte kein offenes PR. CI für diesen Feature-Branch ist nicht grün nachgewiesen.

## Kurzstatus

**Fortsetzung 11.11.2026:** CPU-/synthetische Integrationsprüfungen nachgeführt: Hearing-Browser 107/107, Hearing-Panel 42/42, MainWindow 22/22, Hearing-Workflow 32/32, Scoring/Strategien 182/182, Deep-Feature-Runtime 65/65, Native-Reader 36/36, Cache-Migration 8/8 und statische Release-Gates 38/38 bestanden. Zusätzlich bestanden 168 Playlist-/Layouttests, 13 Tabellen-/Detailpaneltests und 16 Hearing-Kartentests mit Exitcode 0. In drei Qt-Läufen erschien `Windows fatal exception: code 0x8001010d`: bei `qtbot.wait(50)`, Drag-Tests und Kartenaufbau im `pytestqt.plugin._process_events`. Alle Assertions bestanden; Ursache bleibt ungeklärt.

**Rangwechsel-Gate:** Neue Regression `tests/test_hearing_end_to_end.py::test_applied_preferences_reorder_visible_mixpoint_ranking` besteht **1/1** (`venv312`, Python 3.12.10, `-n 0 --no-cov`). Persistierte synthetische BPM- und Harmoniegewichte gehen durch den echten MainWindow-Refresh und drehen die tatsächliche Mixpunktreihenfolge von 16/32 auf 32/16. Temporäre Fixturedateien; keine Originalmusik, Audioanalyse oder GPU. Das ergänzt den separaten Fit-/Apply-Integrationsnachweis; vollständige CSV/JSON-Rundreisen und manuelle App-Abnahme bleiben offen.

**Einzel-Fit-App-Pfad:** `tests/test_hearing_calibration.py::test_single_fit_from_app_button_shows_real_draft_without_applying` besteht **1/1** (`venv312`, Python 3.12.10, `-n 0 --no-cov`, 2,08 s). Echter CSV-Fit-Button, `HearingCalibrationWorker`-Spawn, Fitberechnung und Ergebnisdialog; synthetische Zwei-Zeilen-CSV, kein Cache oder Audio. Dialog kennzeichnet Gewichte als nicht übernommen; aktive Präferenzen und Quelldateien bleiben unverändert. Kein vollständiger CSV/JSON-Golden-Master-Rundlauf.

**Vier-Modi-CLI/GUI-Sitzungsparität:** `tests/test_hearing_workflow.py::test_real_internal_producer_artifacts_match_cli_and_native_service` besteht **4/4** (`venv312`, Python 3.12.10, `-n 0 --no-cov`, 3,09 s). Einzel, Kandidaten, Dreinoten und Dramaturgie liefern identische logische Rating-Sessions und Clipzahlen. Der CLI-Pfad publiziert lesbare synthetische WAVs; der native Pfad publiziert strikt gebundene virtuelle Referenzen. Die Dramaturgie prüft die vollständige Acht-Strategien-Matrix. Der Beleg deckt noch keine Golden-Master-Rundreise sämtlicher Fit-/Blindtest- und Export-CSV/JSON-Schemas.

**ComfyUI (Live-Abgleich 11.11.2026):** `FX_0512`–`FX_0516` erfolgreich; `ffprobe` bestätigt H.264, 736×416, 24 fps, 243 Frames und 10,125 s. `FX_0516` hat 2.086.830 Byte. Aktuell läuft `FX_0518` (UUID `404ca812-c32e-4c26-9fa4-07aa0ad7ca81`); Queue 1/0, `film_batch.py` PID 26284 lebt. Batch-Ende nicht festgestellt; Queue unberührt. Frühere FX_0499–FX_0504-Einträge weiter unten sind historische Momentaufnahmen.

**Noch offen:** Vollsuite, aktueller Frozen-Build und vollständige sichtbare App-Abnahme nach Batchende; Originalmusik/native GPU-Prüfung erst nach Freigabe, iGPU bleibt frei. 93 vorbestehende Arbeitsbaumänderungen bleiben geschützt.

Letzte Vollsuite vor dem neuen Playlist-Aktionszustandsfix am 11.11.2026:
**6.679/6.679 bestanden**, Coverage **81,11 %**, Exitcode 0 (`venv312`, Python
3.12.10, `pytest tests/ --tb=short -q -n 2`, Laufzeit 22:51). Der aktuelle
Aktionszustandsfix besteht den gezielten Qt-Test und ist im isolierten Frozen-Build
visuell sowie barrierefrei geprüft. Die vollständige manuelle GUI-/Originalmusik-
Abnahme bleibt offen. Der laufende ComfyUI-Batch bleibt unangetastet.

Aktueller UI-Audit: Der Bericht in `AnalyticsPanel` zeigte noch englische
Überschriften, Messwerte und Empfehlungen; Statuszähler, Tooltips, Exportmeldungen,
Preview und Messdiagnose-Dialog mischten ebenfalls Englisch und Deutsch. Diese
gefundenen sichtbaren Texte sind jetzt konsistent deutsch. Gezielte Qt-Regressionen
decken Qualitätsstufen, Titelzähler, Worker-Status, Timeline, Preview und
Exportmeldungen ab. Synthetische Worker-/UI-Tests ohne Audioanalyse.

Die Sichtprüfung des vorhandenen isolierten Frozen-Builds bestätigte im
Playlist-Leerzustand noch „Track auswählen“ im Detailfeld. Quelltext und
Accessibility-Name verwenden jetzt „Titel auswählen“ bzw.
„Titel- und Übergangsdetails“; `test_erweiterte_spalten_und_leere_details`
besteht **1/1** (`venv312`, Python 3.12.10, pytest 9.1.1, `-n 0 --no-cov`,
0,69 s). Der Frozen-Build selbst stammt von vor diesem letzten Textdelta.

Die Statusleiste transliterierte deutsche Umlaute noch als `ae/ue`; außerdem
waren einzelne Warnhinweise sprachlich gemischt. Statushinweis sowie Pedalboard-,
KI-Server- und Rekordbox-Warntext verwenden jetzt normale deutsche Schreibweise.
End-to-End-Rekordboxwarnung und neue Status-/Tooltip-Regression bestanden
**2/2** (`venv312`, Python 3.12.10, pytest 9.1.1, `-n 0 --no-cov`, 1,13 s).

## Verifizierte Änderungen und Prüfungen
- UI-Lokalisierungsdelta: Statuszähler, Analytics, Timeline, Tooltips und
  Worker-Text wurden vereinheitlicht. Die gezielte Qt-Regression bestand
  **13/13** (`venv312`, Python 3.12.10, pytest 9.1.1, `-n 0 --no-cov`, 1,43 s);
  der ergänzte synthetische Worker-Status-Test bestand **1/1** (0,67 s).
  `git diff --check` ist sauber. Keine Vollsuite, kein Frozen-Build und keine
  Audio-/Originaltrack-Prüfung für dieses Delta.
- Folge-UI-Prüfung: Preview-Beschriftungen/Tooltips und Messdiagnose-Zähler
  wurden ebenfalls lokalisiert. Regressionen für Preview und leeren sowie
  2.500-Titel-Messdialog bestanden **3/3** (`venv312`, Python 3.12.10, pytest
  9.1.1, `-n 0 --no-cov`, 2,37 s gesamt). Ein erster Testlauf hatte einen
  Qt-Eltern-Lebensdauerfehler im neu angelegten Test; nach Korrektur bestand
  der Preview-Test separat. Kein Produktlauf, Frozen-Build oder Audiotest.
- Weitere sichtbare Beschriftungen: Playlist-Details, Sammlungsinventar und
  Hörtestdialog behalten einzelne Fachbegriffe wie „Track“ bei; sie sind im
  DJ-Kontext üblich. Der jetzige Sprachdelta-Scan hat nur die eindeutigen
  englischen Preview-Werte `Out`/`In` und `Track A/B` korrigiert; eine
  vollständige Sichtprüfung aller Dialoge ist weiterhin nicht erfolgt.
- Result-Identität bis zum konkreten UI-Export geprüft: `tests/test_run_lifecycle.py::test_generation_result_reorder_exportiert_dieselbe_occurrence_reihenfolge` besteht **1/1** (`venv312`, Python 3.12.10, pytest 9.1.1, `-n 0 --no-cov`, 0,58 s). Der Test veröffentlicht ein synthetisches `PlaylistGenerationResult`, sortiert anhand der Occurrence-IDs um, klickt den Button des danach aktuellen Panels und liest die tatsächlich geschriebene M3U8-Reihenfolge zurück. Keine Originalaudios oder Modellinferenz; keine musikalische Bewertung.
- Rekordbox-XML-/Preview-Verträge gezielt nachgeprüft: **58/58 Tests bestanden** in `tests/test_rekordbox_xml_exporter.py` und drei GUI-Exportregressionen aus `tests/test_main_workers.py` (`venv312`, Python 3.12.10, `-n 0 --no-cov`, 1,01 s). Dabei zwei überholte englische Preview-Erwartungen an den aktuellen deutschen Dialogtext angepasst. XML-Exporter-Tests stubs pyrekordbox; kein Rekordbox-Liveimport und keine manuelle XML-App-Abnahme.
- Alten Diagnoseverdacht im Paar-Ranking am aktuellen Quellstand geprüft: Ablehnungsgründe werden über den Rankinglauf und `rejection_reasons` bis zum ungeplanten Übergang transportiert; die GUI zeigt den konkreten Grund. Fehlende Klangfarbenmessung erscheint als „unbekannt“ statt als gemessener Kontrast. `tests/test_pair_rejection_diagnostics.py` und `tests/test_transition_labels.py`: **16/16 bestanden** (`venv312`, Python 3.12.10, `-n 0 --no-cov`, 0,52 s). Der damalige Befund ist im aktuellen Code behoben; kein neuer Scoring- oder Diagnose-Fix erforderlich.
- Vollständige Analytics-Panel-Aktionsverdrahtung geprüft: neuer Qt-Regressionstest klickt alle 14 sichtbaren Aktionen (Sammlung, Messdiagnosen und zwölf Hörtestaktionen) und prüft den erreichten `MainWindow`-Handler samt Audit-Parameter. `tests/test_main_window.py::test_quality_panel_actions_reach_mainwindow_handlers` besteht **1/1** (`venv312`, Python 3.12.10, pytest 9.1.1, `-n 0 --no-cov`, 0,64 s). Das verifiziert Button→Signal→Handler im Qt-Test; reale Dialog-/Server-/Audioabläufe bleiben getrennte Abnahmepfade. Wiederholung am aktuellen HEAD: Test erneut **1/1 bestanden** (`venv312`, Python 3.12.10, `-n 0 --no-cov`, 0,47 s).
- Leichtgewichtiger Quellsyntax-Gate am aktuellen Quellstand bestanden: `venv312\Scripts\python.exe -m compileall -q main.py hpg_core tools` (Exitcode 0). Keine GPU-/Audioarbeit; ersetzt weder Vollsuite noch Frozen-Build.
- Abhängigkeits-Vorabcheck am aktuellen `venv312`: `python -m pip check` meldet `No broken requirements found.` Keine Paketpins geändert; CI, Vollsuite und Frozen-Build bleiben getrennte Gates.
- Release-Metadaten abgeglichen: `APP_VERSION`, README-Titel, `installer.iss` `AppVersion`/Dateiname und `version_info.txt` stimmen sämtlich auf `3.7.2` überein. Kein Versionsdrift; der aktuelle Frozen-Build ist weiterhin offen.
- MainWindow-Worker-Lifecycle gezielt geprüft: `tests/test_run_lifecycle.py` **37/37 bestanden** (`venv312`, Python 3.12.10, pytest 9.1.1, `-n 0 --no-cov`, 1,27 s). Abgedeckt: RunState/Cancel, Reihenfolge-Sperre, Worker-Drain und Preview-/Generation-Lifecycle. Keine GPU und keine Originalmusik; kein Ersatz für Vollsuite.
- Playlist-Auswahl/Exportrotation geprüft: `tests/test_playlist_selection.py` **19/19 bestanden** (`venv312`, Python 3.12.10, pytest 9.1.1, `-n 0 --no-cov`, 0,12 s). Abgedeckt: Längenvalidierung, Auswahlrotation, Mitgliedschaftserhalt beim Ranking-Refresh und atomare Historie nur nach erfolgreichem Export. Synthetische Tracks und temporäre Dateien; kein Ersatz für Vollsuite.
- Release-Metadaten-/Build-Gate geprüft: `tests/test_release_metadata.py` **38/38 bestanden** (`venv312`, Python 3.12.10, pytest 9.1.1, `-n 0 --no-cov`, 2,41 s). Abgedeckt: Versionsquellen, Spec-Ressourcen, Qt-Runtime-Ausschluss, Daten-/Source-Fingerprint, Build-Pfadvalidierung und gemeinsame CI-/Installer-Gates. Kein echter PyInstaller-Build oder Installerlauf.
- Installer-GUI-Smoke gehärtet: `.github/scripts/test_installer_runtime.ps1` wartet bis zu 30 s auf ein echtes `MainWindowHandle` mit Fenstertitel; bloßes Weiterleben des Prozesses reicht nicht mehr. PowerShell-Parser meldet **0 Syntaxfehler**. Das bestehende Release-Metadatenmodul besteht nach Ergänzung der Gate-Marker weiter **38/38** (`venv312`, `-n 0 --no-cov`, 2,44 s). Ein realer Installer-/GUI-Lauf bleibt offen.
- Cache-Identitäts-/Migrations-Delta gegen den historischen Plan geprüft: `core_fingerprint` und `get_legacy_cached_core` sind in Analyse und Cache-Leser verdrahtet. Der CPU-only Vertragssatz `tests/test_core_cache_migration.py` plus fünf ausgewählte Identitätsfälle aus `tests/test_cue_service.py` besteht **17/17** (`venv312`, Python 3.12.10, pytest 9.1.1, `-n 0 --no-cov`, 1,30 s). Geprüft: `fresh` umgeht Lesen/Migration/Schreiben; `reuse` migriert nur bei passender Audioquelle, Rekordbox-Herkunft, Kernidentität und Schema; alte Cachezeile bleibt unverändert, normalisierte Pfadschreibweise wird akzeptiert. Temporäre SQLite und synthetische Quelldatei; keine Audioanalyse, GPU oder Originaltrack-Reuse. Die historische Planmeldung „Einbindung offen“ ist überholt; der echte App-Reuse-Nachweis bleibt separat offen.
- Deep-Feature-Laufzeitintegration gegen den historischen Plan geprüft: `deep_feature_runtime.attach` ist an beiden Analyse-/Refresh-Aufrufstellen verdrahtet; `tests/test_deep_feature_runtime.py` besteht **65/65** (`venv312`, Python 3.12.10, pytest 9.1.1, `-n 0 --no-cov`, 0,27 s). Abgedeckt: Stem-Budget, Session-/Pool-Proxies, Quellenbindung, Fallback-Restzeit, Brokerlimit und globaler Haenger-Cap. Synthetische Stat-Dateien und kontrollierte Clients, keine Audio-/Modellinferenz. Die historischen Planpassagen „noch nicht integriert/getestet“ sind für den Vertragstest überholt; der reale Originaltrack-Stem-Timeout ist nicht neu bestätigt und bleibt offen.
- Dokumentations-Delta-Audit: Der Planhinweis zu angeblich englischen Exportfehlern ist am aktuellen `main.py` widerlegt: `_export_m3u8` und `_export_rekordbox_xml` geben bereits deutsche Fehlermeldungen weiter. Die veraltete offene Aufgabe wurde im lokalen Plan korrigiert; kein Produktcode geändert. Ergänzte GUI-Fehlerpfad-Regression `test_mainwindow_export_errors_are_localized`: **2/2 bestanden** (`venv312`, Python 3.12.10, pytest 9.1.1, `-n 0 --no-cov`, 1,00 s); beide Formate erreichen den kritischen Dialog mit lokalisiertem Kontext und Backendfehler. GitHub-Abgleich für HEAD `42526f66`: Remote-Branch identisch; `origin/main` ist Vorfahr (128 Commits Abstand); Combined Status hat keine Checks, es gibt kein offenes PR. Der Installer-Workflow triggert automatisch nur bei `main`-Push/PR nach `main`; CI für diesen Feature-HEAD ist daher unbekannt, nicht grün.
- Delta-Audit: identische doppelte Definition von `test_prepare_portable_rollback_preserves_replaced_foreign_key` aus `tests/test_prepare_dj_blind_test.py` entfernt. Die zweite Definition hatte die erste beim Python-Modulimport überschrieben; ein Rollback-Regressionsfall wird jetzt einmal gesammelt und ausgeführt. Gezielter Test bestanden (1/1; Python 3.12.10, pytest 9.1.1, `-n 0 --no-cov`). `git diff --check` sauber. Noch kein neuer Gesamt-Audit oder Vollsuite.
- Vorhandene Root-EXE zuletzt geschrieben am 04.10.2026; Frozen-Build gegen aktuellen HEAD fehlt. Der isolierte Build vom 11.11. liegt vor der Smoke-Spawn-Friständerung und ersetzt deshalb keinen Build des aktuellen Quellstands. Build bleibt bis nach dem aktiven ComfyUI-GPU-Batch offen.
- Aktuelle Nachprüfung der Hörtest-Matrix: 16 gezielte Tests bestanden (`venv312`, Python 3.12.10, pytest 9.1.1, `-n 0 --no-cov`). Abgedeckt: exakte UI→Producer-Optionsabbildung, Modi Einzel/Kandidaten/Dreinoten/Dramaturgie, wirksame Kandidatenoptionen und portabler Blindtest-Dialog mit realem Worker samt Fehler-/Konfliktpfaden. Synthetische Fixtures; keine GPU und keine Originalmusik. Kein Volltest oder manueller Fit-/Export-Abnahmepfad.
- Zusätzliche Fit-/Export-Regression: Legacy Einzel-CSV-Fit mit echtem Rechenpfad, ohne Cache oder Audiodatei, bestand mit und ohne vorherige `gewichte.json`; der Qt-Ergebnisdialog weist den Entwurf als nicht aktiv übernommen aus und Export erzeugt den Bericht. Echter GUI-Button→M3U8-Exporter schrieb eine Playlistdatei. **3/3 Tests** (`venv312`, Python 3.12.10, pytest 9.1.1, `-n 0 --no-cov`, 1,12 s). Synthetische Zwei-Zeilen-Fixture, keine Ground Truth; kein manueller Fit-/Rekordbox-XML-Abnahmelauf.

- Veraltete Suite-Zahl in der README auf den letzten Vollteststand korrigiert.
  Hörtest-CLI/GUI-Matrix auf Quellcommit `6285970870d41a69c842e2905d3dba53758ea97c`
  nachgeführt; die späteren GUI-Änderungen betreffen nur Playlist-Startzustand
  und Aktionsaktivierung, nicht die dort beschriebenen Hörtest-Verträge.
- Leere Playlist-Aktionen waren aktiv, obwohl die Playlist fehlte. Export ist nun
  bei 0 Tracks deaktiviert, Übergangsprüfung erst ab 2 Tracks aktiv.
  `test_playlist_panel_schaltet_leerzustand_mit_playlistinhalt`: **1 bestanden**
  (`-n 0 --no-cov`, 6,79 s). PyInstaller 6.21.0 Build mit Python 3.12.10:
  `E:\AI\HPG-build-verification-2026-11-11-playlist-actions-6ab75606\dist\HarmonicPlaylistGenerator.exe`,
  SHA-256 `26A6D36FE1B9F506BBEB81807CCF90F9209790EC77C6665F657A812F05700C95`.
  Sichtprüfung im isolierten Profil zeigt den Leerhinweis und deaktivierte Panel-
  Aktionen; Accessibility-Tree bestätigt beide Buttons als disabled. Keine Analyse gestartet.
- Playlist-Exportklick zusätzlich mit einem Qt-MainWindow, einem synthetischen Track
  und echtem M3U8-Exporter durchlaufen: temporäre Datei enthält `#EXTM3U` und den
  Trackpfad. `test_playlist_panel_export_button_writes_m3u8`: **1 bestanden**
  (`-n 0 --no-cov`, 0,74 s). Dies deckt den Button-/Signal-/Speicherpfad ab,
  ersetzt keine manuelle Set-/Fit-/Rekordbox-XML-/Originalmusik-Abnahme.
- Isolierter synthetischer Kandidatensatz mit dem echten `create_set`-Producer
  vorbereitet: ein Paar, zwei Kandidatenclips, sechs Satzdateien unter
  `E:\AI\HPG-build-verification-2026-11-11-manual-hearing-32012e5\hearing-set`;
  Quellhashes unverändert. Am 11.11.2026 im Frozen-GUI über den Satzbrowser
  vollständig geprüft und geöffnet. Accessibility-Tree meldet „Satz geladen
  (kandidaten)“; Analyseherkunft bleibt unbekannt, kein Audit-Nachweis. Beide
  Varianten wurden auf Abruf im RAM gerendert und als 32-Sekunden-Vorschau
  abgespielt. Im schreibenden Dialog speicherte die GUI eine temporäre Note 3
  für `001_k1` in `bewertung.csv`; CSV danach auf den vorher leeren Stand
  zurückgesetzt und verifiziert. Nach erneutem Laden meldet das GUI `0/2`
  Varianten bewertet; „Bewertungen auswerten“ bleibt ohne Noten deaktiviert.
  Der Kandidaten-Fit blieb wegen leerer Bewertungen deaktiviert. Der separate Einzel-CSV-Pfad wurde danach mit einer synthetischen Fixture geprüft; das ist keine Musikbewertung. Für beide GUI-Prüfungen wurden weder Originalaudio noch Analyse verwendet. Der
  Legacy-Browserknopf zeigt für quellenbasierte Sätze den Hinweis, dass er
  vorhandene Hörclips erwartet; Server/Browser wurden nicht gestartet.
  Wiederaufnahme weiterer Modi und Originalmusik-Abnahme bleiben offen.
- Satzbrowser-End-to-End im isolierten Frozen-GUI geprüft: „Sätze / Fortschritt“ mit dem synthetischen Testordner als Wurzel listet genau einen Kandidatensatz, `0/1`, Status `new`. Nach Auswahl wurde „Open“ aktiv; Öffnen lud den Satz und meldete „Satz geladen (kandidaten). Analyseherkunft: unbekannt. Kein Render-/Audit-Nachweis.“ Keine Analyse oder Bewertung gestartet.
- Einzel-CSV-Fit am 11.11.2026 mit isolierter synthetischer Fixture (`E:\AI\HPG-build-verification-2026-11-11-csv-fit-ui`, zwei Bewertungen, keine Audios und kein Cache) im Frozen-GUI ausgeführt. Fitstatus `passed`; Ergebnis 2 Bewertungen (1 gut, 1 nicht gut), Datenlage nicht belastbar. Produktive Übernahme war deaktiviert. Dialog zeigte Datei-Hashes, Build-Fingerprint und Vorschlagsdigest; aktive Gewichte blieben laut Dialog unverändert. Kein Vorschlag wurde übernommen oder gespeichert.
- „Messdiagnosen anzeigen“ am 11.11.2026 im isolierten Frozen-GUI geöffnet: ohne übergebene Tracks meldet die App „Keine analysierten Tracks übergeben. Keine Messdiagnosen verfügbar.“ Beide Tabellen bleiben leer und melden keine Trackauswahl. Dialog danach geschlossen; keine Analyse oder Änderung ausgelöst.
- Hörtest-Bewertung/Remote-Vertrag am 11.11.2026 erneut fokussiert geprüft:
  **323 Tests bestanden** in Ratingspeicher, HTTP-Routen/Range, nativen
  Bewertungskarten, Satzfortsetzung und MainWindow-Serverlebenszyklus. Lauf mit
  `--no-cov`; er belegt diese Gruppen, nicht die vollständige Suite oder reale
  Decoder-/Musikabnahme.
- Blindtest-Vorbereitung/Integritätsprüfung am 11.11.2026 fokussiert geprüft:
  **87 Tests bestanden** für Pfadcontainment, Duplikate, Audioeigenschaften,
  No-overwrite, Schlüsseltrennung, portable Worker-Abbruch-/Rollback-Grenzen
  und native GUI-Weitergabe. Keine Entblindung oder Statistik implementiert.
- Genre-Gate zusätzlich mit dem echten Fitverfahren geprüft:
  `test_zwei_genres_lernen_gegensaetzliche_gewichte_real` besteht. Der Test lässt
  120 synthetische, unabhängige Paare je Genre durch `_fit_kandidaten_genre`
  laufen und reproduziert gegensätzliche Gewichtungen samt realer Gate-Logik.
  Danach schloss `test_real_producer_audit_native_fit_confirm_apply_actual_ranking`
  die durchgehende Kette mit echtem Producer, Audit, Fit, Gate, GUI-Bestätigung,
  Apply und Ranking-Refresh: **1 Test in 251,99 s**. Der Test injiziert keinen
  Fit- oder Gate-Ausgang. Seine 64 synthetischen Paare und 128 Varianten liefern
  keine Musik-Ground-Truth; Originalmusik-Abnahme bleibt offen. Der frühere
  Hinweis auf einen injizierten Apply-E2E-Ausgang ist damit veraltet.
- Fit-Optionsabbildung neu geprüft: **8/8 Dialog-/Workerfälle bestanden**.
  Einzel-Fit reicht Genres weiter; Kandidaten-/Dreinoten-Fit deaktiviert den
  unwirksamen Genrefilter; Replay-Audit deaktiviert den Seed. Artefakt-/Golden-
  Master-Vergleich bleibt ein separates offenes Task-7-Kriterium.
- Erster CLI-/GUI-Publikationsvergleich bestanden (**1/1**): ein deterministischer
  Einzelmodus-Fixture-Producer erzeugt über beide Wrapper bytegleiche CSVs;
  Legacy- und Quellvalidator akzeptieren die Resultate. Der interne Algorithmus
  war dabei absichtlich ersetzt. Das ist ein reiner Wrapper-/Schema-Vertrag;
  der nachfolgende Test ergänzt den Vergleich mit echten internen Produzenten.
- CLI-/native Service-Parität der echten internen Producer am 11.11. ergänzt:
  `test_real_internal_producer_artifacts_match_cli_and_native_service` prüft
  Einzel, Kandidaten, Dreinoten und Dramaturgie; **4/4 bestanden** (`venv312`,
  `-n 0 --no-cov`, 7,50 s). Der native Service lädt und validiert jeden erzeugten
  Quellsatz. Gemeinsame CSV-/JSON-Artefakte stimmen bytegleich überein; beim
  Dramaturgie-Manifest werden nur die absichtlich unterschiedlichen Clip-
  Speicherbindungen auf den gemeinsamen relativen Pfad normalisiert. Cache-
  Trackladen, Kandidaten-/Playlist-Eingaben und WAV-Rendern sind kontrollierte
  synthetische Fixtures. Damit sind Producer-/Wrapperverträge abgedeckt, keine
  echten Cache-/Such-/Scoringalgorithmen, Audio-Renderqualität, Rating-Fortsetzung
  oder musikalische Qualität. Das gesamte Modul `tests/test_hearing_workflow.py`
  bestand danach mit **32/32 Tests** (`-n 0 --no-cov`, 2,06 s).
- Native GUI-Satzfolge nochmals für alle Modi gezielt geprüft:
  `test_native_prepare_load_edit_reopen_source_metadata` bestand für Einzel,
  Kandidaten, Dreinoten und Dramaturgie mit **4/4 in 4,24 s** (`venv312`,
  `-n 0 --no-cov`). Reale Prepare-/Load-Worker, Rating-Speicherung, Dialogschluss
  und erneutes Laden laufen; Render-Preflight und Wiedergabe-Payload sind
  synthetisch, ohne Audio-DSP oder Originalmusik.
- Wiederholung dieser vier Modi am aktuellen HEAD bestand am 11.11. erneut **4/4 in 3,68 s** (`venv312`, Python 3.12.10, pytest 9.1.1, `-n 0 --no-cov`). Die Queue blieb dabei unverändert (FilmX Prompt 73 aktiv, zwei `PBStudio_T007`-Jobs wartend).
- Native Worker-Lifecycle-Ergänzung: Persistenzfehler/-erfolg mit verspätetem Refresh erst nach eigenem Worker-Cleanup sowie Cancel-Reset bei unverändertem aktivem Playlistlauf bestanden **5/5** (`tests/test_hearing_native_integration.py`, `venv312`, Python 3.12.10, `-n 0 --no-cov`, 0,87 s). Synthetische Ergebnisse, keine Präferenzdateien oder Originalmusik geschrieben.
- Read-only-Frischeprüfung der CLI/GUI-Matrix gegen den aktuellen HEAD:
  zwischen ihrem Quellstand `6285970` und HEAD änderte sich in den geprüften
  Matrix-Produktionsdateien nur `hpg_core/hearing_smoke.py`, außerhalb der
  Matrixpfade. Der neuere Producer-Paritätstest ergänzt die Belege, ohne
  Producer-/GUI-Verträge zu ändern. Kein Produktionsdrift in der geprüften
  Hörtest-Matrix gefunden; der getrennte unabhängige Abschluss-Wächter bleibt
  offen.
- Native Veröffentlichung mit den echten internen Producerfunktionen ergänzt
  geprüft: **3/3** für Einzel, Kandidaten und Dreinoten-Kandidaten. Alle Outputs
  werden vom späteren Quellmanifest-Loader eingelesen; Einzel zusätzlich vom
  Legacy-Validator. Analyse-Cache und Kandidatenfindung sind kontrollierte
  Fixtures, Audios werden nicht dekodiert. Das deckt Loader-/Schemaannahme der
  Producer-Ausgaben ab, aber keinen CLI-/GUI-Golden-Master oder Originalmusik.
- Hörtest-Smoke-Ausreißer nachgeprüft: der archivierte Vollsuite-Fehler entstand
  in `_check_parallel_initializer` bei `future.result(timeout=30)`; der isolierte
  Lauf bestand zuvor in 34,24 s Gesamtlaufzeit. Die interne, weiterhin begrenzte
  Spawn-Frist ist auf 60 s erhöht. Der aktuelle synthetische Diagnose-Smoke
  bestand gezielt mit **1/1 in 33,48 s** (`venv312`, `-n 0 --no-cov`). Das
  bestätigt den Einzelpfad, noch nicht das Verhalten unter xdist-Vollsuite-Last;
  dafür bleibt der nächste Vollsuite-Lauf nach dem ComfyUI-Batch erforderlich.
  Nachprüfung am 11.11.2026 nach dem Release-Metadaten-Gate: derselbe echte
  Qt-/Spawn-/RAM-DSP-Smoke bestand erneut **1/1 in 34,54 s** aus einem fremden
  Arbeitsverzeichnis. Der 60-s-Initializer, Worker-Reaping, private Numba-Cache,
  synthetischer Render und abgelehnter CSV-Fit liefen damit erneut grün. Weiterhin
  kein Nachweis unter xdist-Vollsuite-Last, kein Originalaudio und keine GPU-Inferenz.
- Zusätzlicher CLI-/GUI-Paritätsabgleich fand den vorhandenen optionalen
  `Start_Hoertest.bat`-Launcher, der in der ersten Matrixfassung fehlte. Der
  Launcher ist getesteter Kompatibilitätsweg, kein verwaister Starter: seine
  Port-/Prozess-/Fortschrittsverträge bestanden mit **34/34 Tests**. Die Matrix
  enthält nun auch seine Abgrenzung zum nativen Qualitätsbereich.

- Neuester Stand: Satzbrowser filtert vorhandene Sets nach Ordner, Format,
  Fortschritt, Status und Fehlern; eine beim Filtern ausgeblendete Auswahl wird
  gelöscht. Gezielt und in der vollständigen Suite verifiziert. Der native UI-
  Pfad wurde im aktuellen Frozen-Build mit drei isolierten Beispielsätzen
  geprüft: Ordner-, Status- und Fortschrittsfilter funktionieren; beim
  Ausblenden der ausgewählten Zeile wird „Öffnen“ deaktiviert. Kein Satz wurde
  geöffnet, keine Analyse gestartet.
- Playlist-Längenwunsch und Exportrotation am 11.11.2026 im Hauptcheckout
  integriert: `0`/„Alle“ erhält die bisherige Trackliste; Werte 1–1000 wählen
  vor der bestehenden Strategie aus gültigen Tracks ohne Zurücklegen. Tracks
  mit länger zurückliegendem letztem erfolgreichem Export erhalten höheres
  Auswahlgewicht. Eine identische letzte Trackzusammenstellung wird vermieden,
  wenn eine andere Teilmenge möglich ist. Hörtest-Ranking-Refresh behält die
  aktuelle Trackmitgliedschaft. Die lokale Historie wird atomar nur bei
  `ExportReport.status == "success"` aktualisiert; ungültige Historie wird
  nicht überschrieben. Nachweise: 19 Auswahl-/Rotationstests, 6 GUI-/Worker-/
  Settings-Tests und 1 Export-Hook-Test bestanden (`--no-cov`). Volltest, nativer Originaltrack-Lauf und musikalisches Urteil nach dieser Änderung fehlen.
- Neuer isolierter Qt-/Worker-E2E-Nachweis am 11.11.2026: echter Kandidaten-
  Producer, Audit/Fit-Worker, bestätigtes Apply und Ranking-Refresh bestanden;
  **1 Test in 251,99 s**. Die Audiodateien und der Cache liegen in einer
  temporären synthetischen Fixture; Labels sind keine Musik-Ground-Truth und
  Rating-/Bestenwahl werden über die Test-API eingespeist. Separat bestanden
  **130 GUI-, M3U8-, Rekordbox-XML- und Playlistrotations-Tests in 1,30 s**
  (`-n 0 --no-cov`). Das prüft die technische Kette, nicht manuelle Nutzerklicks,
  Originalmusik oder die musikalische Qualität. Vollsuite nach Rotation und vollständige manuelle Set-/Fit-/Exportbedienung bleiben offen.
  Zusätzlich bestanden **143 Browser-/Dialog-/Satzmodus-Preflight- und
  Workflowtests in 8,49 s** (`-n 0 --no-cov`), einschließlich Einzel-,
  Kandidaten- und Dramaturgie-Produktion.
- Mix-Tab-Startzustand im Frozen-Build als UI-Lücke reproduziert: Der vorhandene
  Leerhinweis wurde erst nach `set_recommendations()` gerendert; `MixTipsPanel.init_ui()`
  ruft `_populate()` jetzt initial auf. Regression `test_mix_tips_panel_shows_initial_empty_state`
  und kompletter `tests/test_run_lifecycle.py`-Lauf: **36/36 bestanden** (`-n 0 --no-cov`).
  Der neue Frozen-Build zeigt sichtbar „Noch keine Übergänge vorhanden. Zuerst eine
  Playlist erstellen.“; keine Analyse gestartet.
- Aktueller isolierter Frozen-Build nach Mix-Tab-Fix: Python 3.12.10, PyInstaller
  6.21.0; Build und Frozen-Native-Smoke erfolgreich. EXE:
  `E:\AI\HPG-build-verification-2026-11-11-mix-empty-state-b289e9292dd44d93baff5dfd43cb4d9e\dist\HarmonicPlaylistGenerator.exe`,
  SHA-256 `412A062C3683020F8FE10DB8EE70B217697048D2275B623FE5240A42D5F7675B`.
  Smoke `ok=true`: Imports/Formulare, Spawn-Worker, RAM-Render und isolierte CSV-Fit-Probe;
  Algorithmusfingerprint 117 Dateien, SHA-256
  `591fae4d619aeb696ee706d27a4a31605dfbe0bb570fae47f6dc259bab3b97f5`.
  Der aktuelle Quellfingerprint wurde am 11.11. erneut mit demselben Verfahren
  berechnet: ebenfalls 117 Dateien, SHA-256
  `2ba0636673669ba21fbf8edca2a7656792a03f0c102b2fef18d4dd64f9defbae`.
  Die Abweichung verifiziert, dass dieser Frozen-Build nicht zum aktuellen
  Algorithmusquellstand passt; Neubau bleibt bis Batch-Ende vertagt.
  Drei kurze Qt-Regressionen zum späteren UI-Textstand bestehen am aktuellen
  Quellcode **3/3** (`test_transition_preview_labels_and_tooltips_are_german`,
  `test_empty_input_is_explicit`, `test_advanced_tooltips_use_correct_german_accents`,
  `venv312`, Python 3.12.10, `-n 0 --no-cov`, 0,78 s). Der echte Native-Smoke,
  Vollsuite und Frozen-Neubau bleiben offen.
  Vollsuite nach Rotation sowie vollständige manuelle Set-/Fit-/Export- und
  Originalmusik-Abnahme bleiben offen.
- Nach dem Timeline-Startzustandsfix erneut isoliert gebaut: Python 3.12.10,
  PyInstaller 6.21.0. EXE:
  `E:\AI\HPG-build-verification-2026-11-11-timeline-empty-1dfe5c20c07946b8828db8b50e56fa30\dist\HarmonicPlaylistGenerator.exe`,
  SHA-256 `3894A9827D5537ADA59ECA67F6AB86CE36C65DCDE6EFDE15FBF514FE3CE2F4C3`.
  Im isolierten GUI-Profil gestartet; Timeline zeigte sichtbar und im
  Accessibility-Tree „Keine Playlist vorhanden.“ Keine Analyse gestartet.
  Das Worker-/Timeline-Testmodul bestand mit **214 Tests**, 1 Test war
  abgewählt (Exitcode 0, `-n 0 --no-cov`, 7,27 s).
- Nach dem Playlist-Leerzustandsfix isoliert gebaut: Python 3.12.10,
  PyInstaller 6.21.0; Build erfolgreich. EXE:
  `E:\AI\HPG-build-verification-2026-11-11-playlist-empty-a95512adad7f4d1689e09c2889af9386\dist\HarmonicPlaylistGenerator.exe`,
  SHA-256 `7BA80381972534ABE5FA1828A2E0CF2112F7123F37DF33876BDE2AA026DAADF0`.
  Im isolierten GUI-Profil zeigt der Playlist-Tab den Leerhinweis sichtbar und
  im Accessibility-Tree; Regressionstest plus Vollsuite bestanden. Keine Analyse gestartet.
- Voriger Frozen-Build für den Playlistrotations-Quellstand: Python 3.12.10,
  PyInstaller 6.21.0; Build vollständig erfolgreich. EXE:
  `E:\AI\HPG-build-verification-2026-11-11-playlist-rotation-4fe4a1757cfd4349877bcbd826904fdc\dist\HarmonicPlaylistGenerator.exe`,
  SHA-256 `C0BF60E56B0E976391AC846DF084FC38F51A80FDA50E3A36DDCBFC304AD38573`.
  Frozen-Native-Smoke: `ok=true`, Imports/Formulare, Spawn-Worker, RAM-Render
  (16.000 Frames, 8 kHz Stereo) und isolierte CSV-Fit-Probe bestanden.
  Algorithmusfingerprint: 117 Dateien, SHA-256
  `591fae4d619aeb696ee706d27a4a31605dfbe0bb570fae47f6dc259bab3b97f5`.
  Der normale GUI-Start wurde mit leerem isoliertem Profil sichtbar und
  responsiv geprüft; Playlistlänge zeigte 0/„Alle“. Keine Analyse oder
  Playlistgenerierung gestartet. Vollsuite nach Rotation und manuelle
  Satz-/Fit-/Exportbedienung bleiben offen.
- Manueller GUI-Pfad des vorherigen Satzbrowser-Frozen-Builds (SHA-256
  `54109AC5DC376B877912839BD310D6BB55E030910B85ECA619F2CCF7BEB7CD9D`) am
  11.11.2026 mit ausschließlich synthetischen Audios und isoliertem AppData:
  vorbereiteten Einzelsatz geöffnet, Vorschau im RAM gerendert/abgespielt,
  Testnote 3 in `bewertung.csv` gespeichert, Dialog geschlossen und Satz erneut
  geöffnet. Beim erneuten Öffnen zeigte die App `Bewertet: 1/1` und
  `Vorhandene Noten geladen`; damit ist Save-/Reload-Verhalten für diese
  synthetische Einzelvariante manuell bestätigt. Die Testnote wurde danach nur
  im isolierten Temp-Artefakt entfernt; die synthetische Paarzeile bleibt mit leerer Bewertung erhalten.
  Kein Originalaudio, keine Analyse, kein Fit, kein Export und keine
  musikalische Qualitätsbewertung. Vollständige GUI-Abnahme bleibt offen.
- Vollsuite nach Satzbrowser-Änderung: **6.644/6.644 bestanden**, Coverage
  **81,02 %**, Exitcode 0. Isolierter PyInstaller-Build mit `HPG.spec`
  abgeschlossen; Native-Smoke `ok=true` (Imports/Formulare, Spawn/Worker-
  Cleanup, 16.000 RAM-Audioframes bei 8 kHz Stereo, CSV-Fit-Probe). EXE:
  `E:\AI\HPG-build-verification-2026-11-11-set-browser-search\dist\HarmonicPlaylistGenerator.exe`,
  SHA-256 `54109AC5DC376B877912839BD310D6BB55E030910B85ECA619F2CCF7BEB7CD9D`.
  Smoke belegt Paketierung und synthetische Verträge, keine vollständige
  GUI- oder Musikabnahme.

- Vollsuite nach dem Dialog-/Fit-Fix erneut ausgeführt: **6.643/6.643 bestanden**,
  Coverage **81,01 %**, Exitcode 0 (`venv312\Scripts\python.exe -m pytest
  tests/ --tb=short -q`). Dabei erschien einmal `Windows fatal exception:
  code 0x8001010d` in einem xdist-Worker; der Worker wurde ersetzt, alle Tests
  liefen zu Ende. Das ist ein verbliebenes Stabilitätssignal, keine rote
  Pytest-Prüfung.
- Fehler im angenommenen Hörtest-Ergebnis behoben: Einzel-Fit-Vorschläge haben
  `candidate_report=None`; `_show_hearing_proposal` las danach bisher trotzdem
  `candidate_report["dreinoten"]` und konnte den Apply-Dialog abbrechen. Die
  Dreinoten-Bestätigung wird nun nur bei vorhandenem Bericht geprüft.
  Apply-/GUI-Integration: **119 Tests bestanden**; Suite oben grün.
- Der Repository-Audit vom 10.11. fand keinen bestätigten Produktionscode-Bug.
  Er prüfte statische Bereiche und gezielte Testgruppen, nicht die gesamte
  Laufzeit. Details und Grenzen stehen in
  [AUDITBERICHT_2026-11-10.md](AUDITBERICHT_2026-11-10.md).
- Beim aktuellen Codeabgleich war `HearingWorkflowWorker` nur noch eine tote
  GUI-Implementierung: Kein Produktionspfad erzeugte diese Workerklasse; sie
  startete alte Hörtest-CLI-Prozesse. Die aktiven nativen Worker decken den
  aktuellen GUI-Pfad ab. Die Altklasse und ihre nur darauf bezogenen Tests
  wurden entfernt; ein veralteter Monkeypatch wurde ebenfalls gelöscht.
- `tests/test_main_window.py` und
  `tests/test_hearing_native_integration.py` bestanden nach der Bereinigung
  mit dem Python-3.12-Projektinterpreter. `git diff --check` war sauber.
- Bei der Bewertungsfortschreibung fand sich eine Abweichung zum Satzinventar:
  interne Symlinks auf Metadaten bestanden `_metadata`'s Elternpfadtest, obwohl
  die Inventarsuche Links ablehnt. Die Bewertungsroutine lehnt jetzt Symlinks
  und Junctions explizit ab. `test_internal_metadata_symlink_rejected_before_rating_write`
  bestand isoliert. Das gesamte Modul meldete **205 bestanden**, aber der
  Befehl endete wegen des projektweiten Coverage-Gates mit Exitcode 1
  (8,74 % statt mindestens 70 %); daraus folgt kein grüner Modul-Gesamtlauf.
- Der Full-VERITAS-Audit vom 11.11. prüfte `hpg_core`, GUI, Tools, Tests,
  Build/Release und aktuelle Produktdokumente in drei unabhängigen Kontexten
  (Seeds 7112027–7112029). Alle drei Pass-Dateien und der Nullbefund-Verifikator
  waren valide; der Merge ergab **0 Findings**. Der Vorgänger-Audit vom 10.11.
  hatte einen einzelnen, nicht reproduzierten Dokumentationsbefund. Sync-Dry-Run
  zeigte nur die allowlist-gesteuerten generierten Ziele, keine Waisen oder
  Konflikte; Apply endete mit `sync_difference_count=0` und `complete=true`.
  Pass 2 meldete gezielte Testgruppen mit **303** und **350** bestandenen Tests;
  deren Einzelbefehle sind nicht im Laufartefakt protokolliert. Kein Volltest,
  GUI-/Originalmusik-/Rekordbox-Ablauf oder Build wurde in diesem Audit
  ausgeführt. Optionale Scanner Bandit, mypy, radon, ruff und vulture fehlten.
  Der Laufbericht und die Passdateien liegen unter
  `E:\AI\HPG-veritas-full-2026-11-11`.
- Der letzte Volltestlauf vor zwei zusätzlichen Race-Regressionstests sammelte 6.600 Tests: **6.599 bestanden, 1 fehlgeschlagen**
  in 768,35 Sekunden; Coverage 81,03 %. Fehler:
  `tests/test_hearing_smoke.py::test_source_smoke_actual_qt_spawn_ram_dsp_from_unrelated_directory`.
  Genau dieser Test bestand isoliert in 33,32 Sekunden; Vollsuite deshalb nicht als
  grün werten. Nach den zusätzlichen Export-No-Clobber-/Rollback-Tests bestanden 11 fokussierte
  Blindtest-Tests. Der konfigurierte Lauf schließt `slow`-Tests aus. Automatisierte
  Tests ersetzen keine menschliche Bedien- oder Klangabnahme.
- Die Dialogbereinigung entfernte unverbundene Cache-/Zielpfadfelder, einen
  ungenutzten Dateibrowser und ein nicht angeschlossenes Mehrordnerfeld.
  `managed_config` bindet den Hörtest an genau einen gewählten Musikordner und
  leitet private Cache- und Satzziele ab. Danach blieb der fokussierte Dialoglauf
  mit **26 Tests** grün; der nachfolgende Gesamtlauf umfasst diese Änderung.
- Die aktuelle Frozen-EXE startete auch im normalen GUI-Modus. Bibliotheks-
  und Qualitätsbereich sowie der Hörtest-Erzeugungsdialog wurden sichtbar
  geöffnet. Der Dialog wurde abgebrochen, bevor Analyse oder Satz-Erzeugung
  startete. Die temporären Cache-/Logpfade lagen im Build-Scratch. Trotz
  APPDATA/LOCALAPPDATA-Overrides erschien ein gespeicherter Musikordner im
  Dialog; die Quelle dieser Voreinstellung wurde nicht separat geprüft.
- Zusätzliche GUI-Sichtprüfung: Qualitätsbereich und Hörtest-Erzeugungsdialog
  öffneten sich; die erweiterten Kandidatenoptionen waren sichtbar. Der Dialog
  wurde ohne Satzstart abgebrochen. Das laufende Fenster gehörte jedoch zur
  älteren Smoke-EXE
  `E:\AI\HPG-build-verification-2026-11-11-portable-blind-check\dist\HarmonicPlaylistGenerator.exe`
  (SHA-256 `B8D36D86A74524658CDEA09394B9948DEC024EC7910DB3C7677C8C69D4D9083F`),
  nicht zum zuletzt geprüften Build `portable-blind-final2` (SHA-256
  `2626E2ECC32DF8F60836EA7C79246B5E49FB6E849482B3A89114A21ECCA1F67A`). Diese
  Bedienprobe bestätigt daher nicht den aktuellen Build. Testabdeckung der
  Zuordnung liegt außerdem in `test_prepare_form_maps_modes_and_disables_ineffective_fields`,
  `test_prepare_form_exposes_all_effective_candidate_options` und
  `test_namespace_has_exact_ui_to_parser_mapping`.
- Live-Desktopinventar am 11.11.2026 zeigt zwei offene HPG-Fenster aus älteren
  Scratch-EXEs (`candidate-report-fix` und `portable-blind-check`). Der aktuelle
  Satzbrowser-Build liegt separat unter
  `E:\AI\HPG-build-verification-2026-11-11-set-browser-search`; sein SHA-256
  stimmt mit `54109AC5DC376B877912839BD310D6BB55E030910B85ECA619F2CCF7BEB7CD9D`
  überein, war im Desktopinventar aber nicht geöffnet. Daher bleibt die
  Bedienabnahme am aktuellen Build offen. Die älteren Fenster wurden nicht
  verändert.
- Nach dem Exportpfad wurde mit Python 3.12.10 und PyInstaller 6.21.0 erneut
  isoliert unter `E:\AI\HPG-build-verification-2026-11-11-portable-blind-final2` gebaut.
  Bestehende Buildziele und Root-EXE lagen außerhalb des Wirkpfads. Die EXE
  bestand `--hpg-native-smoke` mit Exitcode 0 und `ok=true`; der PyInstaller-
  Abhängigkeitsgraph enthält `tools.prepare_dj_blind_test`. EXE-SHA256:
  `2626E2ECC32DF8F60836EA7C79246B5E49FB6E849482B3A89114A21ECCA1F67A`.
  Der Native-Smoke endete mit `ok=true`, Exitcode 0; Spawn, RAM-Render und CSV-Fit-Probe bestanden. Der xref enthält `tools.prepare_dj_blind_test`. PyInstaller meldete fehlendes optionales `tbb12.dll`. Das belegt Packaging/Smoke, nicht den manuellen Exportklick oder Klang.
- Nach dem Vorschlagsdialog-Fix wurde Commit `bcf2fb70` erneut isoliert gebaut:
  Scratch `E:\AI\HPG-build-verification-2026-11-11-candidate-report-fix`;
  EXE `dist\HarmonicPlaylistGenerator.exe`, SHA-256
  `C9D9E4A5CE9148AAB8054D0CDF873D4693EDB68FB8EB1B48604F242E2659B790`.
  Der Native-Smoke-Report meldet `ok=true`: native Imports/Formulare,
  isolierter Spawn-/Cleanup-Worker, RAM-Render (16.000 Frames, 8 kHz, Stereo)
  und CSV-Fit-Probe ohne Audiodatei bestanden. Scope ist Packaging/Qt/Prozess/DSP,
  keine musikalische oder vollständige App-Abnahme. PyInstaller meldete das
  optionale `tbb12.dll` als fehlend.
- Commit `c507efa` enthält ausschließlich `main.py` und die beiden genannten
  Testdateien und wurde zu GitHub gepusht.
- Commit `0bba81e` ergänzt im Qualitätsbereich eine native Auswahl zwischen
  bisherigen lokalen A/B-Referenzen und portablem Export vorhandener
  Übergangsclips. Der portable Pfad ruft `tools.prepare_dj_blind_test.prepare`
  direkt in einem Worker auf. Er kopiert keine Originaltracks, erzeugt neutrale
  WAV-Namen und hält den Zuordnungsschlüssel als getrennte CSV-Datei. Start- und
  Fehlerpfad sind mit 143 fokussierten Tests geprüft.

- Beim Fortsetzen wurde ein Fehler im Legacy-Einzel-CSV-Fit gefunden: doppelte oder inkonsistente Paar-IDs konnten die Snapshot-Grenze passieren; der Fit-Merge konnte doppelte Bewertungen überschreiben. `hpg_core.hearing_calibration.validate_set` validiert jetzt CSV-Schema, IDs, Noten, Faktoren und 1:1-Bindung, ohne Clipdateien zu traversieren. `tests/test_hearing_calibration.py -k csv_single`: **30 bestanden**. Kein Volltest nach dieser Änderung. Commit `f5b45a8a` enthält Fix, Regressionstests, Plan-Korrektur und VERITAS-Wissenssync.
- Nächste geprüfte GUI-Lücke: Der Kandidaten-Fit-Service verwarf `ergebnis`, Genregewichte, Schema-Rangfolge und Zählwerte aus `CandidateFitResult`; angezeigt wurde damit nicht der vollständige tatsächliche Fitbericht. Der gebundene Vorschlag transportiert nun den kompletten strukturierten Report aus demselben RAM-Fit. Der Qt-Ergebnisdialog zeigt zusätzlich eine Genreübersicht mit Freigabestatus/-grund, Train-/Holdout-Größe, Holdout-Treffer und Baseline, AUC, identifizierbaren Merkmalen, Konfidenzintervallen, neuen Gewichten und Schema-Rang; der vollständige JSON-Bericht bleibt enthalten. Vorschlagsdigest, Report-Schema und Konsistenz mit Diagnose/Gate-Updates werden validiert. Drei gezielte Tests bestanden: echter Kandidaten-Audit/Fit, Digest-Manipulation und Qt-Berichtsanzeige. Kein Volltest oder Build nach dieser Änderung. Apply-/Ranking-Refresh-Kette zusätzlich mit fünf gezielten MainWindow-Regressionen geprüft: Persistenz steuert Refresh, Cache-Reset, neuer Scoring-Context/Kandidatensnapshot, und Fehler wird nicht als Erfolg gemeldet. Kein Volltest. Einzel-Fit-Ergebnis zeigt jetzt Bewertungen/Klassen, Belastbarkeit samt Grund, aktive Merkmale, Streuungen, Koeffizienten und 95-%-Bootstrapintervalle; es ist sichtbar als nicht aktiv übernommener Entwurf markiert. Drei gezielte Tests für Kandidaten- und Einzelansicht bestanden. Dreinoten-Pilot zeigt Deep-Feature-Abblation nun je Gruppe lesbar (Status/Grund, Train-/Holdout-Clips und Cluster, Baseline-/erweiterte AUC, Delta; keine Wirkung auf Produkt-Score); GUI-Test bestanden. Separater Auditdialog ergänzt: Replay bestanden/Fit nicht ausgeführt, Receipt sowie Datei-/Quell-/Cache-/Build-Bindung und Digest sichtbar; Close-sicher. Neun gezielte Audit-/Lifecycle-Tests bestanden. Zusätzlich tatsächlichen Dialog-Abschluss und Modal-Cleanup mit eigenem GUI-Test geprüft.

## Verbleibende HPG-Arbeit

- Dreinoten-Fit war im GUI-Start zwar schemaerkennbar, aber die Erkennung wurde nicht an den Optionsdialog gegeben und die zweite Apply-Bestätigung hatte keinen Ja-Pfad-Test. Dialog zeigt jetzt explizit Dreinoten-Pilot; Fit bleibt unverändert ein Vorschlag. Übernahme startet nur nach bestandenem Gate, erster Dialogfreigabe und separater zweiter Ja-Bestätigung; Nein lässt Präferenzen unberührt. Optionsmatrix bestätigt: Seed bleibt im Fit aktiv, Audit deaktiviert Seed, Genre gilt nur für Einzel-Fit. GUI-Modustext und deaktivierte irrelevante Optionen geprüft. `tests/test_hearing_browser_integration.py` plus `tests/test_hearing_calibration.py`: **10 gezielte Tests bestanden** (11.11.2026). Kein Volltest, Build oder manueller App-Lauf.
- Apply-E2E ergänzt: Ja und Nein laufen mit demselben digest-validierten, gatebestückten Vorschlag. Ja startet den echten Apply-Worker, schreibt atomar in eine temporäre Preference-Datei, lädt Gewichte und Schema-Rangfolge über den echten Preference-Loader und löst Ranking-Refresh aus. Ein absichtlicher Schreibfehler meldet `persisted=False`/`effective_reload=False`. Zusammen mit Dreinoten-/Optionsregressionen: **12 gezielte Tests bestanden**. Das statistische Genre-Gate wurde in dieser Fixture deterministisch eingesetzt; ein realer Datensatz mit statistisch tatsächlich bestandenem Gate bleibt offen. Kein Volltest, Build oder manueller App-Lauf.
- Ergänzung dazu: Der spätere Test `test_real_producer_audit_native_fit_confirm_apply_actual_ranking` führt inzwischen auch den echten statistischen Fit bis zum bestätigten Apply und Ranking-Refresh aus (64 synthetische Paare; 1 bestanden in 251,99 s). Die 12 Tests oben beschreiben weiterhin die isolierten Ja-/Nein-/Fehlerpfade; deren deterministisch eingesetzter Vorschlag ist kein Gegenbeleg und bleibt als eigener Test nützlich. Der echte Fit liefert nur synthetische Evidenz, keine Musik-Ground-Truth.
- Folgeprüfung am 11.11.: Bestätigungsdialoge (Ja/Nein), Dreinoten-Workerstart, Fit-Modusoptionen, gated Apply mit Preference-Persistenz/Reload/Ranking-Refresh sowie isolierter Schreibfehlerpfad bestanden **14/14** (`tests/test_hearing_browser_integration.py`, `venv312`, Python 3.12.10, `-n 0 --no-cov`, 4,58 s). Synthetische GUI-/Workerprüfung; kein Originalaudio und keine musikalische Ground-Truth.
- Erzeugungsoptionen jetzt durchgehend GUI→`PrepareConfig`→Producer-Namespace für Einzel, Kandidaten, Dreinoten und Dramaturgie geprüft. Tests decken wirksame Werte, Defaultwerte und deaktivierte Modusfelder ab; Service-Rangevalidierung zusätzlich geprüft: **22 Tests bestanden**, anschließend nochmals **8 GUI-Modus-/Verdrahtungstests bestanden**. Gesamte CLI/GUI-Matrix, Volltest, Build und manueller App-Lauf bleiben offen.
- Auswahlprofil-Lücke geschlossen: JSON-Dateiauswahl im Dialog; vor Konfiguration/Analyse/Workerstart werden Zweckmarker, Merkmale, Mittelwerte/Streuungen, drei Modellziele/Koeffizienten und Tracklisten validiert. Der Kandidatenproducer nutzt denselben Validator erneut. Gültige Profilanwendung plus Ablehnung fehlerhafter Profile ohne Konfiguration geprüft. `tests/test_hearing_panel.py`: **14 gezielte Tests bestanden**. Gesamte CLI/GUI-Matrix, Volltest, Build und manueller App-Lauf bleiben offen.
- Unabhängiger gezielter Folgecheck der Erzeugungsverdrahtung am aktuellen Quellstand: vier GUI-Modi, effektive Kandidatenoptionen und exaktes UI→Parser-Mapping bestanden **6/6** (`venv312`, Python 3.12.10, `-n 0 --no-cov`, 0,17 s). Damit sind diese drei geprüften Verträge bestätigt; die vollständige CLI/GUI-Matrix, Vollsuite, Build und Bedienabnahme bleiben offen.
- Native Hörtest-Module und GUI-Aktionen sind im Code vorhanden. Vollständige
  Zuordnung aller Werkzeugoptionen zu GUI-Aktionen und manueller App-Ablauf sind
  nicht abgenommen. Portable CSV-Sessions lassen sich gegen die getrennte
  Schlüsseldatei prüfen. Exportkopie bricht an Hash- und Audio-Chunk-Checkpoints ab;
  vor Veröffentlichung wird Staging entfernt. Schlüssel erhält atomare No-Clobber-
  Publikation.
- Der erhaltene Umsetzungsplan vom 27.09.2026 wurde nach Hashvergleich aus dem
  gesicherten Branch-Commit nach
  [2026-09-27-hoertest-werkzeuge-in-app.md](superpowers/plans/2026-09-27-hoertest-werkzeuge-in-app.md)
  zurückgeholt. Seine ursprünglichen Checkboxen und Matrix sind nicht gegen
  den heutigen Code synchronisiert; er bleibt Anforderungssammlung, keine
  aktuelle Fertigstellungsanzeige. Einzel-Quellsätze werden durch
  `hpg_core.hearing_sources.load_source_session`/`_single_metadata` geprüft;
  Legacy-Einzel-CSV zusätzlich durch `hpg_core.hearing_calibration.validate_set`.
  Der falsche Smoke-Schalter wurde auf den realen `--hpg-native-smoke`-Einstieg
  korrigiert.
- Originalmusik-/manuelle Bewertungsabnahme bleibt offen. Das optionale
  Threading-Backend wurde im Projektinterpreter geprüft: NumPy meldet
  OpenBLAS `pthreads` mit 16 Threads; HPG-Quellen, Spec und Requirements
  referenzieren TBB nicht. Die beim PyInstaller-Lauf fehlende optionale
  `tbb12.dll` ist damit kein belegter HPG-Laufzeitbedarf. Die geladenen
  Threadpools der Frozen-EXE wurden nicht separat inventarisiert.
- Der alte Deep-Sky-Provenienzfehler ist im vorbereiteten Artefaktstand vom
  01.11. behoben: `dict_to_track` lädt `hpg-deepsky-fresh-20261101-8ceqex1v/track.json`
  mit aktuellem Code; native Kandidatenherkunft bleibt bei
  `downbeat_confidence=0` ausdrücklich getrennt. Die bestehende Qt-App-Probe
  W ↔ Deep Sky ergab trotzdem **0 freigegebene Übergänge** (`planned=0`,
  `recommendations=0`, Qualität 0 %). Der gespeicherte Diagnosebericht zeigt
  bei 125/127 BPM (2-BPM-Grenze unverändert) in beiden Richtungen
  beste lokale Scores 0,513 bzw. 0,662, beide unter dem Score-Gatewert 0,70.
  Für die jeweiligen besten 8-Bar-Kandidaten bestehen beide geprüften
  `stable_model_window`-Fenster; die 16-Bar-Varianten fallen teilweise am
  `native_beat_gap`-Gate durch. Keine Variante erreicht dennoch den
  Score-Mindestwert. Die aktuelle Cachedatei `hpg_cache_v183.db` enthält
  read-only geprüft nur den Versionsmarker und keine Trackdatensätze; der ältere
  v46-Cache ist kein aktueller Analysebeleg. Damit ist in den geprüften
  Bestandsdaten kein verifizierter Alternativpartner vorhanden. Kein Gate wurde
  gelockert und keine Originalaudio-Datei neu analysiert oder verändert. Die technische
  Provenienzreparatur ist damit bestätigt, eine brauchbare W/Deep-Sky-Mischung
  oder musikalische Abnahme nicht.
- Bereits vorher vorhandene lokale Änderungen an Agenten-/Skill-Spiegeln,
  Dokumentation und Playlist-Längenspezifikation wurden nicht in die obigen
  gezielten Commits aufgenommen und bleiben im Arbeitsbaum erhalten.

## ComfyUI-Batchstatus

- Der lokale Server antwortet mit ComfyUI `0.45.2` und erkennt die AMD Radeon
  RX 7800 XT. Modelle und Referenzbilder für den vorbereiteten H3-Workflow
  wurden lokal geprüft; die zwei Referenzbilder wurden hashgeprüft in den
  ComfyUI-Eingabeordner kopiert.
- Ein bereits laufender FilmX-Auftrag `FX_0431` wurde erfolgreich beendet.
  Die Datei `E:\03_Video_&_Medien\Film_x_batch\FX_0431_00001_.mp4` wurde von
  ComfyUI als erfolgreich gemeldet und mit `ffprobe` als H.264, 736×416,
  24 fps, 243 Frames und 10,125 Sekunden bestätigt.
- Letzte bestätigte Dateizählung: **527 MP4-Dateien**. Auftrag `FX_0460` (Prompt-ID `29`,
  UUID `676d873b-1edb-45a5-8a56-1a778b6f9e3c`) wurde erfolgreich abgeschlossen;
  `ffprobe` bestätigt H.264, 736×416, 24 fps, 243 Frames und 10,125 Sekunden
  für `FX_0460_00001_.mp4`. Auftrag `FX_0461` läuft (Prompt-ID `30`, UUID
  `dcb2a262-6c59-4d4a-8e00-be8a7a0eee14`), Queue hat 0 wartende Aufträge.
  Live-Queue am 11.11.2026 zeigt Prompt-ID `42` (UUID
  `805d4d33-05d5-4c9a-9023-851c8cecdf14`) aktiv und 0 wartende Aufträge.
  Promptverlauf und Ausgabedatei sind noch nicht bestätigt. Auftrag und
  Batchproducer blieben unangetastet.
  Folgender Live-Poll am 11.11.2026: Prompt-ID `43`, UUID
  `24d90852-cd71-4d86-9fc9-9d7dcc94a932`, läuft mit Ausgabepräfix
  `Film_x_batch/FX_0474`; Queue hat 0 wartende Aufträge. Der History-Endpunkt
  liefert während des laufenden Auftrags noch keinen Eintrag. Kein neuer Prompt
  wurde eingereiht.
  Prompt-ID `51`, UUID `94e16fa1-ff24-4699-8bfe-d43d7a30bfc0`, Ausgabe
  `Film_x_batch/FX_0482` ist seit dem vorigen Poll abgeschlossen; die Datei
  `E:\03_Video_&_Medien\Film_x_batch\FX_0482_00001_.mp4` liegt vor.
  `ffprobe` bestätigt H.264, 736×416, 24 fps, 243 Frames und 10,125 Sekunden.
  Aktueller Live-Poll: Prompt-ID `52`, UUID
  `58504f56-8bcd-452e-b1db-b8c5f843a14e`, Präfix `Film_x_batch/FX_0483`,
  1 laufend, 0 wartend; History und Zieldatei für 0483 noch nicht vorhanden.
  Producer blieb unangetastet; kein Auftrag eingereiht, geändert oder abgebrochen.
  Nächster Live-Poll: Prompt 52 abgeschlossen. History und
  `FX_0483_00001_.mp4` bestätigen H.264, 736×416, 24 fps, 243 Frames,
  10,125 Sekunden. Der Producer hat anschließend Prompt 53 (UUID
  `2317eeec-4883-4498-a4aa-ffdd550b1327`, Präfix `Film_x_batch/FX_0484`)
  gestartet; Queue: 1 laufend, 0 wartend. Keine Queue- oder Produceränderung.
  Prompt 53 wurde danach abgeschlossen; `FX_0484_00001_.mp4` wurde per `ffprobe` als H.264, 736×416, 24 fps, 243 Frames und 10,125 Sekunden bestätigt. Anschließend startete der Producer Prompt 54 (UUID `45db9fc5-ea21-4067-96a1-33e9d2c64bea`, Präfix `Film_x_batch/FX_0485`). Live-Poll 11.11.2026 17:05 UTC: Producer-PID 10456 aktiv, `rendert`, 484/558 fertig, Prompt 54 läuft, 1 laufend und 0 wartend. Kein zusätzlicher Prompt wurde eingereiht.
  Folge-Poll 11.11.2026 17:11:30 +01:00: Prompt 54/`FX_0485` abgeschlossen; `FX_0485_00001_.mp4` (1.266.834 Bytes) liegt vor. `ffprobe` bestätigt H.264, 736×416, 24 fps, 243 Frames und 10,125 Sekunden. Prompt 55 läuft: UUID `7e3b88f4-5c6e-448b-b3df-a483a54b5cd6`, Präfix `Film_x_batch/FX_0486`; Producer-PID 10456 aktiv, 485/558 fertig, Queue 1 laufend/0 wartend, Heartbeat 17:11:29. Kein zusätzlicher Prompt eingereiht.
  Folge-Poll 11.11.2026 17:20 +01:00: Prompt 55/`FX_0486` ist in der ComfyUI-History erfolgreich abgeschlossen. `FX_0486_00001_.mp4` (1.517.764 Bytes) liegt vor; `ffprobe` bestätigt H.264, 736×416, 24 fps, 243 Frames und 10,125 Sekunden. Prompt 56 läuft mit UUID `dde5a945-30ad-4d8b-a65f-71b769dac2a0` und Präfix `Film_x_batch/FX_0487`; Producer-PID 10456 aktiv, Queue 1 laufend/0 wartend. Kein zusätzlicher Prompt eingereiht.
  Folge-Poll 11.11.2026 17:33 +01:00: Prompt 56/`FX_0487` ist in der History erfolgreich abgeschlossen. `FX_0487_00001_.mp4` (264.855 Bytes) liegt vor; `ffprobe` bestätigt H.264, 736×416, 24 fps, 243 Frames und 10,125 Sekunden. Prompt 57 läuft mit UUID `2b215237-d6bc-43e4-a311-a5971481dc4c` und Präfix `Film_x_batch/FX_0488`; Producer-PID 10456 (`film_batch.py`) aktiv, Queue 1 laufend/0 wartend. Kein zusätzlicher Prompt eingereiht.
  Folge-Poll danach: `FX_0488_00001_.mp4` (2.194.175 Bytes) ist vorhanden; `ffprobe` bestätigt H.264, 736×416, 24 fps, 243 Frames und 10,125 Sekunden. Prompt 58 läuft mit UUID `da9c0372-d76a-494d-8a0b-57c0fbcfbe48`, Präfix `Film_x_batch/FX_0489`; Producer-PID 10456 aktiv, Queue 1 laufend/0 wartend. Keine Queue- oder Produceränderung.
  Folge-Poll danach: Prompt 58/`FX_0489` abgeschlossen; `FX_0489_00001_.mp4` (3.770.778 Bytes) liegt vor, `ffprobe` bestätigt H.264, 736×416, 24 fps, 243 Frames und 10,125 Sekunden. Prompt 59 läuft mit UUID `e5172546-6fd9-425e-9dda-c54c86a8ddc5`, Präfix `Film_x_batch/FX_0490`; Producer-PID 10456 aktiv, Queue 1 laufend/0 wartend. Keine Queue- oder Produceränderung.
  Letzter Live-Poll: Prompt 59/`FX_0490` weiterhin aktiv, Queue 1 laufend/0 wartend; Zieldatei noch nicht vorhanden. Producer-PID 10456 lebt. Keine HPG-Analyse oder Queue-Aktion gestartet.
  Frühere Ausgaben `FX_0436` bis `FX_0438` bestätigte `ffprobe` ebenfalls als
  H.264, 736×416, 24 fps, 243 Frames und 10,125 Sekunden.
- Der separate Vier-Prompt-Auftrag `H3_Clip_11` bis `H3_Clip_14` wurde vom
  Batchskript sicher abgewiesen, bevor ein Prompt gesendet wurde, weil dieser
  bestehende Producer die Queue belegt. Dieser zusätzliche H3-Lauf ist noch
  nicht ausgeführt; der laufende FilmX-Batch bleibt unberührt. Die Datei `prompts_h3_clips_11_14.json` wurde im Ordner Colab-ComfyUI gefunden. H3 bleibt bis zum Ende des laufenden FilmX-Producers zurückgestellt.

- Live-Poll danach: Producer-PID 10456 lebt weiter. ComfyUI meldet Prompt 60, UUID `537e8032-5083-4ccd-871b-180486ee0c7c`, Queue 1 laufend/0 wartend. Die History enthält noch keinen Abschluss; `FX_0491` ist nicht als fertige Datei bestätigt. Kein Queue-Eingriff.
- Folgepoll: derselbe Prompt 60 und PID 10456 weiterhin aktiv; keine History-Abschlussmeldung und keine fertige `FX_0491`-Datei. HPG-Arbeit blieb CPU-/Datei-isoliert, keine GPU- oder Originalmusik-Analyse gestartet.
- Neuer Live-Poll: Prompt 60/UUID `537e8032-5083-4ccd-871b-180486ee0c7c` ist erfolgreich abgeschlossen. `E:\03_Video_&_Medien\Film_x_batch\FX_0491_00001_.mp4` liegt mit 2.608.249 Byte vor. ComfyUI-History meldet 736×416, 24 fps, 243 Frames, 10,125 s; FFmpeg liest H.264 High/AVC1 und Containerdauer 10,13 s.
- Folgeauftrag: Prompt 61, UUID `f58ec805-d9fe-4ccb-82b5-b0e3d49937f3`, Präfix `Film_x_batch/FX_0492`, läuft; Producer-PID 10456 lebt, Queue 1 laufend/0 wartend. Kein Eingriff oder zusätzlicher Prompt.
- Folgepoll: Prompt 61/UUID `f58ec805-d9fe-4ccb-82b5-b0e3d49937f3` ist erfolgreich abgeschlossen. `E:\03_Video_&_Medien\Film_x_batch\FX_0492_00001_.mp4` liegt mit 2.475.858 Byte vor. History: 736×416, 24 fps, 243 Frames, 10,125 s; FFmpeg: H.264 High/AVC1, 24 fps, 10,13 s.
- Aktiver Folgeprompt 62/UUID `2979c237-f19f-406b-b947-e0b0ac3d5dda` verwendet erneut `Film_x_batch/FX_0492`; Queue 1 laufend/0 wartend, Producer-PID 10456 aktiv. Für Prompt 62 ist noch keine History und keine zweite Datei sichtbar. Doppeltes Präfix als ungeklärt notiert; keine Queue-Aktion.
- Folgepoll: Prompt 62 läuft weiter; Queue nun 1 laufend/2 wartend. Wartende IDs 63/UUID `22ef2101-2f00-4472-a4f7-6214ef16b5aa` und 64/UUID `5ceba7ee-ec6d-409a-8320-f595e9298f8b`; ihre Präfixe sind aus der verfügbaren Queue-Antwort nicht aufgelöst. Producer bleibt unangetastet.
- Live-Poll am 11.11.2026: Prompt 64/UUID `5ceba7ee-ec6d-409a-8320-f595e9298f8b` läuft; Prompt 65/UUID `a97fbddd-1d44-4a1a-bbf6-491c49498aa4` wartet. Queue 1 laufend/1 wartend. Producer und Warteschlange unverändert gelassen.
- Folgepoll: Prompt 62/UUID `2979c237-f19f-406b-b947-e0b0ac3d5dda` ist erfolgreich abgeschlossen und als `FX_0492_00002_.mp4` gespeichert; damit ist das zuvor doppelte Präfix durch getrennte Dateinummern aufgelöst. Beide Dateien `FX_0492_00001_.mp4` und `_00002_.mp4` wurden mit `ffprobe` als H.264, 736×416, 24 fps, 243 Frames und 10,125 s bestätigt. Aktueller Live-Stand: Prompt 65/UUID `a97fbddd-1d44-4a1a-bbf6-491c49498aa4` läuft, Queue 1/0. Kein Eingriff.
- Folgepoll: Prompt 65/UUID `a97fbddd-1d44-4a1a-bbf6-491c49498aa4` erfolgreich beendet; dritte Ausgabe desselben Präfixes `FX_0492_00003_.mp4` (3.262.669 Byte). `ffprobe`: H.264, 736×416, 24 fps, 243 Frames, 10,125 s. Damit erzeugten die drei Prompts mit Präfix `FX_0492` eindeutige Dateinummern 00001–00003. Prompt 66/UUID `fa05ce9b-d9bb-43a7-aa6a-69990a303fb7`, Präfix `Film_x_batch/FX_0493`, läuft; Queue 1/0. Producer und Queue unangetastet.
- Folgepoll 11.11.2026: Prompt 66 erfolgreich abgeschlossen; History nennt `FX_0493_00001_.mp4`, H.264-Ausgabe 736×416, 24 fps, 243 Frames, 10,125 s. Producer-PID 10456 lebt; Prompt 67/UUID `89bc932c-7282-47e4-9eed-28d22d0ae392`, Präfix `Film_x_batch/FX_0494`, läuft, Queue 1/0. Keine Queue-Änderung.
- Folgepoll 11.11.2026: Prompt 67 erfolgreich abgeschlossen; History nennt `FX_0494_00001_.mp4`, Video 736×416, 24 fps, 243 Frames, 10,125 s. Producer-PID 10456 lebt; Prompt 68/UUID `cea766e1-dcf5-48cc-a399-b4aa12a76e3e`, Präfix `Film_x_batch/FX_0495`, läuft, Queue 1/0. Keine Queue-Änderung.
## Erledigte GUI-Startzustandsprüfung

### Nachprüfung GUI-Startzustände

- Beim manuellen Start des isolierten Builds war die Timeline-Ansicht vollständig
  leer, obwohl `TimelinePanel.set_timeline([], [])` bereits den korrekten Text
  „Keine Playlist vorhanden.“ setzt. Ursache: Beim Erzeugen des Panels wurde
  `set_timeline` noch nicht aufgerufen. Der Startzustand ist nun direkt im
  schreibgeschützten Textfeld vorbelegt.
- Regressionstest `test_timeline_panel_zeigt_leerzustand_beim_start` und
  bestehender Timeline-Renderingstest waren in **214 bestandenen Tests** des
  Worker-/Timeline-Testmoduls enthalten (`venv312`, `-n 0 --no-cov`). Ein erster Aufruf mit globalem Python fand
  `librosa` nicht; der korrigierte Aufruf nutzte die Projektumgebung.
- Der Qualitäts-Tab zeigt beim Start das Camelot-Rad, seine Hörtest-Aktionen
  und den erklärenden Text.
- Der Playlist-Tab hatte beim Start eine leere Tabelle ohne Erklärung. Er zeigt
  nun „Noch keine Playlist vorhanden. Erstelle zuerst eine Playlist in der
  Bibliothek.“; beim Setzen von Tracks schaltet die Ansicht auf die Tabelle und
  beim Leeren zurück. Regression `test_playlist_panel_schaltet_leerzustand_mit_playlistinhalt`
  bestanden. Der neue Frozen-Build bestätigt sichtbare und barrierefreie Darstellung;
  keine Analyse gestartet.
- Zusätzliche sichtbare Prüfung desselben isolierten Frozen-Builds am 11.11.:
  Playlist zeigt den Leerhinweis, Übergänge „Noch keine Übergänge vorhanden.
  Zuerst eine Playlist erstellen.“, Zeitlinie „Keine Playlist vorhanden.“;
  Qualität zeigt Camelot-Rad und Hörtest-Aktionen. Keine Tracks geladen,
  keine Analyse gestartet und keine Quelldatei verändert. Das ist eine Prüfung
  der leeren Startzustände, keine Abnahme des produktiven Playlist-/Fit-/Exportpfads.
- Der Set-Erstellungsdialog wurde read-only geöffnet: Satztyp `Kandidaten`,
  Original-Musikordner `F:\`. Der Dialog wurde abgebrochen. Sein OK startet im
  Code erst eine frische Analyse dieses Ordners; deshalb keine Produktiv-Analyse
  oder Set-Erstellung ohne iGPU-Freigabe. Read-only Abgleich der
  Satzvorbereitungsmatrix am HEAD `4c9301e`: `HearingPrepareDialog.values`,
  `_producer_namespace` und CLI-Parser stimmen für Modusabbildung und
  aktivierte/deaktivierte Optionen überein; relevante Produktivdateien sind
  seit dem in der Matrix gepinnten Quellcommit unverändert. Kein Code-Delta
  gefunden. Unabhängiger Dateidrift-Check bis HEAD `ff1d1393` bestätigt für
  die Matrix-Produktivpfade seit `6285970` weiterhin keine Änderungen; geändert
  wurden nur `tests/test_hearing_workflow.py` und `tests/test_prepare_dj_blind_test.py`.
  Fit-/Export-/Restmatrix- und Gesamt-Abnahme bleiben offen.

## Nächste Schritte

1. FilmX-Queue nicht unterbrechen. Live-Poll am 11.11.2026: `FX_0516`
   (UUID `6a769380-4248-4c91-b491-02d422588931`) läuft; Queue 1/0,
   `film_batch.py`-PID 26284 lebt. `FX_0515` ist erfolgreich und per `ffprobe`
   geprüft (H.264, 736×416, 24 fps, 243 Frames, 10,125 s). Batch-Ende erst
   annehmen, wenn der Producer beendet ist und die Queue leer bleibt. Fremde
   Queue-Jobs nicht verändern.
2. Nach Ende des gesamten ComfyUI-Batches die Vollsuite gegen den dann
   aktuellen HEAD ausführen. Letzter dokumentierter Volltest vor den jüngsten
   Änderungen: 6.679/6.679 Tests, 81,11 % Coverage. Prüfen, ob die auf
   60 Sekunden verlängerte Smoke-Spawn-Frist den dokumentierten xdist-Timeout
   beseitigt.
3. Danach einen isolierten Frozen-Build vom aktuellen HEAD erstellen und
   genau diesen Build für die noch offene sichtbare GUI-Abnahme verwenden.
   Fit-, Export- und weitere Modi bleiben bis zu dieser Abnahme offen.
4. Originalmusik- und native GPU-Prüfungen erst nach Batchende und nur nach
   der vereinbarten iGPU-/Analysefreigabe durchführen. Die iGPU bleibt frei.
   Keine Musik- oder Produktivcache-Dateien verschieben oder überschreiben.

## UI-Sprachkorrektur 11.11.2026

- Im sichtbaren Bereich `AdvancedParametersWidget` wurden 26 deutsche
  Beschriftungs- und Tooltip-Texte mit ASCII-Umschriften auf korrekte Umlaute
  umgestellt; die KI-Statuszeile heißt nun „KI: noch nicht geprüft“ vor der
  Initialisierung. Im tatsächlichen Widget-Startzustand wechselt sie korrekt zu
  „KI deaktiviert (deterministischer Kernlauf)“.
- Weitere noch sichtbare ASCII-Umschriften in Genre-/Kandidatengewicht-
  Tooltips und Statusmeldungen korrigiert; einschließlich der Statusmeldung
  „ungültig“ und des Hinweises auf den nächsten Lauf.
- A/B-Integritätsbutton mit echtem Worker, getrenntem Schlüssel und synthetischer portabler CSV-Session nachgeprüft: gültig, ungültig, Abbruch und Schließen bestehen **4/4** (`tests/test_hearing_browser_integration.py::test_blind_check_button_slow_actual_worker_no_modal_or_state_change`, `venv312`, Python 3.12.10, `-n 0 --no-cov`, 1,06 s). Read-only; keine Ratings/Statistik, Originalaudio oder Queue-Aktionen.
- Neuer Qt-Regressionstest
  `tests/test_transition_weight_ui.py`: **12/12 bestanden** mit
  Python 3.12.10 (`venv312`, `-n 0 --no-cov`). Kein Vollsuite-Lauf und kein
  Frozen-Build; beides bleibt nach dem ComfyUI-Batch eingeplant.
- Prompt 73 / `FX_0498` ist nicht mehr in der Queue; `FX_0498_00001_.mp4`
  (3.036.269 Bytes) ist per `ffprobe` als H.264, 736×416, 24 fps, 243 Frames,
  10,125 s bestätigt. Die History war beim Poll bereits leer. Prompt 74 ist
  nicht mehr gelistet. Prompt 76 / UUID
  `faad791c-1432-4256-be04-ab53b54a3b72`, Präfix `Film_x_batch/FX_0499`,
  läuft; Queue 1/0, Producer-PID 10456 lebt. History und Ausgabedatei waren
  beim letzten Poll noch nicht vorhanden. Keine Queue-Aktion vorgenommen.

## Aktuelle Fortsetzung: Hearing-Panel und Queue

- Hearing-Panel Playback-/Render-Gates isoliert erneut geprüft: **6/6 bestanden** (`test_native_memory_playback_retains_buffer_and_releases_on_reject`, `test_navigation_away_and_back_rejects_stale_render`, `test_native_spec_rating_requires_current_successful_render`, `test_native_spec_render_error_never_writes_negative_rating`, `test_spec_path_cannot_bypass_ram_render`, `test_group_best_choice_requires_all_rendered_and_error_revokes_it`; Python 3.12.10, `venv312`, `-n 0 --no-cov`, 0,53 s). Synthetische Qt-Verträge zu Buffer-Lebensdauer, veraltetem Render, Rating-Gates, Fehlerbehandlung und Gruppenwahl; keine Originalaudioanalyse.
- Queue unmittelbar nach dem Test per ComfyUI-API geprüft: Prompt 76 / UUID `faad791c-1432-4256-be04-ab53b54a3b72`, Präfix `Film_x_batch/FX_0499`, läuft; 1 aktiv, 0 wartend. Kein Queue-Job verändert.
- Berichtdatei war im `HEAD` bereits versioniert und ohne lokale Änderung; 93 andere bestehende Änderungen bleiben unangetastet.
- Kandidaten-Fit→Apply-E2E anschließend gezielt erneut geprüft: **3/3 bestanden** (`test_gated_candidate_fit_apply_persists_and_refreshes_ranking_end_to_end` mit beiden Parametervarianten sowie `test_apply_worker_reports_isolated_preference_write_failure`; Python 3.12.10, `venv312`, `-n 0 --no-cov`, 4,93 s). Verifiziert: Ja/Nein-Pfade, persistierte Präferenzen und Ranking-Refresh sowie isolierte Schreibfehler-Rückmeldung. Synthetische Qt-Fixtures, kein Originalaudio.
- Native-Reader-Vertrag am aktuellen Quellstand vollständig gezielt geprüft: **36/36 bestanden** (`tests/test_native_reader_selection.py`, Python 3.12.10, `venv312`, `-n 0 --no-cov`, 0,53 s). Abgedeckt: ALAC/AAC-Metadatenrouting, Modusauswahl, Provenienzbindung, kein stiller Fallback bei erzwungenem Native-Reader, WAV-Fallback und Zeitbasis. Fixtures/Mocks; kein Originalaudio und keine Modellinferenz.
- Gesamte Cache-Migrations-Regression am aktuellen Quellstand: **8/8 bestanden** (`tests/test_core_cache_migration.py`, Python 3.12.10, `venv312`, `-n 0 --no-cov`, 1,20 s). Fresh umgeht Lookup/Migration, Reuse migriert nur bei passender Quelle/Rekordbox/Kernidentität/Schema; alte Zeilen bleiben erhalten und Pfadschreibweise wird normalisiert. Synthetische WAV-/SQLite-Fixtures; kein Originaltrack-Reuse oder Audio-Cache-Lauf.
- Deep-Feature-Laufzeitvertrag am aktuellen Quellstand vollständig erneut geprüft: **65/65 bestanden** (`tests/test_deep_feature_runtime.py`, Python 3.12.10, `venv312`, `-n 0 --no-cov`, 0,37 s). Abgedeckt: Stem-Budgetgrenzen, Quellenbindung, kurzlebige Session-Proxies, Fallback-Restzeit, Broker-/Trackdeadline und Cleanup. Kontrollierte Clients/Fixtures; keine Modellinferenz, GPU oder Originalaudio.
- Statische Release-/Installer-/CI-Metadaten-Gates erneut geprüft: **38/38 bestanden** (`tests/test_release_metadata.py`, Python 3.12.10, `venv312`, `-n 0 --no-cov`, 2,47 s). Verifiziert: Versionsquellen, PyInstaller-Spec-Verträge, build-path allowlist, CI-Gates und Release-Manifestregeln. Kein echter PyInstaller-, Installer- oder GUI-Lauf.
- Hearing-Workflow-Integration erneut vollständig geprüft: **32/32 bestanden** (`tests/test_hearing_workflow.py`, Python 3.12.10, `venv312`, `-n 0 --no-cov`, 2,93 s). CLI-/Native-Artefaktparität, Einzel-/Kandidaten-/Dramaturgiemodi, UI→Parser-Mapping, Konfigurationsvalidierung und Abbruch-/Publikationsgrenzen mit synthetischen Quellen; keine Originalmusik.
- Hearing-Browser-Integrationsmodul vollständig geprüft: **107/107 bestanden** (`tests/test_hearing_browser_integration.py`, Python 3.12.10, `venv312`, `-n 0 --no-cov`, 8,03 s). Blindtest-Worker/Discovery, Shutdown-/Cancel-/Publikationsgrenzen, Fit-Modal, Apply-Persistenz und Schreibfehlerpfade mit synthetischen Daten. Kein Originalaudio und keine GPU.
- Hearing-Panel-Modul vollständig geprüft: **42/42 bestanden** (`tests/test_hearing_panel.py`, Python 3.12.10, `venv312`, `-n 0 --no-cov`, 1,37 s). Dialogoptionen/Modi, Auswahlprofilvalidierung, Browser, RAM-Playback, Rating-Gates und persistierte Session-Wiederöffnung mit synthetischen Daten. Keine Originalaudio-Abnahme.
- MainWindow-Hörtest-/Fit-Integrationsmodul vollständig geprüft: **22/22 bestanden** (`tests/test_main_window.py`, Python 3.12.10, `venv312`, `-n 0 --no-cov`, 1,01 s). Sichtbare deutsche Navigation, Action→Handler-Verdrahtung, Vorprüfungen, Workerwahl, Persistenz→Ranking-Refresh und Fehlerstatus; synthetische Qt-Fixtures.

## GitHub-Liveabgleich nach Fortsetzung

- Remote-Refs am 11.11.2026 direkt gegen GitHub gelesen und `origin/main` aktualisiert: `main` (`95a7edbe75c1af466090585ea68f7bf206388f08`) ist Vorfahr des gepushten Feature-HEAD `857441ccdac416f8ae18f9ae419fef51414dcf12`; Feature-Branch **176 Commits voraus**, `main` **0 voraus**. `gh run list --branch codex/gesamtrefaktorierung` und `gh pr list --head codex/gesamtrefaktorierung --state all` lieferten keine Einträge. Branch-CI bleibt unbekannt/nicht grün.
- UI-/Playlist-Ergebnisverträge gezielt geprüft: **168/168 Tests bestanden**, Exitcode 0 (`tests/test_mix_tips_layout.py` und `tests/test_playlist_generation_result.py`, Python 3.12.10, `venv312`, `-n 0 --no-cov`, 2,53 s). Der erste Layouttest bestand, während Pytest-Qt beim `qtbot.wait(50)` zusätzlich `Windows fatal exception: code 0x8001010d` mit Stack in `pytestqt/qtbot.py::wait` ausgab. Ursache unbekannt; deshalb kein störungsfreier Qt-Lauf behauptet. Mixkartenlayout, Plan-/Ergebnisverträge, Kandidaten und Abbruchpfade geprüft; synthetische Daten, keine Audioanalyse.
- Queue-Fortschritt seit dem vorherigen Poll: Prompt 76 / `FX_0499` ist in der ComfyUI-History erfolgreich abgeschlossen. Ausgabe `E:\03_Video_&_Medien\Film_x_batch\FX_0499_00001_.mp4` liegt mit 2.025.148 Byte vor; `ffprobe` bestätigt H.264, 736×416, 24 fps, 243 Frames und 10,125 s. Folgeprompt 77 / UUID `6719e24f-8155-458c-801e-6b2cdf00de7c`, Präfix `Film_x_batch/FX_0500`, läuft; Queue 1/0. Producer-/Queue-Aktion unterblieb.
- Playlist-Scoring- und Strategieverträge vollständig geprüft: **182/182 bestanden** (`tests/test_scoring_contract.py` und `tests/test_playlist_strategies.py`, Python 3.12.10, `venv312`, `-n 0 --no-cov`, 5,45 s). Einheitlicher Qualitäts-/Empfehlungsvertrag, alle acht Strategien und Aliasnamen, Parametervalidierung, Energieverlauf und Track-Erhalt mit synthetischen Fixtures; keine musikalische Ground-Truth-Bewertung.
- Exportverträge vollständig erneut geprüft: **92/92 bestanden** (`tests/test_exporters.py` und `tests/test_rekordbox_xml_exporter.py`, Python 3.12.10, `venv312`, `-n 0 --no-cov`, 0,86 s). M3U8-Injektion/Pfade, Rekordbox-XML/Cue-Punkte, Plan-/Kandidatenbindung und Fehlerbehandlung in temporären Fixtures. Kein Live-Rekordbox-Import.

## Read-only Altlastenprüfung: entfernte Agentenspiegel

- Referenzsuche über README, Doku, GitHub-Workflows, `.agents`, `main.py`, `hpg_core`, `tools` und `tests`: keine aktive Produktcode-, Build- oder CI-Verdrahtung an `.claude/`-/`.codex/`-Agentenspiegel gefunden. Treffer liegen in datierten Cleanup-/Audit-/Übergabedokumenten, Cleanup-Manifesten, Inventartests und `.agents`-Installationshinweisen. `docs/PROJECT_KNOWLEDGE.md` nennt `.agents/` ausdrücklich als kanonischen Bestand und ordnet historische Übergabebefehle als nicht aktuell ein. Die 93 bereits gelöschten/geänderten Arbeitsbaumdateien bleiben unberührt.
- Read-only Repo-Inventartest besteht **3/3** (`tests/test_repo_inventory.py`, Python 3.12.10, `venv312`, `-n 0 --no-cov`, 0,37 s): nur echte Agentenpaare werden als Spiegel klassifiziert; ignorierte Altdateien werden gefunden, ohne Dateien oder Symlinks zu verändern. Stützt den Verweisbefund; keine Spiegel wiederhergestellt.
- Read-only-Nachprüfung des Qt-Hinweises: Microsoft ordnet `0x8001010d` als `RPC_E_CANTCALLOUT_ININPUTSYNCCALL` ein: ausgehender COM-Aufruf während eines eingabesynchronen Aufrufs ([Microsoft COM-Fehlercodes](https://learn.microsoft.com/en-us/windows/win32/com/com-error-codes-3)). Der Hinweis erschien bei `qtbot.wait(50)` und beim Pytest-Qt-Eventpump; beide Testprozesse liefen mit Exitcode 0 weiter. Die Quellsuche fand keine direkte COM-/ActiveX-Integration in `main.py` oder `hpg_core`; Treffer waren reguläre `QDialog.exec()`-Aufrufe und ein separater `QEventLoop` in `hearing_smoke.py`. Auslöser und Aufrufer bleiben unbekannt; kein Produktfehler belegt.
- Produktions-/Testcode nach `TODO`, `FIXME`, `XXX`, `NotImplementedError` durchsucht: keine offenen Marker. Der einzige `pass`-Treffer in `main.py` fängt gezielt `RuntimeError` ab, wenn ein Qt-Worker-C++-Objekt bereits via `deleteLater()` zerstört wurde; Kommentar und Generation-Counter belegen defensive Lifecycle-Behandlung, kein toter Code.
- Folgepoll: Prompt 77 / `FX_0500` erfolgreich abgeschlossen. `E:\03_Video_&_Medien\Film_x_batch\FX_0500_00001_.mp4` liegt mit 1.980.063 Byte vor; `ffprobe` bestätigt H.264, 736×416, 24 fps, 243 Frames und 10,125 s. Prompt 78 / UUID `f2877b56-4f1a-43fc-9a8e-ed60bef19c54`, Präfix `Film_x_batch/FX_0501`, läuft; Queue 1/0, Producer-PID 10456 lebt.
- MainWindow-Kandidatenwechsel-/Rollbackpfade gezielt geprüft: **10/10 bestanden** (`tests/test_main_workers.py`, zehn ausgewählte Cases, Python 3.12.10, `venv312`, `-n 0 --no-cov`, 1,35 s). Ergebnis-Key-Snapshot und Rebuild, Playlist-Mitgliedschaft beim Ranking-Refresh, Sperre während Audio-Lauf sowie atomarer Rollback bei Berechnungs-, Verteilungs- und Preference-Fehlern; kontrollierte Fixtures.

## Dokumentationslink-Audit

- Read-only-Linkcheck für 45 lokale Markdown-Links in README, `docs/` und `specs/` fand einen defekten relativen README-Link in `docs/superpowers/plans/2026-09-27-hoertest-werkzeuge-in-app.md`. Pfad von `../../README.md` auf `../../../README.md` korrigiert; erneuter Linkcheck: **45 geprüft, 0 fehlend**. Historischer Planinhalt blieb sonst unverändert.
- Vollständiger Markdown-Linkcheck nach Beseitigung der toten `AGENTS.md`-Verweise: **183 Dateien, 57 lokale Links, 0 fehlende Ziele**. `OPENCLAW_HPG_SETUP.md` und `PRODUCTION_STATUS.md` verweisen nun auf das aktive `docs/PROJECT_KNOWLEDGE.md`; historische Inhaltspassagen sonst bewahrt.
- Folgepoll: Prompt 78 / `FX_0501` erfolgreich abgeschlossen. `E:\03_Video_&_Medien\Film_x_batch\FX_0501_00001_.mp4` liegt mit 1.973.519 Byte vor; `ffprobe` bestätigt H.264, 736×416, 24 fps, 243 Frames und 10,125 s. Prompt 79 / UUID `15139be3-cc17-44a2-885c-56c2cc8e86a1`, Präfix `Film_x_batch/FX_0502`, läuft; Queue 1/0, Producer-PID 10456 lebt.
- Hearing-Karten-/Rating-Integration vollständig geprüft: **16/16 bestanden** (`tests/test_hearing_panel_cards.py`, Python 3.12.10, `venv312`, `-n 0 --no-cov`, 2,24 s). Synthetisches WAV und Qt-Fixtures belegen Notenskalen, card-spezifische Schreibsperren, Renderfehler-Entzug, Navigation ohne Fake-Saves, veraltete Callbacks, Seek-/Progress-Signale und sichtbare Auswahl. Keine DSP-/Originalaudioqualität. Der erste Test meldete denselben Windows-HRESULT im Pytest-Qt-Eventpump; Prozess und Assertions liefen erfolgreich weiter.
- RAM-gebundene Übergangsbewertung vollständig gezielt geprüft: **3/3 bestanden** (`tests/test_transition_rating_ram.py`, Python 3.12.10, `venv312`, `-n 0 --no-cov`, 0,59 s). Preview-Bytes erreichen Dialog ohne temporäre Audiodatei; Playerfehler sperrt Rating; persistierte Metadaten öffnen erneut und verwerfen geänderte Quelle. Synthetische Bytes/temporäre Metadaten, keine Originalmusik.
- Launcher-/Probe-Verträge gezielt vollständig geprüft: **66/66 bestanden** (`tests/test_hoertest_launcher.py`, `tests/test_ai_launcher.py`, `tests/test_probe_launcher.py`; Python 3.12.10, `venv312`, `-n 0 --no-cov`, 1,26 s). Abgedeckt: eigener Serverprozess/Port und Browserbereitschaft/-fehler, CSV-/Bewertungsschemas, Provider-Auswahl und Cancel ohne impliziten Download, eindeutige Probe-Logs und korrekt quotierter Skriptpfad. Server/Prozesse gemockt; keine Live-Provider-/GPU-Abnahme.

## ComfyUI-Fortschritt nach Prompt 79

- ComfyUI-History meldet Prompt 79 / UUID `15139be3-cc17-44a2-885c-56c2cc8e86a1` erfolgreich. Ausgabe `E:\03_Video_&_Medien\Film_x_batch\FX_0502_00001_.mp4` liegt mit 2.471.871 Byte vor; `ffprobe` bestätigt H.264, 736×416, 24 fps, 243 Frames und 10,125 s.
- Prompt 80 / UUID `644d430c-0dbf-446d-8f62-4fb5a8fdf156`, Präfix `Film_x_batch/FX_0503`, ist aktiv; Queue 1/0. Producer-PID 10456 lebt. Keine Queue-Aktion vorgenommen.

## ComfyUI-Fortschritt nach Prompt 80

- ComfyUI-History meldet Prompt 80 / UUID `644d430c-0dbf-446d-8f62-4fb5a8fdf156` erfolgreich. Ausgabe `E:\03_Video_&_Medien\Film_x_batch\FX_0503_00001_.mp4` liegt mit 2.567.714 Byte vor; `ffprobe` bestätigt H.264, 736×416, 24 fps, 243 Frames und 10,125 s.
- Prompt 81 / UUID `d2fe4670-d775-400a-8970-240546e3f066`, Präfix `Film_x_batch/FX_0504`, ist aktiv; Queue 1/0, Producer-PID 10456 lebt. Keine Queue-Aktion vorgenommen.

## Einzel-Fit-Gap geschlossen, Gesamt-Abnahme offen

- Die App-Einzel-Fit-Kette wurde vom sichtbaren Button bis zum Ergebnisdialog mit dem echten Worker und isolierter CSV geprüft: **1/1 bestanden**. Der Fit erzeugt einen Vorschlag, schreibt keine aktiven Kandidatenpräferenzen und verändert keine Quelldatei. Beleg: `tests/test_hearing_calibration.py::test_single_fit_from_app_button_shows_real_draft_without_applying`.
- Prompt 81 / UUID `d2fe4670-d775-400a-8970-240546e3f066`, Präfix `Film_x_batch/FX_0504`, war beim Queue-Poll aktiv; Queue 1/0, Producer-PID 10456 lebt. Keine Queue-Aktion vorgenommen.

## Vier-Modi-Sitzungsparität nachgeführt

- CLI- und native App-Sätze wurden für Einzel, Kandidaten, Dreinoten und Dramaturgie über die jeweiligen realen Loader eingelesen; die normalisierten logischen Rating-Sessions stimmen in allen vier Varianten überein. Kandidaten- und Dramaturgie-Manifeste werden durch ihre strikten Loader validiert; die Dramaturgie-Fixture enthält alle acht Strategien. **4/4 bestanden**, synthetische Quelldateien und kontrollierte Producer, keine Audioanalyse/GPU. Vollständige Rundreisen aller Fit-, Blindtest- und Export-Schemas bleiben offen.

## Vertragsprüfungen und Git-/Batch-Stand der damaligen Momentaufnahme

- `tests/test_prepare_dj_blind_test.py`: **9/9 bestanden**; Session-/Schlüsseltrennung, No-clobber, Reihenfolge, Pfadvalidierung, Hashbindung sowie Abbruch-/Rollback. Synthetische temporäre Dateien, keine Originalmusik.
- Fit-Artefakte: **2/2 bestanden** (`test_export_valid_native_receipt_and_canonical_binding_roundtrip`, `test_export_new_report_is_no_clobber`); gültiger Bericht wird exportiert, erneut gelesen und validiert; bestehendes Ziel bleibt unangetastet. GUI-Button-Rundreise bleibt ungeprüft.
- GUI-Exporttest-Probe wurde nach zwei fehlgeschlagenen Fixture-Aufrufen entfernt. Verifizierte Voraussetzung: `compute_proposal` verlangt `HPG_CANDIDATE_PREFERENCES_FILE` gleich `<operation_root>\\child_preferences.json`; der Pfad muss vor dem Fit fehlen. Das ist die Child-Präferenzisolation, kein nachgewiesener Produktfehler.
- Zum Zeitpunkt dieser Momentaufnahme zeigte der ComfyUI-Poll Präfix `Film_x_batch/FX_0505`, Queue 1 aktiv / 0 wartend; Prompt-ID `d07ad550-1972-45ab-b37d-ff38863cd593`, Producer-PID 10456 lebte. Keine Queue-Aktion vorgenommen.
- Zum damaligen Snapshot stimmten Repo-HEAD und GitHub-Branch `codex/gesamtrefaktorierung` auf `7fbafed931e1a5733312c83164cfb233443a5002` überein. 93 lokale Arbeitsänderungen blieben unangetastet. Vollsuite, Frozen-Build und GUI-Abnahme waren zu diesem Zeitpunkt noch offen.

## Release-Abstand nach dem Folgebericht

- Read-only-Vergleich des vorhandenen Scratch-Build-Ausgangs `6ab75606f2d9d2f3761b46f950f0d63bba3517d6` mit App-Quellstand `a44c7b40acdd6225564895259e4070a26bd3dd96`: seit dem Build änderten sich `main.py`, `hpg_core/app_workers.py`, `hpg_core/hearing_smoke.py` und `hpg_core/measurement_panel.py` (unter anderem 126/122 Zeilen in `main.py`). Der alte Scratch-Build ist damit kein Frozen-Nachweis für den aktuellen App-Quellstand. Aktueller Isolated-Build und GUI-Abnahme bleiben nach Ende des aktiven ComfyUI-Batches erforderlich.
- GitHub-Prüfung für Commit `a44c7b40acdd6225564895259e4070a26bd3dd96`: keine offenen PRs auf `codex/gesamtrefaktorierung` und keine PR-getriggerten Workflow-Läufe für diesen Commit. Das belegt keine CI-Ausführung oder grüne Checks.
- Folgepoll: Prompt-ID `d07ad550-1972-45ab-b37d-ff38863cd593`, Präfix `Film_x_batch/FX_0505`, weiter aktiv; History ohne Abschluss, Queue 1/0, Producer-PID 10456 lebt. Keine Queue-Aktion vorgenommen.

## ComfyUI-Fortschritt nach FX_0505

- Prompt-ID `d07ad550-1972-45ab-b37d-ff38863cd593` meldet `success` und `completed=true`. `E:\03_Video_&_Medien\Film_x_batch\FX_0505_00001_.mp4` liegt mit 1.521.253 Byte vor; `ffprobe` bestätigt H.264, 736×416, 24 fps, 243 Frames und 10,125 s.
- Prompt-ID `e3fe365d-8695-4609-8699-1cbd50d84aa0`, Präfix `Film_x_batch/FX_0506`, läuft; Queue 1/0, Producer-PID 10456 lebt. Keine Queue-Aktion vorgenommen.
- Nachfolgender GitHub-/Quellstand `4b7d4adf2fb9757ade223d46b3e3e90075d9c241` wurde gepusht und remote verifiziert. Dieser Folgebericht ändert nur Dokumentation.

## GUI-Fit-Bericht-Export verifiziert

- `tests/test_hearing_calibration.py::test_csv_single_real_fit_without_cache_audio_preserves_old_output` klickt jetzt den echten Ergebnisdialog-Button „Bericht / Vorschlag speichern“. Beide Fälle mit und ohne vorhandene `gewichte.json` bestanden: **2/2** (`venv312`, Python 3.12.10, pytest 9.1.1, `-n 0 --no-cov`, 0,57 s). Der Export wird erneut eingelesen, `validate_proposal` akzeptiert ihn, Inhalt stimmt mit dem Vorschlag überein und der Dialog zeigt den Zielpfad. Synthetische CSV, keine Audioanalyse/GPU.
- Der Runtime-Nachweis schließt die zuvor offene Fit-Dialogklick-Lücke. Keine fehlende Button-Verdrahtung gefunden. Vollständige CLI-gegen-native Fit-Parität, Vollsuite, aktueller Frozen-Build und manuelle GUI-Abnahme bleiben offen.
- Batch-Folgepoll bei Beginn dieses Prüfschritts: Prompt `e3fe365d-8695-4609-8699-1cbd50d84aa0` / `FX_0506` aktiv, Queue 1/0, Producer-PID 10456 lebt.

## ComfyUI-Fortschritt nach FX_0506

- Prompt-ID `e3fe365d-8695-4609-8699-1cbd50d84aa0` meldet `success` und `completed=true`. `E:\03_Video_&_Medien\Film_x_batch\FX_0506_00001_.mp4` liegt mit 1.290.442 Byte vor; `ffprobe` bestätigt H.264, 736×416, 24 fps, 243 Frames und 10,125 s.
- Prompt-ID `f1ae3519-0d7c-488c-9e99-952b36668899`, Präfix `Film_x_batch/FX_0507`, läuft; Queue 1/0, Producer-PID 10456 lebt. Keine Queue-Aktion vorgenommen.
- Der Fit-Dialogtest-Commit `50057538040f6e56456278ffc618fcbbca19b359` ist gepusht und remote bestätigt; dieser Folgeeintrag dokumentiert den danach verifizierten Batchabschluss.

## ComfyUI-Fortschritt nach FX_0506 und GUI-Testcommit

- ComfyUI-Folgepoll zeigt Prompt-ID `f1ae3519-0d7c-488c-9e99-952b36668899`, Präfix `Film_x_batch/FX_0507`, aktiv; Queue 1/0, Producer-PID 10456 lebt.
- Commit `50057538040f6e56456278ffc618fcbbca19b359` ergänzt den Dialogklick-Rundreisenachweis und wurde gepusht. Der neue GUI-Exporttest besteht in beiden Parametervarianten (**2/2**); Plan und Fit-Exportstatus sind nachgeführt.

## Kanonische Kandidaten-Fit-Parität geprüft

- `tests/test_hearing_ram_calibration.py::test_candidate_cli_and_native_fit_share_report_but_keep_publication_separate`: **1/1 bestanden** (`venv312`, Python 3.12.10, pytest 9.1.1, `-n 0 --no-cov`, 1,30 s). Nativer `compute_proposal` führt RAM-Audit und Fit auf synthetischen Daten aus; CLI-Wrapper liest CSV und berechnet über denselben `_compute_candidate_fit`. Kanonische Berichte sind gleich. CLI schreibt den Gate-Entwurf, GUI lässt Child-Präferenzen unverändert. CLI-Bindungsprüfung/-token wurden für diesen Berechnungsvertragstest kontrolliert ersetzt; separate Tests decken Bindungen ab. Keine Originalmusik/GPU.
- Prompt-ID `f1ae3519-0d7c-488c-9e99-952b36668899` / `FX_0507` meldet `success`, `completed=true`. Ausgabe `E:\03_Video_&_Medien\Film_x_batch\FX_0507_00001_.mp4`: 1.202.688 Byte; `ffprobe` bestätigt H.264, 736×416, 24 fps, 243 Frames und 10,125 s.
- Prompt-ID `6f822810-c414-41cd-a34c-31a07fe98efd`, Präfix `Film_x_batch/FX_0508`, läuft; Queue 1/0, Producer-PID 10456 lebt. Keine Queue-Aktion vorgenommen.

## Lokale Arbeitsänderungen abgegrenzt

- Der read-only-Dateistatus zählt weiterhin 93 unveränderte lokale Änderungen. Endungs-/Pfadabgleich ordnet sie Markdown/HTML, `.claude/`- und `.codex/`-Agent-/Skillkonfigurationen sowie Projektanweisungen zu; keine `.py`-, `.spec`-, Installer-, Build- oder Requirements-Dateien darunter. Nichts davon wurde gestaged oder verändert.
- Dieser Zwischenstand entstand vor der Dreinoten-Parität: Der erste Kandidaten-Paritätstest und das Plan-Update waren damals noch uncommitted; Dreinoten-CLI/native-Fit-Vergleich war zu diesem Zeitpunkt offen. Der aktuelle Test-/Commitstand folgt im Nachtrag „Dreinoten-CLI/native-Fit-Parität geprüft“; Vollsuite, aktueller Frozen-Build und manuelle GUI-Abnahme bleiben offen.

## Dreinoten-CLI/native-Fit-Parität geprüft

- `tests/test_hearing_ram_calibration.py::test_three_note_cli_and_native_fit_share_report_but_publish_separately`: **1/1 bestanden** (`venv312`, Python 3.12.10, pytest 9.1.1, `-n 0 --no-cov`, 1,33 s). Nativer GUI-Vorschlag und CLI-Wrapper liefern denselben kanonischen Dreinoten-Fitbericht und dieselben Gate-Updates. GUI-Bericht bleibt `aktiviert_candidate_preferences=false`; CLI-Bericht setzt es nach erfolgreicher Veröffentlichung auf `true`. CLI-Bindungstoken/-validierung im Vergleichstest kontrolliert ersetzt; übrige Schema- und Fit-Bindungstests getrennt. Synthetischer RAM-Satz, keine Originalmusik/GPU.
- Der Fit-Paritätsbeleg deckt nun Standard-Kandidaten- und Dreinotenpfad ab. Vollständiger Golden-Master mit unveränderter CLI-Bindungsprüfung und sämtlichen publizierten Schemas bleibt offen. Ein früherer Versuch, vollständige Dateiinventare gleichzusetzen, scheiterte an unterschiedlichen Transportverträgen: CLI-Ausgaben enthalten reale WAV-Dateien und eigene Anleitungstexte, der native Pfad virtuelle Clip-Referenzen samt `hearing_source_manifest.json`. Diese erste Erweiterung wurde nach zwei fehlgeschlagenen Läufen zurückgenommen. Der später ergänzte und bestandene Test prüft die Medientransporte getrennt und Rating-Sessions/Clipzahlen semantisch; siehe „CLI-/Native-Medientransport getrennt validiert“.
- ComfyUI-Prompts `8d02d7b5-62da-4abd-bf59-3601b495abab` / `FX_0509`, `9fad4e75-7133-4ca7-9d7b-1806cdd9dd84` / `FX_0510` und `4374eb35-d3da-41d9-8a5f-b8597f256976` / `FX_0511` melden in der History `success`. Die MP4s haben 1.329.063, 2.874.351 und 1.962.176 Byte; `ffprobe` bestätigt jeweils H.264, 736×416, 24 fps, 243 Frames und 10,125 s. Folgeprompt `02106d71-4cd8-4cd1-a679-9c1cfb8e2c99` / `Film_x_batch/FX_0512` ist aktiv (Queue 1/0); Producer-PID 10456 lebt. Batch-Ende nicht festgestellt. Keine Queue-Aktion vorgenommen.

## Unabhängiger Produktcode-Delta-Review

- Read-only-Review des Produktcode-Deltas von `149f5af1ad46eb99f3958a5ad28376d52ad11854` bis `c0f851ceee0f73e6faf2ddc4d54a540aa70be4fd`: kein belastbar reproduzierbarer Defekt gefunden. Geprüft wurden Playlist-Auswahl/Exportrotation, Hearing-Profile/CSV-Validierung sowie geänderte UI-, Worker- und Installer-Pfade. Keine Tests, Builds, Audio-/GPU-Arbeit oder Dateien geändert.
- Ein zweiter unabhängiger Read-only-Blindspot-Pass über dasselbe Produktcode-Delta fand ebenfalls keinen quellcodebelegten Defekt oder fehlende Verdrahtung. Schwerpunkt: `hpg_core/hearing_calibration.py`, `tools/rate_transitions.py`, `hpg_core/playlist_selection.py` und die Aufrufpfade in `main.py`. Auch dieser Pass führte keine Tests, Builds oder Audio-/GPU-/GUI-Prüfungen aus.
- Der geprüfte Produktcode ist am aktuellen HEAD `a411e7709ef4be9d453d7544245f541845ac1dcf` unverändert; danach kamen nur Dokumentationscommits hinzu. Die beiden Delta-Reviews ersetzen weder Laufzeit-/Musikabnahme noch den offenen vollständigen GUI-/Release-Abschlussreview.

## FilmX-Batch-Fortschritt

- Prompt `02106d71-4cd8-4cd1-a679-9c1cfb8e2c99` / `FX_0512` meldet in der ComfyUI-History `success`. `Film_x_batch/FX_0512_00001_.mp4` existiert mit 2.125.400 Byte; `ffprobe` bestätigt H.264, 736×416, 24 fps, 243 Frames und 10,125 s.
- Prompt `56a12074-ae4d-4fd2-bdcd-f8ab05967796` / `FX_0513` meldet `success`. `Film_x_batch/FX_0513_00001_.mp4` existiert mit 2.047.495 Byte; `ffprobe` bestätigt H.264, 736×416, 24 fps, 243 Frames und 10,125 s.
- Prompt `73ddd6a6-e467-4ad0-9c98-0bad98621545` / `FX_0514` meldet `success`. `Film_x_batch/FX_0514_00001_.mp4` existiert mit 1.811.717 Byte; `ffprobe` bestätigt H.264, 736×416, 24 fps, 243 Frames und 10,125 s.
- Prompt `558de56e-c1ab-4044-985c-af6c33e2173e` / `FX_0515` meldet `success`. `Film_x_batch/FX_0515_00001_.mp4` existiert mit 1.961.825 Byte; `ffprobe` bestätigt H.264, 736×416, 24 fps, 243 Frames und 10,125 s.
- Prompt `6a769380-4248-4c91-b491-02d422588931` / Präfix `Film_x_batch/FX_0516` meldet `success`. `FX_0516_00001_.mp4` existiert mit 2.086.830 Byte; `ffprobe` bestätigt H.264, 736×416, 24 fps, 243 Frames und 10,125 s.
- Folgeprompt `404ca812-c32e-4c26-9fa4-07aa0ad7ca81` / Präfix `Film_x_batch/FX_0518` läuft; Queue 1/0, `film_batch.py` PID 26284 lebt. Batch-Ende nicht festgestellt. Keine Queue-Aktion vorgenommen.

## CLI-/Native-Medientransport getrennt validiert

- Der Producer-Paritätstest prüft jetzt die beiden Transportverträge unabhängig: CLI-Clips sind existierende, lesbare WAV-Dateien; native Clips haben keine WAV-Dateien und sind durch das strikt geladene `hearing_source_manifest.json` als virtuelle Referenzen gebunden.
- Clipzahlen und logische Rating-Sessions stimmen für Einzel, Kandidaten, Dreinoten und Dramaturgie überein. `tests/test_hearing_workflow.py::test_real_internal_producer_artifacts_match_cli_and_native_service`: **4/4 bestanden** (`venv312`, Python 3.12.10, pytest 9.1.1, `-n 0 --no-cov`, 3,09 s). Kein Originalaudio, keine GPU. Vollständige Fit-/Blindtest-/Export-Schema-Golden-Master-Prüfung bleibt offen.
- Rating-Persistenz und Blindtest-Referenzverträge: `tests/test_hearing_ratings.py tests/test_hearing_blind.py`: **246/246 bestanden** (`venv312`, Python 3.12.10, pytest 9.1.1, `-n 0 --no-cov`, 98,71 s). Geprüft wurden alle Bewertungsmodi, strikte Public-/Private-Referenzschemas, Resume-Bindung und Fehler-/Abbruchverträge. Temporäre Test-Fixtures, kein Originalaudio oder GPU. Der Vollsuite- und GUI-Abschluss bleibt offen.
- Calibration-/Fit-Verträge: `tests/test_hearing_calibration.py tests/test_hearing_ram_calibration.py`: **152/152 bestanden** (`venv312`, Python 3.12.10, pytest 9.1.1, `-n 0 --no-cov`, 77,46 s). Geprüft wurden CSV-/Quellbindung, echter synthetischer RAM-Replay, Fit-Gates, Proposal-Export und kanonischer Binding-Roundtrip sowie Manipulationsablehnung. Keine Originalmusik oder GPU. Der vollständige Cross-Entry-Point-Golden-Master über alle CLI-/Native-Fit-, Blindtest- und Exportausgaben bleibt offen.
- Ein CLI-Audit-/Fit-Paritätsversuch auf einem nativen Producer-Set wurde vom bestehenden CLI-Auditor abgewiesen, weil dessen Legacy-Set-Inventar WAV-Dateien und ein anderes Manifest verlangt, während der native Vertrag virtuelle Referenzen mit `hearing_source_manifest.json` nutzt. Der ungültige Testzusatz wurde entfernt; kein Produktfehler belegt. Ein Cross-Entry-Point-Vergleich muss zunächst ein CLI-materialisiertes Set verwenden.
