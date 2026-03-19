"""
Erweiterte Bonuses und Penalties: Phase 2

Intelligentere, musik-informed Bonuses und Penalties basierend auf:
- Harmonic Überraschung vs. Vorhersehbarkeit
- Energie-Kontrolliertherit vs. Chaos
- Genre-Storytelling statt bloße Genre-Fatigue
- Spektrale Komplementarität (Brightness/Darkness)
- Danceability-Konsistenz
"""

import logging
from .models import Track
from .scoring_context import PlaylistContext
from .genre_compatibility import GenreCompatibilityMatrix

logger = logging.getLogger(__name__)


class EnhancedBonusCalculator:
    """Berechnet intelligente Bonuses."""

    @staticmethod
    def calculate_all_bonuses(
        current: Track, candidate: Track, context: PlaylistContext, strategy: str
    ) -> float:
        """
        Berechnet Summe aller Bonuses (max +0.2).

        Args:
          current: Aktueller Track
          candidate: Kandidat-Track
          context: Playlist-Kontext
          strategy: Strategie (z.B. "PEAK_TIME")

        Returns:
          Bonus 0.0 to +0.2
        """
        bonus = 0.0

        # === SURPRISE BONUS (erweitert) ===
        bonus += EnhancedBonusCalculator._surprise_bonus(current, candidate, context)

        # === FLOW BONUS (erweitert) ===
        bonus += EnhancedBonusCalculator._flow_bonus(current, candidate, context)

        # === SPECTRAL COMPLEMENT BONUS ===
        bonus += EnhancedBonusCalculator._spectral_bonus(current, candidate)

        # === DANCEABILITY MATCH BONUS ===
        bonus += EnhancedBonusCalculator._danceability_bonus(
            current, candidate, context
        )

        # === PEAK MOMENTUM BONUS ===
        if context.get_playlist_phase() == "PEAK":
            bonus += EnhancedBonusCalculator._peak_momentum_bonus(
                current, candidate, context
            )

        # === STRATEGY-SPECIFIC BONUSES ===
        if strategy == "EMOTIONAL_JOURNEY":
            bonus += EnhancedBonusCalculator._emotional_journey_bonus(
                current, candidate
            )

        elif strategy == "GENRE_FLOW":
            bonus += EnhancedBonusCalculator._genre_storytelling_bonus(
                current, candidate
            )

        return min(0.2, bonus)

    @staticmethod
    def _surprise_bonus(
        current: Track, candidate: Track, context: PlaylistContext
    ) -> float:
        """
        Belohne überraschende, aber passende Übergänge.

        Wenn Camelot eng aber Genre weit entfernt (oder umgekehrt):
        Das ist überraschend GUT!
        """
        bonus = 0.0

        camelot_dist = EnhancedBonusCalculator._camelot_distance(
            current.camelotCode, candidate.camelotCode
        )

        current_genre = current.detected_genre or current.genre
        candidate_genre = candidate.detected_genre or candidate.genre
        genre_compat = GenreCompatibilityMatrix.get_compatibility(
            current_genre, candidate_genre
        )

        bpm_diff = abs(current.bpm - candidate.bpm)

        # Überraschung 1: Harmonisch eng, Genre-Wechsel, BPM-ähnlich
        # → "Wie passt das?! Aber es passt!"
        if camelot_dist <= 1 and genre_compat < 0.6 and bpm_diff < 5:
            bonus += 0.08

        # Überraschung 2: Genre sehr kompatibel, aber Camelot weit
        # → "Genres harmonieren perfekt, auch wenn Camelot weit"
        if genre_compat >= 0.85 and camelot_dist > 3 and bpm_diff < 10:
            bonus += 0.06

        # Überraschung 3: Alles unerwartet, aber Energy-Trend macht Sinn
        # → "Technisch seltsam, musikalisch aber richtig für den Moment"
        energy_trend = context.get_energy_trend()
        if (
            energy_trend == "RISING"
            and candidate.energy > current.energy
            and camelot_dist <= 2
        ):
            bonus += 0.04

        return bonus

    @staticmethod
    def _flow_bonus(
        current: Track, candidate: Track, context: PlaylistContext
    ) -> float:
        """
        Belohne glatte, natürliche Flüsse.

        Wenn Kandidat den bisherigen "Fluss" perfekt fortsetzt.
        """
        bonus = 0.0

        energy_trend = context.get_energy_trend()
        bpm_trend = context.get_bpm_trend()

        # === ENERGY FLOW ===
        if energy_trend == "RISING":
            energy_diff = candidate.energy - current.energy
            if 5 < energy_diff < 20:
                bonus += 0.05  # "Perfekte Energie-Eskalation"

        elif energy_trend == "FALLING":
            energy_diff = current.energy - candidate.energy
            if 5 < energy_diff < 20:
                bonus += 0.05  # "Sanfte Energie-Reduktion"

        # === BPM FLOW ===
        if bpm_trend == "ACCELERATING":
            bpm_diff = candidate.bpm - current.bpm
            if 2 < bpm_diff < 15:
                bonus += 0.04  # "Tempo steigt schön schrittweise"

        elif bpm_trend == "DECELERATING":
            bpm_diff = current.bpm - candidate.bpm
            if 2 < bpm_diff < 15:
                bonus += 0.04  # "Tempo sinkt sanft"

        # === GENRE FLOW ===
        genre_streak = context.get_genre_streak()
        current_genre = current.detected_genre or current.genre
        candidate_genre = candidate.detected_genre or candidate.genre

        # Wenn Genre-Streak mittelhoch, weiche Genre-Wechsel begünstigen
        if 3 <= genre_streak <= 5:
            genre_compat = GenreCompatibilityMatrix.get_compatibility(
                current_genre, candidate_genre
            )
            if 0.6 < genre_compat < 1.0:  # Genre-Wechsel aber kompatibel
                bonus += 0.04  # "Perfekter Genre-Übergangspunkt"

        return bonus

    @staticmethod
    def _spectral_bonus(current: Track, candidate: Track) -> float:
        """
        Belohne Spektral-Komplementarität.

        Wenn Kandidat heller/dunkler als Current:
        Abwechslung im klanglichen Charakter ist gut!
        """
        bonus = 0.0

        current_brightness = getattr(current, "brightness", 50)
        candidate_brightness = getattr(candidate, "brightness", 50)

        brightness_diff = abs(candidate_brightness - current_brightness)

        # Mittlere Unterschiede sind gut (10-30 Punkte)
        if 10 < brightness_diff < 40:
            bonus += 0.03

        return bonus

    @staticmethod
    def _danceability_bonus(
        current: Track, candidate: Track, context: PlaylistContext
    ) -> float:
        """
        Belohne Tanzbarkeits-Konsistenz bei bestimmten Phasen.
        """
        bonus = 0.0

        current_dance = getattr(current, "danceability", 50)
        candidate_dance = getattr(candidate, "danceability", 50)
        dance_diff = abs(candidate_dance - current_dance)

        phase = context.get_playlist_phase()

        # Im PEAK: Enge Tanzbarkeit = Gut
        if phase == "PEAK" and dance_diff < 10:
            bonus += 0.05

        # Im BUILD_UP: Tanzbarkeit steigt = Gut
        if phase == "BUILD_UP" and candidate_dance > current_dance and dance_diff < 20:
            bonus += 0.04

        return bonus

    @staticmethod
    def _peak_momentum_bonus(
        current: Track, candidate: Track, context: PlaylistContext
    ) -> float:
        """
        Besondere Bonuses für Peak-Phasen-Kohärenz.
        """
        bonus = 0.0

        energy_diff = abs(candidate.energy - current.energy)
        bpm_diff = abs(candidate.bpm - current.bpm)

        # PEAK: Enge Energy + BPM = Momentum halten
        if energy_diff < 5 and bpm_diff < 3:
            bonus += 0.06

        # PEAK: Genre-Konsistenz = Fokus halten
        current_genre = current.detected_genre or current.genre
        candidate_genre = candidate.detected_genre or candidate.genre
        if current_genre == candidate_genre:
            bonus += 0.03

        return bonus

    @staticmethod
    def _emotional_journey_bonus(current: Track, candidate: Track) -> float:
        """
        EMOTIONAL_JOURNEY Strategie: Gefühlsmäßige Kontinuität.
        """
        bonus = 0.0

        # Wenn Vocal-Status erhalten bleibt
        current_vocal = getattr(current, "vocal_instrumental", "unknown")
        candidate_vocal = getattr(candidate, "vocal_instrumental", "unknown")
        if current_vocal == candidate_vocal and current_vocal != "unknown":
            bonus += 0.05

        return bonus

    @staticmethod
    def _genre_storytelling_bonus(current: Track, candidate: Track) -> float:
        """
        GENRE_FLOW Strategie: Genre-Story erzählen.
        """
        bonus = 0.0

        current_genre = current.detected_genre or current.genre
        candidate_genre = candidate.detected_genre or candidate.genre

        # Musik-verwandtes Genre-Paar ist eine "gute Geschichte"
        compat = GenreCompatibilityMatrix.get_compatibility(
            current_genre, candidate_genre
        )

        # Nicht gleich, aber verwandt
        if current_genre != candidate_genre and 0.65 <= compat <= 0.95:
            bonus += 0.08  # "Schöne Genre-Progression"

        return bonus

    @staticmethod
    def _camelot_distance(code1: str, code2: str) -> float:
        """Berechne Camelot-Abstand."""
        if not code1 or not code2:
            return 999

        import re

        try:
            match1 = re.match(r"(\d+)([AB])", code1)
            match2 = re.match(r"(\d+)([AB])", code2)

            if not match1 or not match2:
                return 999

            num1, mode1 = int(match1.group(1)), match1.group(2)
            num2, mode2 = int(match2.group(1)), match2.group(2)

            num_distance = min(abs(num1 - num2), 12 - abs(num1 - num2))
            mode_distance = 2 if mode1 != mode2 else 0

            return num_distance + mode_distance

        except (ValueError, AttributeError):
            return 999


