"""Hohe DSP-Phrasenkonfidenz darf vorhandene Modellbelege nicht uebergehen."""
import numpy as np
import pytest
from hpg_core import analysis
from tests.test_neural_anchor_integration import windows


@pytest.mark.parametrize('contradictory', [False, True])
def test_available_model_positions_are_checked_despite_strong_baseline(monkeypatch, contradictory):
    monkeypatch.setattr(analysis, '_reference_grid_attempt', lambda *a, **k: None)
    monkeypatch.setattr(analysis, '_estimate_audio_downbeat', lambda *a, **k: (.7, .8))
    monkeypatch.setattr(analysis, '_validate_track_beatgrid',
                        lambda *a, **k: analysis.BeatgridValidation('verified', 3, 0.))
    monkeypatch.setattr(analysis, 'estimate_first_phrase', lambda *a, **k: (.7, .9))
    calls = []
    def vote(*args, **kwargs):
        calls.append(kwargs['external_beats'])
        return (.7 if contradictory and len(calls) == 2 else .2), .6
    monkeypatch.setattr(analysis, 'estimate_first_downbeat', vote)
    result = analysis._resolve_track_anchor('unused', 48., 120.,
        np.ones(48 * 100, np.float32), 100, [], windows(), phrase_unit=16)
    assert len(calls) == 6
    if contradictory:
        assert result[0] == .7
        assert result[6]['neural']['reason'] == 'bar_conflict'
    else:
        assert result[0] == pytest.approx(.2)
        assert result[6]['neural']['reason'] == 'adopted'
