"""
Tests fuer Playlist-Qualitaetsmetriken.
Prueft overall_score, harmonic_flow, energy_consistency, bpm_smoothness.
"""
import pytest
from hpg_core.playlist import calculate_playlist_quality
from tests.fixtures.track_factories import make_track


class TestQualityMetricsBasics:
  """Grundlegende Qualitaetsmetriken."""

  def test_returns_dict(self):
    """Ergebnis ist ein Dictionary."""
    tracks = [
      make_track(camelotCode="8A", bpm=128.0, energy=70),
      make_track(camelotCode="8A", bpm=128.0, energy=72),
    ]
    result = calculate_playlist_quality(tracks, 3.0)
    assert isinstance(result, dict)

  def test_has_required_keys(self):
    """Dictionary hat alle erforderlichen Keys."""
    tracks = [
      make_track(camelotCode="8A", bpm=128.0, energy=70),
      make_track(camelotCode="9A", bpm=128.0, energy=72),
    ]
    result = calculate_playlist_quality(tracks, 3.0)
    required_keys = {"overall_score", "harmonic_flow",
                     "energy_consistency", "bpm_smoothness"}
    for key in required_keys:
      assert key in result, f"Key '{key}' fehlt"

  def test_scores_between_0_and_1(self):
    """Scores zwischen 0 und 1."""
    tracks = [
      make_track(camelotCode="8A", bpm=128.0, energy=70),
      make_track(camelotCode="9A", bpm=128.0, energy=72),
    ]
    result = calculate_playlist_quality(tracks, 3.0)
    for key in ("overall_score", "harmonic_flow",
                "energy_consistency", "bpm_smoothness"):
      assert 0 <= result[key] <= 1.0, (
        f"{key} = {result[key]} nicht in [0, 1]"
      )


class TestPerfectPlaylist:
  """Perfekte Playlist (gleiche Keys und BPM)."""

  def test_same_key_high_harmonic_flow(self):
    """Gleicher Key = hoher Harmonic Flow."""
    tracks = [
      make_track(camelotCode="8A", bpm=128.0, energy=70),
      make_track(camelotCode="8A", bpm=128.0, energy=72),
      make_track(camelotCode="8A", bpm=128.0, energy=74),
    ]
    result = calculate_playlist_quality(tracks, 3.0)
    assert result["harmonic_flow"] >= 0.9, (
      f"Same-Key Harmonic Flow {result['harmonic_flow']} (erwartet >=0.9)"
    )

  def test_same_bpm_high_smoothness(self):
    """Gleicher BPM = hohe BPM Smoothness."""
    tracks = [
      make_track(camelotCode="8A", bpm=128.0, energy=70),
      make_track(camelotCode="9A", bpm=128.0, energy=72),
      make_track(camelotCode="10A", bpm=128.0, energy=74),
    ]
    result = calculate_playlist_quality(tracks, 3.0)
    assert result["bpm_smoothness"] == 1.0, (
      f"Same-BPM Smoothness {result['bpm_smoothness']} (erwartet 1.0)"
    )

  def test_similar_energy_high_consistency(self):
    """Aehnliche Energy = hohe Energy Consistency."""
    tracks = [
      make_track(camelotCode="8A", bpm=128.0, energy=70),
      make_track(camelotCode="8A", bpm=128.0, energy=72),
      make_track(camelotCode="8A", bpm=128.0, energy=71),
    ]
    result = calculate_playlist_quality(tracks, 3.0)
    assert result["energy_consistency"] >= 0.9, (
      f"Energy Consistency {result['energy_consistency']} (erwartet >=0.9)"
    )


class TestPoorPlaylist:
  """Schlechte Playlist (inkompatible Tracks)."""

  def test_incompatible_keys_low_harmonic_flow(self):
    """Inkompatible Keys = niedriger Harmonic Flow."""
    tracks = [
      make_track(camelotCode="1A", bpm=128.0, energy=70),
      make_track(camelotCode="6B", bpm=128.0, energy=70),
      make_track(camelotCode="3A", bpm=128.0, energy=70),
    ]
    result = calculate_playlist_quality(tracks, 3.0)
    # Inkompatible Keys sollten niedrigeren Score haben als perfekte
    assert result["harmonic_flow"] < 0.9

  def test_big_bpm_jumps_low_smoothness(self):
    """Grosse BPM-Spruenge = niedrige Smoothness."""
    tracks = [
      make_track(camelotCode="8A", bpm=120.0, energy=70),
      make_track(camelotCode="8A", bpm=128.0, energy=70),
      make_track(camelotCode="8A", bpm=140.0, energy=70),
    ]
    result = calculate_playlist_quality(tracks, 3.0)
    # Grosse BPM-Spruenge = Smoothness unter 1
    assert result["bpm_smoothness"] < 1.0

  def test_big_energy_jumps_low_consistency(self):
    """Grosse Energy-Spruenge = niedrige Consistency."""
    tracks = [
      make_track(camelotCode="8A", bpm=128.0, energy=10),
      make_track(camelotCode="8A", bpm=128.0, energy=90),
      make_track(camelotCode="8A", bpm=128.0, energy=20),
    ]
    result = calculate_playlist_quality(tracks, 3.0)
    assert result["energy_consistency"] < 0.5, (
      f"Energy Consistency {result['energy_consistency']} "
      f"zu hoch bei grossen Spruengen"
    )


class TestEdgeCases:
  """Edge Cases."""

  def test_single_track(self):
    """1 Track = perfekte Scores (nichts zu vergleichen)."""
    tracks = [make_track(camelotCode="8A", bpm=128.0, energy=70)]
    result = calculate_playlist_quality(tracks, 3.0)
    assert result["overall_score"] == 1.0

  def test_empty_playlist(self):
    """Leere Playlist = perfekte Scores."""
    result = calculate_playlist_quality([], 3.0)
    assert result["overall_score"] == 1.0

  def test_two_identical_tracks(self):
    """Zwei identische Tracks = perfekte Scores."""
    tracks = [
      make_track(camelotCode="8A", bpm=128.0, energy=70),
      make_track(camelotCode="8A", bpm=128.0, energy=70),
    ]
    result = calculate_playlist_quality(tracks, 3.0)
    assert result["overall_score"] >= 0.9

  def test_zero_bpm_tolerance(self):
    """BPM Toleranz 0 - kein Crash."""
    tracks = [
      make_track(camelotCode="8A", bpm=128.0, energy=70),
      make_track(camelotCode="8A", bpm=128.0, energy=70),
    ]
    result = calculate_playlist_quality(tracks, 0.0)
    assert isinstance(result["bpm_smoothness"], float)
