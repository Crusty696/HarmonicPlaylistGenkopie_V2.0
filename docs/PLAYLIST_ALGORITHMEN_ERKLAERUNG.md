# Wie HarmonicPlaylistGenerator Entscheidungen Trifft

## Übersicht: Das Herz des DJ-Algorithmus

Der Harmonic Playlist Generator ist wie ein virtueller DJ, der **20 Parameter** pro Track analysiert und dann **intelligent entscheidet**, welche Tracks nacheinander kommen sollen. Es gibt **10 verschiedene Strategien** zur Playlist-Generierung.

---

## 1. Die Grundidee: Harmonic Mixing

**Ziel:** Tracks so kombinieren, dass der Übergang für DJ und Hörer natürlich klingt.

Das funktioniert wie in der Musik-Theorie:
- **C Major** passt gut zu **G Major** (5. Stufe der Tonleiter)
- **A Minor** passt zu **D Minor** (4. Stufe)
- Diese Übergänge klingen "harmonisch" und nicht abrupt

### Das Camelot Code System
```
Visuell wie eine Uhr (Harmonic Wheel):

        1A (B Minor)
    12A     2A
   (E)       (C#)
 11A           3A
(F#)  ...     (G#)

Benachbarte Codes = gute Übergänge
Z.B. 8A → 9A oder 8A → 7A
```

**Im Code:** `playlist.py`, Zeile ~450
```python
def _calculate_harmonic_compatibility(track1, track2):
    # Berechne wie gut 2 Tracks harmonisch zusammenpassen
    # Rückgabewert: 0.0-1.0 (0=überhaupt nicht, 1=perfekt)
    code1 = parse_camelot_code(track1.camelotCode)  # Z.B. 8A
    code2 = parse_camelot_code(track2.camelotCode)  # Z.B. 9A

    distance = abs(code1 - code2)  # Abstand auf dem Wheel
    return 1.0 - (distance / 6.0)  # Je näher, desto besser
```

---

## 2. Die 10 Playlist-Strategien

Jede Strategie priorisiert unterschiedliche Kriterien. Der Nutzer wählt, welche am besten zu seinen Tracks passt.

### Strategie 1: **Harmonic Flow Enhanced** (BELIEBT)

**Logik:** "Nimm immer den Track mit dem besten harmonischen Übergang"

```python
def select_next_track(current_track, remaining_tracks):
    best_track = None
    best_score = -999

    for candidate in remaining_tracks:
        # Berechne Harmonie-Kompatibilität
        harmonic_score = calculate_harmonic_compatibility(
            current_track,
            candidate
        )
        # Bonus für ähnliche BPM (Übergänge sind leichter)
        bpm_bonus = 0.2 if abs(current.bpm - candidate.bpm) < 5 else 0

        total_score = harmonic_score * 0.7 + bpm_bonus

        if total_score > best_score:
            best_score = total_score
            best_track = candidate

    return best_track
```

**Ergebnis:** Smooth, musikalische Übergänge. Die Playlist klingt "zusammenhängend".

---

### Strategie 2: **Genre Flow**

**Logik:** "Bleibe in ähnlichen Genres, aber mit harmonischen Übergängen"

```python
for candidate in remaining_tracks:
    genre_match = 1.0 if candidate.genre == current.genre else 0.5
    harmonic_score = calculate_harmonic_compatibility(current, candidate)

    # Genre wird stärker gewichtet
    total = (harmonic_score * 0.4) + (genre_match * 0.6)
```

**Ergebnis:** Kohäsive Sets. Alle House-Tracks zusammen, dann Techno, dann Drum&Bass. Aber mit guten Übergängen.

---

### Strategie 3: **Peak Time**

**Logik:** "Steigere die Energie schnell, hol dich dann wieder runter"

```python
# Phase 1: Energie hochfahren (0% → 100%)
if playlist_length < 50% of all_tracks:
    prefer_tracks_with_higher_energy(remaining_tracks)

# Phase 2: Peak halten (100%)
elif playlist_length < 70% of all_tracks:
    prefer_tracks_with_same_energy(remaining_tracks)

# Phase 3: Energie reduzieren (100% → 0%)
else:
    prefer_tracks_with_lower_energy(remaining_tracks)
```

