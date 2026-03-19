import pytest
from hpg_core.scoring_context import PlaylistContext
from hpg_core.scoring_weights import DynamicWeightCalculator
from hpg_core.models import Track

class MockTrack:
    def __init__(self, energy=50, bpm=120, detected_genre="House", genre="House", camelotCode="8A"):
        self.energy = energy
        self.bpm = bpm
        self.detected_genre = detected_genre
        self.genre = genre
        self.camelotCode = camelotCode

class TestDynamicWeightCalculator:
    def setup_method(self):
        self.calculator = DynamicWeightCalculator()

    def test_base_weights(self):
        # Create an empty context to avoid triggering phase/trend adjustments
        context = PlaylistContext([], total_tracks=10)
        # Mock get_playlist_phase to return UNDEFINED to avoid phase adjustments
        context.get_playlist_phase = lambda: "UNDEFINED"
        weights = self.calculator.calculate_weights(context, strategy="HARMONIC_FLOW")

        assert weights['harmonic'] == 0.30
        assert weights['bpm'] == 0.25
        assert weights['energy'] == 0.25
        assert weights['genre'] == 0.15
        assert weights['structure'] == 0.05
        assert abs(sum(weights.values()) - 1.0) < 1e-6

    def test_phase_adjustments(self):
        # INTRO phase
        context = PlaylistContext([], total_tracks=10)
        context.get_playlist_phase = lambda: "INTRO"
        weights = self.calculator.calculate_weights(context, strategy="DEFAULT")
        assert weights['harmonic'] > 0.45
        assert abs(sum(weights.values()) - 1.0) < 1e-6

        # BUILD_UP phase
        context.get_playlist_phase = lambda: "BUILD_UP"
        weights = self.calculator.calculate_weights(context, strategy="DEFAULT")
        assert weights['energy'] > 0.35

        # PEAK phase
        context.get_playlist_phase = lambda: "PEAK"
        weights = self.calculator.calculate_weights(context, strategy="DEFAULT")
        assert weights['energy'] > 0.30
        assert weights['bpm'] > 0.25

        # OUTRO phase
        context.get_playlist_phase = lambda: "OUTRO"
        weights = self.calculator.calculate_weights(context, strategy="DEFAULT")
        assert weights['harmonic'] > 0.30

    def test_trend_adjustments(self):
        context = PlaylistContext([], total_tracks=10)
        context.get_playlist_phase = lambda: "PEAK" # Use a stable phase

        # RISING energy
        context.get_energy_trend = lambda: "RISING"
        context.get_bpm_trend = lambda: "STABLE"
        weights = self.calculator.calculate_weights(context, strategy="DEFAULT")
        # Energy weight should be boosted
        assert weights['energy'] > 0.35

        # Reset and test FALLING energy
        context.get_energy_trend = lambda: "FALLING"
        weights = self.calculator.calculate_weights(context, strategy="DEFAULT")
        # Energy and harmonic weights boosted
        assert weights['energy'] > 0.35
        assert weights['harmonic'] > 0.20

        # Reset and test ACCELERATING bpm
        context.get_energy_trend = lambda: "STABLE"
        context.get_bpm_trend = lambda: "ACCELERATING"
        weights = self.calculator.calculate_weights(context, strategy="DEFAULT")
        # BPM weight boosted
        assert weights['bpm'] > 0.30

    def test_genre_streak_fatigue(self):
        context = PlaylistContext([], total_tracks=10)
        context.get_playlist_phase = lambda: "PEAK"
        context.get_energy_trend = lambda: "STABLE"
        context.get_bpm_trend = lambda: "STABLE"
        context.get_genre_streak = lambda: 6 # > 5 triggers fatigue

        weights = self.calculator.calculate_weights(context, strategy="DEFAULT")
        # Genre weight should be reduced, energy boosted
        assert weights['genre'] < 0.10
        assert weights['energy'] > 0.35

    @pytest.mark.parametrize("strategy, dominant_weight", [
        ("PEAK_TIME", "energy"),
        ("GENRE_FLOW", "genre"),
        ("ENERGY_WAVE", "energy"),
        ("EMOTIONAL_JOURNEY", "harmonic"),
        ("HARMONIC_CONSISTENT", "harmonic"),
        ("BPM_PROGRESSION", "bpm"),
        ("SMOOTH_CROSSFADE", "bpm"),
    ])
    def test_strategy_adjustments(self, strategy, dominant_weight):
        context = PlaylistContext([], total_tracks=10)
        context.get_playlist_phase = lambda: "UNDEFINED"
        context.get_energy_trend = lambda: "STABLE"
        context.get_bpm_trend = lambda: "STABLE"
        context.get_genre_streak = lambda: 0

        weights = self.calculator.calculate_weights(context, strategy=strategy)

        # The dominant weight for the strategy should be the highest or near highest
        max_weight = max(weights.values())
        assert weights[dominant_weight] >= max_weight * 0.9
        assert abs(sum(weights.values()) - 1.0) < 1e-6

    def test_normalization_fallback(self):
        # Test the fallback when weights somehow sum to 0 or less
        context = PlaylistContext([], total_tracks=10)
        context.get_playlist_phase = lambda: "UNDEFINED"

        weights = self.calculator.calculate_weights(context, strategy="UNKNOWN_STRATEGY")
        assert abs(sum(weights.values()) - 1.0) < 1e-6
