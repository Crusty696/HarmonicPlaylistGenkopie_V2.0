# HPG Entwicklungs- und Lagebericht

**Stand:** 11.11.2026

**Branch:** `codex/gesamtrefaktorierung`
**GitHub-Abgleich:** Lokaler `HEAD` und `origin/codex/gesamtrefaktorierung` stimmen auf `f357e4e7e99f545fb6947779225e659c83136371` überein. Letzter Code-Commit ist `baa77d314cfef093c9c00d530be67c85ceb8d1c8`; `f357e4e` dokumentiert den anschließenden GUI-Startnachweis.

## Kurzstatus

Die App ist weiter in Entwicklung. Ein Repository-Audit und gezielte
Bereinigungen sind erfolgt. Die vollständige automatisierte Testsuite besteht;
eine Produktabnahme mit Originalmusik, manuellem GUI-Gesamtlauf und neuem
Frozen-Build liegt weiterhin nicht vor.

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
- Die vollständige Suite `venv312\Scripts\python.exe -m pytest tests/ --tb=short -q`
  bestand mit **6.591 Tests** in 770,27 Sekunden (Exitcode 0). Darin bestand
  auch der Hörtest-E2E-Vertrag mit Producer, Audit, nativem Fit, Bestätigung
  und Ranking-Aktualisierung. Das ersetzt keine menschliche Bedien- oder
  Klangabnahme.
- Eine anschließende Bereinigung entfernte unverbundene Cache-/Zielpfadfelder
  und einen ungenutzten Dateibrowser aus dem nativen Erzeugungsdialog; der
  Managed-Workflow leitet diese Pfade selbst ab. Der fokussierte Lauf
  `tests/test_hearing_panel.py --no-cov --tb=short -q` bestand mit **26 Tests**.
  Die Vollsuite wurde vor genau dieser letzten kleinen GUI-Bereinigung
  ausgeführt und danach nicht wiederholt.
- Die aktuelle Frozen-EXE startete auch im normalen GUI-Modus. Bibliotheks-
  und Qualitätsbereich sowie der Hörtest-Erzeugungsdialog wurden sichtbar
  geöffnet. Der Dialog wurde abgebrochen, bevor Analyse oder Satz-Erzeugung
  startete. Die temporären Cache-/Logpfade lagen im Build-Scratch. Trotz
  APPDATA/LOCALAPPDATA-Overrides erschien ein gespeicherter Musikordner im
  Dialog; die Quelle dieser Voreinstellung wurde nicht separat geprüft.
- Der aktuelle Quellstand wurde isoliert mit Python 3.12.10 und PyInstaller
  6.21.0 unter `E:\AI\HPG-build-verification-2026-11-11-final` gebaut.
  Bestehende Buildziele und Root-EXE blieben außerhalb des Buildpfads. Die
  gebaute EXE bestand `--hpg-native-smoke` mit Exitcode 0 und `ok=true`:
  native Imports/Formulare, Spawn-Worker, RAM-Audiorendering, Fit-Ablehnung und
  Cleanup waren erfolgreich. EXE-SHA256:
  `49C9B17873C3D7965CEA66F5784E4E5E4808A057DBBD30AAFABA2944A2D693E3`.
  Die bestehende Root-EXE behielt SHA256
  `07BBB91DF0A74B8C457156AB1DE368B5C9B8496D0528055C8A2E8FC1583AA3D4`.
- PyInstaller meldete `tbb12.dll` für `numba.np.ufunc.tbbpool` nicht gefunden.
  Der Build und Smoke waren trotzdem erfolgreich; eine explizite TBB-Backend-
  Abnahme ist damit nicht belegt.
- Commit `c507efa` enthält ausschließlich `main.py` und die beiden genannten
  Testdateien und wurde zu GitHub gepusht.

## Verbleibende HPG-Arbeit

- Native Hörtest-Module und GUI-Aktionen sind im Code vorhanden. Die Suite
  deckt zentrale Erzeugungs-, Audit-, Fit-, Blindtest- und Rankingpfade ab;
  vollständige Zuordnung aller Werkzeugoptionen zu GUI-Aktionen und ein
  manueller App-Ablauf sind nicht abgenommen.
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
  Dokumentation und Playlist-Längenspezifikation wurden nicht in `c507efa`
  aufgenommen und bleiben im Arbeitsbaum erhalten.

## ComfyUI-Batchstatus

- Der lokale Server antwortet mit ComfyUI `0.45.2` und erkennt die AMD Radeon
  RX 7800 XT. Modelle und Referenzbilder für den vorbereiteten H3-Workflow
  wurden lokal geprüft; die zwei Referenzbilder wurden hashgeprüft in den
  ComfyUI-Eingabeordner kopiert.
- Ein bereits laufender FilmX-Auftrag `FX_0431` wurde erfolgreich beendet.
  Die Datei `E:\03_Video_&_Medien\Film_x_batch\FX_0431_00001_.mp4` wurde von
  ComfyUI als erfolgreich gemeldet und mit `ffprobe` als H.264, 736×416,
  24 fps, 243 Frames und 10,125 Sekunden bestätigt.
- Der bestehende FilmX-Batch enthält **502 MP4-Dateien**; `FX_0431`,
  `FX_0432`, `FX_0433` und `FX_0435` meldeten in der History `success`.
  `ffprobe`
  bestätigte `FX_0431` bis `FX_0433` als H.264, 736×416, 24 fps, 243 Frames und 10,125
  Sekunden. `FX_0435` ist das letzte fertige Video; `FX_0436` ist aktuell in
  der Queue aktiv.
- Der separate Vier-Prompt-Auftrag `H3_Clip_11` bis `H3_Clip_14` wurde vom
  Batchskript sicher abgewiesen, bevor ein Prompt gesendet wurde, weil dieser
  bestehende Producer die Queue belegt. Dieser zusätzliche H3-Lauf ist noch
  nicht ausgeführt; der laufende FilmX-Batch bleibt unberührt.

## Nächste Schritte

1. Laufende FilmX-Queue nicht unterbrechen; nach deren Ende den vorbereiteten
   H3-Vier-Clip-Batch starten und jede MP4-Datei anhand History und
   Mediendaten prüfen.
2. Hörtest-Plan gegen den aktuellen Code abgleichen und nur belegte offene
   Paritätslücken weiter implementieren.
3. Verbleibende manuelle Hörtest-/Originalmusik-Abnahme und optionale
   TBB-Backend-Prüfung getrennt bewerten; nach Produktänderungen gezielt
   Vollsuite und Frozen-Smoke erneut ausführen.
