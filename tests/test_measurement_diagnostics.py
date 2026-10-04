"""Diagnosevertrag mit RAM-Signalen; keine Originalmusik oder Datenbanken."""

import json
from dataclasses import FrozenInstanceError, asdict
from unittest.mock import Mock

import numpy as np
import pytest

from hpg_core import downbeat


def _controlled_estimator(monkeypatch):
  # Kontrollierte DSP-Ausgaben machen den ausgefuehrten Zweig eindeutig.
  tracker = Mock(return_value=(120.0, np.arange(32)))
  onset = Mock(return_value=np.arange(34, dtype=float))
  chroma = Mock(return_value=np.ones((12, 34)))
  fold = Mock(return_value=(0.1, 0.8))
  monkeypatch.setattr(downbeat.librosa.beat, "beat_track", tracker)
  monkeypatch.setattr(downbeat.librosa, "frames_to_time", lambda frames, **kw: frames * 0.5)
  monkeypatch.setattr(downbeat.librosa.onset, "onset_strength", onset)
  monkeypatch.setattr(downbeat.librosa.feature, "chroma_stft", chroma)
  monkeypatch.setattr(downbeat, "_beat_phase_from_fold", fold)
  monkeypatch.setattr(downbeat, "_bar_phase_confidence", lambda votes: 0.8)
  return tracker, onset, chroma, fold


def test_validation_legacy_constructor_defaults():
  result = downbeat.BeatgridValidation("verified", 3, 2.0)
  assert result.reason is None
  assert result.window_diagnostics == ()


def test_grid_diagnostics_immutable_json_and_same_legacy_values(monkeypatch):
  fold = Mock(return_value=(0.0, 0.8))
  monkeypatch.setattr(downbeat, "_beat_phase_from_fold", fold)
  windows = [(offset, np.ones(100)) for offset in (0.0, 30.0, 60.0)]
  legacy = downbeat.validate_beatgrid_windows(windows, 1024, 120.0, anchor=0.0)
  fold.reset_mock()
  result = downbeat.validate_beatgrid_windows(
    windows, 1024, 120.0, anchor=0.0, collect_diagnostics=True,
  )
  assert (result.status, result.windows_checked, result.max_phase_error_ms) == (
    legacy.status, legacy.windows_checked, legacy.max_phase_error_ms,
  )
  assert (result.status, result.windows_checked, result.max_phase_error_ms) == ("verified", 3, 0.0)
  assert result.reason == "verified"
  assert isinstance(result.window_diagnostics, tuple)
  assert len(result.window_diagnostics) == 3
  assert fold.call_count == 3
  first = result.window_diagnostics[0]
  assert first.offset_seconds == 0.0
  assert first.phase_seconds == 0.0
  assert first.fold_lock == 0.8
  assert first.phase_error_ms == 0.0
  assert first.reason == "measured"
  with pytest.raises(FrozenInstanceError):
    first.reason = "changed"
  raw = json.loads(json.dumps(asdict(result), allow_nan=False))
  assert raw["window_diagnostics"][0]["reason"] == "measured"


