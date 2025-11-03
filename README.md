# 🎵 Harmonic Playlist Generator (HPG) v3.0

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey.svg)]()
[![Releases](https://img.shields.io/badge/releases-latest-green.svg)](../../releases)

> **Professional DJ Tool for Harmonically Perfect Playlists**

---

## 📥 Download Latest Version

### ⚡ Windows Standalone Executable - Ready to Use!

**Latest Release: v3.0.7.1** (CPU Optimization Hotfix)

<div align="center">

### [⬇️ **DOWNLOAD HarmonicPlaylistGenerator.exe** (164 MB)](https://github.com/Crusty696/HarmonicPlaylistGenkopie_V2.0/releases/download/v3.0.7.1/HarmonicPlaylistGenerator.exe)

**No installation required • Just download and run!**

</div>

**What's New in v3.0.7.1:**
- 🔥 **HOTFIX:** Now uses full CPU capacity (8 cores on 16-core AMD Ryzen 7 7800X3D)
- ✅ Fixed workload scaling bug (was limiting to 5 cores for typical workloads)
- ✅ Smart CPU scaling (uses up to 50% of cores on high-end CPUs)
- ✅ 33-433% faster on 16+ core systems
- ✅ Maintains performance on 4-12 core systems

**Alternative Downloads:**
- All releases: [GitHub Releases Page](https://github.com/Crusty696/HarmonicPlaylistGenkopie_V2.0/releases)
- Source code: See "For Developers" section below

---

HPG is a high-performance desktop application for professional DJs that creates harmonically and rhythmically coherent playlists using advanced audio analysis and intelligent sorting algorithms. Version 3.0 introduces **4-6x faster** performance through multi-core processing and optional Rekordbox integration.

---

## 🚀 Quick Start

### For End Users (Windows)

1. **Download** [HPG_v3.0_Setup.exe](../../releases/latest)
2. **Run** the installer
3. **Launch** from Desktop icon
4. **Select** your music folder
5. **Choose** a playlist strategy
6. **Export** your optimized playlist

### For Developers

```bash
git clone https://github.com/yourusername/HarmonicPlaylistGenerator.git
cd HarmonicPlaylistGenerator
pip install -r requirements.txt
python main.py
```

---

## Highlights v3.0 OPTIMIZED EDITION

### Performance Boost
- **4-12x faster** audio analysis with smart multi-core scaling
- **Scales automatically** with CPU capabilities (up to 50% of cores)
- **12x faster** when using Rekordbox import (existing analyzed tracks)
- Thread-safe caching with file-locking for parallel processing
- Intelligent workload distribution across CPU cores

### Rekordbox Integration (NEW!)
- Import BPM, Key, and Cue Points from your Rekordbox library
- Professional-grade analysis data from Rekordbox 6/7
- Automatic hybrid key system (Camelot codes + musical notation)
- Graceful fallback to librosa when Rekordbox data unavailable
- See [REKORDBOX_IMPORT_GUIDE.md](docs/REKORDBOX_IMPORT_GUIDE.md) for details

### Dual-Format Export (NEW!)
- **M3U8 Playlist**: Universal compatibility (Rekordbox, Serato, Traktor, iTunes)
- **Rekordbox XML**: Professional DJ format with full metadata (BPM, Key, Genre)
- Automatic Camelot → Rekordbox key conversion
- See [EXPORT_USER_GUIDE.md](docs/EXPORT_USER_GUIDE.md) for details

---

## Features

### Audio Analysis
**Enhanced multi-modal audio analysis with optional Rekordbox import:**

- **BPM (Beats Per Minute)**: Precise tempo detection via librosa or Rekordbox
- **Musical Key & Camelot Code**: Harmonic key detection with Camelot wheel system
- **Energy Analysis**: RMS energy calculation for dynamic playlist progression
- **Bass Intensity**: 20-200Hz band extraction for genre-specific sorting
- **Mix Points**: Intelligent intro/outro detection for seamless transitions
- **ID3 Metadata**: Artist, Title, Genre, Album extraction via mutagen
- **Rekordbox Import**: Optional fast import from Rekordbox 6/7 database

### Advanced Playlist Generation
**10 sophisticated sorting strategies for any DJ scenario:**

#### Basic Strategies:
1. **Harmonic Flow**: Greedy harmonic compatibility (Camelot wheel)
2. **Warm-Up**: Ascending BPM progression
3. **Cool-Down**: Descending BPM progression

#### Enhanced Strategies:
4. **Harmonic Flow Enhanced**: Advanced harmonic + energy + genre compatibility
5. **Peak-Time Enhanced**: Mathematical sine wave energy curve for club sets
6. **Energy Wave Enhanced**: Alternating high/low energy pattern
7. **Consistent Enhanced**: Minimal BPM/energy jumps with harmonic preference
8. **Genre Flow**: Genre clustering with smooth transitions
9. **Emotional Journey**: Multi-phase energy progression (intro/build/peak/cool)
10. **Smart Harmonic**: Dynamic key/BPM weighting with local optimization

### Performance & Caching
- **Smart multi-core processing**: Auto-scales with CPU (up to 50% of cores)
- **Optimized for high-end CPUs**: 16+ cores see 33-433% improvement
- **SQLite caching**: File-based cache with version control (`hpg_cache_v3.dbm`)
- **Thread-safe**: File-locking system for concurrent access
- **Smart invalidation**: Automatic cache refresh on file changes (path, size, mtime)
- **Rekordbox caching**: In-memory cache of 2000+ tracks for instant lookup

### Export Options
- **M3U8 Playlist**: Standard format with UTF-8 encoding
- **Rekordbox XML**: Professional DJ format with full metadata
- **Dual export dialog**: Choose format based on your workflow

---

## Installation

### Prerequisites
- **Python 3.9+** (3.11 recommended)
- **Windows 10/11** (tested), macOS, or Linux
- **4+ CPU cores** recommended for optimal multi-core performance
- **Rekordbox 6 or 7** (optional, for Rekordbox import feature)

### Setup

1. **Clone the repository:**
   ```bash
   git clone <repository_url>
   cd HarmonicPlaylistGenkopie_V2.0
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv venv
   ```

3. **Activate virtual environment:**
   - Windows:
     ```bash
     .\venv\Scripts\activate
     ```
   - macOS/Linux:
     ```bash
     source venv/bin/activate
     ```

4. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

5. **Optional: Install Rekordbox integration:**
   ```bash
   pip install pyrekordbox
   ```
   *Note: Rekordbox 6/7 must be installed with analyzed tracks*

---

## Quick Start

### Basic Usage

1. **Launch HPG:**
   ```bash
   python main.py
   ```

2. **Select Music:**
   - Drag & drop your music folder onto the window, OR
   - Click "Select Music Folder" button

3. **Configure:**
   - Choose playlist strategy (e.g., "Harmonic Flow Enhanced")
   - Adjust BPM tolerance (default: 3.0 BPM)

4. **Analyze:**
   - HPG automatically analyzes all tracks
   - Progress bar shows real-time status
   - **NEW**: Rekordbox tracks analyzed in ~0.3s (vs. ~3.6s with librosa)

5. **Review & Export:**
   - Sorted playlist displayed with quality metrics
   - Export as M3U8 or Rekordbox XML
   - Ready to import into your DJ software!

### Performance Benchmark

Run the included benchmark to test your system:
```bash
python performance_benchmark.py "path/to/your/music"
```

**Expected Results (50 tracks, 16-core CPU):**
- **Sequential**: ~180 seconds (3.6s/track)
- **Multi-core (6 workers)**: ~38 seconds (0.76s/track) - **4.7x faster**
- **With Rekordbox**: ~15 seconds (0.3s/track) - **12x faster**

---

## Technology Stack

### Core Technologies
- **Python 3.9+**: Main programming language
- **PyQt6**: Modern GUI framework with Material Design
- **librosa**: Professional-grade audio analysis
- **numpy**: High-performance numerical computing

### Audio Processing
- **librosa**: BPM, key, energy, beat tracking
- **mutagen**: ID3 tag extraction (MP3, FLAC, WAV, AIFF)
- **pyrekordbox** (optional): Rekordbox 6/7 database import

### Performance
- **multiprocessing**: Multi-core parallel processing
- **ProcessPoolExecutor**: Thread-safe workload distribution
- **sqlite3/shelve**: High-performance caching with file-locking
- **fcntl/msvcrt**: Platform-specific file locking

### Export
- **M3U8**: Standard playlist format (UTF-8)
- **pyrekordbox** (optional): Rekordbox XML generation

---

## Performance Comparison

### Audio Analysis Speed

| Scenario | Method | Time (50 tracks) | Speedup |
|----------|--------|------------------|---------|
| **Old v2.0** | Single-core librosa | ~180s | Baseline |
| **v3.0 Multi-core** | 6-core librosa | ~38s | **4.7x faster** |
| **v3.0 + Rekordbox** | Import from RB | ~15s | **12x faster** |

### Scaling Test (Multi-core)

| Tracks | Sequential | 6 Cores | Speedup |
|--------|-----------|---------|---------|
| 10 | 36s | 10s | 3.6x |
| 50 | 180s | 38s | 4.7x |
| 100 | 380s | 75s | 5.1x |

*Tested on Windows 11, Intel i7-12700 (16 cores)*

---

## Supported Audio Formats

### Fully Supported
- **WAV** (Waveform Audio File Format) - Native, fastest
- **AIFF** (Audio Interchange File Format) - Native, macOS standard
- **MP3** (MPEG Audio Layer 3) - Via librosa
- **FLAC** (Free Lossless Audio Codec) - Via librosa

### Sample Rates
- 44.1 kHz (CD quality) - Recommended
- 48 kHz (Studio standard)
- 96 kHz (High-res audio)
- 192 kHz (Audiophile)

*All sample rates automatically resampled to 22.05 kHz for analysis*

---

## Project Structure

```
HarmonicPlaylistGenkopie_V2.0/
├── main.py                          # PyQt6 GUI application
├── hpg_core/                        # Core analysis modules
│   ├── analysis.py                  # Audio analysis engine
│   ├── playlist.py                  # Playlist generation algorithms
│   ├── models.py                    # Track data model
│   ├── caching.py                   # SQLite cache with file-locking
│   ├── parallel_analyzer.py         # Multi-core processing (NEW!)
│   ├── caching_threadsafe.py        # Thread-safe cache (NEW!)
│   ├── rekordbox_importer.py        # Rekordbox integration (NEW!)
│   └── exporters/                   # Export modules (NEW!)
│       ├── base_exporter.py
│       ├── m3u8_exporter.py
│       └── rekordbox_xml_exporter.py
├── tests/                           # Comprehensive test suite
│   └── test audio files/            # Test audio samples
├── docs/                            # Documentation
│   ├── REKORDBOX_IMPORT_GUIDE.md    # Rekordbox integration guide
│   ├── EXPORT_USER_GUIDE.md         # Export format guide
│   ├── OPTIMIZATION_README.md       # Multi-core optimization details
│   └── QUICK_START.md               # Getting started guide
├── performance_benchmark.py         # Performance testing tool (NEW!)
├── test_rekordbox_integration.py    # Rekordbox tests (NEW!)
├── requirements.txt                 # Python dependencies
└── README.md                        # This file
```

---

## Configuration

### Multi-core Settings
Smart auto-scaling is enabled by default. To customize:

Edit `hpg_core/parallel_analyzer.py`:
```python
# Smart allocation (default):
# Small CPUs (≤12 cores): up to 6 cores
# Large CPUs (>12 cores): up to 50% of cores

TIMEOUT_PER_TRACK = 60  # Timeout per track in seconds
```

### BPM Tolerance
Adjust in GUI or modify default in `main.py`:
```python
DEFAULT_BPM_TOLERANCE = 3.0  # BPM range for compatibility
```

### Cache Location
Cache files stored in project root:
- `hpg_cache_v3.dbm.*` - Main analysis cache
- `rekordbox_cache/` - Rekordbox import cache (in-memory)

---

## Troubleshooting

### Performance Issues

**Problem:** Analysis is slow
**Solutions:**
1. Check CPU usage - should use 50-80% with multi-core (smart scaling active)
2. Verify cache is working: check `hpg_cache_v3.dbm.dat` size
3. Install pyrekordbox for 12x speedup on Rekordbox tracks
4. Close other CPU-intensive applications
5. **High-end CPUs**: v3.0.7+ automatically uses up to 50% of cores

**Problem:** Worker crashes or timeouts
**Solutions:**
1. Smart scaling automatically adjusts based on CPU
2. Increase `TIMEOUT_PER_TRACK` to 120 seconds if needed
3. Check for corrupted audio files (timeout messages)
4. Ensure adequate RAM (2GB+ free)

### Rekordbox Integration

**Problem:** "pyrekordbox not installed"
**Solution:**
```bash
pip install pyrekordbox
```

**Problem:** "Rekordbox database loaded: 0 tracks"
**Solutions:**
1. Install Rekordbox 6 or 7
2. Import and analyze tracks in Rekordbox
3. Restart HPG
4. Check database: `%APPDATA%\Pioneer\rekordbox\master.db`

**Problem:** Tracks not matching
**Causes:** File paths differ between Rekordbox and HPG
**Solutions:**
- Use same drive letter (C:\ not D:\)
- HPG tries filename-only matching as fallback
- See [REKORDBOX_IMPORT_GUIDE.md](docs/REKORDBOX_IMPORT_GUIDE.md)

### Export Issues

**Problem:** "Export failed: pyrekordbox not installed"
**Solution:** Rekordbox XML export requires pyrekordbox:
```bash
pip install pyrekordbox
```

**Problem:** Keys look wrong in Rekordbox
**Solution:** This is expected - Rekordbox uses different notation than Camelot
- HPG: 8A (A minor)
- Rekordbox: Am
- Conversion is automatic!

---

## Development

### Running Tests
```bash
# All tests
pytest

# Specific test categories
pytest -m unit                  # Fast unit tests
pytest -m integration           # Integration tests
pytest -m performance_test      # Performance benchmarks

# With coverage
pytest --cov=hpg_core --cov-report=html
```

### Benchmark Suite
```bash
# Quick benchmark (21 test tracks)
python performance_benchmark.py "tests/test audio files"

# Full benchmark (your music library)
python performance_benchmark.py "/path/to/your/music"
```

### Code Quality
```bash
# Format code
black hpg_core/ tests/

# Lint code
pylint hpg_core/

# Type checking
mypy hpg_core/
```

---

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Run tests (`pytest`)
4. Commit changes (`git commit -m 'Add amazing feature'`)
5. Push to branch (`git push origin feature/amazing-feature`)
6. Open a Pull Request

### Development Guidelines
- Follow PEP 8 style guide
- Add tests for new features
- Update documentation
- Maintain backward compatibility
- Use type hints

---

## Roadmap

### Planned for v3.1
- [ ] Cue point integration (use Rekordbox Mix In/Out directly)
- [ ] Rekordbox playlist import/export
- [ ] Advanced filtering (rating, color, genre)
- [ ] Batch processing multiple folders
- [ ] Cloud sync for cache

### Planned for v3.2+
- [ ] Serato/Traktor database import
- [ ] AI-powered track similarity
- [ ] Real-time BPM adjustment preview
- [ ] Waveform visualization
- [ ] Streaming service integration

---

## Known Limitations

### v3.0
1. **Cue Points**: Imported from Rekordbox but not yet used in mix point detection
   - **Status**: Planned for v3.1
   - **Workaround**: HPG calculates mix points using librosa

2. **Multi-core on macOS/Linux**: File-locking uses different APIs
   - **Status**: Works but not extensively tested
   - **Workaround**: Sequential mode always available

3. **Rekordbox 5.x**: Not officially supported
   - **Status**: May work but not tested
   - **Workaround**: Upgrade to Rekordbox 6 or 7

---

## Credits & Acknowledgments

### Core Libraries
- **librosa** - Audio analysis foundation
- **PyQt6** - Modern GUI framework
- **pyrekordbox** - Rekordbox database access
- **numpy** - Numerical computing

### Algorithms
- Camelot Wheel System - Mark Davis (Mixed In Key)
- Beat tracking - librosa (`beat.beat_track`)
- Key detection - Krumhansl-Schmuckler algorithm

### Inspiration
- Mixed In Key - Harmonic mixing pioneer
- Rekordbox - Industry-standard DJ software
- Serato DJ - Playlist workflow design

---

## License

**MIT License**

Copyright (c) 2025 Harmonic Playlist Generator

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---

## 🔨 Building from Source

### Build Standalone Executable (Windows)

```bash
# 1. Create application icon (optional)
python create_icon.py

# 2. Build executable (~164 MB)
build.bat

# Result: HarmonicPlaylistGenerator.exe
```

### Build Windows Installer (Professional Distribution)

```bash
# Prerequisites: Inno Setup 6 (https://jrsoftware.org/isdl.php)

# 1. Build executable first
build.bat

# 2. Build installer
build_installer.bat

# Result: installer_output/HPG_v3.0_Setup.exe
```

### Full Documentation

See [BUILD_INSTRUCTIONS.md](BUILD_INSTRUCTIONS.md) for:
- Detailed build process
- Icon creation guide
- Troubleshooting
- Distribution checklist
- Advanced configuration

---

## Support & Documentation

### User Guides
- [Rekordbox Import Guide](docs/REKORDBOX_IMPORT_GUIDE.md) - Complete Rekordbox integration guide
- [Export User Guide](docs/EXPORT_USER_GUIDE.md) - M3U8 and Rekordbox XML export
- [Quick Start Guide](docs/QUICK_START.md) - Getting started quickly
- [Optimization Guide](docs/OPTIMIZATION_README.md) - Multi-core performance details

### Technical Documentation
- [CLAUDE.md](CLAUDE.md) - Developer documentation for Claude Code
- [Implementation Summaries](docs/) - Detailed technical summaries

### Getting Help
- **Issues**: Report bugs via GitHub Issues
- **Discussions**: Feature requests and questions
- **Documentation**: Check `docs/` folder for detailed guides

---

**Version 3.0.7 SMART SCALING EDITION - January 2025**

*Professional DJ tool for harmonically perfect playlists*
*4-12x faster with smart multi-core scaling | 12x faster with Rekordbox integration*
