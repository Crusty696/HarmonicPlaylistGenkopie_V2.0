"""Lokale Zusatzmerkmale: Coverage, Herkunft, Fehlerfallback und keine Scheinscores."""
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from hpg_core.ai_models import deep_features as features
from hpg_core.ai_models.feature_audio import EnergyBins
from hpg_core.models import Track


def test_rekordbox_artifacts_follow_shared_install_root(monkeypatch, tmp_path):
    monkeypatch.setattr(features, 'REKORDBOX_ROOT', tmp_path / 'Rekordbox')

    paths = features.config()

    assert Path(paths['stem_dll']) == tmp_path / 'Rekordbox' / 'Demucs3.dll'
    assert Path(paths['embedding_model']) == (
        tmp_path / 'Rekordbox' / 'models' / 'embed_model' / 'cnn_embedding.onnx'
    )


@pytest.mark.parametrize('duration,expected', [
    (29., 30.), (600., 36.), (7200., 180.),
])
def test_embedding_timeout_scales_with_full_track_windows(duration, expected):
    assert features._feature_timeout_seconds('embedding', duration) == expected


def embedding(duration=58.):
    vector = [1.] + [0.]*63
    return dict(version=1, status='ok', reason=None, kind='embedding', duration=duration,
        fingerprint='a'*64, data=dict(vector=vector, model_sha256=features.EMBEDDING_HASH,
        providers=['CPUExecutionProvider'], calibrated=False,
        aggregation='hpg_duration_weighted_unit_mean_v1',
        windows=[dict(start_s=0., end_s=29., vector=vector),
                 dict(start_s=29., end_s=duration, vector=vector)]))


def test_energy_bins_do_not_move_with_model_block_boundaries():
    bins = EnergyBins(25, 10, ('vocals',))
    bins.add(0, np.ones((1, 2, 7)))
    bins.add(7, np.ones((1, 2, 18))*2)
    assert bins.result()['vocals'] == pytest.approx([np.sqrt(1.9), 2., 2.])


@pytest.mark.parametrize('damage', ['gap', 'norm', 'hash', 'duration', 'nonfinite'])
def test_embedding_rejects_invalid_provenance_and_coverage(damage):
    value = embedding()
    if damage == 'gap':
        value['data']['windows'][1]['start_s'] = 30.
    elif damage == 'norm':
        value['data']['vector'] = [0.]*64
    elif damage == 'hash':
        value['data']['model_sha256'] = '0'*64
    elif damage == 'duration':
        value['duration'] = 57.
    else:
        value['data']['windows'][0]['vector'][0] = float('nan')
    with pytest.raises(ValueError):
        features.validate(value, kind='embedding', duration=58.)


def test_missing_embeddings_are_not_zero_distance():
    left = Track(filePath='track.wav', fileName='track.wav', duration=58., bpm=120.)
    right = Track(filePath='track.wav', fileName='track.wav', duration=58., bpm=120.)
    assert features.pair_diagnostics(left, right, 0., 0., 8) == {}
    left.embedding_analysis = embedding()
    assert features.pair_diagnostics(left, right, 0., 0., 8) == {}
    right.embedding_analysis = embedding()
    diagnostic = features.pair_diagnostics(left, right, 0., 0., 8)
    assert diagnostic['embedding_cosine'] == pytest.approx(1.)
    assert diagnostic['affects_score'] is False
    assert features.pair_diagnostics(left, right, 50., 0., 8) == {}


def test_local_embedding_rejects_non_unit_window_vector():
    track = Track(filePath='track.wav', fileName='track.wav', duration=58., bpm=120.)
    track.embedding_analysis = embedding()
    track.embedding_analysis['data']['windows'][0]['vector'] = [2.] + [0.]*63

    assert features._local_embedding(track, 0., 10.) is None


