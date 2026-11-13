from types import SimpleNamespace

import pytest

from hpg_core import verified_playlist as verified
from hpg_core.models import Track


def test_verified_search_replaces_dead_end_and_rejected_audio(monkeypatch, tmp_path):
    tracks = [Track(str(tmp_path / name), name, bpm=126) for name in "abcde"]
    allowed = {"ab", "ac", "cd", "de", "ad"}
    def rank(pair, *args):
        edge = "".join(item.track.fileName for item in pair)
        candidates = (SimpleNamespace(key=edge),) if edge in allowed else ()
        return (candidates,), ({},), 0
    def build(**kw):
        seq = kw["occurrences"]
        return SimpleNamespace(tracks=[item.track for item in seq],
            recommendations=[SimpleNamespace(plan=True) for _ in seq[1:]],
            path_stats=SimpleNamespace(planned=len(seq)-1))
    def render(edge, dest):
        if edge == "ad":
            raise verified.BeatSyncError("drift")
        verified.sf.write(dest, [0.25, -0.25], 44100)
    monkeypatch.setattr(verified, "_rank_fixed_boundaries", rank)
    monkeypatch.setattr(verified, "_build_generation_result", build)
    monkeypatch.setattr(verified, "_candidate_link_consistent", lambda *args: True)
    monkeypatch.setattr(verified, "calculate_compatibility", lambda *a, **k: 1)
    monkeypatch.setattr(verified.TransitionClipSpec, "from_plan", lambda plan,a,b: a.fileName+b.fileName)
    monkeypatch.setattr(verified, "render_transition_clip", render)
    result=verified.generate_verified_set(tracks,4,2,{}, {},None)
    assert [t.fileName for t in result.tracks] == list("acde")
    with pytest.raises(ValueError, match="Keine vollständig geprüfte Kette"):
        verified.generate_verified_set(tracks,5,2,{}, {},None)
