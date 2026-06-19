"""
Phase 3: Integration Layer - Intelligent Scoring in Playlist Generation

Verbindet die neue intelligente Scoring-Engine (Phase 1+2) mit dem
vorhandenen Playlist-Sorter für nahtlose Integration.

Ersetzt calculate_compatibility() mit dem intelligenten System,
aber behält die bestehende Schnittstelle.
"""

import logging
from typing import List
from .models import Track
from .scoring_context import PlaylistContext
from .scoring_engine import IntelligentScoreEngine

logger = logging.getLogger(__name__)


class IntelligentPlaylistSorter:
  """
  Integration Layer für Intelligent Scoring in Playlist-Generierung.

  Ersetzt die starre calculate_compatibility() mit der adaptiven
  IntelligentScoreEngine unter Beibehaltung der bestehenden API.
  """

  def __init__(self, strategy: str = "HARMONIC_FLOW"):
    """
    Initialisiere den intelligenten Sorter.

    Args:
      strategy: Playlist-Strategie (HARMONIC_FLOW, PEAK_TIME, GENRE_FLOW, etc.)
    """
    self.engine = IntelligentScoreEngine()
    self.strategy = strategy
    self.playlist_so_far = []

  def calculate_intelligent_score(
      self,
      current: Track,
      candidate: Track,
      position: int = 0,
      total_tracks: int = 10
  ) -> float:
    """
    Berechne intelligenten Score mit Kontext.

    Args:
      current: Aktueller Track
      candidate: Kandidat-Track
      position: Aktuelle Position in Playlist
      total_tracks: Ziel-Länge der Playlist

    Returns:
      Score 0.0-1.0
    """
    context = PlaylistContext(self.playlist_so_far, total_tracks, self.strategy)

    score = self.engine.calculate_score(
        current, candidate, context, self.strategy
    )

    return score

  def record_track(self, track: Track) -> None:
    """Registriere einen Track als Teil der bisherigen Playlist."""
    self.playlist_so_far.append(track)

  def reset_playlist_state(self) -> None:
    """Setze den Playlist-Zustand zurück."""
    self.playlist_so_far = []

  def get_context_summary(self, total_tracks: int) -> dict:
    """
    Hole Zusammenfassung des aktuellen Kontextes.

    Returns:
      Dictionary mit phase, energy_trend, genre_streak, etc.
    """
    context = PlaylistContext(self.playlist_so_far, total_tracks, self.strategy)

    return {
        "phase": context.get_playlist_phase(),
        "position": context.position,
        "energy_trend": context.get_energy_trend(),
        "bpm_trend": context.get_bpm_trend(),
        "camelot_stability": context.get_camelot_stability(),
        "genre_streak": context.get_genre_streak(),
        "consistency": self._measure_consistency(context),
    }

  def _measure_consistency(self, context: PlaylistContext) -> float:
    """Messe aktuelle Playlist-Konsistenz (0.0-1.0)."""
    if len(self.playlist_so_far) < 3:
      return 0.5

    energies = [t.energy for t in self.playlist_so_far[-5:]]
    energy_variance = sum((e - sum(energies) / len(energies)) ** 2 for e in energies) / len(energies)
    consistency = 1.0 - (energy_variance / 5000)  # Normalisiert

    return max(0.0, min(1.0, consistency))

  @staticmethod
  def create_sorter_for_strategy(strategy: str) -> "IntelligentPlaylistSorter":
    """
    Factory-Methode: Erstelle Sorter für bestimmte Strategie.

    Args:
      strategy: Name der Strategie

    Returns:
      Konfigurierter IntelligentPlaylistSorter
    """
    valid_strategies = [
        "HARMONIC_FLOW",
        "PEAK_TIME",
        "GENRE_FLOW",
        "ENERGY_WAVE",
        "EMOTIONAL_JOURNEY",
        "HARMONIC_CONSISTENT",
        "BPM_PROGRESSION",
        "SMOOTH_CROSSFADE",
    ]

    if strategy not in valid_strategies:
      logger.warning(
          f"Strategy '{strategy}' unknown, defaulting to HARMONIC_FLOW"
      )
      strategy = "HARMONIC_FLOW"

    return IntelligentPlaylistSorter(strategy)


def create_intelligent_compatibility_wrapper(
    strategy: str = "HARMONIC_FLOW"
) -> callable:
  """
  Erstelle einen Wrapper, der IntelligentScoreEngine als
  calculate_compatibility() Replacement nutzen kann.

  Konvertiert 0.0-1.0 float zurück zu 0-100 int für Backward-Compatibility.

  Args:
    strategy: Playlist-Strategie

  Returns:
    Funktion mit Signatur (track1, track2, context) -> int score
  """
  sorter = IntelligentPlaylistSorter(strategy)

  def intelligent_compatibility(
      track1: Track,
      track2: Track,
      context: PlaylistContext = None,
      **kwargs
  ) -> int:
    """
    Berechne Kompatibilität mit intelligentem System.

    Args:
      track1: Aktueller Track
      track2: Kandidat-Track
      context: PlaylistContext (optional)
      **kwargs: Wird ignoriert (für Backward-Compatibility)

    Returns:
      Score 0-100 (für Backward-Compatibility)
    """
    if context is None:
      context = PlaylistContext([], 10, strategy)

    # Nutze intelligent score, konvertiere zu 0-100 range
    intelligent_score = sorter.engine.calculate_score(
        track1, track2, context, strategy
    )

    # Konvertiere 0.0-1.0 zu 0-100
    legacy_score = int(intelligent_score * 100)

    return legacy_score

  return intelligent_compatibility


def log_sorting_context(
    playlist_so_far: List[Track],
    total_tracks: int,
    strategy: str
) -> None:
  """Debug: Zeige Sorting-Kontext."""
  context = PlaylistContext(playlist_so_far, total_tracks, strategy)

  logger.debug(
      f"Playlist Sorting Context: phase={context.get_playlist_phase()}, "
      f"position={context.position}/{total_tracks}, "
      f"energy_trend={context.get_energy_trend()}, "
      f"genre_streak={context.get_genre_streak()}, "
      f"strategy={strategy}"
  )
