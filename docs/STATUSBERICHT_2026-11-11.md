# HPG Entwicklungs- und Lagebericht

**Stand:** 11.11.2026

**Branch:** `codex/gesamtrefaktorierung`
**GitHub-Abgleich:** Der zuletzt geprüfte Code-Commit `0bba81eaa2f17bc1c46c233cf1fc1cc0aa651297` ist auf `origin/codex/gesamtrefaktorierung` vorhanden. Dieser Bericht hält den Stand danach fest; der Integritätsvalidator ist noch uncommitted.

## Kurzstatus

Die App ist weiter in Entwicklung. Repository-Audit und gezielte Bereinigungen
sind erfolgt. Die vollständige Testsuite und ein isolierter Frozen-Build
bestanden nach dem neuen portablen A/B-Export. Originalmusik-Abnahme und
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
- Nach den Änderungen bestand `venv312\Scripts\python.exe -m pytest tests/ --tb=short -q`
  mit **6.598 Tests** in 794,28 Sekunden; fokussierte CSV-Prüfung: 122 Tests (Exitcode 0, Coverage-Gate bestanden).
  Der konfigurierte Lauf schließt `slow`-Tests aus. Der Hörtest-E2E-Vertrag
  deckt Producer, Audit, nativen Fit, Bestätigung und Ranking-Aktualisierung ab.
  Automatisierte Tests ersetzen keine menschliche Bedien- oder Klangabnahme.
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
  isoliert unter `E:\AI\HPG-build-verification-2026-11-11-portable-blind-check` gebaut.
  Bestehende Buildziele und Root-EXE lagen außerhalb des Wirkpfads. Die EXE
  bestand `--hpg-native-smoke` mit Exitcode 0 und `ok=true`; der PyInstaller-
  Abhängigkeitsgraph enthält `tools.prepare_dj_blind_test`. EXE-SHA256:
  `B8D36D86A74524658CDEA09394B9948DEC024EC7910DB3C7677C8C69D4D9083F`.
  Das belegt Packaging/Smoke, nicht den manuellen Exportklick oder Klang.
- Commit `c507efa` enthält ausschließlich `main.py` und die beiden genannten
  Testdateien und wurde zu GitHub gepusht.
- Commit `0bba81e` ergänzt im Qualitätsbereich eine native Auswahl zwischen
  bisherigen lokalen A/B-Referenzen und portablem Export vorhandener
  Übergangsclips. Der portable Pfad ruft `tools.prepare_dj_blind_test.prepare`
  direkt in einem Worker auf. Er kopiert keine Originaltracks, erzeugt neutrale
  WAV-Namen und hält den Zuordnungsschlüssel als getrennte CSV-Datei. Start- und
  Fehlerpfad sind mit 143 fokussierten Tests geprüft.

## Verbleibende HPG-Arbeit

- Native Hörtest-Module und GUI-Aktionen sind im Code vorhanden. Die Suite
  deckt zentrale Erzeugungs-, Audit-, Fit-, Blindtest- und Rankingpfade ab;
  vollständige Zuordnung aller Werkzeugoptionen zu GUI-Aktionen und ein
  manueller App-Ablauf sind nicht abgenommen. Portable CSV-Sessions können jetzt
  gegen die getrennte Schlüsseldatei integritätsgeprüft werden. Der Export-
  Kopiervorgang bleibt nicht abbrechbar; die GUI weist vor dem Start darauf hin.
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
- Live-Abfrage am 11.11.: FilmX-Batch **508 MP4-Dateien**, Warteschlange 0,
  ein laufender Auftrag `FX_0442` (ID
  `1b374626-80fb-4e6d-be10-cc76fdd358c7`). Der laufende Producer bleibt
  unberührt. Frühere Ausgaben `FX_0436` bis `FX_0438` wurden mit `ffprobe`
  als H.264, 736×416, 24 fps, 243 Frames und 10,125 Sekunden bestätigt.
- Der separate Vier-Prompt-Auftrag `H3_Clip_11` bis `H3_Clip_14` wurde vom
  Batchskript sicher abgewiesen, bevor ein Prompt gesendet wurde, weil dieser
  bestehende Producer die Queue belegt. Dieser zusätzliche H3-Lauf ist noch
  nicht ausgeführt; der laufende FilmX-Batch bleibt unberührt.

## Nächste Schritte

1. FilmX-Queue nicht unterbrechen; erst nach Leerlauf den vorbereiteten
   H3-Vier-Clip-Batch starten und jede Ausgabe per History und `ffprobe` prüfen.
2. Portable CSV-Blindsätze mit einem getrennten Integritäts-/Wiederaufnahmeweg
   ergänzen und die komplette Tool-zu-GUI-Paritätsmatrix dokumentieren.
3. Manuellen Hörtest mit Originalmusik und optionales TBB-Backend getrennt
   abnehmen; menschliches Klangurteil bleibt eigenständig.
