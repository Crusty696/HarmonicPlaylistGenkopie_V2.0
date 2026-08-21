"""Tests fuer Mixpunkt-Kandidaten: Datenmodell, Cues, Gitter, Gates."""
import pytest

from hpg_core.mix_candidates import (
    MixCandidate, normalize_cues, quantize_to_points, passes_track_gates,
)


def test_mixcandidate_roundtrip_dict():
    c = MixCandidate(t=30.0, schema=["benannter_cue"], provenance="rekordbox_manual", confidence=0.9)
    d = c.to_dict()
    assert d["t"] == 30.0 and d["schema"] == ["benannter_cue"]
    assert MixCandidate.from_dict(d) == c
    assert MixCandidate.from_dict({"t": 1.0}).schema == []


def test_normalize_cues_provenienz_und_dedupe():
    cues = [
        {"position": 30.0, "name": "MIX IN", "type": 0, "hot_cue_number": None, "color": None},
        {"position": 30.5, "name": None, "type": 0, "hot_cue_number": None, "color": None},
        {"position": 61.0, "name": "CUE(Auto)", "type": 0, "hot_cue_number": None, "color": None},
        {"position": 90.0, "name": "", "type": 1, "hot_cue_number": 1, "color": 3},
        {"position": None, "name": "X", "type": 0, "hot_cue_number": None, "color": None},
        {"position": -0.5, "name": "X", "type": 0, "hot_cue_number": None, "color": None},
    ]
    out = normalize_cues(cues)
    assert [c["t"] for c in out] == [30.0, 61.0, 90.0]          # 30.5 < 2 s → weg, ungueltige weg
    assert out[0]["provenance"] == "manual" and out[0]["name"] == "MIX IN"
    assert out[1]["provenance"] == "auto"
    assert out[2]["provenance"] == "leer" and out[2]["typ"] == 1
    assert normalize_cues(None) == [] and normalize_cues([]) == []


def test_quantize_to_points_ceil_floor_mit_toleranz():
    pts = [0.0, 15.0, 30.0, 45.0]
    assert quantize_to_points(15.03, pts, "ceil") == 15.0     # 30 ms drueber → bleibt (0.05 s Toleranz)
    assert quantize_to_points(15.2, pts, "ceil") == 30.0
    assert quantize_to_points(29.97, pts, "floor") == 30.0
    assert quantize_to_points(29.8, pts, "floor") == 15.0
    assert quantize_to_points(50.0, pts, "ceil") is None      # hinter dem letzten Punkt
    assert quantize_to_points(-1.0, pts, "floor") is None
    assert quantize_to_points(10.0, [], "ceil") is None


def test_track_gates_in_und_out():
    # intro_end 20, outro_start 280, duration 300, grid 15 → 2 Phrasen = 30
    assert passes_track_gates(20.0, "in", intro_end=20.0, outro_start=280.0, duration=300.0, grid=15.0)
    assert not passes_track_gates(19.9, "in", intro_end=20.0, outro_start=280.0, duration=300.0, grid=15.0)
    assert not passes_track_gates(275.0, "in", intro_end=20.0, outro_start=280.0, duration=300.0, grid=15.0)  # > dur-2grid
    assert passes_track_gates(280.0, "out", intro_end=20.0, outro_start=280.0, duration=300.0, grid=15.0)
    assert not passes_track_gates(280.1, "out", intro_end=20.0, outro_start=280.0, duration=300.0, grid=15.0)
    assert not passes_track_gates(20.0, "out", intro_end=20.0, outro_start=280.0, duration=300.0, grid=15.0)   # < 2grid
