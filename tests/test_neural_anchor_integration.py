"""Ankerübernahme durch beide echten Producer, mit kontrollierten Messungen."""
from copy import deepcopy
import numpy as np
import pytest
from hpg_core import analysis, caching
from hpg_core.ai_models import cue_service as cs, beat_predictor as bp, native_beat_decoder as bd
from hpg_core.rekordbox_importer import RekordboxTrackData
from hpg_core.structure_analyzer import TrackStructure, TrackSection
from tests.test_cue_pipeline_integration import pipeline


def windows():
    values = np.full((1600, 2), .001, np.float32)
    for n, frame in enumerate(range(20, 1600, 50)):
        values[frame, 1 if n % 4 == 0 else 0] = .97
    # Kontrollierter nativer Producer-Double; hier wird die Ankerintegration
    # geprüft, kein EXE-Code im pytest-Hauptprozess gestartet.
    from unittest.mock import patch
    native = {'bpm': 120., 'grid': [{'pos': frame * 441, 'numBar': n % 4 + 1}
                        for n, frame in enumerate(range(20, 1600, 50))]}
    with patch.object(bd, 'decode', return_value=native):
        decoded = bd.decode_beat_activations(values, duration_s=16.)
    result = []
    for start in (0., 16., 32.):
        window = cs._beat_failure_window(start, 16., 'model_error', 'test')
        for item in window['results']:
            candidate = deepcopy(decoded)
            for event in candidate['beats']:
                event['time_s'] += start
            candidate['first_downbeat'] += start
            item.update(status='ok', reason=None, decoder=candidate,
                        model_hashes=bp.MODEL_HASHES[item['model_id']])
        cs._validate_beat_window(window)
        result.append(window)
    return result


def test_fixed_bpm_retry_keeps_retry_cause_when_candidate_is_rejected(monkeypatch):
    calls = iter([
        ((0.0, 0.0), {'reason': 'incommensurate', 'stage': 'beat_tracking'}),
        ((0.0, 0.0), {'reason': 'fold_alignment', 'stage': 'fold'}),
    ])

    def estimate(*args, diagnostics, **kwargs):
        result, values = next(calls)
        diagnostics.update(values)
        return result

    monkeypatch.setattr(analysis, 'estimate_first_downbeat', estimate)
    diagnostics = {}
    result = analysis._estimate_audio_downbeat(
        np.ones(64), 22050, 138., file_path='unused', duration=4., diagnostics=diagnostics,
    )
    assert result == (0.0, 0.0)
    assert diagnostics == {
        'reason': 'incommensurate', 'stage': 'beat_tracking',
        'retry_reason': 'fold_alignment',
    }


def test_fixed_bpm_retry_keeps_grid_rejection_reason(monkeypatch):
    calls = iter([
        ((0.0, 0.0), {'reason': 'incommensurate', 'stage': 'beat_tracking'}),
        ((0.1, 0.7), {'reason': 'ok', 'stage': 'result'}),
    ])

    def estimate(*args, diagnostics, **kwargs):
        result, values = next(calls)
        diagnostics.update(values)
        return result

    monkeypatch.setattr(analysis, 'estimate_first_downbeat', estimate)
    monkeypatch.setattr(analysis, '_validate_track_beatgrid', lambda *a, **k: type(
        'Validation', (), {'status': 'mismatch', 'reason': 'phasemismatch', 'max_phase_error_ms': 16.3}
    )())
    diagnostics = {}
    result = analysis._estimate_audio_downbeat(
        np.ones(64), 22050, 138., file_path='unused', duration=4., diagnostics=diagnostics,
    )
    assert result == (0.0, 0.0)
    assert diagnostics == {
        'reason': 'incommensurate', 'stage': 'beat_tracking',
        'retry_reason': 'phasemismatch',
    }


