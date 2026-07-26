# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

# HPG � Harmonic Playlist Generator V2.0

## Projektarchitektur

`
main.py                    # PyQt6 GUI (~1600 Zeilen), QThread-Worker-Muster
hpg_core/                  # Core analysis modules
  models.py                # Track-Dataclass (25+ Felder), TrackSection
  analysis.py              # Audio-Analyse (librosa): BPM, Key, Energy, Sections
  config.py                # Alle konfigurierbaren Konstanten
  genres.py                # Single Source of Truth: alle Genre-Tabellen + Drift-Validierung
  caching.py               # SQLite-basierter Cache (WAL, hpg_cache_v24.db)
  parallel_analyzer.py     # ProcessPoolExecutor fuer Multi-Core Analyse
  genre_classifier.py      # Genre-Erkennung (regelbasiert, kein ML)
  structure_analyzer.py    # Track-Struktur (Intro/Verse/Drop/Outro)
  dj_brain.py              # Genre-spezifische Mix-Logik
  playlist.py              # Playlist-Generierung und Scoring
  rekordbox_importer.py    # Rekordbox-Datenbank Import (optional)
  exporters/               # m3u8, Rekordbox XML Export
tests/                     # pytest (1200+ Tests), Integrationstests
tools/                     # Hilfsskripte (Manual Test, Genre Check, Cache Inspection)
docs/                      # Dokumentationen, Algorithmus-Erklaerungen, Quick-Start
docs/archive/              # Erledigte Plaene und historische Dokumente
`

## Python-Pfad (WICHTIG!)

- **Echtes Python:** `C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe`
- Im Projekt: `.` + `\venv312\Scripts\python.exe` verwenden.

## Tests ausfuehren

`ash
.\venv312\Scripts\python.exe -m pytest tests/ --tb=short -q
`

## Coding-Konventionen

- 2 Leerzeichen Einrueckung (keine Tabs)
- Kommentare auf **Deutsch**
- UI-Updates NUR im Main-Thread
- Hilfsskripte aus `tools/` muessen den Parent-Pfad zu `sys.path` hinzufuegen

## Geschuetzte Dateien (NICHT editieren)

- `track_cache.*`, `hpg_cache_v*.db`, `*.lock`, `*.coverage` – Cache-/System-Dateien

## Analyse-Pipeline
1. **Rekordbox Fast-Path**: Nutzt existierende Metadaten.
2. **Vollstaendige Librosa-Analyse**: Volle Audio-Analyse falls Metadaten fehlen.
