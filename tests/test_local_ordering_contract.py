"""Lokale Messwerte statt widersprechender Ganztrackwerte steuern die Naht."""
from collections import Counter

import pytest

from hpg_core import playlist as p
from tests.fixtures.track_factories import make_track


def track(name, energy=50):
    return make_track(filePath=f"C:/fixture/{name}.mp3", fileName=name,
                      bpm=128., energy=energy, camelotCode="8A")


def test_local_objective_matches_candidate_not_global_features():
    a, b = track("a"), track("b")
    before = p.calculate_enhanced_compatibility(a, b, 2.)
    assert before.kandidat is not None
    assert before.overall_score == pytest.approx(before.kandidat["score"])
    b.camelotCode = "2B"
    b.groove_pattern = [0., 1.]
    after = p.calculate_enhanced_compatibility(a, b, 2.)
    assert after.overall_score == pytest.approx(before.overall_score)


def test_energy_wave_prefers_local_match_within_selected_side():
    tracks = [track(str(i), 10 + 10*i) for i in range(5)]
    tracks[3].mix_in_candidates[0].camelot_lokal = "2B"
    result = p._sort_energy_wave(tracks, 2.)
    assert result[0] is tracks[2]
    assert result[1] is tracks[4]
    assert Counter(map(id, result)) == Counter(map(id, tracks))


def test_context_flow_prefers_local_match_over_global_key():
    a, b, c, d = [track(n, e) for n, e in zip("abcd", (20, 50, 50, 90))]
    b.mix_in_candidates[0].camelot_lokal = "2B"
    c.camelotCode = "2B"
    result = p._sort_context_flow([a, b, c, d], 2.)
    assert result[0] is a
    assert result[1] is c


@pytest.mark.parametrize("mode", list(p.STRATEGIES))
def test_all_strategies_preserve_occurrences_and_publish_local_scores(mode):
    a, b = track("a"), track("b")
    duplicate_path = track("a")
    isolated = track("isolated")
    isolated.mix_in_candidates = []
    isolated.mix_out_candidates = []
    tracks = [a, a, b, duplicate_path, isolated]
    result = p.generate_playlist_result(tracks, mode, 2.)
    assert Counter(map(id, result.tracks)) == Counter(map(id, tracks))
    assert len({o.occurrence_id for o in result.occurrences}) == 5
    for metrics in result.metrics:
        if metrics.kandidat is not None:
            assert metrics.overall_score == pytest.approx(metrics.kandidat.score)
        else:
            assert metrics.overall_score == 0.


def test_chain_refinement_repairs_an_unplanned_boundary_without_losing_tracks(monkeypatch):
    from hpg_core.pair_candidates import CandidateSnapshot
    from tests.test_playlist_generation_result import _candidate
    items = [track(name) for name in "abcd"]
    occurrences = tuple(p.TrackOccurrence("run", i, t) for i, t in enumerate(items))
    calls = []
    def rank(occ, *args):
        calls.append(tuple(o.track.fileName for o in occ))
        snapshots, maps = [], []
        for a, b in zip(occ, occ[1:]):
            good = (a.track.fileName, b.track.fileName) in {("a", "b"), ("a", "c"), ("c", "b"), ("b", "d"), ("c", "d")}
            candidate = _candidate(t_out=180., t_in=0., score=.8)
            snap = CandidateSnapshot.from_pair_candidate(candidate, original_ordinal=0)
            snapshots.append((snap,) if good else ())
            maps.append({snap.key: candidate} if good else {})
        return tuple(snapshots), tuple(maps), 0
    monkeypatch.setattr(p, "_rank_fixed_boundaries", rank)
    refined, ranked = p._refine_order_with_chain(occurrences, "Harmonic Flow", 2., {}, {}, None)
    assert [o.track.fileName for o in refined] == ["a", "c", "b", "d"]
    assert {o.occurrence_id for o in refined} == {o.occurrence_id for o in occurrences}
    assert len(calls) <= 3 + 32 * 4


@pytest.mark.parametrize("mode", list(p.STRATEGIES))
def test_chain_refinement_checks_cancel_before_ranking(mode):
    occurrences = tuple(p.TrackOccurrence("run", i, track(str(i))) for i in range(4))
    with pytest.raises(InterruptedError):
        p._refine_order_with_chain(occurrences, mode, 2., {}, {}, lambda: True)


def test_refinement_budget_and_directed_pair_reuse(monkeypatch):
    from hpg_core.pair_candidates import CandidateSnapshot
    from tests.test_playlist_generation_result import _candidate
    items = tuple(p.TrackOccurrence("run", i, track(str(i))) for i in range(100))
    calls, windows = [], []
    candidate = _candidate(180., 0.)
    snap = CandidateSnapshot.from_pair_candidate(candidate, original_ordinal=0)
    def rank(occ, *args):
        calls.append(tuple(o.occurrence_id for o in occ))
        return ((snap,),), ({snap.key: candidate},), 0
    original = p._select_snapshot_path
    def select(options, occurrences, cancel_check=None):
        windows.append(len(occurrences))
        return original(options, occurrences, cancel_check)
    monkeypatch.setattr(p, "_rank_fixed_boundaries", rank)
    monkeypatch.setattr(p, "_select_snapshot_path", select)
    result, ranked = p._refine_order_with_chain(items, "Harmonic Flow", 2., {}, {})
    assert result == items
    assert len(calls) == len(set(calls))
    assert len(calls) <= 99 + 32 * 4
    assert windows[0] == 100 and len(windows[1:]) == 32
    assert max(windows[1:]) <= 7
    assert len(ranked[0]) == 99
