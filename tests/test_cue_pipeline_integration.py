from hpg_core import caching
from hpg_core.models import Track
from hpg_core import analysis
from hpg_core.ai_models import cue_service as cs
from hpg_core.structure_analyzer import TrackStructure, TrackSection
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
import pytest


def test_neural_schema_is_persisted():
    assert caching.CACHE_VERSION >= 99
    assert 'neural_analysis' in caching.TRACK_REQUIRED_FIELDS
    assert 'neural_analysis' in caching.TRACK_DICT_FIELDS
    assert 'neural_analysis' in Track.__dataclass_fields__


@pytest.mark.parametrize('tail_error', [False, True])
def test_head_tail_absolute_times_and_coverage(monkeypatch, tail_error):
    calls = []
    client = SimpleNamespace(config=cs.model_config())
    @contextmanager
    def session():
        yield client
    monkeypatch.setattr(cs, 'session', session)
    def structure(audio, sr, bpm, genre, **kwargs):
        calls.append(kwargs['cue_context'])
        results = cs._diagnostics(kwargs['cue_context']['candidates'], 'missing_window_context')
        return TrackStructure(sections=[TrackSection('main', 0., len(audio)/sr, 0, 1, 50.)], cue_diagnostics=results)
    monkeypatch.setattr(analysis, 'analyze_structure', structure)
    monkeypatch.setattr(analysis, 'LIBROSA_TAIL_DURATION', 10)
    def load(*args, **kwargs):
        if tail_error:
            raise OSError('tail probe')
        return np.ones(100, np.float32), 10
    monkeypatch.setattr(analysis.librosa, 'load', load)
    candidates = [dict(start_s=5., kind=1, mood=1), dict(start_s=95., kind=2, mood=1)]
    result, coverage, covered = analysis.analyze_structure_windows(
        'unused', np.ones(100, np.float32), 10, 120, 'Unknown', 100.,
        cue_candidates=candidates, cue_verified_grid=True)
    assert calls[0]['candidates'] is candidates
    assert calls[0]['window_start_s'] == 0
    assert result.cue_diagnostics[1]['start_s'] == 90
    if tail_error:
        assert result.cue_diagnostics[1]['status'] == 'decode_error'
        assert not covered
    else:
        assert calls[1]['candidates'] is candidates
        assert calls[1]['window_start_s'] == 90
        assert [x['index'] for x in result.cue_diagnostics[1]['results']] == [0, 1]
        assert coverage == [{'start': 0., 'end': 10.}, {'start': 90., 'end': 100.}]
    assert any(section.label == 'unanalysed' for section in result.sections)


def test_cache55_roundtrip_and_schema(tmp_path):
    path = tmp_path/'cache-source.wav'
    path.write_bytes(b'synthetic cache identity only')
    neural = dict(version=2, fingerprint='a'*64, beat_windows=[], windows=[dict(start_s=0., status='no_candidates', results=[])])
    track = Track(filePath=str(path), fileName=path.name, duration=300., bpm=120.,
                  analysis_mode='librosa_full_or_tail', neural_analysis=neural,
                  rekordbox_signature='source|neural:'+'a'*64)
    key = caching.generate_cache_key(str(path), track.rekordbox_signature)
    assert caching.cache_track(key, track)
    cached = caching.get_cached_track(key, file_path=str(path))
    assert cached.neural_analysis == neural
    # Exakt der bestehende AI-Worker-Vertrag aus main.py: gespeicherte Signatur.
    from tests.test_caching import _ai_metadata
    ai_key = caching.generate_cache_key(cached.filePath, cached.rekordbox_signature)
    assert ai_key == key
    assert caching.merge_cached_ai_metadata(ai_key, cached.filePath, _ai_metadata())
    merged = caching.get_cached_track(key, file_path=str(path))
    assert merged.neural_analysis == neural
    assert merged.ai_metadata == _ai_metadata()
    mismatch = caching.track_to_dict(track)
    mismatch['neural_analysis']['fingerprint'] = 'b'*64
    with pytest.raises(caching.CacheValidationError):
        caching.dict_to_track(mismatch)
    bad = caching.track_to_dict(track)
    bad['neural_analysis']['unexpected'] = True
    with pytest.raises(caching.CacheValidationError):
        caching.dict_to_track(bad)