**Ergebnis:** Klassische DJ-Set-Kurve (wie ein Event mit Anfang, Höhepunkt, Ausklang).

---

### Strategie 4: **Energy Wave**

**Logik:** "Auf-Ab-Auf-Ab Pattern" (wie Wellen)

```python
current_energy = calculate_average_energy(playlist_so_far)

if len(playlist) % 2 == 0:  # Gerade = hochfahren
    score += (candidate.energy - current_energy) * 0.5
else:  # Ungerade = runterfahren
    score -= (candidate.energy - current_energy) * 0.5
```

**Ergebnis:** Dynamisch und spannend. Verhindert Monotonie.

---

## 3. Die Analyse-Metrics: Worauf der Algorithmus Achtet

Für jeden Track werden ~20 Werte berechnet:

### Audio-Analyse (Librosa)
```python
track.bpm              # Tempo: 90-180 BPM
track.keyNote          # Tonart: C, C#, D, D#, E... (12 Noten)
track.energy           # 0-100 (leise → laut & dynamisch)
track.bass_intensity   # 0-100 (wie viel Bass)
track.brightness       # 0-100 (helle Höhen vs. dunkle Bässe)
```

### Struktur-Analyse
```python
track.sections         # ["Intro", "Buildup", "Main", "Breakdown", "Outro"]
track.phrase_unit      # Typische Länge: 4, 8 oder 16 Bars
track.mix_in_point     # Wo kann man einfaden? (Sekunden)
track.mix_out_point    # Wo kann man ausfaden?
```

### Genre & Stil-Erkennung
```python
track.detected_genre       # "House", "Techno", "Drum & Bass" ...
track.genre_confidence     # Wie sicher ist diese Vorhersage? 0.0-1.0
track.danceability         # 0-100 (tanzbar?)
track.vocal_instrumental   # "vocal" / "instrumental" / "unknown"
```

**Im Code:** `hpg_core/analysis.py`, Zeilen 200-350

---

## 4. Das Scoring-System: Wie Entscheidungen getroffen werden

**Konzept:** Jeder Kandidat-Track bekommt einen "Score" für verschiedene Kriterien.

```python
def calculate_playlist_score(current_track, candidate_track, strategy_weights):
    """
    Score = Summe aller gewichteten Kriterien
    """

    scores = {}

    # Kriterium 1: Harmonie (wie gut passen die Tonarten?)
    scores['harmonic'] = calculate_harmonic_fit(
        current_track.camelotCode,
        candidate_track.camelotCode
    )  # Rückgabe: 0.0 - 1.0

    # Kriterium 2: BPM-Übergänge (wie smooth ist der Tempo-Wechsel?)
    scores['bpm_transition'] = 1.0 - min(
        abs(current_track.bpm - candidate_track.bpm) / 50,
        1.0
    )  # Je ähnlicher die BPM, desto besser

    # Kriterium 3: Energie (passt die Energie zur Strategie?)
    if strategy == "peak_time":
        target_energy = calculate_target_energy_for_peak_time()
        scores['energy'] = 1.0 - abs(
            candidate_track.energy - target_energy
        ) / 100

    # Kriterium 4: Genre (sollte ähnlich sein?)
    scores['genre'] = 1.0 if (
        current_track.detected_genre == candidate_track.detected_genre
    ) else 0.5

    # Kriterium 5: Struktur (können wir an einem guten Punkt wechseln?)
    scores['structure'] = evaluate_mix_points(
        current_track.mix_out_point,
        candidate_track.mix_in_point
    )

    # Gewichte je nach Strategie kombinieren
    total_score = (
        scores['harmonic'] * strategy_weights['harmonic'] +
        scores['bpm_transition'] * strategy_weights['bpm'] +
        scores['energy'] * strategy_weights['energy'] +
        scores['genre'] * strategy_weights['genre'] +
        scores['structure'] * strategy_weights['structure']
    )

    return total_score
```

**Beispiel mit realen Zahlen:**