def test_embedding_roundtrip_and_vector_binding(monkeypatch):
    from hpg_core.caching import track_to_dict, dict_to_track, CacheValidationError
    from hpg_core.ai_models.native_audio_reader import CONTRACT
    current = embedding()
    current['version'] = 5
    current['fingerprint'] = 'a'*64
    current['data'].update(
        reader_backend='rekordbox-mpg123',
        reader_contract=CONTRACT,
        visualization=dict(status='unavailable', reason='models_unavailable',
            coordinates=[None, None], model_hashes=[], calibrated=False),
        danceability=dict(status='unavailable', reason='models_unavailable',
            values=[None, None], model_sha256=features.ENERGY_HASH,
            providers=[], calibrated=False),
    )
    monkeypatch.setattr(
        features, 'config_fingerprint',
        lambda: {'stems': 'b'*64, 'embedding': 'a'*64},
    )
    track = Track(filePath='track.wav', fileName='track.wav', duration=58., bpm=120.,
                  analysis_mode="librosa_full_or_tail", embedding_analysis=current)
    value = track_to_dict(track)
    restored = dict_to_track(value)
    assert restored.embedding_analysis == track.embedding_analysis
    assert not hasattr(restored, 'audio_embedding')
    assert 'audio_embedding' not in value
    value = deepcopy(value)
    value['embedding_analysis']['data']['vector'][0] = 0.
    with pytest.raises(CacheValidationError):
        dict_to_track(value)


def test_feature_failure_keeps_existing_dsp_track(monkeypatch):
    track = Track(filePath='track.wav', fileName='track.wav', duration=58., bpm=128., energy=73.)
    def broken(_track):
        raise OSError('simulated unavailable model')
    monkeypatch.setattr(features, '_attach', broken)
    features.attach(track)
    assert track.energy == 73. and track.bpm == 128.
    assert features.transient_failure(track)


def test_cached_disabled_features_refresh_when_later_enabled(monkeypatch):
    settings = dict(stems_enabled=True, embedding_enabled=True)
    fingerprints = {'stems': 'a'*64, 'embedding': 'b'*64}
    monkeypatch.setattr(features, 'config', lambda: settings)
    monkeypatch.setattr(features, 'config_fingerprint', lambda _settings: fingerprints)
    monkeypatch.setattr(features, 'validate', lambda *_args, **_kwargs: None)
    track = Track(filePath='track.wav', fileName='track.wav', duration=58., bpm=120.,
        stem_analysis=dict(status='disabled', fingerprint='c'*64),
        embedding_analysis=dict(status='disabled', fingerprint='d'*64))

    assert features.needs_refresh(track)
    track.stem_analysis = dict(status='unsupported', fingerprint='a'*64)
    track.embedding_analysis = dict(status='unsupported', fingerprint='b'*64)
    assert not features.needs_refresh(track)


def test_disabled_features_clear_stale_cache_without_opening_model_service(
        monkeypatch, tmp_path):
    import builtins

    settings = dict(stems_enabled=False, embedding_enabled=False)
    fingerprints = {'stems': 'a'*64, 'embedding': 'b'*64}
    monkeypatch.setattr(features, 'config', lambda: settings)
    monkeypatch.setattr(features, 'config_fingerprint', lambda _settings: fingerprints)
    track = Track(filePath=str(tmp_path/'missing.wav'), fileName='missing.wav',
        duration=58., bpm=120.,
        stem_analysis=dict(status='ok', fingerprint='old-stems'),
        embedding_analysis=dict(status='ok', fingerprint='old-embedding'))
    assert features.needs_refresh(track)

    original_import = builtins.__import__
    def guarded_import(name, *args, **kwargs):
        if name.endswith(('.cue_service', '.feature_reuse')):
            raise AssertionError(f'Unexpected disabled feature import: {name}')
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded_import)

    features.attach(track)

    assert track.stem_analysis['status'] == 'disabled'
    assert track.embedding_analysis['status'] == 'disabled'
    assert not features.needs_refresh(track)


