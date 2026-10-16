"""Feintempo muss vor allen zeitabhaengigen Vollpfad-Verbrauchern gelten."""

from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from hpg_core import analysis
from hpg_core.downbeat import BeatgridValidation


PRECISE = 138.123456789
PRIOR = 136.0


@pytest.mark.parametrize("fast_path", [False, True])
def test_feintempo_erreicht_alle_vollpfad_verbraucher(monkeypatch, tmp_path, fast_path):
    from hpg_core.rekordbox_importer import RekordboxTrackData
    from hpg_core.structure_analyzer import TrackSection, TrackStructure
    from tests.test_analyze_track import _create_click_wav

    path = tmp_path / "tempo-pipeline.wav"
    _create_click_wav(str(path), bpm=PRIOR, duration=32.0)
    importer = Mock()
    importer.get_track_data.return_value = RekordboxTrackData(
        bpm=PRIOR if fast_path else None, duration=32.0, camelot_code="8A",
    )
    importer.get_track_signature.return_value = "isolated-tempo-test"
    importer.get_beatgrid.return_value = []
    importer.get_phrases.return_value = []
    monkeypatch.setattr(analysis, "get_rekordbox_importer", lambda: importer)
    monkeypatch.setattr(analysis, "get_cached_track", lambda *_a, **_k: None)
    monkeypatch.setattr(analysis, "_persist_analysis_result", lambda *_a, **_k: True)
    monkeypatch.setattr(analysis, "extract_bpm_from_tags", lambda *_a: PRIOR)
    monkeypatch.setattr(analysis.librosa.beat, "beat_track", lambda **_k: (PRIOR, np.arange(70) * 19))
    refine = Mock(return_value=PRECISE)
    monkeypatch.setattr(analysis, "_refine_audio_tempo", refine, raising=False)
    seen = {}

    def record(name, index, result):
        def call(*args, **kwargs):
            seen[name] = args[index]
            return result
        return call

    monkeypatch.setattr(analysis, "classify_genre", record("genre", 2, SimpleNamespace(
        genre="Techno", confidence=1.0, source="test", mfcc_fingerprint=[0.0] * 13,
    )))
    monkeypatch.setattr(analysis, "_estimate_audio_downbeat", record("downbeat", 2, (0.3, 0.8)))
    monkeypatch.setattr(analysis, "estimate_first_phrase", record("phrase", 2, (0.3, 0.8)))
    structure = TrackStructure(sections=[TrackSection("main", 0.0, 32.0, 0, 16, 50.0)], total_bars=16, phrase_unit=8)
    monkeypatch.setattr(analysis, "analyze_structure_windows", record("structure", 3, (structure, [[0.0, 32.0]], True)))
    monkeypatch.setattr(analysis, "calculate_genre_aware_mix_points", record("mixpoints", 1, (8.0, 24.0, 4, 12)))
    monkeypatch.setattr(analysis, "_validate_track_beatgrid", record("final_validation", 2, BeatgridValidation("verified", 3, 1.0)))
    monkeypatch.setattr(analysis, "calculate_file_lufs", lambda *_a: (-14.0, "complete", 32.0, 1, 22050))

    track = analysis.analyze_track(str(path))

    assert track is not None
    expected = PRIOR if fast_path else PRECISE
    assert track.bpm == expected
    assert seen == {name: expected for name in ("genre", "downbeat", "phrase", "structure", "mixpoints", "final_validation")}
    if fast_path:
        refine.assert_not_called()
    else:
        assert refine.call_count == 1


def _controlled(monkeypatch, candidate_status="verified", prior_status="mismatch"):
    candidate = Mock(return_value=(PRECISE, 0.2))
    monkeypatch.setattr(analysis, "estimate_fine_tempo", candidate)
    monkeypatch.setattr(analysis, "_beat_phase_from_fold", lambda *_a: (0.2, 0.9))
    calls = []

    def validate(windows, sr, bpm, **kwargs):
        calls.append(([(offset, audio.copy()) for offset, audio in windows], sr, bpm))
        return BeatgridValidation(candidate_status if bpm == PRECISE else prior_status, 3, 1.0)

    monkeypatch.setattr(analysis, "validate_beatgrid_windows", validate)
    return candidate, calls


@pytest.mark.parametrize("candidate_status,prior_status,expected", [
    ("verified", "mismatch", PRECISE), ("verified", "unverifiable", PRECISE),
    ("verified", "verified", PRIOR), ("mismatch", "mismatch", PRIOR),
    ("unverifiable", "mismatch", PRIOR),
])
def test_uebernahme_braucht_neue_bestaetigung_und_altes_unbestaetigtes_raster(monkeypatch, candidate_status, prior_status, expected):
    candidate, calls = _controlled(monkeypatch, candidate_status, prior_status)
    sr = 1000
    audio = np.arange(112 * sr, dtype=float)
    result = analysis._refine_audio_tempo(audio, sr, PRIOR, file_path="unused.wav", duration=112.0)
    assert result == expected
    assert candidate.call_count == 1
    np.testing.assert_array_equal(candidate.call_args.args[0], audio[:32 * sr])
    assert calls
    for windows, actual_sr, _bpm in calls:
        assert actual_sr == sr
        assert [offset for offset, _ in windows] == [32.0, 48.0, 96.0]
        for offset, segment in windows:
            np.testing.assert_array_equal(segment, audio[int(offset * sr):int(offset * sr) + 16 * sr])


