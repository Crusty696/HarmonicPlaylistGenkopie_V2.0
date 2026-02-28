"""
Intelligentes Scoring-System: IntelligentScoreEngine
Berechnet Scores intelligent, nicht mechanisch.
Verwendet PlaylistContext und DynamicWeightCalculator.
"""

import re
import logging
import math
from .models import Track
from .scoring_context import PlaylistContext
from .scoring_weights import DynamicWeightCalculator
from .scoring_bonuses import EnhancedBonusCalculator, EnhancedPenaltyCalculator
from .genre_compatibility import GenreCompatibilityMatrix

logger = logging.getLogger(__name__)


class IntelligentScoreEngine:
  """Berechnet Scores mit musikalischer Intelligenz."""

  def __init__(self):
    """Initialisiere die Engine."""
    self.weight_calculator = DynamicWeightCalculator()

  def calculate_score(
      self,
      current_track: Track,
      candidate: Track,
      context: PlaylistContext,
      strategy: str = "HARMONIC_FLOW"
  ) -> float:
    """
    Berechnet einen intelligenten Score für einen Kandidaten-Track.

    Args:
      current_track: Der gerade spielende Track
      candidate: Der Track, den wir als nächsten in Betracht ziehen
      context: Kontext (Position, Phase, Trends)
      strategy: Playlist-Strategie

    Returns:
      Score zwischen 0.0 und 1.0 (1.0 = perfekt)
    """

    # === BERECHNE EINZELNE SCORES ===

    score_harmonic = self._score_harmonic(current_track, candidate, context)
    score_bpm = self._score_bpm(current_track, candidate, context)
    score_energy = self._score_energy(candidate, context)
    score_genre = self._score_genre(current_track, candidate, context)
    score_structure = self._score_structure(current_track, candidate)

    # === BERECHNE BONUSES & PENALTIES (Phase 2 Enhanced) ===

    bonuses = EnhancedBonusCalculator.calculate_all_bonuses(
        current_track, candidate, context, strategy
    )
    penalties = EnhancedPenaltyCalculator.calculate_all_penalties(
        current_track, candidate, context
    )

    # === HOLE DYNAMISCHE GEWICHTE ===

    weights = self.weight_calculator.calculate_weights(context, strategy)

    # === KOMBINIERE MIT GEWICHTEN ===

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

  def _score_harmonic(self, current: Track, candidate: Track, context: PlaylistContext) -> float:
    """
    Harmonic Score mit intelligenter Anpassung.

    - Wenn bisheriger Drift eng war: mehr Strenge für enge Harmonien
    - Wenn bisheriger Drift lose war: erlauben mehr Sprünge
    """
    camelot_distance = self._camelot_distance(
        current.camelotCode,
        candidate.camelotCode
    )

    # Base Score: je näher, desto besser
    # 0 Abstand = 1.0, 6 Abstand = 0.0
    base = max(0.0, 1.0 - (camelot_distance / 6.0))

    # Intelligente Anpassung basierend auf bisherigem Harmonic Drift
    stability = context.get_camelot_stability()

    if stability == "TIGHT":
      # "Wir waren eng harmonisch, bleib eng"
      base *= 1.2                    # Bonus für enge Harmonien
      if camelot_distance > 3:
        base *= 0.6                  # Penalty für große Sprünge

    elif stability == "LOOSE":
      # "Wir sind locker, ein Sprung ist okay"
      pass                           # Keine besonderen Adjustments

    elif stability == "MEDIUM":
      # "Wir waren moderat, continue"
      if camelot_distance > 4:
        base *= 0.8                  # Leichte Penalty für sehr große Sprünge

    return max(0.0, min(1.0, base))

  def _score_bpm(self, current: Track, candidate: Track, context: PlaylistContext) -> float:
    """
    BPM Score mit Kontext-Intelligenz.

    - Wenn Energie steigt: erlauben größere BPM-Sprünge (exciting!)
    - Wenn Energie stabil: halte BPM ähnlich (smooth)
    - Phase-abhängig: BUILD_UP erlaubt Tempo-Steigerung
    """
    bpm_diff = abs(current.bpm - candidate.bpm)

    # Base Score: je näher, desto besser
    # 0 Unterschied = 1.0, 100 Unterschied = 0.0
    base = max(0.0, 1.0 - (bpm_diff / 100.0))

    # Kontext-basierte Anpassung
    energy_trend = context.get_energy_trend()
    phase = context.get_playlist_phase()
    bpm_trend = context.get_bpm_trend()

    if energy_trend == "RISING" and phase in ["BUILD_UP", "PEAK"]:
      # "Beim Aufbau: Tempo-Steigerung ist SPANNEND"
      if bpm_diff > 5:
        base *= 1.3                  # Bonus für Tempo-Steigerung
      elif bpm_diff < 2:
        base *= 0.9                  # Kleine Penalty wenn keine Veränderung

    elif energy_trend == "FALLING" and phase == "OUTRO":
      # "Beim Outro: Tempo runterfahren ist natürlich"
      if bpm_diff < 15:
        base *= 1.2                  # Bonus für sanftes Tempo-Runterfahren

    elif energy_trend == "STABLE":
      # "Bei stabiler Energie: halte BPM stabil"
      if bpm_diff > 20:
        base *= 0.8                  # Penalty für größere Sprünge

    # BPM-Trend-Kohärenz
    if bpm_trend == "ACCELERATING":
      # "Beschleunigung fortsetzen"
      if candidate.bpm > current.bpm:
        base *= 1.15                 # Bonus für Fortführung

    elif bpm_trend == "DECELERATING":
      # "Verlangsamung fortsetzen"
      if candidate.bpm < current.bpm:
        base *= 1.15                 # Bonus für Fortführung

    return max(0.0, min(1.0, base))

  def _score_energy(self, candidate: Track, context: PlaylistContext) -> float:
    """
    Energy Score ist sehr phase- und strategie-spezifisch.

    Jede Phase hat eine "Target-Energie":
    - INTRO: Niedrig (30)
    - BUILD_UP: Mittel-hoch (60)
    - PEAK: Hoch (85)
    - OUTRO: Mittel (40)
    """
    phase = context.get_playlist_phase()

    # Ziel-Energie basierend auf Phase
    if phase == "INTRO":
      target_energy = 30             # Niedrig anfangen
    elif phase == "BUILD_UP":
      target_energy = 60             # Aufbau
    elif phase == "PEAK":
      target_energy = 85             # Hoch
    elif phase == "OUTRO":
      target_energy = 40             # Runterfahren
    else:
      target_energy = 50             # Fallback: Mittel

    # Score basierend auf Nähe zu Target
    energy_diff = abs(candidate.energy - target_energy)
    score = max(0.0, 1.0 - (energy_diff / 100.0))

    return max(0.0, min(1.0, score))

  def _score_genre(self, current: Track, candidate: Track, context: PlaylistContext) -> float:
    """
    Genre Score mit "Genre-Fatigue" Erkennung.

    - Nach < 4 Tracks: bleib im Genre (Score 1.0)
    - Nach 4-5 Tracks: Genre-Wechsel leicht bevorzugt (0.7)
    - Nach > 5 Tracks: Genre-Wechsel DRINGEND (0.9 für Wechsel)
    """
    current_genre = current.detected_genre or current.genre
    candidate_genre = candidate.detected_genre or candidate.genre
    same_genre = (current_genre == candidate_genre)

    genre_streak = context.get_genre_streak()

    if genre_streak < 4:
      # "Noch nicht müde vom Genre"
      return 1.0 if same_genre else 0.5

    elif genre_streak in [4, 5]:
      # "Anfang von Genre-Fatigue"
      return 0.8 if same_genre else 0.7

    else:  # > 5
      # "Definitiv Genre-Wechsel Zeit!"
      if same_genre:
        return 0.3                   # "Bitte nicht, zu viel vom gleichen"
      else:
        return 0.9                   # "Ja! Neues Genre!"

  def _score_structure(self, current: Track, candidate: Track) -> float:
    """
    Structure Score: Können wir an guten Punkten mixen?

    Ideal: Current hat Fade-Out bei > 3:00,
           Candidate hat Fade-In bei < 10 Sekunden
    """
    # Diese Werte werden gesetzt in analysis.py oder sind default
    fade_out_ok = getattr(current, 'mix_out_point', 0) > 180  # > 3 Minuten
    fade_in_ok = getattr(candidate, 'mix_in_point', 999) < 10  # < 10 Sekunden

    if fade_out_ok and fade_in_ok:
      return 0.95                    # Perfekt
    elif fade_out_ok or fade_in_ok:
      return 0.70                    # Okay
    else:
      return 0.40                    # Schwierig

  def _calculate_bonuses(
      self,
      current: Track,
      candidate: Track,
      context: PlaylistContext,
      strategy: str
  ) -> float:
    """
    DEPRECATED: Verwende EnhancedBonusCalculator statt dessen.
    Diese Methode existiert nur für Backward Compatibility.

    Phase 2 Enhancement: Delegiere zu EnhancedBonusCalculator.
    """
    return EnhancedBonusCalculator.calculate_all_bonuses(
        current, candidate, context, strategy
    )

  def _calculate_penalties(self, current: Track, candidate: Track, context: PlaylistContext) -> float:
    """
    DEPRECATED: Verwende EnhancedPenaltyCalculator statt dessen.
    Diese Methode existiert nur für Backward Compatibility.

    Phase 2 Enhancement: Delegiere zu EnhancedPenaltyCalculator.
    """
    return EnhancedPenaltyCalculator.calculate_all_penalties(
        current, candidate, context
    )

  @staticmethod
  def _camelot_distance(code1: str, code2: str) -> float:
    """
    Berechnet den Abstand zwischen zwei Camelot Codes.
    Näher = harmonischer kompatibel.

    Returns:
      Abstand (0 = identisch, bis ~6 = sehr weit weg)
    """
    if not code1 or not code2:
      return 999                     # Keine Daten = unbekannt

    try:
      # Parse "8A" → (8, 'A')
      match1 = re.match(r'(\d+)([AB])', code1)
      match2 = re.match(r'(\d+)([AB])', code2)

      if not match1 or not match2:
        return 999

      num1, mode1 = int(match1.group(1)), match1.group(2)
      num2, mode2 = int(match2.group(1)), match2.group(2)

      # Kreis-Abstand auf Camelot Wheel (1-12)
      num_distance = min(abs(num1 - num2), 12 - abs(num1 - num2))

      # Mode-Unterschied (A zu B = +2)
      mode_distance = 2 if mode1 != mode2 else 0

      return num_distance + mode_distance

    except (ValueError, AttributeError, TypeError):
      return 999
