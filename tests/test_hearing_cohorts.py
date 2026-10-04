"""Metadaten-Kohorten: kein Decoder und keine Originaldateien."""
from dataclasses import replace
import os

import pytest

from hpg_core.collection_index import CollectionEntry, CollectionIndex
from hpg_core.hearing_cohorts import CohortContext, CohortFeature, select_cohort
from hpg_core.config import SECURITY_MAX_PLAYLIST_SIZE


@pytest.fixture
def inventory(tmp_path):
    root = str(tmp_path / "music")
    return CollectionIndex((root,), tuple(
        CollectionEntry(os.path.join(root, f"{i:04}.mp3"), 10, 20, "new")
        for i in range(2500)))


def test_entire_pool_and_order_independence(inventory):
    context = CohortContext("cache", "build")
    result = select_cohort(inventory, count=40, seed=12, context=context)
    assert len(result.paths) == 40
    assert any(int(os.path.basename(path)[:4]) >= 1000 for path in result.paths)
    assert result == select_cohort(replace(inventory, entries=inventory.entries[::-1]),
                                  count=40, seed=12, context=context)
    assert result.total_entries == result.missing_entries + result.eligible_entries
    assert result.eligible_entries == len(result.paths) + result.unselected_entries


def test_binding_and_previous_tampering(inventory):
    context = CohortContext("cache", "build")
    result = select_cohort(inventory, count=2, seed=1, context=context)
    assert select_cohort(inventory, count=2, seed=1, context=context,
                         previous=result).selection_reused
    changed = replace(inventory, entries=(replace(inventory.entries[0], size=99),) + inventory.entries[1:])
    assert not select_cohort(changed, count=2, seed=1, context=context,
                             previous=result).selection_reused
    with pytest.raises(ValueError):
        select_cohort(inventory, count=2, seed=1, context=context,
                      previous=replace(result, paths=result.paths[::-1]))


@pytest.mark.parametrize("count,seed", [(True, 1), (1., 1), (0, 1),
    (SECURITY_MAX_PLAYLIST_SIZE + 1, 1), (1, True), (1, 1.)])
def test_strict_options(inventory, count, seed):
    with pytest.raises(ValueError):
        select_cohort(inventory, count=count, seed=seed, context=CohortContext())


@pytest.mark.parametrize("change", ["cancel", "errors", "duplicate", "outside", "negative", "status", "nul"])
def test_invalid_inventory(inventory, change):
    if change == "cancel":
        inventory = replace(inventory, cancelled=True)
    elif change == "errors":
        inventory = replace(inventory, errors=("unknown",))
    elif change == "duplicate":
        inventory = replace(inventory, entries=inventory.entries[:1] * 2)
    else:
        changes = {"outside": {"path": os.path.abspath("outside.mp3")},
                   "negative": {"mtime_ns": -1}, "status": {"status": "guessed"},
                   "nul": {"path": inventory.entries[0].path + "\x00"}}[change]
        inventory = replace(inventory, entries=(replace(inventory.entries[0], **changes),))
    with pytest.raises(ValueError):
        select_cohort(inventory, count=1, seed=1, context=CohortContext())


def test_stale_features_not_stale_tracks_and_band_edges(inventory):
    context = CohortContext("cache", "build")
    entries = tuple(replace(e, status="changed" if i == 0 else "new")
                    for i, e in enumerate(inventory.entries[:6]))
    entries += (replace(inventory.entries[6], status="missing"),)
    inventory = replace(inventory, entries=entries)
    features = tuple(CohortFeature(e.path, e.size, e.mtime_ns, context, "Techno",
                                  120. if i < 3 else 130., (0., .25, .5, .75, 1., .1)[i], "verified")
                     for i, e in enumerate(entries[:6]))
    features = (replace(features[0], size=11),) + features[1:]
    result = select_cohort(inventory, count=10, seed=3, context=context, features=features)
    assert entries[0].path in result.paths and entries[-1].path not in result.paths
    assert result.stale_feature_records == 1 and result.unknown_feature_entries == 1
    assert result.shortfall == 4 and result.missing_entries == 1
    groups = {group for group, _, _ in result.strata}
    assert ("Techno", "12", "1", "verified") in groups
    assert ("Techno", "12", "2", "verified") in groups
    assert ("Techno", "13", "3", "verified") in groups
    assert select_cohort(inventory, count=10, seed=3, context=context, features=features[::-1]) == result


@pytest.mark.parametrize("field,bad", [("size", True), ("bpm", 0), ("bpm", True),
    ("bpm", float("inf")), ("energy", float("nan")), ("energy", 1.01),
    ("genre", ""), ("beatgrid_status", "guessed")])
def test_invalid_features(inventory, field, bad):
    e = inventory.entries[0]
    feature = CohortFeature(e.path, e.size, e.mtime_ns, CohortContext("c", "b"))
    with pytest.raises(ValueError):
        select_cohort(inventory, count=1, seed=1, context=feature.context,
                      features=(replace(feature, **{field: bad}),))


def test_duplicate_features_and_incomplete_binding(inventory):
    e = inventory.entries[0]
    feature = CohortFeature(e.path, e.size, e.mtime_ns, CohortContext("c", "b"))
    with pytest.raises(ValueError):
        select_cohort(inventory, count=1, seed=1, context=feature.context, features=(feature, feature))
    result = select_cohort(inventory, count=1, seed=1, context=CohortContext())
    assert not select_cohort(inventory, count=1, seed=1, context=CohortContext(),
                             previous=result).selection_reused


def test_no_source_io_or_global_random(inventory, monkeypatch):
    import builtins
    import io
    import random
    def forbidden(*args, **kwargs):
        raise AssertionError("Selektor darf keine Quellen oder globalen RNG verwenden")
    for module, name in ((builtins, "open"), (io, "open"), (os, "stat"), (os, "lstat"),
                         (random, "seed"), (random, "random")):
        monkeypatch.setattr(module, name, forbidden)
    result = select_cohort(inventory, count=1, seed=0, context=CohortContext())
    assert len(result.paths) == 1


def test_previous_boolean_version_is_not_integer(inventory):
    context = CohortContext("c", "b")
    result = select_cohort(inventory, count=1, seed=0, context=context)
    with pytest.raises(ValueError):
        select_cohort(inventory, count=1, seed=0, context=context,
                      previous=replace(result, version=True))
