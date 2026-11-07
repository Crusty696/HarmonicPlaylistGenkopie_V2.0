"""Gezielter Refiner-Neuversuch und quellgebundene Erhaltung der Zusatzmerkmale."""
from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from hpg_core import analysis, caching
from hpg_core.ai_models import cue_service, deep_features as features, deep_feature_runtime
from hpg_core.ai_models import native_track_beats as native
from hpg_core.ai_models.native_audio_reader import CONTRACT
from hpg_core.models import Track
from tests.test_deep_features import embedding


def failure(revision=None):
    value = dict(status='unavailable', reason=native.REFINER_FAILURE_REASON)
    if revision is not None:
        value['failure_producer_revision'] = revision
    return value


@pytest.mark.parametrize('revision', [None, 0, 1])
def test_failure_revision_accepts_history_and_current_producer(revision):
    value = failure(revision)
    native.validate_snapshot(value, duration=58.)
    assert native.needs_refiner_repair(value) is (revision != 1)


@pytest.mark.parametrize('revision', [True, False, 1., -1, 2, '1'])
def test_failure_revision_rejects_invalid_types_and_future(revision):
    with pytest.raises(ValueError):
        native.validate_snapshot(failure(revision), duration=58.)
    assert not native.needs_refiner_repair(failure(revision))


@pytest.mark.parametrize('status,reason', [
    ('disabled', native.REFINER_FAILURE_REASON),
    ('unavailable', 'ValueError: service_error:TimeoutError'), ('ok', None),
])
def test_revision_cannot_mark_other_states(status, reason):
    value = dict(status=status, reason=reason, failure_producer_revision=1)
    with pytest.raises(ValueError):
        native.validate_snapshot(value, duration=58.)
    assert not native.needs_refiner_repair(value)


@pytest.fixture
def lookup(tmp_path, monkeypatch):
    source = tmp_path / 'source.wav'
    source.write_bytes(b'Nur Quellidentitaet, kein Audio')
    monkeypatch.setattr(analysis, '_get_file_duration', lambda *a: 58.)
    monkeypatch.setattr(cue_service, 'core_fingerprint', lambda: 'a'*64)
    monkeypatch.setattr(features, 'needs_refresh', lambda *a: False)
    monkeypatch.setattr(analysis, 'generate_cache_key', lambda *a: 'isolated-key')
    monkeypatch.setattr(analysis, 'get_legacy_cached_core', Mock(return_value=None))
    old = Track(filePath=str(source), fileName=source.name, duration=58., bpm=120.,
                analysis_mode='librosa_full_or_tail', native_beat_analysis=failure())
    monkeypatch.setattr(analysis, 'get_cached_track', Mock(return_value=old))
    return source, old


def importer(monkeypatch, rb):
    monkeypatch.setattr(analysis, 'get_rekordbox_importer', lambda: SimpleNamespace(
        get_track_data=lambda *a: SimpleNamespace(bpm=120.) if rb else None,
        get_track_signature=lambda *a: 'rb'))


@pytest.mark.parametrize('rb', [False, True])
@pytest.mark.parametrize('policy', ['reuse', 'fresh'])
def test_public_lookup_forwards_repair_both_paths_and_fresh_bypasses_cache(lookup, monkeypatch, rb, policy):
    source, old = lookup
    importer(monkeypatch, rb)
    selected = Mock(return_value=old)
    wrong = Mock(side_effect=AssertionError('Falscher Analysepfad'))
    monkeypatch.setattr(analysis, '_analyze_rekordbox_path', selected if rb else wrong)
    monkeypatch.setattr(analysis, '_analyze_audio_path', wrong if rb else selected)
    assert analysis.analyze_track(str(source), cache_policy=policy) is old
    selected.assert_called_once()
    args = selected.call_args.kwargs
    assert args['native_snapshot'] is None
    assert args['cache_policy'] == policy
    if policy == 'fresh':
        analysis.get_cached_track.assert_not_called()
        assert args['preserved_features'] is None
    else:
        assert args['preserved_features']['values']['embedding_analysis'] == old.embedding_analysis
    analysis.get_legacy_cached_core.assert_not_called()


@pytest.mark.parametrize('snapshot', [failure(1), dict(status='disabled', reason='disabled'),
    dict(status='unavailable', reason='ValueError: service_error:EOFError'),
    dict(status='ok', reason=None)])
def test_unaffected_validated_cache_rows_remain_hits(lookup, monkeypatch, snapshot):
    # Lookup ist kontrolliert; erfolgreiche Snapshotvalidierung gehört dem Cache.
    source, old = lookup
    old.native_beat_analysis = snapshot
    importer(monkeypatch, False)
    run = Mock(side_effect=AssertionError('Kein Neuversuch'))
    monkeypatch.setattr(analysis, '_analyze_audio_path', run)
    assert analysis.analyze_track(str(source)) is old
    assert old.analysis_origin == 'cache'
    run.assert_not_called()


