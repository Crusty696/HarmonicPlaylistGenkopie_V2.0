"""Native Gesamtgrid-Übernahme und Sperren; keine Modelle oder Originalmusik."""
from copy import deepcopy

import numpy as np
import pytest

from hpg_core import analysis, caching
from hpg_core.ai_models.native_beat_selection import (
    native_track_job_timeout_seconds, select_model,
)
from hpg_core.ai_models import native_track_beats as native
from tests.test_cue_pipeline_integration import pipeline
from tests.test_neural_anchor_integration import setup_adoption


@pytest.mark.parametrize('duration,expected', [
    (1., 180.), (600., 180.), (3600., 270.), (7200., 420.),
])
def test_native_job_timeout_scales_to_reader_limit(duration, expected):
    assert native_track_job_timeout_seconds(duration) == expected


@pytest.mark.parametrize('duration', [0., -1., 7200.1, float('nan'), float('inf')])
def test_native_job_timeout_rejects_invalid_duration(duration):
    with pytest.raises(ValueError):
        native_track_job_timeout_seconds(duration)


def test_mp3_reader_provenance_accepts_lossy_duration_and_unknown_pcm_depth():
    data = snapshot(48.2)
    data['input_convention'] = 'rekordbox-builtin-mp3-planar-float32'
    data['reader'].update(backend='rekordbox-builtin-mp3', source_bit_depth=0)
    native.validate_snapshot(data, duration=48.2)


def snapshot(duration=48.):
    return dict(status='ok', reason=None, contract=native.CONTRACT,
        executable_sha256=native.SHA256, tensorflow_sha256=native.TF_SHA256,
        model_id='model7', model_hashes=deepcopy(native.MODEL_HASHES['model7']),
        source_identity=[100, 200, 1, 2, 3], sample_rate=44100, frames=int(duration*44100),
        bpm=120., grid=[dict(pos=round((.005+i*.5)*44100), numBar=i%4+1, bpm=12000)
                       for i in range(int(duration*2))],
        first_downbeat=round(.005*44100)/44100, musically_verified=False,
        input_convention='rekordbox-builtin-planar-float32',
        selection=select_model(4), boundary_contract=native.BOUNDARY_CONTRACT,
        model_coverage=dict(start_s=0., end_s=duration-1/44100),
        reader=dict(contract=native.READER_CONTRACT, source_sample_rate=44100,
            source_channels=2, output_channels=2, source_bit_depth=16, source_frames=int(duration*44100),
            output_sample_rate=44100, output_frames=int(duration*44100),
            backend='rekordbox-builtin'))


@pytest.mark.parametrize('fast', [True, False])
def test_both_producers_use_native_grid_without_window_rerun(pipeline, monkeypatch, fast):
    path, importer, phrases = setup_adoption(pipeline, monkeypatch, fast)
    data = snapshot()
    context = dict(analysis=data, accepted=True, transient=False,
        validation=analysis.BeatgridValidation('verified', 3, 1., 'verified'),
        diagnostics={'decode_failures': []})
    monkeypatch.setattr(analysis, '_prepare_native_beats', lambda *a: context)
    from tests.test_neural_anchor_integration import windows
    evidence = windows()
    for window in evidence:
        for result in window['results']:
            decoder = result['decoder']
            decoder['first_downbeat'] += data['first_downbeat'] - .2
            for event in decoder['beats']:
                event['time_s'] += data['first_downbeat'] - .2
    monkeypatch.setattr(analysis, '_reference_grid_attempt', lambda *a, **k: None)
    monkeypatch.setattr(analysis, '_native_reference_candidate_windows',
                        lambda *a, **k: (None, evidence))
    monkeypatch.setattr(analysis, 'estimate_first_downbeat',
                        lambda *a, **k: pytest.fail('Redundant bar confirmation'))
    monkeypatch.setattr(analysis, '_validate_track_beatgrid',
                        lambda *a, **k: analysis.BeatgridValidation('verified', 3, 1.))
    monkeypatch.setattr(analysis, '_collect_beat_windows', lambda *a: pytest.fail('Redundant model windows'))
    monkeypatch.setattr(analysis, '_resolve_track_tempo', lambda *a, **k: pytest.fail('Native tempo overwritten'))
    track = analysis.analyze_track(str(path))
    assert track is not None
    assert track.first_downbeat == data['first_downbeat']
    assert track.bpm == data['bpm']
    assert track.native_beat_analysis == data
    assert track.measurement_diagnostics['anchor']['method'] == 'native_rekordbox'
    assert track.neural_analysis['beat_windows'] == evidence
    assert track.downbeat_confidence == 0.
    assert track.bar_position_status == 'native_candidate'
    assert track.phrase_anchor is not None
    assert track.reference_bar_position_verified is False
    assert track.measurement_diagnostics['anchor']['neural']['windows'] == []
    assert track.phrases == []  # Native Herkunft darf kein importiertes PSSI vortäuschen.
    serialized = caching.track_to_dict(track)
    restored = caching.dict_to_track(serialized)
    assert restored.native_beat_analysis == data
    forged = caching.track_to_dict(track)
    forged['first_downbeat'] += .5
    with pytest.raises(caching.CacheValidationError):
        caching.dict_to_track(forged)
    serialized['native_beat_analysis']['first_downbeat'] += .1
    with pytest.raises(caching.CacheValidationError):
        caching.dict_to_track(serialized)


