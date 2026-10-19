import numpy as np
import pytest

from hpg_core import structure_analyzer as sa
from hpg_core.ai_models import cue_predictor


@pytest.fixture
def dsp(monkeypatch):
  monkeypatch.setattr(sa, '_compute_novelty_curve', lambda *a, **k: (np.ones(3), np.arange(3)))
  monkeypatch.setattr(sa, '_pick_boundaries', lambda *a, **k: [0., 5.])
  monkeypatch.setattr(sa, '_quantize_to_bars', lambda *a, **k: [0., 5.])
  monkeypatch.setattr(sa, '_compute_section_energy', lambda *a, **k: 40.)
  monkeypatch.setattr(sa, '_compute_energy_trend', lambda *a, **k: 0.)
  return np.ones(220500, dtype=np.float32)


def context(start=0):
  return dict(candidates=[{'start_s': start+5, 'kind': 1, 'mood': 2}],
              samplecnn_path='samplecnn', cue_model_path='cue', window_start_s=start,
              track_duration_s=100, verified_grid=True)


def analyze(audio, **kwargs):
  return sa.analyze_structure(audio, 22050, 120, phrase_unit=8, **kwargs)


@pytest.mark.parametrize('start', [0, 90])
def test_absolute_head_tail_and_unchanged_structure(dsp, monkeypatch, start):
  calls = []
  diagnostic = [{'index': 0, 'status': 'ok', 'raw_score': -.2}]
  def scorer(audio, sample_rate, candidates, **kwargs):
    calls.append((audio, sample_rate, candidates, kwargs))
    return diagnostic
  monkeypatch.setattr(cue_predictor, 'score_phrase_candidates', scorer)
  baseline = analyze(dsp)
  result = analyze(dsp, cue_context=context(start))
  assert result.sections == baseline.sections
  assert result.phrase_unit == baseline.phrase_unit
  assert result.total_bars == baseline.total_bars
  assert result.cue_diagnostics == diagnostic
  assert calls[0][0] is dsp
  assert calls[0][1] == 22050
  assert calls[0][2][0]['start_s'] == start+5
  assert calls[0][3]['window_start_s'] == start
  assert calls[0][3]['prefer_directml'] is True


def test_no_context_no_model(dsp, monkeypatch):
  monkeypatch.setattr(cue_predictor, 'score_phrase_candidates', lambda *a, **k: pytest.fail('Unexpected scorer'))
  assert analyze(dsp).cue_diagnostics == []
  a, b = sa.TrackStructure(), sa.TrackStructure()
  a.cue_diagnostics.append({})
  assert b.cue_diagnostics == []


def test_verified_cue_boundaries_take_precedence_over_native_fallback(dsp, monkeypatch):
  native_calls = []
  cue_intervals = []
  original = sa._apply_verified_phrase_boundaries
  original_apply = sa._apply_phrase_intervals
  def record_native(boundaries, phrase_context, duration):
    native_calls.append(phrase_context)
    return original(boundaries, phrase_context, duration)
  def record_cue(boundaries, intervals, duration):
    cue_intervals.append(intervals)
    return original_apply(boundaries, intervals, duration)
  monkeypatch.setattr(sa, '_apply_verified_phrase_boundaries', record_native)
  monkeypatch.setattr(sa, '_apply_phrase_intervals', record_cue)
  monkeypatch.setattr(cue_predictor, 'score_phrase_candidates',
                      lambda *a, **k: [{'index': 0, 'status': 'unavailable', 'raw_score': None}])
  pssi = dict(candidates=[dict(start_s=2., end_s=4., kind=1, mood=2)],
              samplecnn_path='samplecnn', cue_model_path='cue',
              window_start_s=0., track_duration_s=100., verified_grid=True)
  native = dict(candidates=[dict(start_s=6., end_s=8., kind=2, mood=2)],
                window_start_s=0., track_duration_s=100., verified_grid=True)
  analyze(dsp, cue_context=pssi, native_phrase_context=native)
  assert native_calls == []
  assert cue_intervals == [[(2., 4.)]]


def test_scorer_exception_preserves_dsp(dsp, monkeypatch):
  def bad(*a, **k):
    raise RuntimeError('probe')
  monkeypatch.setattr(cue_predictor, 'score_phrase_candidates', bad)
  baseline = analyze(dsp)
  ctx = context()
  ctx['candidates'] *= 2
  result = analyze(dsp, cue_context=ctx)
  assert result.sections == baseline.sections
  assert [d['index'] for d in result.cue_diagnostics] == [0, 1]
  assert all(d['raw_score'] is None and d['reason'] == 'cue_adapter_error:RuntimeError'
             and 'model_hashes' not in d for d in result.cue_diagnostics)


@pytest.mark.parametrize('ctx', [42, {}, {'candidates': None}, {'candidates': 'bad'}])
def test_invalid_context(dsp, ctx, caplog):
  result = analyze(dsp, cue_context=ctx)
  assert result.cue_diagnostics == [dict(index=None, status='invalid_input',
                                        reason='invalid_cue_context', raw_score=None)]
  assert 'Cue' in caplog.text


@pytest.mark.parametrize('verified', [False, None, 1])
def test_unverified_never_loads_models(dsp, monkeypatch, verified):
  monkeypatch.setattr(cue_predictor.onnx_engine, 'get_model', lambda *a, **k: pytest.fail('Unexpected model'))
  ctx = context()
  ctx['verified_grid'] = verified
  result = analyze(dsp, cue_context=ctx)
  assert result.cue_diagnostics[0]['reason'] == 'unverified_grid'


@pytest.mark.parametrize('audio,sr,bpm', [
  (np.array([]), 22050, 120), (np.ones(3), 0, 120), (np.ones(3), 22050, 0),
  (np.ones(3), 22050, np.nan), (np.ones(3), np.inf, 120),
  (np.array([np.nan]), 22050, 120), (None, 22050, 120),
])
def test_early_invalid_returns(audio, sr, bpm, monkeypatch):
  monkeypatch.setattr(cue_predictor, 'score_phrase_candidates', lambda *a, **k: pytest.fail('Unexpected scorer'))
  result = sa.analyze_structure(audio, sr, bpm, cue_context=context())
  assert result.sections == []
  assert result.cue_diagnostics == []
