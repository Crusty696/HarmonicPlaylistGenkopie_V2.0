"""Tempo, Tonhöhe und Stereo-Verhältnis ohne Originaltracks prüfen."""
import numpy as np
import pytest

from hpg_core.preview_stretch import stretch


@pytest.mark.parametrize('rate', [135 / 136, 136 / 138])
def test_stretch_preserves_pitch_and_stereo_at_actual_failed_rates(rate):
    sr = 8000
    time = np.arange(sr * 4) / sr
    mono = np.sin(2 * np.pi * 440 * time).astype(np.float32) * .2
    result = stretch(np.column_stack((mono, mono * .5)), sr, rate)
    assert abs(len(result) - len(mono) / rate) <= 2
    np.testing.assert_allclose(result[:, 1], result[:, 0] * .5, atol=.002)
    spectrum = abs(np.fft.rfft(result[sr:-sr, 0]))
    frequency = np.fft.rfftfreq(len(result[sr:-sr]), 1 / sr)[np.argmax(spectrum)]
    assert abs(frequency - 440) < 2


def test_equal_tempo_keeps_original_samples():
    audio = np.zeros((100, 2), dtype=np.float32)
    assert stretch(audio, 8000, 1.) is audio
