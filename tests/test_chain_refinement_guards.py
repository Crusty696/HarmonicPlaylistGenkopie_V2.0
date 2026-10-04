"""Isolierte Ketten-/Strategieguards; keine Audio- oder Cache-Zugriffe.

Das Ranking ist eine synthetische Naht. Der echte DP, die echte
Refinement-Logik und (ausser gezielter Versuchsauswahl) echte Guards laufen.
Diese Tests beweisen keine Messqualitaet oder musikalische Eignung.
"""
from collections import Counter

import pytest

from hpg_core import playlist as p
from hpg_core.pair_candidates import CandidateSnapshot
from tests.fixtures.track_factories import make_track
from tests.test_playlist_generation_result import _candidate


def _occurrences(count, energy=50):
    return tuple(
        p.TrackOccurrence(
            "guards", i,
            make_track(filePath=f"C:/fixture/guard-{i}.mp3", fileName=str(i),
                       bpm=128.0, energy=energy, duration=1000.0),
        )
        for i in range(count)
    )


def _snapshot(ordinal, *, out=500.0, inn=0.0, score=0.75):
    candidate = _candidate(out, inn, score=score)
    return CandidateSnapshot.from_pair_candidate(
        candidate, original_ordinal=ordinal
    ), candidate


def _install_rank(monkeypatch, graph):
    calls = []

    def rank(items, *args):
        snapshots, maps = [], []
        for a, b in zip(items, items[1:]):
            key = (a.ordinal, b.ordinal)
            calls.append(key)
            value = graph.get(key)
            snapshots.append(() if value is None else (value[0],))
            maps.append({} if value is None else {value[0].key: value[1]})
        return tuple(snapshots), tuple(maps), 0

    monkeypatch.setattr(p, "_rank_fixed_boundaries", rank)
    return calls


def _only_attempt(monkeypatch, left, right):
    original = p._refinement_swap_allowed

    def allowed(order, a, b, mode):
        return (a, b) == (left, right) and original(order, a, b, mode)

    monkeypatch.setattr(p, "_refinement_swap_allowed", allowed)


def _assert_preserved(before, after):
    assert after[0] is before[0]
    assert Counter(o.occurrence_id for o in after) == Counter(
        o.occurrence_id for o in before
    )
    assert Counter(id(o) for o in after) == Counter(id(o) for o in before)


def _assert_links(selected, order):
    for i, (previous, current) in enumerate(zip(selected, selected[1:])):
        if previous is not None and current is not None:
            assert p._candidate_link_consistent(previous, current, order[i + 1].track)


def _anchor_fixture(monkeypatch, *, missing=(), sacrifice=None):
    items = _occurrences(8)
    graph = {
        (i, i + 1): _snapshot(i, out=500.0 + 10 * i)
        for i in range(7)
    }
    # Fenster beim Tausch 3/4: Kanten 1..5; Kanten 0 und 6 bleiben ausserhalb.
    graph[(1, 2)] = _snapshot(101, out=510.0, inn=200.0, score=0.71)
    graph[(5, 6)] = _snapshot(105, out=550.0, inn=20.0, score=0.73)
    graph[(3, 4)] = None
    # None-Anker trotz vorhandenem Ranking: Konflikt mit einer hoeher bewerteten
    # Kante ausserhalb des Fensters. Ohne Fixierung wuerde der lokale DP den
    # Kandidaten erneut planen, weil ihm genau dieser Aussenkonflikt fehlt.
    if "left" in missing:
        graph[(0, 1)] = _snapshot(100, out=500.0, inn=600.0, score=0.99)
    if "right" in missing:
        graph[(5, 6)] = _snapshot(105, out=550.0, inn=600.0, score=0.73)
        graph[(6, 7)] = _snapshot(106, out=560.0, score=0.99)
    graph[(2, 4)] = _snapshot(
        204, out=100.0 if sacrifice == "left" else 520.0, score=0.99
    )
    graph[(4, 3)] = _snapshot(403, out=540.0, score=0.99)
    graph[(3, 5)] = _snapshot(
        305, out=530.0, inn=600.0 if sacrifice == "right" else 0.0,
        score=0.99,
    )
    _install_rank(monkeypatch, graph)
    _only_attempt(monkeypatch, 3, 4)
    original_select = p._select_snapshot_path
    observed = []

    def select(options, order, cancel_check=None):
        result = original_select(options, order, cancel_check)
        observed.append((options, order, result[0]))
        return result

    monkeypatch.setattr(p, "_select_snapshot_path", select)
    return items, graph, observed


