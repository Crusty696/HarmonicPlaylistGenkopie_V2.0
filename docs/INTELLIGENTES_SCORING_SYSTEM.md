# Intelligentes, Adaptives Scoring-System für HarmonicPlaylistGenerator

## Das Problem mit dem alten System

**Alt (Starr):**
```
Score = (Harmonie × 0.4) + (BPM × 0.2) + (Energie × 0.2) + (Genre × 0.2)
```

**Probleme:**
- Immer gleiche Gewichte, egal ob am Anfang, Mitte oder Ende der Playlist
- Ignoriert den **musikalischen Kontext** (wo bin ich gerade?)
- Keine "Flow-Intelligenz" (war der letzte Track schnell, langsam?)
- Keine "Überraschungs-Intelligenz" (wann sollte ich den Genre wechseln?)
- Keine "Energy-Kurve-Intelligenz" (bin ich im Build-Up oder Peak?)

---

## Die neue Idee: Kontextabhängiges Scoring

### **Kern-Konzept:**

Der Score für einen Track hängt ab von:
1. **Wo sind wir gerade?** (Position in Playlist: 0%, 50%, 90%?)
2. **Wie war der Trend?** (Energie steigt? Fällt? Konstant?)
3. **Was war der letzte Track?** (Schnell? Langsam? Genre?)
4. **Welche Strategie wurde gewählt?** (Peak Time? Genre Flow? Harmonic?)
5. **Wie lange sind wir schon in dieser Energie/Genre?** (Zu lange? Zeit für Wechsel?)

---

## Implementierung: Der Adaptive Score Engine

### **Schicht 1: Kontext-Erkennung**

```python
class PlaylistContext:
    """Versteht, wo wir uns in der Playlist befinden."""

    def __init__(self, playlist_so_far, strategy):
        self.playlist = playlist_so_far
        self.position = len(playlist_so_far)
        self.strategy = strategy

    def get_playlist_phase(self):
        """Welche Phase sind wir?"""
        progress = self.position / self.total_tracks

        if progress < 0.2:
            return "INTRO"           # 0-20%
        elif progress < 0.5:
            return "BUILD_UP"        # 20-50%
        elif progress < 0.8:
            return "PEAK"            # 50-80%
        else:
            return "OUTRO"           # 80-100%

    def get_energy_trend(self):
        """Geht Energie hoch oder runter?"""
        if len(self.playlist) < 3:
            return "UNDEFINED"

        recent_energies = [t.energy for t in self.playlist[-3:]]

        trend = recent_energies[-1] - recent_energies[0]

        if trend > 10:
            return "RISING"          # Energie geht hoch
        elif trend < -10:
            return "FALLING"         # Energie geht runter
        else:
            return "STABLE"          # Energie konstant

    def get_genre_streak(self):
        """Wie lange sind wir schon in diesem Genre?"""
        if not self.playlist:
            return 0

        current_genre = self.playlist[-1].detected_genre
        streak = 0

        for track in reversed(self.playlist):
            if track.detected_genre == current_genre:
                streak += 1
            else:
                break

        return streak

    def get_camelot_stability(self):
        """Wie viel "Harmonic Drift" gibt es?"""
        if len(self.playlist) < 2:
            return "UNDEFINED"

        # Berechne durchschnittlichen Abstand zwischen Camelot Codes
        distances = []
        for i in range(len(self.playlist) - 1):
            c1 = parse_camelot(self.playlist[i].camelotCode)
            c2 = parse_camelot(self.playlist[i+1].camelotCode)
            distances.append(abs(c1 - c2))

        avg_distance = sum(distances) / len(distances)

        if avg_distance < 2:
            return "TIGHT"           # Enger harmonischer Flow
        elif avg_distance < 4:
            return "MEDIUM"          # Mittlere harmonische Sprünge
        else:
            return "LOOSE"           # Große harmonische Sprünge
```

---

### **Schicht 2: Dynamische Gewichte basierend auf Kontext**

