import pytest
from hpg_core.scoring_engine import IntelligentScoreEngine
from hpg_core.scoring_context import PlaylistContext
from hpg_core.models import Track

@pytest.fixture
def engine():
    return IntelligentScoreEngine()

@pytest.fixture
def dummy_track():
    return Track(
        filePath="/dummy",
        fileName="dummy.mp3",
        artist="Artist",
        title="Title",
        genre="House",
        detected_genre="House",
        bpm=120.0,
        camelotCode="8A",
        energy=50,
        duration=300
    )

def test_score_harmonic_loose(engine, dummy_track):
    """Test _score_harmonic with LOOSE stability."""
    class MockContext:
        def get_camelot_stability(self):
            return "LOOSE"

    context = MockContext()
    score = engine._score_harmonic(dummy_track, dummy_track, context)
    assert score == 1.0

def test_score_harmonic_tight_penalty(engine, dummy_track):
    """Test _score_harmonic with TIGHT stability and camelot distance > 3."""
    class MockContext:
        def get_camelot_stability(self):
            return "TIGHT"

    context = MockContext()

    # Track with camelot code 4A (distance 4 from 8A)
    dist_track = Track(
        filePath="/dist", fileName="dist.mp3",
        camelotCode="4A",
        bpm=120, energy=50
    )
    score = engine._score_harmonic(dummy_track, dist_track, context)
    # distance = 4. base = 1 - 4/6 = 0.333...
    # tight bonus base *= 1.2 -> 0.4
    # penalty > 3 -> base *= 0.6 -> 0.24
    assert abs(score - 0.24) < 0.01

def test_score_harmonic_medium_penalty(engine, dummy_track):
    """Test _score_harmonic with MEDIUM stability and camelot distance > 4."""
    class MockContext:
        def get_camelot_stability(self):
            return "MEDIUM"

    context = MockContext()

    # Track with camelot code 3A (distance 5 from 8A)
    dist_track = Track(
        filePath="/dist", fileName="dist.mp3",
        camelotCode="3A",
        bpm=120, energy=50
    )
    score = engine._score_harmonic(dummy_track, dist_track, context)
    # distance = 5. base = 1 - 5/6 = 0.166...
    # penalty > 4 -> base *= 0.8 -> 0.133...
    assert abs(score - 0.133) < 0.01

def test_score_bpm_rising_build_up_small_diff(engine, dummy_track):
    class MockContext:
        def get_energy_trend(self): return "RISING"
        def get_playlist_phase(self): return "BUILD_UP"
        def get_bpm_trend(self): return "STABLE"

    context = MockContext()
    cand = Track(filePath="", fileName="", bpm=121.0, energy=50, camelotCode="8A")
    score = engine._score_bpm(dummy_track, cand, context)
    # bpm_diff = 1. base = 1 - 1/100 = 0.99
    # diff < 2 -> base *= 0.9 = 0.891
    assert abs(score - 0.891) < 0.01

def test_score_bpm_falling_outro_small_diff(engine, dummy_track):
    class MockContext:
        def get_energy_trend(self): return "FALLING"
        def get_playlist_phase(self): return "OUTRO"
        def get_bpm_trend(self): return "STABLE"

    context = MockContext()
    cand = Track(filePath="", fileName="", bpm=110.0, energy=50, camelotCode="8A")
    score = engine._score_bpm(dummy_track, cand, context)
    # diff = 10. base = 1 - 10/100 = 0.9
    # diff < 15 -> base *= 1.2 = 1.08 -> clamped 1.0
    assert score == 1.0

def test_score_bpm_stable_large_diff(engine, dummy_track):
    class MockContext:
        def get_energy_trend(self): return "STABLE"
        def get_playlist_phase(self): return "PEAK"
        def get_bpm_trend(self): return "STABLE"

    context = MockContext()
    cand = Track(filePath="", fileName="", bpm=150.0, energy=50, camelotCode="8A")
    score = engine._score_bpm(dummy_track, cand, context)
    # diff = 30. base = 1 - 30/100 = 0.7
    # diff > 20 -> base *= 0.8 = 0.56
    assert abs(score - 0.56) < 0.01

def test_score_energy_phases(engine, dummy_track):
    class MockContext:
        def __init__(self, phase):
            self.phase = phase
        def get_playlist_phase(self):
            return self.phase

    cand = Track(filePath="", fileName="", bpm=120, energy=50, camelotCode="8A")

    # INTRO target = 30
    score_intro = engine._score_energy(cand, MockContext("INTRO"))
    # diff = 20 -> 1 - 0.2 = 0.8
    assert score_intro == 0.8

    # BUILD_UP target = 60
    score_buildup = engine._score_energy(cand, MockContext("BUILD_UP"))
    # diff = 10 -> 1 - 0.1 = 0.9
    assert score_buildup == 0.9

    # OUTRO target = 40
    score_outro = engine._score_energy(cand, MockContext("OUTRO"))
    # diff = 10 -> 0.9
    assert score_outro == 0.9

    # FALLBACK target = 50
    score_fallback = engine._score_energy(cand, MockContext("UNDEFINED"))
    # diff = 0 -> 1.0
    assert score_fallback == 1.0

