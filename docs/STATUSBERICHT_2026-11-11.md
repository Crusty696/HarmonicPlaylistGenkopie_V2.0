# HPG Entwicklungs- und Lagebericht

**Stand:** 11.11.2026

**Branch:** `codex/gesamtrefaktorierung`
**GitHub-Abgleich:** Der bisherige Stand `f46e2b58477d0f07af3b326a90171cb39523b91d` war mit `origin/codex/gesamtrefaktorierung` synchronisiert. Dieser Bericht ergänzt den internen Metadaten-Link-Fix.

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
- Nach dem Exportpfad wurde mit Python 3.12.10 und PyInstaller 6.21.0 erneut
  isoliert unter `E:\AI\HPG-build-verification-2026-11-11-portable-blind-final2` gebaut.
  Bestehende Buildziele und Root-EXE lagen außerhalb des Wirkpfads. Die EXE
  bestand `--hpg-native-smoke` mit Exitcode 0 und `ok=true`; der PyInstaller-
  Abhängigkeitsgraph enthält `tools.prepare_dj_blind_test`. EXE-SHA256:
  `F0B55E177BADDE2C253A2B8752408EC68BE89BB1A678DC553E73BB123CE5565F`.
  Der Native-Smoke endete mit `ok=true`, Exitcode 0; Spawn, RAM-Render und CSV-Fit-Probe bestanden. Der xref enthält `tools.prepare_dj_blind_test`. PyInstaller meldete fehlendes optionales `tbb12.dll`. Das belegt Packaging/Smoke, nicht den manuellen Exportklick oder Klang.
- Commit `c507efa` enthält ausschließlich `main.py` und die beiden genannten
  Testdateien und wurde zu GitHub gepusht.
- Commit `0bba81e` ergänzt im Qualitätsbereich eine native Auswahl zwischen
  bisherigen lokalen A/B-Referenzen und portablem Export vorhandener
  Übergangsclips. Der portable Pfad ruft `tools.prepare_dj_blind_test.prepare`
  direkt in einem Worker auf. Er kopiert keine Originaltracks, erzeugt neutrale
  WAV-Namen und hält den Zuordnungsschlüssel als getrennte CSV-Datei. Start- und
  Fehlerpfad sind mit 143 fokussierten Tests geprüft.

## Verbleibende HPG-Arbeit

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
  aktuelle Fertigstellungsanzeige. Der falsche Smoke-Schalter wurde auf den
  realen `--hpg-native-smoke`-Einstieg korrigiert.
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
- Live-Abfrage am 11.11.: FilmX-Batch **512 MP4-Dateien**, Warteschlange 0,
  ein laufender Auftrag (ID `421d2bea-87fc-41d8-91b8-44060ea9906e`; Prompt-
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
