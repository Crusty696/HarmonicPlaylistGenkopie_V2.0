"""
Tests for mix point calculation in hpg_core/analysis.py
"""

import pytest
import numpy as np
from hpg_core.analysis import analyze_structure_and_mix_points


def generate_test_audio(duration_seconds, sr=22050, frequency=440.0):
    """Generate a simple sine wave for testing."""
    samples = int(duration_seconds * sr)
    t = np.linspace(0, duration_seconds, samples, False)
    audio = np.sin(2 * np.pi * frequency * t)
    return audio.astype(np.float32), sr


class TestMixPointCalculation:
    """Test mathematical correctness of mix point calculation."""

    @pytest.mark.slow
    def test_standard_house_track_128bpm(self):
        """Test standard House track (128 BPM, 300 seconds = 5 minutes)."""
        y, sr = generate_test_audio(300.0)
        duration = 300.0
        energy_level = 'medium'
        bpm = 128.0

        mix_in, mix_out, mix_in_bars, mix_out_bars = analyze_structure_and_mix_points(
            y, sr, duration, energy_level, bpm
        )

        assert 15.0 <= mix_in <= 45.0
        assert 210.0 <= mix_out <= 285.0  # 70-95% of track = typical DJ mix-out zone
        assert mix_in_bars % 8 == 0
        assert mix_out_bars % 8 == 0

    @pytest.mark.slow
    def test_phrase_alignment_calculation(self):
        """Test that mix points align to phrase boundaries correctly."""
        y, sr = generate_test_audio(300.0)
        duration = 300.0
        bpm = 128.0

        mix_in, mix_out, mix_in_bars, mix_out_bars = analyze_structure_and_mix_points(
            y, sr, duration, 'medium', bpm
        )

        seconds_per_beat = 60.0 / bpm
        seconds_per_bar = seconds_per_beat * 4
        seconds_per_phrase = seconds_per_bar * 8

        assert _is_phrase_aligned(mix_in, seconds_per_phrase)
        assert _is_phrase_aligned(mix_out, seconds_per_phrase)

    @pytest.mark.slow
    def test_bar_calculation_accuracy(self):
        """Test that bar calculations match time calculations."""
        y, sr = generate_test_audio(300.0)
        duration = 300.0
        bpm = 128.0

        mix_in, mix_out, mix_in_bars, mix_out_bars = analyze_structure_and_mix_points(
            y, sr, duration, 'medium', bpm
        )

        seconds_per_beat = 60.0 / bpm
        seconds_per_bar = seconds_per_beat * 4

        expected_mix_in_bars = mix_in / seconds_per_bar
        expected_mix_out_bars = mix_out / seconds_per_bar

        assert mix_in_bars == pytest.approx(expected_mix_in_bars, abs=0.1)
        assert mix_out_bars == pytest.approx(expected_mix_out_bars, abs=0.1)

    @pytest.mark.slow
    def test_mathematical_basis_128bpm(self):
        """Test the mathematical basis at 128 BPM."""
        bpm = 128.0

        seconds_per_beat = 60.0 / bpm
        seconds_per_bar = seconds_per_beat * 4
        seconds_per_phrase = seconds_per_bar * 8

        assert seconds_per_beat == pytest.approx(0.46875)
        assert seconds_per_bar == pytest.approx(1.875)
        assert seconds_per_phrase == pytest.approx(15.0)


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.slow
    def test_silent_track(self):
        """Test handling of completely silent track."""
        y = np.zeros(22050 * 300, dtype=np.float32)
        sr = 22050

        mix_in, mix_out, mix_in_bars, mix_out_bars = analyze_structure_and_mix_points(
            y, sr, 300.0, 'medium', 128.0
        )

        assert isinstance(mix_in, (int, float))
        assert isinstance(mix_out, (int, float))
        assert mix_in < mix_out
        assert mix_in_bars % 8 == 0
        assert mix_out_bars % 8 == 0

    def test_zero_bpm(self):
        """Test handling of invalid BPM (0)."""
        y, sr = generate_test_audio(300.0)

        with pytest.raises((ValueError, ZeroDivisionError)):
            analyze_structure_and_mix_points(y, sr, 300.0, 'medium', 0.0)


def _is_phrase_aligned(time_seconds: float, seconds_per_phrase: float, tolerance: float = 0.05) -> bool:
    """Pruefe ob ein Zeitpunkt auf einer Phrase-Grenze liegt (Fliesskomma-sicher)."""
    if seconds_per_phrase <= 0:
        return False
    remainder = time_seconds % seconds_per_phrase
    return remainder < tolerance or (seconds_per_phrase - remainder) < tolerance


class TestDifferentTempos:
    """Test mix point calculation at different BPM ranges."""

    @pytest.mark.slow
    def test_dnb_tempo_174bpm(self):
        """Test Drum & Bass tempo (174 BPM)."""
        y, sr = generate_test_audio(300.0)
        bpm = 174.0

        mix_in, mix_out, mix_in_bars, mix_out_bars = analyze_structure_and_mix_points(
            y, sr, 300.0, 'medium', bpm
        )

        seconds_per_phrase = (60.0 / bpm) * 4 * 8

        assert _is_phrase_aligned(mix_in, seconds_per_phrase)
        assert _is_phrase_aligned(mix_out, seconds_per_phrase)
        assert mix_in_bars % 8 == 0
        assert mix_out_bars % 8 == 0

    @pytest.mark.slow
    def test_slow_tempo_80bpm(self):
        """Test slow tempo (80 BPM)."""
        y, sr = generate_test_audio(300.0)
        bpm = 80.0

        mix_in, mix_out, mix_in_bars, mix_out_bars = analyze_structure_and_mix_points(
            y, sr, 300.0, 'medium', bpm
        )

        seconds_per_phrase = (60.0 / bpm) * 4 * 8

        assert _is_phrase_aligned(mix_in, seconds_per_phrase)
        assert _is_phrase_aligned(mix_out, seconds_per_phrase)
        assert mix_in_bars % 8 == 0
        assert mix_out_bars % 8 == 0


class TestReturnTypes:
    """Test return types and value precision."""

    @pytest.mark.slow
    def test_return_types(self):
        """Test that function returns correct types."""
        y, sr = generate_test_audio(300.0)

        result = analyze_structure_and_mix_points(
            y, sr, 300.0, 'medium', 128.0
        )

        assert isinstance(result, tuple)
        assert len(result) == 4

        mix_in, mix_out, mix_in_bars, mix_out_bars = result

        assert isinstance(mix_in, (int, float))
        assert isinstance(mix_out, (int, float))
        assert isinstance(mix_in_bars, (int, float))
        assert isinstance(mix_out_bars, (int, float))