def test_ein_sample_ueberlappung_verhindert_jeden_kandidaten(monkeypatch):
    candidate, calls = _controlled(monkeypatch)
    sr = 1000
    result = analysis._refine_audio_tempo(np.ones(112 * sr), sr, PRIOR, file_path="unused.wav", duration=112.0 - 1 / sr)
    assert result == PRIOR
    candidate.assert_not_called()
    assert calls == []


@pytest.mark.parametrize("failure", ["short", "nan", "wrong_sr", "exception"])
def test_unvollstaendiges_nachladefenster_ergibt_keinen_teilnachweis(monkeypatch, failure):
    _candidate, calls = _controlled(monkeypatch)
    sr = 1000
    def load(*args, **kwargs):
        if failure == "exception":
            raise OSError("synthetischer Decodefehler")
        count = 16 * sr - (failure == "short")
        return np.full(count, np.nan if failure == "nan" else 1.0), sr + (failure == "wrong_sr")
    monkeypatch.setattr(analysis.librosa, "load", load)
    result = analysis._refine_audio_tempo(np.ones(32 * sr), sr, PRIOR, file_path="synthetic.wav", duration=112.0)
    assert result == PRIOR
    assert calls == []


def test_spaeter_tempoaenderung_bleibt_mit_echten_fenstern_abgelehnt(monkeypatch):
    from tests.test_tempo_refinement import _pulses
    sr = 22050
    audio = _pulses(138.0, duration=112.0)
    audio[64 * sr:] = _pulses(140.0, duration=48.0)
    result = analysis._refine_audio_tempo(audio, sr, PRIOR, file_path="unused.wav", duration=112.0)
    assert result == PRIOR


def test_stabiles_tempo_braucht_drei_echte_disjunkte_audiofenster():
    from tests.test_tempo_refinement import _pulses
    audio = _pulses(138.0, duration=112.0)
    result = analysis._refine_audio_tempo(audio, 22050, PRIOR, file_path="unused.wav", duration=112.0)
    assert result == pytest.approx(138.0, abs=0.001, rel=0)


@pytest.mark.parametrize("failure", ["none", "exception"])
def test_ohne_kandidat_bleibt_urspruenglicher_float_exakt(monkeypatch, failure):
    candidate, calls = _controlled(monkeypatch)
    if failure == "none":
        candidate.return_value = None
    else:
        candidate.side_effect = ValueError("synthetischer Schaetzfehler")
    decode = Mock(side_effect=AssertionError("Ohne Kandidat nicht nachladen"))
    monkeypatch.setattr(analysis.librosa, "load", decode)
    prior = 136.123456789
    result = analysis._refine_audio_tempo(np.ones(32 * 1000), 1000, prior, file_path="unused.wav", duration=112.0)
    assert result.hex() == prior.hex()
    decode.assert_not_called()
    assert calls == []


@pytest.mark.parametrize("kind", ["short", "nan"])
def test_training_muss_vollstaendig_und_endlich_sein(monkeypatch, kind):
    candidate, calls = _controlled(monkeypatch)
    audio = np.ones(32 * 1000)
    if kind == "short":
        audio = audio[:-1]
    else:
        audio[-1] = np.nan
    assert analysis._refine_audio_tempo(audio, 1000, PRIOR, file_path="unused.wav", duration=112.0) == PRIOR
    candidate.assert_not_called()
    assert calls == []


@pytest.mark.parametrize("kind", ["inf", "stereo", "zero_sr", "nan_sr", "negative_duration", "nan_duration", "inf_duration"])
def test_ungueltige_analyseparameter_bewahren_das_prior(monkeypatch, kind):
    candidate, calls = _controlled(monkeypatch)
    audio, sr, duration = np.ones(32000), 1000, 112.0
    if kind == "inf":
        audio[100] = np.inf
    elif kind == "stereo":
        audio = np.ones((32000, 2))
    elif kind == "zero_sr":
        sr = 0
    elif kind == "nan_sr":
        sr = np.nan
    elif kind == "negative_duration":
        duration = -1.0
    elif kind == "nan_duration":
        duration = np.nan
    else:
        duration = np.inf
    assert analysis._refine_audio_tempo(audio, sr, PRIOR, file_path="unused.wav", duration=duration) == PRIOR
    candidate.assert_not_called()
    assert calls == []


def test_fehlender_prioranker_wird_nicht_als_nullanker_geprueft(monkeypatch):
    _candidate, calls = _controlled(monkeypatch)
    monkeypatch.setattr(analysis, "_beat_phase_from_fold", lambda *_a: (None, 0.0))
    assert analysis._refine_audio_tempo(np.ones(112000), 1000, PRIOR, file_path="unused.wav", duration=112.0) == PRECISE
    assert [bpm for _windows, _sr, bpm in calls] == [PRECISE]


def test_komplette_nachladefenster_nutzen_samplegenaue_offsets(monkeypatch):
    _candidate, calls = _controlled(monkeypatch)
    audio = np.arange(112001, dtype=float)
    requests = []
    def load(path, *, offset, duration, sr, **kwargs):
        requests.append((path, offset, duration, sr))
        start = round(offset * sr)
        return audio[start:start + round(duration * sr)], sr
    monkeypatch.setattr(analysis.librosa, "load", load)
    result = analysis._refine_audio_tempo(audio[:32000], 1000, PRIOR, file_path="synthetic.wav", duration=112.001)
    assert result == PRECISE
    assert requests == [("synthetic.wav", offset, 16.0, 1000) for offset in (32.0, 48.0, 96.001)]
    for windows, _sr, _bpm in calls:
        assert [offset for offset, _segment in windows] == [32.0, 48.0, 96.001]
        for offset, segment in windows:
            start = round(offset * 1000)
            np.testing.assert_array_equal(segment, audio[start:start + 16000])
