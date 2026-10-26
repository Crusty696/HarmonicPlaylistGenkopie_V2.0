"""Eine qualifizierte Reservewahl muss die normale Score-Kappung ueberleben."""
from hpg_core.pair_candidates import PairCandidate, dedupe_and_cap
from tests.test_pair_candidates import _out, _in


def test_explicit_existing_reserve_survives_cap_without_new_points():
    pairs = [PairCandidate(out_a=_out(100.+i*100), in_b=_in(20.),
        blend_bars=16, overlap_sec=32., score=1.-i*.01, teilwerte={}, flags={})
        for i in range(9)]
    chosen = dict(t_out=900., t_in=20., blend_bars=16)
    normal = dedupe_and_cap(pairs, 10., 10., set())
    assert all(p.t_out != 900. for p in normal)
    reserved = dedupe_and_cap(pairs, 10., 10., set(), preserve_choice=chosen)
    assert len(reserved) == len(normal)+1
    assert any(p.t_out == 900. for p in reserved)
    assert dedupe_and_cap(pairs, 10., 10., set(), preserve_choice=dict(
        t_out=999., t_in=20., blend_bars=16)) == normal