```
Aktueller Track:   128 BPM, A Minor (8A), House, Energy 75
Kandidaten:

1. Techno Track    130 BPM, E Minor (9A), Energy 85
   - Harmonic:     0.95 ✓ (sehr nahe auf dem Wheel)
   - BPM:          0.96 ✓ (nur 2 BPM Unterschied)
   - Energy:       0.90 ✓ (ähnliche Energie, kleine Steigerung)
   - Genre:        0.60 (unterschiedlich)
   TOTAL SCORE:    0.85

2. Deep House      120 BPM, G Minor (5A), Energy 65
   - Harmonic:     0.85 (weiter weg)
   - BPM:          0.92 (8 BPM Unterschied)
   - Energy:       0.90 (etwas weniger Energie)
   - Genre:        0.95 (gleich!)
   TOTAL SCORE:    0.91  ← GEWONNEN!

→ Der Deep House Track wird ausgewählt, weil Genre-Konsistenz
  in dieser Strategie wichtig ist.
```

**Im Code:** `hpg_core/playlist.py`, Zeilen 1200-1350

---

## 5. Walkthrough: Eine Echtzeit-Playlist-Generierung

Sagen wir, der Nutzer hat 5 Tracks und wählt "Harmonic Flow Enhanced":

```python
initial_track = House 128 BPM, A Minor (8A), Energy 75
remaining = [
    Techno 130 BPM, E Minor (9A), Energy 85,
    Deep House 120 BPM, G Minor (5A), Energy 65,
    Drum&Bass 170 BPM, C Minor (4A), Energy 95,
    Minimal 125 BPM, D Minor (7A), Energy 68
]

# ITERATION 1: Nach dem House-Track
for track in remaining:
    score = calculate_score(House_Track, track, "harmonic_flow")

Techno 9A:        0.88 (harmonisch: +0.95, BPM: +0.96, gemeinsam: +0.75)
Deep House 5A:    0.72 (harmonisch: +0.70, BPM: +0.92, gemeinsam: +0.60)
Drum&Bass 4A:     0.45 (harmonisch: +0.55, BPM: +0.10, gemeinsam: +0.20)
Minimal 7A:       0.91 ← GEWONNEN (harmonisch: +0.98, BPM: +0.92, gemeinsam: +0.75)

PLAYLIST: [House → Minimal]

# ITERATION 2: Nach Minimal 125 BPM, D Minor (7A)
remaining = [Techno, Deep House, Drum&Bass]

Techno 9A:        0.93 ← GEWONNEN (7A→9A nur 2 Schritte)
Deep House 5A:    0.85 (7A→5A nur 2 Schritte, aber BPM-Sprung)
Drum&Bass 4A:     0.70 (zu viel Tempo-Unterschied)

PLAYLIST: [House → Minimal → Techno]

# ITERATION 3: Nach Techno 130 BPM, E Minor (9A)
remaining = [Deep House, Drum&Bass]

Deep House 5A:    0.78 (stabilisiert Energie, aber harmonisch weiter weg)
Drum&Bass 4A:     0.82 ← GEWONNEN (9A→4A ein Schritt, Energie-Boost)

PLAYLIST: [House → Minimal → Techno → Drum&Bass]

# ITERATION 4: Nach Drum&Bass 170 BPM, C Minor (4A)
remaining = [Deep House]

Deep House 5A:    1.0 (einzige Option, aber gutes Comeback zu der Energie)

FINAL PLAYLIST:
1. House 128 BPM, A Minor (8A), Energy 75
2. Minimal 125 BPM, D Minor (7A), Energy 68
3. Techno 130 BPM, E Minor (9A), Energy 85
4. Drum&Bass 170 BPM, C Minor (4A), Energy 95
5. Deep House 120 BPM, G Minor (5A), Energy 65

ANALYSE:
✓ Harmonic: Alle Übergänge ≤2 Schritte auf dem Wheel
✓ BPM: Schrittweise: 128→125→130→170→120 (großer Drop am Ende, aber smooth genug)
✓ Energy: 75→68→85→95→65 (peak at position 4)
✓ Genre: House → Minimal → Techno → Drum&Bass → House (Rückkehr)
```

---

## 6. Spezial-Algorithmen

### BPM Halftime / Double-Time
```python
# Ein 128 BPM Track kann mit 64 BPM oder 256 BPM spielen
# Das macht der Algorithmus automatisch
effective_bpm = adjust_for_halftime_doubletime(track.bpm)

# 128 → kann als 64 oder 256 interpretiert werden
# Das öffnet völlig neue Kombinationen!
```

