"""Tempo-Retry darf nur nach unabhaengiger strenger Audiopruefung gelten."""

from unittest.mock import Mock

import numpy as np
import pytest

from hpg_core import analysis
from hpg_core.downbeat import BeatgridValidation


def _prepare(monkeypatch, reason="incommensurate", confidence=0.75, status="verified"):
    calls = []

    def estimate(y, sr, bpm, *, diagnostics, **kwargs):
        calls.append(kwargs)
        diagnostics.update(reason="ok" if kwargs.get("_fixed_bpm") else reason, stage="result")
        return (0.125, confidence) if kwargs.get("_fixed_bpm") else (0.0, 0.0)

    monkeypatch.setattr(analysis, "estimate_first_downbeat", estimate)
    validator = Mock(return_value=BeatgridValidation(status, 3, 2.0))
    monkeypatch.setattr(analysis, "_validate_track_beatgrid", validator)
    return calls, validator


def _run(diagnostics):
    return analysis._estimate_audio_downbeat(
        np.ones(32000), 1000, 140.0, file_path="original.mp3",
        duration=320.0, diagnostics=diagnostics,
    )


def test_fremde_metrik_wird_nur_mit_geprueftem_audioanker_ersetzt(monkeypatch):
    calls, validator = _prepare(monkeypatch)
    diagnostics = {}
    assert _run(diagnostics) == (0.125, 0.75)
    assert calls == [{"_allow_metric_retry": False}, {"_fixed_bpm": True, "_allow_metric_retry": False}]
    assert validator.call_args.args == ("original.mp3", 320.0, 140.0, 0.125)
    assert validator.call_args.kwargs["head_sr"] == 1000
    assert diagnostics == {"reason": "ok", "stage": "result"}


@pytest.mark.parametrize("status", ["mismatch", "unverifiable", "unsupported"])
def test_unbestaetigter_retry_behaelt_urspruengliche_ablehnung(monkeypatch, status):
    _prepare(monkeypatch, status=status)
    diagnostics = {}
    assert _run(diagnostics) == (0.0, 0.0)
    assert diagnostics == {"reason": "incommensurate", "stage": "result"}


@pytest.mark.parametrize("confidence", [0.0, 0.299])
def test_schwaches_voting_wird_nicht_durch_gutes_grid_aufgewertet(monkeypatch, confidence):
    calls, validator = _prepare(monkeypatch, confidence=confidence)
    assert _run({}) == (0.0, 0.0)
    assert len(calls) == 2
    validator.assert_not_called()


@pytest.mark.parametrize("reason", ["ok", "voteweak", "weakfold", "fewbeats", "estimationerror"])
def test_andere_zweige_erhalten_keinen_tempo_retry(monkeypatch, reason):
    calls, validator = _prepare(monkeypatch, reason=reason)
    assert _run({}) == (0.0, 0.0)
    assert calls == [{"_allow_metric_retry": False}]
    validator.assert_not_called()


@pytest.mark.parametrize("target_bpm,accepted", [(128.0, True), (85.33, False)])
def test_echte_synthetische_audiofenster_trennen_retry_von_falschem_tempo(
    monkeypatch, target_bpm, accepted,
):
    from tests.test_downbeat import SR, _make_four_on_floor

    audio = _make_four_on_floor(128.0, 60.0, 0.3)
    original_tracker = analysis.librosa.beat.beat_track

    def tracker(*args, **kwargs):
        # Kontrolliert den urspruenglichen Fehlentscheid; der Retry und
        # alle drei Faltungsfenster rechnen danach auf echtem Testsignal.
        if accepted and "bpm" not in kwargs:
            kwargs["bpm"] = 85.33
        return original_tracker(*args, **kwargs)

    def load(_path, *, offset, duration, **kwargs):
        return audio[int(offset * SR):int((offset + duration) * SR)], SR

    monkeypatch.setattr(analysis.librosa.beat, "beat_track", tracker)
    monkeypatch.setattr(analysis.librosa, "load", load)
    diagnostics = {}
    result = analysis._estimate_audio_downbeat(
        audio, SR, target_bpm, file_path="only-ram-synthetic.wav",
        duration=60.0, diagnostics=diagnostics,
    )
    if accepted:
        assert result[1] >= 0.30
        assert result[0] == pytest.approx(0.3, abs=0.006)
        assert diagnostics["reason"] == "ok"
    else:
        assert result == (0.0, 0.0)
        assert diagnostics["reason"] == "incommensurate"


@pytest.mark.parametrize("fast_path", [False, True])
@pytest.mark.parametrize("reference_grid", [False, True])
def test_retry_erreicht_beide_pfade_und_bewahrt_referenzdiagnose(
    monkeypatch, tmp_path, fast_path, reference_grid,
):
    from tests.test_analyze_track import _create_click_wav
    from hpg_core.rekordbox_importer import RekordboxTrackData

    wav = tmp_path / "synthetic-retry.wav"
    _create_click_wav(str(wav), bpm=128.0, duration=32.0)
    importer = Mock()
    importer.get_track_data.return_value = RekordboxTrackData(
        bpm=128.0 if fast_path else None, duration=32.0, camelot_code="8A",
    )
    importer.get_track_signature.return_value = "synthetic-signature"
    importer.get_beatgrid.return_value = ([
        {"beat": i % 4 + 1, "time": i * 60.0 / 128.0} for i in range(60)
    ] if reference_grid else [])
    importer.get_phrases.return_value = []
    importer.get_cue_points.return_value = []
    monkeypatch.setattr(analysis, "get_rekordbox_importer", lambda: importer)
    monkeypatch.setattr(analysis, "get_cached_track", lambda *a, **k: None)
    monkeypatch.setattr(analysis, "cache_track", Mock(return_value=True))
    monkeypatch.setattr(analysis, "_collect_beat_windows", lambda *a: [])
    calls, validator = _prepare(monkeypatch)
    validator.side_effect = lambda *a, **k: BeatgridValidation(
        "mismatch" if k.get("grid_points") else "verified", 3,
        35.0 if k.get("grid_points") else 2.0,
        phase_pattern="variable_phase" if k.get("grid_points") else "aligned",
    )

    track = analysis.analyze_track(str(wav))

    assert track is not None
    assert track.first_downbeat == 0.125
    assert track.downbeat_confidence == 0.75
    assert calls == [{"_allow_metric_retry": False}, {"_fixed_bpm": True, "_allow_metric_retry": False}]
    assert track.beatgrid_source == "audio"
    assert track.beatgrid_status == "verified"
    if reference_grid:
        assert track.measurement_diagnostics["anchor"]["reference"]["measurement"]["grid"]["status"] == "mismatch"
    assert track.measurement_diagnostics["downbeat"]["reason"] == "ok"
