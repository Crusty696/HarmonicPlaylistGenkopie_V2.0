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


def anchor_diagnosis(*, method="dsp", confidence=0.8, grid_status="verified", windows=()):
    data = diagnosis()
    data["version"] = 2
    data["grid"].update(status=grid_status, reason="phasemismatch" if grid_status == "mismatch" else grid_status)
    neural_reason = "reference_preferred" if method == "rekordbox" else "baseline_preferred"
    anchor = {"source": "rekordbox" if method == "rekordbox" else "audio",
              "method": method, "anchor_s": 1.25, "confidence": confidence,
              "reference": None,
              "neural": {"reason": neural_reason, "transient": False,
                         "windows": list(windows), "candidate_anchor_s": None}}
    if method == "rekordbox":
        reference = diagnosis()
        reference["grid"].update(status="verified", reason="verified")
        anchor["reference"] = {"anchor_s": 1.25, "bpm": 120.0,
                               "target_bpm": 120.0, "measurement": reference}
    data["anchor"] = anchor
    return data


def phase_offset_diagnosis():
    data = diagnosis()
    data.update(version=3)
    data["downbeat"] = {"reason": "weakfold", "stage": "fold"}
    data["grid"] = {
        "status": "mismatch", "windows_checked": 3,
        "max_phase_error_ms": 20.0, "reason": "phasemismatch",
        "window_diagnostics": [
            {"offset_seconds": float(start), "duration_seconds": 30.0,
             "phase_seconds": 0.02, "fold_lock": 0.8,
             "phase_error_ms": 20.0, "signed_phase_error_ms": 20.0,
             "reason": "measured"}
            for start in (0, 30, 60)
        ],
        "decode_failures": [], "phase_pattern": "consistent_offset",
        "phase_center_ms": 20.0,
    }
    data["anchor"] = {
        "source": "audio", "method": "dsp", "anchor_s": 0.0,
        "confidence": 0.2, "reference": None,
        "neural": {"reason": "baseline_preferred", "transient": False,
                   "windows": [], "candidate_anchor_s": None},
    }
    return data


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


def test_fold_alignment_reason_is_shown_in_german(qtbot):
    data = diagnosis()
    data["downbeat"] = {"reason": "fold_alignment", "stage": "fold"}
    dialog = make(qtbot, [track(data)])
    tooltip = dialog.track_table.model().index(0, 2).data(Qt.ItemDataRole.ToolTipRole)
    assert "Beat-Raster widerspricht Faltungsphase" in tooltip


def test_fixed_bpm_retry_reason_is_shown_in_details(qtbot):
    data = diagnosis()
    data["downbeat"] = {
        "reason": "incommensurate", "stage": "beat_tracking",
        "retry_reason": "fold_alignment",
    }
    dialog = make(qtbot, [track(data)])
    assert "Retry-Grund: Beat-Raster widerspricht Faltungsphase (fold_alignment)" in dialog.detail_label.text()


def test_schema2_audio_anchor_explains_unverified_musical_bar_one(qtbot):
    dialog = make(qtbot, [track(anchor_diagnosis())])
    detail = dialog.detail_label.text()
    assert "Audio-DSP" in detail
    assert "Konfidenz 0.800" in detail
    assert "Takt 1 ist nicht unabhängig geprüft" in detail
    assert "Phrase-/Mixraster: technisch freigegeben" in detail


def test_schema2_rekordbox_anchor_is_provenance_not_ground_truth(qtbot):
    dialog = make(qtbot, [track(anchor_diagnosis(method="rekordbox", confidence=1.0))])
    detail = dialog.detail_label.text()
    assert "Rekordbox bezeichnet die Herkunft" in detail
    assert "keine unabhängige Ground Truth" in detail


def test_schema4_shows_volume_rebind_as_metadata_match(qtbot):
    data = phase_offset_diagnosis()
    data["version"] = 4
    data["anchor"] = anchor_diagnosis()["anchor"]
    reference = anchor_diagnosis(method="rekordbox", confidence=1.0)["anchor"]["reference"]
    reference["path_match"] = "volume_rebind"
    data["anchor"]["reference"] = reference
    dialog = make(qtbot, [track(data)])
    assert "Laufwerkswechsel, Metadatenabgleich" in dialog.detail_label.text()


@pytest.mark.parametrize("confidence, status", [(0.29, "verified"), (0.8, "mismatch")])
def test_schema2_unbrauchbarer_anchor_gibt_phrase_mixraster_nicht_frei(qtbot, confidence, status):
    dialog = make(qtbot, [track(anchor_diagnosis(confidence=confidence, grid_status=status))])
    assert "Phrase-/Mixraster: nicht freigegeben" in dialog.detail_label.text()


def test_schema1_macht_ankerentscheidung_ausdruecklich_unbekannt(qtbot):
    dialog = make(qtbot, [track(diagnosis())])
    assert "Ankerentscheidung: Nicht verfügbar (ältere Diagnose)" in dialog.detail_label.text()


