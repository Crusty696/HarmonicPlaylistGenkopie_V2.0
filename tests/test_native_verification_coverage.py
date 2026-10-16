"""Zusätzliche Modellbelege erweitern Abdeckung, niemals die Synchrontoleranz."""
from copy import deepcopy
import pytest
from tests.test_native_track_beats import snapshot
from hpg_core.ai_models import native_track_beats as native
from hpg_core.ai_models.native_beat_alignment import single_window_evidence_plan


def evidence():
    data = snapshot(240.)
    data['verification'] = dict(model_id='model7',
        model_hashes=deepcopy(native.MODEL_HASHES['model7']),
        coverage=dict(start_s=0., end_s=(data['frames']-1)/44100),
        beats=[[row['pos']/44100, row['numBar']] for row in data['grid']])
    return data


def test_full_evidence_keeps_six_observed_disjoint_windows():
    data = evidence()
    native.validate_snapshot(data, duration=240.)
    calibration, confirmation = single_window_evidence_plan(data, 240., 16.)
    starts = sorted(calibration+confirmation)
    assert len(starts) == 6
    assert all(b-a >= 16 for a,b in zip(starts,starts[1:]))
    data['verification']['beats'] = []
    assert single_window_evidence_plan(data, 240., 16.) is None


@pytest.mark.parametrize('damage', ['hash', 'coverage', 'order'])
def test_rejects_forged_additional_model_evidence(damage):
    data = evidence()
    if damage == 'hash':
        data['verification']['model_hashes'] = {}
    elif damage == 'coverage':
        data['verification']['coverage']['end_s'] = 60.
    else:
        data['verification']['beats'][1][0] = 0.
    with pytest.raises(ValueError):
        native.validate_snapshot(data, duration=240.)
