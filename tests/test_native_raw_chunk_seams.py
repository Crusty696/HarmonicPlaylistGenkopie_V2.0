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


@pytest.mark.parametrize("field", ["model_beats", "verification"])
def test_raw_seams_never_relax_corrected_grid_validation(field):
    from hpg_core.ai_models import native_track_beats as native
    from tests.test_native_track_beats import snapshot

    data = snapshot(180.)
    rows = [[119.5, 3], [120., 4], [120., 3], [120.5, 4]]
    if field == "model_beats":
        data[field] = rows
    else:
        from hpg_core.ai_models.native_beat_selection import select_model
        data.update(model_id="model8", model_hashes=native.MODEL_HASHES["model8"],
                    selection=select_model(3), model_coverage=dict(start_s=0., end_s=60.),
                    model_beats=[[.5, 1], [1., 2], [1.5, 3], [2., 4]])
        data[field] = dict(model_id="model7", model_hashes=native.MODEL_HASHES["model7"],
                           beats=data["model_beats"] + rows,
                           coverage=dict(start_s=0., end_s=180. - 1 / 44100))
    native.validate_snapshot(data, duration=180.)
    data["grid"][2]["pos"] = data["grid"][1]["pos"]
    with pytest.raises(ValueError):
        native.validate_snapshot(data, duration=180.)
