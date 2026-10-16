"""Native Verträge ohne Ausführung des proprietären Generators."""
from copy import deepcopy
from contextlib import contextmanager
from types import SimpleNamespace

import numpy as np
import pytest

from hpg_core.ai_models import native_phrase_adapter as adapter
from hpg_core.rekordbox_phrases import phrase_grid_from_phrases


def native_snapshot():
    return dict(version=4, status='ok', reason=None,
        source='rekordbox_native_phrase_generator', contract=adapter.CONTRACT_VERSION,
        executable_sha256=adapter.SHA256, terminal_boundary_source='native_terminal_beat',
        key_source='native_unknown_fallback_zero',
        input_grid=dict(bpm_hundredths=12000, offset_ms=0, bar_position=1, key_index=0,
                        basis='hpg_verified_constant_grid', beat_count=240,
                        first_tick_s=0., last_tick_s=119.5, terminal_beat=240),
        reader_backend='hpg-libsndfile',
        phrases=[dict(start_s=0., end_s=32., label='Intro', kind=1, mood=1, fill=0),
                 dict(start_s=32., end_s=119.5, label='Outro', kind=6, mood=1, fill=0)])


def test_disabled_and_existing_pssi_never_start_service(monkeypatch):
    from hpg_core.ai_models import cue_service
    monkeypatch.setenv('HPG_NATIVE_PHRASE', '0')
    monkeypatch.setattr(cue_service, 'session', lambda: pytest.fail('Unexpected native service'))
    parameters = dict(bpm=120., duration=120., first_downbeat=0., grid_usable=True,
                      usage_blocked=False, reference_grid=[], grid_source='librosa')
    assert adapter.analyze_track_phrases('unused', imported_phrases=[], **parameters)['status'] == 'disabled'
    monkeypatch.setenv('HPG_NATIVE_PHRASE', '1')
    result = adapter.analyze_track_phrases('unused', imported_phrases=[{}], **parameters)
    assert result['reason'] == 'imported_phrases_preferred'
    parameters['usage_blocked'] = True
    assert adapter.analyze_track_phrases('unused', imported_phrases=[], **parameters)['phrases'] == []


@pytest.mark.parametrize('damage', ['hash', 'phase', 'interval', 'terminal', 'blocked', 'unverified'])
def test_native_snapshot_rejects_provenance_and_grid_corruption(damage):
    value = native_snapshot()
    if damage == 'hash':
        value['executable_sha256'] = '0'*64
    elif damage == 'phase':
        value['phrases'][1]['start_s'] = 32.1
        value['phrases'][0]['end_s'] = 32.1
    elif damage == 'interval':
        value['phrases'][0]['end_s'] = 33.
    elif damage == 'terminal':
        value['phrases'][-1]['end_s'] = 119.
    with pytest.raises(ValueError):
        adapter.validate_snapshot(value, duration=120., grid_verified=damage != 'unverified',
                                  usage_blocked=damage == 'blocked')


def test_worker_grid_changes_are_rejected_before_adoption(tmp_path):
    path = tmp_path/'identity.bin'
    path.write_bytes(b'identity only, no audio')
    def transport(request, **kwargs):
        return dict(status='ok', contract=adapter.CONTRACT_VERSION, executable_sha256=adapter.SHA256,
                    input_grid={key: request[key] for key in ('bpm_hundredths', 'offset_ms', 'bar_position', 'key_index')},
                    header=[2, 10, 1, 1, 0, 0, 0], arrays={}, frames=12000, sample_rate=100,
                    reader_backend='hpg-libsndfile')
    result = adapter.generate_phrases(path, beat_times=[i*.5 for i in range(240)],
        beat_positions=[i%4+1 for i in range(240)], bpm=120., duration=120.,
        verified_grid=True, key_index=0, transport=transport)
    assert result['reason'] == 'invalid_native_header_or_grid_change'


@pytest.mark.parametrize('terminal,expected', [(201, 100.), (65, None), (241, None)])
def test_native_terminal_boundary_is_not_extended_to_file_end(tmp_path, terminal, expected):
    path = tmp_path/'identity.bin'
    path.write_bytes(b'identity only')
    def transport(request, **kwargs):
        return dict(status='ok', contract=adapter.CONTRACT_VERSION, executable_sha256=adapter.SHA256,
            input_grid={key: request[key] for key in ('bpm_hundredths', 'offset_ms', 'bar_position', 'key_index')},
            header=[2, 0, 1, 1, 0, 0, terminal],
            arrays=dict(beat_positions=[1, 65], kind=[1, 6], fill_in=[0, 0]),
            frames=12000, sample_rate=100, reader_backend='hpg-libsndfile')
    result = adapter.generate_phrases(path, beat_times=[i*.5 for i in range(240)],
        beat_positions=[i%4+1 for i in range(240)], bpm=120., duration=120.,
        verified_grid=True, key_index=0, transport=transport)
    if expected is None:
        assert result['status'] == 'unavailable'
        assert result['phrases'] == []
    else:
        assert result['status'] == 'ok'
        assert result['phrases'][-1]['end_s'] == expected
        assert result['terminal_boundary_source'] == 'native_terminal_beat'


