"""Modell7-Fallback braucht stabile Gesamtfolge und explizite Herkunft."""
import pytest

from hpg_core.ai_models.native_beat_selection import full_model_disagrees
from hpg_core.ai_models import native_track_beats as native
from tests.test_native_track_beats import snapshot


def test_stable_full_track_detects_wrong_short_window_tempo():
    rows = [[i * 60 / 135, i % 4 + 1] for i in range(300)]
    assert full_model_disagrees(81., rows)
    assert not full_model_disagrees(135., rows)
    assert not full_model_disagrees(81., rows[:32])
    irregular = [[i * .44 + (i % 3) * .12, i % 4 + 1] for i in range(300)]
    assert not full_model_disagrees(81., irregular)


@pytest.mark.parametrize('requested', [2, 3, True, 4])
def test_fallback_provenance_cannot_override_explicit_mode(requested):
    data = snapshot()
    data['requested_configuration'] = requested
    if type(requested) is int and requested == 2:
        native.validate_snapshot(data, duration=48.)
    else:
        with pytest.raises(ValueError, match='automatic model fallback'):
            native.validate_snapshot(data, duration=48.)


def test_fallback_snapshot_reuses_original_requested_mode(tmp_path, monkeypatch):
    source = tmp_path / 'source.aiff'
    source.write_bytes(b'fixture')
    data = snapshot()
    data['requested_configuration'] = 2
    monkeypatch.setattr(native, '_source_identity', lambda path: data['source_identity'])
    monkeypatch.setattr(native, 'configured_mode', lambda: 2)
    monkeypatch.setattr(native, 'enabled', lambda: True)
    result = native.analyze(source, snapshot=data,
                            transport=lambda *a, **k: pytest.fail('Keine Inferenz'))
    assert result['status'] == 'ok'