@pytest.fixture
def pipeline(monkeypatch, tmp_path):
    path = tmp_path/'pipeline.wav'
    # Der Analysepfad liest den Reader auch bei gemockten Modellfenstern.
    # Ein gültiges kleines PCM-WAV testet den Vertrag ohne Decoderfehler.
    import soundfile as sf
    sf.write(path, np.zeros(44100, dtype=np.int16), 44100, subtype='PCM_16')
    importer = Mock()
    importer.get_track_signature.return_value = 'source-signature'
    importer.get_beatgrid.return_value = [dict(time=0., beat=1)]
    candidates = [dict(start_s=0., end_s=32., label='intro', kind=1, mood=1)]
    importer.get_phrases.return_value = candidates
    monkeypatch.setattr(analysis, 'get_rekordbox_importer', lambda: importer)
    monkeypatch.setattr(analysis, '_get_file_duration', lambda *a, **k: 32.)
    monkeypatch.setattr(analysis.librosa, 'load', lambda *a, **k: (np.ones(22050*32, np.float32), 22050))
    monkeypatch.setattr(analysis.librosa.beat, 'beat_track', lambda **k: (120., np.arange(64)))
    monkeypatch.setattr(analysis, '_refine_audio_tempo', lambda *a, **k: 120.)
    monkeypatch.setattr(analysis, 'extract_bpm_from_tags', lambda *a: None)
    monkeypatch.setattr(analysis, 'extract_metadata', lambda *a: ('Artist', 'Title', 'Techno'))
    monkeypatch.setattr(analysis, 'classify_genre', lambda *a, **k: SimpleNamespace(
        genre='Techno', confidence=1., source='test', mfcc_fingerprint=[0.]*13))
    monkeypatch.setattr(analysis, '_validate_track_beatgrid', lambda *a, **k: analysis.BeatgridValidation('verified', 3, 1.))
    monkeypatch.setattr(analysis, 'estimate_first_phrase', lambda *a, **k: (0., .8))
    monkeypatch.setattr(analysis, 'calculate_genre_aware_mix_points', lambda *a, **k: (8., 24., 4, 12))
    monkeypatch.setattr(analysis, 'calculate_file_lufs', lambda *a, **k: (-14., 'complete', 32., 1, 22050))
    for name, value in [('calculate_energy', 50), ('calculate_bass_intensity', 50),
                        ('calculate_brightness', 50), ('detect_vocal_instrumental', 'Instrumental'),
                        ('calculate_danceability', 50), ('generate_timbre_fingerprint', [0.]*13),
                        ('analyze_frequency_bands', (20., 30., 50.)), ('analyze_rhythm_complexity', (.5, .5)),
                        ('bass_kennwerte', (.5, .5)), ('_kandidaten_berechnen', ([], []))]:
        monkeypatch.setattr(analysis, name, lambda *a, _value=value, **k: _value)
    monkeypatch.setattr(analysis, 'compute_groove_fields', lambda *a, **k: analysis.GrooveFeatures())
    monkeypatch.setattr(cs, 'fingerprint', lambda *a: 'a'*64)
    monkeypatch.setattr(analysis, '_collect_beat_windows', lambda *args: [])
    return path, importer, candidates


