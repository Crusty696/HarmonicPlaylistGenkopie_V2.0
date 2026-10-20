"""Native Roh-Nahtpaare bleiben für die originale Grenzkorrektur erhalten."""
import numpy as np
import pytest

from hpg_core.ai_models.native_beat_pipeline_worker import validate_model_rows
from hpg_core.ai_models.native_phrase_worker import NativeContractError


@pytest.mark.parametrize("left,right", [
    (120., 120.), (240.00001525878906, 240.), (300., 300.),
])
def test_model7_retains_observed_raw_seam_pairs(left, right):
    rows = np.array([[left, 4], [right, 3]], dtype=np.float32)
    assert validate_model_rows(rows, 600 * 44100, chunked=True) == rows.tolist()
    with pytest.raises(NativeContractError):
        validate_model_rows(rows, 600 * 44100)


@pytest.mark.parametrize("left,right", [
    (120.01, 120.), (121., 121.), (119.9, 119.8), (0., 0.),
])
def test_model7_still_rejects_other_ordering_errors(left, right):
    rows = np.array([[left, 4], [right, 3]], dtype=np.float32)
    with pytest.raises(NativeContractError):
        validate_model_rows(rows, 600 * 44100, chunked=True)