```python
class DynamicWeightCalculator:
    """Berechnet Gewichte basierend auf Kontext."""

    def calculate_weights(self, context, strategy):
        """
        Basis-Gewichte werden je nach Phase angepasst.
        """

        phase = context.get_playlist_phase()
        energy_trend = context.get_energy_trend()
        genre_streak = context.get_genre_streak()

        # Basis-Gewichte (standard)
        weights = {
            'harmonic': 0.30,
            'bpm': 0.25,
            'energy': 0.25,
            'genre': 0.15,
            'structure': 0.05,
        }

        # === PHASE-SPEZIFISCHE ANPASSUNGEN ===

        if phase == "INTRO":
            # Am Anfang: Harmonic Flow sehr wichtig, Energy kann niedrig sein
            weights['harmonic'] = 0.50   # ↑ "Setz einen guten Ton"
            weights['energy'] = 0.15     # ↓ "Energie muss nicht hoch sein"
            weights['bpm'] = 0.20
            weights['genre'] = 0.10

        elif phase == "BUILD_UP":
            # Beim Build-Up: Energie-Progression wichtig, Genre-Konsistenz
            weights['energy'] = 0.40     # ↑ "Baue Spannung auf"
            weights['harmonic'] = 0.25   # ↓ "Weniger wichtig während Aufbau"
            weights['bpm'] = 0.20
            weights['genre'] = 0.10      # ↓ "Bleib im Genre"

        elif phase == "PEAK":
            # Am Peak: Energie im Peak halten, gute BPM-Übergänge
            weights['energy'] = 0.35     # ↑ "Halte die Spannung"
            weights['bpm'] = 0.30        # ↑ "Smooth Übergänge wichtig"
            weights['harmonic'] = 0.20   # ↓ "Sekundär beim Peak"
            weights['genre'] = 0.10

        elif phase == "OUTRO":
            # Am Outro: Sanfte Abfahrt, wieder Harmonic wichtig
            weights['energy'] = 0.30     # "Energie runter fahren"
            weights['harmonic'] = 0.35   # ↑ "Musikalische Auflösung"
            weights['bpm'] = 0.20
            weights['genre'] = 0.10

        # === TREND-SPEZIFISCHE ANPASSUNGEN ===

        if energy_trend == "RISING":
            # Wenn Energie steigt: verstärke den Trend
            weights['energy'] *= 1.2     # "Mach weiter hoch!"
            weights['bpm'] *= 0.9

        elif energy_trend == "FALLING":
            # Wenn Energie fällt: sanft weiter runter
            weights['energy'] *= 1.1
            weights['harmonic'] *= 1.1   # "Musikalisch bleiben"

        elif energy_trend == "STABLE":
            # Wenn Energie stabil: könnte sich was ändern
            # Mehr Gewicht auf Überraschung/Genre-Wechsel
            if genre_streak > 5:
                # Zu lange im gleichen Genre
                weights['genre'] = 0.05   # ↓ "Erlaube Genre-Wechsel"
                weights['energy'] *= 1.15 # ↑ "Verändere mit Energie"

        # === STRATEGIE-SPEZIFISCHE ANPASSUNGEN ===

        if strategy == "PEAK_TIME":
            weights['energy'] = 0.45     # ↑ Energie ist König
            weights['harmonic'] = 0.20

        elif strategy == "GENRE_FLOW":
            weights['genre'] = 0.35      # ↑ Genre konsistent
            weights['harmonic'] = 0.35
            weights['energy'] = 0.20

        elif strategy == "ENERGY_WAVE":
            weights['energy'] = 0.50     # ↑ Energie-Welle erzeugen
            weights['harmonic'] = 0.15

        elif strategy == "EMOTIONAL_JOURNEY":
            weights['harmonic'] = 0.40   # ↑ Emotionale Kohärenz
            weights['genre'] = 0.25      # ↑ Genre-Storytelling
            weights['energy'] = 0.25

        # === NORMALISIEREN (Summe = 1.0) ===
        total = sum(weights.values())
        weights = {k: v / total for k, v in weights.items()}

        return weights
```

---

### **Schicht 3: Intelligente Score-Berechnung**