@pytest.mark.parametrize('fast', [False, True])
@pytest.mark.parametrize('failure', ['none', 'transient', 'cache_write'])
def test_both_producers_cache_policy(pipeline, monkeypatch, fast, failure):
    from hpg_core.rekordbox_importer import RekordboxTrackData
    path, importer, candidates = pipeline
    from tests.fixtures.reference_grid import aligned_comparison
    importer.get_beatgrid.return_value = [
        dict(time=index * .5, beat=index % 4 + 1) for index in range(64)
    ]
    monkeypatch.setattr(analysis, '_compare_rekordbox_bar_positions', aligned_comparison)
    importer.get_track_data.return_value = RekordboxTrackData(bpm=120. if fast else None, duration=32., camelot_code='8A')
    misses, writes, seen = [], [], []
    monkeypatch.setattr(analysis, 'get_cached_track', lambda key, **k: misses.append(key))
    def persist(key, track):
        writes.append(track)
        return failure != 'cache_write'
    monkeypatch.setattr(analysis, '_persist_analysis_result', persist)
    def structure(*args, **kwargs):
        seen.append(kwargs)
        results = cs._diagnostics(candidates, 'service_error:TimeoutError') if failure == 'transient' else []
        value = TrackStructure(sections=[TrackSection('main', 0., 32., 0, 16, 50.)],
                               cue_diagnostics=[dict(start_s=0., status='evaluated', results=results)])
        return value, [dict(start=0., end=32.)], True
    monkeypatch.setattr(analysis, 'analyze_structure_windows', structure)
    result = analysis.analyze_track(str(path))
    assert seen[0]['cue_candidates'] == candidates
    assert seen[0]['cue_verified_grid'] is True
    if failure == 'cache_write':
        assert result is None
        assert len(writes) == 1
    else:
        assert result is not None
        assert result.neural_analysis['fingerprint'] == 'a'*64
        assert misses[0] == caching.generate_cache_key(str(path), result.rekordbox_signature)
        assert len(writes) == (0 if failure == 'transient' else 1)
    if failure == 'transient':
        assert analysis.analyze_track(str(path)) is not None
        assert len(misses) == 2
        assert not writes


def test_cache_hit_starts_no_service(pipeline, monkeypatch):
    path, importer, _ = pipeline
    importer.get_track_data.return_value = None
    cached = Track(filePath=str(path), fileName=path.name, analysis_mode='librosa_full_or_tail')
    monkeypatch.setattr(analysis, 'get_cached_track', lambda *a, **k: cached)
    monkeypatch.setattr(cs, 'session', lambda: pytest.fail('Cachehit started service'))
    assert analysis.analyze_track(str(path)) is cached


def test_pool_primary_recovery_deadline_and_cancel(monkeypatch):
    import time
    from concurrent.futures import Future
    from concurrent.futures.process import BrokenProcessPool
    from hpg_core import parallel_analyzer as pa
    created, submitted = [], []
    class Executor:
        _processes = {}
        def __init__(self, owner, broken):
            self._hpg_cue_owner = owner
            self._hpg_cue_generation = owner.register_generation().generation
            self.broken = broken
        def submit(self, fn, path, deadline, cache_policy):
            assert cache_policy == 'reuse'
            assert time.monotonic() < deadline <= time.monotonic()+pa.config.PARALLEL_ANALYSIS_TIMEOUT
            submitted.append((path, deadline, self._hpg_cue_generation))
            future = Future()
            if self.broken:
                future.set_exception(BrokenProcessPool('probe'))
            else:
                future.set_result(Track(filePath=path, fileName=path, analysis_mode='librosa_full_or_tail'))
            return future
        def shutdown(self, **kwargs):
            assert self._hpg_cue_generation not in self._hpg_cue_owner._generations
    def create(count, owner):
        value = Executor(owner, not created)
        created.append(value)
        return value
    monkeypatch.setattr(pa, '_create_executor', create)
    result = pa.ParallelAnalyzer(max_workers=2).analyze_files(['a', 'b'])
    assert len(result) == 2
    assert len(created) == 2
    assert created[0]._hpg_cue_owner is created[1]._hpg_cue_owner
    assert created[0]._hpg_cue_generation != created[1]._hpg_cue_generation


def test_wrapper_installs_exact_submit_deadline(monkeypatch):
    from hpg_core import parallel_analyzer as pa
    expected = 12345.
    def capture(path, *, cache_policy):
        assert cache_policy == 'reuse'
        assert cs._local.deadline == expected
        return 'captured'
    monkeypatch.setattr(analysis, 'analyze_track', capture)
    assert pa._analyze_track_wrapper('unused', expected) == 'captured'
    assert getattr(cs._local, 'deadline', None) is None
