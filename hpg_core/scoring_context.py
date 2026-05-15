"""
Intelligentes Scoring-System: PlaylistContext
Versteht den musikalischen Kontext einer sich entwickelnden Playlist.
"""

from typing import List
from .models import Track
import re
import logging

logger = logging.getLogger(__name__)


class PlaylistContext:
  """Erkennt und verwaltet den Kontext einer Playlist."""

  def __init__(self, playlist_so_far: List[Track], total_tracks: int, strategy: str = "HARMONIC_FLOW"):
    """
    Args:
      playlist_so_far: Tracks, die bereits in der Playlist sind
      total_tracks: Gesamt-Länge, die wir erreichen wollen
      strategy: Welche Strategie wird verwendet (Peak Time, Genre Flow, etc)
    """
    self.playlist = playlist_so_far
    self.position = len(playlist_so_far)
    self.total_tracks = total_tracks if total_tracks > 0 else 1
    self.strategy = strategy
    self._cache = {}

  def get_playlist_phase(self) -> str:
    """
    Bestimmt die aktuelle Phase der Playlist (Intro, Build-Up, Peak, Outro).

    Returns:
      "INTRO", "BUILD_UP", "PEAK", oder "OUTRO"
    """
    if self.total_tracks <= 0:
      return "UNDEFINED"

    progress = self.position / self.total_tracks

    if progress < 0.2:
      return "INTRO"          # 0-20%
    elif progress < 0.5:
      return "BUILD_UP"       # 20-50%
    elif progress < 0.8:
      return "PEAK"           # 50-80%
    else:
      return "OUTRO"          # 80-100%

  def get_energy_trend(self) -> str:
    """
    Erkennt die Energie-Richtung: Steigt sie, fällt sie, oder ist sie stabil?

    Returns:
      "RISING", "FALLING", "STABLE", oder "UNDEFINED" (wenn zu wenig Daten)
    """
    if len(self.playlist) < 3:
      return "UNDEFINED"

    # Schaue auf die letzten 3 Tracks
    recent_energies = [t.energy for t in self.playlist[-3:]]

    # Berechne Trend: ist die letzte Energie höher oder niedriger als die erste?
    energy_change = recent_energies[-1] - recent_energies[0]

    if energy_change > 10:
      return "RISING"         # Energie steigt
    elif energy_change < -10:
      return "FALLING"        # Energie fällt
    else:
      return "STABLE"         # Energie konstant

  def get_genre_streak(self) -> int:
    """
    Zählt, wie lange wir bereits im gleichen Genre sind.
    Wird verwendet zur Erkennung von "Genre-Fatigue".

    Returns:
      Anzahl der Tracks hintereinander im gleichen Genre
    """
    if not self.playlist:
      return 0

    current_genre = self.playlist[-1].detected_genre or self.playlist[-1].genre
    streak = 0

    # Gehe rückwärts durch die Playlist und zähle gleiche Genres
    for track in reversed(self.playlist):
      track_genre = track.detected_genre or track.genre
      if track_genre == current_genre:
        streak += 1
      else:
        break

    return streak

  def get_camelot_stability(self) -> str:
    """
    Misst, wie "stabil" die harmonischen Übergänge waren.
    Enge Übergänge = "TIGHT", lose Übergänge = "LOOSE".

    Returns:
      "TIGHT" (< 2 halftones durchschnittlich),
      "MEDIUM" (2-4 halftones),
      "LOOSE" (> 4 halftones),
      oder "UNDEFINED" wenn nicht genug Daten
    """
    if "camelot_stability" in self._cache:
      return self._cache["camelot_stability"]

    if len(self.playlist) < 2:
      res = "UNDEFINED"
      self._cache["camelot_stability"] = res
      return res

    distances = []

    # Berechne Camelot-Abstände zwischen aufeinanderfolgenden Tracks
    for i in range(len(self.playlist) - 1):
      dist = self._camelot_distance(
          self.playlist[i].camelotCode,
          self.playlist[i + 1].camelotCode
      )
      distances.append(dist)

    if not distances:
      res = "UNDEFINED"
    else:
      avg_distance = sum(distances) / len(distances)

      if avg_distance < 2:
        res = "TIGHT"          # Enger harmonischer Flow
      elif avg_distance < 4:
        res = "MEDIUM"         # Mittlere harmonische Sprünge
      else:
        res = "LOOSE"          # Große harmonische Sprünge

    self._cache["camelot_stability"] = res
    return res

  def get_bpm_trend(self) -> str:
    """
    Erkennt BPM-Richtung: Beschleunigung, Verlangsamung, oder konstant.

    Returns:
      "ACCELERATING", "DECELERATING", "STABLE", oder "UNDEFINED"
    """
    if "bpm_trend" in self._cache:
      return self._cache["bpm_trend"]

    if len(self.playlist) < 3:
      res = "UNDEFINED"
      self._cache["bpm_trend"] = res
      return res

    recent_bpms = [t.bpm for t in self.playlist[-3:]]
    bpm_change = recent_bpms[-1] - recent_bpms[0]

    if bpm_change > 5:
      res = "ACCELERATING"
    elif bpm_change < -5:
      res = "DECELERATING"
    else:
      res = "STABLE"

    self._cache["bpm_trend"] = res
    return res

  def get_last_track_feature(self, feature: str):
    """
    Hole ein Feature des letzten Tracks (z.B. 'energy', 'bpm', 'genre').

    Args:
      feature: Name des Attributes (case-sensitive)

    Returns:
      Der Wert des Features, oder None wenn keine Playlist
    """
    if not self.playlist:
      return None

    last_track = self.playlist[-1]
    return getattr(last_track, feature, None)

  @staticmethod
  def _camelot_distance(code1: str, code2: str) -> float:
    """
    Berechnet den Abstand zwischen zwei Camelot Codes.
    Näher = harmonischer kompatibel.

    Returns:
      Abstand (0 = identisch, bis ~6 = sehr weit weg)
    """
    if not code1 or not code2:
      return 999  # Keine Daten = unbekannt

    try:
      # Parse "8A" → (8, 'A')
      match1 = re.match(r'(\d+)([AB])', code1)
      match2 = re.match(r'(\d+)([AB])', code2)

      if not match1 or not match2:
        return 999

      num1, mode1 = int(match1.group(1)), match1.group(2)
      num2, mode2 = int(match2.group(1)), match2.group(2)

      # Kreis-Abstand (1 bis 12)
      num_distance = min(abs(num1 - num2), 12 - abs(num1 - num2))

      # Mode-Unterschied (A zu B = +2)
      mode_distance = 2 if mode1 != mode2 else 0

      return num_distance + mode_distance

    except (ValueError, AttributeError):
      return 999

  def __repr__(self) -> str:
    """Für Debugging: zeige aktuellen Kontext."""
    return (
        f"PlaylistContext(position={self.position}/{self.total_tracks}, "
        f"phase={self.get_playlist_phase()}, "
        f"energy_trend={self.get_energy_trend()}, "
        f"genre_streak={self.get_genre_streak()})"
    )