```python
class IntelligentScoreEngine:
    """Berechnet Scores intelligent, nicht mechanisch."""

    def calculate_score(self, current_track, candidate, context, strategy):
        """
        Der eigentliche Score-Berechnung mit Intelligenz.
        """

        # Hole dynamische Gewichte
        weights = DynamicWeightCalculator().calculate_weights(context, strategy)

        # === BERECHNE EINZELNE SCORES ===

        score_harmonic = self._score_harmonic(current_track, candidate, context)
        score_bpm = self._score_bpm(current_track, candidate, context)
        score_energy = self._score_energy(candidate, context)
        score_genre = self._score_genre(current_track, candidate, context)
        score_structure = self._score_structure(current_track, candidate)

        # === BONUS/PENALTY SYSTEM ===

        bonuses = self._calculate_bonuses(
            current_track, candidate, context, strategy
        )
        penalties = self._calculate_penalties(
            current_track, candidate, context
        )

        # === KOMBINIEREN MIT GEWICHTEN ===

        base_score = (
            score_harmonic * weights['harmonic'] +
            score_bpm * weights['bpm'] +
            score_energy * weights['energy'] +
            score_genre * weights['genre'] +
            score_structure * weights['structure']
        )

        # Wende Bonuses und Penalties an
        final_score = base_score + bonuses + penalties

        # Clamp zwischen 0-1
        final_score = max(0.0, min(1.0, final_score))

        return final_score

    def _score_harmonic(self, current, candidate, context):
        """
        Harmonic Score mit Intelligenz.

        - Wenn harmonischer "Drift" eng war: mehr Strenge (Tight Coherence)
        - Wenn harmonischer "Drift" locker war: erlauben mehr Sprünge
        """
        camelot_distance = self._camelot_distance(
            current.camelotCode,
            candidate.camelotCode
        )

        # Base Score: je näher, desto besser
        base = 1.0 - (camelot_distance / 6.0)

        # Intelligente Anpassung basierend auf bisherigem Drift
        stability = context.get_camelot_stability()

        if stability == "TIGHT":
            # "Wir waren eng harmonisch, bleib eng"
            base *= 1.2  # Bonus für enge Harmonien
            if camelot_distance > 3:
                base *= 0.6  # Penalty für große Sprünge

        elif stability == "LOOSE":
            # "Wir sind locker, ein Sprung ist okay"
            base *= 1.0  # Keine besonderen Adjustments

        return base

    def _score_bpm(self, current, candidate, context):
        """
        BPM Score mit Kontext.

        - Wenn Energie steigt: erlauben größere BPM-Sprünge (exciting!)
        - Wenn Energie stabil: halte BPM ähnlich (smooth)
        """
        bpm_diff = abs(current.bpm - candidate.bpm)

        # Base Score
        base = 1.0 - (bpm_diff / 100.0)

        # Kontext-basierte Anpassung
        energy_trend = context.get_energy_trend()
        phase = context.get_playlist_phase()

        if energy_trend == "RISING" and phase in ["BUILD_UP", "PEAK"]:
            # "Beim Aufbau: Tempo-Steigerung ist SPANNEND"
            if bpm_diff > 5:
                base *= 1.3  # Bonus für Tempo-Steigerung

        elif energy_trend == "FALLING" and phase == "OUTRO":
            # "Beim Outro: Tempo runterfahren ist natürlich"
            if bpm_diff < 15:
                base *= 1.2  # Bonus für sanftes Tempo-Runterfahren

        return base

    def _score_energy(self, candidate, context):
        """
        Energy Score ist sehr strategiespezifisch.

        - Peak Time: Kandidat sollte zur "Target-Energie" passen
        - Energy Wave: Kandidat sollte Alternative zur aktuellen Energie sein
        - Emotional Journey: kontinuierlich & kohärent
        """
        current_energy = context.playlist[-1].energy if context.playlist else 50

        # Was ist die "ziel-Energie" basierend auf Phase?
        phase = context.get_playlist_phase()

        if phase == "INTRO":
            target_energy = 30  # Niedrig anfangen
        elif phase == "BUILD_UP":
            target_energy = 60  # Aufbau
        elif phase == "PEAK":
            target_energy = 85  # Hoch
        elif phase == "OUTRO":
            target_energy = 40  # Runterfahren

        # Score basierend auf Nähe zu Target
        energy_diff = abs(candidate.energy - target_energy)
        score = 1.0 - (energy_diff / 100.0)

        return score

    def _score_genre(self, current, candidate, context):
        """
        Genre Score mit "Genre-Fatigue" Erkennung.

        - Nach 5 Tracks im gleichen Genre: Genre-Wechsel wird belohnt
        - Aber nicht zu abrupt: ähnliche Genres sind besser als ganz fremde
        """
        genre_streak = context.get_genre_streak()
        same_genre = (current.detected_genre == candidate.detected_genre)

        if genre_streak < 4:
            # "Noch im Genre bleiben"
            return 1.0 if same_genre else 0.5

        elif genre_streak == 4 or genre_streak == 5:
            # "Anfang von Genre-Fatigue"
            return 0.8 if same_genre else 0.7  # Genre-Wechsel leicht bevorzugt

        else:  # > 5
            # "Definitiv Genre-Wechsel Zeit!"
            if same_genre:
                return 0.3  # "Bitte nicht"
            else:
                return 0.9  # "Ja, neues Genre!"

    def _score_structure(self, current, candidate):
        """
        Structure Score: Können wir an guten Punkten mixen?
        """
        # Ideal: Current faded out bei 3:45, Candidate faded in bei 0:05

        fade_out_ok = current.mix_out_point > 0  # 3:00+
        fade_in_ok = candidate.mix_in_point < 10  # < 0:10

        if fade_out_ok and fade_in_ok:
            return 0.95  # Perfekt
        elif fade_out_ok or fade_in_ok:
            return 0.70  # Okay
        else:
            return 0.40  # Schwierig

    def _calculate_bonuses(self, current, candidate, context, strategy):
        """
        Spezielle Bonuses für intelligente Entscheidungen.
        """
        bonus = 0.0

        # === SURPRISE BONUS ===
        # "Ich habe nicht erwartet, dass dieser Track hier gut passt, aber er tut es!"

        # Wenn Tracks sehr unterschiedlich sind, aber harmonisch gut:
        camelot_distance = self._camelot_distance(
            current.camelotCode, candidate.camelotCode
        )
        bpm_diff = abs(current.bpm - candidate.bpm)
        genre_same = current.detected_genre == candidate.detected_genre

        if camelot_distance <= 2 and not genre_same and bpm_diff < 10:
            bonus += 0.08  # "Überraschend gute Cross-Genre Transition"

        # === FLOW BONUS ===
        # "Dieser Track passt perfekt zur bisherigen Entwicklung"

        energy_trend = context.get_energy_trend()
        if energy_trend == "RISING":
            if candidate.energy > current.energy:
                bonus += 0.05  # "Verstärke den Aufwärts-Trend"

        elif energy_trend == "FALLING":
            if candidate.energy < current.energy:
                bonus += 0.05  # "Sanfte Fortsetzung des Abstiegs"

        # === PEAK-MOMENT BONUS ===
        # Am Peak: Energie-Konsistenz ist TOP

        if context.get_playlist_phase() == "PEAK":
            if abs(candidate.energy - current.energy) < 5:
                bonus += 0.05  # "Halten den Peak"

        return bonus

    def _calculate_penalties(self, current, candidate, context):
        """
        Penalties für musikalische Fehler.
        """
        penalty = 0.0

        # === JARRING TRANSITION PENALTY ===
        # "Das klingt merkwürdig / bricht den Flow"

        camelot_distance = self._camelot_distance(
            current.camelotCode, candidate.camelotCode
        )
        bpm_diff = abs(current.bpm - candidate.bpm)
        energy_diff = abs(candidate.energy - current.energy)

        # Zu großer BPM-Sprung bei stabiler Energie = schlecht
        if context.get_energy_trend() == "STABLE" and bpm_diff > 40:
            penalty -= 0.15  # "Das ist ein Schock"

        # Zu großer Harmonic Jump + BPM Jump = doppelt schlecht
        if camelot_distance > 4 and bpm_diff > 30:
            penalty -= 0.10  # "Zu viel auf einmal"

        # === REPETITION PENALTY ===
        # "Wir haben gerade einen Track wie diesen gespielt"

        last_track = context.playlist[-1] if context.playlist else None

        if last_track:
            same_bpm = abs(last_track.bpm - candidate.bpm) < 2
            same_energy = abs(last_track.energy - candidate.energy) < 3
            same_genre = last_track.detected_genre == candidate.detected_genre

            if same_bpm and same_energy and same_genre:
                penalty -= 0.20  # "Zu ähnlich zum letzten"

        # === STRATEGY VIOLATION PENALTY ===
        # "Das passt nicht zur gewählten Strategie"

        # (Diese würde in strategy-spezifischen Unterklassen sein)

        return penalty

    def _camelot_distance(self, code1, code2):
        """Berechne Abstand auf Camelot Wheel."""
        num1 = int(code1[:-1])
        num2 = int(code2[:-1])
        mode1 = code1[-1]
        mode2 = code2[-1]

        distance = abs(num1 - num2)

        # Mode Unterschied = +2 (A zu B ist weiter weg)
        if mode1 != mode2:
            distance += 2

        return distance
```

