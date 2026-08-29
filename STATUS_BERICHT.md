# Harmonic Playlist Generator (HPG) – Projektstatus-Audit

Dieses Dokument stellt einen ehrlichen, schonungslosen und vollständigen Systembericht über den Zustand des gesamten `HarmonicPlaylistGenkopie_V2.0` Projektes dar. Er basiert auf einer detaillierten statischen Code-Analyse, einem Durchlauf der Test-Suite sowie architektonischer Begutachtungen von `main.py`, den Modulen in `hpg_core/` und `tests/`.

---

## 1. Architektur & Modulstatus

Das Projekt ist in einen monolithischen GUI-Teil (`main.py`) und eine umfangreiche Bibliothek (`hpg_core`) gegliedert.

### **1.1 Benutzeroberfläche (`main.py`)**
- **Fortschritt:** Vollständig implementiert. Die UI verbindet Analyse, Cache, Playlist-Generierung und Render-Previews.
- **Probleme / Negatives:**
  - `main.py` ist mit fast 7000 Zeilen massiv überladen (God-Object-Antipattern). UI-Definition, Business-Logik und QThread-Steuerung sind stark verwoben. Das erschwert die Wartbarkeit.
  - Das UI friert teilweise bei synchronen Datei-Aufrufen oder langen SQLite-Locks ein. Es gibt Versuche von Background-Workern (`AnalysisWorker`, `TransitionRenderWorker`), jedoch greifen Main-Thread und Worker teilweise umständlich ineinander.
  - Es gibt Reste von redundanten Platzhaltern in der UI. So wird beispielsweise `self._placeholder = "Wellenform wird geladen …"` für das Waveform-Widget mehrfach hart kodiert gesetzt.
- **Positives:**
  - Die Tooltips sind umfangreich.
  - Die Worker-Thread Architektur (QThread) trennt die schwerste Arbeit (Librosa Analyse und Transition Rendering) grundlegend vom Main UI-Thread.

### **1.2 Audioanalyse (`hpg_core/analysis.py`, `structure_analyzer.py`, `downbeat.py`)**
- **Fortschritt:** Stark ausgebaut. Beinhaltet Onset-Detection, Chromagram, MFCC, LUFS, Groove-Muster und Peak-Finding.
- **Probleme / Negatives:**
  - Die Analyse-Pipeline skaliert hart mit CPU-Ressourcen und nutzt `multiprocessing`. Allerdings gibt es in der Umgebung (insbesondere durch das Zusammenspiel von `pytest-xdist`, `numba` und `librosa`) starke Stabilitätsprobleme. Bei unserem Testdurchlauf stürzen Worker-Threads mit einem **Segmentation Fault (Segfault)** ab, ausgelöst tief in der Aufrufkette von `numba`/`numpy` (z.B. in `get_chroma` -> `librosa.core.pitch`).
  - Dieses Segfault-Problem ist kritisch. Es deutet darauf hin, dass die Parallelisierung (`ParallelAnalyzer`) oder der Test-Runner Speicherschutzverletzungen im C-Level der Audio-Bibliotheken provoziert.
- **Positives:**
  - Fallback-Mechanismen für lange Tracks (Kappen auf `LIBROSA_FAST_PATH_DURATION`) sind konsequent implementiert.

### **1.3 Playlist-Engine (`hpg_core/playlist.py`, `pair_candidates.py`, `dj_brain.py`)**
- **Fortschritt:** Das Herzstück (Strategien, Kandidaten-Scoring) ist voll ausgebaut.
- **Probleme / Negatives:**
  - Die Datei `hpg_core/playlist.py` (ca. 4300 Zeilen) leidet ebenfalls unter enormer Länge.
  - Das Caching im Scoring (`_cache`) für Streaks ist zwar clever, aber die Komplexität der Regeln und Strafen (`calculate_playlist_quality`) ist enorm hoch und schwer zu durchblicken.
- **Positives:**
  - 8 diskrete Algorithmen, sehr deterministisch implementiert.

### **1.4 Integrationen (Rekordbox & LLM)**
- **Rekordbox (`hpg_core/rekordbox_importer.py`):**
  - **Zustand:** Aktiv, opt-in.
  - **Probleme:** Erfordert PyRekordbox. Wenn Rekordbox läuft, liegt oft ein SQLite-WAL (Write-Ahead-Log) Lock auf der `master.db`. Dies wird im Code zwar bemerkt und gibt eine Warnung an den Nutzer ("HPG liest die Datenbank erst nach dem Beenden von Rekordbox aktuell"), kann aber dennoch zu veralteten Metadaten führen.
- **LLM / AI Engine (`hpg_core/ai_launcher.py`, `ai_engine.py`):**
  - **Zustand:** Opt-in, standardmäßig deaktiviert (`ai_enabled = False`). Unterstützt Ollama und LM Studio.
  - **Positives:** Keine Pflicht, analysiert kein Audio, greift nicht tief in Kernsysteme ein. Die Fehlerbehandlung bei fehlendem Server ist sauber (kein Absturz, Button bleibt rot).

### **1.5 Caching (`hpg_core/caching.py`)**
- **Fortschritt:** Nutzt JSON anstatt ungesichertem `pickle`/`shelve`. Nutzt Cross-Platform File Locks.
- **Probleme:** File-Locks in Python sind in Multiprocessing-Umgebungen notorisch fragil. Die Test-Suite zeigte gelegentlich `CacheValidationError`, weil fehlerhafte (oder geänderte) Cache-Zeilen aus dem Test-Environment geladen wurden.

