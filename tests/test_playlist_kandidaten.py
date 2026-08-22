"""Tests: Kandidaten im Playlist-Scoring und in den Empfehlungen (Spec Abschnitt 4)."""
import pytest

from hpg_core import playlist as pl
from hpg_core.mix_candidates import MixCandidate
from hpg_core.models import Track


def _sections(duration=300.0, intro_end=60.0, outro_start=240.0):
    return [
        {"label": "intro", "start_time": 0.0, "end_time": intro_end, "avg_energy": 30},
        {"label": "main", "start_time": intro_end, "end_time": outro_start, "avg_energy": 70},
        {"label": "outro", "start_time": outro_start, "end_time": duration, "avg_energy": 30},
    ]


def _voll(t, **kw):
    c = MixCandidate(t=t, schema=["pssi_phrase"], section_label="main", phrase_label="Chorus",
                     neuheit=0.6, traegt_allein=True,
                     groove_pattern_lokal=[0.25 if s % 4 == 0 else 0.0 for s in range(16)],
                     bass_pattern_lokal=[0.25 if s % 4 == 0 else 0.0 for s in range(16)],
                     syncopation_lokal=0.2, percussive_ratio_lokal=0.5, sub_energy=0.5, bass_punch=2.0,
                     bass_rms_dbfs=-20.0, kick_aktiv=False, camelot_lokal="8A", key_confidence_lokal=0.9,
                     timbre_fingerprint_lokal=[1.0, 0.5, 0.2], brightness_lokal=50, flatness_lokal=0.1,
                     avg_mids_lokal=40.0, avg_highs_lokal=20.0, energy_lokal=70, energy_trend="rising",
                     lufs_lokal=-10.0, mood={"pssi_mood": 1, "brightness": 50, "flatness": 0.1, "key_mode": "Minor"},
                     vocal_aktiv_lokal=False)
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def _track(name, bpm=140.0, camelot="8A", outs=(), ins=()):
    g = (60.0 / bpm) * 4 * 16
    t = Track(filePath=name, fileName=name)
    t.bpm = bpm
    t.duration = 300.0
    t.detected_genre = "Psytrance"
    t.phrase_unit = 16
    t.first_downbeat = 0.0
    t.downbeat_confidence = 1.0
    t.sections = _sections()
    t.outro_covered = True
    t.camelotCode = camelot
    t.keyNote = "A"
    t.keyMode = "Minor"
    t.energy = 70
    t.mix_in_point = round(3 * g, 3)
    t.mix_out_point = round(6 * g, 3)
    t.mix_out_candidates = [c.to_dict() for c in outs]
    t.mix_in_candidates = [c.to_dict() for c in ins]
    return t


def test_enhanced_compatibility_nutzt_kandidat_wenn_vorhanden():
    g = (60.0 / 140.0) * 4 * 16
    a = _track("a.mp3", outs=[_voll(round(5 * g, 3))])
    b = _track("b.mp3", ins=[_voll(round(3 * g, 3))])
    m = pl.calculate_enhanced_compatibility(a, b, 2.0)
    assert m.kandidat is not None and m.kandidat["rang"] == 1
    assert m.loudness_match == pytest.approx(1.0) and m.structure_match is not None
    assert m.groove_match == pytest.approx(m.kandidat["teilwerte"]["groove"])
    assert m.overall_score == pytest.approx(min(1.0, m.kandidat["score"] + m.ai_bonus))


def test_enhanced_compatibility_ohne_kandidaten_wie_bisher():
    a, b = _track("a.mp3"), _track("b.mp3")
    m = pl.calculate_enhanced_compatibility(a, b, 2.0)
    assert m.kandidat is None and m.loudness_match is None and m.structure_match is None


def test_bpm_hard_gate_bleibt_auch_mit_kandidat():
    g = (60.0 / 140.0) * 4 * 16
    a = _track("a.mp3", outs=[_voll(round(5 * g, 3))])
    b = _track("b.mp3", bpm=143.0, ins=[_voll(round(3 * (60.0 / 143.0) * 64, 3))])
    assert pl.calculate_enhanced_compatibility(a, b, 2.0).overall_score == 0.0


def test_recommendations_tragen_kandidaten_und_plan_aus_rang_1():
    g = (60.0 / 140.0) * 4 * 16
    a = _track("a.mp3", outs=[_voll(round(5 * g, 3)), _voll(round(6 * g, 3), schema=["sektion"])])
    b = _track("b.mp3", ins=[_voll(round(3 * g, 3))])
    recs = pl.compute_transition_recommendations([a, b], bpm_tolerance=2.0)
    r = recs[0]
    assert r.kandidaten and r.kandidat_aktiv == 1
    k1 = r.kandidaten[0]
    assert r.plan.mix_out_a == pytest.approx(k1["t_out"]) and r.plan.mix_in_b == pytest.approx(k1["t_in"])
    assert r.plan.overlap == pytest.approx(min(k1["overlap_sec"], 64.0))
    assert r.fade_out_end == pytest.approx(min(r.plan.mix_out_a + r.plan.overlap, 300.0))


def test_bass_swap_pflicht_waehlt_bass_swap():
    g = (60.0 / 140.0) * 4 * 16
    a = _track("a.mp3", outs=[_voll(round(5 * g, 3), kick_aktiv=True)])
    b = _track("b.mp3", ins=[_voll(round(3 * g, 3), kick_aktiv=True)])
    r = pl.compute_transition_recommendations([a, b], bpm_tolerance=2.0)[0]
    assert r.kandidaten[0]["flags"]["bass_swap_pflicht"] is True
    assert r.transition_type == "bass_swap" and r.plan.transition_type == "bass_swap"
