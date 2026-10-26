"""Jede Blendenvariante verwendet ihre eigene lokale Merkmalsabdeckung."""
import pytest
from hpg_core.ai_models import deep_features
from hpg_core.pair_candidates import build_pair_candidates
from tests.test_pair_candidates import _track, _grid, _out, _in


def test_long_blend_uses_long_feature_window_without_model_inference(monkeypatch):
    a, b = _track(), _track('b.mp3')
    a.mix_out_candidates = [_out(3 * _grid())]
    b.mix_in_candidates = [_in(3 * _grid())]
    # Fensterlaenge als messbarer Stellvertreter: der Produktpfad wertet nur
    # vorhandene Kurven aus und darf hier keine Modellinferenz benoetigen.
    monkeypatch.setattr(deep_features, '_local_stems',
                        lambda track, start, end: {'bass': end - start})
    monkeypatch.setattr(deep_features, '_local_embedding', lambda *args: None)
    candidates = build_pair_candidates(a, b)
    assert {p.blend_bars for p in candidates} == {16, 32}
    for candidate in candidates:
        features = candidate.flags['deep_features']
        assert features['stems_a']['bass'] == pytest.approx(candidate.overlap_sec)
        assert features['stems_b']['bass'] == pytest.approx(candidate.overlap_sec)
        assert features['affects_score'] is False
    assert candidates[0].score == candidates[1].score