@pytest.mark.parametrize("missing", [(), ("left",), ("right",), ("left", "right")])
def test_accepts_repair_without_changing_distinct_or_none_outer_anchors(monkeypatch, missing):
    items, graph, observed = _anchor_fixture(monkeypatch, missing=missing)
    refined, ranked = p._refine_order_with_chain(items, "Harmonic Flow", 2.0, {}, {})
    assert tuple(o.ordinal for o in refined) == (0, 1, 2, 4, 3, 5, 6, 7)
    _assert_preserved(items, refined)
    assert len(observed) == 2
    baseline, local = observed
    options, window, proposed = local
    assert tuple(o.ordinal for o in window) == (1, 2, 4, 3, 5, 6)
    for local_index, global_index in ((0, 1), (4, 5)):
        anchor = baseline[2][global_index]
        side = "left" if local_index == 0 else "right"
        assert (anchor is None) == (side in missing)
        assert graph[(global_index, global_index + 1)] is not None
        assert options[local_index] == (() if anchor is None else (anchor,))
        assert proposed[local_index] == anchor
    # Anker muessen unterscheidbar sein, sofern beide geplant sind.
    if not missing:
        assert proposed[0].key != proposed[4].key
    spliced = (*baseline[2][:1], *proposed, *baseline[2][6:])
    assert spliced[0] == graph[(0, 1)][0]
    assert spliced[6] == graph[(6, 7)][0]
    _assert_links(spliced, refined)
    final = p._select_snapshot_path(ranked[0], refined)[0]
    _assert_links(final, refined)
    assert sum(x is not None for x in final) > sum(x is not None for x in baseline[2])


@pytest.mark.parametrize("side,index", [("left", 0), ("right", 4)])
def test_rejects_better_local_score_when_real_dp_sacrifices_an_outer_anchor(monkeypatch, side, index):
    items, _, observed = _anchor_fixture(monkeypatch, sacrifice=side)
    refined, _ = p._refine_order_with_chain(items, "Harmonic Flow", 2.0, {}, {})
    assert len(observed) == 2
    baseline, local = observed
    proposed = local[2]
    previous = baseline[2][1:6]
    assert previous[index] is not None
    assert proposed[index] is None
    # Gleiche Planzahl, aber hoeherer Score: Ablehnung kommt vom Ankervertrag.
    assert sum(x is not None for x in proposed) == sum(x is not None for x in previous)
    assert sum(x.score for x in proposed if x) > sum(x.score for x in previous if x)
    assert all(a is b for a, b in zip(refined, items))
    _assert_preserved(items, refined)
    _assert_links(baseline[2], items)


def _wave_graph(order, trial):
    graph = {
        (a.ordinal, b.ordinal): _snapshot(i, score=0.75)
        for i, (a, b) in enumerate(zip(order, order[1:]))
    }
    graph[(order[1].ordinal, order[2].ordinal)] = None
    for i, (a, b) in enumerate(zip(trial, trial[1:])):
        key = (a.ordinal, b.ordinal)
        if key not in graph or graph[key] is None:
            graph[key] = _snapshot(100 + i, score=0.99)
    return graph


def test_wave_replay_accepts_equal_profile_swap_on_the_same_side(monkeypatch):
    pool = _occurrences(5)
    order = tuple(pool[i] for i in (2, 3, 1, 4, 0))
    trial = tuple(pool[i] for i in (2, 4, 1, 3, 0))
    _install_rank(monkeypatch, _wave_graph(order, trial))
    _only_attempt(monkeypatch, 1, 3)
    refined, ranked = p._refine_order_with_chain(order, "Energy Wave", 2.0, {}, {})
    assert tuple(o.ordinal for o in refined) == (2, 4, 1, 3, 0)
    _assert_preserved(order, refined)
    _assert_links(p._select_snapshot_path(ranked[0], refined)[0], refined)