def setup_adoption(pipeline, monkeypatch, fast=True):
    path, importer, _ = pipeline
    importer.get_track_data.return_value = RekordboxTrackData(bpm=120. if fast else None, duration=48., camelot_code='8A', path_match='volume_rebind')
    monkeypatch.setattr(analysis, '_get_file_duration', lambda *a: 48.)
    monkeypatch.setattr(analysis.librosa, 'load', lambda *a, **k: (np.ones(22050*48, np.float32), 22050))
    # Der Produktpfad lädt inzwischen über den gemeinsamen Reader. Die
    # kontrollierten Fenster dieses Ankertests müssen diese Grenze ersetzen.
    monkeypatch.setattr(analysis, '_load_analysis_audio', lambda *a, **k: (
        np.ones(round(min(k.get('duration', 48.), 48. - k.get('offset', 0.))
                      * k.get('sr', 22050)), np.float32), k.get('sr', 22050)))
    monkeypatch.setattr(analysis, 'get_cached_track', lambda *a, **k: None)
    monkeypatch.setattr(analysis, '_estimate_audio_downbeat', lambda *a, **k: (.7, .1))
    monkeypatch.setattr(analysis, 'estimate_first_downbeat', lambda *a, **k: (.2, .6))
    def grid(path, duration, bpm, anchor, **kwargs):
        return analysis.BeatgridValidation('verified', 3, 0.) if abs(anchor % 2-.2)<1e-6 else analysis.BeatgridValidation('mismatch', 3, 8., phase_pattern='variable_phase')
    monkeypatch.setattr(analysis, '_validate_track_beatgrid', grid)
    monkeypatch.setattr(analysis, '_collect_beat_windows', lambda *a: windows())
    phrases = []
    monkeypatch.setattr(analysis, 'estimate_first_phrase', lambda y, sr, bpm, anchor, unit: (phrases.append(anchor) or anchor, .8))
    def structure(*args, **kwargs):
        if phrases:
            assert kwargs['anchor'] == phrases[-1]
        return (TrackStructure(sections=[TrackSection('main', 0., 48., 0, 24, 50.)]),
                [dict(start=0., end=48.)], True)
    def mixpoints(*args, **kwargs):
        if phrases:
            assert kwargs['anchor'] == phrases[-1]
            assert kwargs['first_downbeat'] == phrases[-1]
        return 8., 24., 4, 12
    monkeypatch.setattr(analysis, 'analyze_structure_windows', structure)
    monkeypatch.setattr(analysis, 'calculate_genre_aware_mix_points', mixpoints)
    monkeypatch.setattr(analysis, '_persist_analysis_result', lambda *a: True)
    return path, importer, phrases


@pytest.mark.parametrize("fast", [True, False])
def test_producer_adopts_anchor(pipeline, monkeypatch, fast):
    path, importer, phrases = setup_adoption(pipeline, monkeypatch, fast)
    track = analysis.analyze_track(str(path))
    assert track is not None
    assert track.first_downbeat == pytest.approx(.2)
    assert phrases == [pytest.approx(.2)]
    assert track.beatgrid_source == 'audio'
    assert track.phrases == []
    assert caching.CACHE_VERSION == 180

    assert track.measurement_diagnostics['version'] == 8
    active = track.measurement_diagnostics['anchor']
    assert active['method'] == 'neural_audio'
    assert active['reference']['anchor_s'] == 0.
    assert active['reference']['path_match'] == 'volume_rebind'
    assert active['reference']['measurement']['grid']['status'] == 'mismatch'
    assert active['neural']['reason'] == 'adopted'
    key = caching.generate_cache_key(str(path), track.rekordbox_signature)
    assert caching.cache_track(key, track)
    cached = caching.get_cached_track(key, file_path=str(path))
    assert cached.first_downbeat == track.first_downbeat
    assert cached.measurement_diagnostics == track.measurement_diagnostics
    bad = caching.track_to_dict(track)
    bad['measurement_diagnostics']['anchor']['source'] = 'rekordbox'
    with pytest.raises(caching.CacheValidationError):
        caching.dict_to_track(bad)


def test_reference_and_reliable_baseline_take_priority(pipeline, monkeypatch):
    path, importer, _ = setup_adoption(pipeline, monkeypatch)
    monkeypatch.setattr(analysis, '_validate_track_beatgrid', lambda *a, **k:
                        analysis.BeatgridValidation('verified', 3, 0.))
    monkeypatch.setattr(analysis, 'estimate_first_downbeat', lambda *a, **k: pytest.fail('external vote not needed'))
    track = analysis.analyze_track(str(path))
    assert track.first_downbeat == 0. and track.downbeat_confidence == 1.
    assert track.phrases and track.beatgrid_source == 'rekordbox'
    importer.get_beatgrid.return_value = []
    monkeypatch.setattr(analysis, '_estimate_audio_downbeat', lambda *a, **k: (.7, .6))
    # Seit Cache 100 werden vorhandene Modellfenster auch bei starker Baseline
    # verglichen. Ein widersprechendes externes Votum erhält die Baseline.
    monkeypatch.setattr(analysis, 'estimate_first_downbeat', lambda *a, **k: (.7, .6))
    track = analysis.analyze_track(str(path))
    assert track.first_downbeat == .7