@pytest.mark.parametrize("case, reason", [
  ("short", "inputshort"), ("few", "fewbeats"),
  ("trim", "fewbeats"), ("tempo", "incommensurate"),
  ("silent", "noactivity"), ("fold", "weakfold"),
  ("vote", "voteweak"), ("error", "estimationerror"), ("ok", "ok"),
])
def test_estimator_records_actual_branch_preserves_tuple(monkeypatch, case, reason):
  tracker, onset, chroma, fold = _controlled_estimator(monkeypatch)
  audio = np.ones(16384)
  if case == "short":
    audio = np.ones(10)
  elif case == "few":
    tracker.return_value = (120.0, np.arange(3))
  elif case == "trim":
    audio[2048:] = 0.0
  elif case == "tempo":
    monkeypatch.setattr(downbeat.librosa, "frames_to_time", lambda frames, **kw: frames * 0.75)
  elif case == "silent":
    audio[:] = 0.0
  elif case == "fold":
    fold.return_value = (None, 0.0)
  elif case == "vote":
    monkeypatch.setattr(downbeat, "_bar_phase_confidence", lambda votes: 0.0)
  elif case == "error":
    tracker.side_effect = ValueError("controlled failure")
  legacy = downbeat.estimate_first_downbeat(audio, 1024, 120.0)
  calls = tuple(mock.call_count for mock in (tracker, onset, chroma, fold))
  for mock in (tracker, onset, chroma, fold):
    mock.reset_mock()
  diagnostics = {}
  result = downbeat.estimate_first_downbeat(audio, 1024, 120.0, diagnostics=diagnostics)
  assert isinstance(result, tuple) and len(result) == 2
  assert result == legacy
  # Gegen die vor der Umsetzung im RAM geladene Quelle gemessene Ergebnisse.
  expected = (1.6, 0.8) if case == "ok" else (1.6, 0.0) if case == "vote" else (0.0, 0.0)
  assert result == expected
  assert diagnostics["reason"] == reason
  assert tuple(mock.call_count for mock in (tracker, onset, chroma, fold)) == calls
  if case == "trim":
    assert diagnostics["stage"] == "trim"
  if case == "few":
    assert diagnostics["stage"] == "beat_tracking"
  if case == "silent":
    assert diagnostics["loud_max"] == 0.0
  if case == "vote":
    # Bestehende Taktphase bleibt erhalten, auch bei null Voting-Konfidenz.
    assert result == (1.6, 0.0)
  json.dumps(diagnostics, allow_nan=False)


@pytest.mark.parametrize("field, value", [
  ("bpm", np.nan), ("bpm", np.inf), ("sr", np.nan),
  ("sr", np.inf), ("sr", 0), ("audio", np.nan), ("audio", np.inf),
])
def test_estimator_invalid_input_rejected_before_dsp(monkeypatch, field, value):
  tracker, *_ = _controlled_estimator(monkeypatch)
  audio, sr, bpm = np.ones(16384), 1024, 120.0
  if field == "audio":
    audio[0] = value
  elif field == "sr":
    sr = value
  else:
    bpm = value
  diagnostics = {}
  assert downbeat.estimate_first_downbeat(audio, sr, bpm, diagnostics=diagnostics) == (0.0, 0.0)
  assert diagnostics["reason"] == "invalidinput"
  assert tracker.call_count == 0


@pytest.mark.parametrize("field, value", [
  ("bpm", np.nan), ("bpm", np.inf), ("sr", np.nan), ("sr", np.inf),
])
def test_grid_invalid_scalar_rejected_before_fold(monkeypatch, field, value):
  fold = Mock(return_value=(0.0, 0.8))
  monkeypatch.setattr(downbeat, "_beat_phase_from_fold", fold)
  kwargs = {"sr": 1024, "bpm": 120.0}
  kwargs[field] = value
  result = downbeat.validate_beatgrid_windows(
    [(0.0, np.ones(100))] * 3, **kwargs, anchor=0.0, collect_diagnostics=True,
  )
  assert result.status == "unverifiable"
  assert result.reason == "invalidinput"
  assert fold.call_count == 0


@pytest.mark.parametrize("field", ["offset", "audio", "phase", "lock"])
def test_invalid_window_not_counted_or_serialized_as_nan(monkeypatch, field):
  audio = np.ones(100)
  offset, phase, lock = 0.0, 0.0, 0.8
  if field == "audio":
    audio[0] = np.nan
  elif field == "offset":
    offset = np.nan
  elif field == "phase":
    phase = np.nan
  else:
    lock = np.nan
  fold = Mock(return_value=(phase, lock))
  monkeypatch.setattr(downbeat, "_beat_phase_from_fold", fold)
  result = downbeat.validate_beatgrid_windows(
    [(offset, audio)] * 3, 1024, 120.0, anchor=0.0, collect_diagnostics=True,
  )
  assert result.status == "unverifiable"
  assert result.windows_checked == 0
  assert all(item.reason == "invalidinput" for item in result.window_diagnostics)
  if field in ("audio", "offset"):
    assert fold.call_count == 0
  json.dumps(asdict(result), allow_nan=False)


