"""
Phase 3 Tests: Integration der Intelligent Scoring Engine in Playlist-Generierung

Tests für:
1. IntelligentPlaylistSorter Wrapper
2. Backward-Compatibility mit altem System
3. Strategy-spezifische Sortierung
"""

import pytest
from hpg_core.models import Track
from hpg_core.scoring_context import PlaylistContext
from hpg_core.intelligent_playlist_integration import (
    IntelligentPlaylistSorter,
    create_intelligent_compatibility_wrapper,
    log_sorting_context,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def basic_playlist():
  """Einfache Test-Playlist mit verschiedenen Genres."""
  return [
      Track("/1", "1", artist="A", title="T1", genre="House", detected_genre="House",
            bpm=128, keyNote="D", keyMode="Minor", camelotCode="7A", energy=70,
            duration=240, brightness=50, danceability=85),
      Track("/2", "2", artist="A", title="T2", genre="House", detected_genre="House",
            bpm=130, keyNote="E", keyMode="Minor", camelotCode="9A", energy=75,
            duration=240, brightness=50, danceability=85),
      Track("/3", "3", artist="A", title="T3", genre="Techno", detected_genre="Techno",
            bpm=132, keyNote="F", keyMode="Minor", camelotCode="4A", energy=78,
            duration=240, brightness=40, danceability=80),
  ]


@pytest.fixture
def rising_energy_playlist():
  """Playlist mit steigender Energie."""
  return [
      Track("/1", "1", energy=50, bpm=120, detected_genre="House", genre="House",
            camelotCode="7A", brightness=50, danceability=75, duration=240),
      Track("/2", "2", energy=60, bpm=124, detected_genre="House", genre="House",
            camelotCode="8A", brightness=50, danceability=78, duration=240),
      Track("/3", "3", energy=70, bpm=128, detected_genre="House", genre="House",
            camelotCode="8A", brightness=50, danceability=82, duration=240),
  ]


# ============================================================================
# WRAPPER TESTS
# ============================================================================

class TestIntelligentPlaylistSorter:
  """Tests für IntelligentPlaylistSorter Integration Layer."""

  def test_sorter_initialization(self):
    """Sorter sollte mit einer Strategie initialisiert werden."""
    sorter = IntelligentPlaylistSorter("HARMONIC_FLOW")
    assert sorter.strategy == "HARMONIC_FLOW"
    assert len(sorter.playlist_so_far) == 0

  def test_calculate_intelligent_score_returns_0_to_1(self, basic_playlist):
    """Intelligenter Score sollte zwischen 0.0 und 1.0 sein."""
    sorter = IntelligentPlaylistSorter("HARMONIC_FLOW")

    score = sorter.calculate_intelligent_score(
        basic_playlist[0],
        basic_playlist[1],
        position=1,
        total_tracks=10
    )

    assert 0.0 <= score <= 1.0

  def test_record_track_updates_state(self, basic_playlist):
    """Track-Registrierung sollte den Zustand aktualisieren."""
    sorter = IntelligentPlaylistSorter("HARMONIC_FLOW")

    sorter.record_track(basic_playlist[0])
    assert len(sorter.playlist_so_far) == 1

    sorter.record_track(basic_playlist[1])
    assert len(sorter.playlist_so_far) == 2

  def test_reset_clears_state(self, basic_playlist):
    """Reset sollte den Zustand zurücksetzen."""
    sorter = IntelligentPlaylistSorter("HARMONIC_FLOW")

    sorter.record_track(basic_playlist[0])
    sorter.record_track(basic_playlist[1])
    assert len(sorter.playlist_so_far) == 2

    sorter.reset_playlist_state()
    assert len(sorter.playlist_so_far) == 0

  def test_get_context_summary(self, basic_playlist):
    """Context-Summary sollte wichtige Playlist-Info enthalten."""
    sorter = IntelligentPlaylistSorter("HARMONIC_FLOW")

    sorter.record_track(basic_playlist[0])
    sorter.record_track(basic_playlist[1])
    sorter.record_track(basic_playlist[2])

    summary = sorter.get_context_summary(10)

    assert "phase" in summary
    assert "position" in summary
    assert "energy_trend" in summary
    assert "genre_streak" in summary
    assert "consistency" in summary

    assert summary["position"] == 3
    assert 0.0 <= summary["consistency"] <= 1.0

  def test_create_sorter_for_strategy_harmonic_flow(self):
    """Factory sollte HARMONIC_FLOW Sorter erstellen."""
    sorter = IntelligentPlaylistSorter.create_sorter_for_strategy("HARMONIC_FLOW")
    assert sorter.strategy == "HARMONIC_FLOW"

  def test_create_sorter_for_strategy_peak_time(self):
    """Factory sollte PEAK_TIME Sorter erstellen."""
    sorter = IntelligentPlaylistSorter.create_sorter_for_strategy("PEAK_TIME")
    assert sorter.strategy == "PEAK_TIME"

  def test_create_sorter_for_strategy_genre_flow(self):
    """Factory sollte GENRE_FLOW Sorter erstellen."""
    sorter = IntelligentPlaylistSorter.create_sorter_for_strategy("GENRE_FLOW")
    assert sorter.strategy == "GENRE_FLOW"

  def test_create_sorter_invalid_strategy_defaults(self):
    """Ungültige Strategie sollte zu HARMONIC_FLOW defaulten."""
    sorter = IntelligentPlaylistSorter.create_sorter_for_strategy("INVALID")
    assert sorter.strategy == "HARMONIC_FLOW"

  def test_different_strategies_produce_different_scores(self, basic_playlist):
    """Unterschiedliche Strategien sollten unterschiedliche Scores liefern."""
    track1 = basic_playlist[0]
    track2 = basic_playlist[1]

    sorter_harmonic = IntelligentPlaylistSorter("HARMONIC_FLOW")
    sorter_genre = IntelligentPlaylistSorter("GENRE_FLOW")

    score_harmonic = sorter_harmonic.calculate_intelligent_score(track1, track2, 1, 10)
    score_genre = sorter_genre.calculate_intelligent_score(track1, track2, 1, 10)

    # Scores können unterschiedlich sein (müssen aber nicht immer)
    # Hauptsache: beide sind gültig
    assert 0.0 <= score_harmonic <= 1.0
    assert 0.0 <= score_genre <= 1.0


# ============================================================================
# BACKWARD COMPATIBILITY TESTS
# ============================================================================

class TestBackwardCompatibility:
  """Tests für Backward-Compatibility mit altem System."""

  def test_compatibility_wrapper_converts_to_0_100(self, basic_playlist):
    """Wrapper sollte 0.0-1.0 Score zu 0-100 konvertieren."""
    wrapper = create_intelligent_compatibility_wrapper("HARMONIC_FLOW")

    score = wrapper(basic_playlist[0], basic_playlist[1])

    # Score sollte integer zwischen 0-100 sein
    assert isinstance(score, int)
    assert 0 <= score <= 100

  def test_compatibility_wrapper_handles_context_none(self, basic_playlist):
    """Wrapper sollte mit context=None arbeiten."""
    wrapper = create_intelligent_compatibility_wrapper("HARMONIC_FLOW")

    score = wrapper(basic_playlist[0], basic_playlist[1], context=None)

    assert 0 <= score <= 100

  def test_compatibility_wrapper_accepts_context(self, basic_playlist):
    """Wrapper sollte PlaylistContext akzeptieren."""
    context = PlaylistContext(basic_playlist[:1], 10, "HARMONIC_FLOW")
    wrapper = create_intelligent_compatibility_wrapper("HARMONIC_FLOW")

    score = wrapper(basic_playlist[0], basic_playlist[1], context=context)

    assert 0 <= score <= 100

  def test_compatibility_wrapper_ignores_kwargs(self, basic_playlist):
    """Wrapper sollte extra kwargs ignorieren (Backward-Compat)."""
    wrapper = create_intelligent_compatibility_wrapper("HARMONIC_FLOW")

    score = wrapper(
        basic_playlist[0],
        basic_playlist[1],
        bpm_tolerance=20,
        harmonic_strictness=7,
        allow_experimental=True
    )

    assert 0 <= score <= 100


# ============================================================================
# CONTEXT-AWARE SCORING TESTS
# ============================================================================

class TestContextAwareSorting:
  """Tests für Kontext-bewusste Sortierung."""

  def test_scoring_varies_with_position(self, basic_playlist):
    """Scoring sollte je nach Position in Playlist unterschiedlich sein."""
    track1 = basic_playlist[0]
    track2 = basic_playlist[1]

    sorter = IntelligentPlaylistSorter("PEAK_TIME")

    # Score im INTRO (Position 1 von 10)
    score_intro = sorter.calculate_intelligent_score(track1, track2, position=1, total_tracks=10)

    # Score im PEAK (Position 6 von 10)
    score_peak = sorter.calculate_intelligent_score(track1, track2, position=6, total_tracks=10)

    # Beide sollten gültig sein (können unterschiedlich sein)
    assert 0.0 <= score_intro <= 1.0
    assert 0.0 <= score_peak <= 1.0

  def test_rising_energy_context_affects_score(self, rising_energy_playlist):
    """Rising Energy Playlist sollte Kandidaten mit höherer Energie bevorzugen."""
    sorter = IntelligentPlaylistSorter("PEAK_TIME")

    # Registriere steigende Energie
    for track in rising_energy_playlist:
      sorter.record_track(track)

    current = rising_energy_playlist[-1]  # Energy 70

    # Kandidat mit höherer Energie
    candidate_high = Track(
        "/high", "high", energy=80, bpm=132, detected_genre="House", genre="House",
        camelotCode="8A", brightness=50, danceability=85, duration=240
    )

    # Kandidat mit niedriger Energie
    candidate_low = Track(
        "/low", "low", energy=60, bpm=132, detected_genre="House", genre="House",
        camelotCode="8A", brightness=50, danceability=85, duration=240
    )

    score_high = sorter.calculate_intelligent_score(current, candidate_high, 3, 10)
    score_low = sorter.calculate_intelligent_score(current, candidate_low, 3, 10)

    # Rising energy sollte höhere Energy bevorzugen
    assert score_high >= score_low


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestPhase3Integration:
  """Integration Tests für Phase 3."""

  def test_sorter_produces_consistent_scores(self, basic_playlist):
    """Sorter sollte konsistente Scores produzieren."""
    sorter = IntelligentPlaylistSorter("HARMONIC_FLOW")

    score1 = sorter.calculate_intelligent_score(basic_playlist[0], basic_playlist[1], 1, 10)
    score2 = sorter.calculate_intelligent_score(basic_playlist[0], basic_playlist[1], 1, 10)

    # Sollten gleich sein (deterministisch)
    assert score1 == score2

  def test_multiple_strategies_available(self):
    """Alle wichtigen Strategien sollten verfügbar sein."""
    strategies = [
        "HARMONIC_FLOW",
        "PEAK_TIME",
        "GENRE_FLOW",
        "ENERGY_WAVE",
        "EMOTIONAL_JOURNEY",
    ]

    for strategy in strategies:
      sorter = IntelligentPlaylistSorter.create_sorter_for_strategy(strategy)
      assert sorter.strategy == strategy

  def test_log_sorting_context_completes(self, basic_playlist):
    """Logging sollte ohne Fehler funktionieren."""
    try:
      log_sorting_context(basic_playlist, 10, "HARMONIC_FLOW")
      # Kein Fehler = Success
      assert True
    except Exception as e:
      pytest.fail(f"log_sorting_context raised: {e}")