def test_score_genre_streak_edge_cases(engine, dummy_track):
    cand_diff = Track(filePath="", fileName="", genre="Techno", detected_genre="Techno", bpm=120, energy=50, camelotCode="8A")
    cand_same = Track(filePath="", fileName="", genre="House", detected_genre="House", bpm=120, energy=50, camelotCode="8A")
    cand_missing_detected = Track(filePath="", fileName="", genre="House", detected_genre="", bpm=120, energy=50, camelotCode="8A")

    class MockContext:
        def __init__(self, streak):
            self.streak = streak
        def get_genre_streak(self):
            return self.streak

    # missing detected genre falls back to genre
    assert engine._score_genre(dummy_track, cand_missing_detected, MockContext(3)) == 1.0

    # streak < 4
    assert engine._score_genre(dummy_track, cand_same, MockContext(3)) == 1.0
    assert engine._score_genre(dummy_track, cand_diff, MockContext(3)) == 0.5

    # streak in [4, 5]
    assert engine._score_genre(dummy_track, cand_same, MockContext(4)) == 0.8
    assert engine._score_genre(dummy_track, cand_diff, MockContext(5)) == 0.7

    # streak > 5
    assert engine._score_genre(dummy_track, cand_same, MockContext(6)) == 0.3
    assert engine._score_genre(dummy_track, cand_diff, MockContext(6)) == 0.9

def test_score_structure_combinations(engine):
    t_perfect_out = Track(filePath="", fileName="", mix_out_point=200, bpm=120, energy=50, camelotCode="8A")
    t_perfect_in = Track(filePath="", fileName="", mix_in_point=5, bpm=120, energy=50, camelotCode="8A")

    t_bad_out = Track(filePath="", fileName="", mix_out_point=100, bpm=120, energy=50, camelotCode="8A")
    t_bad_in = Track(filePath="", fileName="", mix_in_point=30, bpm=120, energy=50, camelotCode="8A")

    # Both OK
    assert engine._score_structure(t_perfect_out, t_perfect_in) == 0.95
    # One OK (out)
    assert engine._score_structure(t_perfect_out, t_bad_in) == 0.70
    # One OK (in)
    assert engine._score_structure(t_bad_out, t_perfect_in) == 0.70
    # Both Bad
    assert engine._score_structure(t_bad_out, t_bad_in) == 0.40

def test_deprecated_bonuses_penalties(engine, dummy_track):
    context = PlaylistContext([], 10)
    # Test they don't crash
    engine._calculate_bonuses(dummy_track, dummy_track, context, "HARMONIC_FLOW")
    engine._calculate_penalties(dummy_track, dummy_track, context)

def test_camelot_distance_edge_cases(engine):
    # None or empty
    assert engine._camelot_distance(None, "8A") == 999
    assert engine._camelot_distance("", "8A") == 999

    # Invalid formats
    assert engine._camelot_distance("INVALID", "8A") == 999
    assert engine._camelot_distance("8A", "INVALID") == 999

    # Mock TypeError or ValueError using a broken object for regex match
    class BrokenString(str):
        def __str__(self):
            return "8A"
        def __getattr__(self, name):
            raise TypeError("Expected string or bytes-like object")

    # The exception block in _camelot_distance handles ValueError, AttributeError, TypeError
    # Actually, the quickest way to hit it is passing an object that fails in re.match
    # like an int instead of string
    assert engine._camelot_distance(8, "8A") == 999

def test_score_bpm_rising_build_up_large_diff(engine, dummy_track):
    class MockContext:
        def get_energy_trend(self): return "RISING"
        def get_playlist_phase(self): return "BUILD_UP"
        def get_bpm_trend(self): return "STABLE"

    context = MockContext()
    cand = Track(filePath="", fileName="", bpm=130.0, energy=50, camelotCode="8A")
    score = engine._score_bpm(dummy_track, cand, context)
    # diff = 10. base = 1 - 0.1 = 0.9
    # diff > 5 -> base *= 1.3 = 1.17 -> clamped 1.0
    assert score == 1.0

def test_score_bpm_accelerating(engine, dummy_track):
    class MockContext:
        def get_energy_trend(self): return "STABLE"
        def get_playlist_phase(self): return "STABLE"
        def get_bpm_trend(self): return "ACCELERATING"

    context = MockContext()
    cand = Track(filePath="", fileName="", bpm=125.0, energy=50, camelotCode="8A")
    score = engine._score_bpm(dummy_track, cand, context)
    # diff = 5. base = 0.95
    # cand.bpm > current.bpm -> 0.95 * 1.15 = 1.0925 -> 1.0
    assert score == 1.0

