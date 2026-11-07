"""Verträge der getrennten Fachmodule und ihrer kompatiblen Fassaden."""

import importlib.util
import pickle

import pytest


@pytest.mark.parametrize("module", [
    "hpg_core.scoring_primitives", "hpg_core.playlist_results",
    "hpg_core.set_timeline",
])
def test_fachmodule_sind_eigenstaendig_importierbar(module):
    assert importlib.util.find_spec(module) is not None


def test_result_fassade_bewahrt_typidentitaet_und_pickle():
    from hpg_core import playlist
    assert importlib.util.find_spec("hpg_core.playlist_results") is not None
    from hpg_core import playlist_results
    plan = playlist.TransitionPlan(64.0, 32.0, 64.0, 80.0, 16.0, "pro_eq_swap")
    assert playlist.TransitionPlan is playlist_results.TransitionPlan
    assert pickle.loads(pickle.dumps(plan)) == plan


def test_scoring_fassade_bewahrt_fehlende_faktoren():
    from hpg_core import playlist
    assert importlib.util.find_spec("hpg_core.scoring_primitives") is not None
    from hpg_core.scoring_primitives import combine_weighted
    assert playlist.combine_weighted is combine_weighted
    assert combine_weighted({"a": 0.75, "b": None}, {"a": 0.2, "b": 0.8}) == pytest.approx(0.75)
    assert combine_weighted({"a": None}, {"a": 1.0}) == 0.0
    assert combine_weighted({"a": 1.0}, {"a": 0.0}) == 0.0