def test_estimator_resets_owned_fields_without_erasing_caller_context(monkeypatch):
  _controlled_estimator(monkeypatch)
  diagnostics = {"caller": "main"}
  downbeat.estimate_first_downbeat(np.ones(16384), 1024, 120.0, diagnostics=diagnostics)
  assert diagnostics["phase_seconds"] == 0.1
  diagnostics["error_type"] = "stale"
  downbeat.estimate_first_downbeat(np.ones(10), 1024, 120.0, diagnostics=diagnostics)
  assert diagnostics == {
    "caller": "main", "reason": "inputshort", "stage": "input",
    "beats_detected": 0, "beats_used": 0, "grid_ibi_seconds": None,
    "bar_confidence": None, "fold_lock": None, "phase_seconds": None,
    "loud_max": None, "error_type": None,
  }


@pytest.mark.parametrize("lock", [0.0, 0.05, 0.1])
def test_estimator_does_not_add_fold_lock_gate(monkeypatch, lock):
  _, _, _, fold = _controlled_estimator(monkeypatch)
  fold.return_value = (0.1, lock)
  audio = np.ones(16384)
  diagnostics = {}
  result = downbeat.estimate_first_downbeat(audio, 1024, 120.0, diagnostics=diagnostics)
  assert result == (1.6, lock)
  assert diagnostics["reason"] == "ok"
  assert diagnostics["phase_seconds"] == 0.1


@pytest.mark.parametrize("field", ["frames", "times", "onset", "chroma", "vote", "phase", "lock"])
def test_estimator_nonfinite_dsp_values_rejected(monkeypatch, field):
  tracker, onset, chroma, fold = _controlled_estimator(monkeypatch)
  if field == "frames":
    tracker.return_value = (120.0, np.full(32, np.nan))
  elif field == "times":
    monkeypatch.setattr(downbeat.librosa, "frames_to_time", lambda *a, **kw: np.full(32, np.inf))
  elif field == "onset":
    onset.return_value[0] = np.nan
  elif field == "chroma":
    chroma.return_value[0, 0] = np.inf
  elif field == "vote":
    monkeypatch.setattr(downbeat, "_bar_phase_confidence", lambda votes: np.nan)
  elif field == "phase":
    fold.return_value = (np.nan, 0.8)
  else:
    fold.return_value = (0.1, np.inf)
  diagnostics = {}
  assert downbeat.estimate_first_downbeat(np.ones(16384), 1024, 120.0, diagnostics=diagnostics) == (0.0, 0.0)
  assert diagnostics["reason"] == "invalidinput"
  json.dumps(diagnostics, allow_nan=False)


def test_grid_rejected_window_kept_but_not_counted(monkeypatch):
  fold = Mock(side_effect=[(0.0, 0.8), (None, 0.0), (0.0, 0.8)])
  monkeypatch.setattr(downbeat, "_beat_phase_from_fold", fold)
  result = downbeat.validate_beatgrid_windows(
    [(offset, np.ones(100)) for offset in (0.0, 30.0, 60.0)],
    1024, 120.0, anchor=0.0, collect_diagnostics=True,
  )
  assert result.status == "unverifiable"
  assert result.reason == "fewwindows"
  assert result.windows_checked == 2
  assert [item.reason for item in result.window_diagnostics] == ["measured", "weakfold", "measured"]
  assert result.window_diagnostics[1].phase_seconds is None
  assert result.window_diagnostics[1].phase_error_ms is None
  assert fold.call_count == 3


