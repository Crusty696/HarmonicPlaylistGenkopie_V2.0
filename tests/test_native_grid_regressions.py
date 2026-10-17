"""Native Rohgrenzen, getrennte Zeitkorrektur und Weitergabe an den Renderer."""
from copy import deepcopy
from types import SimpleNamespace
import math

import numpy as np
import pytest

from hpg_core import analysis, caching
from hpg_core.ai_models import native_beat_grid as grid, native_track_beats as native
from hpg_core.ai_models.native_beat_alignment import active_anchor, stable_model_window
from tests.test_native_track_beats import snapshot
from tests.test_cue_pipeline_integration import pipeline
from tests.test_neural_anchor_integration import setup_adoption


def aligned():
    data = snapshot()
    data['model_beats'] = [[r['pos']/44100, r['numBar']] for r in data['grid']]
    anchor = data['first_downbeat']
    def row(start, corrected):
        error = 0. if corrected else .01
        tick = min((r['pos']/44100 for r in data['grid']), key=lambda t: abs(t-start))
        return dict(offset_seconds=float(start), duration_seconds=8.,
                    phase_seconds=(tick-start+.01) % .5, fold_lock=.95, reason='measured',
                    signed_phase_error_ms=error*1000, phase_error_ms=abs(error)*1000)
    data['audio_alignment'] = dict(offset_seconds=.01,
        calibration=[row(t, False) for t in (0, 16, 32)],
        confirmation=[row(t, True) for t in (8, 24, 40)])
    return data