def _rekordbox_grid(rotation=0):
    return [
        {'time': .2 + index * .5, 'beat': ((index + rotation) % 4) + 1}
        for index in range(96)
    ]


@pytest.mark.parametrize('rotation', range(4))
def test_bar_position_comparator_reports_only_direct_rotation_candidates(rotation):
    beat_windows = windows()
    for window in beat_windows:
        for item in window['results']:
            for event in item['decoder']['beats']:
                event['position'] = (event['position'] - 1 + rotation) % 4 + 1

    comparison = analysis._compare_rekordbox_bar_positions(
        120., _rekordbox_grid(), beat_windows,
    )

    expected_status = 'aligned' if rotation == 0 else 'candidate_rotation'
    assert comparison['status'] == expected_status
    assert comparison['rotation_beats'] == rotation
    assert len(comparison['windows']) == 6
    assert all(row['status'] == 'measured' for row in comparison['windows'])
    assert all(row['max_time_error_ms'] <= 6. for row in comparison['windows'])


def test_bar_position_comparator_does_not_retime_or_fill_missing_direct_matches():
    beat_windows = windows()
    event = next(
        event for event in beat_windows[0]['results'][0]['decoder']['beats']
        if event['observed']
    )
    event['time_s'] += .007

    comparison = analysis._compare_rekordbox_bar_positions(
        120., _rekordbox_grid(), beat_windows,
    )

    assert comparison['status'] == 'unknown'
    assert comparison['rotation_beats'] is None
    assert any(row['status'] == 'time_mismatch' for row in comparison['windows'])


def test_verified_rekordbox_anchor_keeps_active_value_and_attaches_rotation_diagnosis(
        pipeline, monkeypatch):
    path, importer, _ = setup_adoption(pipeline, monkeypatch)
    # Nur die Taktübernahme prüfen; PSSI besitzt einen eigenen Phrasenanker.
    importer.get_phrases.return_value = []
    importer.get_beatgrid.return_value = _rekordbox_grid()
    monkeypatch.setattr(analysis, '_validate_track_beatgrid', lambda *a, **k:
                        analysis.BeatgridValidation('verified', 3, 0.))

    track = analysis.analyze_track(str(path))

    assert track.first_downbeat == pytest.approx(.2)
    assert track.beatgrid_source == 'rekordbox'
    comparison = track.measurement_diagnostics['anchor']['bar_position_comparison']
    assert comparison['status'] == 'aligned'
    assert comparison['rotation_beats'] == 0


def _setup_disjoint_rotation_confirmation(pipeline, monkeypatch):
    from hpg_core.downbeat import BeatgridWindowDiagnostic
    path, importer, _ = setup_adoption(pipeline, monkeypatch)
    importer.get_beatgrid.return_value = _rekordbox_grid(rotation=1)
    monkeypatch.setattr(analysis, '_get_file_duration', lambda *a: 96.)
    evidence = tuple(BeatgridWindowDiagnostic(start, 16., .2, .9, 0., 'measured', 0.)
                     for start in (0., 16., 32.))
    monkeypatch.setattr(analysis, '_validate_track_beatgrid', lambda *a, **k:
        analysis.BeatgridValidation('verified', 3, 0., 'verified', evidence, 'aligned', 0.))
    confirmation_starts = []
    def collect(*args, window_starts=None, retain_audio=False):
        result = windows()
        if window_starts is None:
            return result
        assert retain_audio
        assert len(window_starts) == 3
        for window, start in zip(result, window_starts):
            assert start >= 48. and start + 16. <= 96.
            shift = start - window['start_s']
            window['start_s'] = start
            for item in window['results']:
                item['decoder']['first_downbeat'] += shift
                for event in item['decoder']['beats']:
                    event['time_s'] += shift
            window['_audio'] = np.ones(16*44100, np.float32)
        confirmation_starts.extend(window_starts)
        return result
    monkeypatch.setattr(analysis, '_collect_beat_windows', collect)
    def validate(audio_windows, *args, **kwargs):
        assert [start for start, _ in audio_windows] == confirmation_starts
        assert kwargs['anchor'] == pytest.approx(.2)
        return analysis.BeatgridValidation('verified', 3, 0.)
    monkeypatch.setattr(analysis, 'validate_beatgrid_windows', validate)
    return path, confirmation_starts


