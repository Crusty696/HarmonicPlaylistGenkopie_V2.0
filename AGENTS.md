# AGENTS.md

## OpenClaw-Hochpraezisionsmodus

Dieser Ordner ist der Workspace des OpenClaw-Agenten `hpg`. Arbeite nur an
dem vom Auftrag betroffenen Teil des Repositories. `Claude-Autopilot-v5/`,
`Claude-Autopilot-v6/` und `Claude-Autopilot-v6.zip` sind bestehende,
ungetrackte Benutzerartefakte: nie aendern, verschieben, stagen oder in einen
Commit aufnehmen.

Vor jeder nichttrivialen Aenderung zuerst `hpg-orientation` und danach den
passenden HPG-Skill laden. Die Fachrollen liegen unter `.agents/agents/`:

- Audio/Analyse: `hpg-analyse`; Mixpunkte/Paarung: `hpg-mixpoints`;
  Scoring/Strategien: `hpg-scoring`; Cache: `hpg-cache`.
- PyQt6 und `main.py`: `hpg-gui`; Rekordbox: `hpg-rekordbox`; Rendering:
  `hpg-render`; Tests: `hpg-tests`; Messung/Statistik: `hpg-statistik`.
- Vor der Umsetzung und vor jedem Commit muss ein unabhaengiger,
  schreibgeschuetzter Pruefdurchgang nach `.agents/agents/hpg-waechter.md`
  erfolgen. Sein Urteil ist DURCHGEWUNKEN, MIT AUFLAGEN oder
  ZURUECKGEWIESEN.

Parallelisiere nur voneinander unabhaengige Recherche-, Review- oder
Testvorbereitung. Starte nie zwei volle pytest-Laeufe gleichzeitig: `pytest`
nutzt bereits `-n auto`. Fuer Abschlussbelege immer
`venv312\Scripts\python.exe -m pytest tests/ --tb=short -q` verwenden;
`--no-cov` ist nur fuer den lokalen Entwicklungszyklus erlaubt.

Bei Analyse-, Mixpoint-, Cache-, Genre- oder GUI-Aenderungen die in den
Fach-Skills definierten Invarianten explizit pruefen. Kein Abschluss ohne
Testbeleg, keine unbelegte Erfolgsmeldung, keine Aenderung von Cache-,
Datenbank-, Lock- oder Coverage-Dateien.

This file provides guidance to Codex when working with code in this repository.

# HPG - Harmonic Playlist Generator (v3.7.2)

## Projekt-Skills zuerst laden

Fuer dieses Repo existieren projekt-lokale Experten-Skills mit dem
verifizierten Ist-Stand. Sie liegen unter `.claude/skills/` (Claude Code)
bzw. `.agents/skills/` (Codex). Bei HPG-Arbeit zuerst `hpg-orientation`
laden, danach den fachlich passenden Skill:

`hpg-orientation`, `hpg-debugging`, `hpg-audio-analysis`,
`hpg-mixpoint-engineering`, `hpg-playlist-scoring`, `hpg-genres`,
`hpg-cache-persistence`, `hpg-parallel-performance`, `hpg-qt-gui`,
`hpg-transition-render`, `hpg-rekordbox`, `hpg-testing-verification`,
`hpg-release-build`, `hpg-audit-optimize`.

Regel: Statusdokumente sind Hypothesen, der Code ist die Wahrheit. Jede
Behauptung aus einem Markdown vor Gebrauch im Code nachpruefen.

## Projektarchitektur

