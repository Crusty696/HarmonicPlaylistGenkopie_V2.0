"""Tests fuer Paarung und Bewertung von Mixpunkt-Kandidaten (Spec Abschnitt 2)."""
import math

import pytest

from hpg_core.genres import CANONICAL_GENRES, GENRE_TRANSITION_TOLERANCES

KANDIDATEN_GEWICHTE = (
    "kandidaten_harmonic_weight", "kandidaten_bpm_weight", "kandidaten_energy_weight",
    "kandidaten_genre_weight", "kandidaten_groove_weight", "kandidaten_bass_weight",
    "kandidaten_timbre_weight", "kandidaten_mood_weight", "kandidaten_loudness_weight",
    "kandidaten_structure_weight",
)


def test_kandidaten_gewichte_je_genre_summe_eins():
    for genre in CANONICAL_GENRES:
        w = GENRE_TRANSITION_TOLERANCES[genre]
        assert all(k in w for k in KANDIDATEN_GEWICHTE), genre
        assert math.isclose(sum(w[k] for k in KANDIDATEN_GEWICHTE), 1.0, abs_tol=1e-6), genre


def test_kandidaten_gewichte_startwerte():
    w = GENRE_TRANSITION_TOLERANCES["Psytrance"]
    assert w["kandidaten_groove_weight"] == pytest.approx(0.264)
    assert w["kandidaten_harmonic_weight"] == pytest.approx(0.140)
    assert w["kandidaten_loudness_weight"] == pytest.approx(0.060)
    assert w["kandidaten_structure_weight"] == pytest.approx(0.060)


def test_alte_gewichte_unveraendert():
    w = GENRE_TRANSITION_TOLERANCES["Psytrance"]
    assert w["groove_weight"] == pytest.approx(0.300)
    assert w["harmonic_weight"] == pytest.approx(0.160)

from hpg_core.mix_candidates import MixCandidate
from hpg_core.models import Track
from hpg_core.pair_candidates import (
    PairCandidate, blend_bars_options, pair_gate_reasons,
)


def _sections(duration=300.0, intro_end=60.0, outro_start=240.0):
    return [
        {"label": "intro", "start_time": 0.0, "end_time": intro_end, "avg_energy": 30},
        {"label": "main", "start_time": intro_end, "end_time": outro_start, "avg_energy": 70},
        {"label": "outro", "start_time": outro_start, "end_time": duration, "avg_energy": 30},
    ]


def _track(name="a.mp3", bpm=140.0, duration=300.0, genre="Psytrance", **kw) -> Track:
    t = Track(filePath=name, fileName=name)
    t.bpm = bpm
    t.duration = duration
    t.detected_genre = genre
    t.phrase_unit = 16
    t.first_downbeat = 0.0
    t.downbeat_confidence = 1.0
    t.sections = _sections(duration)
    t.outro_covered = True
    for k, v in kw.items():
        setattr(t, k, v)
    return t


def _grid(bpm=140.0, phrase_unit=16):
    return (60.0 / bpm) * 4 * phrase_unit   # 27.428 s


def _out(t, **kw):
    c = MixCandidate(t=t, schema=["sektion"], section_label="main")
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def _in(t, **kw):
    return _out(t, **kw)


def test_gates_durchlass():
    a, b = _track(), _track("b.mp3")
    g = _grid()
    out, inn = _out(round(6 * g, 3)), _in(round(3 * g, 3))   # 164.6 s, 82.3 s
    assert pair_gate_reasons(a, b, out, inn, blend_bars=16) == []


def test_gate_bpm_und_pitch():
    a, b = _track(bpm=140.0), _track("b.mp3", bpm=143.0)
    g = _grid()
    r = pair_gate_reasons(a, b, _out(round(6 * g, 3)), _in(round(3 * _grid(143.0), 3)), 16)
    assert "bpm" in r


def test_gate_half_double_erlaubt_mit_relation():
    a, b = _track(bpm=140.0), _track("b.mp3", bpm=70.0)
    g_a, g_b = _grid(140.0), _grid(70.0)
    r = pair_gate_reasons(a, b, _out(round(6 * g_a, 3)), _in(round(3 * g_b, 3)), 16)
    assert "bpm" not in r and "pitch" not in r


