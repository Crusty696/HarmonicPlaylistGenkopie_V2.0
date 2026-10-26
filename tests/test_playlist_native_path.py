"""Eine vollständige gerichtete Kette geht vor einem teuren Einzelübergang."""
from types import SimpleNamespace
from hpg_core import playlist


def test_small_pool_avoids_greedy_dead_end_without_repeated_pair_work(monkeypatch):
    tracks = [SimpleNamespace(filePath=name) for name in ('a','b','c')]
    calls = []
    def score(a,b,*args,**kwargs):
        calls.append((a.filePath,b.filePath))
        return {('a','c'):90., ('b','a'):60., ('a','b'):70.}.get(calls[-1],0.)
    monkeypatch.setattr(playlist,'calculate_transition_objective',score)
    ordered = playlist._sort_harmonic_flow(tracks,8.)
    assert [t.filePath for t in ordered] == ['b','a','c']
    assert len(calls) == len(set(calls)) == 6
