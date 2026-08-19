"""Tests fuer die beat-synchrone Mustererkennung."""
import numpy as np
import pytest

from hpg_core.groove import BAR_SLOTS, fold_to_bar


def _envelope_with_peaks(peak_times, duration, sr_frames=100.0):
    """Baut eine Huellkurve mit Spitzen an den gegebenen Sekunden."""
    n = int(duration * sr_frames)
    env = np.zeros(n, dtype=float)
    times = np.arange(n) / sr_frames
    for t in peak_times:
        idx = int(round(t * sr_frames))
        if 0 <= idx < n:
            env[idx] = 1.0
    return env, times


def test_fold_to_bar_viertel_landen_auf_slot_0_4_8_12():
    # 120 BPM -> 0.5 s pro Beat, 2.0 s pro Takt. Zwei Takte, Viertel auf jeder Zaehlzeit.
    peaks = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]
    env, times = _envelope_with_peaks(peaks, duration=4.0)

    pattern = fold_to_bar(env, times, bpm=120.0, first_downbeat=0.0)

    assert len(pattern) == BAR_SLOTS
    belegt = [i for i, v in enumerate(pattern) if v > 0.0]
    assert belegt == [0, 4, 8, 12]
    assert pytest.approx(sum(pattern), abs=1e-9) == 1.0


def test_fold_to_bar_offbeat_landet_auf_slot_2_6_10_14():
    # Offbeat-Achtel: 0.25 s nach jeder Zaehlzeit bei 120 BPM.
    peaks = [0.25, 0.75, 1.25, 1.75]
    env, times = _envelope_with_peaks(peaks, duration=2.0)

    pattern = fold_to_bar(env, times, bpm=120.0, first_downbeat=0.0)

    belegt = [i for i, v in enumerate(pattern) if v > 0.0]
    assert belegt == [2, 6, 10, 14]


def test_fold_to_bar_beruecksichtigt_downbeat_versatz():
    # Gleiche Viertel, aber das Raster beginnt erst bei 0.3 s.
    peaks = [0.3, 0.8, 1.3, 1.8]
    env, times = _envelope_with_peaks(peaks, duration=2.5)

    pattern = fold_to_bar(env, times, bpm=120.0, first_downbeat=0.3)

    belegt = [i for i, v in enumerate(pattern) if v > 0.0]
    assert belegt == [0, 4, 8, 12]


def test_fold_to_bar_leere_huellkurve_gibt_leere_liste():
    assert fold_to_bar(np.array([]), np.array([]), bpm=120.0, first_downbeat=0.0) == []


def test_fold_to_bar_ungueltige_bpm_gibt_leere_liste():
    env, times = _envelope_with_peaks([0.0], duration=1.0)
    assert fold_to_bar(env, times, bpm=0.0, first_downbeat=0.0) == []