def test_gate_blende_im_outro_und_benannter_cue_ausnahme():
    a, b = _track(), _track("b.mp3")
    g = _grid()
    spaet = _out(round(8 * g, 3))          # 219.4 s, 16 Takte = 27.4 s -> 246.9 > 240
    assert "blende_im_outro" in pair_gate_reasons(a, b, spaet, _in(round(3 * g, 3)), 16)
    # "Drop 2" ist benannter_cue, aber KEIN IN/OUT-Muster -> Guard bleibt.
    spaet.schema = ["benannter_cue"]
    a.cue_points = [{"t": round(8 * g, 3), "name": "Drop 2", "typ": 0, "hot_cue": None, "provenance": "manual"}]
    assert "blende_im_outro" in pair_gate_reasons(a, b, spaet, _in(round(3 * g, 3)), 16)
    # Manueller "MIX OUT"-Cue, der (floor, Teil-1-Quantisierung) auf denselben Gitterpunkt faellt -> guard-frei.
    a.cue_points = [{"t": round(8 * g, 3) + 0.4, "name": "MIX OUT", "typ": 0, "hot_cue": None, "provenance": "manual"}]
    assert "blende_im_outro" not in pair_gate_reasons(a, b, spaet, _in(round(3 * g, 3)), 16)
    # Auto-Cue mit OUT im Namen zaehlt nicht (provenance auto).
    a.cue_points = [{"t": round(8 * g, 3), "name": "CUE(Auto) OUT", "typ": 0, "hot_cue": None, "provenance": "auto"}]
    assert "blende_im_outro" in pair_gate_reasons(a, b, spaet, _in(round(3 * g, 3)), 16)


def test_blend_bars_options_unter_min_transition_bars_entfaellt():
    a = _track()
    g = _grid()
    c = _out(round(8 * g + 6 * (60.0 / 140.0) * 4, 3))   # 229.7 s, bis 240 bleiben 10.3 s = 6 Takte
    assert blend_bars_options(a, c, "direct") == []


def test_gate_in_im_intro_coverage_gitter():
    a, b = _track(), _track("b.mp3")
    g = _grid()
    assert "in_im_intro" in pair_gate_reasons(a, b, _out(round(6 * g, 3)), _in(round(1 * g, 3)), 16)
    assert "coverage" in pair_gate_reasons(
        a, b, _out(round(6 * g, 3), section_label="unanalysed"), _in(round(3 * g, 3)), 16)
    a.outro_covered = False
    assert "outro_covered" in pair_gate_reasons(a, b, _out(round(6 * g, 3)), _in(round(3 * g, 3)), 16)
    a.outro_covered = True
    assert "gitter_out" in pair_gate_reasons(a, b, _out(round(6 * g + 1.0, 3)), _in(round(3 * g, 3)), 16)


def test_gate_gitter_pssi():
    a, b = _track(), _track("b.mp3")
    a.phrase_grid = [0.0, 30.0, 61.0, 95.0, 130.0, 170.0, 200.0, 230.0]
    out = _out(170.0)
    assert "gitter_out" not in pair_gate_reasons(a, b, out, _in(round(3 * _grid(), 3)), 16)
    assert "gitter_out" in pair_gate_reasons(a, b, _out(171.0), _in(round(3 * _grid(), 3)), 16)


def test_blend_bars_options_deckel_und_half_double():
    a = _track()
    g = _grid()
    assert blend_bars_options(a, _out(round(6 * g, 3)), "direct") == [16, 32]
    # 219.4 s: bis Outro 240 bleiben 20.6 s = 12.0 Takte (1.714 s/Takt)
    assert blend_bars_options(a, _out(round(8 * g, 3)), "direct") == [12]
    assert blend_bars_options(a, _out(round(6 * g, 3)), "half") == [16]


def test_paircandidate_roundtrip():
    pc = PairCandidate(out_a=_out(10.0), in_b=_in(20.0), blend_bars=16, overlap_sec=27.4,
                       score=0.5, teilwerte={"bpm": 1.0}, flags={"half_double": False},
                       begruendung="x", rang=1, bpm_relation="direct")
    d = pc.to_dict()
    assert d["out_a"]["t"] == 10.0 and d["t_out"] == 10.0 and d["t_in"] == 20.0
    back = PairCandidate.from_dict(d)
    assert back.out_a.t == 10.0 and back.in_b.t == 20.0 and back.blend_bars == 16