def test_audio_confirmation_adopts_rotation_from_disjoint_windows(
        pipeline, monkeypatch):
    path, starts = _setup_disjoint_rotation_confirmation(pipeline, monkeypatch)

    track = analysis.analyze_track(str(path))

    comparison = track.measurement_diagnostics['anchor']['bar_position_comparison']
    assert comparison['status'] == 'candidate_rotation'
    assert comparison['rotation_beats'] == 3
    assert comparison['audio_confirmation']['status'] == 'audio_confirmed'
    assert comparison['audio_confirmation']['expected_anchor_s'] == pytest.approx(.2)
    assert len(comparison['audio_confirmation']['windows']) == 6
    assert len(starts) == 3
    assert track.first_downbeat == pytest.approx(.2)
    assert track.beatgrid_source == 'audio'


def test_one_weak_audio_vote_rejects_diagnostic_candidate_and_keeps_rb_anchor(
        pipeline, monkeypatch):
    path, _ = _setup_disjoint_rotation_confirmation(pipeline, monkeypatch)
    calls = []
    def vote(*args, **kwargs):
        calls.append(None)
        return .2, .1 if len(calls) == 6 else .6
    monkeypatch.setattr(analysis, 'estimate_first_downbeat', vote)

    track = analysis.analyze_track(str(path))

    comparison = track.measurement_diagnostics['anchor']['bar_position_comparison']
    confirmation = comparison['audio_confirmation']
    assert confirmation['status'] == 'rejected'
    assert confirmation['reason'] == 'weak_audio'
    assert len(confirmation['windows']) == 6
    assert sum(row['status'] == 'confirmed' for row in confirmation['windows']) == 5
    assert track.first_downbeat == pytest.approx(1.7)
    assert track.beatgrid_source == 'rekordbox'
    assert track.measurement_diagnostics['anchor']['neural']['reason'] == 'reference_preferred'


@pytest.mark.parametrize("fast", [True, False])
def test_high_phrase_confidence_baseline_reuses_phrase_both_paths(
        pipeline, monkeypatch, fast):
    path, importer, _ = setup_adoption(pipeline, monkeypatch, fast)
    importer.get_beatgrid.return_value = []
    phrase_calls = []
    monkeypatch.setattr(analysis, '_estimate_audio_downbeat', lambda *a, **k: (.2, .6))
    monkeypatch.setattr(analysis, '_validate_track_beatgrid', lambda *a, **k:
                        analysis.BeatgridValidation('verified', 3, 0.))
    monkeypatch.setattr(analysis, '_collect_beat_windows', lambda *a: [])
    monkeypatch.setattr(analysis, 'estimate_first_downbeat',
                        lambda *a, **k: pytest.fail('high-confidence phrase skips anchor voting'))
    monkeypatch.setattr(analysis, 'estimate_first_phrase',
                        lambda y, sr, bpm, anchor, unit:
                        (phrase_calls.append(anchor) or .47, .8))
    track = analysis.analyze_track(str(path))
    assert track is not None
    assert track.first_downbeat == pytest.approx(.2)
    assert track.first_phrase == pytest.approx(.47)
    assert track.phrase_confidence == pytest.approx(.8)
    assert phrase_calls == [pytest.approx(.2)]
    assert track.measurement_diagnostics['anchor']['neural']['reason'] == 'baseline_preferred'


@pytest.mark.parametrize("fast", [True, False])
def test_low_phrase_confidence_baseline_can_be_challenged_without_duplicate_phrase_work(
        pipeline, monkeypatch, fast):
    path, importer, phrases = setup_adoption(pipeline, monkeypatch, fast)
    importer.get_beatgrid.return_value = []
    phrase_calls = []
    monkeypatch.setattr(analysis, '_estimate_audio_downbeat', lambda *a, **k: (.2, .6))
    monkeypatch.setattr(analysis, '_validate_track_beatgrid', lambda *a, **k:
                        analysis.BeatgridValidation('verified', 3, 0.))
    def phrase(y, sr, bpm, anchor, unit):
        phrase_calls.append(anchor)
        phrases.append(anchor)
        return anchor, .1 if len(phrase_calls) == 1 else .8
    monkeypatch.setattr(analysis, 'estimate_first_phrase', phrase)
    track = analysis.analyze_track(str(path))
    assert track is not None
    # Neuronale Fenster stimmen mit .2 s überein; Baseline-Phrase-Konfidenz .1
    # erlaubt Prüfung, aber der finale Phrase-Schätzer wird nur einmal erneut gerufen.
    assert track.measurement_diagnostics['anchor']['neural']['reason'] == 'adopted'
    assert track.first_downbeat == pytest.approx(.2)
    assert phrase_calls == [pytest.approx(.2), pytest.approx(.2)]


