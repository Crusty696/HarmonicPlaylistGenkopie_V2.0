"""Lautheitsregelung darf kurze Transienten nicht in den Limiter treiben."""
import numpy as np
import pytest

from hpg_core.transition_renderer import _level_mix_loudness


@pytest.mark.parametrize('seconds', [1.0, 6.13])
def test_loudness_preserves_transient_headroom_and_stereo(seconds):
    sr = 8000
    t = np.arange(int(sr * seconds)) / sr
    mono = (0.04 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    for position in (0, len(mono) // 2, len(mono) - 1):
        mono[position] = 0.72
    audio = np.column_stack((mono, mono * 0.5))
    result = _level_mix_loudness(audio, sr, target_db=-14)
    assert np.isfinite(result).all()
    assert np.max(np.abs(result)) <= 0.950001
    np.testing.assert_allclose(result[:, 1], result[:, 0] * 0.5, atol=1e-7)
    # Eine globale Absenkung auf Null waere keine Lautheitsregelung.
    assert np.sqrt(np.mean(result ** 2)) > np.sqrt(np.mean(audio ** 2))
