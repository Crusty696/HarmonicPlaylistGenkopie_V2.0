"""Fortsetzung ohne erneute Inferenz und exakte Modellfenster-Endpunkte."""
import pytest

from hpg_core.ai_models import native_track_beats as native
from hpg_core.ai_models.native_beat_boundaries import absolute_model_rows
from tests.test_native_track_beats import snapshot


def test_selected_window_endpoint_matches_coverage():
    start = 1250078
    assert 60. + start / 44100 > (start + 60 * 44100) / 44100
    rows = absolute_model_rows([[0., 1], [60., 4]], start)
    assert rows == [[start / 44100, 1], [(start + 60 * 44100) / 44100, 4]]
    assert absolute_model_rows([[60.01, 1]], start)[0][0] > rows[-1][0]


@pytest.mark.parametrize("mismatch", [None, "source", "mode", "grid"])
def test_native_resume_checks_provenance_without_inference(tmp_path, monkeypatch, mismatch):
    source = tmp_path / "source.aiff"
    source.write_bytes(b"fixture")
    data = snapshot()
    monkeypatch.setattr(native, "_source_identity", lambda path: [100, 200, 1, 2, 3])
    monkeypatch.setattr(native, "configured_mode", lambda: 4)
    monkeypatch.setattr(native, "enabled", lambda: True)
    if mismatch == "source":
        data["source_identity"][0] += 1
    elif mismatch == "mode":
        monkeypatch.setattr(native, "configured_mode", lambda: 2)
    elif mismatch == "grid":
        data["grid"][1]["pos"] = data["grid"][0]["pos"]
    def forbidden(*args, **kwargs):
        pytest.fail("Keine wiederholte Modellinferenz")
    result = native.analyze(source, snapshot=data, transport=forbidden)
    assert result["status"] == ("unavailable" if mismatch else "ok")
    if mismatch is None:
        result["grid"][0]["pos"] = 0
        assert data["grid"][0]["pos"] != 0