def test_retry_once_then_current_revision_is_cache_hit(lookup, monkeypatch):
    source, old = lookup
    importer(monkeypatch, False)
    rows = {'isolated-key': old}
    monkeypatch.setattr(analysis, 'get_cached_track', lambda key, **kw: rows.get(key))
    monkeypatch.setattr(analysis, '_persist_analysis_result', lambda key, value: rows.update({key: value}) or True)
    monkeypatch.setattr(deep_feature_runtime, 'attach', lambda track: None)
    monkeypatch.setattr(cue_service, 'transient_failure', lambda value: False)
    transport = Mock(return_value=dict(status='unavailable', reason=native.REFINER_FAILURE_REASON.removeprefix('ValueError: ')))
    monkeypatch.setenv('HPG_NATIVE_BEAT', '1')
    def regular(**kw):
        track = deepcopy(old)
        track.native_beat_analysis = native.analyze(str(source), transport=transport)
        return analysis._finalize_analyzed_track(track, cache_key=kw['cache_key'],
            cache_policy=kw['cache_policy'], analysis_degraded=False,
            anchor_decision={'neural': {'transient': False}}, preserved_features=kw['preserved_features'])
    run = Mock(side_effect=regular)
    monkeypatch.setattr(analysis, '_analyze_audio_path', run)
    first = analysis.analyze_track(str(source))
    assert first.native_beat_analysis == failure(1)
    assert first.analysis_origin == 'fresh'
    assert analysis.analyze_track(str(source)) is first
    assert first.analysis_origin == 'cache'
    run.assert_called_once()
    transport.assert_called_once()


def valid_features():
    vector = embedding()
    vector['version'] = 5
    vector['data'].update(reader_backend='rekordbox-mpg123', reader_contract=CONTRACT,
        visualization=dict(status='unavailable', reason='models_unavailable',
            coordinates=[None, None], model_hashes=[], calibrated=False),
        danceability=dict(status='unavailable', reason='models_unavailable',
            values=[None, None], model_sha256=features.ENERGY_HASH, providers=[], calibrated=False))
    stem = dict(version=3, kind='stems', duration=58., fingerprint='a'*64,
        status='ok', reason=None, data=dict(curves={n: [0.]*58 for n in ('vocals', 'bass', 'drums', 'other')},
        hop_s=1., sample_rate=44100, samples=58*44100,
        reader_backend='rekordbox-mpg123', reader_contract=CONTRACT,
        model_sha256=features.MODEL_HASHES['hdemucs.onnx'], dll_sha256=features.DLL_HASH,
        provider_request='CPU', provider_verified=False, scale='stereo_rms_normalized_pcm', calibrated=False))
    return stem, vector


@pytest.mark.parametrize('mutation', [None, 'source', 'path', 'embedding_fingerprint', 'stem_version'])
def test_finalizer_preserves_only_source_bound_current_valid_features(lookup, monkeypatch, tmp_path, mutation):
    source, old = lookup
    old.stem_analysis, old.embedding_analysis = valid_features()
    preserved = analysis._preserve_repair_features(old)
    expected = deepcopy(preserved['values'])
    if mutation == 'source':
        source.write_bytes(b'Geaenderte Quelldatei mit anderer Laenge')
    elif mutation == 'path':
        source = tmp_path / 'other.wav'
        source.write_bytes(b'Andere Quelle')
    elif mutation == 'embedding_fingerprint':
        preserved['values']['embedding_analysis']['fingerprint'] = 'b'*64
    elif mutation == 'stem_version':
        preserved['values']['stem_analysis']['version'] = 2
    settings = features.config()
    settings.update(stems_enabled=True, embedding_enabled=True)
    monkeypatch.setattr(features, 'config', lambda: settings)
    monkeypatch.setattr(features, 'config_fingerprint', lambda *a: {'stems': 'a'*64, 'embedding': 'a'*64})
    from hpg_core.ai_models import feature_reuse
    monkeypatch.setattr(feature_reuse, 'load', lambda *a: None)
    monkeypatch.setattr(features, 'identities', lambda *a: {
        'stems': {'dll': features.DLL_HASH, 'stems': features.MODEL_HASHES},
        'embedding': {'embedding_model': features.EMBEDDING_HASH, 'energy_model': features.ENERGY_HASH, **features.UMAP_HASHES}})
    monkeypatch.setattr(features, 'source_duration_tolerance', lambda *a: 1/16000.)
    client = SimpleNamespace(deep_features=Mock(return_value=dict(status='unavailable', reason='test_no_inference')))
    monkeypatch.setattr(cue_service, 'session', lambda: nullcontext(client))
    monkeypatch.setattr(deep_feature_runtime, 'attach', features._attach)
    track = Track(filePath=str(source), fileName=source.name, duration=58., bpm=120., analysis_mode='librosa_full_or_tail')
    result = analysis._finalize_analyzed_track(track, cache_key='unused', cache_policy='fresh',
        analysis_degraded=False, anchor_decision={'neural': {'transient': False}}, preserved_features=preserved)
    assert result is track
    called = [call.args[0]['kind'] for call in client.deep_features.call_args_list]
    wanted = {'source': ['embedding', 'stems'], 'path': ['embedding', 'stems'],
              'embedding_fingerprint': ['embedding'], 'stem_version': ['stems']}.get(mutation, [])
    assert called == wanted
    for kind, field in [('stems', 'stem_analysis'), ('embedding', 'embedding_analysis')]:
        if kind not in wanted:
            assert getattr(track, field) == expected[field]
            features.validate(getattr(track, field), kind=kind, duration=58.)
        else:
            assert getattr(track, field)['status'] == 'unavailable'
    if mutation is None:
        restored = caching.dict_to_track(caching.track_to_dict(track))
        assert restored.stem_analysis == expected['stem_analysis']
        assert restored.embedding_analysis == expected['embedding_analysis']
