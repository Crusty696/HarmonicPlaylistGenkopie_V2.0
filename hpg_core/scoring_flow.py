"""
Flow Continuity Analysis: Erkennung von Playlist-Flüssen

Analyisiert, wie "smooth" die bisherige Playlist fließt und
passt die Scoring-Strategie an, um Kontinuität zu belohnen.

Beispiel:
- Wenn Playlist RISING Energy hatte: favorisiere weitere Rising Energy
- Wenn Playlist TIGHT harmonic war: bleib tight
- Wenn Playlist wechselnd war: erlaube Variabilität
"""

import logging
from typing import List, Tuple
from .models import Track
from .scoring_context import PlaylistContext

logger = logging.getLogger(__name__)


class FlowAnalyzer:
  """Analysiert und beschreibt Playlist-Flüsse."""

  # Flow-Beschreibungen für Logging
  FLOW_STATES = {
    "SMOOTH_RISING": "Sanfte Energie-Eskalation",
    "SMOOTH_FALLING": "Sanfte Energie-Reduktion",
    "SMOOTH_STABLE": "Stabile Energie",
    "CHAOTIC": "Chaotische Energie-Sprünge",
    "TIGHT_HARMONIC": "Enge harmonische Übergänge",
    "LOOSE_HARMONIC": "Lose harmonische Übergänge",
    "MIXED_HARMONIC": "Gemischte harmonische Übergänge",
    "CONSISTENT_GENRE": "Konsistentes Genre",
    "VARIED_GENRE": "Variiertes Genre",
  }

  @staticmethod
  def detect_flow_pattern(context: PlaylistContext) -> str:
    """
    Erkennt das aktuelle Flow-Muster der Playlist.

    Returns:
      String wie "SMOOTH_RISING", "TIGHT_HARMONIC", etc.
    """
    if len(context.playlist) < 3:
      return "UNDEFINED"

    energy_trend = context.get_energy_trend()
    camelot_stability = context.get_camelot_stability()
    genre_streak = context.get_genre_streak()

    # === ENERGIE-FLOW ===
    if energy_trend == "RISING":
      return "SMOOTH_RISING"
    elif energy_trend == "FALLING":
      return "SMOOTH_FALLING"
    elif energy_trend == "STABLE":
      return "SMOOTH_STABLE"

    # Fallback
    return "UNDEFINED"

  @staticmethod
  def get_flow_consistency_score(context: PlaylistContext) -> float:
    """
    Bewertet, wie konsistent der Playlist-Fluss ist.

    Returns:
      0.0 = sehr chaotisch, 1.0 = sehr konsistent
    """
    if len(context.playlist) < 3:
      return 0.5  # Neutral bei wenig Daten

    playlist = context.playlist
    energies = [t.energy for t in playlist[-5:]]  # Letzte 5 oder weniger

    # === ENERGIE-KONSISTENZ ===
    energy_variance = FlowAnalyzer._calculate_variance(energies)
    energy_consistency = 1.0 - (energy_variance / 100.0)  # Normalisiert auf 0-1

    # === BPM-KONSISTENZ ===
    bpms = [t.bpm for t in playlist[-5:]]
    bpm_variance = FlowAnalyzer._calculate_variance(bpms)
    bpm_consistency = 1.0 - (bpm_variance / 100.0)  # Normalisiert

    # === GENRE-KONSISTENZ ===
    genres = [t.detected_genre or t.genre for t in playlist[-5:]]
    genre_changes = sum(1 for i in range(1, len(genres)) if genres[i] != genres[i-1])
    genre_consistency = 1.0 - (genre_changes / len(genres))

    # === GEWICHTETE GESAMTKONSISTENZ ===
    consistency = (
        energy_consistency * 0.4 +  # Energie am wichtigsten
        bpm_consistency * 0.3 +
        genre_consistency * 0.3
    )

    return max(0.0, min(1.0, consistency))

  @staticmethod
  def predict_good_flow_candidates(
      context: PlaylistContext,
      candidates: List[Track]
  ) -> List[Tuple[Track, float]]:
    """
    Bewertet Kandidaten basierend auf Flow-Fortsetzung.

    Args:
      context: Playlist-Kontext
      candidates: Liste von Kandidaten

    Returns:
      Liste von (Track, flow_score) Tupeln, nach Score sortiert
    """
    if len(context.playlist) < 2:
      return [(t, 0.5) for t in candidates]

    current_track = context.playlist[-1]
    flow_pattern = FlowAnalyzer.detect_flow_pattern(context)

    candidate_scores = []

    for candidate in candidates:
      flow_score = 0.5  # Neutral

      # === Energie-Flow ===
      if flow_pattern == "SMOOTH_RISING":
        if candidate.energy > current_track.energy:
          flow_score += 0.3  # Gutes Fortsetzung
        elif candidate.energy < current_track.energy - 15:
          flow_score -= 0.2  # Bricht Muster

      elif flow_pattern == "SMOOTH_FALLING":
        if candidate.energy < current_track.energy:
          flow_score += 0.3
        elif candidate.energy > current_track.energy + 15:
          flow_score -= 0.2

      elif flow_pattern == "SMOOTH_STABLE":
        energy_diff = abs(candidate.energy - current_track.energy)
        if energy_diff < 10:
          flow_score += 0.2  # Stabil halten ist gut

      # === BPM-Flow ===
      bpm_trend = context.get_bpm_trend()
      if bpm_trend == "ACCELERATING":
        if candidate.bpm > current_track.bpm:
          flow_score += 0.15
      elif bpm_trend == "DECELERATING":
        if candidate.bpm < current_track.bpm:
          flow_score += 0.15

      # === Genre-Konsistenz ===
      current_genre = current_track.detected_genre or current_track.genre
      candidate_genre = candidate.detected_genre or candidate.genre
      genre_streak = context.get_genre_streak()

      # Wenn Streak < 3: erlaube Genre-Wechsel
      if genre_streak < 3:
        flow_score += 0.1  # Leichter Bonus für Genre-Variabilität

      # Wenn Streak >= 5: belohne Genre-Wechsel
      elif genre_streak >= 5:
        if candidate_genre != current_genre:
          flow_score += 0.2
        else:
          flow_score -= 0.15

      candidate_scores.append((candidate, max(0.0, min(1.0, flow_score))))

    # Sortiere nach Score (absteigend)
    candidate_scores.sort(key=lambda x: x[1], reverse=True)

    return candidate_scores

  @staticmethod
  def measure_flow_coherence(context: PlaylistContext) -> float:
    """
    Misst die musikalische Kohärenz des Flows (0.0-1.0).

    Berücksichtigt:
    - Sanftheit der Energie-Übergänge
    - Harmonic-Enge
    - Genre-Konsistenz vs. Vielfalt (phasenabhängig)
    """
    if len(context.playlist) < 3:
      return 0.5

    playlist = context.playlist

    # === ENERGIE-ÜBERGÄNGE ===
    energy_transitions = []
    for i in range(len(playlist) - 1):
      energy_diff = abs(playlist[i+1].energy - playlist[i].energy)
      # Ideal: 10-20 Punkte pro Übergang (sanft aber vorhanden)
      transition_quality = 1.0 - (abs(15 - energy_diff) / 30.0)  # Optimal bei 15
      energy_transitions.append(max(0.0, min(1.0, transition_quality)))

    avg_energy_quality = sum(energy_transitions) / len(energy_transitions) if energy_transitions else 0.5

    # === HARMONIC-ENGE ===
    camelot_stability = context.get_camelot_stability()
    if camelot_stability == "TIGHT":
      harmonic_quality = 0.9
    elif camelot_stability == "MEDIUM":
      harmonic_quality = 0.7
    elif camelot_stability == "LOOSE":
      harmonic_quality = 0.5
    else:
      harmonic_quality = 0.5

    # === GENRE-VIELFALT ===
    current_phase = context.get_playlist_phase()
    genre_streak = context.get_genre_streak()

    # Im PEAK: Genre-Konsistenz ist gut
    if current_phase == "PEAK":
      if genre_streak >= 3:
        genre_quality = 0.8
      else:
        genre_quality = 0.5
    # Im BUILD_UP: Genre-Vielfalt ist OK
    elif current_phase == "BUILD_UP":
      if genre_streak < 5:
        genre_quality = 0.8
      else:
        genre_quality = 0.5
    else:
      genre_quality = 0.7

    # === GESAMTKOHÄRENZ ===
    coherence = (
        avg_energy_quality * 0.5 +
        harmonic_quality * 0.3 +
        genre_quality * 0.2
    )

    return max(0.0, min(1.0, coherence))

  @staticmethod
  def _calculate_variance(values: List[float]) -> float:
    """Berechnet die Varianz einer Liste."""
    if not values:
      return 0.0

    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)

    return variance

  @staticmethod
  def log_flow_analysis(context: PlaylistContext) -> None:
    """Debug: Zeige Flow-Analyse."""
    flow_pattern = FlowAnalyzer.detect_flow_pattern(context)
    consistency = FlowAnalyzer.get_flow_consistency_score(context)
    coherence = FlowAnalyzer.measure_flow_coherence(context)

    flow_desc = FlowAnalyzer.FLOW_STATES.get(flow_pattern, "Unknown")

    logger.debug(
        f"Flow Analysis: pattern={flow_pattern} ({flow_desc}), "
        f"consistency={consistency:.2f}, coherence={coherence:.2f}"
    )