### Energiewellenfunktion
```python
def energy_wave_algorithm(playlist_progress):
    """
    Erzeugt eine Sinus-Welle für die Energie
    """
    import math

    progress_percent = len(playlist) / total_tracks

    # Sinus-Welle: 0°→90°→180°→270°→360°
    phase = progress_percent * 2 * math.pi

    wave_value = math.sin(phase)  # -1 bis +1

    # Konvertiere zu Energie (0-100)
    target_energy = 50 + (wave_value * 25)  # 25-75 Schwankung

    # Wähle Tracks nahe an target_energy
    return select_tracks_near_energy(target_energy)
```

---

## 7. Das GUI und die Visualisierung

Wenn du die App startest, siehst du:

```
┌─────────────────────────────────────┐
│ HarmonicPlaylistGenerator v3.5.3     │
├─────────────────────────────────────┤
│ 📁 Folder: C:\Music\                 │
│ Tracks gefunden: 35                 │
├─────────────────────────────────────┤
│ Algorithmus: [▼ Harmonic Flow]      │
│ Shuffle: [☐]  |  Limit: [50]        │
├─────────────────────────────────────┤
│ [📊 Preview] [▶ Generate] [💾 Export]│
├─────────────────────────────────────┤
│ Harmonic Flow Enhanced   Score: 0.89 │
│ Genre Flow               Score: 0.76 │
│ Peak Time                Score: 0.92 │
│ Energy Wave              Score: 0.85 │
│ ...7 weitere Strategien  │
├─────────────────────────────────────┤
│ Playlist (Preview):                 │
│ 1. Better Days (House) 128 BPM      │
│ 2. Warm Up (Deep House) 120 BPM     │
│ 3. Beats (Techno) 130 BPM           │
│ 4. Rush (Drum&Bass) 170 BPM         │
│ 5. Chill (Ambient) 100 BPM          │
└─────────────────────────────────────┘
```

---

## 8. Zusammenfassung: Die Entscheidungslogik

**VEREINFACHT:**

```
1. Lade alle Tracks und analysiere sie
   ↓
2. Nutzer wählt Algorithmus + Einstellungen
   ↓
3. Für jeden Track in der Playlist:
   a) Berechne Score für alle verbleibenden Tracks
   b) Wähle Track mit höchstem Score
   c) Entferne gewählten Track aus verbleibenden
   d) Wiederhole bis alle Tracks verwendet
   ↓
4. Exportiere als M3U8 oder Rekordbox XML
```

**DETAILLIERT:**

```
Das System achtet auf:
- Harmonische Kompatibilität (Tonarten-Radiant)
- BPM-Übergänge (sanfte Tempo-Wechsel)
- Energieverläufe (Spannung aufbauen und senken)
- Genre-Konsistenz (bleib in einem Style)
- Struktur-Übergänge (fade in/out Punkte)
- Danceability & Vibe (Tanzbarkeit, Vocal vs Instrumental)

→ Kombiniert in einen Score
→ Beste Kombination gewinnt
→ Nächstes Lied erkannt
```

---

## 9. Debugging & Verstehen

Wenn du wissen willst, **WARUM** ein Track ausgewählt wurde:

```python
# In playlist.py kann man Debug-Mode einschalten
DEBUG = True

# Dann sieht man:
Track "Better Days" wird gewählt
  Harmonisch mit "Warm Up":  0.95 ✓ (8A→5A, nur 3 Schritte)
  BPM-Übergang:              0.92 ✓ (128→120, -8 BPM)
  Energie:                   0.90 ✓ (75→65, sanft runter)
  Genre-Match:               0.60 ~ (House→House, perfekt!)
  Struktur-Übergänge:        0.88 ✓ (Mix-Out 240s → Mix-In 5s)
  ──────────────────────────────────
  TOTAL SCORE:               0.89 ← BESTE OPTION
```

---

## Fragen?

Stelle Fragen, wenn du folgende Dinge verstehen willst:
- Warum wurde **dieser Track** nach **jenem Track** gewählt?
- Wie funktioniert eine **spezifische Strategie**?
- Warum **schneidet diese Playlist schlecht ab**?

Der Code ist dokumentiert und du kannst jeden Schritt nachverfolgen! 🎵
