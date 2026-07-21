---
name: hpg-debugging
description: Use when debugging HPG — Tests laufen lassen, Analyse-Pipeline-Fehler, Cache-Probleme (hpg_cache_v11.db), BrokenProcessPool/C-Level-Crashes, QThread/UI-Freezes, ImportError beim Start, oder wenn build.bat/config.py Fehler wirft.
---

# HPG Debugging

## Overview

PyQt6-App (main.py, ~3500 Zeilen) + hpg_core/. Business-Logik läuft in QThreads, Ergebnisse NUR über pyqtSignals in den GUI-Thread. Audio-Analyse in Subprozessen (librosa kann auf C-Ebene crashen).

## Umgebung & Tests

- **Python fixiert**: `C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe` — NIE System-Python 3.14 (numba braucht <3.13, siehe AUDIT_REPORT.md).
- Tests: `powershell -Command "& '<python.exe>' -m pytest tests/ --tb=short -q"` — pytest.ini erzwingt `--cov-fail-under=70`, `-n auto` (xdist), UserWarnings aus hpg_core werden zu Fehlern.
- Test-Helper: `assert_mix_points_valid` [tests/conftest.py:186](tests/conftest.py:186), `assert_phrase_aligned` [:215](tests/conftest.py:215), Track-Factories (`make_house_track`, `make_dnb_track`), `performance_fixtures.py` (vor-analysierte Tracks, kein Audio nötig).
- Einzelne Testklasse ohne Coverage-Zwang: `-p no:cacheprovider --no-cov` anhängen.

## Symptom → Ursache

| Symptom | Prüfe |
|---------|-------|
| App startet nicht / SyntaxError | [config.py:136-141](hpg_core/config.py:136) — bekanntes verwaistes AI-Prompt-Fragment nach `AI_MODELS_AVAILABLE` (Stand 2026-07: uncommitted defekt) |
| ImportError `error_reporter`/`playlist_security` | main.py:53-87 importiert untracked Module — existieren `hpg_core/error_reporter.py`, `hpg_core/playlist_security.py`? |
| build.bat schlägt fehl | [build.bat:14-34](build.bat:14) — defekte if/else-Kette, PYTHON_EXE mehrfach überschrieben, zeigt auf Python 3.14 |
| `BrokenProcessPool` bei Analyse | Erwartetes Verhalten: [parallel_analyzer.py:175-236](hpg_core/parallel_analyzer.py:175) fängt Crash, Safe-Mode retry einzeln (`max_workers=1`), korrupte Datei → `[CRASHED/SKIPPED]` |
| Analyse hängt | Future-Timeout `PARALLEL_ANALYSIS_TIMEOUT=60s` [parallel_analyzer.py:162](hpg_core/parallel_analyzer.py:162); Preview-Rendering 30s-Timeout [main.py:513-516](main.py:513) |
| Alte Analyse-Werte trotz Code-Änderung | Cache-Hit! `hpg_cache_v11.db` (SQLite, NICHT shelve). Key = `{filepath}-{size}-{mtime}` [caching.py:111](hpg_core/caching.py:111). Bei geänderter Analyse-Logik: `CACHE_VERSION` [caching.py:18](hpg_core/caching.py:18) hochzählen → kompletter Flush |
| UI-Freeze | UI-Update aus Worker-Thread? Regel: NUR Signale. Progress ist auf 100ms gedrosselt [main.py:319-330](main.py:319) |
| Preview-Clip fehlt | `clip_error`-Signal + Subprocess-Timeout prüfen; Renderer-Kette siehe hpg-mixpoint-engineering Skill |

## Cache-Regeln

- Geschützt (nie editieren/löschen ohne Ankündigung): `track_cache.*`, `hpg_cache_v*.db`, `*.lock`.
- Versions-Mismatch → automatischer `DELETE FROM cache` [caching.py:97-104](hpg_core/caching.py:97).
- AI-Overrides werden im Cache persistiert — Cache-Flush verwirft auch LLM-Mixpoints.

## Common Mistakes

- Debugging mit System-Python 3.14 → numba-Fehler, die wie Code-Bugs aussehen.
- Cache nicht bedacht → "Fix wirkt nicht", obwohl Code korrekt.
- BrokenProcessPool als Bug behandeln — ist designtes Recovery, Log auf `[CRASHED/SKIPPED]` prüfen (welche Datei ist korrupt?).
- Worker-Exceptions suchen: Worker werfen nie, sie melden per `status_update` + leeres `finished([], {})` [main.py:279ff](main.py:279).
