# HARMONIC PLAYLIST GENERATOR PRO v3.0
## Mit Mix In/Out Points & erweiterten Metadaten

========================================
NEUE VERSION 3.0 - ALLE FEATURES
========================================

## NEU IN VERSION 3.0

### MIX POINTS
- Mix In Point: Wo du einmischen sollst
- Mix Out Point: Wo du ausmischen sollst
- Automatisch berechnet auf Basis von 16-Bar-Phrasen
- Intro/Outro-Erkennung durch Energy-Analyse

### ERWEITERTE METADATEN
- Artist (aus ID3-Tags)
- Title (aus ID3-Tags)  
- Genre (aus ID3-Tags)
- Duration (formatiert MM:SS)
- Energy Level (0-100)
- Bass Intensity (0-100, 20-150 Hz)
- Intro/Main/Outro-Längen
- Anzahl Phrasen (16-Bar-Struktur)

### NEUE TABELLEN-SPALTEN
- # | Artist | Title | BPM | Key | Camelot
- Energy | Bass | Duration | Mix In | Mix Out

### DETAIL-ANSICHT
- Doppelklick auf Track
- Alle Metadaten übersichtlich
- Mix Points in Sekunden
- Mixing-Tipps

========================================
INSTALLATION
========================================

1. PYTHON INSTALLIEREN
   - https://www.python.org/downloads/
   - Python 3.9+ herunterladen
   - "Add Python to PATH" aktivieren!

2. BIBLIOTHEKEN INSTALLIEREN
   Öffne CMD (Eingabeaufforderung):
   
   cd Desktop\HarmonicPlaylistGenerator
   pip install -r requirements.txt
   
   WICHTIG: Neue Bibliothek "mutagen" wird installiert!
   
3. APP STARTEN
   Doppelklick auf: start.bat

========================================
NUTZUNG
========================================

1. ORDNER LADEN
   - Klick "Ordner laden"
   - Wähle Ordner mit Audio-Dateien
   - Formate: WAV, AIFF, MP3, FLAC

2. MODUS WÄHLEN
   - Warm-Up: Langsam → Schnell
   - Cool-Down: Schnell → Langsam  
   - Peak-Time: Mittel → Hoch → Mittel
   - Energy Wave: Wellenförmig
   - Consistent: Konstantes Tempo
   - Harmonic Flow: Beste Harmonie

3. BPM-TOLERANZ EINSTELLEN
   - Slider: 1-10 BPM
   - Standard: 3 BPM

4. ANALYSE LÄUFT
   - Automatisch für alle Tracks
   - Fortschritt wird angezeigt
   - Cache beschleunigt spätere Analysen

5. ERGEBNIS PRÜFEN
   - Tabelle mit allen Tracks
   - Sortiert nach gewähltem Modus
   - Mix Points bereits berechnet!

6. DETAILS ANZEIGEN
   - Doppelklick auf Track ODER
   - "Details"-Button klicken
   - Zeigt alle Metadaten & Mix Points

7. NEU GENERIEREN
   - Modus wechseln
   - "Neu generieren" klicken
   - Keine neue Analyse nötig!

8. EXPORT
   - "Export .m3u" klicken
   - Datei wird mit Mix Points gespeichert
   - Format: #MIXPOINT:in,out

========================================
MIX POINTS - WAS IST DAS?
========================================

MIX IN POINT
= Wo du den neuen Track einmischen sollst
- Nach Intro (typisch 16 Bars)
- Wenn Bassline/Kick einsetzt
- Optimal für nahtlose Übergänge

MIX OUT POINT  
= Wo du aktuellen Track ausmischen sollst
- Vor Outro (typisch 16 Bars vor Ende)
- Bevor Elements verschwinden
- Genug Zeit für sanften Übergang

WARUM WICHTIG?
- Tracks haben Struktur: Intro → Main → Outro
- Phrasen sind 16 Bars lang (EDM-Standard)
- Mischen zwischen Phrasen = professioneller Mix
- Mix Points zeigen optimale Stellen

BEISPIEL:
Track: "Example Song"
Duration: 5:30 (330s)
Mix In: 0:45 (45s)   ← Hier einmischen
Mix Out: 4:45 (285s) ← Hier ausmischen

========================================
ALLE METADATEN
========================================

BASIS-INFO:
- Artist (aus ID3)
- Title (aus ID3)
- Genre (aus ID3)
- Duration (MM:SS)

MUSIKALISCHE ANALYSE:
- BPM (Beats Per Minute)
- Key (Tonart: C, D, E, F, G, A, B)
- Key Mode (Major/Minor)
- Camelot Code (1A-12B)

ENERGIE-ANALYSE:
- Energy Level (0-100)
- Bass Intensity (0-100)

STRUKTUR-ANALYSE:
- Mix In Time (Sekunden + MM:SS)
- Mix Out Time (Sekunden + MM:SS)
- Intro Length (Sekunden)
- Main Section Length (Sekunden)
- Outro Length (Sekunden)
- Estimated Phrases (Anzahl 16-Bar-Phrasen)

========================================
PRAKTISCHE BEISPIELE
========================================

CLUB WARM-UP (21:00-23:00)
Modus: Warm-Up
BPM-Toleranz: 3-4
→ Startet bei 110 BPM, endet bei 128 BPM
→ Mix Points zeigen optimale Ein-/Ausstiegspunkte