---

## Praktisches Beispiel: Intelligenter vs. Starrer Score

### **Szenario: Am Build-Up Phase, Energie steigt**

```
Aktueller Track: 128 BPM, A Minor (8A), House, Energy 70

Kandidaten:

1. TECHNO TRACK
   - 132 BPM (E Minor 9A, Techno)
   - Energy: 78

   STARRES SYSTEM:
   - Harmonic: 0.95 (adjacent codes)
   - BPM: 0.92 (4 BPM difference)
   - Energy: 0.80
   - Genre: 0.60
   Score = 0.95×0.4 + 0.92×0.2 + 0.80×0.2 + 0.60×0.2 = 0.83

   INTELLIGENTES SYSTEM:
   - Phase: BUILD_UP → harmonic 0.25, energy 0.40, bpm 0.20, genre 0.10
   - Trend: RISING → bonus auf energy & bpm für Steigerung
   - Genre-Streak: 4 → erlaubt Genre-Wechsel!

   Harmonic: 0.95 × 0.25 = 0.24
   BPM: 0.92 × 1.3 × 0.20 = 0.24  (Bonus für Tempo-Steigerung!)
   Energy: 0.80 × 1.2 × 0.40 = 0.38  (Bonus für Energie-Steigerung!)
   Genre: 0.60 × 1.1 × 0.10 = 0.07  (Genre-Wechsel erlaubt)
   Bonus: +0.08 (Cross-Genre Surprise!)

   Score = 0.24 + 0.24 + 0.38 + 0.07 + 0.08 = 1.01 (clamped to 1.0) ✓ GEWINNER!

2. DEEP HOUSE TRACK
   - 125 BPM (G Minor 5A, Deep House)
   - Energy: 72

   STARRES SYSTEM:
   - Harmonic: 0.75 (weiter weg)
   - BPM: 0.95 (3 BPM difference)
   - Energy: 0.82
   - Genre: 0.95 (same family)
   Score = 0.75×0.4 + 0.95×0.2 + 0.82×0.2 + 0.95×0.2 = 0.82

   INTELLIGENTES SYSTEM:
   - Phase: BUILD_UP → weniger Punkte für ähnliches Genre
   - Trend: RISING → Deep House Energie-Steigerung klein
   - Genre-Streak: 4 → "Bitte, etwas anderes"

   Harmonic: 0.75 × 0.25 = 0.19
   BPM: 0.95 × 1.1 × 0.20 = 0.21  (Kleine Steigerung)
   Energy: 0.82 × 0.8 × 0.40 = 0.26  (Weniger Steigerung = Penalty)
   Genre: 0.95 × 0.5 × 0.10 = 0.05  (Genre-Fatigue Penalty!)
   Penalty: -0.05

   Score = 0.19 + 0.21 + 0.26 + 0.05 - 0.05 = 0.66 ✗ NICHT GUT
```