class EnhancedPenaltyCalculator:
    """Berechnet intelligente Penalties."""

    @staticmethod
    def calculate_all_penalties(
        current: Track, candidate: Track, context: PlaylistContext
    ) -> float:
        """
        Berechnet Summe aller Penalties (min -0.3).

        Args:
          current: Aktueller Track
          candidate: Kandidat-Track
          context: Playlist-Kontext

        Returns:
          Penalty -0.3 to 0.0
        """
        penalty = 0.0

        # === JARRING TRANSITIONS ===
        penalty += EnhancedPenaltyCalculator._jarring_penalty(
            current, candidate, context
        )

        # === REPETITION PENALTY (erweitert) ===
        penalty += EnhancedPenaltyCalculator._repetition_penalty(
            current, candidate, context
        )

        # === ENERGY CLIFF PENALTY ===
        penalty += EnhancedPenaltyCalculator._energy_cliff_penalty(
            current, candidate, context
        )

        # === SPECTRAL MONOTONY PENALTY ===
        penalty += EnhancedPenaltyCalculator._spectral_monotony_penalty(
            current, candidate, context
        )

        # === TONAL DRIFT PENALTY ===
        penalty += EnhancedPenaltyCalculator._tonal_drift_penalty(
            current, candidate, context
        )

        return max(-0.3, penalty)

    @staticmethod
    def _jarring_penalty(
        current: Track, candidate: Track, context: PlaylistContext
    ) -> float:
        """Strafen für schockierende Übergänge."""
        penalty = 0.0

        camelot_dist = EnhancedPenaltyCalculator._camelot_distance(
            current.camelotCode, candidate.camelotCode
        )
        bpm_diff = abs(current.bpm - candidate.bpm)
        energy_diff = abs(candidate.energy - current.energy)

        # Zu großer BPM-Sprung bei stabiler Energie = merkwürdig
        if context.get_energy_trend() == "STABLE" and bpm_diff > 40:
            penalty -= 0.15

        # Camelot + BPM beides groß = doppelt schlecht
        if camelot_dist > 4 and bpm_diff > 30:
            penalty -= 0.10

        # Sehr großer Energy-Sprung + großer Camelot-Sprung
        if energy_diff > 40 and camelot_dist > 3:
            penalty -= 0.12

        return penalty

    @staticmethod
    def _repetition_penalty(
        current: Track, candidate: Track, context: PlaylistContext
    ) -> float:
        """
        Strafen für zu ähnliche Tracks.

        Erweitert: nutze auch Brightness/Danceability.
        """
        penalty = 0.0

        if not context.playlist:
            return 0.0

        last_track = context.playlist[-1]

        same_bpm = abs(last_track.bpm - candidate.bpm) < 2
        same_energy = abs(last_track.energy - candidate.energy) < 3
        same_brightness = (
            abs(
                getattr(last_track, "brightness", 50)
                - getattr(candidate, "brightness", 50)
            )
            < 10
        )

        last_genre = last_track.detected_genre or last_track.genre
        cand_genre = candidate.detected_genre or candidate.genre
        same_genre = last_genre == cand_genre

        # Wenn alles zu gleich: große Strafe
        if same_bpm and same_energy and same_genre and same_brightness:
            penalty -= 0.20

        # Wenn 3 von 4 Kriterien gleich: mittlere Strafe
        elif sum([same_bpm, same_energy, same_genre, same_brightness]) >= 3:
            penalty -= 0.10

        return penalty

    @staticmethod
    def _energy_cliff_penalty(
        current: Track, candidate: Track, context: PlaylistContext
    ) -> float:
        """Strafen für Energie-Klippen in sensiblen Phasen."""
        penalty = 0.0

        phase = context.get_playlist_phase()
        energy_diff = abs(candidate.energy - current.energy)

        if phase == "PEAK" and energy_diff > 30:
            penalty -= 0.08  # Im Peak: Stabilität ist wichtig

        if phase == "INTRO" and energy_diff > 25:
            penalty -= 0.05  # Am Anfang: sanft aufbauen

        return penalty

    @staticmethod
    def _spectral_monotony_penalty(
        current: Track, candidate: Track, context: PlaylistContext
    ) -> float:
        """
        Strafen für zu lange spektrale Monotonie.

        Wenn letzte 3 Tracks alle ähnliche Brightness haben.
        """
        penalty = 0.0

        if len(context.playlist) < 3:
            return 0.0

        recent_brightnesses = [
            getattr(t, "brightness", 50) for t in context.playlist[-3:]
        ]
        recent_diff = max(recent_brightnesses) - min(recent_brightnesses)

        candidate_brightness = getattr(candidate, "brightness", 50)

        # Wenn alle letzten sehr ähnlich UND neue auch ähnlich
        if (
            recent_diff < 10
            and abs(candidate_brightness - recent_brightnesses[-1]) < 10
        ):
            penalty -= 0.05  # "Zu viel gleiche Farbe"

        return penalty

    @staticmethod
    def _tonal_drift_penalty(
        current: Track, candidate: Track, context: PlaylistContext
    ) -> float:
        """
        Strafen für tonale Divergenz bei engen Übergängen.

        Wenn Camelot sehr eng, aber Energy sehr unterschiedlich: widersprüchlich.
        """
        penalty = 0.0

        camelot_dist = EnhancedPenaltyCalculator._camelot_distance(
            current.camelotCode, candidate.camelotCode
        )
        energy_diff = abs(candidate.energy - current.energy)

        # "Harmonisch eng aber energetisch weit" = widersprüchlich
        if camelot_dist <= 1 and energy_diff > 30:
            penalty -= 0.08

        return penalty

    @staticmethod
    def _camelot_distance(code1: str, code2: str) -> float:
        """Berechne Camelot-Abstand."""
        if not code1 or not code2:
            return 999

        import re

        try:
            match1 = re.match(r"(\d+)([AB])", code1)
            match2 = re.match(r"(\d+)([AB])", code2)

            if not match1 or not match2:
                return 999

            num1, mode1 = int(match1.group(1)), match1.group(2)
            num2, mode2 = int(match2.group(1)), match2.group(2)

            num_distance = min(abs(num1 - num2), 12 - abs(num1 - num2))
            mode_distance = 2 if mode1 != mode2 else 0

            return num_distance + mode_distance

        except (ValueError, AttributeError):
            return 999