@pytest.mark.parametrize("reason", ["outside_window", "wrong_side", "wrong_center"])
def test_wave_replay_rejects_invalid_trial_before_local_dp(monkeypatch, reason):
    if reason == "outside_window":
        assert p.ENERGY_WAVE_FENSTER == 8
        pool = _occurrences(19)
        # 18 ist nach Entnahme von 10 im Fenster, vorher jedoch an Position 9.
        indices = (9, 10, 8, 18, 7, 11, 6, 12, 5, 13, 4, 14, 3, 15, 2, 16, 1, 17, 0)
    else:
        pool = _occurrences(5)
        # Absichtlich fehlerhafte Eingangsfolgen pruefen den Replay fail-closed.
        indices = (2, 3, 4, 1, 0) if reason == "wrong_side" else (1, 3, 2, 4, 0)
    order = tuple(pool[i] for i in indices)
    trial = list(order)
    trial[1], trial[3] = trial[3], trial[1]
    calls = _install_rank(monkeypatch, _wave_graph(order, trial))
    _only_attempt(monkeypatch, 1, 3)
    original_select = p._select_snapshot_path
    windows = []

    def select(options, items, cancel_check=None):
        windows.append(len(items))
        return original_select(options, items, cancel_check)

    monkeypatch.setattr(p, "_select_snapshot_path", select)
    refined, _ = p._refine_order_with_chain(order, "Energy Wave", 2.0, {}, {})
    assert all(a is b for a, b in zip(refined, order))
    _assert_preserved(order, refined)
    assert windows == [len(order)]
    assert calls == [(a.ordinal, b.ordinal) for a, b in zip(order, order[1:])]


@pytest.mark.parametrize("mode", tuple(p.STRATEGIES))
def test_swap_guard_never_moves_the_strategy_start(mode):
    assert not p._refinement_swap_allowed(_occurrences(4), 0, 1, mode)


@pytest.mark.parametrize("mode", tuple(p.STRATEGIES))
def test_swap_guard_allows_identical_profile_except_wave_cross_side(mode):
    items = _occurrences(4)
    right = 3 if mode == "Energy Wave" else 2
    assert p._refinement_swap_allowed(items, 1, right, mode)
    if mode == "Energy Wave":
        assert not p._refinement_swap_allowed(items, 1, 2, mode)


@pytest.mark.parametrize("mode", ["Warm-Up", "Cool-Down"])
def test_directional_guard_preserves_bpm_but_allows_energy_tie_break(mode):
    items = _occurrences(4)
    items[2].track.energy = 90
    assert p._refinement_swap_allowed(items, 1, 2, mode)
    items[2].track.bpm = 129.0
    assert not p._refinement_swap_allowed(items, 1, 2, mode)


@pytest.mark.parametrize("mode", ["Peak-Time", "Consistent", "Energy Wave", "Context Flow"])
@pytest.mark.parametrize("field,value", [("energy", 60), ("bpm", 129.0)])
def test_profile_guard_rejects_energy_or_bpm_curve_change(mode, field, value):
    items = _occurrences(4)
    right = 3 if mode == "Energy Wave" else 2
    setattr(items[right].track, field, value)
    assert not p._refinement_swap_allowed(items, 1, right, mode)


@pytest.mark.parametrize("mode", ["Genre Flow", "Context Flow"])
def test_genre_guard_rejects_a_canonical_genre_change(mode):
    items = _occurrences(4)
    items[2].track.genre = "Techno"
    items[2].track.detected_genre = "Techno"
    assert not p._refinement_swap_allowed(items, 1, 2, mode)


def test_context_guard_preserves_clone_penalty_key():
    items = _occurrences(4)
    items[2].track.camelotCode = "9A"
    assert not p._refinement_swap_allowed(items, 1, 2, "Context Flow")


def test_harmonic_guard_does_not_invent_energy_or_bpm_profile_constraints():
    items = _occurrences(4)
    items[2].track.energy = 90
    items[2].track.bpm = 140.0
    assert p._refinement_swap_allowed(items, 1, 2, "Harmonic Flow")
