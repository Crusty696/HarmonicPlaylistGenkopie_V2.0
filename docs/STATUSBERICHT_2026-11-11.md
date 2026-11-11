# HPG Entwicklungs- und Lagebericht

**Stand:** 11.11.2026

**Branch:** `codex/gesamtrefaktorierung`
**GitHub-Abgleich:** Der VERITAS-Codeaudit prüfte Commit `149f5af1ad46eb99f3958a5ad28376d52ad11854`; der Branch ist inzwischen weiter. Der Bericht wird mit jedem bestätigten Schritt nachgeführt.

## Kurzstatus

Letzte Vollsuite vor dem neuen Playlist-Aktionszustandsfix am 11.11.2026:
**6.679/6.679 bestanden**, Coverage **81,11 %**, Exitcode 0 (`venv312`, Python
3.12.10, `pytest tests/ --tb=short -q -n 2`, Laufzeit 22:51). Der aktuelle
Aktionszustandsfix besteht den gezielten Qt-Test und ist im isolierten Frozen-Build
visuell sowie barrierefrei geprüft. Die vollständige manuelle GUI-/Originalmusik-
Abnahme bleibt offen. Der laufende ComfyUI-Batch bleibt unangetastet.

## Verifizierte Änderungen und Prüfungen

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
  Quellhashes unverändert. Das neue GUI-Fenster ließ sich nach zwei CUA-Inventur-
  Zeitlimits nicht anbinden. Öffnen/Bewerten im GUI bleibt daher unbestätigt;
  keine Analyse und kein Zugriff auf Originalmusik.
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
  Das belegt keinen Fit auf Originalmusik. Die Apply-E2E verwendet weiter einen
  injizierten Pass-Ausgang und bleibt als durchgehende Kette offen.
- Fit-Optionsabbildung neu geprüft: **8/8 Dialog-/Workerfälle bestanden**.
  Einzel-Fit reicht Genres weiter; Kandidaten-/Dreinoten-Fit deaktiviert den
  unwirksamen Genrefilter; Replay-Audit deaktiviert den Seed. Artefakt-/Golden-
  Master-Vergleich bleibt ein separates offenes Task-7-Kriterium.
- Erster CLI-/GUI-Publikationsvergleich bestanden (**1/1**): ein deterministischer
  Einzelmodus-Fixture-Producer erzeugt über beide Wrapper bytegleiche CSVs;
  Legacy- und Quellvalidator akzeptieren die Resultate. Der interne Algorithmus
  war dabei absichtlich ersetzt. Das ist ein Wrapper-/Schema-Vertrag, kein
  Golden Master für reale Producer; die übrigen Modi und JSON-Rundreisen bleiben
  offen.
- Native Veröffentlichung mit den echten internen Producerfunktionen ergänzt
  geprüft: **3/3** für Einzel, Kandidaten und Dreinoten-Kandidaten. Alle Outputs
  werden vom späteren Quellmanifest-Loader eingelesen; Einzel zusätzlich vom
  Legacy-Validator. Analyse-Cache und Kandidatenfindung sind kontrollierte
  Fixtures, Audios werden nicht dekodiert. Das deckt Loader-/Schemaannahme der
  Producer-Ausgaben ab, aber keinen CLI-/GUI-Golden-Master oder Originalmusik.
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
- Erzeugungsoptionen jetzt durchgehend GUI→`PrepareConfig`→Producer-Namespace für Einzel, Kandidaten, Dreinoten und Dramaturgie geprüft. Tests decken wirksame Werte, Defaultwerte und deaktivierte Modusfelder ab; Service-Rangevalidierung zusätzlich geprüft: **22 Tests bestanden**, anschließend nochmals **8 GUI-Modus-/Verdrahtungstests bestanden**. Gesamte CLI/GUI-Matrix, Volltest, Build und manueller App-Lauf bleiben offen.
- Auswahlprofil-Lücke geschlossen: JSON-Dateiauswahl im Dialog; vor Konfiguration/Analyse/Workerstart werden Zweckmarker, Merkmale, Mittelwerte/Streuungen, drei Modellziele/Koeffizienten und Tracklisten validiert. Der Kandidatenproducer nutzt denselben Validator erneut. Gültige Profilanwendung plus Ablehnung fehlerhafter Profile ohne Konfiguration geprüft. `tests/test_hearing_panel.py`: **14 gezielte Tests bestanden**. Gesamte CLI/GUI-Matrix, Volltest, Build und manueller App-Lauf bleiben offen.
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
  Live-Poll nach dem M3U8-Exportpfad: Prompt-ID `51`, UUID
  `94e16fa1-ff24-4699-8bfe-d43d7a30bfc0`, Ausgabepräfix
  `Film_x_batch/FX_0482`; Queue hat 0 wartende Aufträge.
  Producer bleibt unberührt; kein Auftrag eingereiht, geändert oder abgebrochen. Frühere Ausgaben
  `FX_0436` bis `FX_0438` bestätigte `ffprobe` als H.264, 736×416, 24 fps,
  243 Frames und 10,125 Sekunden.
- Der separate Vier-Prompt-Auftrag `H3_Clip_11` bis `H3_Clip_14` wurde vom
  Batchskript sicher abgewiesen, bevor ein Prompt gesendet wurde, weil dieser
  bestehende Producer die Queue belegt. Dieser zusätzliche H3-Lauf ist noch
  nicht ausgeführt; der laufende FilmX-Batch bleibt unberührt. Für den nächsten
  H3-Lauf fehlen weiterhin die verbindlichen Prompttexte oder deren Quelldatei.

## Nächste Schritte

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

1. FilmX-Queue nicht unterbrechen; nach Leerlauf H3-Vier-Clip-Batch starten
   und jede Ausgabe per History und `ffprobe` prüfen.
2. Restlichen manuellen GUI-Pfad (Satz erstellen, Fit/Export und weitere Modi)
   abnehmen; Matrix-Parität nach der erneuten Parser-/Producerprüfung unabhängig
   read-only gegen den Code reviewen.
3. Parallelen nativen Smoke-Ausreißer untersuchen und Originalmusikabnahme
   abschließen, sobald die iGPU-/Analysefreigabe wieder gilt.
