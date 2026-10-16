"""Merkmalsraster korrigieren, ohne Beatidentitaet oder Fehlerprioritaet zu verlieren."""

from unittest.mock import Mock

import numpy as np
import pytest

from hpg_core import downbeat as d
from tests.test_downbeat import SR, _make_four_on_floor


def test_verspaeteter_tracker_erhaelt_bekannte_takteins(monkeypatch):
    audio = _make_four_on_floor(128.0, 60.0, 0.3)
    times = np.arange(0.3, 59.5, 60.0 / 128.0)
    frames = np.rint((times + 0.120) * SR / d.HOP_LENGTH).astype(int)
    monkeypatch.setattr(d.librosa.beat, "beat_track", lambda **kwargs: (128.0, frames))
    diagnostics = {}

    anchor, confidence = d.estimate_first_downbeat(
        audio, SR, 128.0, diagnostics=diagnostics, _allow_metric_retry=False,
    )

    assert confidence >= d.DOWNBEAT_RELIABLE_MIN
    # Bekannte musikalische Eins, nicht bloss die gleiche Phase modulo Beat.
    assert anchor == pytest.approx(0.3, abs=d.EXACT_BEAT_SYNC_TOLERANCE_SECONDS)
    assert diagnostics["reason"] == "ok"


@pytest.mark.parametrize("numbers", [np.arange(5), np.array([0, 1, 3, 4])])
def test_gemeinsamer_offset_erhaelt_luecken_und_identitaet(numbers):
    times = 1.12 + numbers * 0.5
    aligned, actual_numbers, keep = d._align_beat_feature_grid(times, numbers, 0.0, 0.5, 5.0)
    np.testing.assert_allclose(aligned, 1.0 + numbers * 0.5)
    np.testing.assert_array_equal(actual_numbers, numbers)
    np.testing.assert_array_equal(keep, np.ones(len(numbers), dtype=bool))


def test_randpunkte_werden_gemeinsam_entfernt_ohne_clipping():
    times = np.arange(5) * 0.5
    aligned, numbers, keep = d._align_beat_feature_grid(times, np.arange(5), 0.4, 0.5, 1.9)
    np.testing.assert_allclose(aligned, [0.4, 0.9, 1.4])
    np.testing.assert_array_equal(numbers, [1, 2, 3])
    np.testing.assert_array_equal(keep, [False, True, True, True, False])


def test_interner_wandernder_lag_erhaelt_nummern_aber_keine_externe_freigabe():
    numbers = np.arange(64)
    times = 1.12 + numbers * .5 + .2 * np.sin(np.linspace(0, 4*np.pi, 64))
    assert d._align_beat_feature_grid(times, numbers, 0., .5, 35.) is None
    aligned, retained, keep = d._align_beat_feature_grid(times, numbers, 0., .5, 35., True)
    np.testing.assert_array_equal(retained, numbers)
    np.testing.assert_allclose(aligned, 1. + numbers * .5)
    assert np.all(keep)


def test_interner_lag_mit_ganzem_beat_drift_bleibt_gesperrt():
    numbers = np.arange(64)
    times = 1.12 + numbers * .5 + np.linspace(0., .6, 64)
    assert d._align_beat_feature_grid(times, numbers, 0., .5, 35., True) is None


@pytest.mark.parametrize("times,numbers,phase,ibi,duration", [
    ([0.01, 0.6, 1.3, 1.9], [0, 1, 2, 3], 0.0, 0.5, 3.0),
    ([], [], 0.0, 0.5, 3.0),
    ([0.1, 0.6], [0], 0.0, 0.5, 3.0),
    ([0.6, 0.1], [0, 1], 0.0, 0.5, 3.0),
    ([0.1, 0.6], [0, 0], 0.0, 0.5, 3.0),
    ([0.1, np.nan], [0, 1], 0.0, 0.5, 3.0),
    ([0.1, 0.6], [0, 1], np.inf, 0.5, 3.0),
    ([0.1, 0.6], [0, 1], 0.0, 0.0, 3.0),
    ([0.1, 0.6], [0, 1], 0.0, 0.5, np.nan),
])
def test_ungueltige_oder_widerspruechliche_zuordnung_bleibt_offen(times, numbers, phase, ibi, duration):
    assert d._align_beat_feature_grid(times, numbers, phase, ibi, duration) is None


@pytest.fixture
def controlled(monkeypatch):
    # Nur Kontrollfluss: reale Audio-Qualitaet prueft der separate DSP-Test oben.
    audio = np.ones(20 * SR, dtype=np.float32)
    frames = np.rint((0.12 + np.arange(36) * 0.5) * SR / d.HOP_LENGTH).astype(int)
    monkeypatch.setattr(d.librosa.beat, "beat_track", lambda **kwargs: (120.0, frames))
    monkeypatch.setattr(d.librosa.onset, "onset_strength", lambda **kwargs: np.ones(1000))
    monkeypatch.setattr(d.librosa.feature, "chroma_stft", lambda **kwargs: np.ones((12, 1000)))
    return audio


