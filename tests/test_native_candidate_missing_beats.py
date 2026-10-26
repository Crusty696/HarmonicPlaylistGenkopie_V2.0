"""Optionale Modellereignisse dürfen das lokale Audio-Gate nicht umgehen."""
from types import SimpleNamespace

from hpg_core.ai_models import native_audio_phase, native_track_beats
from hpg_core.pair_candidates import _native_blend_supported
from tests.test_native_track_beats import snapshot


def test_verified_snapshot_without_model_beats_still_checks_audio(monkeypatch):
    data = snapshot()
    data['phase_method'] = 'native_attack_v1'
    assert 'model_beats' not in data
    track = SimpleNamespace(native_beat_analysis=data, duration=48.,
        bpm=data['bpm'], first_downbeat=data['first_downbeat'],
        downbeat_confidence=1., beatgrid_status='verified')
    assert native_track_beats.has_verified_grid(track)
    calls = []
    def reject_window(item, start, duration):
        calls.append((item, start, duration))
        return False
    monkeypatch.setattr(native_audio_phase, 'supports_window', reject_window)
    assert not _native_blend_supported(track, 4., 8.)
    assert calls == [(track, 4., 8.)]
