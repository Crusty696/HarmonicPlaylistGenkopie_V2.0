# Harmonic Playlist Generator v5 - Installation & Start

## 🚀 Schnellstart (5 Minuten)

### Schritt 1: Python installieren (falls noch nicht vorhanden)

**Windows:**
1. Download: https://www.python.org/downloads/
2. Version: Python 3.10 oder neuer
3. ✅ **WICHTIG:** Haken setzen bei "Add Python to PATH"
4. Installation durchführen

**Überprüfung:**
```bash
python --version
# Sollte zeigen: Python 3.10.x oder höher
```

---

### Schritt 2: Dependencies installieren

**Im Projektordner:**
```bash
cd C:\Users\david\Desktop\HarmonicPlaylistGenerator_v5

# Alle benötigten Bibliotheken installieren
pip install -r requirements.txt
```

**Was wird installiert:**
- PyQt6 (GUI Framework)
- librosa (Audio-Analyse)
- numpy (Mathematik)
- mutagen (ID3 Tags)
- soundfile (Audio I/O)

**Dauer:** ~2-3 Minuten

---

### Schritt 3: App starten

**Einfach:**
```bash
python main.py
```

**Oder:** Doppelklick auf `main.py` (wenn Python mit .py Dateien verknüpft ist)

---

## 🎵 App benutzen

### Nach dem Start:

1. **Drag & Drop:**
   - Ziehe deinen Musik-Ordner in das Fenster
   - ODER klicke "📂 Select Music Folder"

2. **Strategie wählen:**
   - Empfohlen: "Harmonic Flow Enhanced"
   - Oder: "Genre Flow" für beste Qualität

3. **BPM Tolerance einstellen:**
   - Standard: ±3 BPM
   - Erhöhen für mehr Flexibilität

4. **Generate Playlist klicken:**
   - Analyse läuft im Hintergrund
   - Progress-Bar zeigt Fortschritt

5. **Playlist exportieren:**
   - Klick "💾 Export as M3U Playlist"
   - Datei für DJ-Software (Traktor, Rekordbox, Serato)

---

## 📋 Unterstützte Formate

- ✅ WAV
- ✅ AIFF
- ✅ MP3
- ✅ FLAC

---

## 🐛 Troubleshooting

### Problem: "Python nicht gefunden"
**Lösung:**
```bash
# Python zum PATH hinzufügen (Windows)
# Oder: Python neu installieren mit "Add to PATH"
```

### Problem: "Module not found"
**Lösung:**
```bash
pip install -r requirements.txt
```

### Problem: "Qt platform plugin not found"
**Lösung:**
```bash
pip uninstall PyQt6
pip install PyQt6
```

### Problem: App startet nicht
**Lösung:**
```bash
# Starte mit Error-Output:
python main.py 2>&1
```

---

## ⚡ Performance-Tipps

### Erste Analyse dauert lange?
- **Normal:** ~2 Sekunden pro Track
- **Cache:** Beim 2. Mal instant!
- **100 Tracks:** ~3-4 Minuten erste Analyse

### Cache löschen (wenn Probleme):
```bash
# Windows:
del hpg_cache_v3.dbm.*
del cache.db

# Oder im Python:
python -c "import os; [os.remove(f) for f in os.listdir('.') if 'cache' in f.lower()]"
```

---

## 🎯 Empfohlene Einstellungen

### Für DJ-Sets:
- **Strategie:** "Harmonic Flow Enhanced"
- **BPM Tolerance:** ±3 BPM
- **Harmonic Strictness:** 7/10

### Für Warm-Up Sets:
- **Strategie:** "Warm-Up"
- **BPM Tolerance:** ±5 BPM

### Für Peak-Time:
- **Strategie:** "Peak-Time Enhanced"
- **BPM Tolerance:** ±3 BPM

### Für Chill/Downtempo:
- **Strategie:** "Emotional Journey"
- **BPM Tolerance:** ±8 BPM

---

## 📦 Systemanforderungen

**Minimum:**
- Windows 10/11, macOS 10.15+, oder Linux
- Python 3.10+
- 4 GB RAM
- 500 MB freier Speicher

**Empfohlen:**
- 8 GB RAM
- SSD für schnellere Analyse

---

## 🔧 Advanced: Virtual Environment (Optional)

**Für saubere Installation:**

```bash
# Virtual Environment erstellen
python -m venv venv

# Aktivieren (Windows)
venv\Scripts\activate

# Aktivieren (macOS/Linux)
source venv/bin/activate

# Dependencies installieren
pip install -r requirements.txt

# App starten
python main.py
```

---

## 📱 Exportierte Playlists benutzen

### Traktor:
1. File → Import → Import Other
2. Wähle .m3u Datei
3. Tracks werden zur Collection hinzugefügt

### Rekordbox:
1. File → Import Playlist
2. Wähle .m3u Datei
3. Playlist erscheint in Playlists

### Serato:
1. Files Panel → + → Import Playlist
2. Wähle .m3u Datei
3. Playlist wird erstellt

---

## 💡 Tipps für beste Ergebnisse

1. **Große Collections:** Je mehr Tracks, desto besser die harmonische Sortierung
2. **Vielfältige BPMs:** Mix verschiedener Geschwindigkeiten für bessere Übergänge
3. **ID3 Tags:** Stelle sicher dass Artist/Title korrekt sind
4. **Cache nutzen:** Beim 2. Mal ist es instant!
5. **Strategien testen:** Probiere verschiedene Modi für unterschiedliche Ergebnisse

---

## 🆘 Support

**Bei Problemen:**
1. Checke `HONEST_STATUS.md` für bekannte Issues
2. Checke `docs/CODE_REVIEW_2025.md` für Details
3. Starte mit `python main.py` und schau dir Fehler an

**Logs:**
```bash
# Mit Debugging:
python main.py 2>&1 | tee app.log
```

---

## ✅ Installation verifizieren

**Test-Script:**
```bash
python test_full_collection.py
```

**Sollte ausgeben:**
```
✓ 21 Tracks analysiert
✓ 10 Strategien getestet
✓ Beste Strategie: Genre Flow (66.0%)
✓ Playlist exportiert
```

---

**Viel Spaß beim Mixen! 🎧**