def _run(audio):
    diagnostics = {}
    result = d.estimate_first_downbeat(audio, SR, 120.0, diagnostics=diagnostics, _allow_metric_retry=False)
    return result, diagnostics


@pytest.mark.parametrize("case,reason,stage,error", [
    ("active", "estimationerror", "fold", "RuntimeError"),
    ("unpack", "estimationerror", "fold", "ValueError"),
    ("silent", "noactivity", "trim", None),
    ("sparse", "fewbeats", "trim", None),
    ("feature", "estimationerror", "features", "ValueError"),
])
def test_frueher_fold_bewahrt_diagnoseprioritaet(monkeypatch, controlled, case, reason, stage, error):
    fold = Mock(return_value=(0.0,)) if case == "unpack" else Mock(side_effect=RuntimeError("Fold-Testfehler"))
    monkeypatch.setattr(d, "_beat_phase_from_fold", fold)
    audio = controlled.copy()
    if case == "silent":
        audio[:] = 0
    elif case == "sparse":
        audio[int(2.5 * SR):] = 0
    elif case == "feature":
        monkeypatch.setattr(d.librosa.onset, "onset_strength", Mock(side_effect=ValueError("Feature-Testfehler")))
    result, diagnostics = _run(audio)
    assert result == (0.0, 0.0)
    assert (diagnostics["reason"], diagnostics["stage"], diagnostics["error_type"]) == (reason, stage, error)
    assert fold.call_count == 1


@pytest.mark.parametrize("phase,lock", [
    (0.0, 0.099), (None, 0.0), (np.nan, 0.9), (np.inf, 0.9),
    (0.0, np.nan), (0.0, np.inf),
])
def test_ungeeigneter_fold_aendert_keine_featurezeiten(monkeypatch, controlled, phase, lock):
    helper = Mock(side_effect=AssertionError("Ungeeigneter Fold darf kein Raster ersetzen"))
    converter = Mock(wraps=d.librosa.time_to_frames)
    fold = Mock(return_value=(phase, lock))
    monkeypatch.setattr(d, "_align_beat_feature_grid", helper)
    monkeypatch.setattr(d, "_beat_phase_from_fold", fold)
    monkeypatch.setattr(d.librosa, "time_to_frames", converter)
    _, diagnostics = _run(controlled)
    helper.assert_not_called()
    converter.assert_not_called()
    assert diagnostics["reason"] != "fold_alignment"
    assert fold.call_count == 1


@pytest.mark.parametrize("case", ["none", "few", "missing_class"])
def test_unvollstaendiges_neues_raster_verwirft_taktanker(monkeypatch, controlled, case):
    monkeypatch.setattr(d, "_beat_phase_from_fold", lambda *_args: (0.0, 0.9))
    # Seit Cache99 darf ein fehlendes internes Raster nur mit separat
    # bestaetigtem Audio-Raster ersetzt werden. Hier fehlt diese Bestaetigung.
    monkeypatch.setattr(d, "validate_beatgrid_windows",
                        lambda *a, **kw: d.BeatgridValidation("mismatch", 3, 20.0))
    monkeypatch.setattr(d, "_align_beat_feature_grid", lambda *_args: None)
    numbers = np.arange(15) if case == "few" else np.arange(20) * 4
    candidate = None if case == "none" else (numbers * 0.5, numbers, np.ones(len(numbers), dtype=bool))
    helper = Mock(return_value=candidate)
    converter = Mock(wraps=d.librosa.time_to_frames)
    monkeypatch.setattr(d, "_align_beat_feature_grid", helper)
    monkeypatch.setattr(d.librosa, "time_to_frames", converter)
    result, diagnostics = _run(controlled)
    assert result == (0.0, 0.0)
    assert diagnostics["reason"] == "fold_alignment"
    assert diagnostics["stage"] == "fold"
    assert helper.call_count == 1
    converter.assert_not_called()


def test_gueltiges_raster_erneuert_frames_und_verwendet_fold_nur_einmal(monkeypatch, controlled):
    fold = Mock(return_value=(0.0, 0.9))
    converter = Mock(wraps=d.librosa.time_to_frames)
    monkeypatch.setattr(d, "_beat_phase_from_fold", fold)
    monkeypatch.setattr(d.librosa, "time_to_frames", converter)
    _run(controlled)
    assert fold.call_count == 1
    assert converter.call_count == 1
    np.testing.assert_allclose(converter.call_args.args[0], np.arange(36) * 0.5)
