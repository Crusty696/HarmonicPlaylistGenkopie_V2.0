# Harmonic Playlist Generator (HPG) v3.7.2

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12.1+](https://img.shields.io/badge/python-3.12.1+-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey.svg)]()

> **Professional DJ Tool for Harmonically Perfect Playlists**

---

## Download

### Windows Standalone Executable

**Latest Release: v3.7.2**

[**DOWNLOAD HarmonicPlaylistGenerator.exe**](https://github.com/Crusty696/HarmonicPlaylistGenkopie_V2.0/releases/latest/download/HarmonicPlaylistGenerator.exe)

**No installation required - Just download and run!**

---

## Features

### Audio Analysis
- **BPM Detection**: Precise tempo detection via librosa or Rekordbox
- **Musical Key & Camelot Code**: Harmonic key detection with Camelot wheel
- **Energy Analysis**: RMS energy calculation for dynamic playlist progression
- **Bass Intensity**: 20-200Hz band extraction for genre-specific sorting
- **Genre Classification**: Rule-based genre detection from audio features
- **Structure Analysis**: Track section detection (Intro, Breakdown, Drop, Outro)
- **DJ Brain**: Genre-specific mix point calculation with phrase alignment
- **Mix Points**: Intelligent intro/outro detection for seamless transitions
- **ID3 Metadata**: Artist, Title, Genre, Album extraction via mutagen
- **Rekordbox Import**: Optional fast import from Rekordbox 6/7 database

### Playlist Strategies
8 sorting strategies:

1. **Harmonic Flow** - Greedy harmonic compatibility (Camelot wheel)
2. **Warm-Up** - Ascending BPM progression
3. **Cool-Down** - Descending BPM progression
4. **Peak-Time** - Adjustable peak placement with harmonic smoothing
5. **Energy Wave** - Alternating high/low energy pattern
6. **Genre Flow** - Genre clustering with smooth transitions
7. **Consistent** - Minimal BPM/energy jumps with harmonic preference
8. **Context Flow** - Phase-aware energy, trend and genre-fatigue objective

### Optional local LLM enrichment

Ollama or LM Studio can optionally add validated Mood/Subgenre metadata after the deterministic playlist is ready. This feature is disabled by default, does not analyze audio, and is not required for playlist generation.

### Performance
- **4-12x faster** audio analysis with smart multi-core scaling
- **Scales automatically** with CPU capabilities (up to 50% of cores)
- **12x faster** when using Rekordbox import
- Thread-safe caching with file-locking for parallel processing

### Export
- **M3U8 Playlist** - Universal compatibility (Rekordbox, Serato, Traktor, iTunes)
- **Rekordbox XML** - Professional DJ format with full metadata (BPM, Key, Genre)

---

## Installation (Developers)

### Prerequisites
- Python 3.12.1+ (3.12.10 tested)
- Windows 10/11

### Setup

```bash
git clone https://github.com/Crusty696/HarmonicPlaylistGenkopie_V2.0.git
cd HarmonicPlaylistGenkopie_V2.0
pip install -r requirements.txt
python main.py
```

Rekordbox integration is optional at runtime. The full developer requirements
include its package; a lean installation can omit that line from
`requirements.txt` and the app will continue with the librosa path:
```bash
pip install pyrekordbox
```

---

## Project Structure

```
HarmonicPlaylistGenkopie_V2.0/
├── main.py                          # PyQt6 GUI application
├── Start.bat                        # App-Starter (Doppelklick)
├── hpg_core/                        # Core analysis modules
│   ├── analysis.py                  # Audio analysis engine
│   ├── caching.py                   # Cache with file-locking
│   ├── config.py                    # Configurable constants
│   ├── dj_brain.py                  # Genre-specific mix logic
│   ├── genre_classifier.py          # Rule-based genre detection
│   ├── models.py                    # Track data model & Camelot map
│   ├── parallel_analyzer.py         # Multi-core processing
│   ├── playlist.py                  # Playlist generation algorithms
│   ├── rekordbox_importer.py        # Rekordbox integration
│   ├── structure_analyzer.py        # Track structure detection
│   └── exporters/                   # Export modules
│       ├── base_exporter.py
│       ├── m3u8_exporter.py
│       └── rekordbox_xml_exporter.py
├── tests/                           # pytest unit/integration suite
├── requirements.txt                 # Python dependencies
├── pytest.ini                       # Test configuration
├── build.bat                        # Build standalone .exe
├── build_installer.bat              # Build Windows installer
├── HPG.spec                         # PyInstaller spec
├── installer.iss                    # Inno Setup script
├── icon.ico                         # Application icon
├── version_info.txt                 # Windows version info
├── LICENSE                          # MIT License
└── README.md                        # This file
```

---

## Running Tests

```bash
pytest
```

---

## Building from Source

### Standalone Executable (Windows)

```bash
build.bat
```

### Windows Installer

Requires [Inno Setup 6](https://jrsoftware.org/isdl.php):

```bash
build.bat
build_installer.bat
```

---

## Supported Audio Formats

- **MP3** - Via librosa
- **WAV** - Native, fastest
- **FLAC** - Free Lossless Audio Codec
- **AIFF** - Audio Interchange File Format

---

## License

MIT License - See [LICENSE](LICENSE) for details.