@pytest.mark.parametrize('source', ['audio', 'rekordbox'])
@pytest.mark.parametrize('note,mode,index,key_source', [
    ('', '', 0, 'native_unknown_fallback_zero'),
    ('A', 'Major', 0, 'hpg_key_native_table'),
    ('A#', 'Major', 1, 'hpg_key_native_table'),
    ('F#', 'Minor', 21, 'hpg_key_native_table'),
])
def test_active_native_path_preserves_input_grid_and_separate_snapshot(monkeypatch, source, note, mode, index, key_source):
    from hpg_core.ai_models import cue_service
    monkeypatch.setenv('HPG_NATIVE_PHRASE', '1')
    monkeypatch.setattr(adapter, 'identity', lambda: {'actual_sha256': adapter.SHA256})
    @contextmanager
    def session():
        yield SimpleNamespace(native_phrases=lambda *a, **kw: None)
    monkeypatch.setattr(cue_service, 'session', session)
    def generate(path, **kwargs):
        assert kwargs['beat_times'] == [i*.5 for i in range(240)]
        assert kwargs['beat_positions'] == [i%4+1 for i in range(240)]
        assert kwargs['verified_grid'] is True
        assert kwargs['key_index'] == index
        return dict(status='ok', reason=None, phrases=native_snapshot()['phrases'], terminal_beat=240,
            reader_backend='hpg-libsndfile',
            raw_result=dict(input_grid=dict(bpm_hundredths=12000, offset_ms=0, bar_position=1, key_index=index)))
    monkeypatch.setattr(adapter, 'generate_phrases', generate)
    reference = [dict(time=i*.5, beat=i%4+1) for i in range(240)] if source == 'rekordbox' else []
    result = adapter.analyze_track_phrases('unused', bpm=120., duration=120., first_downbeat=0.,
        grid_usable=True, usage_blocked=False, imported_phrases=[], reference_grid=reference, grid_source=source,
        key_note=note, key_mode=mode)
    assert result['status'] == 'ok'
    assert result['key_source'] == key_source
    assert result['input_grid']['basis'] == ('verified_rekordbox_grid' if source == 'rekordbox' else 'hpg_verified_constant_grid')


def test_native_boundaries_reach_head_and_tail_without_filling_coverage(monkeypatch):
    from hpg_core import analysis
    from hpg_core.structure_analyzer import TrackSection, TrackStructure
    contexts = []
    def structure(audio, sr, bpm, genre, **kwargs):
        contexts.append(kwargs['native_phrase_context'])
        return TrackStructure(sections=[TrackSection('main', 0., len(audio)/sr, 0, 1, 50.)])
    monkeypatch.setattr(analysis, 'analyze_structure', structure)
    monkeypatch.setattr(analysis, 'LIBROSA_TAIL_DURATION', 10)
    monkeypatch.setattr(analysis.librosa, 'load', lambda *a, **kw: (np.ones(100), 10))
    structure, coverage, covered = analysis.analyze_structure_windows(
        'unused', np.ones(100), 10, 120., 'Unknown', 120., native_phrase_analysis=native_snapshot())
    assert [x['window_start_s'] for x in contexts] == [0., 110.]
    assert coverage == [{'start': 0., 'end': 10.}, {'start': 110., 'end': 120.}]
    assert covered and any(section.label == 'unanalysed' for section in structure.sections)


def test_native_candidate_provenance_is_not_pssi():
    from hpg_core.mix_candidates import collect_candidate_times
    phrases = native_snapshot()['phrases']
    ins, outs = collect_candidate_times(seite_grid=phrase_grid_from_phrases(phrases),
        sections=[dict(start_time=0., end_time=120., label='main')], phrases=[], native_phrases=phrases,
        cues=[], analyzer_in=None, analyzer_out=None, duration=120., grid_sec=16.,
        intro_end=16., outro_start=96., outro_covered=True)
    candidates = ins + outs
    assert candidates
    assert all('pssi_phrase' not in item.schema for item in candidates)
    assert any(item.provenance == 'rekordbox_native_phrase_generator' for item in candidates)


def test_native_cache_contract_roundtrip_and_tampering(tmp_path):
    from hpg_core import caching
    from hpg_core.models import Track
    snapshot = native_snapshot()
    path = tmp_path/'source.bin'
    path.write_bytes(b'cache identity only')
    track = Track(filePath=str(path), fileName=path.name, duration=120., bpm=120.,
        downbeat_confidence=.9, beatgrid_status='verified', beatgrid_source='audio',
        bar_position_status='audio_estimate',
        beatgrid_windows_checked=3, beatgrid_max_phase_error_ms=1.,
        analysis_mode='librosa_full_or_tail', native_phrase_analysis=snapshot,
        phrase_grid=phrase_grid_from_phrases(snapshot['phrases']),
        neural_analysis=dict(version=2, fingerprint='a'*64, windows=[], beat_windows=[]),
        rekordbox_signature='source|neural:'+'a'*64)
    payload = caching.track_to_dict(track)
    restored = caching.dict_to_track(payload)
    assert restored.native_phrase_analysis == snapshot
    assert restored.phrases == []
    corrupt = deepcopy(payload)
    corrupt['phrase_grid'] = []
    with pytest.raises(caching.CacheValidationError):
        caching.dict_to_track(corrupt)