**Ergebnis:**
- **Starres System:** 0.83 vs 0.82 → Deep House gewinnt (LANGWEILIG)
- **Intelligentes System:** 1.0 vs 0.66 → Techno gewinnt (SPANNEND!)

---

## Implementierungs-Roadmap

### Phase 1: Basis-Engine (2-3 Stunden)
```python
# Schicht 1: PlaylistContext
# Schicht 2: DynamicWeightCalculator
# Schicht 3: IntelligentScoreEngine (basis)
```

### Phase 2: Erweiterte Intelligenz (2-3 Stunden)
```python
# Bonuses & Penalties verfeinern
# Genre-Fatigue smart detektieren
# Surprise-Bonus System
# Flow-Bonus für Trends
```

### Phase 3: Strategie-Integration (1-2 Stunden)
```python
# Jede Strategie hat eigene Scoring-Logik
# Peak Time vs Genre Flow vs Energy Wave vs Emotional Journey
# Strategy-specific Penalties
```

### Phase 4: Testing & Validierung (2-3 Stunden)
```python
# Teste Scoring auf realen Playlists
# Vergleiche mit Alt-System
# Fine-tune Gewichte basierend auf Testergebnissen
```

---

## Die Philosophie

**Nicht mechanisch:** Der Score ist nicht einfach eine Formel.

**Musikalisch sinnvoll:** Entscheidungen passen zur DJ-Kunst.

**Kontextabhängig:** Was gut am Anfang ist, ist schlecht am Peak.

**Intelligent:** Das System "versteht" Genre-Fatigue, Trends, Überraschungen.

**Adaptiv:** Je nach Strategie ändern sich die Prioritäten.

---

## Fragen für dich:

1. **Welche der Bonuses/Penalties sind dir am wichtigsten?**
   - Cross-Genre Überraschung?
   - Genre-Fatigue Erkennung?
   - Trend-Fortführung?
   - Etwas anderes?

2. **Sollten Nutzer die Gewichte anpassen können?**
   - Schieber für "wie intelligent" (0% = starr, 100% = sehr adaptiv)?

3. **Welche Metriken sollten noch Einfluss haben?**
   - Danceability?
   - Vocal vs Instrumental?
   - Brightness/Darkness?

Lass mich wissen, und ich implementiere das!
