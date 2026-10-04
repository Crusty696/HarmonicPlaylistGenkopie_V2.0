"""RAM-/Qt-Diagnoseanzeige ohne Quelldateien oder Analyse."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import Qt

from hpg_core.measurement_panel import MeasurementDialog

pytestmark = pytest.mark.gui


def diagnosis(lock=0.0, phase_error=0.0):
    return {"version": 1, "downbeat": {"reason": "fewbeats", "stage": "trim"},
            "grid": {"status": "unverifiable", "windows_checked": 0,
                     "max_phase_error_ms": -1.0, "reason": "fewwindows",
                     "window_diagnostics": [{"offset_seconds": 0.0,
                         "duration_seconds": 30.0, "phase_seconds": None,
                         "fold_lock": lock, "phase_error_ms": phase_error,
                         "reason": "weakfold"}],
                     "decode_failures": [{"offset_seconds": 120.0, "reason": "decode_error"}]}}


def track(data=None, name="RAM-Track"):
    return SimpleNamespace(fileName=name, filePath="Z:/NEVER_OPEN/source.aiff",
                           measurement_diagnostics={} if data is None else data)


def make(qtbot, tracks):
    dialog = MeasurementDialog(tracks)
    qtbot.addWidget(dialog)
    return dialog


def cell(table, row, column):
    return table.model().index(row, column).data()


def test_empty_input_is_explicit(qtbot):
    dialog = make(qtbot, ())
    assert dialog.track_table.model().rowCount() == 0
    assert "Keine analysierten Tracks" in dialog.status_label.text()
    assert dialog.window_table.rowCount() == 0


def test_missing_attributes_and_unknown_are_not_fabricated(qtbot):
    dialog = make(qtbot, (SimpleNamespace(), track()))
    assert "unbekannt" in cell(dialog.track_table, 0, 2).lower()
    assert "möglicherweise alte Analyse" in cell(dialog.track_table, 1, 2)
    assert "Unbekannt" in dialog.detail_label.text()


@pytest.mark.parametrize("bad", [{"secret": "PRIVATE-PAYLOAD"}, None,
                                  {"version": True}, {"version": 999}])
def test_invalid_diagnostics_have_no_payload_or_error_leak(qtbot, bad):
    source = track()
    source.measurement_diagnostics = bad
    before = deepcopy(source.__dict__)
    dialog = make(qtbot, (source,))
    assert cell(dialog.track_table, 0, 2) == "Unverifiziert – ungültige Diagnose"
    assert "PRIVATE-PAYLOAD" not in dialog.detail_label.text()
    assert dialog.window_table.rowCount() == 0
    assert source.__dict__ == before


def test_snapshot_does_not_follow_source_mutation(qtbot):
    source = track(diagnosis())
    before = deepcopy(source.__dict__)
    dialog = make(qtbot, (source,))
    assert source.__dict__ == before
    source.fileName = "CHANGED"
    source.measurement_diagnostics["grid"]["window_diagnostics"][0]["fold_lock"] = 0.9
    assert cell(dialog.track_table, 0, 0) == "RAM-Track"
    assert cell(dialog.window_table, 0, 3) == "0.000"


def test_zero_missing_sentinel_and_decode_offsets_are_distinct(qtbot):
    dialog = make(qtbot, (track(diagnosis()), track(diagnosis(None, None))))
    assert cell(dialog.track_table, 0, 4) == "Nicht gemessen"
    assert cell(dialog.window_table, 0, 2) == "Nicht gemessen"
    assert cell(dialog.window_table, 0, 3) == "0.000"
    assert cell(dialog.window_table, 0, 4) == "0.000"
    assert "120.000 s" in dialog.decode_label.text()
    assert "Zu wenige Beats" in dialog.detail_label.text()
    assert "Beschneiden" in dialog.detail_label.text()
    dialog.track_table.selectRow(1)
    assert cell(dialog.window_table, 0, 3) == "Nicht gemessen"
    assert cell(dialog.window_table, 0, 4) == "Nicht gemessen"
    assert dialog.window_table.item(0, 5).toolTip()
    assert dialog.track_table.model().index(0, 2).data(Qt.ItemDataRole.ToolTipRole)


def test_all_2500_tracks_but_only_selected_window_details(qtbot):
    data = diagnosis()
    data["grid"]["decode_failures"] = []
    data["grid"]["window_diagnostics"] = [
        dict(data["grid"]["window_diagnostics"][0], offset_seconds=float(i))
        for i in range(100)]
    sources = tuple(track(deepcopy(data), f"Track {i}") for i in range(2500))
    dialog = make(qtbot, sources)
    assert dialog.track_table.model().rowCount() == 2500
    assert dialog.window_table.rowCount() == 100
    dialog.track_table.selectRow(2499)
    assert cell(dialog.track_table, 2499, 0) == "Track 2499"
    assert dialog.window_table.rowCount() == 100
    assert cell(dialog.window_table, 99, 0) == "99.000"
    assert "2500" in dialog.status_label.text()


def test_central_validator_is_used_for_each_snapshot(qtbot, monkeypatch):
    from hpg_core import measurement_panel
    actual = measurement_panel.validate_measurement_diagnostics
    calls = []

    def validate(data):
        calls.append(data)
        return actual(data)

    monkeypatch.setattr(measurement_panel, "validate_measurement_diagnostics", validate)
    sources = (track(), track(diagnosis()))
    dialog = make(qtbot, sources)
    assert len(calls) == 2
    assert calls[1] is not sources[1].measurement_diagnostics
    dialog.track_table.clearSelection()
    assert dialog.window_table.rowCount() == 0
    assert dialog.detail_label.text() == "Keine Trackauswahl."


def test_dialog_never_opens_or_stats_track_sources(qtbot, monkeypatch):
    import builtins
    import os
    from pathlib import Path
    source = track(diagnosis())

    def forbidden(*args, **kwargs):
        raise AssertionError("Keine Dateioperation erlaubt")

    with monkeypatch.context() as guarded:
        guarded.setattr(builtins, "open", forbidden)
        guarded.setattr(os, "stat", forbidden)
        guarded.setattr(Path, "open", forbidden)
        dialog = MeasurementDialog((source,))
        dialog.track_table.selectRow(0)
        dialog.reject()
    qtbot.addWidget(dialog)
