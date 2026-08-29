import pytest
import numpy as np

from hpg_core.analysis import generate_timbre_fingerprint
from tests.fixtures.audio_generators import (
    generate_tone,
    generate_silence,
    generate_noise,
    DEFAULT_SR,
)

@pytest.mark.unit
class TestGenerateTimbreFingerprint:
    """Tests for generate_timbre_fingerprint()."""

    def test_returns_list(self):
        """Returns a list."""
        y = generate_tone(440.0, 3.0, DEFAULT_SR)
        result = generate_timbre_fingerprint(y, DEFAULT_SR)
        assert isinstance(result, list)

    def test_correct_length(self):
        """Standard: 13 MFCCs."""
        y = generate_tone(440.0, 3.0, DEFAULT_SR)
        result = generate_timbre_fingerprint(y, DEFAULT_SR)
        assert len(result) == 13, f"MFCC length {len(result)}, expected 13"

    def test_none_input_returns_empty(self):
        """None Input = empty list."""
        assert generate_timbre_fingerprint(None, 22050) == []

    def test_empty_array_returns_empty(self):
        """Empty Array = empty list."""
        assert generate_timbre_fingerprint(np.array([]), 22050) == []

    def test_values_are_float(self):
        """All values are floats."""
        y = generate_tone(440.0, 3.0, DEFAULT_SR)
        result = generate_timbre_fingerprint(y, DEFAULT_SR)
        for val in result:
            assert isinstance(val, float), f"Value {val} is {type(val)}, expected float"

    def test_values_are_finite(self):
        """All values are finite (no NaN/Inf)."""
        y = generate_tone(440.0, 3.0, DEFAULT_SR)
        result = generate_timbre_fingerprint(y, DEFAULT_SR)
        for val in result:
            assert np.isfinite(val), f"MFCC value {val} is not finite"

    def test_different_signals_different_fingerprints(self):
        """Different signals have different fingerprints."""
        tone = generate_tone(440.0, 3.0, DEFAULT_SR)
        noise = generate_noise(3.0, DEFAULT_SR)
        fp_tone = generate_timbre_fingerprint(tone, DEFAULT_SR)
        fp_noise = generate_timbre_fingerprint(noise, DEFAULT_SR)
        assert fp_tone != fp_noise, "Tone and noise should have different fingerprints"

    def test_same_signal_same_fingerprint(self):
        """Same signal = same fingerprint."""
        y = generate_tone(440.0, 3.0, DEFAULT_SR)
        fp1 = generate_timbre_fingerprint(y, DEFAULT_SR)
        fp2 = generate_timbre_fingerprint(y, DEFAULT_SR)
        assert fp1 == fp2

    def test_silence_returns_valid_fingerprint(self):
        """Silence returns valid fingerprint."""
        y = generate_silence(3.0, DEFAULT_SR)
        result = generate_timbre_fingerprint(y, DEFAULT_SR)
        assert isinstance(result, list)
        if len(result) > 0:
            assert len(result) == 13

    def test_nan_values_handled(self):
        """NaN values are handled safely."""
        y = np.full(DEFAULT_SR * 3, np.nan, dtype=np.float32)
        result = generate_timbre_fingerprint(y, DEFAULT_SR)
        assert isinstance(result, list)

    def test_rounded_to_3_decimals(self):
        """Values are rounded to 3 decimal places."""
        y = generate_noise(3.0, DEFAULT_SR)
        result = generate_timbre_fingerprint(y, DEFAULT_SR)
        for val in result:
            assert round(val, 3) == val, f"Value {val} has more than 3 decimal places"