@pytest.mark.parametrize('damage', ['bar_rotation', 'missing_window'])
def test_native_position_keeps_unconfirmed_status_despite_model_disagreement(monkeypatch, damage):
    from tests.test_neural_anchor_integration import windows
    data = snapshot()
    evidence = windows()
    if damage == 'missing_window':
        evidence.pop()
    context = dict(analysis=data, accepted=True,
        validation=analysis.BeatgridValidation('verified', 3, 1.), diagnostics={})
    monkeypatch.setattr(analysis, '_reference_grid_attempt', lambda *a, **k: None)
    monkeypatch.setattr(analysis, '_validate_track_beatgrid',
                        lambda *a, **k: analysis.BeatgridValidation('verified', 3, 1.))
    estimate = data['first_downbeat'] + (.5 if damage == 'bar_rotation' else 0.)
    monkeypatch.setattr(analysis, 'estimate_first_downbeat', lambda *a, **k: (estimate, .6))
    result = analysis._resolve_track_anchor(
        'unused', 48., 120., np.ones(4800, np.float32), 100, [], evidence,
        native_context=context)
    assert result[0] == data['first_downbeat']
    assert result[1] == 0.
    assert result[6]['method'] == 'native_rekordbox'
    assert result[6]['neural']['windows'] == []


@pytest.mark.parametrize('status,accepted', [('verified', True), ('mismatch', False)])
def test_native_grid_does_not_bypass_audio_gate(monkeypatch, status, accepted):
    monkeypatch.setenv('HPG_NATIVE_BEAT', '1')
    monkeypatch.setattr(native, 'analyze', lambda *a, **k: snapshot())
    monkeypatch.setattr(analysis, '_validate_track_beatgrid', lambda *a, **k:
        analysis.BeatgridValidation(status, 3, 1. if accepted else 10.6))
    result = analysis._prepare_native_beats('unused.wav', 48., np.ones(32), 44100)
    assert result['accepted'] is accepted
    assert result['analysis']['musically_verified'] is False


def test_native_variable_grid_is_not_silently_straightened(monkeypatch):
    monkeypatch.setenv('HPG_NATIVE_BEAT', '1')
    data = snapshot()
    data['grid'][20]['pos'] += 4410
    monkeypatch.setattr(native, 'analyze', lambda *a, **k: data)
    monkeypatch.setattr(analysis, '_validate_track_beatgrid', lambda *a, **k: pytest.fail('Unsupported geometry'))
    assert not analysis._prepare_native_beats('unused.wav', 48., np.ones(32), 44100)['accepted']


def test_native_snapshot_duration_mismatch_uses_analysis_fallback(monkeypatch):
    from contextlib import nullcontext
    monkeypatch.setenv('HPG_NATIVE_BEAT', '1')
    monkeypatch.setattr(analysis.cue_service, 'session', lambda: nullcontext(None))
    monkeypatch.setattr(native, 'analyze', lambda *a, **k: snapshot(48.2))

    context = analysis._prepare_native_beats('unused.wav', 48., np.ones(32), 44100)

    assert context['accepted'] is False
    assert context['transient'] is False
    assert context['analysis'] == dict(
        status='unavailable', reason='native_path_unavailable:ValueError')
    assert context['decision']['reason'] == 'native_path_unavailable:ValueError'


def test_native_service_start_failure_uses_analysis_fallback(monkeypatch):
    from contextlib import contextmanager

    @contextmanager
    def broken_session():
        raise RuntimeError('service unavailable')
        yield None

    monkeypatch.setenv('HPG_NATIVE_BEAT', '1')
    monkeypatch.setattr(analysis.cue_service, 'session', broken_session)

    context = analysis._prepare_native_beats('unused.wav', 48., np.ones(32), 44100)

    assert context['accepted'] is False
    assert context['transient'] is True
    assert context['analysis'] == dict(
        status='unavailable', reason='native_path_unavailable:RuntimeError')


@pytest.mark.parametrize('field,value', [('executable_sha256', '0'*64),
    ('tensorflow_sha256', '0'*64), ('frames', 44100), ('musically_verified', True),
    ('first_downbeat', True), ('bpm', float('nan'))])
def test_rejects_corrupt_native_provenance(field, value):
    data = snapshot()
    data[field] = value
    with pytest.raises(ValueError):
        native.validate_snapshot(data, duration=48.)


def test_single_model_window_keeps_six_audio_windows_disjoint():
    from hpg_core.ai_models.native_beat_alignment import single_window_evidence_plan
    data = dict(bpm=120., selection=select_model(3),
                model_coverage=dict(start_s=30., end_s=90.),
                model_beats=[[30.+i*.5, i%4+1] for i in range(121)])
    calibration, confirmation = single_window_evidence_plan(data, 240., 16.)
    assert len(calibration) == len(confirmation) == 3
    assert all(30. <= start and start+16. <= 90. for start in confirmation)
    assert all(start+16. <= 30. or start >= 90. for start in calibration)
    starts = sorted(calibration+confirmation)
    assert all(b-a >= 16. for a, b in zip(starts, starts[1:]))
    assert single_window_evidence_plan(data, 80., 16.) is None
    data['model_beats'] = []
    assert single_window_evidence_plan(data, 240., 16.) is None