PEAK-TIME (23:00-01:00)
Modus: Peak-Time
BPM-Toleranz: 2-3
→ Startet bei 126 BPM, Peak bei 132 BPM
→ Details zeigen lange Main-Sections für extended Mixes

AFTER-HOUR (03:00-06:00)
Modus: Cool-Down
BPM-Toleranz: 3-5
→ Startet bei 128 BPM, endet bei 100 BPM
→ Energy-Werte sinken graduell

MARATHON-SET (6+ Stunden)
Modus: Energy Wave
BPM-Toleranz: 4-5
→ Wellenförmige Energy-Kurve
→ Dynamik über lange Zeit

TECHNO-SET
Modus: Consistent
BPM-Toleranz: 1-2
→ Konstanter Drive um 130 BPM
→ Minimal Energy-Schwankungen

========================================
EXPORT-FORMAT (.m3u mit Mix Points)
========================================

Die .m3u-Datei enthält:

#EXTM3U
#EXTINF:330,Artist Name - Track Title
#MIXPOINT:45.5,285.0
C:\Path\To\Track.mp3
#EXTINF:300,Next Artist - Next Title  
#MIXPOINT:52.0,248.5
C:\Path\To\NextTrack.mp3

Format:
#MIXPOINT:MixInTime,MixOutTime
(beide in Sekunden)

========================================
TECHNISCHE DETAILS
========================================

MIX POINT BERECHNUNG:
- 4/4-Takt = 4 Beats pro Bar
- 16 Bars = 1 Phrase (EDM-Standard)
- Mix In: Nach erstem Intro (16-32 Bars)
- Mix Out: Vor letztem Outro (16-32 Bars)

INTRO/OUTRO-ERKENNUNG:
- RMS-Energy-Analyse über Zeit
- Threshold-Detection für Strukturwechsel
- Smoothing für robuste Erkennung

BASS-INTENSITÄT:
- STFT (Short-Time Fourier Transform)
- Frequenzbereich: 20-150 Hz
- Ratio: Bass-Energy / Total-Energy

========================================
CHANGELOG v3.0
========================================

NEU:
✨ Mix In/Out Points (automatisch)
✨ Artist/Title/Genre aus ID3-Tags
✨ Bass-Intensität-Analyse (20-150 Hz)
✨ Struktur-Erkennung (Intro/Main/Outro)
✨ Phrase-Analyse (16-Bar-Phrasen)
✨ Detail-Ansicht mit allen Infos
✨ Mix Points im .m3u-Export
✨ Doppelklick für Details

VERBESSERT:
🔧 Schnellere Analyse
🔧 Bessere Energy-Berechnung
🔧 Präzisere Mix Point Detection
🔧 Erweiterte Tabelle
🔧 Optimierte UI

TECHNISCH:
- Neue Cache-Version (v3)
- Mutagen für ID3-Tags
- Verbesserte Algorithmen
- RMS-basierte Intro/Outro-Erkennung

========================================
HÄUFIGE FRAGEN
========================================

Q: Wie genau sind die Mix Points?
A: Sehr genau! Basiert auf RMS-Energy und
   16-Bar-Phrasen. In 90% optimal.

Q: Kann ich Mix Points anpassen?
A: Aktuell nicht in der App, aber .m3u-Datei
   kann manuell bearbeitet werden.

Q: Warum keine ID3-Tags?
A: Stelle sicher, dass deine Dateien ID3-Tags
   haben. Sonst zeigt App "Unknown".

Q: Cache löschen?
A: Lösche:
   C:\Users\[Name]\.hpg_cache_v3.json

Q: Alte Version updaten?
A: Installiere neue Bibliothek:
   pip install mutagen==1.47.0

========================================
MIXING-TIPPS MIT MIX POINTS
========================================

32-BAR-MIX:
- Starte bei Mix In Point
- Mixe über 32 Bars (8 Phrasen)
- Ende bei Mix Out Point

QUICK-MIX:
- Bei kurzen Intros/Outros
- 16-Bar-Mix (4 Phrasen)
- Schneller EQ-Tausch

EXTENDED MIX:
- Bei langen Main-Sections
- 64-Bar-Mix (16 Phrasen)  
- Langsamer EQ-Übergang

ENERGY-MATCHING:
- Achte auf Energy-Werte
- Mixe ähnliche Energy-Level
- Details zeigen Bass-Level

========================================
PROBLEMLÖSUNG
========================================

"pip wird nicht erkannt"
→ Python neu installieren mit "Add to PATH"

"mutagen Installation fehlgeschlagen"
→ pip install mutagen --no-cache-dir

"Keine ID3-Tags angezeigt"
→ Prüfe ob Dateien Tags haben
→ Nutze MP3Tag zum Bearbeiten

"Analyse dauert lange"
→ Normal bei vielen/großen Dateien
→ Cache beschleunigt nächstes Mal

"Energy-Werte alle gleich"
→ Cache löschen
→ Neu analysieren

========================================
ZUKÜNFTIGE FEATURES (v4.0)
========================================

- Manuelle Mix Point Anpassung
- Visuelle Waveform-Anzeige
- Automatisches Beatgrid
- Cue Point Export (Rekordbox/Serato)
- Genre-basierte Sortierung
- BPM-Shift-Vorschläge
- Harmonic Mixing Visualisierung

========================================

VERSION 3.0 | 2025
Harmonic Playlist Generator Pro

Viel Erfolg mit deinen perfekten DJ-Sets!
