"""LLM-Antworten dürfen nicht nachträglich an eine andere Quelldatei gebunden werden."""
from contextlib import contextmanager
from copy import deepcopy
import sqlite3

import pytest

from hpg_core import ai_engine, caching
from hpg_core.app_workers import AIAnalysisWorker
from hpg_core.models import Track


def metadata(track, label, model='previous-model'):
    return ai_engine.validate_ai_analysis(dict(
        sub_genre='Psytrance', moods=['driving', 'dark'], description=label,
        mix_in_time=10., mix_out_time=250.), track, 'Ollama', model)


@pytest.mark.parametrize('change_at', ['request', 'before_merge', 'inside_lock', None])
def test_ai_response_keeps_original_source_binding(tmp_path, monkeypatch, qtbot, change_at):
    # Keine Originalmusik und kein Decoder: ausschließlich synthetische Statdaten.
    source = tmp_path / 'source.wav'
    source.write_bytes(b'source A')
    monkeypatch.setattr(caching, 'CACHE_FILE', str(tmp_path / 'cache.db'))
    monkeypatch.setattr(caching, 'LOCK_FILE', str(tmp_path / 'cache.lock'))
    caching.init_cache()
    track = Track(filePath=str(source), fileName=source.name, duration=300., bpm=128.,
                  analysis_mode='librosa_full_or_tail')
    track.ai_metadata = metadata(track, 'Bestehende Beschreibung A')
    original_metadata = deepcopy(track.ai_metadata)
    key_a = caching.generate_cache_key(str(source), track.rekordbox_signature)
    assert caching.cache_track(key_a, track)
    answer_a = metadata(track, 'Neue Antwort für Quelle A', model='selected')
    replacement = deepcopy(track)
    replacement.title = 'Quelle B'
    replacement.ai_metadata = metadata(replacement, 'Gültige Beschreibung B')
    key_b = None
    changed = False

    def replace_source():
        nonlocal changed
        source.write_bytes(b'changed source B with different size')
        changed = True

    def fetch(*args, **kwargs):
        nonlocal key_b
        if change_at == 'request':
            replace_source()
            key_b = caching.generate_cache_key(str(source), replacement.rekordbox_signature)
            assert key_b != key_a
            assert caching.cache_track(key_b, replacement)
        return answer_a

    monkeypatch.setattr(ai_engine, 'fetch_ai_analysis', fetch)
    original_merge = caching.merge_cached_ai_metadata
    def merge(*args, **kwargs):
        if change_at == 'before_merge':
            replace_source()
        return original_merge(*args, **kwargs)
    monkeypatch.setattr(caching, 'merge_cached_ai_metadata', merge)

    original_lock = caching.file_lock
    @contextmanager
    def lock(*args, **kwargs):
        with original_lock(*args, **kwargs):
            # Simuliert Änderung während Wartezeit vor dem geschützten Merge.
            if change_at == 'inside_lock' and not changed:
                replace_source()
            yield
    monkeypatch.setattr(caching, 'file_lock', lock)
    worker = AIAnalysisWorker([track], 'Ollama', 'selected', 'http://local/test')
    published, failures = [], []
    worker.ai_finished.connect(lambda *args: published.append(args))
    worker.failed.connect(failures.append)
    worker.run()

    # Direkter SQL-Lesezugriff bewahrt auch die inzwischen historische Zeile A.
    # Keine Quarantäne oder Invalidierung als vermeintliche Fehlerbehebung.
    import json
    with sqlite3.connect(caching.CACHE_FILE) as connection:
        rows = {key: json.loads(data) for key, data in connection.execute(
            "SELECT key, data FROM cache WHERE key <> 'version'")}
    if change_at is None:
        assert not failures
        assert published == [(str(source), answer_a)]
        assert rows[key_a]['ai_metadata'] == answer_a
        assert track.ai_metadata == answer_a
    else:
        assert changed
        assert failures, 'Quellwechsel muss sichtbar scheitern'
        assert 'Quelldatei geändert' in failures[0]
        assert 'erneut analysieren' in failures[0]
        assert not published, 'Veraltete Antwort darf keinen Erfolg publizieren'
        assert track.ai_metadata == original_metadata
        assert rows[key_a]['ai_metadata'] == original_metadata
        if key_b is not None:
            assert rows[key_b]['ai_metadata'] == replacement.ai_metadata
            assert rows[key_b]['title'] == 'Quelle B'


@pytest.mark.parametrize('changed', [False, True])
def test_fresh_ai_does_not_require_or_write_track_cache(tmp_path, monkeypatch, qtbot, changed):
    source = tmp_path / 'fresh.wav'
    source.write_bytes(b'original source')
    monkeypatch.setattr(caching, 'CACHE_FILE', str(tmp_path / 'cache.db'))
    monkeypatch.setattr(caching, 'LOCK_FILE', str(tmp_path / 'cache.lock'))
    caching.init_cache()
    track = Track(filePath=str(source), fileName=source.name, duration=300., bpm=128.,
                  analysis_mode='librosa_full_or_tail')
    answer = metadata(track, 'Frische Antwort', model='selected')
    def fetch(*args, **kwargs):
        if changed:
            source.write_bytes(b'replaced source with different length')
        return answer
    monkeypatch.setattr(ai_engine, 'fetch_ai_analysis', fetch)
    worker = AIAnalysisWorker([track], 'Ollama', 'selected', 'http://local/test',
                              cache_policy='fresh')
    published, failures = [], []
    worker.ai_finished.connect(lambda *args: published.append(args))
    worker.failed.connect(failures.append)
    worker.run()
    with sqlite3.connect(caching.CACHE_FILE) as connection:
        assert connection.execute("SELECT count(*) FROM cache WHERE key <> 'version'").fetchone()[0] == 0
    if changed:
        assert not published
        assert 'Quelldatei geändert' in failures[0]
    else:
        assert not failures
        assert published == [(str(source), answer)]
        assert track.ai_metadata == answer
