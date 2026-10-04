"""Expliziter Diagnosevertrag; keine Rekonstruktion fehlender Messursachen."""
from copy import deepcopy
from dataclasses import asdict
import math


DOWNBEAT_FIELDS = frozenset({
    "reason", "stage", "beats_detected", "beats_used", "grid_ibi_seconds",
    "bar_confidence", "fold_lock", "phase_seconds", "loud_max", "error_type",
})
DOWNBEAT_REASONS = frozenset({
    "unknown", "reference_verified", "invalidinput", "inputshort", "fewbeats",
    "incommensurate", "noactivity", "weakfold", "voteweak", "estimationerror", "ok",
})
STAGES = frozenset({"input", "beat_tracking", "features", "trim", "voting", "fold", "result", "reference"})
GRID_REASONS = frozenset({
    "unknown", "invalidinput", "nowindows", "duplicategrid", "variablegrid",
    "tempomismatch", "missingreference", "fewwindows", "verified", "phasemismatch",
})
WINDOW_REASONS = frozenset({"measured", "weakfold", "invalidinput", "estimationerror"})
WINDOW_FIELDS = frozenset({
    "offset_seconds", "duration_seconds", "phase_seconds", "fold_lock", "phase_error_ms", "reason",
})
GRID_FIELDS = frozenset({
    "status", "windows_checked", "max_phase_error_ms", "reason", "window_diagnostics", "decode_failures",
})


def _error():
    raise ValueError("measurement_diagnostics verletzt den Diagnosevertrag")


def _number(value, *, minimum=0.0, maximum=None, nullable=True):
    if value is None and nullable:
        return
    if type(value) not in (int, float) or not math.isfinite(value) or value < minimum:
        _error()
    if maximum is not None and value > maximum:
        _error()


def _count(value):
    if type(value) is not int or value < 0:
        _error()


def validate_measurement_diagnostics(value):
    """Gespeicherte Fremdschluessel ablehnen; {} bleibt ausdruecklich unbekannt."""
    if type(value) is not dict:
        _error()
    if not value:
        return
    if set(value) != {"version", "downbeat", "grid"} or type(value["version"]) is not int or value["version"] != 1:
        _error()
    downbeat, grid = value["downbeat"], value["grid"]
    if (type(downbeat) is not dict or not {"reason", "stage"}.issubset(downbeat)
            or set(downbeat) - DOWNBEAT_FIELDS):
        _error()
    if type(downbeat["reason"]) is not str or downbeat["reason"] not in DOWNBEAT_REASONS:
        _error()
    stage = downbeat["stage"]
    if stage is not None and (type(stage) is not str or stage not in STAGES):
        _error()
    for name in ("beats_detected", "beats_used"):
        if name in downbeat:
            _count(downbeat[name])
    for name in ("grid_ibi_seconds", "phase_seconds", "loud_max"):
        if name in downbeat:
            _number(downbeat[name])
    for name in ("bar_confidence", "fold_lock"):
        if name in downbeat:
            _number(downbeat[name], maximum=1.0)
    error = downbeat.get("error_type")
    if error is not None and (type(error) is not str or not error.isidentifier() or len(error) > 100):
        _error()
    if type(grid) is not dict or set(grid) != GRID_FIELDS:
        _error()
    if type(grid["status"]) is not str or grid["status"] not in {"unknown", "unverifiable", "unsupported", "mismatch", "verified"}:
        _error()
    if type(grid["reason"]) is not str or grid["reason"] not in GRID_REASONS:
        _error()
    _count(grid["windows_checked"])
    _number(grid["max_phase_error_ms"], minimum=-1.0, nullable=False)
    if grid["max_phase_error_ms"] < 0 and grid["max_phase_error_ms"] != -1.0:
        _error()
    windows = grid["window_diagnostics"]
    failures = grid["decode_failures"]
    if type(windows) is not list or type(failures) is not list or len(windows) + len(failures) > 100:
        _error()
    for window in windows:
        if type(window) is not dict or set(window) != WINDOW_FIELDS:
            _error()
        if type(window["reason"]) is not str or window["reason"] not in WINDOW_REASONS:
            _error()
        for name in WINDOW_FIELDS - {"reason", "fold_lock"}:
            _number(window[name])
        _number(window["fold_lock"], maximum=1.0)
        if window["reason"] == "measured" and any(window[k] is None for k in WINDOW_FIELDS - {"reason"}):
            _error()
    for failure in failures:
        if type(failure) is not dict or set(failure) != {"offset_seconds", "reason"} or failure["reason"] != "decode_error":
            _error()
        _number(failure["offset_seconds"], nullable=False)


def measurement_snapshot(downbeat, grid, *, decode_failures=()):
    """Nur bekannte Producer-Felder projizieren; Legacy-Mocks liefern unbekannt."""
    measured = {key: deepcopy(value) for key, value in downbeat.items() if key in DOWNBEAT_FIELDS}
    measured.setdefault("reason", "unknown")
    measured.setdefault("stage", None)
    grid_data = asdict(grid)
    grid_data["reason"] = grid_data.get("reason") or "unknown"
    grid_data["window_diagnostics"] = list(grid_data.get("window_diagnostics", ()))
    grid_data["decode_failures"] = deepcopy(list(decode_failures))
    result = {"version": 1, "downbeat": measured, "grid": grid_data}
    validate_measurement_diagnostics(result)
    return result