def test_schema3_zeigt_konstanten_versatz_mit_vorzeichen_und_beweisgrenze(qtbot):
    dialog = make(qtbot, [track(phase_offset_diagnosis())])
    detail = dialog.detail_label.text()
    assert "Konsistenter Beatphasen-Versatz" in detail
    assert "Zentrum Audio minus Grid: 20.000 ms" in detail
    assert "keine unabhängige musikalische Takt-1-Referenz" in detail
    assert cell(dialog.window_table, 0, 5) == "20.000"
    assert "Audio minus Grid" in dialog.window_table.item(0, 5).toolTip()
    assert dialog.window_table.horizontalHeaderItem(5).text() == "Signierter Phasenfehler (Audio minus Grid, ms)"


def test_schema5_zeigt_rekordbox_taktrotation_als_unbestaetigten_modellkandidaten(qtbot):
    data = phase_offset_diagnosis()
    data["version"] = 5
    data["anchor"] = anchor_diagnosis()["anchor"]
    data["anchor"]["bar_position_comparison"] = {
        "status": "candidate_rotation", "reason": "measured",
        "rotation_beats": 1,
        "windows": [
            {"model_id": model, "start_s": start, "status": "measured",
             "matched_beats": 8, "max_time_error_ms": 1.0,
             "rotation_beats": 1, "decoder_positions": [1, 2, 3, 4],
             "rekordbox_positions": [1, 2, 3, 4], "rotation_candidates": [1]}
            for start in (0.0, 16.0, 32.0) for model in ("model7", "model8")
        ],
        "audio_confirmation": {
            "status": "audio_confirmed", "reason": "measured",
            "expected_anchor_s": 0.75, "final_grid_status": "verified",
            "windows": [
                {"model_id": model, "start_s": start, "status": "confirmed",
                 "reason": "measured", "anchor_s": 0.75, "confidence": 0.8,
                 "phase_error_ms": 1.0}
                for start in (0.0, 16.0, 32.0) for model in ("model7", "model8")
            ],
        },
    }

    dialog = make(qtbot, [track(data)])

    assert "Modellkandidat: 1 Beat(s) gegenüber Rekordbox rotiert" in dialog.detail_label.text()
    assert "Zusätzliche DSP-Prüfung in sechs Modellfenstern und Gesamtgridprüfung bestanden" in dialog.detail_label.text()
    assert "Keine unabhängige musikalische Ground Truth" in dialog.detail_label.text()


def test_modellfenster_zeigen_ursache_und_zeit_ohne_freie_fehlertexte(qtbot):
    window = {"model_id": "model7", "start_s": 12.0, "duration_s": 16.0,
              "reason": "tempo_mismatch", "input_status": "ok",
              "input_reason": "private-error-detail", "anchor_s": None,
              "confidence": None, "downbeat": {}}
    dialog = make(qtbot, [track(anchor_diagnosis(windows=(window,)))])
    detail = dialog.detail_label.text()
    assert "Beat-Modell 7" in detail
    assert "Start 12.000 s" in detail
    assert "Dauer 16.000 s" in detail
    assert "Tempoabweichung" in detail
    assert "Eingabe verfügbar" in detail
    assert "private-error-detail" not in detail


def test_missing_attributes_and_unknown_are_not_fabricated(qtbot):
    dialog = make(qtbot, (SimpleNamespace(), track()))
    assert "unbekannt" in cell(dialog.track_table, 0, 2).lower()
    assert "möglicherweise alte Analyse" in cell(dialog.track_table, 1, 3)
    assert "Unbekannt" in dialog.detail_label.text()


@pytest.mark.parametrize("bad", [{"secret": "PRIVATE-PAYLOAD"}, None,
                                  {"version": True}, {"version": 999}])
def test_invalid_diagnostics_have_no_payload_or_error_leak(qtbot, bad):
    source = track()
    source.measurement_diagnostics = bad
    before = deepcopy(source.__dict__)
    dialog = make(qtbot, (source,))
    assert cell(dialog.track_table, 0, 3) == "Unverifiziert – ungültige Diagnose"
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
    assert cell(dialog.track_table, 0, 6) == "Nicht gemessen"
    assert cell(dialog.window_table, 0, 2) == "Nicht gemessen"
    assert cell(dialog.window_table, 0, 3) == "0.000"
    assert cell(dialog.window_table, 0, 4) == "0.000"
    assert "120.000 s" in dialog.decode_label.text()
    assert "Zu wenige Beats" in dialog.detail_label.text()
    assert "Beschneiden" in dialog.detail_label.text()
    dialog.track_table.selectRow(1)
    assert cell(dialog.window_table, 0, 3) == "Nicht gemessen"
    assert cell(dialog.window_table, 0, 4) == "Nicht gemessen"
    assert dialog.window_table.item(0, 6).toolTip()
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