```
main.py                    # PyQt6 GUI, QThread-Worker-Muster
hpg_core/                  # Core analysis modules
  models.py                # Track-Dataclass, Camelot-Map, TrackSection
  analysis.py              # Audio-Analyse (librosa): BPM, Key, Energy, Sections
  downbeat.py              # Downbeat- und Phrasen-Anker
  config.py                # Alle konfigurierbaren Konstanten
  genres.py                # Single Source of Truth: 9 kanonische Genres + Drift-Validierung
  caching.py               # SQLite-Cache (WAL), CACHE_VERSION 44
  parallel_analyzer.py     # ProcessPoolExecutor fuer Multi-Core Analyse
  genre_classifier.py      # Genre-Erkennung (regelbasiert, kein ML)
  structure_analyzer.py    # Track-Struktur (Intro/Breakdown/Drop/Outro)
  dj_brain.py              # Genre-spezifische Mix-Logik, Mixpoints
  playlist.py              # Playlist-Generierung und Scoring (STRATEGIES)
  transition_renderer.py   # Uebergangs-Preview (Crossfade, EQ, Limiter)
  rekordbox_importer.py    # Rekordbox-Datenbank Import (optional)
  ai_engine.py             # Optionales lokales LLM (nur Mood/Subgenre, kein Audio)
  ai_launcher.py           # Erkennung/Start von Ollama bzw. LM Studio
  theme.py                 # Farben und Styles der GUI
  playlist_security.py     # Pfad-Sanitizing und Playlist-Validierung
  resource_limits.py       # Groessen-/Dauer-/Anzahl-Limits
  error_reporter.py        # JSON-Fehlersenke logs/error_report.json
  logging_config.py        # Logging-Setup
  app_metadata.py          # APP_VERSION, MIN_PYTHON (Single Source)
  exporters/               # m3u8, Rekordbox XML Export
tests/                     # pytest (3537 bestanden, 85,80 % Coverage; 2026-08-31)
tools/                     # Hilfsskripte (Manual Test, Genre Check, Cache Inspection)
docs/                      # Dokumentationen, Algorithmus-Erklaerungen, Quick-Start
docs/archive/              # Erledigte Plaene und historische Dokumente
```

Es gibt kein `ui/`-Paket, keinen `GUI/`-Ordner und kein `theme.py` im
Wurzelverzeichnis — die gesamte GUI liegt in `main.py`, das Theme in
`hpg_core/theme.py`.

## Playlist-Strategien

Genau 8, registriert in `hpg_core/playlist.py` (`STRATEGIES`):
Harmonic Flow, Warm-Up, Cool-Down, Peak-Time, Energy Wave, Genre Flow,
Consistent, Context Flow. GUI-Default: Harmonic Flow.

Drei Altnamen bleiben ueber `STRATEGY_ALIASES` gueltig (gespeicherte
Settings, Cache-Metadaten): "Harmonic Flow Enhanced" -> Harmonic Flow,
"Peak-Time Enhanced" -> Peak-Time, "Emotional Journey" -> Context Flow.

## Python-Pfad (WICHTIG!)

- Python 3.12 zwingend, mindestens 3.12.1 (`MIN_PYTHON` in
  `hpg_core/app_metadata.py`). Kein 3.13+ — numba unterstuetzt es nicht.
- Projekt-venv: `.\venv312\Scripts\python.exe` (aktuell Python 3.12.10).

## Tests ausfuehren

```bash
.\venv312\Scripts\python.exe -m pytest tests/ --tb=short -q
```

`pytest.ini` setzt bereits `-n auto`, Coverage auf `hpg_core` und `main`
sowie `--cov-fail-under=70`. Fuer schnelle Laeufe `--no-cov` anhaengen.

## Coding-Konventionen

- Einrueckung: die des bearbeiteten Files fortsetzen. `main.py`,
  `hpg_core/analysis.py` und `hpg_core/playlist.py` nutzen 4 Leerzeichen,
  neuere Dateien wie `hpg_core/theme.py` und neuere Tests 2. Keine Tabs.
- Kommentare auf **Deutsch**
- UI-Updates NUR im Main-Thread
- Hilfsskripte aus `tools/` muessen den Parent-Pfad zu `sys.path` hinzufuegen

## Geschuetzte Dateien (NICHT editieren)

- `hpg_cache_v*.db`, `*.db-wal`, `*.db-shm`, `*.lock`, `*.coverage` —
  Cache-/System-Dateien. Der Laufzeit-Cache liegt ausserhalb des Repos unter
  `%LOCALAPPDATA%\HPG\hpg_cache_v44.db` (ueberschreibbar mit `HPG_CACHE_DIR`
  bzw. `HPG_CACHE_FILE`).

## Analyse-Pipeline

1. **Cache-Lookup** (Rekordbox-Signatur -> Cache-Key) — passiert **vor** der Analyse.
2. **Rekordbox Fast-Path**: Nutzt existierende Metadaten (BPM/Key/Beatgrid).
3. **Vollstaendige Librosa-Analyse**: Volle Audio-Analyse falls Metadaten fehlen.
4. Downbeat -> Phrasen-Anker -> Struktur -> Mixpoints entstehen innerhalb von
   `analyze_track`, nicht in einem spaeteren Schritt.