def test_score_bpm_decelerating(engine, dummy_track):
    class MockContext:
        def get_energy_trend(self): return "STABLE"
        def get_playlist_phase(self): return "STABLE"
        def get_bpm_trend(self): return "DECELERATING"

    context = MockContext()
    cand = Track(filePath="", fileName="", bpm=115.0, energy=50, camelotCode="8A")
    score = engine._score_bpm(dummy_track, cand, context)
    # diff = 5. base = 0.95
    # cand.bpm < current.bpm -> 0.95 * 1.15 = 1.0925 -> 1.0
    assert score == 1.0

from unittest.mock import patch, MagicMock

def test_calculate_score_integration(engine, dummy_track):
    """Test public calculate_score method, integrating the various mocked components."""
    class FullMockContext:
        def get_camelot_stability(self): return "MEDIUM"
        def get_energy_trend(self): return "STABLE"
        def get_playlist_phase(self): return "PEAK"
        def get_bpm_trend(self): return "STABLE"
        def get_genre_streak(self): return 3

    context = FullMockContext()

    cand = Track(
        filePath="/cand",
        fileName="cand.mp3",
        artist="Artist",
        title="Title",
        genre="House",
        detected_genre="House",
        bpm=120.0,
        camelotCode="8A",
        energy=85,  # Target for peak
        mix_out_point=200,
        mix_in_point=5,
        duration=300
    )

    dummy_track.mix_out_point = 200
    dummy_track.mix_in_point = 5

    # Mock dynamic weight calculator
    with patch.object(engine.weight_calculator, 'calculate_weights') as mock_weights:
        mock_weights.return_value = {
            'harmonic': 0.2,
            'bpm': 0.2,
            'energy': 0.2,
            'genre': 0.2,
            'structure': 0.2
        }

        # Mock the external Bonus and Penalty calculators
        with patch('hpg_core.scoring_engine.EnhancedBonusCalculator.calculate_all_bonuses') as mock_bonus:
            mock_bonus.return_value = 0.1
            with patch('hpg_core.scoring_engine.EnhancedPenaltyCalculator.calculate_all_penalties') as mock_penalty:
                mock_penalty.return_value = -0.05

                final_score = engine.calculate_score(
                    dummy_track, cand, context, strategy="PEAK_TIME"
                )

                # Check base scores
                # harmonic (camelot 8A vs 8A) -> dist 0 -> base 1.0 (since MEDIUM stability and dist < 4) -> 1.0
                # bpm (120 vs 120) -> diff 0 -> base 1.0 -> 1.0
                # energy (target 85, cand 85) -> diff 0 -> base 1.0 -> 1.0
                # genre (House vs House, streak 3) -> same_genre = True, streak < 4 -> 1.0
                # structure (fade_out > 180, fade_in < 10) -> 0.95

                # Weighted score = (1.0 * 0.2) + (1.0 * 0.2) + (1.0 * 0.2) + (1.0 * 0.2) + (0.95 * 0.2)
                # = 0.2 + 0.2 + 0.2 + 0.2 + 0.19 = 0.99

                # Final = 0.99 + 0.1 (bonus) - 0.05 (penalty) = 1.04
                # Clamped to 1.0

                assert final_score == 1.0

                # verify calls
                mock_weights.assert_called_once_with(context, "PEAK_TIME")
                mock_bonus.assert_called_once_with(dummy_track, cand, context, "PEAK_TIME")
                mock_penalty.assert_called_once_with(dummy_track, cand, context)

def test_calculate_score_clamps_to_zero(engine, dummy_track):
    """Test that final score is correctly clamped to 0.0 if penalties are huge."""
    class FullMockContext:
        def get_camelot_stability(self): return "LOOSE"
        def get_energy_trend(self): return "UNDEFINED"
        def get_playlist_phase(self): return "UNDEFINED"
        def get_bpm_trend(self): return "UNDEFINED"
        def get_genre_streak(self): return 0
    context = FullMockContext()

    cand = Track(filePath="/cand", fileName="cand.mp3", bpm=120, energy=50, camelotCode="8A")

    with patch.object(engine.weight_calculator, 'calculate_weights') as mock_weights:
        mock_weights.return_value = {
            'harmonic': 0.2, 'bpm': 0.2, 'energy': 0.2, 'genre': 0.2, 'structure': 0.2
        }
        with patch('hpg_core.scoring_engine.EnhancedBonusCalculator.calculate_all_bonuses', return_value=0.0):
            with patch('hpg_core.scoring_engine.EnhancedPenaltyCalculator.calculate_all_penalties', return_value=-5.0):
                final_score = engine.calculate_score(dummy_track, cand, context)
                assert final_score == 0.0