@pytest.mark.parametrize("lock, checked", [(0.099, 0), (0.1, 3)])
def test_validator_preserves_existing_fold_lock_gate(monkeypatch, lock, checked):
  fold = Mock(return_value=(0.0, lock))
  monkeypatch.setattr(downbeat, "_beat_phase_from_fold", fold)
  windows = [(offset, np.ones(100)) for offset in (0.0, 30.0, 60.0)]
  result = downbeat.validate_beatgrid_windows(
    windows, 1024, 120.0, anchor=0.0, collect_diagnostics=True,
  )
  assert result.windows_checked == checked
  expected = ("verified", 3, 0.0) if checked else ("unverifiable", 0, -1.0)
  assert (result.status, result.windows_checked, result.max_phase_error_ms) == expected


@pytest.mark.parametrize("error", [0.006, 0.006 + 1.0 / 1024])
def test_validator_preserves_phase_error_boundary(monkeypatch, error):
  fold = Mock(return_value=(error, 0.8))
  monkeypatch.setattr(downbeat, "_beat_phase_from_fold", fold)
  windows = [(offset, np.ones(100)) for offset in (0.0, 30.0, 60.0)]
  result = downbeat.validate_beatgrid_windows(
    windows, 1024, 120.0, anchor=0.0, collect_diagnostics=True,
  )
  expected_status = "verified" if error == 0.006 else "mismatch"
  assert (result.status, result.windows_checked, result.max_phase_error_ms) == (
    expected_status, 3, round(error * 1000.0, 3),
  )
  assert result.reason == ("verified" if error == 0.006 else "phasemismatch")


@pytest.mark.parametrize("ticks, anchor, reason, status", [
  ([0.0, 0.0, 0.0], None, "duplicategrid", "unsupported"),
  ([0.0, 0.5, 1.1], None, "variablegrid", "unsupported"),
  ([0.0, 0.75, 1.5], None, "tempomismatch", "mismatch"),
  ([], None, "missingreference", "unverifiable"),
])
def test_grid_early_reasons_skip_dsp(monkeypatch, ticks, anchor, reason, status):
  fold = Mock(return_value=(0.0, 0.8))
  monkeypatch.setattr(downbeat, "_beat_phase_from_fold", fold)
  windows = [(0.0, np.ones(100))] * 3
  result = downbeat.validate_beatgrid_windows(
    windows, 1024, 120.0, anchor=anchor, grid_times=ticks, collect_diagnostics=True,
  )
  assert result.status == status
  assert result.max_phase_error_ms == -1.0
  assert result.reason == reason
  assert result.windows_checked == 0
  assert fold.call_count == 0


def test_window_phase_is_local_to_offset(monkeypatch):
  fold = Mock(return_value=(0.37, 0.8))
  monkeypatch.setattr(downbeat, "_beat_phase_from_fold", fold)
  result = downbeat.validate_beatgrid_windows(
    [(offset, np.ones(100)) for offset in (0.13, 30.13, 60.13)],
    1024, 120.0, anchor=0.0, collect_diagnostics=True,
  )
  assert result.status == "verified"
  assert result.window_diagnostics[0].offset_seconds == 0.13
  assert result.window_diagnostics[0].phase_seconds == 0.37
  assert result.window_diagnostics[0].duration_seconds == 100 / 1024
  assert result.window_diagnostics[0].phase_error_ms == pytest.approx(0.0)


def test_window_fold_exception_is_explicit_and_missing_values_none(monkeypatch):
  fold = Mock(side_effect=ValueError("controlled failure"))
  monkeypatch.setattr(downbeat, "_beat_phase_from_fold", fold)
  result = downbeat.validate_beatgrid_windows(
    [(0.0, np.ones(100))], 1024, 120.0, anchor=0.0, collect_diagnostics=True,
  )
  assert result.windows_checked == 0
  item = result.window_diagnostics[0]
  assert item.reason == "estimationerror"
  assert item.phase_seconds is None and item.fold_lock is None
  assert item.phase_error_ms is None
