"""Tests fuer Mixpunkt-Kandidaten: Datenmodell, Cues, Gitter, Gates."""
import pytest

from hpg_core.mix_candidates import (
    MixCandidate, normalize_cues, quantize_to_points, passes_track_gates,
    collect_candidate_times,
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


def test_normalize_cues_verwirft_nan_und_inf():
    cues = [{"position": float("nan"), "name": "", "type": 0, "hot_cue_number": None, "color": None},
            {"position": float("inf"), "name": "", "type": 0, "hot_cue_number": None, "color": None},
            {"position": 12.0, "name": "", "type": 0, "hot_cue_number": None, "color": None}]
    assert [c["t"] for c in normalize_cues(cues)] == [12.0]


def _sections():
    return [
        {"label": "intro", "start_time": 0.0, "end_time": 30.0, "avg_energy": 30.0},
        {"label": "build", "start_time": 30.0, "end_time": 60.0, "avg_energy": 55.0},
        {"label": "drop", "start_time": 60.0, "end_time": 120.0, "avg_energy": 90.0},
        {"label": "breakdown", "start_time": 120.0, "end_time": 150.0, "avg_energy": 50.0},
        {"label": "drop", "start_time": 150.0, "end_time": 240.0, "avg_energy": 92.0},
        {"label": "outro", "start_time": 240.0, "end_time": 300.0, "avg_energy": 25.0},
    ]


def test_collect_candidate_times_alle_schemata_mit_pssi_gitter():
    grid = [float(x) for x in range(0, 301, 15)]          # 15 s = 8 Bars @ 128 BPM
    phrases = [{"start_s": s, "end_s": s + 15.0, "label": "Chorus" if s in (60.0, 150.0) else "Up",
                "mood": 1, "kind": 5 if s in (60.0, 150.0) else 2, "fill": 0} for s in grid[:-1]]
    cues = [{"t": 45.0, "name": "MIX IN", "typ": 0, "hot_cue": None, "provenance": "manual"},
            {"t": 25.0, "name": "START", "typ": 0, "hot_cue": None, "provenance": "manual"},   # im Intro (bis 30 s)
            {"t": 61.0, "name": "CUE(Auto)", "typ": 0, "hot_cue": None, "provenance": "auto"},
            {"t": 20.0, "name": "Drop 2", "typ": 0, "hot_cue": None, "provenance": "manual"},   # benannt, kein IN/OUT: Guard gilt
            {"t": 233.0, "name": "", "typ": 0, "hot_cue": None, "provenance": "leer"}]
    ins, outs = collect_candidate_times(
        seite_grid=grid, sections=_sections(), phrases=phrases, cues=cues,
        analyzer_in=60.0, analyzer_out=240.0, duration=300.0, grid_sec=15.0,
        intro_end=30.0, outro_start=240.0, outro_covered=True,
    )
    t_in = {c.t: c for c in ins}
    assert 45.0 in t_in and "benannter_cue" in t_in[45.0].schema
    assert 75.0 in t_in and "auto_cue" in t_in[75.0].schema            # 61 ceil → 75
    assert 60.0 in t_in and {"analyzer", "pssi_phrase", "sektion", "energie_neuheit"} <= set(t_in[60.0].schema)
    assert 30.0 in t_in and "benannter_cue" in t_in[30.0].schema       # 25 s ceil → 30, schlaegt den Guard
    assert all(c.t >= 30.0 for c in ins)                                  # "Drop 2" @20 s: ceil → 30 (Guard), nicht 20
    assert "benannter_cue" in t_in[30.0].schema and t_in[30.0].provenance == "rekordbox_manual"
    t_out = {c.t: c for c in outs}
    assert 225.0 in t_out and "auto_cue" in t_out[225.0].schema          # 233 floor → 225
    assert 240.0 in t_out and "analyzer" in t_out[240.0].schema
    assert all(c.t <= 240.0 for c in outs)                                # Outro-Guard
    assert len(ins) <= 8 and len(outs) <= 8
    assert ins == sorted(ins, key=lambda c: c.t)
    assert t_in[45.0].provenance == "rekordbox_manual"
    assert t_in[60.0].phrase_label == "Chorus" and t_in[60.0].section_label == "drop"


def test_collect_candidate_times_ohne_pssi_nutzt_phrasenanker_gitter():
    ins, outs = collect_candidate_times(
        seite_grid=[], sections=_sections(), phrases=[], cues=[],
        analyzer_in=60.0, analyzer_out=240.0, duration=300.0, grid_sec=15.0,
        intro_end=30.0, outro_start=240.0, outro_covered=True, anchor=0.0,
    )
    assert any("analyzer" in c.schema for c in ins)
    assert all(abs((c.t / 15.0) - round(c.t / 15.0)) < 1e-6 for c in ins + outs)


def test_collect_candidate_times_outro_nicht_abgedeckt_keine_out_kandidaten():
    ins, outs = collect_candidate_times(
        seite_grid=[], sections=_sections(), phrases=[], cues=[],
        analyzer_in=60.0, analyzer_out=240.0, duration=300.0, grid_sec=15.0,
        intro_end=30.0, outro_start=240.0, outro_covered=False, anchor=0.0,
    )
    assert outs == [] and ins


def test_unanalysed_sektion_liefert_keinen_kandidaten():
    secs = _sections()
    secs[3] = {"label": "unanalysed", "start_time": 120.0, "end_time": 150.0, "avg_energy": 0.0}
    ins, outs = collect_candidate_times(
        seite_grid=[], sections=secs, phrases=[], cues=[{"t": 130.0, "name": "", "typ": 0, "hot_cue": None, "provenance": "leer"}],
        analyzer_in=60.0, analyzer_out=240.0, duration=300.0, grid_sec=15.0,
        intro_end=30.0, outro_start=240.0, outro_covered=True, anchor=0.0,
    )
    assert all(not (120.0 <= c.t < 150.0) for c in ins + outs)


def test_kappung_auf_acht_mit_prioritaet():
    cues = [{"t": float(t), "name": "", "typ": 0, "hot_cue": None, "provenance": "leer"} for t in range(35, 230, 10)]
    ins, outs = collect_candidate_times(
        seite_grid=[], sections=_sections(), phrases=[], cues=cues,
        analyzer_in=60.0, analyzer_out=240.0, duration=300.0, grid_sec=15.0,
        intro_end=30.0, outro_start=240.0, outro_covered=True, anchor=0.0,
    )
    assert len(ins) == 8 and len(outs) == 8
    assert any("analyzer" in c.schema for c in ins)   # hoehere Prioritaet ueberlebt die Kappung
