# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# HPG – Harmonic Playlist Generator V2.0

## Projektarchitektur

`
main.py                    # PyQt6 GUI (~1600 Zeilen), QThread-Worker-Muster
hpg_core/                  # Core analysis modules
  models.py                # Track-Dataclass (25+ Felder), TrackSection
  analysis.py              # Audio-Analyse (librosa): BPM, Key, Energy, Sections
  config.py                # Alle konfigurierbaren Konstanten
  caching.py               # shelve-basierter Cache
  parallel_analyzer.py     # ProcessPoolExecutor fuer Multi-Core Analyse
  genre_classifier.py      # Genre-Erkennung (regelbasiert, kein ML)
  structure_analyzer.py    # Track-Struktur (Intro/Verse/Drop/Outro)
  dj_brain.py              # Genre-spezifische Mix-Logik
  playlist.py              # Playlist-Generierung und Scoring
  rekordbox_importer.py    # Rekordbox-Datenbank Import (optional)
  exporters/               # m3u8, Rekordbox XML Export
tests/                     # pytest (725+ Tests), Integrationstests
tools/                     # Hilfsskripte (Manual Test, Genre Check, Cache Inspection)
docs/                      # Dokumentationen, Algorithmus-Erklaerungen, Quick-Start
plans/                     # Entwicklungsplaene und Roadmaps
scripts/                   # Build- und Utility-Skripte
`

## Python-Pfad (WICHTIG!)

- **Echtes Python:** `C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe`
- In Bash-Tool: `powershell -Command "& 'C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe' ..."`

## Tests ausfuehren

`ash
powershell -Command "Set-Location 'C:\Users\david\Dokumente\HarmonicPlaylistGenkopie_V2.0-main'; & 'C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/ --tb=short -q"
`

## Coding-Konventionen

- 2 Leerzeichen Einrueckung (keine Tabs)
- Kommentare auf **Deutsch**
- UI-Updates NUR im Main-Thread
- Hilfsskripte aus `tools/` muessen den Parent-Pfad zu `sys.path` hinzufuegen

## Geschuetzte Dateien (NICHT editieren)

- `track_cache.*`, `hpg_cache_v10.*` – Cache-Dateien
- `*.lock`, `*.coverage` – System-Dateien

## Analyse-Pipeline
1. **Rekordbox Fast-Path**: Nutzt existierende Metadaten.
2. **Vollstaendige Librosa-Analyse**: Volle Audio-Analyse falls Metadaten fehlen.
