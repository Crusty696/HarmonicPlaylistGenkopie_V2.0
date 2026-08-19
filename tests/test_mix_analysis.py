"""Tests fuer die Mix-Analyse (Uebergangserkennung und Statistik)."""
import numpy as np
import pytest

from hpg_core.mix_analysis import find_transitions


def _zwei_abschnitte(sr=22050, dauer_je=60.0):
    """Baut ein Signal aus zwei klar verschiedenen Klanghaelften."""
    n = int(dauer_je * sr)
    t = np.arange(n) / sr
    a = (0.5 * np.sin(2 * np.pi * 80 * t)).astype(np.float32)
    b = (0.5 * np.sin(2 * np.pi * 2000 * t)).astype(np.float32)
    return np.concatenate([a, b]), sr


def test_find_transitions_findet_den_wechsel_in_der_mitte():
    y, sr = _zwei_abschnitte()
    stellen = find_transitions(y, sr, min_abstand_s=20.0)
    assert len(stellen) >= 1
    assert any(abs(s - 60.0) < 8.0 for s in stellen)


def test_find_transitions_haelt_mindestabstand_ein():
    y, sr = _zwei_abschnitte()
    stellen = find_transitions(y, sr, min_abstand_s=20.0)
    for erste, zweite in zip(stellen, stellen[1:]):
        assert zweite - erste >= 20.0


def test_find_transitions_homogenes_signal_findet_nichts():
    sr = 22050
    t = np.arange(int(120 * sr)) / sr
    y = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    stellen = find_transitions(y, sr, min_abstand_s=20.0)
    assert stellen == []


def test_find_transitions_zu_kurzes_signal_gibt_leer():
    assert find_transitions(np.zeros(1000, dtype=np.float32), 22050) == []
