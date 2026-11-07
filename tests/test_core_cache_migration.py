"""Historische Kernanalysen nur bei vollständiger Herkunft wiederverwenden."""
import sqlite3

import pytest

from hpg_core import caching
from hpg_core.ai_models import cue_service, deep_features
from hpg_core.models import Track


@pytest.mark.parametrize('policy', ['fresh', 'reuse'])
def test_analysis_routes_fresh_and_migrated_core_separately(tmp_path, monkeypatch, policy):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from hpg_core import analysis
    source = tmp_path/'source.wav'
    source.write_bytes(b'identity-only fixture')
    monkeypatch.setattr(analysis, '_get_file_duration', lambda *a: 300.)
    monkeypatch.setattr(analysis, 'get_rekordbox_importer', lambda: SimpleNamespace(
        get_track_data=lambda *a: None, get_track_signature=lambda *a: 'rb'))
    monkeypatch.setattr(cue_service, 'core_fingerprint', lambda: 'a'*64)
    track = Track(filePath=str(source), fileName=source.name, analysis_mode='librosa_full_or_tail')
    read = Mock(return_value=None)
    migrate = Mock(return_value=track)
    write = Mock(return_value=True)
    fresh = Mock(return_value=track)
    monkeypatch.setattr(analysis, 'get_cached_track', read)
    monkeypatch.setattr(analysis, 'get_legacy_cached_core', migrate)
    monkeypatch.setattr(analysis, 'cache_track', write)
    monkeypatch.setattr(analysis, '_analyze_audio_path', fresh)
    monkeypatch.setattr(deep_features, 'needs_refresh', lambda *a: False)
    assert analysis.analyze_track(str(source), cache_policy=policy) is track
    if policy == 'fresh':
        read.assert_not_called()
        migrate.assert_not_called()
        write.assert_not_called()
        fresh.assert_called_once()
        assert fresh.call_args.kwargs['cache_policy'] == 'fresh'
    else:
        migrate.assert_called_once_with(str(source), 'rb', 'a'*64)
        write.assert_called_once()
        fresh.assert_not_called()
        assert track.analysis_origin == 'cache'


@pytest.mark.parametrize('mutation', ['none', 'source', 'rekordbox', 'core', 'schema', 'path_spelling'])
def test_legacy_core_migration_is_bound_and_preserves_old_row(tmp_path, monkeypatch, mutation):
    monkeypatch.setattr(caching, 'CACHE_FILE', str(tmp_path/'cache.db'))
    monkeypatch.setattr(caching, 'LOCK_FILE', str(tmp_path/'cache.lock'))
    caching.init_cache()
    source = tmp_path/'source.wav'
    source.write_bytes(b'identity-only fixture')
    identities = {'stems': 'a'*64, 'embedding': 'b'*64}
    monkeypatch.setattr(deep_features, 'config_fingerprint', lambda: identities)
    old = cue_service.fingerprint()
    core = cue_service.core_fingerprint()
    track = Track(filePath=str(source), fileName=source.name, duration=300., bpm=128.,
                  analysis_mode='librosa_full_or_tail')
    track.rekordbox_signature = 'rb|neural:' + old
    track.neural_analysis = dict(version=2, fingerprint=old, windows=[], beat_windows=[])
    track.stem_analysis = deep_features._empty('stems', 300., identities['stems'], 'unavailable', 'fixture')
    track.embedding_analysis = deep_features._empty('embedding', 300., identities['embedding'], 'unavailable', 'fixture')
    key = caching.generate_cache_key(str(source), track.rekordbox_signature)
    assert caching.cache_track(key, track)
    identities = {'stems': 'c'*64, 'embedding': 'd'*64}
    rb = 'changed' if mutation == 'rekordbox' else 'rb'
    if mutation == 'source':
        source.write_bytes(b'changed source')
    if mutation == 'core':
        monkeypatch.setattr(cue_service, '_runtime_versions', lambda: {'changed': 'runtime'})
        core = cue_service.core_fingerprint()
    if mutation == 'schema':
        with sqlite3.connect(caching.CACHE_FILE) as connection:
            connection.execute('UPDATE cache SET data = ? WHERE key = ?', ('{}', key))
    if mutation == 'path_spelling':
        with sqlite3.connect(caching.CACHE_FILE) as connection:
            connection.execute('UPDATE cache SET filepath = ? WHERE key = ?', (str(source).replace('\\', '/').upper(), key))
    with sqlite3.connect(caching.CACHE_FILE) as connection:
        before = connection.execute('SELECT key, data FROM cache ORDER BY key').fetchall()
    migrated = caching.get_legacy_cached_core(str(source), rb, core)
    if mutation in {'none', 'path_spelling'}:
        assert migrated is not None
        assert migrated.rekordbox_signature == 'rb|neural:' + core
        assert migrated.neural_analysis['fingerprint'] == core
        assert migrated.bpm == track.bpm
    else:
        assert migrated is None
    with sqlite3.connect(caching.CACHE_FILE) as connection:
        assert connection.execute('SELECT key, data FROM cache ORDER BY key').fetchall() == before