@pytest.mark.parametrize("fast", [True, False])
def test_low_phrase_confidence_rejected_models_reuse_baseline_phrase(
        pipeline, monkeypatch, fast):
    path, importer, phrases = setup_adoption(pipeline, monkeypatch, fast)
    importer.get_beatgrid.return_value = []
    phrase_calls = []
    monkeypatch.setattr(analysis, '_estimate_audio_downbeat', lambda *a, **k: (.2, .6))
    monkeypatch.setattr(analysis, '_validate_track_beatgrid', lambda *a, **k:
                        analysis.BeatgridValidation('verified', 3, 0.))
    monkeypatch.setattr(analysis, '_collect_beat_windows', lambda *a: windows()[:1])
    def phrase(y, sr, bpm, anchor, unit):
        phrase_calls.append(anchor)
        phrases.append(anchor)
        return anchor + .01, .1
    monkeypatch.setattr(analysis, 'estimate_first_phrase', phrase)
    track = analysis.analyze_track(str(path))
    assert track is not None
    assert track.first_downbeat == pytest.approx(.2)
    assert track.measurement_diagnostics['anchor']['neural']['reason'] == 'insufficient_windows'
    assert phrase_calls == [pytest.approx(.2)]


def test_single_other_model_conflict_and_insufficient_evidence(pipeline, monkeypatch):
    path, _, _ = setup_adoption(pipeline, monkeypatch)
    candidate_windows = windows()
    for window in candidate_windows[1:]:
        window['results'][1].update(status='unavailable', decoder=None)
    # Ein belastbarer Widerspruch genügt, obwohl Modell 8 keine drei Fenster hat.
    for event in candidate_windows[0]['results'][1]['decoder']['beats']:
        event['position'] = event['position'] % 4 + 1
    monkeypatch.setattr(analysis, '_collect_beat_windows', lambda *a: candidate_windows)
    monkeypatch.setattr(analysis, 'estimate_first_downbeat', lambda *a, **k:
        (.7 if k['external_beats'][0]['position'] == 2 else .2, .6))
    track = analysis.analyze_track(str(path))
    assert track.first_downbeat == .7
    assert track.measurement_diagnostics['anchor']['neural']['reason'] == 'bar_conflict'
    monkeypatch.setattr(analysis, 'estimate_first_downbeat', lambda *a, **k: (.2, .2))
    track = analysis.analyze_track(str(path))
    assert track.first_downbeat == .7
    assert track.measurement_diagnostics['anchor']['neural']['reason'] == 'insufficient_evidence'


def test_local_errors_skip_cache_and_final_grid_fails_closed(pipeline, monkeypatch):
    path, _, _ = setup_adoption(pipeline, monkeypatch)
    writes = []
    monkeypatch.setattr(analysis, '_persist_analysis_result', lambda *a: writes.append(a) or True)
    def fail(*a, **k):
        raise RuntimeError('local verification failure')
    monkeypatch.setattr(analysis, 'estimate_first_downbeat', fail)
    track = analysis.analyze_track(str(path))
    assert track is not None and track.first_downbeat == .7 and writes == []
    assert track.measurement_diagnostics['anchor']['neural']['transient'] is True
    monkeypatch.setattr(analysis, 'estimate_first_downbeat', lambda *a, **k: (.2, .6))
    monkeypatch.setattr(analysis, '_validate_track_beatgrid', lambda *a, **k:
                        analysis.BeatgridValidation('mismatch', 3, 8., phase_pattern='variable_phase'))
    track = analysis.analyze_track(str(path))
    assert track.first_downbeat == .7 and len(writes) == 1
    assert track.measurement_diagnostics['anchor']['neural']['reason'] == 'final_grid_rejected'


@pytest.mark.parametrize("fast", [True, False])
def test_transient_deep_feature_failure_skips_cache(pipeline, monkeypatch, fast):
    path, _, _ = setup_adoption(pipeline, monkeypatch, fast=fast)
    writes = []
    monkeypatch.setattr(analysis, '_persist_analysis_result', lambda *a: writes.append(a) or True)

    def attach_unavailable(track):
        track.stem_analysis = {'status': 'unavailable'}
        track.embedding_analysis = {'status': 'disabled'}

    from hpg_core.ai_models import deep_features
    monkeypatch.setattr(deep_features, 'attach', attach_unavailable)
    track = analysis.analyze_track(str(path))

    assert track is not None
    assert track.stem_analysis['status'] == 'unavailable'
    assert writes == []


