"""Nativer Adaptervertrag; keine Musik-, Modell- oder EXE-Wiederholung."""
import ctypes
import numpy as np
import pytest
from hpg_core.ai_models import native_beat_decoder as bd
from hpg_core.ai_models.native_beat_worker import FloatMatrix, IntVector


@pytest.fixture
def native(monkeypatch):
    values = np.full((1000, 2), .001, np.float32)
    rows = []
    for index, frame in enumerate(range(13, 1000, 50)):
        position = (index + 2) % 4 + 1
        values[frame, 1 if position == 1 else 0] = .97
        rows.append([frame / 100., position])
    monkeypatch.setattr(bd, 'decode', lambda _: {'bpm': 120., 'grid': [
        {'pos': round(stamp*44100), 'numBar': position} for stamp, position in rows]})
    return values, rows


def test_native_times_and_positions_are_not_rotated(native):
    values, rows = native
    result = bd.decode_beat_activations(values, duration_s=10.)
    assert result['status'] == 'ok'
    assert [[b['time_s'], b['position']] for b in result['beats']] == rows
    assert result['first_downbeat'] == 1.13
    assert not {'selected_bar_rotation', 'path_log_likelihood', 'conditional_bar_log_scores'} & result.keys()
    assert result['verified'] is False
    bd.validate_decoder(result, {'start_s': 0., 'duration_s': 10.})


def test_weak_native_peak_is_not_declared_observed(native):
    values, _ = native
    values[13] = .001
    result = bd.decode_beat_activations(values, duration_s=10.)
    assert result['beats'][0]['observed'] is False
    assert result['beats'][0]['position'] == 3


def test_peak_in_adjacent_model_frame_is_still_observed(native):
    values, _ = native
    values[14] = values[13].copy()
    values[13] = .001
    result = bd.decode_beat_activations(values, duration_s=10.)
    assert result['beats'][0]['observed'] is True


@pytest.mark.parametrize('field,value', [
    ('first_downbeat', True), ('selected_bar_rotation', 0),
    ('path_log_likelihood', -1.), ('verified', True),
    ('algorithm_version', 'hpg-4-4-sparse-viterbi-v1'),
])
def test_rejects_false_native_provenance(native, field, value):
    result = bd.decode_beat_activations(native[0], duration_s=10.)
    result[field] = value
    with pytest.raises(ValueError):
        bd.validate_decoder(result, {'start_s': 0., 'duration_s': 10.})


def test_native_matrix_abi_matches_callsite():
    assert ctypes.sizeof(FloatMatrix) == 40
    assert FloatMatrix.rows.offset == 4
    assert FloatMatrix.columns.offset == 8
    assert FloatMatrix.data.offset == 24
    assert FloatMatrix.owns_data.offset == 32
    assert ctypes.sizeof(IntVector) == 24
