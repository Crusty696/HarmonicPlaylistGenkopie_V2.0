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

from hpg_core.pair_candidates import score_pair


def _voll(t, **kw):
    """Kandidat mit allen lokalen Messwerten gesetzt."""
    basis = dict(
        schema=["pssi_phrase"], section_label="main", phrase_label="Chorus",
        neuheit=0.6, traegt_allein=True,
        groove_pattern_lokal=[0.25 if s % 4 == 0 else 0.0 for s in range(16)],
        bass_pattern_lokal=[0.25 if s % 4 == 0 else 0.0 for s in range(16)],
        syncopation_lokal=0.2,
        percussive_ratio_lokal=0.5, sub_energy=0.5, bass_punch=2.0,
        bass_rms_dbfs=-20.0, kick_aktiv=True, camelot_lokal="8A",
        key_confidence_lokal=0.9, timbre_fingerprint_lokal=[1.0, 0.5, 0.2],
        brightness_lokal=50, flatness_lokal=0.1, avg_mids_lokal=40.0,
        avg_highs_lokal=20.0, energy_lokal=70, energy_trend="rising",
        lufs_lokal=-10.0, mood={"pssi_mood": 1, "brightness": 50, "flatness": 0.1,
                                "key_mode": "Minor"}, vocal_aktiv_lokal=False,
    )
    basis.update(kw)
    c = MixCandidate(t=t)
    for k, v in basis.items():
        setattr(c, k, v)
    return c


def test_score_identische_kandidaten_nahe_eins_und_alle_teilwerte():
    a, b = _track(), _track("b.mp3")
    out, inn = _voll(160.0, kick_aktiv=False), _voll(80.0, kick_aktiv=False)
    score, teil, flags = score_pair(a, b, out, inn, blend_bars=16, energy_direction="maintain")
    assert set(teil) == {"harmonic", "bpm", "energy", "genre", "groove", "bass",
                         "timbre", "mood", "loudness", "structure"}
    assert all(v is not None for v in teil.values())
    assert teil["bpm"] == pytest.approx(1.0)
    assert teil["loudness"] == pytest.approx(1.0)
    assert teil["harmonic"] == pytest.approx(1.0)
    assert score > 0.9
    assert flags["bass_swap_pflicht"] is False and flags["half_double"] is False


def test_score_kick_konflikt_flag_und_abzug():
    a, b = _track(), _track("b.mp3")
    s_ohne, t_ohne, _ = score_pair(a, b, _voll(160.0, kick_aktiv=False), _voll(80.0, kick_aktiv=False), 16)
    s_mit, t_mit, flags = score_pair(a, b, _voll(160.0), _voll(80.0), 16)
    assert flags["bass_swap_pflicht"] is True
    assert t_mit["bass"] == pytest.approx(t_ohne["bass"] - 0.15)
    assert s_mit < s_ohne


def test_score_lautheit_linear_bis_3db():
    a, b = _track(), _track("b.mp3")
    _, t1, _ = score_pair(a, b, _voll(160.0), _voll(80.0, lufs_lokal=-11.5), 16)
    _, t3, _ = score_pair(a, b, _voll(160.0), _voll(80.0, lufs_lokal=-14.0), 16)
    assert t1["loudness"] == pytest.approx(0.5)
    assert t3["loudness"] == pytest.approx(0.0)


def test_score_fehlende_werte_werden_umverteilt_nicht_null():
    a, b = _track(), _track("b.mp3")
    leer_out = MixCandidate(t=160.0, schema=["sektion"], section_label="main")
    leer_in = MixCandidate(t=80.0, schema=["sektion"], section_label="main")
    score, teil, _ = score_pair(a, b, leer_out, leer_in, 16)
    assert teil["harmonic"] is None and teil["loudness"] is None and teil["groove"] is None
    assert teil["bpm"] == pytest.approx(1.0) and teil["genre"] == pytest.approx(1.0)
    assert score == pytest.approx(1.0)      # nur bpm+genre verfuegbar, beide 1.0


def test_score_half_double_penalty_und_vocals():
    a, b = _track(bpm=140.0), _track("b.mp3", bpm=70.0)
    s_hd, _, flags = score_pair(a, b, _voll(160.0, kick_aktiv=False), _voll(80.0, kick_aktiv=False), 16)
    a2, b2 = _track(), _track("b.mp3")
    s_direct, _, _ = score_pair(a2, b2, _voll(160.0, kick_aktiv=False), _voll(80.0, kick_aktiv=False), 16)
    assert flags["half_double"] is True
    assert s_hd == pytest.approx(s_direct * 0.85)
    s_voc, _, _ = score_pair(a2, b2, _voll(160.0, kick_aktiv=False, vocal_aktiv_lokal=True),
                             _voll(80.0, kick_aktiv=False, vocal_aktiv_lokal=True), 16)
    assert s_voc == pytest.approx(s_direct - 0.06)


def test_score_harmonie_gewicht_skaliert_mit_key_confidence():
    a, b = _track(), _track("b.mp3")
    # 8A -> 3A = 65/100; mit hoher Confidence drueckt das den Score staerker als mit niedriger
    s_hoch, _, _ = score_pair(a, b, _voll(160.0, kick_aktiv=False),
                              _voll(80.0, kick_aktiv=False, camelot_lokal="3A"), 16)
    s_tief, _, _ = score_pair(a, b, _voll(160.0, kick_aktiv=False, key_confidence_lokal=0.1),
                              _voll(80.0, kick_aktiv=False, camelot_lokal="3A"), 16)
    assert s_tief > s_hoch


