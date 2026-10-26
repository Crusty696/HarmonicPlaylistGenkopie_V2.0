"""Native Nahtduplikate sind keine musikalischen Beatlücken."""
from types import SimpleNamespace

import pytest

from hpg_core.ai_models.native_beat_alignment import stable_model_window
from hpg_core.pair_candidates import _native_blend_supported


@pytest.mark.parametrize('chunked,expected', [(True, True), (False, False)])
def test_window_with_native_seam_retains_stability(chunked, expected):
    rows = [[112. + i * .5, i % 4 + 1] for i in range(32)]
    rows.insert(16, [120., 4])
    native = dict(bpm=120., model_beats=rows, selection=dict(chunked=chunked))
    assert stable_model_window(native, 112., 16.) is expected
    rows[16][0] = 120.01
    assert not stable_model_window(native, 112., 16.)


def test_real_model_gap_skips_unnecessary_audio_decode(monkeypatch):
    from hpg_core.ai_models import native_audio_phase, native_track_beats
    native = dict(status='ok', bpm=120., model_beats=[[0., 1], [10., 2]],
                  phase_method='native_attack_v1', model_coverage=dict(start_s=0., end_s=30.))
    track = SimpleNamespace(native_beat_analysis=native)
    monkeypatch.setattr(native_track_beats, 'has_verified_grid', lambda t: True)
    monkeypatch.setattr(native_audio_phase, 'supports_window',
                        lambda *a: pytest.fail('Kein Decode für bekannte Modelllücke'))
    assert not _native_blend_supported(track, 0., 16.)
