import numpy as np
import pytest

from hpg_core.ai_models import cue_predictor as cp


@pytest.fixture
def models(monkeypatch):
    calls = []

    class Model:
        def __init__(self, path):
            self.path = path

        def describe(self):
            return {'sha256': cp.MODEL_HASHES[self.path]}

        def run(self, inputs, output_names=None):
            calls.append((self.path, inputs))
            if self.path == 'samplecnn':
                return [np.repeat((np.arange(inputs["waveform"].shape[0], dtype=np.float32) % 6)[:, None], 512, axis=1)]
            return [np.full((inputs['input'].shape[0], 1), -2.5, dtype=np.float32)]

    monkeypatch.setattr(cp, '_file_hash', lambda path: cp.MODEL_HASHES[path])
    monkeypatch.setattr(cp.onnx_engine, 'get_model', lambda path, **kw: Model(path))
    return calls


def score(audio=None, candidates=None, **kw):
    args = dict(sample_rate=22050, samplecnn_path='samplecnn', cue_model_path='cue',
                window_start_s=0, track_duration_s=20, verified_grid=True)
    args.update(kw)
    if audio is None:
        audio = np.ones(441000, dtype=np.float32)
    if candidates is None:
        candidates = [{'start_s': 10, 'kind': 10, 'mood': 3}]
    return cp.score_phrase_candidates(audio, candidates=candidates, **args)


def test_feature_order_and_onehot(models):
    audio = np.arange(441000, dtype=np.float32) / np.float32(441000)
    result = score(audio=audio)
    assert result[0]['raw_score'] == -2.5
    waveform = models[0][1]['waveform']
    assert waveform.shape == (6, 59049)
    np.testing.assert_array_equal(waveform.reshape(-1), audio[220500-3*59049:220500+3*59049])
    feature = models[1][1]['input']
    assert feature.dtype == np.float64
    assert feature.shape == (1, 3085)
    assert np.flatnonzero(feature[0, :13]).tolist() == [9, 12]
    np.testing.assert_array_equal(feature[0, 13:], np.repeat(np.arange(6), 512))


def test_real_edge_padding_and_missing_context(models):
    result = score(candidates=[{'start_s': 0, 'kind': 1, 'mood': 1}])
    assert result[0]['status'] == 'ok'
    assert not models[0][1]['waveform'][:3].any()
    assert models[0][1]['waveform'][3:].all()
    models.clear()
    result = score(audio=np.ones(220500, dtype=np.float32), window_start_s=5)
    assert result[0]['status'] == 'unavailable'
    assert result[0]['raw_score'] is None
    assert not models


@pytest.mark.parametrize('kwargs', [
    {'sample_rate': 0}, {'sample_rate': True}, {'sample_rate': float('nan')},
    {'window_start_s': -1}, {'track_duration_s': 19}, {'verified_grid': 1},
    {'audio': np.ones((2, 3))}, {'audio': np.array([np.nan])},
    {'audio': np.array([1, 2], dtype=np.int16)},
    {'candidates': [{'start_s': 10, 'kind': 0, 'mood': 1}]},
    {'candidates': [{'start_s': 10, 'kind': 1, 'mood': 4}]},
    {'candidates': [{'start_s': 10, 'kind': True, 'mood': 1}]},
    {'candidates': [{'start_s': float('nan'), 'kind': 1, 'mood': 1}]},
])
def test_invalid_inputs_never_score(models, kwargs):
    result = score(**kwargs)
    assert result[0]['raw_score'] is None
    assert result[0]['status'] != 'ok'
    assert not models


def test_duplicates_preserve_indices(models):
    result = score(candidates=[{'start_s': 10, 'kind': 1, 'mood': 1}] * 2)
    assert [r['index'] for r in result] == [0, 1]
    assert [r['raw_score'] for r in result] == [-2.5, -2.5]


def test_unknown_hash(models, monkeypatch):
    monkeypatch.setattr(cp, '_file_hash', lambda path: 'unknown')
    assert score()[0]['status'] == 'unsupported_model'
    assert not models


@pytest.mark.parametrize('bad', [np.full((6, 512), np.nan), np.zeros((5, 512)), RuntimeError('failed')])
def test_model_failure(models, monkeypatch, bad):
    class Bad:
        def describe(self):
            return {'sha256': cp.MODEL_HASHES['samplecnn']}
        def run(self, *args, **kwargs):
            if isinstance(bad, Exception):
                raise bad
            return [bad]
    original = cp.onnx_engine.get_model
    monkeypatch.setattr(cp.onnx_engine, 'get_model', lambda path, **kw: Bad() if path == 'samplecnn' else original(path))
    assert score()[0]['raw_score'] is None


@pytest.mark.parametrize('bad', [np.array([[np.inf]], dtype=np.float32), np.zeros((2, 1), dtype=np.float32)])
def test_invalid_cue_output(models, monkeypatch, bad):
    original = cp.onnx_engine.get_model
    class Bad:
        def describe(self):
            return {'sha256': cp.MODEL_HASHES['cue']}
        def run(self, *args, **kwargs):
            return [bad]
    monkeypatch.setattr(cp.onnx_engine, 'get_model', lambda path, **kw: Bad() if path == 'cue' else original(path))
    assert score()[0]['raw_score'] is None


def test_tail_padding(models):
    result = score(candidates=[{'start_s': 19, 'kind': 1, 'mood': 1}])
    assert result[0]['status'] == 'ok'
    flat = models[0][1]['waveform'].reshape(-1)
    assert flat[:3*59049+22050].all()
    assert not flat[3*59049+22050:].any()


def test_resample_contract(models, monkeypatch):
    import sys
    from types import SimpleNamespace
    calls = []
    def resample(audio, **kwargs):
        calls.append(kwargs)
        return np.repeat(audio, 2)
    monkeypatch.setitem(sys.modules, 'librosa', SimpleNamespace(resample=resample))
    result = score(audio=np.full(220500, .25, dtype=np.float32), sample_rate=11025)
    assert result[0]['status'] == 'ok'
    assert calls == [{'orig_sr': 11025, 'target_sr': 22050, 'res_type': 'soxr_hq'}]
    assert np.all(models[0][1]['waveform'] == .25)


def test_bad_resampled_length(models, monkeypatch):
    import sys
    from types import SimpleNamespace
    monkeypatch.setitem(sys.modules, 'librosa', SimpleNamespace(resample=lambda *a, **k: np.ones(10)))
    result = score(audio=np.ones(220500, dtype=np.float32), sample_rate=11025)
    assert result[0]['status'] == 'unavailable'
    assert not models
