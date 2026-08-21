"""Tests fuer Mixpunkt-Kandidaten: Datenmodell, Cues, Gitter, Gates."""
import numpy as np
import pytest
import soundfile as sf

from hpg_core.mix_candidates import (
    MixCandidate, normalize_cues, quantize_to_points, passes_track_gates,
    collect_candidate_times, measure_candidate_window, build_track_candidates, candidate_confidence,
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
    # 60 s ueberlebt, weil der Punkt die meisten Schemata vereinigt (Sektion +
    # Energie-Neuheit + Analyzer), nicht weil "analyzer" allein hoeher stuende
    assert any("analyzer" in c.schema for c in ins)
    # Tiebreak bei gleichem Top-Schema und gleicher Schema-Anzahl: die FRUEHEREN
    # Zeitpunkte ueberleben (explizit ueber k.t, nicht Einfuegereihenfolge)
    nur_auto = sorted(c.t for c in ins if c.schema == ["auto_cue"])
    assert nur_auto and nur_auto[0] == 45.0 and nur_auto[-1] < 225.0


def test_kappung_out_seite_behaelt_spaete_punkte():
    cues = [{"t": float(t), "name": "", "typ": 0, "hot_cue": None, "provenance": "leer"} for t in range(35, 230, 10)]
    ins, outs = collect_candidate_times(
        seite_grid=[], sections=_sections(), phrases=[], cues=cues,
        analyzer_in=60.0, analyzer_out=240.0, duration=300.0, grid_sec=15.0,
        intro_end=30.0, outro_start=240.0, outro_covered=True, anchor=0.0,
    )
    nur_auto_out = [c.t for c in outs if c.schema == ["auto_cue"]]
    assert nur_auto_out and nur_auto_out[-1] >= 195.0 and nur_auto_out[0] > 45.0   # spaete ueberleben, fruehe fallen
    nur_auto_in = [c.t for c in ins if c.schema == ["auto_cue"]]
    assert nur_auto_in and nur_auto_in[0] == 45.0                                   # In unveraendert: fruehe zuerst


def _kick_track(tmp_path, bpm=128.0, sekunden=60.0, sr=22050, kick_ab=0.0, kick_bis=None):
    """Sinus-Kick (55 Hz, 120 ms) auf jeder Zaehlzeit + leises Rauschen; Kick nur in [kick_ab, kick_bis)."""
    n = int(sekunden * sr)
    y = 0.01 * np.random.default_rng(0).standard_normal(n)
    spb = 60.0 / bpm
    kick_bis = sekunden if kick_bis is None else kick_bis
    t_kick = np.arange(0, sekunden, spb)
    for tk in t_kick:
        if not (kick_ab <= tk < kick_bis):
            continue
        i0 = int(tk * sr); L = int(0.12 * sr)
        tt = np.arange(L) / sr
        y[i0:i0 + L] += 0.8 * np.sin(2 * np.pi * 55 * tt) * np.exp(-tt * 25)
    p = tmp_path / "kick.wav"
    sf.write(p, y.astype(np.float32), sr)
    return str(p)


def test_measure_window_liefert_alle_felder_und_kick_aktiv(tmp_path):
    path = _kick_track(tmp_path)
    c = MixCandidate(t=30.0, schema=["sektion"])
    m = measure_candidate_window(
        path, c, bpm=128.0, first_downbeat=0.0, downbeat_confidence=1.0,
        grid_sec=15.0, duration=60.0, sections=[{"label": "drop", "start_time": 0.0, "end_time": 60.0, "avg_energy": 80.0}],
    )
    assert m is c
    assert len(c.bass_pattern_lokal) == 16 and len(c.groove_pattern_lokal) == 16
    assert c.kick_aktiv is True and c.bass_rms_dbfs is not None and c.bass_rms_dbfs > -35.0
    assert c.sub_energy is not None and c.bass_punch is not None
    assert c.syncopation_lokal is not None and 0.0 <= c.syncopation_lokal <= 1.0
    assert c.percussive_ratio_lokal is not None
    assert c.camelot_lokal != "" and c.key_confidence_lokal is not None
    assert len(c.timbre_fingerprint_lokal) > 0
    assert c.brightness_lokal is not None and c.flatness_lokal is not None
    assert c.avg_mids_lokal is not None and c.avg_highs_lokal is not None
    assert c.energy_lokal is not None and c.energy_trend in ("rising", "falling", "stable")
    assert c.lufs_lokal is not None and -70.0 < c.lufs_lokal < 0.0
    assert set(c.mood) == {"brightness", "flatness", "key_mode", "pssi_mood"}
    assert c.vocal_aktiv_lokal in (True, False)
    assert c.neuheit is not None and 0.0 <= c.neuheit <= 1.0
    assert c.traegt_allein is True


def test_measure_window_ohne_kick_nach_t_traegt_nicht_allein_und_neuheit_hoch(tmp_path):
    path = _kick_track(tmp_path, kick_ab=0.0, kick_bis=30.0)      # nach 30 s Stille
    c = MixCandidate(t=30.0, schema=["sektion"])
    measure_candidate_window(path, c, bpm=128.0, first_downbeat=0.0, downbeat_confidence=1.0,
                             grid_sec=15.0, duration=60.0, sections=[])
    assert c.traegt_allein is False
    assert c.energy_trend == "falling"
    assert c.neuheit > 0.3


def test_measure_window_ohne_downbeat_keine_muster_aber_rest_gemessen(tmp_path):
    path = _kick_track(tmp_path)
    c = MixCandidate(t=30.0)
    measure_candidate_window(path, c, bpm=128.0, first_downbeat=0.0, downbeat_confidence=0.0,
                             grid_sec=15.0, duration=60.0, sections=[])
    assert c.bass_pattern_lokal == [] and c.kick_aktiv is None
    assert c.lufs_lokal is not None and c.energy_lokal is not None


def test_measure_window_am_trackrand_klemmt_und_kurz_ist_kein_absturz(tmp_path):
    path = _kick_track(tmp_path, sekunden=20.0)
    c = MixCandidate(t=1.0)
    measure_candidate_window(path, c, bpm=128.0, first_downbeat=0.0, downbeat_confidence=1.0,
                             grid_sec=15.0, duration=20.0, sections=[])
    assert c.energy_lokal is not None


def test_candidate_confidence_formel():
    # Mittel aus: downbeat_confidence, Gitterqualitaet (1.0 PSSI / phrase_confidence), key_confidence_lokal, Coverage (1/0)
    assert candidate_confidence(downbeat_confidence=1.0, pssi_grid=True, phrase_confidence=0.1,
                                key_confidence_lokal=0.5, covered=True) == pytest.approx((1.0 + 1.0 + 0.5 + 1.0) / 4)
    assert candidate_confidence(downbeat_confidence=0.4, pssi_grid=False, phrase_confidence=0.2,
                                key_confidence_lokal=None, covered=False) == pytest.approx((0.4 + 0.2 + 0.0) / 3)


def test_build_track_candidates_end_to_end_synthetisch(tmp_path):
    path = _kick_track(tmp_path, sekunden=120.0)
    sections = [{"label": "intro", "start_time": 0.0, "end_time": 15.0, "avg_energy": 20.0},
                {"label": "drop", "start_time": 15.0, "end_time": 105.0, "avg_energy": 80.0},
                {"label": "outro", "start_time": 105.0, "end_time": 120.0, "avg_energy": 20.0}]
    ins, outs = build_track_candidates(
        path, bpm=128.0, duration=120.0, first_downbeat=0.0, downbeat_confidence=1.0,
        phrase_confidence=0.0, phrase_anchor=0.0, phrase_unit=8, sections=sections,
        phrases=[], cues=[], analyzer_in=30.0, analyzer_out=90.0, outro_covered=True,
    )
    assert ins and outs
    assert all(isinstance(c, dict) for c in ins + outs)           # Track-Felder sind Dicts
    assert all(c["t"] >= 15.0 for c in ins) and all(c["t"] <= 105.0 for c in outs)
    assert all(0.0 <= c["confidence"] <= 1.0 for c in ins + outs)
    assert any(c["lufs_lokal"] is not None for c in ins)


def test_build_track_candidates_kandidat_in_unanalysed_ist_nicht_covered(tmp_path):
    """Coverage haengt nur an der Sektion: ein Kandidat in einer unanalysed-Sektion entsteht gar nicht,
    einer in einer analysierten Sektion bekommt covered=1 in der Confidence."""
    path = _kick_track(tmp_path, sekunden=120.0)
    sections = [{"label": "intro", "start_time": 0.0, "end_time": 15.0, "avg_energy": 20.0},
                {"label": "drop", "start_time": 15.0, "end_time": 60.0, "avg_energy": 80.0},
                {"label": "unanalysed", "start_time": 60.0, "end_time": 90.0, "avg_energy": 0.0},
                {"label": "drop", "start_time": 90.0, "end_time": 105.0, "avg_energy": 80.0},
                {"label": "outro", "start_time": 105.0, "end_time": 120.0, "avg_energy": 20.0}]
    ins, outs = build_track_candidates(
        path, bpm=128.0, duration=120.0, first_downbeat=0.0, downbeat_confidence=1.0,
        phrase_confidence=0.0, phrase_anchor=0.0, phrase_unit=8, sections=sections,
        phrases=[], cues=[], analyzer_in=30.0, analyzer_out=90.0, outro_covered=True,
    )
    assert all(not (60.0 <= c["t"] < 90.0) for c in ins + outs)
    assert ins and all(c["confidence"] > 0.0 for c in ins)
