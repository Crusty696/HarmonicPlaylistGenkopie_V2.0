# HPG — Harmonic Playlist Generator V2.0

## Projektarchitektur

```
main.py                    # PyQt6 GUI (~1600 Zeilen), QThread-Worker-Muster
hpg_core/
  models.py                # Track-Dataclass (25+ Felder), TrackSection
  analysis.py              # Audio-Analyse (librosa): BPM, Key, Energy, Sections
  config.py                # Alle konfigurierbaren Konstanten (PARALLEL_ANALYSIS_TIMEOUT etc.)
  caching.py               # shelve-basierter Cache mit Cross-Platform File Locking
  parallel_analyzer.py     # ProcessPoolExecutor fuer Multi-Core Analyse
  genre_classifier.py      # Genre-Erkennung (regelbasiert, kein ML)
  structure_analyzer.py    # Track-Struktur (Intro/Verse/Drop/Outro)
  dj_brain.py              # Genre-spezifische Mix-Logik, Transition-Empfehlungen
  playlist.py              # Playlist-Generierung und Scoring
  rekordbox_importer.py    # Rekordbox-Datenbank Import (optional)
  exporters/               # m3u8, Rekordbox XML Export
tests/                     # pytest, 29 Test-Dateien, ~80% Coverage
```

## Python-Pfad (WICHTIG!)

- **Echtes Python:** `C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe`
- **NICHT** `python` oder `python3` aus PATH — findet Windows Store Stub
- In Bash-Tool: `powershell -Command "& 'C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe' ..."`

## Tests ausfuehren

```bash
powershell -Command "Set-Location 'C:\Users\david\Dokumente\HarmonicPlaylistGenkopie_V2.0-main'; & 'C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/ --tb=short -q"
```

Test-Audio-Dateien: `D:\beatport_tracks_2025-08`

## Coding-Konventionen

- 2 Leerzeichen Einrueckung (keine Tabs)
- Kommentare auf **Deutsch**
- HTML in QTextBrowser IMMER mit `html_mod.escape()` escapen (import: `import html as html_mod`)
- UI-Updates NUR im Main-Thread (nie direkt aus Worker-Threads)
- `setUpdatesEnabled(False/True)` um Batch-Updates in Tabellen

## Geschuetzte Dateien (NICHT editieren)

- `track_cache.*` — shelve Cache-Dateien
- `*.lock`, `*.dbm`, `*.dat`, `*.coverage` — Lock- und Coverage-Dateien
- `__pycache__/`, `.pytest_cache/` — Caches

## Git

- Repo: `https://github.com/Crusty696/HarmonicPlaylistGenkopie_V2.0.git`
- Branch: `main`
- Vor jedem Commit: Tests laufen lassen (`/test`)

## Wichtige Muster

### Worker-Thread (Thread-Safety)
```python
class AnalysisWorker(QThread):
    def __init__(self):
        self._should_cancel = False
    def request_cancel(self):
        self._should_cancel = True
    def run(self):
        if self._should_cancel:
            return
```

### Cache TOCTOU-Fix
```python
# Double-check nach Lock-Akquise
stat = os.stat(file_path)
expected_key = f"{file_path}-{stat.st_size}-{stat.st_mtime}"
if expected_key != cache_key:
    return None  # Stale
```

### TrackSection.to_dict() Schluessel
`label`, `start_time`, `end_time`, `start_bar`, `end_bar`, `avg_energy`
(NICHT `start`/`end` — das sind die falschen Namen!)

## Projekt-Status

- DJ Brain Phase 1-5: KOMPLETT
- 961 Tests, 4 skipped (pyrekordbox), 0 failed
- Coverage: ~81%
- Letzte Fixes: K1 Thread-Safety, K2 Button-Disable, K3 XSS, K4 Cache-Race, W2 O(N)->O(1), W3 Progress-Reset, W4 Anti-Flicker, W5 Timeout, W8 Permission-Check
