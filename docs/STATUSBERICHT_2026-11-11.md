# HPG Entwicklungs- und Lagebericht

**Stand:** 11.11.2026

**Branch:** `codex/gesamtrefaktorierung`
**GitHub-Abgleich:** Der VERITAS-Codeaudit prüfte Commit `149f5af1ad46eb99f3958a5ad28376d52ad11854`; der Branch ist inzwischen weiter. Der Bericht wird mit jedem bestätigten Schritt nachgeführt.

## Kurzstatus

Die gezielten A/B-Änderungen bestehen fokussierte Tests und isolierten
Frozen-Smoke. Zusätzlich lehnt die Bewertungsfortschreibung interne Symlinks
auf Metadaten jetzt ab. Der letzte Volltest meldete einen parallelen
Subprozess-Ausreißer; der Einzeltest bestand. Originalmusik-Abnahme und
manueller kompletter GUI-Ablauf bleiben offen.

## Verifizierte Änderungen und Prüfungen

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
- Nach dem Exportpfad wurde mit Python 3.12.10 und PyInstaller 6.21.0 erneut
  isoliert unter `E:\AI\HPG-build-verification-2026-11-11-portable-blind-final2` gebaut.
  Bestehende Buildziele und Root-EXE lagen außerhalb des Wirkpfads. Die EXE
  bestand `--hpg-native-smoke` mit Exitcode 0 und `ok=true`; der PyInstaller-
  Abhängigkeitsgraph enthält `tools.prepare_dj_blind_test`. EXE-SHA256:
  `2626E2ECC32DF8F60836EA7C79246B5E49FB6E849482B3A89114A21ECCA1F67A`.
  Der Native-Smoke endete mit `ok=true`, Exitcode 0; Spawn, RAM-Render und CSV-Fit-Probe bestanden. Der xref enthält `tools.prepare_dj_blind_test`. PyInstaller meldete fehlendes optionales `tbb12.dll`. Das belegt Packaging/Smoke, nicht den manuellen Exportklick oder Klang.
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
- Originalmusik-/manuelle Bewertungsabnahme und eine explizite Prüfung des
  optionalen TBB-Threading-Backends bleiben offen.
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
- Live-Abfrage am 11.11.: FilmX-Batch **514 MP4-Dateien**, Warteschlange 0,
  ein laufender Auftrag (ID `9559b1ca-575a-4ae2-b60b-ccfd55a077c6`; Prompt-
  Prefix nicht erneut ausgelesen). Producer bleibt unberührt. Frühere Ausgaben
  `FX_0436` bis `FX_0438` bestätigte `ffprobe` als H.264, 736×416, 24 fps,
  243 Frames und 10,125 Sekunden.
- Der separate Vier-Prompt-Auftrag `H3_Clip_11` bis `H3_Clip_14` wurde vom
  Batchskript sicher abgewiesen, bevor ein Prompt gesendet wurde, weil dieser
  bestehende Producer die Queue belegt. Dieser zusätzliche H3-Lauf ist noch
  nicht ausgeführt; der laufende FilmX-Batch bleibt unberührt.

## Nächste Schritte

1. FilmX-Queue nicht unterbrechen; nach Leerlauf H3-Vier-Clip-Batch starten
   und jede Ausgabe per History und `ffprobe` prüfen.
2. Manuellen GUI-Klickpfad verifizieren und die vollständige Tool-zu-GUI-
   Paritätsmatrix mit Parser, Routen und Tests synchronisieren.
3. Parallelen nativen Smoke-Ausreißer untersuchen; Originalmusikabnahme und
   optionales TBB-Backend getrennt prüfen.