def test_external_reason_and_real_sample_offset(pipeline, monkeypatch):
    from hpg_core.measurement_contract import measurement_snapshot, validate_measurement_diagnostics
    path, _, _ = setup_adoption(pipeline, monkeypatch)
    sample_rate = 22050
    audio = np.arange(sample_rate*49, dtype=np.float32)
    candidate_windows = windows()
    # Modelloffset liegt absichtlich zwischen zwei DSP-Samples.
    for window in candidate_windows:
        window['start_s'] += 1/44100
        for item in window['results']:
            for event in item['decoder']['beats']:
                event['time_s'] += 1/44100
    calls = []
    def vote(y, sr, bpm, **kwargs):
        event = kwargs['external_beats'][0]
        calls.append((float(y[0]), event['time_s']))
        kwargs['diagnostics'].update(reason='external_vote_ambiguous', stage='voting')
        return 0., 0.
    monkeypatch.setattr(analysis, 'estimate_first_downbeat', vote)
    result = analysis._resolve_track_anchor(str(path), 49., 120., audio, sample_rate, [], candidate_windows)
    assert calls[2][0] == 16*sample_rate
    assert calls[2][1] == pytest.approx(.2+1/44100)
    snapshot = measurement_snapshot(result[4], result[3], anchor_decision=result[6])
    validate_measurement_diagnostics(snapshot)
    assert snapshot['anchor']['neural']['windows'][0]['downbeat']['reason'] == 'external_vote_ambiguous'


def test_native_acceptance_does_not_bypass_consistent_reference_offset_without_windows(
        monkeypatch):
    reference = {
        'anchor_s': .2,
        'measurement': {
            'grid': {
                'status': 'mismatch', 'phase_pattern': 'consistent_offset',
                'phase_center_ms': 12., 'decode_failures': [],
            },
            'downbeat': {},
        },
    }
    monkeypatch.setattr(analysis, '_reference_grid_attempt', lambda *a, **k: reference)
    monkeypatch.setattr(analysis, '_estimate_audio_downbeat', lambda *a, **k: (.7, .8))
    monkeypatch.setattr(analysis, '_validate_track_beatgrid', lambda *a, **k:
                        analysis.BeatgridValidation('verified', 3, 0.))
    native_context = {
        'accepted': True,
        'analysis': {'bpm': 120., 'first_downbeat': .2},
        'validation': analysis.BeatgridValidation('verified', 3, 0.),
        'diagnostics': {},
    }

    result = analysis._resolve_track_anchor(
        'unused', 48., 120., np.ones(48 * 100, np.float32), 100, [], [],
        native_context=native_context,
    )

    assert result[0] == pytest.approx(.7)
    assert result[2] == 'audio'
    assert result[6]['method'] == 'dsp'
    assert result[6]['reference'] is reference
    assert native_context['accepted'] is False
    assert native_context['decision'] == {
        'status': 'rejected', 'reason': 'reference_offset_unresolved'}


def test_native_bar_rotation_collects_model_candidate_windows_only_on_conflict(monkeypatch):
    bpm = 120.
    native_rows = [dict(pos=index * 22050, numBar=index % 4 + 1, bpm=12000)
                   for index in range(16)]
    rekordbox_grid = [dict(time=index * .5, beat=(index + 2) % 4 + 1)
                      for index in range(16)]
    native_context = {'analysis': {'grid': native_rows}}
    assert analysis._native_grid_rotation_candidate(
        rekordbox_grid, native_context, bpm
    )

    reference = {'measurement': {'grid': {
        'status': 'verified', 'phase_pattern': 'aligned',
    }}}
    monkeypatch.setattr(analysis, '_reference_grid_attempt', lambda *args, **kwargs: reference)
    expected_windows = [{'start_s': 4.0}, {'start_s': 20.0}, {'start_s': 36.0}]
    calls = []
    monkeypatch.setattr(analysis, '_collect_beat_windows',
                        lambda *args, **kwargs: calls.append(args[0]) or expected_windows)

    actual_reference, candidate_windows = analysis._native_reference_candidate_windows(
        'source.wav', 48., bpm, np.zeros(48 * 100, np.float32), 100,
        rekordbox_grid, bpm, 'exact', native_context,
    )

    assert actual_reference is reference
    assert candidate_windows is expected_windows
    assert calls == ['source.wav']

    aligned_grid = [dict(point, beat=native_rows[index]['numBar'])
                    for index, point in enumerate(rekordbox_grid)]
    aligned_context = {'analysis': {'grid': [
        dict(row, numBar=aligned_grid[index]['beat'])
        for index, row in enumerate(native_rows)
    ]}}
    assert not analysis._native_grid_rotation_candidate(aligned_grid, aligned_context, bpm)
    mixed_grid = [dict(point) for point in rekordbox_grid]
    mixed_grid[0]['beat'] = native_rows[0]['numBar']
    assert not analysis._native_grid_rotation_candidate(
        mixed_grid, native_context, bpm
    )
    _, aligned_windows = analysis._native_reference_candidate_windows(
        'source.wav', 48., bpm, np.zeros(48 * 100, np.float32), 100,
        aligned_grid, bpm, 'exact', aligned_context,
    )
    assert aligned_windows == []
    assert calls == ['source.wav']

    malformed_offset = {'measurement': {'grid': {
        'status': 'mismatch', 'phase_pattern': 'consistent_offset',
        'phase_center_ms': float('nan'),
    }}}
    monkeypatch.setattr(analysis, '_reference_grid_attempt',
                        lambda *args, **kwargs: malformed_offset)
    _, offset_windows = analysis._native_reference_candidate_windows(
        'source.wav', 48., bpm, np.zeros(48 * 100, np.float32), 100,
        rekordbox_grid, bpm, 'exact', native_context,
    )
    assert offset_windows == []
    assert calls == ['source.wav']