def test_raw_duplicate_reaches_refinement_without_changing_rows(monkeypatch):
    rows = [dict(index=i, bpm=bpm, pos=pos, msec=pos//44, numBar=i%4+1)
            for i, (pos, bpm) in enumerate([(100, -2147483648), (100, 13800), (19274, 13800)])]
    monkeypatch.setattr(grid, '_read_json', lambda _: rows)
    class Image:
        def function(self, address, *args):
            return (lambda *a: 13800.) if address == 0x1296a80 else (lambda *a: None)
    result, bpm = grid.convert(Image(), [[.01, 1], [.5, 2]], 100, refinement_input=True)
    assert result == rows and bpm == 138.
    with pytest.raises(grid.NativeContractError):
        grid.convert(Image(), [[.01, 1], [.5, 2]], 100)


@pytest.mark.parametrize('damage', ['overlap', 'shift', 'residual', 'model_gap', 'nan'])
def test_alignment_rejects_unconfirmed_or_corrupt_evidence(damage):
    data = aligned()
    native.validate_snapshot(data, duration=48.)
    correction = data['audio_alignment']
    if damage == 'overlap':
        correction['confirmation'][0]['offset_seconds'] = 0.
    elif damage == 'shift':
        correction['offset_seconds'] = .02
    elif damage == 'residual':
        correction['confirmation'][0]['phase_seconds'] += .007
    elif damage == 'model_gap':
        data['model_beats'] = [r for r in data['model_beats'] if not 9 < r[0] < 11]
    else:
        correction['confirmation'][0]['fold_lock'] = math.nan
    with pytest.raises(ValueError):
        native.validate_snapshot(data, duration=48.)


@pytest.mark.parametrize('fast', [True, False])
def test_corrected_native_producer_cache_and_render_contract(pipeline, monkeypatch, fast):
    path, _, _ = setup_adoption(pipeline, monkeypatch, fast)
    data = aligned()
    original = deepcopy(data['grid'])
    context = dict(analysis=data, accepted=True, transient=False,
        validation=analysis.BeatgridValidation('verified', 3, .2, 'verified'),
        diagnostics={'decode_failures': []})
    monkeypatch.setattr(analysis, '_prepare_native_beats', lambda *a: context)
    monkeypatch.setattr(analysis, '_collect_beat_windows', lambda *a: pytest.fail('Model rerun'))
    track = analysis.analyze_track(str(path))
    assert track is not None and track.first_downbeat == active_anchor(data)
    assert track.native_beat_analysis['grid'] == original
    assert track.measurement_diagnostics['anchor']['method'] == 'native_rekordbox_audio_offset'
    restored = caching.dict_to_track(caching.track_to_dict(track))
    assert restored.first_downbeat == track.first_downbeat
    from hpg_core.transition_renderer import TransitionClipSpec
    plan = SimpleNamespace(mix_out_a=20., mix_in_b=4., overlap=8.,
        transition_type='pro_eq_swap', target_sr=44100, tempo_ratio=1.)
    spec = TransitionClipSpec.from_plan(plan, track, restored)
    assert spec.downbeat_reliable_a and spec.bar_phase_reliable_a and spec.bar_phase_reliable_b
    assert spec.strict_beat_sync
    restored.first_downbeat += .1
    assert not TransitionClipSpec.from_plan(plan, restored, track).bar_phase_reliable_a


def test_confirmation_selection_does_not_use_audio_residual():
    data = aligned()
    assert stable_model_window(data, 8., 8.)
    data['model_beats'] = [r for r in data['model_beats'] if not 9 < r[0] < 11]
    assert not stable_model_window(data, 8., 8.)


def test_native_break_is_excluded_before_expensive_render():
    from hpg_core.pair_candidates import _native_blend_supported
    data = aligned()
    track = SimpleNamespace(native_beat_analysis=data)
    assert _native_blend_supported(track, 8., 8.)
    data['model_beats'] = [r for r in data['model_beats'] if not 9 < r[0] < 11]
    assert not _native_blend_supported(track, 8., 8.)
    assert _native_blend_supported(track, 24., 8.)


def test_legacy_candidate_without_native_measurement_keeps_contract():
    from hpg_core.pair_candidates import _native_blend_supported
    assert _native_blend_supported(SimpleNamespace(native_beat_analysis={}), 8., 8.)


def test_native_blends_include_existing_minimum_without_changing_genre():
    from tests.test_pair_candidates import _track, _out
    from hpg_core.pair_candidates import blend_bars_options
    from hpg_core.config import MIN_TRANSITION_BARS
    track = _track()
    original = blend_bars_options(track, _out(120.), 'direct')
    track.native_beat_analysis = {'status': 'ok'}
    choices = blend_bars_options(track, _out(120.), 'direct')
    assert all(value in choices for value in original)
    assert MIN_TRANSITION_BARS in choices
    assert min(choices) >= MIN_TRANSITION_BARS


@pytest.mark.parametrize('rounding_samples', [2, 40, -2])
def test_millisecond_rounding_does_not_insert_a_whole_bar(rounding_samples):
    from hpg_core.transition_renderer import _align_beat_phase
    sr, bpm = 44100, 138.
    lead = round(240./bpm*sr)
    audio = np.arange(lead*3, dtype=float)[:, None]
    result = _align_beat_phase(audio, audio, bpm, sr,
        known_first_beat_a=0., known_first_beat_b=rounding_samples/sr,
        lead_frames=lead, bar_aligned=True)
    assert result[0, 0] == lead
    assert len(result) == len(audio)-lead


@pytest.mark.parametrize('damage', [None, 'delay', 'silence', 'local_delay'])
def test_native_reference_renderer_keeps_six_ms_gate(damage):
    from hpg_core.transition_renderer import _synchronize_and_verify_kicks, BeatSyncError
    sr, bpm = 8000, 120.
    t = np.arange(int(sr*.15))/sr
    kick = np.sin(2*np.pi*65*t)*np.exp(-35*t)
    a, b = np.zeros(sr*12), np.zeros(sr*12)
    for beat in np.arange(.25, 11.5, .5):
        first = round(beat*sr)
        second = first + (200 if damage == 'delay' or damage == 'local_delay' and 4 <= beat < 6 else 0)
        a[first:first+len(kick)] += kick
        if damage != 'silence':
            b[second:second+len(kick)] += kick
    a, b = np.column_stack((a,a)), np.column_stack((b,b))
    if damage:
        with pytest.raises(BeatSyncError):
            _synchronize_and_verify_kicks(a,b,sr,bpm,len(a),reference_phases=(.25,.25))
    else:
        np.testing.assert_allclose(_synchronize_and_verify_kicks(a,b,sr,bpm,len(a),
            reference_phases=(.25,.25)), b)


def test_native_beat_worker_reports_python_contract_failure_without_native_crash(monkeypatch):
    import importlib, json
    worker = importlib.import_module('hpg_core.ai_models.native_beat_pipeline_worker')
    def invalid(payload):
        raise ValueError('invalid contract')
    monkeypatch.setattr(worker, '_handle', invalid)
    assert json.loads(worker.handle(b'{}')) == dict(status='unavailable', reason='ValueError: invalid contract')


def test_native_segment_average_tempo_accepts_variable_grid_periods():
    from hpg_core.ai_models.native_beat_pipeline_worker import _average_grid_bpm

    grid = []
    position = 0
    for index in range(120):
        grid.append(dict(pos=position, numBar=index % 4 + 1))
        position += round((.60 - .00035 * index) * 44100)

    bpm = _average_grid_bpm(grid)

    assert 95.0 < bpm < 115.0