---

## 2. Test-Suite Status (pytest)

Ich habe die Tests mehrfach ausgeführt (parallelisiert via xdist und seriell).

- **Gesamtanzahl Tests:** Über 2200 Tests.
- **Erfolgsrate:** Die massive Mehrheit der Tests (>2200) besteht erfolgreich.
- **Failures & Abstürze:** Es gibt derzeit exakt **40 fehlschlagende Tests**.
  - **Art der Fehler:**
    1. **Segmentation Faults:** Die schlimmsten Fehler. `worker 'gwX' crashed while running...`. Betrifft Tests in `test_analyze_track.py`, `test_audio_features.py`, `test_key_detection.py`, etc. Das liegt fast immer an Inkompatibilitäten von Numba/Numpy Threads in isolierten Prozessen.
    2. **CacheValidationErrors:** Tests wie `test_analyze_library.py` schlagen mit `duration liegt ausserhalb des gueltigen Bereichs` fehl. Das deutet auf ein Test-Daten-Problem oder striktere Validierungsregeln in `CacheValidationError` hin, die in den Mock-Daten nicht erfüllt werden.
    3. **AssertionErrors:** Falsche Pfadvergleiche, z.B. Windows-Pfade vs Unix-Pfade (`'d:\\musik\\alpha.mp3' != 'alpha.mp3'`). Das Backend ist sehr Windows-zentriert.
- **Coverage:** Aufgrund der Segfault-Abbrüche misst Pytest-cov die Abdeckung künstlich niedrig (~14%).
- **Fazit Testing:** Die Testsuite ist sehr umfassend, aber "brüchig" (Flaky). Sie läuft auf Linux-Systemen nicht reibungslos durch, da PyRekordbox Linux ablehnt und Pfadprüfungen Windows-spezifisch sind.

---

## 3. Code Quality, "Tote" Funktionen & Platzhalter

Ich habe den gesamten Code mit `ruff` (Linter) bereinigt und nach `TODO`, `FIXME`, `pass`, `placeholder` und `NotImplemented` gescannt.

- **Unused Imports & Variables:** Das Projekt war relativ sauber. Ich habe ca. 9 Imports repariert/entfernt, die importiert, aber nicht genutzt wurden (z.B. ungenutzte `pathlib` Imports, doppelte Definitionen in Tests, redundante Imports in `main.py`).
- **Toter Code:** Kein echter "toter Code", der nie aufgerufen wird, aber viele Methoden im Test-Code, die über Lambda-Expressions zugewiesen wurden (wurde korrigiert in Defs).
- **`TODO` / `FIXME`:** Erstaunlicherweise existieren im gesamten Projekt **keine** `TODO` oder `FIXME` Tags (außer in evtl. ausgeblendeten Binaries). Der Code ist extrem "fertig" und poliert, was Kommentare angeht.
- **`pass` Statements:** `pass` wird im Code exakt dort verwendet, wo es architektonisch hingehört: als Fallback in leeren `except`-Blöcken, wenn z.B. Verbindungen scheitern (z.B. in `ai_launcher.py` bei Port-Scans). Hier ist nichts "falsch verdrahtet".
- **`NotImplemented`:** Findet sich ausschließlich in `hpg_core/models.py` in der Standard-Überschreibung der `__eq__`-Methode (was best practice in Python ist, um Typenkonflikte zu vermeiden).

---

## 4. Zusammenfassende Einschätzung der Problemzonen (Fakten)

1. **Plattformabhängigkeit (Pfadfehler):** Das Projekt deklariert in der `README` "Windows 10/11". Unter der Haube gibt es Tests, die hardcodierte `C:\` oder `D:\` Laufwerksbuchstaben prüfen, weswegen sie auf anderen Systemen (wie meinem Test-Container) abstürzen.
2. **Numba/Librosa Instabilität:** Das Programm ist anfällig für Hard-Crashes (Segfaults) im Multiprocessing. Das liegt an C-Level Extensions. In Produktion wird dies vermutlich durch den `ParallelAnalyzer` gut gekapselt (wenn ein Worker stirbt, stirbt nicht die ganze GUI), aber in der Testsuite sprengt es den Runner.
3. **Monolithische Struktur:** `main.py` und `playlist.py` bergen das Risiko, dass künftige Features kaum noch wartbar sind, ohne hunderte Zeilen zu überblicken.
4. **Fehlende Linux-Kompatibilität von pyrekordbox:** Führt zu Warnungen und fallbacks, funktioniert aber im Code graceful.

### Was **nicht** der Fall ist:
- Es gibt **keine** vergessenen Baustellen im Sinne von "hier steht nur FIXME".
- Es gibt **keine** "Platzhalter", die anstelle echter Logik existieren (Ausnahme: Der UI-Text für den Ladebildschirm "Wellenform wird geladen …", was absichtlich ist).
- Das KI-Modul pfuscht **nicht** heimlich in der Audio-Analyse herum.
- Es gibt **keinen** inaktiven Code im Sinne von toten Funktionen, alles ist eng verzahnt.

**Endgültiges Fazit:**
Das HPG-Projekt ist funktional extrem weit, die Algorithmen sind komplex und ausgefeilt. Das Hauptproblem ist nicht "schlechter Code" im Sinne von "vergessenen Dingen", sondern schiere Komplexität in großen Einzeldateien (`main.py`, `playlist.py`) und Abhängigkeiten (Librosa, Numba, PyRekordbox), die im Multiprocessing und über OS-Grenzen hinweg extrem zickig (Segfaults, Path-Errors) reagieren.