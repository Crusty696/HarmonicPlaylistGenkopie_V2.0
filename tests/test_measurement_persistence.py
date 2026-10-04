"""Diagnosen bleiben gebunden, endlich und getrennt von unbekannten Altdaten."""
from copy import deepcopy

import pytest

from hpg_core import caching
from hpg_core.models import Track


def _track():
    return Track(filePath="C:/synthetic/source.aiff", fileName="source.aiff",
                 duration=300.0, bpm=128.0, analysis_mode="librosa_full_or_tail")


def _diagnosis():
    return {
        "version": 1,
        "downbeat": {"reason": "fewbeats", "stage": "trim"},
        "grid": {"status": "unverifiable", "windows_checked": 0,
                 "max_phase_error_ms": -1.0, "reason": "fewwindows",
                 "window_diagnostics": [], "decode_failures": []},
    }


def test_unknown_default_is_not_a_fabricated_failure():
    track = _track()
    assert track.measurement_diagnostics == {}
    restored = caching.dict_to_track(caching.track_to_dict(track))
    assert restored.measurement_diagnostics == {}


def test_diagnostic_snapshot_is_deeply_detached_and_roundtrips():
    track = _track()
    track.measurement_diagnostics = _diagnosis()
    data = caching.track_to_dict(track)
    restored = caching.dict_to_track(data)
    expected = deepcopy(restored.measurement_diagnostics)
    track.measurement_diagnostics["downbeat"]["reason"] = "unknown"
    assert data["measurement_diagnostics"] == expected
    assert restored.measurement_diagnostics == expected
    data["measurement_diagnostics"]["downbeat"]["reason"] = "unknown"
    assert restored.measurement_diagnostics == expected


@pytest.mark.parametrize("bad", [None, [], {"version": True}, {"version": 999},
                                  {"downbeat": {"reason": "guessed"}}])
def test_invalid_diagnostic_schema_is_not_silently_accepted(bad):
    data = caching.track_to_dict(_track())
    data["measurement_diagnostics"] = bad
    with pytest.raises(caching.CacheValidationError, match="measurement_diagnostics"):
        caching.validate_track_dict(data)


def test_nonfinite_diagnostic_measurements_are_rejected():
    data = caching.track_to_dict(_track())
    diagnosis = _diagnosis()
    diagnosis["grid"]["max_phase_error_ms"] = float("nan")
    data["measurement_diagnostics"] = diagnosis
    with pytest.raises(caching.CacheValidationError, match="measurement_diagnostics"):
        caching.validate_track_dict(data)


def test_snapshot_projects_producer_context_but_stored_extras_are_rejected():
    from hpg_core.downbeat import BeatgridValidation
    from hpg_core.measurement_contract import measurement_snapshot
    grid = BeatgridValidation("unverifiable", 0, -1.0, "fewwindows")
    snapshot = measurement_snapshot({"reason": "estimationerror", "stage": None,
                                     "caller": "must not persist"}, grid)
    assert "caller" not in snapshot["downbeat"]
    snapshot["downbeat"]["caller"] = "untrusted stored key"
    data = caching.track_to_dict(_track())
    data["measurement_diagnostics"] = snapshot
    with pytest.raises(caching.CacheValidationError, match="measurement_diagnostics"):
        caching.validate_track_dict(data)


def test_actual_decode_failure_is_separate_from_measured_windows(monkeypatch):
    import numpy as np
    from hpg_core import analysis, downbeat
    calls = []

    def load(path, **kwargs):
        calls.append(kwargs["offset"])
        raise OSError("sensitive diagnostic text must not persist")

    monkeypatch.setattr(analysis.librosa, "load", load)
    monkeypatch.setattr(downbeat, "_beat_phase_from_fold", lambda *args: (0.0, 0.8))
    diagnostics = {}
    result = analysis._validate_track_beatgrid(
        "not opened source.aiff", 300.0, 120.0, 0.0,
        head_audio=np.ones(22050), head_sr=22050, diagnostics=diagnostics,
    )
    assert result.windows_checked == 1
    assert len(result.window_diagnostics) == 1
    assert diagnostics == {"decode_failures": [
        {"offset_seconds": offset, "reason": "decode_error"} for offset in calls
    ]}
    assert len(calls) == 2
