# 🎵 Harmonic Playlist Generator v3.0

**Multi-Core Optimized DJ Playlist Generator**

## ✨ What's New in v3.0

### ⚡ Performance Improvements
- **4-6x faster audio analysis** with multi-core processing
- Parallel processing using up to 6 CPU cores
- Thread-safe caching system with file-locking
- Intelligent workload distribution

### 🎯 New Features
- Real-time performance monitoring
- Comprehensive benchmark suite
- Cache-hit optimization (~95%+ speedup on re-analysis)
- Robust error handling for corrupted files
- Timeout protection (60s per track)
- Memory-efficient chunk processing

### 🔧 Technical Improvements
- Enhanced Rekordbox XML integration
- Improved compatibility with Windows 11
- Better error messages and user feedback
- Graceful degradation on worker crashes

## 📥 Installation

### Windows 10/11 (64-bit)

**One-Click Installation:**
1. Download `HarmonicPlaylistGenerator.exe`
2. Run the executable (no installation required!)
3. Select your music folder
4. Start generating playlists!

**Size:** ~7.9 MB (all dependencies included)

## 🚀 Quick Start

1. **Launch** the application
2. **Import** your music library or Rekordbox XML
3. **Analyze** your tracks (multi-core processing!)
4. **Generate** harmonic playlists
5. **Export** to M3U/M3U8 format

## 📊 Performance Benchmarks

- **50 tracks:** 180s → 38s (4.7x speedup)
- **100 tracks:** 380s → 75s (5.1x speedup)
- **Parallel processing** via ProcessPoolExecutor
- **Cache-hit optimization** for previously analyzed tracks

## 🐛 Bug Fixes

- Fixed PyQt6 missing in standalone build
- Resolved dependency issues in GitHub Actions
- Improved build script reliability
- Better error handling for missing audio files

## 📝 System Requirements

- **OS:** Windows 10/11 (64-bit)
- **RAM:** 4GB minimum, 8GB recommended
- **CPU:** Multi-core processor recommended
- **Storage:** 500MB free space

## 🔗 Links

- [GitHub Repository](https://github.com/Crusty696/HarmonicPlaylistGenkopie_V2.0)
- [Report Issues](https://github.com/Crusty696/HarmonicPlaylistGenkopie_V2.0/issues)
- [Documentation](https://github.com/Crusty696/HarmonicPlaylistGenkopie_V2.0#readme)

## 📜 License

Open Source - See LICENSE file for details

---

**Generated with Claude Code** 🤖