def test_cache_hit_rechecks_ok_features_when_fingerprint_unavailable(monkeypatch):
    monkeypatch.setattr(features, 'config', lambda: dict(
        stems_enabled=True, embedding_enabled=True))
    monkeypatch.setattr(features, 'config_fingerprint',
        lambda _settings: (_ for _ in ()).throw(OSError('model files unavailable')))
    monkeypatch.setattr(features, 'validate', lambda *_args, **_kwargs: None)
    track = Track(filePath='track.wav', fileName='track.wav', duration=58., bpm=120.,
        embedding_analysis=dict(status='ok', fingerprint='b'*64))

    assert features.needs_refresh(track)


def test_expired_optional_budget_never_connects(monkeypatch):
    from hpg_core.ai_models import cue_service as cs
    monkeypatch.setattr(cs.time, 'monotonic', lambda: 100.)
    monkeypatch.setattr(cs.socket, 'socket', lambda: pytest.fail('Kein Start ohne Restbudget'))
    client = cs.CueClient(('127.0.0.1', 1), 'token', 'generation', {})
    with cs.request_deadline(104.):
        result = client.deep_features({'kind': 'embedding'})
    assert result['status'] == 'unavailable'
    assert result['reason'] == 'service_error:TimeoutError'


@pytest.mark.parametrize('workers,stems,embedding,expected', [
    (1, '0', '0', 180.), (1, '1', '1', 600.),
    (4, '1', '1', 870.), (4, '0', '1', 870.),
])
def test_track_budget_accounts_for_serial_models(monkeypatch, workers, stems, embedding, expected):
    from hpg_core import config
    monkeypatch.setenv('HPG_STEMS', stems)
    monkeypatch.setenv('HPG_EMBEDDINGS', embedding)
    assert config.analysis_timeout_seconds(workers) == expected


def test_model_execution_budget_starts_after_broker_queue(monkeypatch):
    from hpg_core.ai_models import cue_service as cs
    clock = [100.]
    sent = []
    deadlines = []
    class Socket:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def settimeout(self, value): pass
        def connect(self, address): pass
    monkeypatch.setattr(cs.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(cs.socket, 'socket', Socket)
    monkeypatch.setattr(cs, '_send', lambda sock, data, deadline, cancel: sent.append(data))
    def receive(sock, maximum, deadline, cancel):
        deadlines.append(deadline)
        if len(deadlines) == 1:
            clock[0] = 300.
            return b'READY'
        auth = cs._load(sent[0])
        return cs._json(dict(request=auth['request'], results=dict(status='ok')))
    monkeypatch.setattr(cs, '_receive', receive)
    client = cs.CueClient(('127.0.0.1', 1), 'token', 'generation', {})
    with cs.request_deadline(800.):
        assert client.deep_features({'kind': 'embedding'}, timeout_s=30.) == {'status': 'ok'}
    assert deadlines == [795., 330.]
    envelope, _ = cs._header(sent[1])
    assert envelope['execution_timeout_s'] == 30.


def test_attach_assigns_each_model_its_execution_budget(monkeypatch, tmp_path):
    from contextlib import contextmanager
    from hpg_core.ai_models import cue_service as cs
    path = tmp_path / 'identity.wav'
    path.write_bytes(b'Nur Identitaet, keine Audiodaten')
    settings = dict(stems_enabled=True, embedding_enabled=True)
    monkeypatch.setattr(features, 'config', lambda: settings)
    monkeypatch.setattr(features, 'config_fingerprint', lambda config: 'a'*64)
    monkeypatch.setattr(features, 'identities', lambda config: dict(
        dll=features.DLL_HASH, stems=features.MODEL_HASHES, embedding=features.EMBEDDING_HASH))
    calls = []
    class Client:
        def deep_features(self, parameters, *, timeout_s):
            calls.append((parameters['kind'], timeout_s))
            return dict(status='unavailable', reason='controlled_failure')
    @contextmanager
    def session():
        yield Client()
    monkeypatch.setattr(cs, 'session', session)
    track = Track(filePath=str(path), fileName=path.name, duration=58., bpm=120.)
    features.attach(track)
    assert calls == [('embedding', 30.), ('stems', 240.)]
    assert features.transient_failure(track)
    assert track.bpm == 120.