def test_six_disjoint_windows_can_confirm_audio_phase_against_model_labels(pipeline, monkeypatch):
    from hpg_core.measurement_contract import measurement_snapshot, validate_measurement_diagnostics
    path, _, _ = setup_adoption(pipeline, monkeypatch)
    sample_rate = 22050
    audio = np.arange(sample_rate*48, dtype=np.float32)
    candidate_windows = windows()
    calls = []

    def vote(window_audio, sr, bpm, **kwargs):
        assert kwargs['_allow_external_conflict_candidate'] is True
        start = float(window_audio[0]) / sr
        local_anchor = (0.2 - start) % (4 * 60. / bpm)
        calls.append((start, local_anchor))
        kwargs['diagnostics'].update(reason='external_vote_conflict', stage='result')
        return local_anchor, 0.8

    monkeypatch.setattr(analysis, 'estimate_first_downbeat', vote)
    result = analysis._resolve_track_anchor(
        str(path), 48., 120., audio, sample_rate, [], candidate_windows,
    )
    snapshot = measurement_snapshot(result[4], result[3], anchor_decision=result[6])
    validate_measurement_diagnostics(snapshot)
    assert len(calls) == 6
    assert result[0] == pytest.approx(0.2)
    assert result[6]['neural']['reason'] == 'adopted'
    assert all(window['downbeat']['reason'] == 'external_vote_conflict'
               for window in snapshot['anchor']['neural']['windows'])


def test_three_nonoverlapping_windows_and_tempo_gate(pipeline, monkeypatch):
    path, _, _ = setup_adoption(pipeline, monkeypatch)
    audio = np.ones(22050*48, np.float32)
    candidates = windows()[:2]
    result = analysis._resolve_track_anchor(str(path), 48., 120., audio, 22050, [], candidates)
    assert result[6]['neural']['reason'] == 'insufficient_windows'
    candidates = windows()
    for window in candidates:
        for item in window['results']:
            item['decoder']['bpm'] = 130.
    result = analysis._resolve_track_anchor(str(path), 48., 120., audio, 22050, [], candidates)
    assert all(w['reason'] == 'tempo_mismatch' for w in result[6]['neural']['windows'])


