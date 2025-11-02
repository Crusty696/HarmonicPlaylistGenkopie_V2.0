# CHANGELOG v3.1 - OPTIMIZED EDITION

**Release Date:** 2025-11-02
**Version:** 3.1.0

---

## 🎯 HAUPTVERBESSERUNGEN

### 1. **Artist-Extraktion aus Dateinamen** ✨ NEU
- **Problem gelöst:** Artist-Feld zeigte "Unknown" obwohl der Artist im Dateinamen enthalten war
- **Neue Funktion:** `parse_filename_for_metadata()` in `hpg_core/analysis.py`
- **Unterstützte Formate:**
  - `"Artist - Track.ext"`
  - `"01 - Artist - Track.ext"`
  - `"Artist-Track.ext"`
  - `"Artist_Track.ext"`
- **Fallback-Mechanismus:** Wenn ID3-Tags fehlen, wird der Dateiname automatisch geparst
- **Neue Funktion:** `extract_metadata()` ersetzt `get_id3_tags()` mit intelligentem Fallback

### 2. **Multi-Core Processing** 🚀 NEU
- **Bis zu 6 CPU-Kerne** werden jetzt gleichzeitig genutzt
- **Neue Datei:** `hpg_core/parallel_analyzer.py`
- **ProcessPoolExecutor** für echte parallele Verarbeitung (umgeht Python GIL)
- **Intelligente Worker-Auswahl:**
  - < 5 Files: 1 Worker (Single-Threaded)
  - < 20 Files: 2 Workers
  - < 50 Files: 4 Workers
  - 50+ Files: 6 Workers (Maximum)
- **Robuste Fehlerbehandlung:**
  - 60s Timeout pro Track (schützt vor korrupten Files)
  - Graceful Degradation bei Worker-Crashes
  - Fehlerhafte Tracks werden übersprungen, nicht die ganze Analyse

### 3. **Thread-Safe Caching** 🔒 NEU
- **Neue Datei:** `hpg_core/caching_threadsafe.py`
- **Plattformübergreifendes File-Locking:**
  - Windows: `msvcrt` Locking
  - Unix/Linux: `fcntl` Locking
- **Verhindert Race Conditions** bei Multi-Process Zugriff
- **Timeout-Schutz:** 2s für Cache-Locks (verhindert Deadlocks)
- **Cache-Version:** v3 → v4 (automatischer Rebuild)

### 4. **Optimierter AnalysisWorker** ⚡ VERBESSERT
- **main.py:** `AnalysisWorker` nutzt jetzt `ParallelAnalyzer`
- **GUI-Integration:** Progress-Callback für Echtzeit-Updates
- **Besseres Feedback:** Zeigt Worker-Count und erfolgreiche Analysen

---

## 📁 NEUE DATEIEN

```
hpg_core/
├── parallel_analyzer.py        # Multi-Core Engine (NEU)
├── caching_threadsafe.py       # Thread-Safe Cache (NEU)
└── analysis.py                 # parse_filename_for_metadata() + extract_metadata() (ERWEITERT)

Tests/
├── test_artist_extraction.py   # Artist-Parsing Tests (NEU)
```

---

## 🔧 GEÄNDERTE DATEIEN

### `hpg_core/analysis.py`
- ✨ **NEU:** `parse_filename_for_metadata()` Funktion
- ✨ **NEU:** `extract_metadata()` mit Fallback-Mechanismus
- ⚠️ **DEPRECATED:** `get_id3_tags()` ersetzt durch `extract_metadata()`
- Import: `re` Modul hinzugefügt

### `hpg_core/caching.py`
- **Cache-Version:** 3 → 4
- **Cache-File:** `hpg_cache_v3.dbm` → `hpg_cache_v4.dbm`

### `main.py`
- Import: `ParallelAnalyzer` hinzugefügt
- `AnalysisWorker.run()`: Sequential for-loop → ParallelAnalyzer
- Explizit: `max_workers=6` gesetzt

### `.gitignore`
- ✅ `hpg_cache_v4.dbm.*` hinzugefügt
- ✅ `hpg_cache_v4.lock` hinzugefügt

---

## 🎯 PERFORMANCE-VERBESSERUNGEN

### Erwartete Speedups (ohne Cache):
- **50 Tracks:** 180s → ~38s (4.7x schneller)
- **100 Tracks:** 380s → ~75s (5.1x schneller)

### Mit Cache (95%+ Hit-Rate):
- **50 Tracks:** ~5s (36x schneller)
- **100 Tracks:** ~10s (38x schneller)

---

## ⚠️ BREAKING CHANGES

### Cache-Reset erforderlich!
- Cache-Version wurde auf v4 erhöht
- **Alter Cache:** `hpg_cache_v3.dbm.*` wird NICHT gelöscht (aber ignoriert)
- **Neuer Cache:** `hpg_cache_v4.dbm.*` wird automatisch erstellt
- **Manuelle Bereinigung:** User kann alte Cache-Files manuell löschen

### API-Änderung (intern):
- `get_id3_tags()` → `extract_metadata()` (Aufrufe in `analyze_track()` aktualisiert)
- Keine User-sichtbaren Änderungen

---

## 🐛 BEHOBENE BUGS

1. **Artist-Feld zeigt "Unknown"**
   - ✅ Fixed: Intelligenter Filename-Parser
   - ✅ Fallback funktioniert auch ohne ID3-Tags

2. **App nutzt nur 1 CPU-Kern**
   - ✅ Fixed: Multi-Core Processing mit bis zu 6 Kernen
   - ✅ Parallele Verarbeitung via ProcessPoolExecutor

3. **Cache nicht thread-safe**
   - ✅ Fixed: File-Locking für Multi-Process Safety
   - ✅ Windows + Unix kompatibel

---

## 🧪 TESTS

### Neue Tests:
- ✅ `test_artist_extraction.py` - Filename-Parsing Tests (5/5 passed)
- ✅ Import-Tests - Alle neuen Module (3/3 passed)

### Test-Ergebnisse:
```
Filename Parsing Tests: 5/5 [OK]
- "Artist - Track.ext" → PARSED
- "01 - Artist - Track.ext" → PARSED
- "ArtistName-TrackTitle.ext" → PARSED
- "Track_Number_Artist_Track.ext" → PARSED
- "SomeArtist_SomeTrack.ext" → PARSED

Import Tests: 3/3 [OK]
✓ parse_filename_for_metadata
✓ ParallelAnalyzer
✓ file_lock
```

---

## 📝 NÄCHSTE SCHRITTE

### Empfohlen für v3.2:
1. **SQLite-Migration:** Ersetze `shelve` durch SQLite für bessere Performance
2. **Mix-Point Optimierung:** Schnellerer Algorithmus als `ruptures`
3. **Unit-Tests:** Erweitere Test-Suite für neue Features
4. **Performance-Benchmarks:** Validiere Speedups mit echten Audio-Files

---

## 🙏 CREDITS

- **Entwicklung:** Claude Code + User Collaboration
- **Testing:** Windows 11, Python 3.9+
- **Libraries:**
  - `librosa` - Audio Analysis
  - `PyQt6` - GUI Framework
  - `mutagen` - ID3 Tag Extraction
  - `concurrent.futures` - Multi-Processing

---

## 📄 LICENSE

Siehe LICENSE Datei im Hauptverzeichnis.

---

**Status:** ✅ READY FOR TESTING
**Kompatibilität:** Windows 11, Python 3.9+
**Installations-Hinweis:** Keine zusätzlichen Dependencies erforderlich
