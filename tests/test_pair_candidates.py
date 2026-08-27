"""Tests fuer Paarung und Bewertung von Mixpunkt-Kandidaten (Spec Abschnitt 2)."""
import math
from unittest.mock import Mock

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


@pytest.mark.parametrize("wert", [float("nan"), float("inf"), -0.1, "0.1", True])
def test_candidate_preferences_verwirft_ungueltige_gewichte(wert):
    from hpg_core.candidate_preferences import _gueltige_gewichte

    eintrag = {key: 0.1 for key in KANDIDATEN_GEWICHTE}
    eintrag[KANDIDATEN_GEWICHTE[0]] = wert

    assert _gueltige_gewichte(eintrag) is None


def test_alte_gewichte_unveraendert():
    w = GENRE_TRANSITION_TOLERANCES["Psytrance"]
    assert w["groove_weight"] == pytest.approx(0.300)
    assert w["harmonic_weight"] == pytest.approx(0.160)

from hpg_core.mix_candidates import MixCandidate
from hpg_core.models import QUANTIZE_TOLERANCE_SEC, Track
from hpg_core.pair_candidates import (
    PairCandidate, blend_bars_options, build_pair_candidates, pair_gate_reasons,
    pair_quality_reasons,
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
    t.beatgrid_source = "rekordbox"
    t.beatgrid_status = "verified"
    t.beatgrid_windows_checked = 3
    t.beatgrid_max_phase_error_ms = 5.0
    t.sections = _sections(duration)
    t.analysis_coverage = [{"start": 0.0, "end": duration}]
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


@pytest.mark.parametrize(
    "status", ["unknown", "mismatch", "unverifiable", "unsupported"]
)
@pytest.mark.parametrize("side", ["a", "b"])
def test_beatgrid_status_ist_diagnose_und_keine_paarsperre(status, side):
    a, b = _track(), _track("b.mp3")
    g = _grid()
    out, inn = _out(round(6 * g, 3)), _in(round(3 * g, 3))
    invalid = a if side == "a" else b
    invalid.beatgrid_status = status
    invalid.analysis_mode = "full"

    reasons = pair_gate_reasons(a, b, out, inn, blend_bars=16)

    assert f"beatgrid_{side}" not in reasons
    a.mix_out_candidates = [out.to_dict()]
    b.mix_in_candidates = [inn.to_dict()]
    assert build_pair_candidates(a, b)


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


def test_gerichteter_manueller_mix_out_darf_nicht_ins_outro_blenden():
    a, b = _track(), _track("b.mp3")
    g = _grid()
    spaet = _out(round(8 * g, 3))          # 219.4 s, 16 Takte = 27.4 s -> 246.9 > 240
    assert "blende_im_outro" in pair_gate_reasons(a, b, spaet, _in(round(3 * g, 3)), 16)
    # "Drop 2" ist benannter_cue, aber KEIN IN/OUT-Muster -> Guard bleibt.
    spaet.schema = ["benannter_cue"]
    a.cue_points = [{"t": round(8 * g, 3), "name": "Drop 2", "typ": 0, "hot_cue": None, "provenance": "manual"}]
    assert "blende_im_outro" in pair_gate_reasons(a, b, spaet, _in(round(3 * g, 3)), 16)
    # Auch ein gerichteter manueller MIX-OUT-Cue hat keine Ausnahme.
    a.cue_points = [{"t": round(8 * g, 3) + 0.4, "name": "MIX OUT", "typ": 0, "hot_cue": None, "provenance": "manual"}]
    assert "blende_im_outro" in pair_gate_reasons(a, b, spaet, _in(round(3 * g, 3)), 16)
    # Auto-Cue mit OUT im Namen zaehlt nicht (provenance auto).
    a.cue_points = [{"t": round(8 * g, 3), "name": "CUE(Auto) OUT", "typ": 0, "hot_cue": None, "provenance": "auto"}]
    assert "blende_im_outro" in pair_gate_reasons(a, b, spaet, _in(round(3 * g, 3)), 16)


def test_build_verwirft_gerichtete_manuelle_cues_in_intro_und_outro():
    g = _grid()
    out = _voll(round(9 * g, 3), schema=["benannter_cue"], section_label="outro")
    inn = _voll(round(1 * g, 3), schema=["benannter_cue"], section_label="intro")
    a = _track_mit_kandidaten("a.mp3", outs=[out])
    b = _track_mit_kandidaten("b.mp3", ins=[inn])
    a.cue_points = [{"t": out.t, "name": "MIX OUT", "provenance": "manual"}]
    b.cue_points = [{"t": inn.t, "name": "MIX IN", "provenance": "manual"}]

    paare = build_pair_candidates(a, b)

    assert paare == []


def test_build_bewahrt_gueltige_manuelle_cues_und_herkunftsflag():
    g = _grid()
    out = _voll(round(6 * g, 3), schema=["benannter_cue"])
    inn = _voll(round(3 * g, 3), schema=["benannter_cue"])
    a = _track_mit_kandidaten("a.mp3", outs=[out])
    b = _track_mit_kandidaten("b.mp3", ins=[inn])
    a.cue_points = [{"t": out.t, "name": "MIX OUT", "provenance": "manual"}]
    b.cue_points = [{"t": inn.t, "name": "MIX IN", "provenance": "manual"}]

    paare = build_pair_candidates(a, b)

    assert paare
    assert all(p.flags["benannter_cue"] for p in paare)


def test_blend_bars_options_unter_min_transition_bars_entfaellt():
    a = _track()
    g = _grid()
    c = _out(round(8 * g + 6 * (60.0 / 140.0) * 4, 3))   # 229.7 s, bis 240 bleiben 10.3 s = 6 Takte
    assert blend_bars_options(a, c, "direct") == []


def test_gate_in_im_intro_coverage_gitter():
    a, b = _track(), _track("b.mp3")
    g = _grid()
    assert "in_im_intro" in pair_gate_reasons(a, b, _out(round(6 * g, 3)), _in(round(1 * g, 3)), 16)
    assert "coverage" not in pair_gate_reasons(
        a, b, _out(round(6 * g, 3), section_label="unanalysed"),
        _in(round(3 * g, 3)), 16,
    )
    a.analysis_coverage = [{"start": 0.0, "end": 150.0},
                           {"start": 180.0, "end": a.duration}]
    assert "coverage" in pair_gate_reasons(
        a, b, _out(round(6 * g, 3), section_label="main"),
        _in(round(3 * g, 3)), 16,
    )
    a.outro_covered = False
    assert "outro_covered" in pair_gate_reasons(a, b, _out(round(6 * g, 3)), _in(round(3 * g, 3)), 16)
    a.outro_covered = True
    assert "gitter_out" in pair_gate_reasons(a, b, _out(round(6 * g + 1.0, 3)), _in(round(3 * g, 3)), 16)


def test_gate_sperrt_autoritative_unanalysed_section_und_fehlende_coverage():
    a, b = _track(), _track("b.mp3")
    g = _grid()
    out, inn = _out(round(6 * g, 3)), _in(round(3 * g, 3))
    a.sections = [
        {"label": "intro", "start_time": 0.0, "end_time": 60.0},
        {"label": "unanalysed", "start_time": 60.0, "end_time": 200.0},
        {"label": "outro", "start_time": 200.0, "end_time": 300.0},
    ]

    assert "coverage" in pair_gate_reasons(a, b, out, inn, 16)
    a.sections = _sections()
    a.analysis_coverage = []
    assert "coverage" in pair_gate_reasons(a, b, out, inn, 16)
    a.analysis_coverage = [{"start": 0.0, "end": a.duration}, {"start": "kaputt"}]
    assert "coverage" in pair_gate_reasons(a, b, out, inn, 16)


def test_build_verwirft_coverage_luecke_trotz_kopiertem_main_label():
    g = _grid()
    out = _voll(round(6 * g, 3), section_label="main")
    inn = _voll(round(3 * g, 3), section_label="main")
    a = _track_mit_kandidaten("a.mp3", outs=[out])
    b = _track_mit_kandidaten("b.mp3", ins=[inn])
    a.analysis_coverage = [{"start": 0.0, "end": 150.0},
                           {"start": 180.0, "end": a.duration}]

    assert build_pair_candidates(a, b) == []


def test_intro_und_outro_grenze_selbst_sind_strukturverletzung():
    a, b = _track(), _track("b.mp3")

    reasons = pair_gate_reasons(a, b, _out(240.0), _in(60.0), 16)

    assert "out_im_outro" in reasons
    assert "in_im_intro" in reasons
    assert "blende_im_outro" in reasons


def test_pair_gates_sperren_das_gesamte_sicherheitsband():
    a, b = _track(), _track("b.mp3")
    tol = QUANTIZE_TOLERANCE_SEC

    reasons = pair_gate_reasons(
        a, b, _out(240.0 - tol), _in(60.0 + tol), 16
    )

    assert "out_im_outro" in reasons
    assert "in_im_intro" in reasons


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


def test_lokaler_qualitaetsvertrag_lehnt_fehlende_und_schwache_werte_ab():
    voll = {name: 0.8 for name in (
        "harmonic", "bpm", "energy", "genre", "groove", "bass", "timbre",
        "mood", "loudness", "structure",
    )}
    assert pair_quality_reasons(0.8, voll) == []
    fehlt = dict(voll, timbre=None)
    assert "faktor_fehlt:timbre" in pair_quality_reasons(0.8, fehlt)
    assert "groove_zu_niedrig" in pair_quality_reasons(0.8, dict(voll, groove=0.49))
    assert "lokaler_score_zu_niedrig" in pair_quality_reasons(0.69, voll)
    assert "lokaler_score_zu_niedrig" in pair_quality_reasons(1.01, voll)


@pytest.mark.parametrize(
    "feld,wert,grund",
    [
        ("timbre_fingerprint_lokal", [float("nan")], "quellmessung_fehlt:timbre"),
        ("bass_punch", float("nan"), "quellmessung_ungueltig:bass_punch"),
        ("bass_rms_dbfs", float("nan"), "quellmessung_ungueltig:bass_rms_dbfs"),
        ("avg_mids_lokal", float("nan"), "quellmessung_ungueltig:avg_mids_lokal"),
        ("avg_highs_lokal", float("nan"), "quellmessung_ungueltig:avg_highs_lokal"),
    ],
)
def test_verwendete_rohmessungen_duerfen_nicht_nan_sein(feld, wert, grund):
    a, b = _track(), _track("b.mp3")
    out, inn = _voll(160.0, kick_aktiv=False), _voll(80.0, kick_aktiv=False)
    setattr(out, feld, wert)
    score, teil, flags = score_pair(a, b, out, inn, 16)
    kandidat = PairCandidate(out, inn, 16, 16.0, score, teil, flags)

    assert grund in pair_quality_reasons(score, teil, kandidat)


@pytest.mark.parametrize("feld", ["brightness", "flatness"])
def test_verwendete_mood_rohmessungen_duerfen_nicht_nan_sein(feld):
    a, b = _track(), _track("b.mp3")
    out, inn = _voll(160.0, kick_aktiv=False), _voll(80.0, kick_aktiv=False)
    out.mood = dict(out.mood, **{feld: float("nan")})
    score, teil, flags = score_pair(a, b, out, inn, 16)
    kandidat = PairCandidate(out, inn, 16, 16.0, score, teil, flags)

    assert f"quellmessung_ungueltig:{feld}" in pair_quality_reasons(
        score, teil, kandidat
    )


@pytest.mark.parametrize(
    "seite,feld",
    [("out", "neuheit"), ("out", "traegt_allein"),
     ("in", "neuheit"), ("in", "traegt_allein")],
)
def test_struktur_braucht_alle_vier_gerichteten_rohmessungen(seite, feld):
    a, b = _track(), _track("b.mp3")
    out, inn = _voll(160.0, kick_aktiv=False), _voll(80.0, kick_aktiv=False)
    setattr(out if seite == "out" else inn, feld, None)

    score, teil, flags = score_pair(a, b, out, inn, 16)
    kandidat = PairCandidate(out, inn, 16, 16.0, score, teil, flags)

    assert teil["structure"] is None
    assert "quellmessung_fehlt:structure" in pair_quality_reasons(score, teil, kandidat)


@pytest.mark.parametrize("feld", ["kick_aktiv", "vocal_aktiv_lokal"])
def test_unbekannte_boolesche_rohmessung_sperrt_paar(feld):
    a, b = _track(), _track("b.mp3")
    out, inn = _voll(160.0, kick_aktiv=False), _voll(80.0, kick_aktiv=False)
    setattr(out, feld, None)

    score, teil, flags = score_pair(a, b, out, inn, 16)
    kandidat = PairCandidate(out, inn, 16, 16.0, score, teil, flags)

    assert any(
        grund in pair_quality_reasons(score, teil, kandidat)
        for grund in ("quellmessung_fehlt:bass", "quellmessung_fehlt:vocals")
    )


def test_unbekanntes_genre_ist_nicht_lokal_bewertbar():
    a, b = _track(genre="Unknown"), _track("b.mp3")
    out, inn = _voll(160.0, kick_aktiv=False), _voll(80.0, kick_aktiv=False)

    score, teil, flags = score_pair(a, b, out, inn, 16)
    kandidat = PairCandidate(out, inn, 16, 16.0, score, teil, flags)

    assert teil["genre"] is None
    assert "faktor_fehlt:genre" in pair_quality_reasons(score, teil, kandidat)


def test_ungueltiger_lokaler_camelot_code_sperrt_paar():
    a, b = _track(), _track("b.mp3")
    out = _voll(160.0, kick_aktiv=False, camelot_lokal="X")
    inn = _voll(80.0, kick_aktiv=False)
    score, teil, flags = score_pair(a, b, out, inn, 16)
    kandidat = PairCandidate(out, inn, 16, 16.0, score, teil, flags)

    assert "quellmessung_fehlt:harmonic" in pair_quality_reasons(
        score, teil, kandidat
    )


@pytest.mark.parametrize("bpm", [0.0, float("nan"), float("inf")])
def test_ungueltiges_bpm_erzeugt_keine_paarkandidaten(bpm):
    a, b = _track(bpm=bpm), _track("b.mp3")
    a.mix_out_candidates = [_voll(round(6 * _grid(), 3))]
    b.mix_in_candidates = [_voll(round(3 * _grid(), 3))]

    assert build_pair_candidates(a, b) == []


def test_groove_bewertet_passung_statt_gleichheit():
    a, b = _track(), _track("b.mp3")
    basis = [0.8 if index % 4 == 0 else 0.0 for index in range(16)]
    anders_aber_passend = [0.5 if index % 4 == 0 else 0.05 for index in range(16)]
    konflikt = [0.8 if index % 4 == 2 else 0.0 for index in range(16)]
    out = _voll(160.0, groove_pattern_lokal=basis, bass_pattern_lokal=basis)
    _, passend, _ = score_pair(
        a, b, out,
        _voll(80.0, groove_pattern_lokal=anders_aber_passend,
              bass_pattern_lokal=anders_aber_passend),
        16,
    )
    _, unpassend, _ = score_pair(
        a, b, out,
        _voll(80.0, groove_pattern_lokal=konflikt, bass_pattern_lokal=konflikt),
        16,
    )
    assert passend["groove"] > unpassend["groove"]
    assert passend["groove"] >= 0.5


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
    a.sections[1]["label"] = "breakdown"
    b.sections[1]["label"] = "drop"
    _, t1, _ = score_pair(
        a, b,
        _voll(160.0, section_label="main", phrase_label="Main"),
        _voll(80.0, section_label="main", neuheit=1.0,
              traegt_allein=True, phrase_label="Main"),
        16,
    )
    assert t1["structure"] == pytest.approx((0.6 + 1.0 + 0.0 + 1.0) / 4.0 + 0.1)
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


def test_build_akzeptiert_exakt_64_sekunden_overlap(monkeypatch):
    bpm = 120.0
    g = _grid(bpm)
    a = _track_mit_kandidaten(
        "a.mp3", bpm=bpm,
        outs=[_voll(round(6 * g, 3), kick_aktiv=False)],
    )
    b = _track_mit_kandidaten(
        "b.mp3", bpm=bpm,
        ins=[_voll(round(3 * g, 3), kick_aktiv=False)],
    )
    a.duration = b.duration = 600.0
    a.sections = b.sections = _sections(600.0, outro_start=480.0)
    monkeypatch.setattr(
        "hpg_core.pair_candidates.blend_bars_options", lambda *_args: [32]
    )

    result = build_pair_candidates(a, b)

    assert result
    assert {candidate.overlap_sec for candidate in result} == {64.0}


def test_build_verwirft_64_takte_wenn_sie_mehr_als_64_sekunden_dauern(
    monkeypatch,
):
    bpm = 138.0
    g = _grid(bpm)
    a = _track_mit_kandidaten(
        "a.mp3", bpm=bpm,
        outs=[_voll(round(6 * g, 3), kick_aktiv=False)],
    )
    b = _track_mit_kandidaten(
        "b.mp3", bpm=bpm,
        ins=[_voll(round(3 * g, 3), kick_aktiv=False)],
    )
    a.duration = b.duration = 600.0
    a.sections = b.sections = _sections(600.0, outro_start=480.0)
    monkeypatch.setattr(
        "hpg_core.pair_candidates.blend_bars_options", lambda *_args: [64]
    )

    assert 64 * (60.0 / bpm) * 4 > 64.0
    assert build_pair_candidates(a, b) == []


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


def test_score_pair_nimmt_praeferenz_gewichte_vor_toleranzen(monkeypatch):
    from hpg_core import candidate_preferences as cp
    a, b = _track(), _track("b.mp3")
    out, inn = _voll(160.0, kick_aktiv=False), _voll(80.0, kick_aktiv=False, camelot_lokal="3A")
    s_default, _, _ = score_pair(a, b, out, inn, 16)
    nur_harmonie = {f"kandidaten_{f}_weight": (1.0 if f == "harmonic" else 0.0) for f in (
        "harmonic", "bpm", "energy", "genre", "groove", "bass", "timbre", "mood", "loudness", "structure")}
    monkeypatch.setattr(cp, "kandidaten_gewichte", lambda genre: nur_harmonie)
    s_pref, _, _ = score_pair(a, b, out, inn, 16)
    assert s_pref == pytest.approx(0.65)          # 8A -> 3A = 65/100, nur Harmonie zaehlt
    assert s_pref != pytest.approx(s_default)
    # explizites tolerances-Argument gewinnt vor der Praeferenz
    from hpg_core.genres import GENRE_TRANSITION_TOLERANCES
    s_expl, _, _ = score_pair(a, b, out, inn, 16, tolerances=GENRE_TRANSITION_TOLERANCES["Psytrance"])
    assert s_expl == pytest.approx(s_default)


def _explizite_kandidaten_toleranzen():
    return dict(GENRE_TRANSITION_TOLERANCES["Psytrance"])


def _korrumpiere_explizite_gewichte(toleranzen, fall):
    erster = KANDIDATEN_GEWICHTE[0]
    if fall == "missing":
        toleranzen.pop(erster)
    elif fall == "extra":
        toleranzen["kandidaten_falsch_weight"] = 0.0
    elif fall == "bool":
        toleranzen[erster] = True
    elif fall == "nonnumeric":
        toleranzen[erster] = "0.1"
    elif fall == "nan":
        toleranzen[erster] = float("nan")
    elif fall == "inf":
        toleranzen[erster] = float("inf")
    elif fall == "negative":
        toleranzen[erster] = -0.1
    elif fall == "above_one":
        toleranzen[erster] = 1.1
    elif fall == "bad_sum":
        toleranzen[erster] += 0.01
    return toleranzen


@pytest.mark.parametrize("api", ["score_pair", "rank_pair_candidates"])
@pytest.mark.parametrize(
    "fall",
    [
        "missing", "extra", "bool", "nonnumeric", "nan", "inf",
        "negative", "above_one", "bad_sum",
    ],
)
def test_explizite_kandidatengewichte_sind_an_beiden_apis_fail_closed(api, fall):
    toleranzen = _korrumpiere_explizite_gewichte(
        _explizite_kandidaten_toleranzen(), fall
    )
    if api == "score_pair":
        aufruf = lambda: score_pair(
            _track(), _track("b.mp3"),
            _voll(160.0, kick_aktiv=False),
            _voll(80.0, kick_aktiv=False),
            16,
            tolerances=toleranzen,
        )
    else:
        gitter = _grid()
        a = _track_mit_kandidaten(
            "a.mp3", outs=[_voll(round(5 * gitter, 3), kick_aktiv=False)]
        )
        b = _track_mit_kandidaten(
            "b.mp3", ins=[_voll(round(3 * gitter, 3), kick_aktiv=False)]
        )
        aufruf = lambda: rank_pair_candidates(
            a, b, tolerances=toleranzen, wahl={}, schema_rang=[]
        )

    with pytest.raises(ValueError, match="Kandidatengewicht"):
        aufruf()


def test_explizite_vollstaendige_gewichte_erlauben_wirksame_nichtgewichtstoleranz():
    a, b = _track(), _track("b.mp3")
    out = _voll(
        160.0, kick_aktiv=False,
        mood={"brightness": 0.0, "flatness": 0.1, "key_mode": "Minor"},
    )
    inn = _voll(
        80.0, kick_aktiv=False,
        mood={"brightness": 50.0, "flatness": 0.1, "key_mode": "Minor"},
    )
    weit = _explizite_kandidaten_toleranzen()
    eng = _explizite_kandidaten_toleranzen()
    for key in KANDIDATEN_GEWICHTE:
        weit[key] = eng[key] = 0.0
    weit["kandidaten_mood_weight"] = 1.0
    eng["kandidaten_mood_weight"] = 1.0
    weit["brightness_delta_max"] = 100.0
    eng["brightness_delta_max"] = 10.0

    score_weit, teil_weit, _ = score_pair(a, b, out, inn, 16, tolerances=weit)
    score_eng, teil_eng, _ = score_pair(a, b, out, inn, 16, tolerances=eng)

    assert score_weit > score_eng
    assert teil_weit["mood"] > teil_eng["mood"]


from hpg_core.pair_candidates import rank_pair_candidates, select_pair_candidate


def test_bass_swap_geplant_hebt_kick_abzug_auf():
    a, b = _track(), _track("b.mp3")
    s_ohne, t_ohne, f = score_pair(a, b, _voll(160.0), _voll(80.0), 16)
    s_mit, t_mit, f2 = score_pair(a, b, _voll(160.0), _voll(80.0), 16, bass_swap_geplant=True)
    assert f["bass_swap_pflicht"] and f2["bass_swap_pflicht"]
    assert t_mit["bass"] == pytest.approx(t_ohne["bass"] + 0.15) and s_mit > s_ohne


def test_select_zieht_gespeicherte_wahl_nach_vorn(monkeypatch, tmp_path):
    from hpg_core import candidate_choices as cc
    monkeypatch.setenv("HPG_CANDIDATE_CHOICES_FILE", str(tmp_path / "c.json"))
    cc.reset_cache()
    g = _grid()
    a = _track_mit_kandidaten("a.mp3", outs=[_voll(round(5 * g, 3), kick_aktiv=False),
                                             _voll(round(6 * g, 3), kick_aktiv=False, schema=["sektion"])])
    b = _track_mit_kandidaten("b.mp3", ins=[_voll(round(3 * g, 3), kick_aktiv=False)])
    erst = select_pair_candidate(a, b)
    assert erst is not None and erst.rang == 1
    alle = rank_pair_candidates(a, b)
    letzte = alle[-1]
    cc.merke("a.mp3", "b.mp3", t_out=letzte.t_out, t_in=letzte.t_in, blend_bars=letzte.blend_bars)
    cc.reset_cache()
    gewaehlt = select_pair_candidate(a, b)
    assert (gewaehlt.t_out, gewaehlt.t_in, gewaehlt.blend_bars) == (letzte.t_out, letzte.t_in, letzte.blend_bars)
    assert gewaehlt.rang == 1 and gewaehlt.flags.get("gespeicherte_wahl") is True
    neu = rank_pair_candidates(a, b)
    assert [p.rang for p in neu] == list(range(1, len(neu) + 1))
    cc.merke("a.mp3", "b.mp3", t_out=1.0, t_in=2.0, blend_bars=8)
    cc.reset_cache()
    assert select_pair_candidate(a, b).flags.get("gespeicherte_wahl") is False
    cc.reset_cache()


def test_select_invalidiert_neue_wahl_bei_bpm_abweichung(monkeypatch, tmp_path):
    from hpg_core import candidate_choices as cc
    monkeypatch.setenv("HPG_CANDIDATE_CHOICES_FILE", str(tmp_path / "c.json"))
    cc.reset_cache()
    g = _grid()
    a = _track_mit_kandidaten(
        "a.mp3",
        outs=[
            _voll(round(5 * g, 3), kick_aktiv=False),
            _voll(round(6 * g, 3), kick_aktiv=False, schema=["sektion"]),
        ],
    )
    b = _track_mit_kandidaten(
        "b.mp3", ins=[_voll(round(3 * g, 3), kick_aktiv=False)]
    )
    alle = rank_pair_candidates(a, b, wahl={})
    letzte = alle[-1]
    cc.merke(
        "a.mp3", "b.mp3",
        t_out=letzte.t_out, t_in=letzte.t_in,
        blend_bars=letzte.blend_bars,
        bpm_a=a.bpm + 1.0, bpm_b=b.bpm,
        overlap_sec=letzte.overlap_sec,
    )
    cc.reset_cache()

    neu = rank_pair_candidates(a, b)

    assert neu[0].t_out != pytest.approx(letzte.t_out)
    assert all(not p.flags["gespeicherte_wahl"] for p in neu)
    assert all(p.flags["gespeicherte_wahl_ungueltig"] for p in neu)
    assert {p.flags["gespeicherte_wahl_grund"] for p in neu} == {
        "bpm_a_abweichung"
    }
    cc.reset_cache()


def test_select_priorisiert_identischen_version_2_snapshot_nach_reload(
    monkeypatch, tmp_path
):
    from hpg_core import candidate_choices as cc

    monkeypatch.setenv("HPG_CANDIDATE_CHOICES_FILE", str(tmp_path / "c.json"))
    cc.reset_cache()
    g = _grid()
    a = _track_mit_kandidaten(
        "a.mp3",
        outs=[
            _voll(round(5 * g, 3), kick_aktiv=False),
            _voll(round(6 * g, 3), kick_aktiv=False, schema=["sektion"]),
        ],
    )
    b = _track_mit_kandidaten(
        "b.mp3", ins=[_voll(round(3 * g, 3), kick_aktiv=False)]
    )
    letzte = rank_pair_candidates(a, b, wahl={})[-1]
    cc.merke(
        a.filePath,
        b.filePath,
        t_out=letzte.t_out,
        t_in=letzte.t_in,
        blend_bars=letzte.blend_bars,
        bpm_a=a.bpm,
        bpm_b=b.bpm,
        overlap_sec=letzte.overlap_sec,
    )
    cc.reset_cache()

    neu = rank_pair_candidates(a, b)

    assert neu[0].t_out == pytest.approx(letzte.t_out)
    assert neu[0].t_in == pytest.approx(letzte.t_in)
    assert neu[0].blend_bars == letzte.blend_bars
    assert neu[0].flags["gespeicherte_wahl"] is True
    assert neu[0].flags["gespeicherte_wahl_ungueltig"] is False
    cc.reset_cache()


def test_select_invalidiert_version_2_snapshot_nur_bei_overlap_abweichung(
    monkeypatch, tmp_path
):
    from hpg_core import candidate_choices as cc

    monkeypatch.setenv("HPG_CANDIDATE_CHOICES_FILE", str(tmp_path / "c.json"))
    cc.reset_cache()
    g = _grid()
    a = _track_mit_kandidaten(
        "a.mp3",
        outs=[
            _voll(round(5 * g, 3), kick_aktiv=False),
            _voll(round(6 * g, 3), kick_aktiv=False, schema=["sektion"]),
        ],
    )
    b = _track_mit_kandidaten(
        "b.mp3", ins=[_voll(round(3 * g, 3), kick_aktiv=False)]
    )
    letzte = rank_pair_candidates(a, b, wahl={})[-1]
    cc.merke(
        a.filePath,
        b.filePath,
        t_out=letzte.t_out,
        t_in=letzte.t_in,
        blend_bars=letzte.blend_bars,
        bpm_a=a.bpm,
        bpm_b=b.bpm,
        overlap_sec=letzte.overlap_sec + 0.001,
    )
    cc.reset_cache()

    neu = rank_pair_candidates(a, b)

    assert all(not p.flags["gespeicherte_wahl"] for p in neu)
    assert all(p.flags["gespeicherte_wahl_ungueltig"] for p in neu)
    assert {p.flags["gespeicherte_wahl_grund"] for p in neu} == {
        "overlap_sec_abweichung"
    }
    cc.reset_cache()


def test_select_none_ohne_kandidaten():
    a, b = _track(), _track("b.mp3")
    assert select_pair_candidate(a, b) is None and rank_pair_candidates(a, b) == []


def test_rank_pair_candidates_respektiert_uebergebene_bpm_toleranz():
    a = _track_mit_kandidaten(
        "a.mp3", bpm=140.0, outs=[_voll(round(6 * _grid(), 3), kick_aktiv=False)]
    )
    b = _track_mit_kandidaten(
        "b.mp3", bpm=141.5,
        ins=[_voll(round(3 * _grid(141.5), 3), kick_aktiv=False)],
    )

    assert rank_pair_candidates(a, b, bpm_tolerance=2.0)
    assert rank_pair_candidates(a, b, bpm_tolerance=1.0) == []


def test_schema_rang_aus_praeferenzen_bricht_gleichstand(monkeypatch):
    from hpg_core import candidate_preferences as cp
    g = _grid()
    o1 = _voll(round(5 * g, 3), kick_aktiv=False)                       # pssi_phrase
    o2 = _voll(round(6 * g, 3), kick_aktiv=False, schema=["sektion"])   # gleicher Score
    a = _track_mit_kandidaten("a.mp3", outs=[o1, o2])
    b = _track_mit_kandidaten("b.mp3", ins=[_voll(round(3 * g, 3), kick_aktiv=False)])
    assert "pssi_phrase" in select_pair_candidate(a, b).out_a.schema
    monkeypatch.setattr(cp, "schema_rangfolge", lambda genre: ["sektion", "pssi_phrase"])
    assert "sektion" in select_pair_candidate(a, b).out_a.schema


def test_explizit_leerer_schema_rang_laesst_live_praeferenz_unberuehrt(monkeypatch):
    from hpg_core import candidate_preferences as cp
    g = _grid()
    a = _track_mit_kandidaten(
        "a.mp3", outs=[_voll(round(5 * g, 3), kick_aktiv=False)]
    )
    b = _track_mit_kandidaten(
        "b.mp3", ins=[_voll(round(3 * g, 3), kick_aktiv=False)]
    )
    live = Mock(side_effect=AssertionError("Live-Praeferenz abgefragt"))
    monkeypatch.setattr(cp, "schema_rangfolge", live)

    assert rank_pair_candidates(a, b, schema_rang=[])
    live.assert_not_called()


def test_gate_blende_ueber_b_ende():
    a, b = _track(), _track("b.mp3", duration=200.0)
    g = _grid()
    # In bei 6g = 164.6 s, Blende 32 Takte = 54.9 s -> 219.5 s > 200 s Dauer von B
    assert "blende_ueber_b_ende" in pair_gate_reasons(a, b, _out(round(6 * g, 3)), _in(round(6 * g, 3)), 32)
    assert "blende_ueber_b_ende" not in pair_gate_reasons(a, b, _out(round(6 * g, 3)), _in(round(3 * g, 3)), 32)
    bk = _track_mit_kandidaten("b.mp3", ins=[_voll(round(6 * g, 3), kick_aktiv=False)])
    bk.duration = 200.0
    res = build_pair_candidates(_track_mit_kandidaten("a.mp3", outs=[_voll(round(6 * g, 3), kick_aktiv=False)]), bk)
    assert res and {p.blend_bars for p in res} == {16}   # 32 Takte (54.9 s) passen ab 164.6 s nicht in 200 s
