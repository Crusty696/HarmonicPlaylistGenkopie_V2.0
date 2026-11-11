# HPG Entwicklungs- und Lagebericht

**Stand:** 11.11.2026

**Branch:** `codex/gesamtrefaktorierung`
**GitHub-/CI-Abgleich (11.11.2026):** Der letzte Produktcode-Commit `a220ca69b989eb6f5e6863ac9e01672a10f435aa` ist auf `origin/codex/gesamtrefaktorierung`. `origin/main` ist Vorfahr; bis zu diesem Produktcode-Commit liegt `main` 150 Commits zurück. `gh run list --branch codex/gesamtrefaktorierung` zeigte beim frischen Abgleich keine Branch-Runs; ein offenes PR gab es nicht. `.github/workflows/test-installer.yml` triggert auf Push nach `main` oder PR nach `main`, nicht auf diesen Feature-Branch. CI für diesen Feature-Branch ist unbekannt, nicht grün. Nachfolgende Änderungen auf dem Feature-Branch waren reine Statusbericht-Commits.

## Kurzstatus

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
- Vollständige Analytics-Panel-Aktionsverdrahtung geprüft: neuer Qt-Regressionstest klickt alle 14 sichtbaren Aktionen (Sammlung, Messdiagnosen und zwölf Hörtestaktionen) und prüft den erreichten `MainWindow`-Handler samt Audit-Parameter. `tests/test_main_window.py::test_quality_panel_actions_reach_mainwindow_handlers` besteht **1/1** (`venv312`, Python 3.12.10, pytest 9.1.1, `-n 0 --no-cov`, 0,64 s). Das verifiziert Button→Signal→Handler im Qt-Test; reale Dialog-/Server-/Audioabläufe bleiben getrennte Abnahmepfade.
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

1. FilmX-Queue nicht unterbrechen. Live-Stand am 11.11.2026:
   Prompt 71 / UUID `5874445e-04ac-4f13-a938-9a695bccdc4f` ist in History
   erfolgreich abgeschlossen. `FX_0496_00003_.mp4` liegt mit 3.512.006 Bytes
   vor; `ffprobe` bestätigt H.264, 736×416, 24 fps, 243 Frames und 10,125 s.
   Die Dateien `_00001_` und `_00002_` sind separat bestätigt. Der Folgepoll
   zeigt Prompt 72 aus `FX_0497` abgeschlossen und Prompt 73 / UUID
   `5a0f9ad9-7e82-433f-84f0-a79417d28340` mit Präfix `Film_x_batch/FX_0498`
   aktiv (Producer-PID 10456, Queue 1/2). `FX_0497_00001_.mp4` liegt mit
   2.272.035 Bytes vor; `ffprobe` bestätigt H.264, 736×416, 24 fps, 243 Frames
   und 10,125 s. Die History für Prompt 72 war beim Poll bereits leer. In der
   Warteschlange stehen Prompt 74 und 75 für `PBStudio_T007/g1_6daef520-735b-4534-941d-c71665559440/item_1` und `item_2`; diese Jobs bleiben unangetastet.
   Den geplanten H3-Vier-Clip-Batch erst nach Ende aller aktiven und wartenden
   Jobs starten, Queue-Eigentümer und freie Queue vorher erneut prüfen und jede
   Ausgabe über History und `ffprobe` prüfen.
   Desktopinventar: sechs Fenster aus isolierten `HPG-build-verification`-
   Builds sind noch offen. Die dazugehörigen HPG-Prozesse zeigten im 3-s-
   CPU-Snapshot keine fortlaufende Last außer 0,12 CPU-s bei einem Prozess;
   die Fenster wurden nicht verändert oder geschlossen.
2. Nach Ende des laufenden Batches die Vollsuite gegen den aktuellen HEAD
   ausführen; die letzte Vollsuite vor jüngsten Änderungen bestand mit
   6.679/6.679 Tests und 81,11 % Coverage.
3. Im Vollsuite-Lauf nach dem Batch prüfen, ob die auf 60 Sekunden erweiterte
   Smoke-Spawn-Frist den dokumentierten xdist-Timeout beseitigt.
4. Manuellen Fit-/Exportpfad und weitere Modi abnehmen; Originalmusik- und
   Native-Analyse erst prüfen, wenn die iGPU-/Analysefreigabe wieder gilt.

## UI-Sprachkorrektur 11.11.2026

- Im sichtbaren Bereich `AdvancedParametersWidget` wurden 26 deutsche
  Beschriftungs- und Tooltip-Texte mit ASCII-Umschriften auf korrekte Umlaute
  umgestellt; die KI-Statuszeile heißt nun „KI: noch nicht geprüft“ vor der
  Initialisierung. Im tatsächlichen Widget-Startzustand wechselt sie korrekt zu
  „KI deaktiviert (deterministischer Kernlauf)“.
- Weitere noch sichtbare ASCII-Umschriften in Genre-/Kandidatengewicht-
  Tooltips und Statusmeldungen korrigiert; einschließlich der Statusmeldung
  „ungültig“ und des Hinweises auf den nächsten Lauf.
- Neuer Qt-Regressionstest
  `tests/test_transition_weight_ui.py`: **12/12 bestanden** mit
  Python 3.12.10 (`venv312`, `-n 0 --no-cov`). Kein Vollsuite-Lauf und kein
  Frozen-Build; beides bleibt nach dem ComfyUI-Batch eingeplant.
- Prompt 72 wurde im Folgepoll durch Prompt 73 ersetzt; ComfyUI-Queue zeigt
  Prompt 73 / UUID `5a0f9ad9-7e82-433f-84f0-a79417d28340`, Präfix `FX_0498`,
  aktiv; Queue 1/2, Producer-PID 10456 lebt. Wartend sind Prompt 74 und 75 mit
  Präfixen `PBStudio_T007/g1_6daef520-735b-4534-941d-c71665559440/item_1` und
  `item_2`; sie blieben unberührt. `FX_0497_00001_.mp4` (2.272.035 Bytes) ist
  mit `ffprobe` als H.264, 736×416, 24 fps, 243 Frames und 10,125 s bestätigt.
  Die History von Prompt 72 war beim Poll bereits leer; die Ausgabe-/Queue-
  Beobachtung stützt den Abschluss, nicht ein History-Eintrag. Queue und
  Producer blieben unangetastet.
