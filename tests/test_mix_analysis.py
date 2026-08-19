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


from hpg_core.mix_analysis import TransitionSample, deltas_between, window_bounds


def test_window_bounds_spart_blendzone_aus():
    vor, nach = window_bounds(600.0, dauer=1200.0)
    assert vor[1] <= 600.0 - 20.0
    assert nach[0] >= 600.0 + 20.0
    assert vor[1] - vor[0] == pytest.approx(30.0)
    assert nach[1] - nach[0] == pytest.approx(30.0)


def test_window_bounds_am_rand_gibt_none():
    assert window_bounds(5.0, dauer=1200.0) is None
    assert window_bounds(1195.0, dauer=1200.0) is None


def test_deltas_between_identische_seiten_sind_null():
    gerade = [0.0] * 16
    for s in (0, 4, 8, 12):
        gerade[s] = 0.25
    a = TransitionSample(groove_pattern=gerade, bass_pattern=gerade,
                         sub_energy=0.3, bass_punch=3.0, brightness=50.0,
                         timbre=[1.0, 2.0, 3.0])
    d = deltas_between(a, a)
    assert d["groove_sim"] == pytest.approx(1.0)
    assert d["sub_delta"] == pytest.approx(0.0)
    assert d["brightness_delta"] == pytest.approx(0.0)
    assert d["timbre_sim"] == pytest.approx(1.0)


def test_deltas_between_offbeat_gegen_gerade_ist_unaehnlich():
    gerade = [0.0] * 16
    offbeat = [0.0] * 16
    for s in (0, 4, 8, 12):
        gerade[s] = 0.25
    for s in (2, 6, 10, 14):
        offbeat[s] = 0.25
    a = TransitionSample(groove_pattern=gerade, bass_pattern=gerade,
                         sub_energy=0.3, bass_punch=3.0, brightness=50.0,
                         timbre=[1.0, 0.0])
    b = TransitionSample(groove_pattern=offbeat, bass_pattern=offbeat,
                         sub_energy=0.3, bass_punch=3.0, brightness=50.0,
                         timbre=[0.0, 1.0])
    d = deltas_between(a, b)
    assert d["groove_sim"] < 0.2
    assert d["timbre_sim"] < 0.2


from hpg_core.mix_analysis import (
    discrimination_auc, holdout_passed, learn_weights, tolerance_percentile,
)


def test_discrimination_auc_perfekte_trennung_ist_eins():
    assert discrimination_auc([0.9, 0.95, 0.92], [0.1, 0.2, 0.15], True) == pytest.approx(1.0)


def test_discrimination_auc_keine_trennung_ist_halb():
    werte = [0.5, 0.5, 0.5]
    assert discrimination_auc(werte, werte, True) == pytest.approx(0.5)


def test_discrimination_auc_umgekehrte_richtung():
    # Bei Abstaenden ist NIEDRIGER besser.
    assert discrimination_auc([0.1, 0.15], [0.8, 0.9], False) == pytest.approx(1.0)


def test_tolerance_percentile_nimmt_90er():
    assert tolerance_percentile(list(range(101)), 90.0) == pytest.approx(90.0, abs=1.0)


def test_tolerance_percentile_leer_gibt_none():
    assert tolerance_percentile([], 90.0) is None


def test_learn_weights_summiert_auf_dreissig_prozent():
    auc = {"groove": 1.0, "bass": 0.5, "timbre": 0.5, "mood": 0.5}
    gewichte = learn_weights(auc, gesamt=0.30)
    assert sum(gewichte.values()) == pytest.approx(0.30)
    assert gewichte["groove"] > gewichte["bass"]
    assert all(w >= 0.0 for w in gewichte.values())


def test_learn_weights_ohne_trennschaerfe_verteilt_gleich():
    auc = {"groove": 0.5, "bass": 0.5, "timbre": 0.5, "mood": 0.5}
    gewichte = learn_weights(auc, gesamt=0.30)
    for wert in gewichte.values():
        assert wert == pytest.approx(0.075)


def test_holdout_passed_bei_klarer_trennung():
    assert holdout_passed([0.8, 0.85, 0.9], [0.3, 0.35, 0.4]) is True


def test_holdout_failed_ohne_trennung():
    assert holdout_passed([0.5, 0.5], [0.5, 0.5]) is False


def test_holdout_failed_bei_umgekehrter_ordnung():
    assert holdout_passed([0.2, 0.25], [0.8, 0.9]) is False