@pytest.mark.parametrize('fast', [True, False])
def test_neural_bpm_reaches_both_producers(pipeline, monkeypatch, fast):
    path, importer, _ = setup_adoption(pipeline, monkeypatch, fast)
    candidates = windows()
    for window in candidates:
        for item in window['results']:
            item['decoder']['bpm'] = 125.
    monkeypatch.setattr(analysis, '_collect_beat_windows', lambda *a: candidates)
    def refine(y, sr, bpm, **kwargs):
        if kwargs.get('diagnostics') is not None:
            kwargs['diagnostics']['reason'] = 'prior_verified'
        return bpm
    monkeypatch.setattr(analysis, '_refine_audio_tempo', refine)
    monkeypatch.setattr(analysis, '_beat_phase_from_fold', lambda *a: (.2, .8))
    def grid(path, duration, bpm, anchor, **kwargs):
        return analysis.BeatgridValidation('mismatch', 3, 8., phase_pattern='variable_phase') if kwargs.get('grid_points') else analysis.BeatgridValidation('verified', 3, 0.)
    monkeypatch.setattr(analysis, '_validate_track_beatgrid', grid)
    seen = []
    old_genre = analysis.classify_genre
    monkeypatch.setattr(analysis, 'classify_genre', lambda y, sr, bpm, *a, **k:
                        (seen.append(('genre', bpm)) or old_genre(y, sr, bpm, *a, **k)))
    old_structure = analysis.analyze_structure_windows
    monkeypatch.setattr(analysis, 'analyze_structure_windows', lambda path, y, sr, bpm, *a, **k:
                        (seen.append(('structure', bpm)) or old_structure(path, y, sr, bpm, *a, **k)))
    old_mix = analysis.calculate_genre_aware_mix_points
    monkeypatch.setattr(analysis, 'calculate_genre_aware_mix_points', lambda sections, bpm, *a, **k:
                        (seen.append(('mix', bpm)) or old_mix(sections, bpm, *a, **k)))
    for name in ('calculate_danceability', 'compute_groove_fields'):
        original = getattr(analysis, name)
        def capture(y, sr, bpm, *args, _name=name, _original=original, **kwargs):
            seen.append((_name, bpm))
            return _original(y, sr, bpm, *args, **kwargs)
        monkeypatch.setattr(analysis, name, capture)
    track = analysis.analyze_track(str(path))
    assert track is not None and track.bpm == 125.
    assert seen and all(bpm == 125. for _, bpm in seen)
    reference = track.measurement_diagnostics['anchor']['reference']
    assert reference['target_bpm'] == 120.
    assert reference['bpm'] == (120. if fast else None)
    assert reference['measurement']['grid']['status'] == 'mismatch'
    assert importer.get_track_data.return_value.bpm == (120. if fast else None)


def test_tempo_conflict_missing_window_and_verified_reference(pipeline, monkeypatch):
    path, _, _ = setup_adoption(pipeline, monkeypatch)
    audio = np.ones(22050*48, np.float32)
    candidates = windows()
    for window in candidates:
        for item in window['results']:
            item['decoder']['bpm'] = 125.
    calls = []
    monkeypatch.setattr(analysis, '_refine_audio_tempo', lambda *a, **k: calls.append(a) or 125.)
    candidates[2]['results'][1]['decoder']['bpm'] = 140.
    assert analysis._resolve_track_tempo(str(path),48.,120.,audio,22050,[],candidates)[0] == 120.
    candidates[2]['results'][1]['decoder']['bpm'] = 125.
    assert analysis._resolve_track_tempo(str(path),48.,120.,audio,22050,[],candidates[:2])[0] == 120.
    monkeypatch.setattr(analysis, '_validate_track_beatgrid', lambda *a, **k:
                        analysis.BeatgridValidation('verified',3,0.))
    result = analysis._resolve_track_tempo(str(path),48.,120.,audio,22050,
                                          [dict(time=0.,beat=1)],candidates,reference_bpm=120.)
    assert result[0] == 120. and result[1]['measurement']['grid']['status'] == 'verified'
    assert calls == []


def test_tempo_audio_failure_retains_baseline_and_is_transient(pipeline, monkeypatch):
    path, _, _ = setup_adoption(pipeline, monkeypatch)
    candidates = windows()
    for window in candidates:
        for item in window['results']:
            item['decoder']['bpm'] = 125.
    def fail(*args, **kwargs):
        raise RuntimeError('audio verifier failure')
    monkeypatch.setattr(analysis, '_refine_audio_tempo', fail)
    value, reference, transient, diagnostic = analysis._resolve_track_tempo(str(path),48.,120.,
        np.ones(22050*48,np.float32),22050,[],candidates)
    assert value == 120. and reference is None and transient is True


@pytest.mark.parametrize('reference_bpm', [None, 0., -120., float('nan'), float('inf'), True])
def test_unmeasured_reference_tempo_stays_unknown(monkeypatch, reference_bpm):
    monkeypatch.setattr(analysis, '_validate_track_beatgrid', lambda *a, **k:
                        analysis.BeatgridValidation('verified', 3, 0.))
    result = analysis._reference_grid_attempt('unused.wav', 48., 120.,
        np.ones(48), 1, [dict(beat=1, time=0.)], reference_bpm)
    assert result['bpm'] is None
    assert result['target_bpm'] == 120.
    assert result['measurement']['grid']['status'] == 'verified'
