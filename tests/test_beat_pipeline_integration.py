"""Quellfenster/Produzenten/Persistenz; keine Originalmedien."""
from contextlib import contextmanager
from types import SimpleNamespace

import numpy as np
import pytest

from hpg_core import analysis, caching
from hpg_core.ai_models import cue_service as cs
from hpg_core.models import Track
from hpg_core.structure_analyzer import TrackStructure, TrackSection
from tests.test_cue_pipeline_integration import pipeline


def fake_window(start, duration=16., status='model_error'):
    return cs._beat_failure_window(start, duration, status, 'test')


@pytest.mark.parametrize('head_sr,loads', [(22050, 3), (44100, 0)])
def test_source_rate_and_full_head_reuse(monkeypatch, head_sr, loads):
    loaded, scored = [], []
    def load(path, **kwargs):
        loaded.append(kwargs)
        assert kwargs['sr'] == 44100 and kwargs['res_type'] == 'soxr_hq'
        return np.full(44100 * 16, .25, np.float32), 44100
    def score(audio, sr, **kwargs):
        scored.append((audio, sr, kwargs))
        return fake_window(kwargs['window_start_s'])
    @contextmanager
    def session():
        yield SimpleNamespace(score_beats=score)
    monkeypatch.setattr(analysis.librosa, 'load', load)
    monkeypatch.setattr(cs, 'session', session)
    windows = analysis._collect_beat_windows('unused', 48., np.ones(head_sr * 48, np.float32), head_sr)
    assert len(loaded) == loads
    assert [window['start_s'] for window in windows] == [0., 16., 32.]
    assert all(sr == 44100 for _, sr, _ in scored)
    if head_sr == 22050:
        assert all(audio[0] == .25 for audio, _, _ in scored)


def test_decode_failure_is_preserved_and_short_track_deduplicated(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError('synthetic decode failure')
    monkeypatch.setattr(analysis.librosa, 'load', fail)
    result = analysis._collect_beat_windows('unused', 8., np.zeros(22050, np.float32), 22050)
    assert len(result) == 1
    assert result[0]['status'] == 'decode_error'
    assert cs.transient_failure(dict(windows=[], beat_windows=result))


@pytest.mark.parametrize('fast', [False, True])
@pytest.mark.parametrize('status', ['missing_model', 'unsupported_model', 'model_error'])
def test_both_producers_beat_persistence_policy(pipeline, monkeypatch, fast, status):
    from hpg_core.rekordbox_importer import RekordboxTrackData
    path, importer, _ = pipeline
    importer.get_track_data.return_value = RekordboxTrackData(bpm=120. if fast else None,
                                                              duration=32., camelot_code='8A')
    monkeypatch.setattr(analysis, 'get_cached_track', lambda *args, **kwargs: None)
    monkeypatch.setattr(analysis, '_collect_beat_windows', lambda *args: [fake_window(0., status=status)])
    monkeypatch.setattr(analysis, 'analyze_structure_windows', lambda *args, **kwargs:
        (TrackStructure(sections=[TrackSection('main', 0., 32., 0, 16, 50.)]),
         [dict(start=0., end=32.)], True))
    writes = []
    monkeypatch.setattr(analysis, '_persist_analysis_result', lambda key, track: writes.append(track) or True)
    track = analysis.analyze_track(str(path))
    assert track is not None
    assert track.neural_analysis['version'] == 2
    assert '|neural:' in track.rekordbox_signature
    assert track.neural_analysis['beat_windows'][0]['results'][0]['status'] == status
    assert bool(writes) == (status != 'model_error')
    assert track.bpm == 120.


def test_schema55_roundtrip_and_strict_validation(tmp_path):
    path = tmp_path/'identity.wav'
    path.write_bytes(b'no audio; synthetic cache identity')
    neural = dict(version=2, fingerprint='a'*64, windows=[],
                  beat_windows=[fake_window(0., status='missing_model')])
    track = Track(filePath=str(path), fileName=path.name, duration=32., bpm=120., neural_analysis=neural,
                  rekordbox_signature='source|neural:'+'a'*64, analysis_mode='librosa_full_or_tail')
    key = caching.generate_cache_key(str(path), track.rekordbox_signature)
    assert caching.CACHE_VERSION >= 99
    assert caching.cache_track(key, track)
    assert caching.get_cached_track(key, file_path=str(path)).neural_analysis == neural
    neural['beat_windows'][0]['results'][0]['extra'] = True
    with pytest.raises(ValueError):
        cs.validate_neural_analysis(neural)


def test_eof_and_short_read_are_not_padded(monkeypatch):
    loaded = []
    def load(path, **kwargs):
        loaded.append(kwargs)
        return np.zeros(44100, np.float32), 44100
    monkeypatch.setattr(analysis.librosa, 'load', load)
    result = analysis._collect_beat_windows('unused', 20., None, 0)
    assert [window['start_s'] for window in result] == [0., 2., 4.]
    assert all(window['status'] == 'decode_error' for window in result)
    assert loaded[-1]['offset'] + loaded[-1]['duration'] == 20.


def test_cache_rejects_outside_track_or_duplicate_windows():
    window = fake_window(0., status='missing_model')
    value = dict(version=2, fingerprint='a'*64, windows=[], beat_windows=[window])
    with pytest.raises(ValueError):
        cs.validate_neural_analysis(value, track_duration_s=8.)
    value['beat_windows'].append(window)
    with pytest.raises(ValueError):
        cs.validate_neural_analysis(value)