def test_score_energie_richtung_und_trend():
    a, b = _track(), _track("b.mp3")
    _, t_up, _ = score_pair(a, b, _voll(160.0, energy_lokal=40), _voll(80.0, energy_lokal=90, energy_trend="rising"), 16, energy_direction="up")
    _, t_w, _ = score_pair(a, b, _voll(160.0, energy_lokal=40), _voll(80.0, energy_lokal=90, energy_trend="falling"), 16, energy_direction="up")
    assert t_up["energy"] == pytest.approx(1.0)
    assert t_w["energy"] == pytest.approx(0.8)


def test_score_struktur_und_mood():
    a, b = _track(), _track("b.mp3")
    _, t1, _ = score_pair(a, b, _voll(160.0, section_label="outro", phrase_label="Outro"),
                          _voll(80.0, neuheit=1.0, traegt_allein=True, phrase_label="Chorus"), 16)
    assert t1["structure"] == pytest.approx(1.0)
    _, t2, _ = score_pair(a, b, _voll(160.0), _voll(80.0, mood={"pssi_mood": 2, "brightness": 50,
                                                                "flatness": 0.1, "key_mode": "Major"}), 16)
    assert t2["mood"] == pytest.approx(1.0 - 0.15 - 0.10)

from hpg_core.pair_candidates import begruendung_aus_teilwerten, build_pair_candidates


def _track_mit_kandidaten(name, bpm=140.0, outs=(), ins=()):
    t = _track(name, bpm=bpm)
    t.mix_out_candidates = [c.to_dict() for c in outs]
    t.mix_in_candidates = [c.to_dict() for c in ins]
    return t


def test_build_liefert_sortierte_raenge_und_zwei_blenden():
    g = _grid()
    a = _track_mit_kandidaten("a.mp3", outs=[_voll(round(5 * g, 3), kick_aktiv=False),
                                             _voll(round(6 * g, 3), kick_aktiv=False, schema=["sektion"])])
    b = _track_mit_kandidaten("b.mp3", ins=[_voll(round(3 * g, 3), kick_aktiv=False)])
    res = build_pair_candidates(a, b)
    assert len(res) == 4                      # 2 Kombinationen x 2 Blenden
    assert [p.rang for p in res] == [1, 2, 3, 4]
    assert all(res[i].score >= res[i + 1].score for i in range(len(res) - 1))
    assert {p.blend_bars for p in res} == {16, 32}
    assert all(p.begruendung for p in res)
    assert all(p.overlap_sec == pytest.approx(p.blend_bars * (60.0 / 140.0) * 4) for p in res)


def test_build_gates_leer_bei_bpm():
    a = _track_mit_kandidaten("a.mp3", bpm=140.0, outs=[_voll(round(5 * _grid(), 3))])
    b = _track_mit_kandidaten("b.mp3", bpm=143.0, ins=[_voll(round(3 * _grid(143.0), 3))])
    assert build_pair_candidates(a, b) == []


def test_build_dedupe_und_kappung_mit_schema_garantie():
    g = _grid()
    outs = [_voll(round(k * g, 3), kick_aktiv=False) for k in (3, 4, 5, 6, 7)]       # 5 pssi
    outs.append(_voll(round(7 * g, 3), kick_aktiv=False, schema=["sektion"], neuheit=0.0, traegt_allein=False))
    ins = [_voll(round(k * g, 3), kick_aktiv=False) for k in (3, 4)]
    a = _track_mit_kandidaten("a.mp3", outs=outs)
    b = _track_mit_kandidaten("b.mp3", ins=ins)
    res = build_pair_candidates(a, b)
    kombis = {(p.t_out, p.t_in) for p in res}
    assert len(kombis) <= 6
    assert any("sektion" in p.out_a.schema for p in res)      # Schema-Garantie
    assert len(res) <= 12


def test_build_dedupe_fasst_nahe_gleiche_schemata_zusammen():
    g = _grid()
    o1 = _voll(round(5 * g, 3), kick_aktiv=False)
    o2 = _voll(round(5 * g + 2.0, 3), kick_aktiv=False)   # < 1 Phrase, gleiches Hauptschema
    a = _track_mit_kandidaten("a.mp3", outs=[o1, o2])
    a.phrase_grid = [0.0, round(5 * g, 3), round(5 * g + 2.0, 3), round(8 * g, 3)]
    b = _track_mit_kandidaten("b.mp3", ins=[_voll(round(3 * g, 3), kick_aktiv=False)])
    res = build_pair_candidates(a, b)
    assert len({(p.t_out, p.t_in) for p in res}) == 1


def test_build_dedupe_laesst_genau_eine_phrase_abstand_getrennt():
    g = _grid()
    # Teil 1 rundet auf 3 Dezimalen: round(4g)-round(3g) = 27.428 < 27.42857
    o1, o2 = _voll(round(3 * g, 3), kick_aktiv=False), _voll(round(4 * g, 3), kick_aktiv=False)
    a = _track_mit_kandidaten("a.mp3", outs=[o1, o2])
    b = _track_mit_kandidaten("b.mp3", ins=[_voll(round(3 * g, 3), kick_aktiv=False)])
    res = build_pair_candidates(a, b)
    assert len({(p.t_out, p.t_in) for p in res}) == 2
    assert {p.blend_bars for p in res} == {16, 32}


def test_begruendung_aus_teilwerten_fester_text():
    txt = begruendung_aus_teilwerten(
        {"harmonic": 0.9, "bpm": 1.0, "groove": 0.6, "loudness": None},
        {"bass_swap_pflicht": True, "half_double": False, "lange_blende_erlaubt": False,
         "benannter_cue": False}, 16)
    assert "Harmonie stark" in txt and "Groove mittel" in txt and "Lautheit nicht messbar" in txt
    assert "Bass-Swap noetig" in txt and "16 Takte" in txt
