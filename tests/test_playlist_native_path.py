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


def test_twelve_track_set_prefers_complete_path_to_high_scoring_dead_end(monkeypatch):
    from tests.fixtures.track_factories import make_track
    tracks = [make_track(filePath=f"{i}.mp3", title=str(i)) for i in range(12)]
    def score(a, b, *args, **kwargs):
        step = int(b.title) - int(a.title)
        return {1: 30, 2: 99}.get(step, 0)
    monkeypatch.setattr(playlist, "calculate_transition_objective", score)
    assert playlist._sort_harmonic_flow(list(reversed(tracks)), 2.0) == tracks
