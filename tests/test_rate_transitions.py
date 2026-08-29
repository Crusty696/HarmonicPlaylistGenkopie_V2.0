"""Tests fuer das Hoertest-Werkzeug tools/rate_transitions.py.

Geprueft wird ausschliesslich die REINE Logik: Maximin-Auswahl, CSV-Verbinden,
Log-Likelihood, Bootstrap, Gewichtsableitung und das Datenlage-Urteil.

Kein Test rendert Audio und kein Test liest die Cache-Datenbank des Nutzers —
beides waere langsam, nicht reproduzierbar und wuerde fremde Daten anfassen.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import math
import json
import hashlib
import sqlite3
import csv
from dataclasses import replace as dataclass_replace
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
import soundfile as sf

from hpg_core.playlist import TransitionPlan

from tools import rate_transitions
from tools.rate_transitions import (
    ALLE_FAKTOREN,
    BUDGET_MAX,
    CROSSFADE_SEK,
    POST_ROLL_SEK,
    crossfade_reserve,
    L2_STAERKE,
    MIN_EREIGNISSE_JE_MERKMAL,
    NEUE_FAKTOREN,
    baue_genre_gewichte,
    bootstrap_intervalle,
    datenlage_urteil,
    filtere_nach_genre,
    fit_logistic,
    leite_gewichte_ab,
    maximin_auswahl,
    negative_log_likelihood,
    streuung,
    verbinde_bewertungen,
    waehle_merkmale,
    zu_zielgroesse,
)


# ---------------------------------------------------------------------------
# Maximin-Auswahl
# ---------------------------------------------------------------------------

def test_maximin_waehlt_die_extreme():
    """Aus einem Klumpen plus zwei Extremen muessen die Extreme kommen."""
    punkte = [
        [0.0, 0.0, 0.0, 0.0],   # Extrem unten
        [0.5, 0.5, 0.5, 0.5],   # Klumpen
        [0.51, 0.5, 0.5, 0.5],  # Klumpen
        [0.49, 0.5, 0.5, 0.5],  # Klumpen
        [1.0, 1.0, 1.0, 1.0],   # Extrem oben
    ]
    gewaehlt = maximin_auswahl(punkte, anzahl=3, start=0)
    assert gewaehlt[0] == 0
    assert set(gewaehlt) >= {0, 4}


def test_maximin_deterministisch_bei_gleichem_seed():
    rng = np.random.default_rng(7)
    punkte = rng.random((40, 4)).tolist()
    erste = maximin_auswahl(punkte, anzahl=10, seed=123)
    zweite = maximin_auswahl(punkte, anzahl=10, seed=123)
    assert erste == zweite


def test_maximin_liefert_keine_doppelten_und_nicht_mehr_als_vorhanden():
    punkte = [[0.0, 0.0, 0.0, 0.0], [1.0, 1.0, 1.0, 1.0], [0.2, 0.2, 0.2, 0.2]]
    gewaehlt = maximin_auswahl(punkte, anzahl=99, seed=1)
    assert sorted(gewaehlt) == [0, 1, 2]


def test_maximin_leere_eingabe():
    assert maximin_auswahl([], anzahl=5, seed=1) == []


# ---------------------------------------------------------------------------
# CSV-Verbinden
# ---------------------------------------------------------------------------

def _merkmalszeile(pair_id, **werte):
    zeile = {"pair_id": pair_id, "track_a": "a.wav", "track_b": "b.wav"}
    for name in ALLE_FAKTOREN:
        zeile[name] = str(werte.get(name, 0.5))
    return zeile


def test_verbinden_ueberspringt_leere_und_ungueltige_bewertungen():
    merkmale = [_merkmalszeile("001"), _merkmalszeile("002"), _merkmalszeile("003"),
                _merkmalszeile("004")]
    bewertungen = [
        {"pair_id": "001", "clip": "x", "bewertung": "5"},
        {"pair_id": "002", "clip": "x", "bewertung": ""},     # leer
        {"pair_id": "003", "clip": "x", "bewertung": "9"},    # ausserhalb 1..5
        # 004 fehlt in der Bewertungsdatei komplett
    ]
    zeilen, ohne, ungueltig = verbinde_bewertungen(merkmale, bewertungen)
    assert [z["pair_id"] for z in zeilen] == ["001"]
    assert zeilen[0]["bewertung"] == 5
    assert ohne == 2
    assert ungueltig == 1


def test_verbinden_uebernimmt_merkmale_als_float():
    merkmale = [_merkmalszeile("001", groove=0.25, mood=0.75)]
    bewertungen = [{"pair_id": "001", "clip": "x", "bewertung": "4"}]
    zeilen, _, _ = verbinde_bewertungen(merkmale, bewertungen)
    assert zeilen[0]["merkmale"]["groove"] == pytest.approx(0.25)
    assert zeilen[0]["merkmale"]["mood"] == pytest.approx(0.75)


def test_merkmalswahl_verwirft_konstante_kontrollvariablen():
    """Klassische Faktoren ohne Streuung kosten nur Freiheitsgrade."""
    rng = np.random.default_rng(11)
    zeilen = []
    for i in range(50):
        merkmale = {n: float(rng.random()) for n in NEUE_FAKTOREN}
        # harmonic streut kraeftig, die drei anderen sind praktisch konstant
        # (so wirkt der prepare-Filter: harmonic >= 60, BPM in Toleranz).
        merkmale["harmonic"] = float(rng.random())
        merkmale["bpm"] = 0.9 + 0.001 * (i % 3)
        merkmale["energy"] = 0.8
        merkmale["genre"] = 1.0
        zeilen.append({"pair_id": str(i), "bewertung": 4, "merkmale": merkmale})

    aktiv, streuungen = waehle_merkmale(zeilen)
    assert set(NEUE_FAKTOREN) <= set(aktiv)
    assert "harmonic" in aktiv
    assert "bpm" not in aktiv and "energy" not in aktiv and "genre" not in aktiv
    assert streuungen["genre"] == pytest.approx(0.0)


def test_merkmalswahl_behaelt_streuende_kontrollvariablen():
    rng = np.random.default_rng(12)
    zeilen = [
        {
            "pair_id": str(i),
            "bewertung": 3,
            "merkmale": {n: float(rng.random()) for n in ALLE_FAKTOREN},
        }
        for i in range(60)
    ]
    aktiv, _ = waehle_merkmale(zeilen)
    assert aktiv == list(ALLE_FAKTOREN)


def test_zielgroesse_beschraenkt_sich_auf_die_aktiven_merkmale():
    zeilen = [
        {"pair_id": "1", "bewertung": 5, "merkmale": {n: 0.5 for n in ALLE_FAKTOREN}},
        {"pair_id": "2", "bewertung": 1, "merkmale": {n: 0.5 for n in ALLE_FAKTOREN}},
    ]
    X, y = zu_zielgroesse(zeilen, list(NEUE_FAKTOREN))
    assert X.shape == (2, len(NEUE_FAKTOREN))
    assert list(y) == [1.0, 0.0]


def test_datenlage_richtet_sich_nach_der_tatsaechlichen_merkmalszahl():
    """Nur die vier neuen Faktoren -> 40 Ereignisse je Klasse genuegen."""
    belastbar, _ = datenlage_urteil(40, 40, len(NEUE_FAKTOREN))
    assert belastbar is True
    # Dieselben Zahlen reichen bei acht Merkmalen NICHT.
    belastbar_acht, _ = datenlage_urteil(40, 40, len(ALLE_FAKTOREN))
    assert belastbar_acht is False


def test_zielgroesse_gut_ab_vier():
    zeilen = [
        {"pair_id": "1", "bewertung": 3, "merkmale": {n: 0.5 for n in ALLE_FAKTOREN}},
        {"pair_id": "2", "bewertung": 4, "merkmale": {n: 0.5 for n in ALLE_FAKTOREN}},
        {"pair_id": "3", "bewertung": 5, "merkmale": {n: 0.5 for n in ALLE_FAKTOREN}},
    ]
    X, y = zu_zielgroesse(zeilen)
    assert X.shape == (3, len(ALLE_FAKTOREN))
    assert list(y) == [0.0, 1.0, 1.0]


# ---------------------------------------------------------------------------
# Log-Likelihood
# ---------------------------------------------------------------------------

def test_nll_bei_nullkoeffizienten_ist_n_mal_log_zwei():
    """Alle Koeffizienten 0 -> Wahrscheinlichkeit 0,5 je Zeile, Strafterm 0."""
    X = np.array([[0.3, -0.2], [1.0, 0.5], [-0.4, 0.9]])
    y = np.array([1.0, 0.0, 1.0])
    beta = np.zeros(3)
    erwartet = 3 * math.log(2.0)
    assert negative_log_likelihood(beta, X, y, 1.0) == pytest.approx(erwartet)


def test_nll_bestraft_nur_die_steigungen_nicht_den_achsenabschnitt():
    X = np.zeros((2, 2))
    y = np.array([1.0, 0.0])
    nur_achse = negative_log_likelihood(np.array([2.0, 0.0, 0.0]), X, y, 1.0)
    mit_steigung = negative_log_likelihood(np.array([2.0, 1.0, 0.0]), X, y, 1.0)
    # X ist Null, die Likelihood ist also identisch; der Unterschied ist reine Strafe.
    assert mit_steigung - nur_achse == pytest.approx(1.0)


def test_regression_findet_genau_den_einen_faktor():
    """Nur `groove` bestimmt das Urteil — der Fit muss genau das zeigen."""
    rng = np.random.default_rng(42)
    n = 240
    X = rng.random((n, len(ALLE_FAKTOREN)))
    groove_index = ALLE_FAKTOREN.index("groove")
    y = (X[:, groove_index] > 0.5).astype(float)

    beta = fit_logistic(X, y, L2_STAERKE)
    steigungen = beta[1:]
    assert len(steigungen) == len(ALLE_FAKTOREN)
    # Der wahre Faktor hat den groessten Betrag und zeigt in die richtige Richtung.
    assert int(np.argmax(np.abs(steigungen))) == groove_index
    assert steigungen[groove_index] > 0.0

    intervalle = bootstrap_intervalle(X, y, L2_STAERKE, ziehungen=120, seed=5)
    unten, oben = intervalle["groove"]
    assert unten > 0.0 and oben > unten


def test_bootstrap_reproduzierbar_bei_gleichem_seed():
    rng = np.random.default_rng(3)
    X = rng.random((60, len(ALLE_FAKTOREN)))
    y = (X[:, 0] + rng.normal(0, 0.1, 60) > 0.5).astype(float)
    erste = bootstrap_intervalle(X, y, L2_STAERKE, ziehungen=60, seed=99)
    zweite = bootstrap_intervalle(X, y, L2_STAERKE, ziehungen=60, seed=99)
    for name in ALLE_FAKTOREN:
        assert erste[name] == pytest.approx(zweite[name])


# ---------------------------------------------------------------------------
# Datenlage
# ---------------------------------------------------------------------------

def test_datenlage_zu_duenn_bei_vierzig_bewertungen():
    belastbar, text = datenlage_urteil(20, 20, len(ALLE_FAKTOREN))
    assert belastbar is False
    assert "nicht belastbar" in text.lower()


def test_datenlage_zu_duenn_wenn_nur_eine_seite_fehlt():
    noetig = MIN_EREIGNISSE_JE_MERKMAL * len(ALLE_FAKTOREN)
    belastbar, _ = datenlage_urteil(noetig, noetig - 1, len(ALLE_FAKTOREN))
    assert belastbar is False


def test_datenlage_ausreichend_ab_achtzig_je_klasse():
    noetig = MIN_EREIGNISSE_JE_MERKMAL * len(ALLE_FAKTOREN)
    assert noetig == 80
    belastbar, _ = datenlage_urteil(noetig, noetig, len(ALLE_FAKTOREN))
    assert belastbar is True


# ---------------------------------------------------------------------------
# Gewichtsableitung
# ---------------------------------------------------------------------------

def test_gewicht_nur_fuer_faktoren_deren_intervall_die_null_nicht_enthaelt():
    koeffizienten = {"groove": 1.2, "bass": 0.4, "timbre": -0.9, "mood": 0.1}
    intervalle = {
        "groove": (0.6, 1.8),    # gesichert positiv
        "bass": (-0.1, 0.9),     # enthaelt die Null
        "timbre": (-1.4, -0.4),  # gesichert NEGATIV -> trotzdem kein Gewicht
        "mood": (-0.5, 0.7),     # enthaelt die Null
    }
    gewichte = leite_gewichte_ab(koeffizienten, intervalle, belastbar=True)
    assert gewichte["groove"] > 0.0
    assert gewichte["bass"] == 0.0
    assert gewichte["timbre"] == 0.0
    assert gewichte["mood"] == 0.0


def test_budget_ist_gedeckelt_und_waechst_mit_dem_besten_faktor():
    stark = leite_gewichte_ab(
        {n: 3.0 for n in NEUE_FAKTOREN},
        {n: (2.0, 4.0) for n in NEUE_FAKTOREN},
        belastbar=True,
    )
    assert sum(stark.values()) == pytest.approx(BUDGET_MAX)

    schwach = leite_gewichte_ab(
        {n: 0.2 for n in NEUE_FAKTOREN},
        {n: (0.1, 0.3) for n in NEUE_FAKTOREN},
        belastbar=True,
    )
    assert 0.0 < sum(schwach.values()) < BUDGET_MAX


def test_kein_gewicht_wenn_keiner_ueberlebt():
    gewichte = leite_gewichte_ab(
        {n: 0.1 for n in NEUE_FAKTOREN},
        {n: (-0.5, 0.7) for n in NEUE_FAKTOREN},
        belastbar=True,
    )
    assert sum(gewichte.values()) == 0.0


def test_kein_gewicht_bei_zu_duenner_datenlage():
    """Auch ein scheinbar gesicherter Faktor bekommt nichts, wenn zu wenig da ist."""
    gewichte = leite_gewichte_ab(
        {n: 3.0 for n in NEUE_FAKTOREN},
        {n: (2.0, 4.0) for n in NEUE_FAKTOREN},
        belastbar=False,
    )
    assert sum(gewichte.values()) == 0.0


def test_genre_gewichte_summieren_auf_eins():
    neue = {"groove": 0.15, "bass": 0.05, "timbre": 0.0, "mood": 0.0}
    alle = baue_genre_gewichte(neue)
    assert sum(alle.values()) == pytest.approx(1.0)
    assert alle["groove_weight"] == pytest.approx(0.15)
    assert alle["timbre_weight"] == 0.0
    # Die vier klassischen Faktoren fuellen den Rest im Verhaeltnis der Defaults.
    assert alle["harmonic_weight"] > alle["genre_weight"] > 0.0


def test_genre_gewichte_bei_budget_null_sind_die_defaults():
    alle = baue_genre_gewichte({n: 0.0 for n in NEUE_FAKTOREN})
    assert sum(alle.values()) == pytest.approx(1.0)
    assert all(alle[f"{n}_weight"] == 0.0 for n in NEUE_FAKTOREN)


# ---------------------------------------------------------------------------
# Streuungs-Bericht
# ---------------------------------------------------------------------------

def test_streuung_liefert_min_median_max():
    werte = streuung([0.1, 0.5, 0.9, 0.3])
    assert werte["min"] == pytest.approx(0.1)
    assert werte["max"] == pytest.approx(0.9)
    assert werte["median"] == pytest.approx(0.4)


def test_crossfade_reserve_reicht_bei_langen_tracks():
    rest_a, rest_b = crossfade_reserve(
        mix_out_a=400.0, dauer_a=460.0, dauer_b=420.0, mix_in_b=100.0
    )
    assert rest_a == pytest.approx(460.0 - 400.0)
    assert rest_b == pytest.approx(420.0 - 100.0 - POST_ROLL_SEK)
    assert min(rest_a, rest_b) >= CROSSFADE_SEK


def test_crossfade_reserve_erkennt_zu_spaeten_mix_in():
    """Mix-In dicht am Ende von Track B — die Blende passt nicht mehr."""
    _rest_a, rest_b = crossfade_reserve(
        mix_out_a=400.0, dauer_a=460.0, dauer_b=420.0, mix_in_b=418.0
    )
    assert rest_b < CROSSFADE_SEK


class _FakeTrack:
    """Minimaler Track fuer den Spec-Aufbau in rendere_paar."""
    def __init__(self, pfad, bpm, dauer, first_downbeat, confidence):
        self.filePath = pfad
        self.bpm = bpm
        self.duration = dauer
        self.first_downbeat = first_downbeat
        self.downbeat_confidence = confidence
        self.mix_in_point = 30.0
        self.mix_out_point = dauer - 60.0
        self.sections = [
            {"start_time": 0.0, "end_time": 30.0, "label": "intro"},
            {"start_time": 30.0, "end_time": dauer - 60.0, "label": "main"},
            {"start_time": dauer - 60.0, "end_time": dauer, "label": "outro"},
        ]
        self.detected_genre = "Psytrance"
        self.genre = "Psytrance"
        self.phrase_anchor = first_downbeat
        self.beatgrid_source = "rekordbox"
        self.beatgrid_status = "verified"
        self.analysis_mode = "rekordbox_fast"


def _plan_empfehlung(a, b, *, rang=1, overlap=32.0, kandidat_overlap=32.0,
                     mix_out=300.0, mix_in=30.0, kandidaten=None):
    plan = TransitionPlan(
        mix_out_a=mix_out, mix_in_b=mix_in, fade_out_start=mix_out,
        fade_out_end=mix_out + overlap, overlap=overlap,
        transition_type="bass_swap", target_sr=48000,
        tempo_ratio=float(b.bpm) / float(a.bpm),
    )
    if kandidaten is None:
        kandidaten = [{
            "rang": rang, "t_out": mix_out, "t_in": mix_in,
            "overlap_sec": kandidat_overlap,
        }]
    return SimpleNamespace(
        index=0, from_track=a, to_track=b, plan=plan,
        kandidat_aktiv=rang, kandidaten=kandidaten,
    )


def _fake_render(monkeypatch, gesehen):
    def render(spec, ziel):
        gesehen["spec"] = spec
        Path(ziel).write_bytes(b"RIFF")
    monkeypatch.setattr(rate_transitions, "render_transition_clip", render)


def test_rendere_paar_nutzt_plan_als_einzige_timingquelle_und_reicht_bpm_weiter(
    monkeypatch, tmp_path
):
    a = _FakeTrack("A.wav", 140.0, 400.0, 0.0123, 1.0)
    b = _FakeTrack("B.wav", 141.0, 400.0, 0.0456, 1.0)
    gesehen = {}
    emp = _plan_empfehlung(a, b, rang=2, overlap=24.0, kandidat_overlap=32.0)

    def compute(tracks, *, bpm_tolerance, scoring_context):
        gesehen["tracks"] = tracks
        gesehen["bpm_tolerance"] = bpm_tolerance
        gesehen["scoring_context"] = scoring_context
        return [emp]

    monkeypatch.setattr(rate_transitions, "compute_transition_recommendations", compute)
    _fake_render(monkeypatch, gesehen)
    clip, plan, aktiv = rate_transitions.rendere_paar(
        {"track_a": a, "track_b": b}, "001", tmp_path,
        bpm_toleranz=1.75, energy_direction="up",
    )

    assert gesehen["tracks"] == [a, b]
    assert gesehen["bpm_tolerance"] == pytest.approx(1.75)
    assert gesehen["scoring_context"] == {"energy_direction": "up"}
    assert clip == "clips/001.wav"
    assert plan is emp.plan
    assert aktiv["rang"] == 2
    spec = gesehen["spec"]
    assert (spec.mix_out_sec, spec.mix_in_sec, spec.crossfade_sec) == (300.0, 30.0, 24.0)
    assert spec.transition_type == "bass_swap"
    assert spec.target_sr == 48000
    assert spec.pre_roll_sec == rate_transitions.PRE_ROLL_SEK
    assert spec.post_roll_sec == rate_transitions.POST_ROLL_SEK
    assert spec.strict_beat_sync is True
    assert spec.bar_phase_reliable_a is True
    assert spec.bar_phase_reliable_b is True


def test_rendere_paar_findet_tatsaechlich_aktiven_rang_zwei(monkeypatch, tmp_path):
    a = _FakeTrack("A.wav", 140.0, 400.0, 0.0, 1.0)
    b = _FakeTrack("B.wav", 140.0, 400.0, 0.0, 1.0)
    kandidaten = [
        {"rang": 1, "t_out": 280.0, "t_in": 20.0, "overlap_sec": 32.0},
        {"rang": 2, "t_out": 300.0, "t_in": 30.0, "overlap_sec": 32.0},
    ]
    emp = _plan_empfehlung(a, b, rang=2, kandidaten=kandidaten)
    monkeypatch.setattr(rate_transitions, "compute_transition_recommendations", lambda *a_, **k: [emp])
    _fake_render(monkeypatch, {})
    _clip, _plan, aktiv = rate_transitions.rendere_paar(
        {"track_a": a, "track_b": b}, "002", tmp_path
    )
    assert aktiv is kandidaten[1]


@pytest.mark.parametrize("aenderung", [
    {"plan": None},
    {"kandidat_aktiv": 0},
    {"kandidat_aktiv": 3},
])
def test_rendere_paar_verwirft_planlos_oder_ohne_aktiven_rang(
    monkeypatch, tmp_path, aenderung
):
    a = _FakeTrack("A.wav", 140.0, 400.0, 0.0, 1.0)
    b = _FakeTrack("B.wav", 140.0, 400.0, 0.0, 1.0)
    emp = _plan_empfehlung(a, b)
    for name, wert in aenderung.items():
        setattr(emp, name, wert)
    monkeypatch.setattr(rate_transitions, "compute_transition_recommendations", lambda *a_, **k: [emp])
    with pytest.raises(ValueError):
        rate_transitions.rendere_paar({"track_a": a, "track_b": b}, "003", tmp_path)


def test_rendere_paar_verwirft_fremdes_paar_und_mixpunkt_mismatch(monkeypatch, tmp_path):
    a = _FakeTrack("A.wav", 140.0, 400.0, 0.0, 1.0)
    b = _FakeTrack("B.wav", 140.0, 400.0, 0.0, 1.0)
    fremd = _plan_empfehlung(a, _FakeTrack("C.wav", 140.0, 400.0, 0.0, 1.0))
    monkeypatch.setattr(rate_transitions, "compute_transition_recommendations", lambda *x, **k: [fremd])
    with pytest.raises(ValueError, match="anderen Track-Paar"):
        rate_transitions.rendere_paar({"track_a": a, "track_b": b}, "004", tmp_path)

    mismatch = _plan_empfehlung(a, b, mix_out=300.0)
    mismatch.kandidaten[0]["t_out"] = 300.0 + rate_transitions.QUANTIZE_TOLERANCE_SEC + 0.001
    monkeypatch.setattr(rate_transitions, "compute_transition_recommendations", lambda *x, **k: [mismatch])
    with pytest.raises(ValueError, match="stimmt nicht"):
        rate_transitions.rendere_paar({"track_a": a, "track_b": b}, "004", tmp_path)


def test_rendere_paar_akzeptiert_positiv_geklemmten_plan_overlap(monkeypatch, tmp_path):
    a = _FakeTrack("A.wav", 140.0, 400.0, 0.0, 1.0)
    b = _FakeTrack("B.wav", 140.0, 400.0, 0.0, 1.0)
    emp = _plan_empfehlung(a, b, overlap=17.3, kandidat_overlap=32.0)
    monkeypatch.setattr(rate_transitions, "compute_transition_recommendations", lambda *x, **k: [emp])
    gesehen = {}
    _fake_render(monkeypatch, gesehen)
    rate_transitions.rendere_paar({"track_a": a, "track_b": b}, "005", tmp_path)
    assert gesehen["spec"].crossfade_sec == pytest.approx(17.3)


@pytest.mark.parametrize("index", [False, 0.0, "0"])
def test_rendere_paar_verwirft_nicht_exakt_ganzzahligen_empfehlungsindex(
    monkeypatch, tmp_path, index
):
    a = _FakeTrack("A.wav", 140.0, 400.0, 0.0, 1.0)
    b = _FakeTrack("B.wav", 140.0, 400.0, 0.0, 1.0)
    emp = _plan_empfehlung(a, b)
    emp.index = index
    monkeypatch.setattr(rate_transitions, "compute_transition_recommendations", lambda *x, **k: [emp])
    with pytest.raises(ValueError, match="Paar-Index 0"):
        rate_transitions.rendere_paar({"track_a": a, "track_b": b}, "006", tmp_path)


@pytest.mark.parametrize("aktiver_rang", [True, 1.0, "1"])
def test_rendere_paar_verwirft_nicht_exakt_ganzzahligen_aktiven_rang(
    monkeypatch, tmp_path, aktiver_rang
):
    a = _FakeTrack("A.wav", 140.0, 400.0, 0.0, 1.0)
    b = _FakeTrack("B.wav", 140.0, 400.0, 0.0, 1.0)
    emp = _plan_empfehlung(a, b)
    emp.kandidat_aktiv = aktiver_rang
    monkeypatch.setattr(rate_transitions, "compute_transition_recommendations", lambda *x, **k: [emp])
    with pytest.raises(ValueError, match="aktiven PairCandidate"):
        rate_transitions.rendere_paar({"track_a": a, "track_b": b}, "006", tmp_path)


@pytest.mark.parametrize("kandidat_rang", [True, 1.0, "1"])
def test_rendere_paar_verwirft_nicht_exakt_ganzzahligen_kandidatenrang(
    monkeypatch, tmp_path, kandidat_rang
):
    a = _FakeTrack("A.wav", 140.0, 400.0, 0.0, 1.0)
    b = _FakeTrack("B.wav", 140.0, 400.0, 0.0, 1.0)
    emp = _plan_empfehlung(a, b)
    emp.kandidaten[0]["rang"] = kandidat_rang
    monkeypatch.setattr(rate_transitions, "compute_transition_recommendations", lambda *x, **k: [emp])
    with pytest.raises(ValueError, match="positive Ganzzahl"):
        rate_transitions.rendere_paar({"track_a": a, "track_b": b}, "007", tmp_path)


@pytest.mark.parametrize(
    ("kandidat_feld", "kandidat_wert", "plan_aenderung", "meldung"),
    [
        ("t_out", -0.001, {}, "Trackdauer"),
        ("t_in", 400.0, {}, "Trackdauer"),
        ("t_out", float("nan"), {}, "nicht-endliche"),
        (None, None, {"mix_out_a": -0.001, "fade_out_start": -0.001}, "Trackdauer"),
        (None, None, {"mix_in_b": 400.0}, "Trackdauer"),
        (None, None, {"fade_out_start": 300.051}, "Fade-Grenzen"),
        (None, None, {"fade_out_end": 332.051}, "Fade-Grenzen"),
    ],
)
def test_rendere_paar_validiert_plan_und_kandidatenzeitvertrag(
    monkeypatch, tmp_path, kandidat_feld, kandidat_wert, plan_aenderung, meldung
):
    a = _FakeTrack("A.wav", 140.0, 400.0, 0.0, 1.0)
    b = _FakeTrack("B.wav", 140.0, 400.0, 0.0, 1.0)
    emp = _plan_empfehlung(a, b)
    if kandidat_feld is not None:
        emp.kandidaten[0][kandidat_feld] = kandidat_wert
    if plan_aenderung:
        emp.plan = dataclass_replace(emp.plan, **plan_aenderung)
    monkeypatch.setattr(rate_transitions, "compute_transition_recommendations", lambda *x, **k: [emp])
    with pytest.raises(ValueError, match=meldung):
        rate_transitions.rendere_paar({"track_a": a, "track_b": b}, "008", tmp_path)


def test_normaler_hoertest_hat_keinen_alten_mixpunkt_oder_overlap_pfad():
    assert not hasattr(rate_transitions, "calculate_paired_mix_points")
    assert not hasattr(rate_transitions, "geplanter_overlap")


def test_crossfade_reserve_erkennt_zu_wenig_audio_hinter_mix_out_a():
    """Track A endet kurz nach dem Mix-Out — die Blende liefe in Stille.

    Regression zum Fix 2026-08-20: die A-Seite mass vorher das Audio VOR dem
    Mix-Out (mix_out_a minus Vorlauf) und haette hier 392 s Reserve gemeldet,
    obwohl real nur 17,3 s hinter dem Mix-Out liegen. _ensure_len haette den
    Rest still mit Nullen aufgefuellt.
    """
    rest_a, _rest_b = crossfade_reserve(
        mix_out_a=400.0, dauer_a=417.3, dauer_b=420.0, mix_in_b=100.0
    )
    assert rest_a == pytest.approx(17.3)
    assert rest_a < CROSSFADE_SEK


def test_streuung_leer():
    werte = streuung([])
    assert werte == {"min": None, "median": None, "max": None}


# ---------------------------------------------------------------------------
# Genre-Filter fuer prepare
# ---------------------------------------------------------------------------

class _GenreTrack:
    """Minimaler Track-Ersatz: `loese_genre_auf` liest genau diese zwei Felder."""

    def __init__(self, detected_genre="", genre=""):
        self.detected_genre = detected_genre
        self.genre = genre


def _paar(a, b):
    return {"track_a": a, "track_b": b, "merkmale": {}}


def test_filtere_nach_genre_behaelt_nur_reine_paare():
    psy = _GenreTrack(detected_genre="Psytrance")
    techno = _GenreTrack(detected_genre="Techno")
    kandidaten = [_paar(psy, psy), _paar(psy, techno), _paar(techno, techno)]
    ergebnis = filtere_nach_genre(kandidaten, "Psytrance")
    assert len(ergebnis) == 1
    assert ergebnis[0]["track_a"] is psy and ergebnis[0]["track_b"] is psy


def test_filtere_nach_genre_wirft_wechsel_in_beide_richtungen_weg():
    psy = _GenreTrack(detected_genre="Psytrance")
    techno = _GenreTrack(detected_genre="Techno")
    kandidaten = [_paar(psy, techno), _paar(techno, psy)]
    assert filtere_nach_genre(kandidaten, "Psytrance") == []


def test_filtere_nach_genre_nutzt_dieselbe_aufloesung_wie_das_scoring():
    """Erkanntes Genre schlaegt das Tag — sonst haette der Satz eine andere
    Genre-Sicht als die Bewertung, die er steuert."""
    getaggt = _GenreTrack(detected_genre="Psytrance", genre="Techno")
    kandidaten = [_paar(getaggt, getaggt)]
    assert len(filtere_nach_genre(kandidaten, "Psytrance")) == 1
    assert filtere_nach_genre(kandidaten, "Techno") == []


def test_filtere_nach_genre_ignoriert_unknown():
    unbekannt = _GenreTrack()
    kandidaten = [_paar(unbekannt, unbekannt)]
    assert filtere_nach_genre(kandidaten, "Psytrance") == []


def test_filtere_nach_genre_leere_eingabe_bleibt_leer():
    assert filtere_nach_genre([], "Psytrance") == []


class _GateTrack:
    """Minimaler Track fuer sammle_kandidaten (BPM, Pfad, LUFS)."""
    def __init__(self, pfad, bpm, lufs=-9.0):
        self.filePath = pfad
        self.bpm = bpm
        self.lufs = lufs


class _Metrik:
    def __init__(self, harmonic=80, overall=0.8):
        self.harmonic_score = harmonic
        self.overall_score = overall


def _faktoren_mit(groove):
    return {"groove": groove, "bass": 0.7, "timbre": 0.7, "mood": 0.7,
            "harmonic": 0.8, "bpm": 0.9, "energy": 0.8, "genre": 1.0,
            "loudness": 0.8, "structure": 0.7}


def _lokaler_pc(groove=0.8, score=0.8, harmonic=0.8):
    teil = _faktoren_mit(groove)
    teil["harmonic"] = harmonic
    pc = _pc(300.0, 40.0, 16, score, teil=teil)
    muster = [0.8 if index % 4 == 0 else 0.0 for index in range(16)]
    for kandidat in (pc.out_a, pc.in_b):
        kandidat.camelot_lokal = "8A"
        kandidat.energy_lokal = 70
        kandidat.groove_pattern_lokal = list(muster)
        kandidat.bass_pattern_lokal = list(muster)
        kandidat.sub_energy = 0.5
        kandidat.bass_punch = 2.0
        kandidat.timbre_fingerprint_lokal = [1.0, 0.5, 0.2]
        kandidat.mood = {"pssi_mood": 1}
        kandidat.lufs_lokal = -10.0
        kandidat.section_label = "main"
    pc.out_a.lufs_lokal = -8.0
    pc.in_b.lufs_lokal = -11.5
    return pc


def test_sammle_kandidaten_bpm_grenze_ist_zwei_scoring_app_default():
    assert rate_transitions.STANDARD_BPM_TOLERANZ == 2.0
    assert rate_transitions.SCORING_BPM_TOLERANZ == 3.0


def test_sammle_kandidaten_nutzt_den_lokalen_app_kandidatenpfad(monkeypatch):
    gesehen = {}
    def fake_build(x, y, **kwargs):
        gesehen["called"] = (x.filePath, y.filePath)
        gesehen["kwargs"] = kwargs
        return [_lokaler_pc()]
    monkeypatch.setattr(rate_transitions, "rank_pair_candidates", fake_build)
    rate_transitions.sammle_kandidaten(
        [_GateTrack("A.wav", 140.0), _GateTrack("B.wav", 141.0)],
        1.75,
        "up",
    )
    assert set(gesehen["called"]) == {"A.wav", "B.wav"}
    assert gesehen["kwargs"] == {"bpm_tolerance": 1.75, "energy_direction": "up"}


def test_sammle_kandidaten_gates_overall_und_groove(monkeypatch):
    """Nur Paare, die die App mit ALLEN Gewichten als solide sieht
    (overall >= 0.70) und deren Groove >= 0.5 ist, kommen in den Hoertest."""
    a = _GateTrack("A.wav", 140.0, lufs=-8.0)
    b = _GateTrack("B.wav", 141.0, lufs=-11.5)
    faelle = [
        (_Metrik(overall=0.8), 0.7, True),
        (_Metrik(overall=0.70), 0.7, True),   # Grenze inklusive
        (_Metrik(overall=0.65), 0.7, False),  # overall unter Gate
        (_Metrik(overall=0.8), 0.4, False),   # groove unter Gate
        (_Metrik(harmonic=50, overall=0.8), 0.7, False),  # Harmonik-Gate wie bisher
    ]
    for metrik, groove, erwartet in faelle:
        monkeypatch.setattr(
            rate_transitions, "rank_pair_candidates",
            lambda x, y, _m=metrik, _g=groove, **kw: [
                _lokaler_pc(_g, _m.overall_score, _m.harmonic_score / 100.0)
            ],
        )
        kandidaten = rate_transitions.sammle_kandidaten([a, b], 2.0)
        assert (len(kandidaten) > 0) is erwartet, (metrik.overall_score, groove)


def test_sammle_kandidaten_schreibt_zusatzwerte(monkeypatch):
    a = _GateTrack("A.wav", 140.0, lufs=-8.0)
    b = _GateTrack("B.wav", 141.0, lufs=-11.5)
    monkeypatch.setattr(
        rate_transitions, "rank_pair_candidates",
        lambda x, y, **kw: [_lokaler_pc(score=0.75)],
    )
    kandidaten = rate_transitions.sammle_kandidaten([a, b], 2.0)
    zusatz = kandidaten[0]["zusatz"]
    assert zusatz["overall_score"] == pytest.approx(0.75)
    assert zusatz["lufs_delta"] == pytest.approx(-3.5)
    assert set(zusatz) == set(rate_transitions.ZUSATZ_SPALTEN)


@pytest.mark.parametrize("faktor", rate_transitions.KANDIDATEN_TEILWERTE)
@pytest.mark.parametrize(
    "ungueltig",
    [None, True, "kaputt", float("nan"), float("inf"), float("-inf"), -0.001, 1.001],
)
def test_sammle_kandidaten_verwirft_jeden_ungueltigen_teilwert_vor_metrics(
    monkeypatch, faktor, ungueltig
):
    pc = _lokaler_pc()
    pc.teilwerte[faktor] = ungueltig
    monkeypatch.setattr(rate_transitions, "rank_pair_candidates", lambda *_a, **_k: [pc])
    monkeypatch.setattr(
        rate_transitions,
        "transition_metrics_from_candidate",
        lambda *_a: (_ for _ in ()).throw(AssertionError("Metrics zu frueh aufgerufen")),
    )
    assert rate_transitions.sammle_kandidaten(
        [_GateTrack("A.wav", 140.0), _GateTrack("B.wav", 141.0)], 2.0
    ) == []


def test_sammle_kandidaten_verwirft_fehlenden_teilwert_vor_metrics(monkeypatch):
    pc = _lokaler_pc()
    pc.teilwerte.pop("mood")
    monkeypatch.setattr(rate_transitions, "rank_pair_candidates", lambda *_a, **_k: [pc])
    monkeypatch.setattr(
        rate_transitions,
        "transition_metrics_from_candidate",
        lambda *_a: (_ for _ in ()).throw(AssertionError("Metrics zu frueh aufgerufen")),
    )
    assert rate_transitions.sammle_kandidaten(
        [_GateTrack("A.wav", 140.0), _GateTrack("B.wav", 141.0)], 2.0
    ) == []


def test_sammle_kandidaten_verwirft_zusaetzlichen_teilwert_vor_metrics(
    monkeypatch,
):
    pc = _lokaler_pc()
    pc.teilwerte["schema_drift"] = 0.5
    monkeypatch.setattr(rate_transitions, "rank_pair_candidates", lambda *_a, **_k: [pc])
    metrics = Mock(side_effect=AssertionError("Metrics zu frueh aufgerufen"))
    monkeypatch.setattr(rate_transitions, "transition_metrics_from_candidate", metrics)

    assert rate_transitions.sammle_kandidaten(
        [_GateTrack("A.wav", 140.0), _GateTrack("B.wav", 141.0)], 2.0
    ) == []
    metrics.assert_not_called()


@pytest.mark.parametrize(
    "feld,ungueltig",
    [
        ("score", True), ("score", "kaputt"), ("score", float("nan")),
        ("score", float("inf")), ("score", -0.001), ("score", 1.001),
        ("lufs_a", True), ("lufs_a", "kaputt"), ("lufs_a", float("nan")),
        ("lufs_b", float("inf")),
    ],
)
def test_sammle_kandidaten_verwirft_ungueltigen_score_oder_lufs_vor_metrics(
    monkeypatch, feld, ungueltig
):
    pc = _lokaler_pc()
    if feld == "score":
        pc.score = ungueltig
    elif feld == "lufs_a":
        pc.out_a.lufs_lokal = ungueltig
    else:
        pc.in_b.lufs_lokal = ungueltig
    monkeypatch.setattr(rate_transitions, "rank_pair_candidates", lambda *_a, **_k: [pc])
    monkeypatch.setattr(
        rate_transitions,
        "transition_metrics_from_candidate",
        lambda *_a: (_ for _ in ()).throw(AssertionError("Metrics zu frueh aufgerufen")),
    )
    assert rate_transitions.sammle_kandidaten(
        [_GateTrack("A.wav", 140.0), _GateTrack("B.wav", 141.0)], 2.0
    ) == []


@pytest.mark.parametrize(
    "feld,ungueltig",
    [
        ("harmonic_score", True), ("harmonic_score", float("nan")),
        ("harmonic_score", -0.1), ("harmonic_score", 100.1),
        ("overall_score", True), ("overall_score", float("inf")),
        ("overall_score", -0.001), ("overall_score", 1.001),
        ("groove_match", True), ("groove_match", float("nan")),
        ("groove_match", -0.001), ("groove_match", 1.001),
        ("lufs_delta", True), ("lufs_delta", "kaputt"),
        ("lufs_delta", float("nan")), ("lufs_delta", float("inf")),
    ],
)
def test_sammle_kandidaten_verwirft_ungueltige_gate_metrics(monkeypatch, feld, ungueltig):
    pc = _lokaler_pc()
    metrics = SimpleNamespace(
        harmonic_score=80,
        overall_score=0.8,
        groove_match=0.8,
        lufs_delta=-3.5,
    )
    setattr(metrics, feld, ungueltig)
    monkeypatch.setattr(rate_transitions, "rank_pair_candidates", lambda *_a, **_k: [pc])
    monkeypatch.setattr(rate_transitions, "transition_metrics_from_candidate", lambda *_a: metrics)
    assert rate_transitions.sammle_kandidaten(
        [_GateTrack("A.wav", 140.0), _GateTrack("B.wav", 141.0)], 2.0
    ) == []


def test_sammle_kandidaten_akzeptiert_gate_grenzen_und_endliches_rohes_lufs_delta(monkeypatch):
    pc = _lokaler_pc(groove=0.5, score=0.7, harmonic=0.6)
    metrics = SimpleNamespace(
        harmonic_score=60,
        overall_score=0.7,
        groove_match=0.5,
        lufs_delta=-123.456,
    )
    monkeypatch.setattr(rate_transitions, "rank_pair_candidates", lambda *_a, **_k: [pc])
    monkeypatch.setattr(rate_transitions, "transition_metrics_from_candidate", lambda *_a: metrics)
    result = rate_transitions.sammle_kandidaten(
        [_GateTrack("A.wav", 140.0), _GateTrack("B.wav", 141.0)], 2.0
    )
    assert len(result) == 2
    assert result[0]["zusatz"] == {"overall_score": 0.7, "lufs_delta": -123.46}


def test_sammle_kandidaten_bpm_grenze_inklusive(monkeypatch):
    monkeypatch.setattr(
        rate_transitions, "rank_pair_candidates",
        lambda x, y, **kw: [_lokaler_pc()],
    )
    a = _GateTrack("A.wav", 140.0)
    assert rate_transitions.sammle_kandidaten([a, _GateTrack("B.wav", 142.0)]) != []
    assert rate_transitions.sammle_kandidaten([a, _GateTrack("C.wav", 142.5)]) == []


def _brute_force_bpm_paare(tracks, toleranz):
    """Referenz fuer Reihenfolge und gerichtete effective_bpm_diff-Semantik."""
    paare = []
    for a in tracks:
        a_bpm = rate_transitions._gueltige_bpm(a.bpm)
        if a_bpm is None:
            continue
        for b in tracks:
            b_bpm = rate_transitions._gueltige_bpm(b.bpm)
            if a.filePath == b.filePath or b_bpm is None:
                continue
            diff, _relation = rate_transitions.effective_bpm_diff(a_bpm, b_bpm)
            if diff <= toleranz:
                paare.append((a.filePath, b.filePath))
    return paare


def test_sammle_kandidaten_bpm_index_entspricht_bruteforce_gerichtet(monkeypatch):
    tracks = [
        _GateTrack("A.wav", 140.0),
        _GateTrack("DirektGrenze.wav", 142.0),
        _GateTrack("HalfUnten.wav", 69.0),
        _GateTrack("HalfOben.wav", 71.0),
        _GateTrack("DoubleUnten.wav", 276.0),
        _GateTrack("DoubleOben.wav", 284.0),
        _GateTrack("Fern.wav", 199.0),
        _GateTrack("A.wav", 141.0),
    ]
    aufrufe = []

    def fake_rank(a, b, **_kwargs):
        aufrufe.append((a.filePath, b.filePath))
        return [_lokaler_pc()]

    monkeypatch.setattr(rate_transitions, "rank_pair_candidates", fake_rank)
    kandidaten = rate_transitions.sammle_kandidaten(tracks, 2.0)
    erwartet = _brute_force_bpm_paare(tracks, 2.0)

    assert aufrufe == erwartet
    assert [(k["track_a"].filePath, k["track_b"].filePath) for k in kandidaten] == erwartet


def test_sammle_kandidaten_bpm_index_dedupliziert_ueberlappende_fenster(monkeypatch):
    tracks = [_GateTrack("A.wav", 2.0), _GateTrack("B.wav", 1.0), _GateTrack("C.wav", 4.0)]
    aufrufe = []
    monkeypatch.setattr(
        rate_transitions,
        "rank_pair_candidates",
        lambda a, b, **_kw: aufrufe.append((a.filePath, b.filePath)) or [_lokaler_pc()],
    )

    rate_transitions.sammle_kandidaten(tracks, 2.0)

    assert aufrufe == _brute_force_bpm_paare(tracks, 2.0)
    assert len(aufrufe) == len(set(aufrufe))


def test_sammle_kandidaten_bpm_index_filtert_ungueltige_cachewerte(monkeypatch):
    tracks = [
        _GateTrack("A.wav", 140.0),
        _GateTrack("B.wav", 141.0),
        _GateTrack("Null.wav", 0),
        _GateTrack("Negativ.wav", -1),
        _GateTrack("None.wav", None),
        _GateTrack("Nan.wav", float("nan")),
        _GateTrack("Inf.wav", float("inf")),
        _GateTrack("Text.wav", "unbekannt"),
    ]
    aufrufe = []
    monkeypatch.setattr(
        rate_transitions,
        "rank_pair_candidates",
        lambda a, b, **_kw: aufrufe.append((a.filePath, b.filePath)) or [_lokaler_pc()],
    )

    rate_transitions.sammle_kandidaten(tracks, 2.0)

    assert aufrufe == [("A.wav", "B.wav"), ("B.wav", "A.wav")]


def test_sammle_kandidaten_bpm_index_respektiert_half_double_schalter(monkeypatch):
    tracks = [_GateTrack("Schnell.wav", 140.0), _GateTrack("Langsam.wav", 70.0)]
    aufrufe = []
    monkeypatch.setattr(rate_transitions.hpg_config, "BPM_HALF_DOUBLE_ENABLED", False)
    monkeypatch.setattr(
        rate_transitions,
        "rank_pair_candidates",
        lambda a, b, **_kw: aufrufe.append((a.filePath, b.filePath)) or [_lokaler_pc()],
    )

    assert rate_transitions.sammle_kandidaten(tracks, 2.0) == []
    assert aufrufe == []


def test_sammle_kandidaten_bpm_index_rankt_nur_lokale_paare(monkeypatch):
    tracks = []
    for gruppe in range(500):
        bpm = 100.0 + gruppe * 10.0
        tracks.extend(
            [_GateTrack(f"A{gruppe}.wav", bpm), _GateTrack(f"B{gruppe}.wav", bpm)]
        )
    aufrufe = []
    monkeypatch.setattr(rate_transitions.hpg_config, "BPM_HALF_DOUBLE_ENABLED", False)
    monkeypatch.setattr(
        rate_transitions,
        "rank_pair_candidates",
        lambda a, b, **_kw: aufrufe.append((a.filePath, b.filePath)) or [_lokaler_pc()],
    )

    rate_transitions.sammle_kandidaten(tracks, 0.1)

    assert len(aufrufe) == 1000
    assert len(aufrufe) < len(tracks) * len(tracks) // 100


# ===========================================================================
# Kandidatenmodus (Spec 2026-08-21 Abschnitt 3, Plan Teil 3)
# ===========================================================================
from pathlib import Path


from tools.rate_transitions import (
    BEWERTUNG_KANDIDATEN_SPALTEN, MERKMALE_KANDIDATEN_SPALTEN, clip_id_fuer,
    kandidaten_zeilen, reihenfolge_fuer_paar,
)


def _pc(t_out, t_in, bars, score, teil=None, schema_out=("pssi_phrase",), schema_in=("auto_cue",)):
    from hpg_core.mix_candidates import MixCandidate
    from hpg_core.pair_candidates import PairCandidate
    o = MixCandidate(t=t_out, schema=list(schema_out), provenance="rekordbox_pssi", confidence=0.8)
    i = MixCandidate(t=t_in, schema=list(schema_in), provenance="rekordbox_auto", confidence=0.7)
    o.energy_lokal = i.energy_lokal = 70
    o.lufs_lokal = i.lufs_lokal = -10.0
    return PairCandidate(out_a=o, in_b=i, blend_bars=bars, overlap_sec=bars * 1.714, score=score,
                         teilwerte=teil or {"harmonic": 0.9, "bpm": 1.0, "loudness": None},
                         flags={}, begruendung="x", rang=1, bpm_relation="direct")


def _ns_track(name, bpm=140.0, camelot="8A", genre="Psytrance"):
    return SimpleNamespace(filePath=name, bpm=bpm, camelotCode=camelot, detected_genre=genre, genre=genre,
                           duration=400.0, first_downbeat=0.0, downbeat_confidence=1.0,
                           beatgrid_source="rekordbox", beatgrid_status="verified",
                           analysis_mode="rekordbox_fast")


def test_clip_id_und_spalten():
    assert clip_id_fuer("007", 3) == "007_k3"
    assert BEWERTUNG_KANDIDATEN_SPALTEN == ("pair_id", "clip_id", "note", "gewaehlt", "zeit")
    assert MERKMALE_KANDIDATEN_SPALTEN[:3] == ("pair_id", "clip_id", "clip")
    assert "score" in MERKMALE_KANDIDATEN_SPALTEN and "t_out" in MERKMALE_KANDIDATEN_SPALTEN
    assert "schemata_out" in MERKMALE_KANDIDATEN_SPALTEN and "bpm_a" in MERKMALE_KANDIDATEN_SPALTEN
    assert MERKMALE_KANDIDATEN_SPALTEN[-2:] == ("track_a", "track_b")


def test_kandidaten_zeilen_schreiben_teilwerte_und_leer_bei_none():
    a, b = _ns_track("a.mp3"), _ns_track("b.mp3", camelot="9A")
    bew, merk = kandidaten_zeilen(
        "007", [_pc(160.0, 80.0, 16, 0.8)], a, b,
        clips=["clips/007_k1.wav"], bpm_toleranz=1.5,
        energy_direction="maintain",
    )
    assert bew == [{"pair_id": "007", "clip_id": "007_k1", "note": "", "gewaehlt": "", "zeit": ""}]
    m = merk[0]
    assert m["clip"] == "clips/007_k1.wav" and m["harmonic"] == 0.9 and m["loudness"] == ""
    assert m["schema_out"] == "pssi_phrase" and m["schemata_out"] == "pssi_phrase"
    assert m["blend_bars"] == 16 and m["t_out"] == 160.0
    assert m["provenance_in"] == "rekordbox_auto" and m["confidence_out"] == 0.8
    assert m["crossfade_sek"] == pytest.approx(16 * 1.714, abs=0.01)
    assert m["bpm_a"] == 140.0 and m["key_b"] == "9A" and m["genre_a"] == "Psytrance"
    assert m["bpm_toleranz"] == pytest.approx(1.5)
    assert m["energy_direction"] == "maintain"
    assert m["rendered_transition_type"] == "pro_eq_swap"
    assert m["transition_type_mode"] == "kontrolliert"


def test_kandidaten_zeilen_schreiben_auto_satzidentisch():
    a, b = _ns_track("a.mp3"), _ns_track("b.mp3")
    _bew, merk = kandidaten_zeilen(
        "007", [_pc(160.0, 80.0, 16, 0.8), _pc(161.0, 81.0, 8, 0.7)],
        a, b, clips=["clips/007_k1.wav", "clips/007_k2.wav"],
        bpm_toleranz=2.0, energy_direction=None,
    )
    assert {(row["bpm_toleranz"], row["energy_direction"]) for row in merk} == {(2.0, "auto")}


def test_reihenfolge_fuer_paar_deterministisch_und_vollstaendig():
    clips = ["007_k1", "007_k2", "007_k3", "007_k4"]
    r1 = reihenfolge_fuer_paar("007", clips, seed_satz=20260820)
    r2 = reihenfolge_fuer_paar("007", clips, seed_satz=20260820)
    assert r1 == r2 and sorted(r1["clips"]) == clips and r1["seed"] == 20260820 + 7
    assert reihenfolge_fuer_paar("008", clips, seed_satz=20260820)["seed"] == 20260828


def test_rendere_kandidat_verwirft_blende_ueber_deckel(monkeypatch):
    from tools import rate_transitions as rt
    pc = _pc(100.0, 60.0, 48, 0.5)                                    # 48 Takte * 1.714 = 82 s > 64
    a, b = _ns_track("a.mp3"), _ns_track("b.mp3")
    monkeypatch.setattr(rt, "render_transition_clip", lambda spec, pfad: pfad)
    with pytest.raises(ValueError):
        rt.rendere_kandidat(a, b, pc, "001", 1, Path("."))


def test_rendere_kandidat_verwendet_den_strikten_beatgridvertrag(monkeypatch, tmp_path):
    from tools import rate_transitions as rt
    pc = _pc(100.0, 60.0, 16, 0.8)
    a, b = _ns_track("a.mp3"), _ns_track("b.mp3")
    gesehen = {}
    def fake_render(spec, pfad):
        gesehen["spec"] = spec
        Path(pfad).write_bytes(b"RIFF")
    monkeypatch.setattr(rt, "render_transition_clip", fake_render)

    clip, transition_type = rt.rendere_kandidat(a, b, pc, "001", 1, tmp_path)

    spec = gesehen["spec"]
    assert clip == "clips/001_k1.wav"
    assert transition_type == spec.transition_type == "pro_eq_swap"
    assert spec.strict_beat_sync is True
    assert spec.beatgrid_status_a == spec.beatgrid_status_b == "verified"
    assert spec.analysis_mode_a == spec.analysis_mode_b == "rekordbox_fast"


from tools.rate_transitions import (
    _kennzahlen, _standardisiere_mit, auc, baue_candidate_preferences, bootstrap_paarvergleich,
    filtere_reine_kandidatenpaare, fit_paarvergleich, gewichte_aus_paarvergleich,
    holdout_nach_tracks, holdout_nach_tracks_mit_diagnose, identifizierbare_merkmale,
    nur_mit_note, paarvergleich_daten, schema_rangfolge, trefferquote_paarvergleich,
    uebernahme_erlaubt, verbinde_bewertungen_kandidaten,
)


def _merk(pid, cid, ta, tb, **teil):
    z = {"pair_id": pid, "clip_id": cid, "track_a": ta, "track_b": tb, "schema_out": "pssi_phrase",
         "schema_in": "auto_cue", "schemata_out": "pssi_phrase|sektion", "schemata_in": "auto_cue"}
    z.update({k: ("" if v is None else v) for k, v in teil.items()})
    return z


def test_verbinde_bewertungen_kandidaten_liest_note_gewaehlt_und_verwirft_leere_merkmale():
    merk = [_merk("001", "001_k1", "a", "b", harmonic=0.9, groove=0.8),
            _merk("001", "001_k2", "a", "b", harmonic=0.2, groove=None),
            _merk("002", "002_k1", "a", "c", harmonic=0.5, groove=0.5)]
    bew = [{"pair_id": "001", "clip_id": "001_k1", "note": "5", "gewaehlt": "1", "zeit": "t"},
           {"pair_id": "001", "clip_id": "001_k2", "note": "2", "gewaehlt": "", "zeit": "t"},
           {"pair_id": "002", "clip_id": "002_k1", "note": "", "gewaehlt": "", "zeit": ""}]
    genres = {"a": "Psytrance", "b": "Psytrance", "c": "Techno"}
    zeilen, ohne, verworfen = verbinde_bewertungen_kandidaten(
        merk, bew, merkmale=("harmonic", "groove"), genre_von=genres.get
    )
    # 001_k2: leeres Merkmal -> verworfen; 002_k1: ohne Note -> bleibt (note None) fuer den Paarvergleich
    assert [z["clip_id"] for z in zeilen] == ["001_k1", "002_k1"] and ohne == 1 and verworfen == 1
    assert zeilen[0]["note"] == 5 and zeilen[0]["bewertung"] == 5 and zeilen[0]["gewaehlt"] is True
    assert zeilen[0]["tracks"] == ("a", "b") and zeilen[1]["note"] is None
    assert (zeilen[0]["genre_a"], zeilen[0]["genre_b"], zeilen[0]["genre"]) == (
        "Psytrance", "Psytrance", "Psytrance"
    )
    assert zeilen[1]["genre"] == ""
    assert zeilen[0]["schemata_out"] == ["pssi_phrase", "sektion"]
    assert [z["clip_id"] for z in nur_mit_note(zeilen)] == ["001_k1"]


def test_filtere_reine_kandidatenpaare_schliesst_mixed_unknown_und_inkonsistent_aus():
    def zeile(pid, tracks, ga, gb, cid):
        return {
            "pair_id": pid, "clip_id": cid, "tracks": tracks,
            "genre_a": ga, "genre_b": gb, "genre": "",
        }

    zeilen = [
        zeile("rein", ("a", "b"), "Psytrance", "Psytrance", "r1"),
        zeile("rein", ("a", "b"), "Psytrance", "Psytrance", "r2"),
        zeile("mixed", ("c", "d"), "Psytrance", "Techno", "m1"),
        zeile("unknown", ("e", "f"), "", "Techno", "u1"),
        zeile("kaputt", ("g", "h"), "Techno", "Techno", "k1"),
        zeile("kaputt", ("g", "x"), "Techno", "Techno", "k2"),
    ]
    rein, diagnose = filtere_reine_kandidatenpaare(zeilen)
    assert [z["clip_id"] for z in rein] == ["r1", "r2"]
    assert all(z["genre"] == "Psytrance" for z in rein)
    assert diagnose == {
        "inkonsistente_paare": 1, "inkonsistente_clips": 2,
        "gemischte_paare": 1, "gemischte_clips": 1,
        "unbekannte_paare": 1, "unbekannte_clips": 1,
    }


def test_auc_rangstatistik():
    assert auc(np.array([1, 1, 0, 0]), np.array([0.9, 0.8, 0.2, 0.1])) == pytest.approx(1.0)
    assert auc(np.array([1, 0]), np.array([0.5, 0.5])) == pytest.approx(0.5)
    assert auc(np.array([1, 1]), np.array([0.5, 0.6])) is None


def test_holdout_nach_tracks_trennt_clips_deterministisch():
    zeilen = [{"tracks": ("a", "b")}, {"tracks": ("c", "d")}, {"tracks": ("a", "d")}, {"tracks": ("e", "f")}]
    train, hold, grenz_paare, grenz_clips = holdout_nach_tracks_mit_diagnose(
        zeilen, anteil=0.5, seed=1
    )
    assert len(train) + len(hold) + grenz_clips == 4
    train_tracks = {t for z in train for t in z["tracks"]}
    hold_tracks = {t for z in hold for t in z["tracks"]}
    assert hold and train_tracks.isdisjoint(hold_tracks)
    assert all(set(z["tracks"]) <= hold_tracks for z in hold)
    assert holdout_nach_tracks(zeilen, anteil=0.5, seed=1) == (train, hold)
    assert holdout_nach_tracks_mit_diagnose(zeilen, anteil=0.5, seed=1) == (
        train, hold, grenz_paare, grenz_clips
    )


def test_holdout_diagnostiziert_grenzpaare_statt_varianten():
    zeilen = [
        {"pair_id": "p1", "tracks": ("a", "b")},
        {"pair_id": "p1", "tracks": ("a", "b")},
        {"pair_id": "p2", "tracks": ("c", "c")},
    ]
    for seed in range(100):
        _train, _hold, paare, clips = holdout_nach_tracks_mit_diagnose(
            zeilen, anteil=0.5, seed=seed
        )
        if clips == 2:
            assert paare == 1
            break
    else:
        pytest.fail("Kein deterministischer Grenzfall fuer p1 gefunden")


def _synth_paare(n=60, seed=3):
    rng = np.random.default_rng(seed)
    zeilen = []
    for p in range(n):
        xs = rng.uniform(0, 1, size=(3, 3))
        nutzen = 3.0 * xs[:, 0] + 0.0 * xs[:, 1]
        sieger = int(np.argmax(nutzen))
        for k in range(3):
            zeilen.append({"pair_id": f"{p:03d}", "clip_id": f"{p:03d}_k{k+1}", "note": 3, "bewertung": 3,
                           "gewaehlt": k == sieger,
                           "merkmale": {"harmonic": xs[k, 0], "groove": xs[k, 1], "bpm": 0.9},  # bpm je Paar konstant
                           "tracks": (f"a{p}", f"b{p}"), "genre": "Psytrance",
                           "schema_out": "pssi_phrase", "schema_in": "auto_cue",
                           "schemata_out": ["pssi_phrase"], "schemata_in": ["auto_cue"]})
    return zeilen


def test_paarvergleich_findet_bekannte_praeferenz_und_identifizierbarkeit():
    zeilen = _synth_paare()
    X, gruppen = paarvergleich_daten(zeilen, ("harmonic", "groove", "bpm"))
    assert X.shape == (120, 3) and len(gruppen) == 120            # 60 Paare x 2 Verlierer, keine Spiegelung
    assert identifizierbare_merkmale(X, ("harmonic", "groove", "bpm")) == ["harmonic", "groove"]
    beta = fit_paarvergleich(X)
    assert beta[0] > 1.0 and abs(beta[1]) < beta[0] / 3 and beta[2] == pytest.approx(0.0, abs=1e-6)
    treffer, basis = trefferquote_paarvergleich(beta, zeilen, ("harmonic", "groove", "bpm"))
    assert treffer > 0.8 and basis == pytest.approx(1 / 3)


def test_bootstrap_paarvergleich_zieht_ueber_paare():
    zeilen = _synth_paare(n=20)
    X, gruppen = paarvergleich_daten(zeilen, ("harmonic", "groove"))
    iv = bootstrap_paarvergleich(X, gruppen, ziehungen=30, seed=1)
    assert len(iv) == 2 and iv[0][0] > 0.0                          # harmonic gesichert positiv
    assert bootstrap_paarvergleich(np.zeros((0, 2)), [], ziehungen=5) == [(0.0, 0.0), (0.0, 0.0)]


def test_gewichte_aus_paarvergleich_restbudget_und_leer():
    tol = {f"kandidaten_{f}_weight": w for f, w in zip(
        ("harmonic", "bpm", "energy", "genre", "groove", "bass", "timbre", "mood", "loudness", "structure"),
        (0.140, 0.106, 0.106, 0.106, 0.264, 0.070, 0.044, 0.044, 0.060, 0.060))}
    g = gewichte_aus_paarvergleich(("harmonic", "groove"), [(0.5, 2.0), (-0.1, 0.3)], ["harmonic", "groove"], tol)
    assert g["bpm"] == pytest.approx(0.106) and g["groove"] == 0.0       # nicht identifizierbar behaelt, ungesichert 0
    assert g["harmonic"] == pytest.approx(1.0 - (1.0 - 0.140 - 0.264))     # Restbudget komplett auf harmonic
    assert sum(g.values()) == pytest.approx(1.0)
    assert gewichte_aus_paarvergleich(("harmonic",), [(-0.2, 0.1)], ["harmonic"], tol) == {}


def test_uebernahme_erlaubt_gruende():
    ok, _ = uebernahme_erlaubt(belastbar_note=True, n_paare_train=40, n_identifizierbar=2, auc_holdout=0.7,
                               treffer_holdout=0.6, basis_holdout=0.33, gewichte={"harmonic": 1.0})
    assert ok
    assert not uebernahme_erlaubt(belastbar_note=False, n_paare_train=40, n_identifizierbar=2, auc_holdout=0.7,
                                  treffer_holdout=0.6, basis_holdout=0.33, gewichte={"harmonic": 1.0})[0]
    assert "zu wenige Paare" in uebernahme_erlaubt(belastbar_note=True, n_paare_train=5, n_identifizierbar=2,
                                                   auc_holdout=0.7, treffer_holdout=0.6, basis_holdout=0.33,
                                                   gewichte={"harmonic": 1.0})[1]
    assert "AUC" in uebernahme_erlaubt(belastbar_note=True, n_paare_train=40, n_identifizierbar=2, auc_holdout=0.5,
                                       treffer_holdout=0.6, basis_holdout=0.33, gewichte={"harmonic": 1.0})[1]
    assert "Trefferquote" in uebernahme_erlaubt(belastbar_note=True, n_paare_train=40, n_identifizierbar=2,
                                                auc_holdout=0.7, treffer_holdout=0.3, basis_holdout=0.33,
                                                gewichte={"harmonic": 1.0})[1]


def test_standardisiere_mit_train_kennzahlen():
    X = np.array([[0.0, 10.0], [2.0, 10.0]])
    m, s = _kennzahlen(X)
    assert list(m) == [1.0, 10.0] and list(s) == [1.0, 1.0]          # Streuung 0 -> 1
    assert _standardisiere_mit(np.array([[3.0, 12.0]]), m, s).tolist() == [[2.0, 2.0]]


def test_schema_rangfolge_und_praeferenz_json():
    zeilen = []
    for index in range(5):
        zeilen.extend([
            {"pair_id": f"p{index}", "note": 4, "genre": "Psytrance", "gewaehlt": True,
             "schemata_out": ["pssi_phrase"], "schemata_in": ["auto_cue"]},
            {"pair_id": f"p{index}", "note": 3, "genre": "Psytrance", "gewaehlt": False,
             "schemata_out": ["sektion"], "schemata_in": ["auto_cue"]},
        ])
    rang = schema_rangfolge(zeilen, min_wahlen=5)
    assert rang["Psytrance"][0] == "pssi_phrase"
    prefs = baue_candidate_preferences(
        {"Psytrance": {"harmonic": 0.7, "groove": 0.3}}, rang, {"quelle": "test"}
    )
    assert prefs["Psytrance"]["kandidaten_harmonic_weight"] == pytest.approx(0.7)
    assert sum(v for k, v in prefs["Psytrance"].items() if k.endswith("_weight")) == pytest.approx(1.0)
    assert prefs["Psytrance"]["schema_rang"][0] == "pssi_phrase" and "_diagnose" in prefs
    assert "Techno" not in prefs


def test_candidate_preferences_erhaelt_kleines_positives_gewicht_ungerundet():
    klein = 1.23456789e-9
    gewichte = {name: 0.0 for name in rate_transitions.KANDIDATEN_TEILWERTE}
    gewichte["harmonic"] = 1.0 - klein
    gewichte["groove"] = klein

    prefs = baue_candidate_preferences(
        {"Psytrance": gewichte}, {}, {"quelle": "test"}
    )

    assert prefs["Psytrance"]["kandidaten_groove_weight"] == klein
    assert prefs["Psytrance"]["kandidaten_groove_weight"] > 0.0


def test_schema_rangfolge_ignoriert_unbekannte_schemata():
    zeilen = []
    for index in range(5):
        zeilen.extend([
            {"pair_id": f"p{index}", "note": 5, "genre": "Psytrance", "gewaehlt": True,
             "schemata_out": ["fremd", "pssi_phrase"], "schemata_in": []},
            {"pair_id": f"p{index}", "note": 2, "genre": "Psytrance", "gewaehlt": False,
             "schemata_out": ["fremd"], "schemata_in": ["auto_cue"]},
        ])
    rang = schema_rangfolge(zeilen, min_wahlen=5)
    assert "fremd" not in rang["Psytrance"]


def _manifest_gewichte(rt, **aenderungen):
    werte = {
        key: 1.0 / len(rt.KANDIDATEN_GEWICHT_SCHLUESSEL)
        for key in rt.KANDIDATEN_GEWICHT_SCHLUESSEL
    }
    werte.update(aenderungen)
    return werte


def _manifest_mit_fit_snapshot(rt):
    return {
        "scoring_snapshot": {
            "candidate_tolerances_by_genre": {
                genre: {
                    **_manifest_gewichte(rt),
                    "brightness_delta_max": 0.25,
                }
                for genre in rt.CANONICAL_GENRES
            }
        }
    }


@pytest.mark.parametrize(
    "mutator",
    [
        lambda rt, entry: entry.pop(rt.KANDIDATEN_GEWICHT_SCHLUESSEL[0]),
        lambda rt, entry: entry.update(kandidaten_falsch_weight=0.0),
        lambda rt, entry: entry.update({rt.KANDIDATEN_GEWICHT_SCHLUESSEL[0]: True}),
        lambda rt, entry: entry.update({rt.KANDIDATEN_GEWICHT_SCHLUESSEL[0]: float("nan")}),
        lambda rt, entry: entry.update({rt.KANDIDATEN_GEWICHT_SCHLUESSEL[0]: 1.1}),
        lambda rt, entry: entry.update({rt.KANDIDATEN_GEWICHT_SCHLUESSEL[0]: 0.2}),
    ],
)
def test_manifest_kandidatengewichte_ist_exakt_und_fail_closed(mutator):
    rt = rate_transitions
    entry = {**_manifest_gewichte(rt), "brightness_delta_max": 0.25}
    mutator(rt, entry)
    snapshot = {"candidate_tolerances_by_genre": {"Psytrance": entry}}

    with pytest.raises(ValueError):
        rt._manifest_kandidatengewichte(snapshot, "Psytrance")


def test_manifest_kandidatengewichte_erlaubt_nichtgewichtstoleranzen():
    rt = rate_transitions
    entry = {**_manifest_gewichte(rt), "brightness_delta_max": 0.25}
    snapshot = {"candidate_tolerances_by_genre": {"Psytrance": entry}}

    assert rt._manifest_kandidatengewichte(snapshot, "Psytrance") == {
        key: entry[key] for key in rt.KANDIDATEN_GEWICHT_SCHLUESSEL
    }


def test_genre_fit_nutzt_ausschliesslich_uebergebene_manifest_gewichte(monkeypatch):
    from tools import rate_transitions as rt

    zeilen = []
    for index, (note, gewaehlt, wert) in enumerate(((5, True, 1.0), (1, False, 0.0))):
        zeilen.append({
            "pair_id": "p", "clip_id": f"c{index}", "note": note,
            "bewertung": note, "gewaehlt": gewaehlt,
            "merkmale": {name: wert for name in rt.KANDIDATEN_TEILWERTE},
            "tracks": ("a", "b"), "genre": "Techno",
            "schemata_out": ["pssi_phrase"], "schemata_in": ["auto_cue"],
        })
    baseline = _manifest_gewichte(rt)
    gesehen = {}
    echtes_ableiten = rt.gewichte_aus_paarvergleich

    def ableiten(*args):
        gesehen["baseline"] = args[-1]
        return echtes_ableiten(*args)

    monkeypatch.setattr(rt, "gewichte_aus_paarvergleich", ableiten)
    monkeypatch.setattr(rt, "bootstrap_paarvergleich", lambda *a, **k: [(1.0, 2.0)] * len(rt.KANDIDATEN_TEILWERTE))
    monkeypatch.setattr(rt, "uebernahme_erlaubt", lambda **k: (False, "Test-Gate"))
    monkeypatch.setattr(
        rt, "holdout_nach_tracks_mit_diagnose",
        lambda rows, *a, **k: (list(rows), [], 0, 0),
    )
    rt._fit_kandidaten_genre("Techno", zeilen, seed=1, toleranz_gewichte=baseline)
    assert gesehen["baseline"] is baseline


def test_grenzpaar_beeinflusst_weder_aktive_merkmale_noch_schema(monkeypatch):
    from tools import rate_transitions as rt

    def clip(cid, pid, harmonic, groove, schema, gewaehlt):
        merkmale = {name: 0.5 for name in rt.KANDIDATEN_TEILWERTE}
        merkmale.update(harmonic=harmonic, groove=groove)
        return {
            "clip_id": cid, "pair_id": pid, "note": 5 if gewaehlt else 1,
            "bewertung": 5 if gewaehlt else 1, "gewaehlt": gewaehlt,
            "merkmale": merkmale, "tracks": (f"{pid}a", f"{pid}b"),
            "genre": "Psytrance", "schemata_out": [schema],
            "schemata_in": ["auto_cue"],
        }

    train = [
        clip("t1", "train", 1.0, 0.5, "pssi_phrase", True),
        clip("t2", "train", 0.0, 0.5, "pssi_phrase", False),
    ]
    holdout = [
        clip("h1", "hold", 1.0, 0.5, "pssi_phrase", True),
        clip("h2", "hold", 0.0, 0.5, "pssi_phrase", False),
    ]
    grenze = [
        clip("g1", "grenze", 0.5, 1.0, "sektion", True),
        clip("g2", "grenze", 0.5, 0.0, "sektion", False),
    ]
    monkeypatch.setattr(
        rt, "holdout_nach_tracks_mit_diagnose",
        lambda *a, **k: (train, holdout, 1, 2),
    )
    gesehen = {}
    def fake_schema(zeilen):
        gesehen["schema_zeilen"] = list(zeilen)
        return {}
    monkeypatch.setattr(rt, "schema_rangfolge", fake_schema)
    monkeypatch.setattr(rt, "bootstrap_paarvergleich", lambda *a, **k: [(1.0, 2.0)])
    monkeypatch.setattr(rt, "uebernahme_erlaubt", lambda **k: (False, "Test-Gate"))
    _gewichte, _schema, diagnose = rt._fit_kandidaten_genre(
        "Psytrance", train + holdout + grenze, seed=1,
        toleranz_gewichte=_manifest_gewichte(rt),
    )
    assert diagnose["aktive_merkmale"] == ["harmonic"]
    assert diagnose["cross_boundary_pairs"] == 1
    assert diagnose["cross_boundary_clips"] == 2
    assert {z["clip_id"] for z in gesehen["schema_zeilen"]} == {"t1", "t2", "h1", "h2"}


def test_zwei_genres_lernen_gegensaetzliche_gewichte_real(monkeypatch):
    from tools import rate_transitions as rt

    rng = np.random.default_rng(20260826)

    def daten(genre, ziel, rauschen):
        zeilen = []
        for paar in range(120):
            noise_a, noise_b = rng.uniform(0.0, 1.0, size=2)
            signal_a = rng.uniform(0.65, 1.0)
            signal_b = rng.uniform(0.0, 0.35)
            for rang, (signal, noise, gewaehlt) in enumerate(
                ((signal_a, noise_a, True), (signal_b, noise_b, False))
            ):
                merkmale = {name: 0.5 for name in rt.KANDIDATEN_TEILWERTE}
                merkmale[ziel] = signal
                merkmale[rauschen] = noise
                zeilen.append({
                    "pair_id": f"{genre}-{paar}", "clip_id": f"{genre}-{paar}-{rang}",
                    "note": 5 if gewaehlt else 1, "bewertung": 5 if gewaehlt else 1,
                    "gewaehlt": gewaehlt, "merkmale": merkmale,
                    "tracks": (f"{genre}-a{paar}", f"{genre}-b{paar}"), "genre": genre,
                    "schemata_out": ["pssi_phrase"], "schemata_in": ["auto_cue"],
                })
        return zeilen

    monkeypatch.setattr(rt, "BOOTSTRAP_ZIEHUNGEN", 80)
    psy, _, psy_diag = rt._fit_kandidaten_genre(
        "Psytrance", daten("Psytrance", "harmonic", "groove"), seed=7,
        toleranz_gewichte=_manifest_gewichte(rt),
    )
    techno, _, techno_diag = rt._fit_kandidaten_genre(
        "Techno", daten("Techno", "groove", "harmonic"), seed=7,
        toleranz_gewichte=_manifest_gewichte(rt),
    )
    assert psy is not None, psy_diag["grund"]
    assert techno is not None, techno_diag["grund"]
    assert set(psy_diag["aktive_merkmale"]) == {"harmonic", "groove"}
    assert set(techno_diag["aktive_merkmale"]) == {"harmonic", "groove"}
    assert psy["harmonic"] > psy["groove"]
    assert techno["groove"] > techno["harmonic"]
    assert psy != techno


def _stubbe_fit_binding_io(monkeypatch, rt, merkmale, bewertung):
    token = (("merkmale_sha256", "m"), ("bewertung_sha256", "b"))
    monkeypatch.setattr(rt, "_fit_binding_token", lambda *_args: token)
    monkeypatch.setattr(rt, "_bestaetige_fit_binding", lambda *_args: None)
    monkeypatch.setattr(
        rt,
        "_lies_fit_csv_gebunden",
        lambda path, *_args: merkmale if path.name == "merkmale.csv" else bewertung,
    )


def test_fit_kandidaten_uebernimmt_nur_bestandenes_genre(monkeypatch, tmp_path):
    from hpg_core import candidate_preferences as cp
    from tools import rate_transitions as rt

    zeilen = [
        {"genre": "Psytrance", "pair_id": "p", "tracks": ("a", "b")},
        {"genre": "Techno", "pair_id": "t", "tracks": ("c", "d")},
    ]
    _stubbe_fit_binding_io(monkeypatch, rt, [], [])
    monkeypatch.setattr(rt, "validiere_kandidaten_csvs", lambda a, b: None)
    monkeypatch.setattr(rt, "validiere_vollstaendige_kandidatenbewertung", lambda _rows: None)
    monkeypatch.setattr(
        rt, "_validiere_fit_bindung", lambda *_args: _manifest_mit_fit_snapshot(rt)
    )
    monkeypatch.setattr(rt, "lade_tracks_aus_cache", lambda pfad: [])
    monkeypatch.setattr(rt, "verbinde_bewertungen_kandidaten", lambda *a, **k: (zeilen, 0, 0))
    monkeypatch.setattr(rt, "filtere_reine_kandidatenpaare", lambda z: (z, {}))
    gewichte = {name: 0.0 for name in rt.KANDIDATEN_TEILWERTE}
    gewichte["harmonic"] = 1.0

    def fake_fit(genre, genre_zeilen, seed, toleranz_gewichte):
        assert toleranz_gewichte == _manifest_gewichte(rt)
        if genre == "Psytrance":
            return gewichte, ["pssi_phrase"], {"uebernommen": True, "grund": "ok"}
        return None, None, {"uebernommen": False, "grund": "Gate"}

    monkeypatch.setattr(rt, "_fit_kandidaten_genre", fake_fit)
    gesehen = {}
    monkeypatch.setattr(
        cp, "merge_user_preferences_atomically",
        lambda updates, diagnose=None: gesehen.update(updates=updates, diagnose=diagnose) or tmp_path / "prefs.json",
    )
    args = SimpleNamespace(
        dir=tmp_path, cache="cache.db", audit_report="audit.json", seed=7
    )
    assert rt.befehl_fit_kandidaten(args) == 0
    assert set(gesehen["updates"]) == {"Psytrance"}
    assert gesehen["updates"]["Psytrance"]["schema_rang"] == ["pssi_phrase"]
    assert set(gesehen["diagnose"]["genres"]) == {"Psytrance", "Techno"}


def test_fit_kandidaten_all_fail_laesst_override_byteidentisch(monkeypatch, tmp_path):
    from hpg_core import candidate_preferences as cp
    from tools import rate_transitions as rt

    override = tmp_path / "override.json"
    vorher = b'{"fremd": {"bleibt": true}}\r\n'
    override.write_bytes(vorher)
    monkeypatch.setenv("HPG_CANDIDATE_PREFERENCES_FILE", str(override))
    zeilen = [{"genre": "Psytrance", "pair_id": "p", "tracks": ("a", "b")}]
    _stubbe_fit_binding_io(monkeypatch, rt, [], [])
    monkeypatch.setattr(rt, "validiere_kandidaten_csvs", lambda a, b: None)
    monkeypatch.setattr(rt, "validiere_vollstaendige_kandidatenbewertung", lambda _rows: None)
    monkeypatch.setattr(
        rt, "_validiere_fit_bindung", lambda *_args: _manifest_mit_fit_snapshot(rt)
    )
    monkeypatch.setattr(rt, "lade_tracks_aus_cache", lambda pfad: [])
    monkeypatch.setattr(rt, "verbinde_bewertungen_kandidaten", lambda *a, **k: (zeilen, 0, 0))
    monkeypatch.setattr(rt, "filtere_reine_kandidatenpaare", lambda z: (z, {}))
    monkeypatch.setattr(
        rt, "_fit_kandidaten_genre",
        lambda *a, **k: (None, None, {"uebernommen": False, "grund": "Gate"}),
    )
    monkeypatch.setattr(
        cp, "merge_user_preferences_atomically",
        lambda *a, **k: pytest.fail("All-Fail darf den Override nicht anfassen"),
    )
    assert rt.befehl_fit_kandidaten(SimpleNamespace(
        dir=tmp_path, cache="cache.db", audit_report="audit.json", seed=1
    )) == 0
    assert override.read_bytes() == vorher
    entwurf = json.loads((tmp_path / "candidate_preferences_entwurf.json").read_text(encoding="utf-8"))
    assert set(entwurf) == {"_diagnose"}


def test_prepare_kandidaten_ruft_das_zentrale_ranking(monkeypatch, tmp_path):
    from tools import rate_transitions as rt
    aufrufe = {}

    def fake_build(a, b, **kw):
        aufrufe["called"] = True
        aufrufe["kwargs"] = kw
        return []

    monkeypatch.setattr(rt, "rank_pair_candidates", fake_build)
    monkeypatch.setattr(rt, "lade_tracks_aus_cache", lambda c: [])
    monkeypatch.setattr(rt, "sammle_kandidaten", lambda t, tol, direction, **_kw: [
        {"track_a": _ns_track("a"), "track_b": _ns_track("b"), "merkmale": {n: 0.5 for n in rt.NEUE_FAKTOREN}}])
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"cache")
    args = SimpleNamespace(
        out=tmp_path / "satz", cache=str(cache), bpm_toleranz=1.25,
        energy_direction="down", nur_genre=None, anzahl=1, seed=1,
    )
    rt.befehl_prepare_kandidaten(args)
    assert aufrufe.get("called") is True
    assert aufrufe["kwargs"]["bpm_tolerance"] == pytest.approx(1.25)
    assert aufrufe["kwargs"]["energy_direction"] == "down"
    assert aufrufe["kwargs"]["harmonic_strictness"] == 7
    assert aufrufe["kwargs"]["allow_experimental"] is True
    assert len(aufrufe["kwargs"]["tolerances"]) == 13
    assert isinstance(aufrufe["kwargs"]["schema_rang"], list)
    assert aufrufe["kwargs"]["wahl"] == {}


def test_scoring_snapshot_friert_cli_harmonieoptionen_exakt_ein(monkeypatch):
    rt = rate_transitions
    monkeypatch.setattr(rt.tolerances, "load_tolerances", lambda: {
        genre: {
            **{key: 0.1 for key in rt.KANDIDATEN_GEWICHT_SCHLUESSEL},
            **{key: 1.0 for key in rt.NICHT_GEWICHT_SCHLUESSEL},
        }
        for genre in rt.CANONICAL_GENRES
    })
    monkeypatch.setattr(rt.candidate_preferences, "load_candidate_preferences", lambda: {})
    monkeypatch.setattr(rt.candidate_choices, "snapshot", lambda: {})

    snapshot = rt._baue_scoring_snapshot(SimpleNamespace(
        bpm_toleranz=2.0,
        energy_direction=None,
        harmonic_strictness=3,
        allow_experimental=False,
    ))

    assert snapshot["rank_args"]["harmonic_strictness"] == 3
    assert snapshot["rank_args"]["allow_experimental"] is False


@pytest.mark.parametrize(("raw", "expected"), [("true", True), ("false", False)])
def test_striktes_bool_cli_akzeptiert_nur_kanonische_werte(raw, expected):
    assert rate_transitions._striktes_bool_arg(raw) is expected


@pytest.mark.parametrize("raw", ["True", "FALSE", "1", "yes", "", " false "])
def test_striktes_bool_cli_lehnt_mehrdeutige_werte_ab(raw):
    with pytest.raises(argparse.ArgumentTypeError):
        rate_transitions._striktes_bool_arg(raw)


def test_prepare_cli_reicht_variable_harmonieoptionen_exakt_weiter(monkeypatch, tmp_path):
    gesehen = {}

    def prepare(args):
        gesehen.update(vars(args))
        return 0

    monkeypatch.setattr(rate_transitions, "_prepare", prepare)
    result = rate_transitions.main([
        "prepare", "--out", str(tmp_path / "satz"),
        "--harmonic-strictness", "4", "--allow-experimental", "false",
    ])

    assert result == 0
    assert gesehen["harmonic_strictness"] == 4
    assert gesehen["allow_experimental"] is False


def test_hoertest_verwendet_fuer_alle_kandidaten_die_feste_eq_technik():
    from tools import rate_transitions as rt

    pc = SimpleNamespace(flags={"bass_swap_pflicht": True})
    assert rt._transition_type_fuer(object(), object(), pc) == "pro_eq_swap"
    assert rt._transition_type_fuer(object(), object(), None) == "pro_eq_swap"


def test_produktionsmodus_verwendet_dieselbe_typentscheidung_wie_die_app(
    monkeypatch,
):
    from tools import rate_transitions as rt

    gesehen = {}

    def fake(a, b, pc, *, bpm_tolerance, scoring_context):
        gesehen.update({
            "a": a, "b": b, "pc": pc,
            "bpm_tolerance": bpm_tolerance,
            "scoring_context": scoring_context,
        })
        return "bass_swap"

    monkeypatch.setattr(rt, "transition_type_for_candidate", fake)
    a, b, pc = object(), object(), object()

    result = rt._transition_type_fuer(
        a,
        b,
        pc,
        modus="produktion",
        bpm_toleranz=1.5,
        energy_direction="down",
    )

    assert result == "bass_swap"
    assert gesehen == {
        "a": a,
        "b": b,
        "pc": pc,
        "bpm_tolerance": 1.5,
        "scoring_context": {"energy_direction": "down"},
    }


def test_entwurf_wird_atomar_mit_fsync_geschrieben(monkeypatch, tmp_path):
    from tools import rate_transitions as rt

    aufrufe = []
    monkeypatch.setattr(rt.os, "fsync", lambda fd: aufrufe.append(fd))
    ziel = tmp_path / "entwurf.json"
    rt._schreibe_json_atomar(ziel, {"ok": True})
    assert json.loads(ziel.read_text(encoding="utf-8")) == {"ok": True}
    assert len(aufrufe) == 1


def test_cli_fehler_bei_fehlendem_fit_ordner_ist_kontrolliert(tmp_path, capsys):
    from tools import rate_transitions as rt

    assert rt.main(["fit", "--dir", str(tmp_path / "fehlt")]) == 2
    assert "FEHLER:" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("auto", None), ("AUTO", None), ("Up", "up"), ("DOWN", "down"), ("Maintain", "maintain")],
)
def test_energy_direction_normalisierung_case_insensitive(raw, expected):
    assert rate_transitions._energy_direction_arg(raw) == expected
    assert rate_transitions._energy_direction_text(expected) == raw.casefold()


def test_cli_energy_direction_default_und_explizit(monkeypatch, tmp_path):
    gesehen = []
    monkeypatch.setattr(
        rate_transitions,
        "_prepare",
        lambda args: gesehen.append(args.energy_direction) or 0,
    )
    assert rate_transitions.main(["prepare", "--out", str(tmp_path / "a")]) == 0
    assert rate_transitions.main([
        "prepare", "--out", str(tmp_path / "b"), "--energy-direction", "Up"
    ]) == 0
    assert gesehen == [None, "up"]


def test_cli_default_und_explizit_bpm_energy_vertrag_ist_semantisch_identisch(
    monkeypatch, tmp_path
):
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"cache")
    a, b = _ns_track("a"), _ns_track("b")
    paar = {
        "track_a": a,
        "track_b": b,
        "merkmale": {name: 0.5 for name in rate_transitions.KANDIDATEN_TEILWERTE},
        "pair_candidates": [_pc(160.0, 80.0, 16, 0.8)],
    }

    def fake_render(_a, _b, _pc, pair_id, n, clips, **_kwargs):
        ziel = clips / f"{pair_id}_k{n}.wav"
        ziel.write_bytes(b"RIFF")
        return f"clips/{pair_id}_k{n}.wav", "pro_eq_swap"

    monkeypatch.setattr(rate_transitions, "lade_tracks_aus_cache", lambda *_args: [a, b])
    monkeypatch.setattr(
        rate_transitions, "sammle_kandidaten", lambda *_args, **_kwargs: [paar]
    )
    monkeypatch.setattr(rate_transitions, "maximin_auswahl", lambda _v, _n, **_kw: [0])
    monkeypatch.setattr(rate_transitions, "rendere_kandidat", fake_render)

    assert rate_transitions.main([
        "prepare",
        "--modus", "kandidaten",
        "--out", str(tmp_path / "auto_default"),
        "--cache", str(cache),
        "--anzahl", "1",
    ]) == 0
    assert rate_transitions.main([
        "prepare",
        "--modus", "kandidaten",
        "--out", str(tmp_path / "auto_explizit"),
        "--cache", str(cache),
        "--anzahl", "1",
        "--bpm-toleranz", "2.0",
        "--energy-direction", "auto",
    ]) == 0

    default_merkmale = rate_transitions.lies_csv(tmp_path / "auto_default" / "merkmale.csv")
    explicit_merkmale = rate_transitions.lies_csv(tmp_path / "auto_explizit" / "merkmale.csv")
    assert len(default_merkmale) == len(explicit_merkmale) == 1
    assert default_merkmale[0]["pair_id"] == explicit_merkmale[0]["pair_id"] == "001"
    assert default_merkmale[0]["clip_id"] == explicit_merkmale[0]["clip_id"] == "001_k1"
    assert default_merkmale[0]["bpm_toleranz"] == explicit_merkmale[0]["bpm_toleranz"] == "2.0"
    assert default_merkmale[0]["energy_direction"] == explicit_merkmale[0]["energy_direction"] == "auto"

    legacy_fields = [
        name for name in rate_transitions.MERKMALE_KANDIDATEN_SPALTEN
        if name not in {"bpm_toleranz", "energy_direction"}
    ]
    default_legacy = [{name: row[name] for name in legacy_fields} for row in default_merkmale]
    explicit_legacy = [{name: row[name] for name in legacy_fields} for row in explicit_merkmale]
    assert default_legacy == explicit_legacy


def test_cli_verwirft_unbekannte_energy_direction(tmp_path):
    with pytest.raises(SystemExit) as exc:
        rate_transitions.main([
            "prepare", "--out", str(tmp_path / "satz"),
            "--energy-direction", "build-up",
        ])
    assert exc.value.code == 2


def test_cli_csv_fehler_ist_kontrolliert(monkeypatch, tmp_path, capsys):
    from tools import rate_transitions as rt

    monkeypatch.setattr(
        rt, "befehl_fit", lambda _args: (_ for _ in ()).throw(csv.Error("kaputt"))
    )
    assert rt.main(["fit", "--dir", str(tmp_path)]) == 2
    assert "FEHLER: kaputt" in capsys.readouterr().err


def test_prepare_kandidaten_nutzt_explizite_fuenf_gerankte_versionen(
    monkeypatch, tmp_path
):
    from tools import rate_transitions as rt

    a, b = _ns_track("a"), _ns_track("b")
    paar = {
        "track_a": a,
        "track_b": b,
        "merkmale": {name: 0.5 for name in rt.NEUE_FAKTOREN},
    }
    kandidaten = [
        _pc(100.0 + index, 60.0 + index, 16, 1.0 - index / 10.0)
        for index in range(7)
    ]
    for rang, kandidat in enumerate(kandidaten, start=1):
        kandidat.rang = rang
    gerendert = []
    monkeypatch.setattr(rt, "lade_tracks_aus_cache", lambda _cache: [a, b])
    monkeypatch.setattr(rt, "sammle_kandidaten", lambda _tracks, _tol, _direction, **_kw: [paar])
    monkeypatch.setattr(
        rt, "rank_pair_candidates", lambda *_args, **_kwargs: kandidaten
    )
    def fake_render(_a, _b, pc, pair_id, n, clips, **_kwargs):
        gerendert.append(pc)
        (clips / f"{pair_id}_k{n}.wav").write_bytes(b"RIFF")
        return f"clips/{pair_id}_k{n}.wav", "pro_eq_swap"

    monkeypatch.setattr(rt, "rendere_kandidat", fake_render)
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"cache")
    args = SimpleNamespace(
        out=tmp_path / "satz",
        cache=str(cache),
        bpm_toleranz=2.0,
        nur_genre=None,
        anzahl=1,
        seed=1,
        max_versionen_pro_paar=5,
    )

    assert rt.befehl_prepare_kandidaten(args) == 0
    assert gerendert == kandidaten[:5]


@pytest.mark.parametrize(
    "option,wert",
    [
        ("--anzahl", "0"),
        ("--anzahl", str(rate_transitions.MAX_ANZAHL + 1)),
        ("--max-versionen-pro-paar", "0"),
        ("--max-versionen-pro-paar", "6"),
        ("--bpm-toleranz", "0"),
        ("--bpm-toleranz", "nan"),
        ("--bpm-toleranz", "inf"),
        ("--bpm-toleranz", str(rate_transitions.PAAR_BPM_MAX + 0.1)),
    ],
)
def test_cli_verwirft_ungueltige_prepare_bereiche(tmp_path, option, wert):
    with pytest.raises(SystemExit) as exc:
        rate_transitions.main(["prepare", "--out", str(tmp_path / "satz"), option, wert])
    assert exc.value.code == 2


def test_prepare_lehnt_jedes_vorhandene_ziel_vor_cachezugriff_ab(monkeypatch, tmp_path):
    ziel = tmp_path / "satz"
    ziel.mkdir()
    monkeypatch.setattr(
        rate_transitions,
        "lade_tracks_aus_cache",
        lambda _cache: pytest.fail("Cache darf bei vorhandenem Ziel nicht gelesen werden"),
    )
    args = SimpleNamespace(
        out=ziel, cache=None, bpm_toleranz=2.0, nur_genre=None,
        anzahl=1, seed=1, max_versionen_pro_paar=5,
    )
    assert rate_transitions.befehl_prepare_kandidaten(args) == 1


def test_prepare_untererfuellung_publiziert_keinen_teilsatz(monkeypatch, tmp_path):
    ziel = tmp_path / "satz"
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"cache")
    monkeypatch.setattr(rate_transitions, "lade_tracks_aus_cache", lambda _cache: [])
    monkeypatch.setattr(
        rate_transitions, "sammle_kandidaten", lambda *_args, **_kwargs: []
    )
    args = SimpleNamespace(
        out=ziel, cache=str(cache), bpm_toleranz=2.0, nur_genre=None,
        anzahl=2, seed=1, max_versionen_pro_paar=5,
    )
    assert rate_transitions.befehl_prepare_kandidaten(args) == 1
    assert not ziel.exists()
    assert list(tmp_path.glob(".satz.staging-*")) == []


@pytest.mark.parametrize(
    ("wrapper_name", "intern_name"),
    [
        ("befehl_prepare", "_befehl_prepare_intern"),
        ("befehl_prepare_kandidaten", "_befehl_prepare_kandidaten_intern"),
    ],
)
def test_prepare_wrapper_publiziert_nichtleeren_satz_windows_tauglich(
    monkeypatch, tmp_path, wrapper_name, intern_name
):
    ziel = tmp_path / wrapper_name

    def fake_intern(args):
        clips = Path(args.out) / "clips"
        clips.mkdir(parents=True)
        (clips / "001.wav").write_bytes(b"RIFF")
        return 0

    monkeypatch.setattr(rate_transitions, intern_name, fake_intern)
    monkeypatch.setattr(
        rate_transitions.os,
        "replace",
        lambda *_args: pytest.fail("Verzeichnis-Publikation darf os.replace nicht nutzen"),
    )
    args = SimpleNamespace(out=ziel)
    assert getattr(rate_transitions, wrapper_name)(args) == 0
    assert (ziel / "clips" / "001.wav").read_bytes() == b"RIFF"
    assert list(tmp_path.glob(f".{ziel.name}.staging-*")) == []


def test_prepare_publikation_wiederholt_einmaligen_permissionerror(
    monkeypatch, tmp_path
):
    ziel = tmp_path / "retry-erfolg"
    original_rename = rate_transitions.os.rename
    aufrufe = []
    wartezeiten = []

    def rename(src, dst):
        aufrufe.append((Path(src), Path(dst)))
        if len(aufrufe) == 1:
            raise PermissionError(5, "Scanner blockiert")
        return original_rename(src, dst)

    def fake_intern(args):
        (Path(args.out) / "clips").mkdir(parents=True)
        (Path(args.out) / "clips" / "001.wav").write_bytes(b"RIFF")
        return 0

    monkeypatch.setattr(rate_transitions.os, "rename", rename)
    monkeypatch.setattr(rate_transitions.time, "sleep", wartezeiten.append)
    monkeypatch.setattr(rate_transitions, "_befehl_prepare_intern", fake_intern)
    assert rate_transitions.befehl_prepare(SimpleNamespace(out=ziel)) == 0
    # Der erste Fehler ist simuliert; Windows/Scanner duerfen zusaetzlich reale,
    # aber weiterhin durch den Produktionscode begrenzte PermissionErrors liefern.
    assert 2 <= len(aufrufe) <= len(rate_transitions.PUBLISH_PERMISSION_BACKOFF_SECONDS) + 1
    assert wartezeiten == list(rate_transitions.PUBLISH_PERMISSION_BACKOFF_SECONDS[:len(aufrufe) - 1])
    assert (ziel / "clips" / "001.wav").read_bytes() == b"RIFF"
    assert list(tmp_path.glob(".retry-erfolg.staging-*")) == []


def test_prepare_publikation_ueberschreibt_nie_ziel_das_zwischen_retries_entsteht(
    monkeypatch, tmp_path
):
    ziel = tmp_path / "race-ziel"
    aufrufe = 0

    def rename(_src, dst):
        nonlocal aufrufe
        aufrufe += 1
        raced = Path(dst)
        raced.mkdir()
        (raced / "fremd.txt").write_bytes(b"nicht anfassen")
        raise PermissionError(5, "Scanner oder Ziel-Race")

    def fake_intern(args):
        (Path(args.out) / "clips").mkdir(parents=True)
        return 0

    monkeypatch.setattr(rate_transitions.os, "rename", rename)
    monkeypatch.setattr(
        rate_transitions.time, "sleep",
        lambda _sek: pytest.fail("Bei entstandenem Ziel darf kein Retry warten"),
    )
    monkeypatch.setattr(rate_transitions, "_befehl_prepare_intern", fake_intern)
    assert rate_transitions.befehl_prepare(SimpleNamespace(out=ziel)) == 1
    assert aufrufe == 1
    assert (ziel / "fremd.txt").read_bytes() == b"nicht anfassen"
    assert list(tmp_path.glob(".race-ziel.staging-*")) == []


def test_prepare_publikation_beendet_dauerhaften_permissionerror_kontrolliert(
    monkeypatch, tmp_path
):
    ziel = tmp_path / "retry-erschoepft"
    aufrufe = 0
    wartezeiten = []

    def rename(_src, _dst):
        nonlocal aufrufe
        aufrufe += 1
        raise PermissionError(5, "Scanner blockiert dauerhaft")

    def fake_intern(args):
        (Path(args.out) / "clips").mkdir(parents=True)
        return 0

    monkeypatch.setattr(rate_transitions.os, "rename", rename)
    monkeypatch.setattr(rate_transitions.time, "sleep", wartezeiten.append)
    monkeypatch.setattr(rate_transitions, "_befehl_prepare_intern", fake_intern)
    assert rate_transitions.befehl_prepare(SimpleNamespace(out=ziel)) == 1
    assert aufrufe == len(rate_transitions.PUBLISH_PERMISSION_BACKOFF_SECONDS) + 1
    assert wartezeiten == list(rate_transitions.PUBLISH_PERMISSION_BACKOFF_SECONDS)
    assert not ziel.exists()
    assert list(tmp_path.glob(".retry-erschoepft.staging-*")) == []


@pytest.mark.parametrize(
    ("wrapper_name", "intern_name"),
    [
        ("befehl_prepare", "_befehl_prepare_intern"),
        ("befehl_prepare_kandidaten", "_befehl_prepare_kandidaten_intern"),
    ],
)
def test_prepare_wrapper_untererfuellung_bleibt_unveroeffentlicht(
    monkeypatch, tmp_path, wrapper_name, intern_name
):
    ziel = tmp_path / wrapper_name

    def fake_intern(args):
        (Path(args.out) / "clips").mkdir(parents=True)
        return 1

    monkeypatch.setattr(rate_transitions, intern_name, fake_intern)
    args = SimpleNamespace(out=ziel)
    assert getattr(rate_transitions, wrapper_name)(args) == 1
    assert not ziel.exists()
    assert list(tmp_path.glob(f".{ziel.name}.staging-*")) == []


@pytest.mark.parametrize("wrapper_name", ["befehl_prepare", "befehl_prepare_kandidaten"])
def test_prepare_wrapper_veraendert_vorhandenen_zielsatz_nicht(
    tmp_path, wrapper_name
):
    ziel = tmp_path / wrapper_name
    ziel.mkdir()
    sentinel = ziel / "bestehend.txt"
    sentinel.write_bytes(b"unveraendert")
    assert getattr(rate_transitions, wrapper_name)(SimpleNamespace(out=ziel)) == 1
    assert sentinel.read_bytes() == b"unveraendert"


def test_prepare_einzel_schreibt_faktoren_und_plan_audit_vom_aktiven_kandidaten(
    monkeypatch, tmp_path, capsys
):
    a, b = _ns_track("a"), _ns_track("b")
    aktiv = _lokaler_pc(groove=0.91, score=0.83, harmonic=0.77)
    aktiv.rang = 2
    plan = TransitionPlan(
        mix_out_a=aktiv.t_out, mix_in_b=aktiv.t_in,
        fade_out_start=aktiv.t_out, fade_out_end=aktiv.t_out + 17.3,
        overlap=17.3, transition_type="filter_ride", target_sr=48000,
    )
    vorauswahl = {
        "track_a": a, "track_b": b,
        "merkmale": {name: 0.1 for name in rate_transitions.ALLE_FAKTOREN},
        "zusatz": {"overall_score": 0.1, "lufs_delta": 99.0},
    }
    gesehen = {}

    monkeypatch.setattr(rate_transitions, "lade_tracks_aus_cache", lambda _cache: [a, b])
    monkeypatch.setattr(rate_transitions, "sammle_kandidaten", lambda *_args: [vorauswahl])

    def fake_rendere(
        kandidat, pair_id, clips_dir, *, bpm_toleranz, energy_direction
    ):
        gesehen["bpm_toleranz"] = bpm_toleranz
        gesehen["energy_direction"] = energy_direction
        (clips_dir / f"{pair_id}.wav").write_bytes(b"RIFF")
        return f"clips/{pair_id}.wav", plan, aktiv.to_dict()

    monkeypatch.setattr(rate_transitions, "rendere_paar", fake_rendere)
    args = SimpleNamespace(
        out=tmp_path / "einzel", cache=None, bpm_toleranz=1.5,
        energy_direction="down", nur_genre=None, anzahl=1, seed=1,
        max_versionen_pro_paar=5,
    )
    assert rate_transitions.befehl_prepare(args) == 0

    zeile = rate_transitions.lies_csv(args.out / "merkmale.csv")[0]
    assert gesehen["bpm_toleranz"] == pytest.approx(1.5)
    assert gesehen["energy_direction"] == "down"
    assert float(zeile["groove"]) == pytest.approx(0.91)
    assert float(zeile["harmonic"]) == pytest.approx(0.77)
    assert float(zeile["overall_score"]) == pytest.approx(0.83)
    assert float(zeile["lufs_delta"]) == pytest.approx(-3.5)
    assert float(zeile["plan_mix_out_sec"]) == pytest.approx(aktiv.t_out)
    assert float(zeile["plan_mix_in_sec"]) == pytest.approx(aktiv.t_in)
    assert float(zeile["plan_overlap_sec"]) == pytest.approx(17.3)
    assert zeile["plan_transition_type"] == "filter_ride"
    assert int(zeile["plan_target_sr"]) == 48000
    assert int(zeile["kandidat_rang"]) == 2
    assert float(zeile["bpm_toleranz"]) == pytest.approx(1.5)
    assert zeile["energy_direction"] == "down"
    ausgabe = capsys.readouterr().out
    assert str(args.out) in ausgabe
    assert ".staging-" not in ausgabe


def test_renderfehler_hinterlaesst_weder_partial_noch_ziel(monkeypatch, tmp_path):
    def kaputt(_spec, pfad):
        Path(pfad).write_bytes(b"partial")
        raise RuntimeError("kaputt")

    monkeypatch.setattr(rate_transitions, "render_transition_clip", kaputt)
    with pytest.raises(RuntimeError, match="kaputt"):
        rate_transitions.rendere_kandidat(
            _ns_track("a"), _ns_track("b"), _pc(100.0, 60.0, 16, 0.8),
            "001", 1, tmp_path,
        )
    assert list(tmp_path.iterdir()) == []


def test_renderfehler_verwirft_auch_weitere_kandidaten_desselben_paars(
    monkeypatch, tmp_path
):
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"cache")
    a, b = _ns_track("a"), _ns_track("b")
    pcs = [_pc(100 + i, 60 + i, 16, 0.9 - i / 10) for i in range(3)]
    for rang, pc in enumerate(pcs, start=1):
        pc.rang = rang
    paar = {
        "track_a": a, "track_b": b,
        "merkmale": {name: 0.5 for name in rate_transitions.NEUE_FAKTOREN},
        "pair_candidates": pcs,
    }
    aufrufe = []

    def fake_render(_a, _b, pc, pair_id, n, clips, **_kwargs):
        aufrufe.append((pc, n))
        if pc is pcs[0]:
            raise RuntimeError("erster Kandidat kaputt")
        ziel = clips / f"{pair_id}_k{n}.wav"
        ziel.write_bytes(b"RIFF")
        return f"clips/{pair_id}_k{n}.wav", "pro_eq_swap"

    monkeypatch.setattr(rate_transitions, "lade_tracks_aus_cache", lambda _cache: [a, b])
    monkeypatch.setattr(
        rate_transitions, "sammle_kandidaten", lambda *_args, **_kwargs: [paar]
    )
    monkeypatch.setattr(rate_transitions, "rendere_kandidat", fake_render)
    args = SimpleNamespace(
        out=tmp_path / "satz", cache=str(cache), bpm_toleranz=2.0, nur_genre=None,
        anzahl=1, seed=1, max_versionen_pro_paar=3,
    )

    assert rate_transitions.befehl_prepare_kandidaten(args) == 1
    assert aufrufe == [(pcs[0], 1)]
    assert not args.out.exists()
    assert list(tmp_path.glob(".satz.staging-*")) == []


def _gueltige_kandidaten_csv_zeilen():
    merk = []
    bew = []
    for index in (1, 2):
        cid = f"001_k{index}"
        zeile = {
            "pair_id": "001",
            "clip_id": cid,
            "track_a": "C:/Musik/a.wav",
            "track_b": "C:/Musik/b.wav",
        }
        zeile.update({name: "0.5" for name in rate_transitions.KANDIDATEN_TEILWERTE})
        merk.append(zeile)
        bew.append({"pair_id": "001", "clip_id": cid, "note": "4", "gewaehlt": "1" if index == 1 else ""})
    return merk, bew


def test_kandidaten_csv_vertrag_ist_strikt_1_zu_1_eindeutig_und_numerisch():
    merk, bew = _gueltige_kandidaten_csv_zeilen()
    rate_transitions.validiere_kandidaten_csvs(merk, bew)

    with pytest.raises(ValueError, match="1:1"):
        rate_transitions.validiere_kandidaten_csvs(merk, bew[:-1])
    with pytest.raises(ValueError, match="nicht eindeutig"):
        rate_transitions.validiere_kandidaten_csvs(merk + [dict(merk[0])], bew)

    schlechte_note = [dict(z) for z in bew]
    schlechte_note[0]["note"] = "4.4"
    with pytest.raises(ValueError, match="Ganzzahl"):
        rate_transitions.validiere_kandidaten_csvs(merk, schlechte_note)

    zwei_sieger = [dict(z, gewaehlt="1") for z in bew]
    with pytest.raises(ValueError, match="mehr als ein Gewinner"):
        rate_transitions.validiere_kandidaten_csvs(merk, zwei_sieger)

    nicht_endlich = [dict(z) for z in merk]
    nicht_endlich[0][rate_transitions.KANDIDATEN_TEILWERTE[0]] = "nan"
    with pytest.raises(ValueError, match="0..1"):
        rate_transitions.validiere_kandidaten_csvs(nicht_endlich, bew)

    ohne_track = [dict(z) for z in merk]
    ohne_track[0]["track_b"] = "  "
    with pytest.raises(ValueError, match="track_a/track_b"):
        rate_transitions.validiere_kandidaten_csvs(ohne_track, bew)


@pytest.mark.parametrize("fall", ["note_fehlt", "unentschieden", "gewinnernote"])
def test_fit_verlangt_vollstaendige_menschliche_kandidatenentscheidung(fall):
    _, bew = _gueltige_kandidaten_csv_zeilen()
    if fall == "note_fehlt":
        bew[1]["note"] = ""
    elif fall == "unentschieden":
        for zeile in bew:
            zeile["gewaehlt"] = ""
    else:
        bew[0]["note"] = "1"
    with pytest.raises(ValueError):
        rate_transitions.validiere_vollstaendige_kandidatenbewertung(bew)


def test_fit_akzeptiert_explizite_keine_beste_entscheidung():
    _, bew = _gueltige_kandidaten_csv_zeilen()
    for zeile in bew:
        zeile["gewaehlt"] = "0"
    rate_transitions.validiere_vollstaendige_kandidatenbewertung(bew)


def test_unvollstaendige_bewertung_schreibt_weder_entwurf_noch_praeferenz(
    monkeypatch, tmp_path,
):
    rt = rate_transitions
    merk, bew = _gueltige_kandidaten_csv_zeilen()
    bew[1]["note"] = ""
    _stubbe_fit_binding_io(monkeypatch, rt, merk, bew)
    monkeypatch.setattr(
        rt, "_validiere_fit_bindung", lambda *_args: _manifest_mit_fit_snapshot(rt)
    )
    args = SimpleNamespace(
        dir=tmp_path, cache="cache.db", audit_report=tmp_path / "audit.json", seed=1,
    )
    assert rt.befehl_fit_kandidaten(args) == 1
    assert not (tmp_path / "candidate_preferences_entwurf.json").exists()


def test_cache_ladefehler_im_kandidatenfit_bleibt_fail_closed(monkeypatch, tmp_path):
    rt = rate_transitions
    merk, bew = _gueltige_kandidaten_csv_zeilen()
    _stubbe_fit_binding_io(monkeypatch, rt, merk, bew)
    monkeypatch.setattr(
        rt, "_validiere_fit_bindung", lambda *_args: _manifest_mit_fit_snapshot(rt)
    )
    monkeypatch.setattr(
        rt, "lade_tracks_aus_cache", lambda _path: (_ for _ in ()).throw(ValueError("Cache kaputt")),
    )
    args = SimpleNamespace(
        dir=tmp_path, cache="cache.db", audit_report=tmp_path / "audit.json", seed=1,
    )
    with pytest.raises(ValueError, match="Cache kaputt"):
        rt.befehl_fit_kandidaten(args)
    assert not (tmp_path / "candidate_preferences_entwurf.json").exists()


def test_bewertung_wird_unmittelbar_vor_fit_write_erneut_geprueft(monkeypatch, tmp_path):
    rt = rate_transitions
    merk, bew = _gueltige_kandidaten_csv_zeilen()
    bew_spaet = [dict(zeile) for zeile in bew]
    bew_spaet[1]["note"] = ""
    bew_reads = iter([bew, bew_spaet])
    _stubbe_fit_binding_io(monkeypatch, rt, merk, bew)

    def read(path, *_args):
        return merk if path.name == "merkmale.csv" else next(bew_reads)

    monkeypatch.setattr(rt, "_lies_fit_csv_gebunden", read)
    monkeypatch.setattr(
        rt, "_validiere_fit_bindung", lambda *_args: _manifest_mit_fit_snapshot(rt)
    )
    monkeypatch.setattr(rt, "lade_tracks_aus_cache", lambda _path: [])
    zeilen = [{"genre": "Psytrance", "pair_id": "001", "tracks": ("a", "b")}]
    monkeypatch.setattr(rt, "verbinde_bewertungen_kandidaten", lambda *a, **k: (zeilen, 0, 0))
    monkeypatch.setattr(rt, "filtere_reine_kandidatenpaare", lambda z: (z, {}))
    monkeypatch.setattr(
        rt, "_fit_kandidaten_genre",
        lambda *a, **k: (None, None, {"uebernommen": False, "grund": "Gate"}),
    )
    args = SimpleNamespace(
        dir=tmp_path, cache="cache.db", audit_report=tmp_path / "audit.json", seed=1,
    )
    with pytest.raises(ValueError, match="vollstaendige"):
        rt.befehl_fit_kandidaten(args)
    assert not (tmp_path / "candidate_preferences_entwurf.json").exists()


def test_audit_report_wird_unmittelbar_vor_fit_write_erneut_geprueft(monkeypatch, tmp_path):
    rt = rate_transitions
    merk, bew = _gueltige_kandidaten_csv_zeilen()
    _stubbe_fit_binding_io(monkeypatch, rt, merk, bew)
    bind_calls = []

    def bind(*_args):
        bind_calls.append(1)
        if len(bind_calls) == 2:
            raise ValueError("Audit-Report spaet veraendert")
        return _manifest_mit_fit_snapshot(rt)

    monkeypatch.setattr(rt, "_validiere_fit_bindung", bind)
    monkeypatch.setattr(rt, "lade_tracks_aus_cache", lambda _path: [])
    rows = [{"genre": "Psytrance", "pair_id": "001", "tracks": ("a", "b")}]
    monkeypatch.setattr(rt, "verbinde_bewertungen_kandidaten", lambda *a, **k: (rows, 0, 0))
    monkeypatch.setattr(rt, "filtere_reine_kandidatenpaare", lambda z: (z, {}))
    monkeypatch.setattr(
        rt, "_fit_kandidaten_genre",
        lambda *a, **k: (None, None, {"uebernommen": False, "grund": "Gate"}),
    )
    args = SimpleNamespace(
        dir=tmp_path, cache="cache.db", audit_report=tmp_path / "audit.json", seed=1,
    )
    with pytest.raises(ValueError, match="spaet veraendert"):
        rt.befehl_fit_kandidaten(args)
    assert len(bind_calls) == 2
    assert not (tmp_path / "candidate_preferences_entwurf.json").exists()


def _fit_binding_fixture(monkeypatch, tmp_path):
    rt = rate_transitions
    set_dir = tmp_path / "satz"
    set_dir.mkdir()
    clips_dir = set_dir / "clips"
    clips_dir.mkdir()
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"cache")
    build = {"scheme": rt.ALGORITHM_BUILD_SCHEME, "files": 2, "sha256": "a" * 64}
    cache_info = {"version": rt.CACHE_VERSION, "size": 5, "sha256": "b" * 64}
    clip_ids = ["001_k1", "001_k2"]
    for cid in clip_ids:
        sf.write(
            clips_dir / f"{cid}.wav",
            np.zeros((32, 2), dtype=np.float32),
            8000,
            subtype="PCM_16",
        )
    rt.schreibe_csv(
        set_dir / "merkmale.csv",
        ("pair_id", "clip_id", "clip"),
        [
            {"pair_id": "001", "clip_id": cid, "clip": f"clips/{cid}.wav"}
            for cid in clip_ids
        ],
    )
    rt.schreibe_csv(
        set_dir / "bewertung.csv",
        rt.BEWERTUNG_KANDIDATEN_SPALTEN,
        [
            {
                "pair_id": "001", "clip_id": cid, "note": "4",
                "gewaehlt": "1" if index == 0 else "", "zeit": "t",
            }
            for index, cid in enumerate(clip_ids)
        ],
    )
    manifest = {
        "format_version": rt.KANDIDATEN_MANIFEST_VERSION,
        "app_version": rt.APP_VERSION,
        "algorithm_build": build,
        "hearing_test_contract": {},
        "cache": cache_info,
        "render_args": {"anzahl": 1},
        "scoring_snapshot": _manifest_mit_fit_snapshot(rt)["scoring_snapshot"],
        "pairs": [{
            "pair_id": "001", "track_a": "A.wav", "track_b": "B.wav",
            "clips": [
                {
                    "clip_id": cid, "rank": index, "t_out": 10.0,
                    "t_in": 5.0, "blend_bars": 4, "overlap_sec": 8.0,
                    "rendered_transition_type": "pro_eq_swap",
                }
                for index, cid in enumerate(clip_ids, 1)
            ],
        }],
    }
    manifest_path = set_dir / rt.KANDIDATEN_MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    candidates = []
    for cid in clip_ids:
        info = sf.info(clips_dir / f"{cid}.wav")
        candidates.append({
            "clip_id": cid,
            "wav": {
                "samplerate": int(info.samplerate), "channels": int(info.channels),
                "frames": int(info.frames), "format": info.format, "subtype": info.subtype,
            },
            "kick_lag_seconds": [-0.006, 0.0, 0.006],
        })
    report = {
        "format_version": 1,
        "status": "passed",
        "ok": True,
        "set": {
            "path": str(set_dir.resolve()),
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            **rt._fingerprint_kandidatensatz(set_dir),
        },
        "cache": cache_info,
        "algorithm_build": build,
        "pairs": 1,
        "clips": 2,
        "candidates": candidates,
    }
    report_path = tmp_path / "audit.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(rt, "_algorithm_build_fingerprint", lambda: build)
    monkeypatch.setattr(rt, "_fingerprint_cache", lambda _path: {"size": 5, "sha256": "b" * 64})
    return set_dir, cache, report_path, manifest, report


def test_fit_bindet_nichtleeren_erfolgsreport_an_manifest_csv_wav_cache_und_build(
    monkeypatch, tmp_path
):
    rt = rate_transitions
    set_dir, cache, report_path, manifest, report = _fit_binding_fixture(monkeypatch, tmp_path)
    assert rt._validiere_fit_bindung(set_dir, cache, report_path) == manifest

    (set_dir / "nachtraeglich.txt").write_text("nicht auditiert", encoding="utf-8")
    with pytest.raises(ValueError, match="Kandidatensatz"):
        rt._validiere_fit_bindung(set_dir, cache, report_path)
    (set_dir / "nachtraeglich.txt").unlink()

    report["status"] = "failed"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="erfolgreicher"):
        rt._validiere_fit_bindung(set_dir, cache, report_path)


def _tausche_gueltige_bewertung_und_audit(
    rt, set_dir: Path, report_path: Path, report: dict
) -> None:
    rows = rt.lies_csv(set_dir / "bewertung.csv")
    rows[0]["note"] = "5"
    rt.schreibe_csv(
        set_dir / "bewertung.csv", rt.BEWERTUNG_KANDIDATEN_SPALTEN, rows
    )
    report["set"].update(rt._fingerprint_kandidatensatz(set_dir))
    report_path.write_text(json.dumps(report), encoding="utf-8")


def _stubbe_fit_nach_bindung(monkeypatch, rt, *, waehrend_fit=None):
    monkeypatch.setattr(rt, "validiere_kandidaten_csvs", lambda *_args: None)
    monkeypatch.setattr(
        rt, "validiere_vollstaendige_kandidatenbewertung", lambda *_args: None
    )
    monkeypatch.setattr(rt, "lade_tracks_aus_cache", lambda _path: [])
    rows = [{"genre": "Psytrance", "pair_id": "001", "tracks": ("a", "b")}]
    monkeypatch.setattr(
        rt, "verbinde_bewertungen_kandidaten", lambda *_a, **_k: (rows, 0, 0)
    )
    monkeypatch.setattr(rt, "filtere_reine_kandidatenpaare", lambda z: (z, {}))

    def fit(*_args, **_kwargs):
        if waehrend_fit is not None:
            waehrend_fit()
        return None, None, {"uebernommen": False, "grund": "Gate"}

    monkeypatch.setattr(rt, "_fit_kandidaten_genre", fit)


def test_fit_verwirft_gueltigen_satzwechsel_zwischen_einlesen_und_validieren(
    monkeypatch, tmp_path
):
    rt = rate_transitions
    set_dir, cache, report_path, _manifest, report = _fit_binding_fixture(
        monkeypatch, tmp_path
    )
    _stubbe_fit_nach_bindung(monkeypatch, rt)
    original = rt._lies_fit_csv_gebunden
    getauscht = False

    def read(path, token, digest_name):
        nonlocal getauscht
        rows = original(path, token, digest_name)
        if digest_name == "bewertung_sha256" and not getauscht:
            getauscht = True
            _tausche_gueltige_bewertung_und_audit(rt, set_dir, report_path, report)
        return rows

    monkeypatch.setattr(rt, "_lies_fit_csv_gebunden", read)
    merge = Mock()
    monkeypatch.setattr(
        rt.candidate_preferences, "merge_user_preferences_atomically", merge
    )
    args = SimpleNamespace(
        dir=set_dir, cache=cache, audit_report=report_path, seed=1
    )

    assert rt.befehl_fit_kandidaten(args) == 1
    merge.assert_not_called()
    assert not (set_dir / "candidate_preferences_entwurf.json").exists()


def test_fit_verwirft_gueltigen_satzwechsel_waehrend_fit(
    monkeypatch, tmp_path
):
    rt = rate_transitions
    set_dir, cache, report_path, _manifest, report = _fit_binding_fixture(
        monkeypatch, tmp_path
    )
    _stubbe_fit_nach_bindung(
        monkeypatch,
        rt,
        waehrend_fit=lambda: _tausche_gueltige_bewertung_und_audit(
            rt, set_dir, report_path, report
        ),
    )
    merge = Mock()
    monkeypatch.setattr(
        rt.candidate_preferences, "merge_user_preferences_atomically", merge
    )
    args = SimpleNamespace(
        dir=set_dir, cache=cache, audit_report=report_path, seed=1
    )

    with pytest.raises(ValueError, match="waehrend fit veraendert"):
        rt.befehl_fit_kandidaten(args)
    merge.assert_not_called()
    assert not (set_dir / "candidate_preferences_entwurf.json").exists()


def _stubbe_bestandenes_fit(monkeypatch, rt):
    gewichte = {name: 0.0 for name in rt.KANDIDATEN_TEILWERTE}
    gewichte["harmonic"] = 1.0
    monkeypatch.setattr(
        rt,
        "_fit_kandidaten_genre",
        lambda *_a, **_k: (
            gewichte,
            ["pssi_phrase"],
            {"uebernommen": True, "grund": "ok"},
        ),
    )


def test_fit_verwirft_satzwechsel_am_finalen_binding_check(
    monkeypatch, tmp_path
):
    rt = rate_transitions
    set_dir, cache, report_path, _manifest, report = _fit_binding_fixture(
        monkeypatch, tmp_path
    )
    _stubbe_fit_nach_bindung(monkeypatch, rt)
    _stubbe_bestandenes_fit(monkeypatch, rt)
    override = tmp_path / "override.json"
    monkeypatch.setenv("HPG_CANDIDATE_PREFERENCES_FILE", str(override))
    original = rt._bestaetige_fit_binding
    aufrufe = 0

    def confirm(token, ordner, audit):
        nonlocal aufrufe
        aufrufe += 1
        if aufrufe == 5:
            _tausche_gueltige_bewertung_und_audit(
                rt, set_dir, report_path, report
            )
        return original(token, ordner, audit)

    monkeypatch.setattr(rt, "_bestaetige_fit_binding", confirm)
    merge = Mock()
    monkeypatch.setattr(
        rt.candidate_preferences, "merge_user_preferences_atomically", merge
    )
    args = SimpleNamespace(
        dir=set_dir, cache=cache, audit_report=report_path, seed=1
    )

    with pytest.raises(ValueError, match="waehrend fit veraendert"):
        rt.befehl_fit_kandidaten(args)
    assert aufrufe == 5
    merge.assert_not_called()
    assert not override.exists()
    assert not (set_dir / "candidate_preferences_entwurf.json").exists()


def test_fit_schreibt_nach_satzwechsel_im_fehlgeschlagenen_merge_nichts(
    monkeypatch, tmp_path
):
    rt = rate_transitions
    set_dir, cache, report_path, _manifest, report = _fit_binding_fixture(
        monkeypatch, tmp_path
    )
    _stubbe_fit_nach_bindung(monkeypatch, rt)
    _stubbe_bestandenes_fit(monkeypatch, rt)
    override = tmp_path / "override.json"
    monkeypatch.setenv("HPG_CANDIDATE_PREFERENCES_FILE", str(override))

    def failing_merge(*_args, **_kwargs):
        _tausche_gueltige_bewertung_und_audit(
            rt, set_dir, report_path, report
        )
        raise RuntimeError("absichtlicher Merge-Fehler")

    monkeypatch.setattr(
        rt.candidate_preferences,
        "merge_user_preferences_atomically",
        failing_merge,
    )
    args = SimpleNamespace(
        dir=set_dir, cache=cache, audit_report=report_path, seed=1
    )

    with pytest.raises(ValueError, match="waehrend fit veraendert"):
        rt.befehl_fit_kandidaten(args)
    assert not override.exists()
    assert not (set_dir / "candidate_preferences_entwurf.json").exists()


@pytest.mark.parametrize(
    "fall",
    [
        "pairs_bool", "clips_bool", "candidate_fehlt", "candidate_doppelt",
        "candidate_vertauscht", "candidate_schema", "wav_schema", "wav_format",
        "wav_subtype", "wav_channels", "wav_samplerate_bool", "wav_frames_null",
        "lags_anzahl", "lag_bool", "lag_nan", "lag_inf", "lag_zu_gross",
    ],
)
def test_fit_report_korruption_bleibt_fail_closed(monkeypatch, tmp_path, fall):
    rt = rate_transitions
    set_dir, cache, report_path, _manifest, report = _fit_binding_fixture(monkeypatch, tmp_path)
    if fall == "pairs_bool":
        report["pairs"] = True
    elif fall == "clips_bool":
        report["clips"] = True
    elif fall == "candidate_fehlt":
        report["candidates"].pop()
    elif fall == "candidate_doppelt":
        report["candidates"][1]["clip_id"] = "001_k1"
    elif fall == "candidate_vertauscht":
        report["candidates"].reverse()
    elif fall == "candidate_schema":
        report["candidates"][0]["extra"] = 1
    elif fall == "wav_schema":
        report["candidates"][0]["wav"].pop("frames")
    elif fall == "wav_format":
        report["candidates"][0]["wav"]["format"] = "AIFF"
    elif fall == "wav_subtype":
        report["candidates"][0]["wav"]["subtype"] = "FLOAT"
    elif fall == "wav_channels":
        report["candidates"][0]["wav"]["channels"] = 1
    elif fall == "wav_samplerate_bool":
        report["candidates"][0]["wav"]["samplerate"] = True
    elif fall == "wav_frames_null":
        report["candidates"][0]["wav"]["frames"] = 0
    elif fall == "lags_anzahl":
        report["candidates"][0]["kick_lag_seconds"] = [0.0, 0.0]
    elif fall == "lag_bool":
        report["candidates"][0]["kick_lag_seconds"][0] = True
    elif fall == "lag_nan":
        report["candidates"][0]["kick_lag_seconds"][0] = float("nan")
    elif fall == "lag_inf":
        report["candidates"][0]["kick_lag_seconds"][0] = float("inf")
    elif fall == "lag_zu_gross":
        report["candidates"][0]["kick_lag_seconds"][0] = 0.006001
    report_path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError):
        rt._validiere_fit_bindung(set_dir, cache, report_path)


def test_fit_report_bindet_clip_ids_auch_semantisch_an_beide_csvs(monkeypatch, tmp_path):
    rt = rate_transitions
    set_dir, cache, report_path, _manifest, report = _fit_binding_fixture(monkeypatch, tmp_path)
    rows = rt.lies_csv(set_dir / "merkmale.csv")
    rows.reverse()
    rt.schreibe_csv(set_dir / "merkmale.csv", ("pair_id", "clip_id", "clip"), rows)
    report["set"].update(rt._fingerprint_kandidatensatz(set_dir))
    report_path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="nicht exakt 1:1 geordnet"):
        rt._validiere_fit_bindung(set_dir, cache, report_path)


def test_fit_bleibt_mit_altem_kandidatensatz_ohne_neue_auditfelder_kompatibel():
    merk, bew = _gueltige_kandidaten_csv_zeilen()
    assert all("bpm_toleranz" not in row and "energy_direction" not in row for row in merk)
    rate_transitions.validiere_kandidaten_csvs(merk, bew)
    zeilen, ohne, verworfen = rate_transitions.verbinde_bewertungen_kandidaten(
        merk, bew
    )
    assert len(zeilen) == 2 and ohne == 0 and verworfen == 0


def test_server_whitelist_verdeckt_scoring_vertrag():
    from tools.hoertest_server import KANDIDAT_ANZEIGE_FELDER, lade_uebersicht_kandidaten

    merkmale = [{
        "pair_id": "001", "clip_id": "001_k1", "clip": "clips/001_k1.wav",
        "crossfade_sek": "16", "bpm_toleranz": "1.5",
        "energy_direction": "down", "score": "0.99",
        "track_a": "a.wav", "track_b": "b.wav",
    }]
    bewertung = [{"pair_id": "001", "clip_id": "001_k1", "note": "", "gewaehlt": ""}]
    daten = lade_uebersicht_kandidaten(
        merkmale, bewertung, {"001": {"seed": 1, "clips": ["001_k1"]}}
    )
    assert set(daten[0]["clips"][0]) == set(KANDIDAT_ANZEIGE_FELDER)
    assert "bpm_toleranz" not in daten[0]["clips"][0]
    assert "energy_direction" not in daten[0]["clips"][0]


def _schreibe_testcache(pfad: Path, tracks, *, marker=None, row_version=None):
    from hpg_core.caching import CACHE_VERSION, track_to_dict
    conn = sqlite3.connect(pfad)
    conn.execute("CREATE TABLE cache (key TEXT PRIMARY KEY, filepath TEXT, version INTEGER, data TEXT)")
    marker_version = CACHE_VERSION if marker is None else marker
    conn.execute(
        "INSERT INTO cache VALUES ('version', 'system', ?, 'metadata')",
        (marker_version,),
    )
    for index, track in enumerate(tracks):
        conn.execute(
            "INSERT INTO cache VALUES (?, ?, ?, ?)",
            (
                f"k{index}", track.filePath,
                CACHE_VERSION if row_version is None else row_version,
                json.dumps(track_to_dict(track)),
            ),
        )
    conn.commit()
    conn.close()


def test_cache_vor_render_ist_strikt_aktuell_und_ohne_windows_duplikate(tmp_path):
    from hpg_core.caching import CACHE_VERSION
    from hpg_core.models import Track

    def cache_track(path, name):
        return Track(
            path,
            name,
            duration=300.0,
            bpm=138.0,
            analysis_mode="librosa_full_or_tail",
        )

    gueltig = tmp_path / "ok.db"
    _schreibe_testcache(gueltig, [cache_track(r"C:\\Musik\\A.wav", "A.wav")])
    assert [t.fileName for t in rate_transitions.lade_tracks_aus_cache(str(gueltig))] == ["A.wav"]

    alt = tmp_path / "alt.db"
    _schreibe_testcache(alt, [cache_track(r"C:\\Musik\\A.wav", "A.wav")], marker=CACHE_VERSION - 1)
    with pytest.raises(ValueError, match="Marker"):
        rate_transitions.lade_tracks_aus_cache(str(alt))

    falsche_zeile = tmp_path / "row.db"
    _schreibe_testcache(
        falsche_zeile, [cache_track(r"C:\\Musik\\A.wav", "A.wav")],
        row_version=CACHE_VERSION - 1,
    )
    with pytest.raises(ValueError, match="Version"):
        rate_transitions.lade_tracks_aus_cache(str(falsche_zeile))

    kaputtes_json = tmp_path / "json.db"
    _schreibe_testcache(kaputtes_json, [cache_track(r"C:\\Musik\\A.wav", "A.wav")])
    conn = sqlite3.connect(kaputtes_json)
    conn.execute("UPDATE cache SET data = '{' WHERE key = 'k0'")
    conn.commit()
    conn.close()
    with pytest.raises(ValueError, match="JSON"):
        rate_transitions.lade_tracks_aus_cache(str(kaputtes_json))

    falsches_schema = tmp_path / "schema.db"
    conn = sqlite3.connect(falsches_schema)
    conn.execute("CREATE TABLE cache (key TEXT PRIMARY KEY, data TEXT)")
    conn.commit()
    conn.close()
    with pytest.raises(ValueError, match="Schema"):
        rate_transitions.lade_tracks_aus_cache(str(falsches_schema))

    doppelt = tmp_path / "dup.db"
    _schreibe_testcache(
        doppelt,
        [
            cache_track(r"C:\\Musik\\A.wav", "A.wav"),
            cache_track(r"c:/musik/a.wav", "a.wav"),
        ],
    )
    with pytest.raises(ValueError, match="doppelt"):
        rate_transitions.lade_tracks_aus_cache(str(doppelt))


def test_scoring_snapshot_laesst_jede_live_quelle_genau_einmal_einfliessen(
    monkeypatch,
):
    rt = rate_transitions
    aufrufe = {"toleranzen": 0, "praeferenzen": 0, "wahlen": 0}
    basis = json.loads(json.dumps(rt.GENRE_TRANSITION_TOLERANCES))
    pref_gewichte = {
        key: 1.0 / len(rt.KANDIDATEN_GEWICHT_SCHLUESSEL)
        for key in rt.KANDIDATEN_GEWICHT_SCHLUESSEL
    }
    wahl_key = rt.candidate_choices.schluessel("A.wav", "B.wav")

    def lade_toleranzen():
        aufrufe["toleranzen"] += 1
        return basis

    def lade_praeferenzen():
        aufrufe["praeferenzen"] += 1
        return {
            "Psytrance": {
                "gewichte": pref_gewichte,
                "schema_rang": ["analyzer"],
            }
        }

    def lade_wahlen():
        aufrufe["wahlen"] += 1
        return {wahl_key: {"t_out": 10.0, "t_in": 20.0, "blend_bars": 8}}

    monkeypatch.setattr(rt.tolerances, "load_tolerances", lade_toleranzen)
    monkeypatch.setattr(
        rt.candidate_preferences,
        "load_candidate_preferences",
        lade_praeferenzen,
    )
    monkeypatch.setattr(rt.candidate_choices, "snapshot", lade_wahlen)
    snapshot = rt._baue_scoring_snapshot(SimpleNamespace(
        bpm_toleranz=1.5,
        energy_direction="down",
    ))

    assert aufrufe == {"toleranzen": 1, "praeferenzen": 1, "wahlen": 1}
    assert snapshot["rank_args"] == {
        "bpm_tolerance": 1.5,
        "energy_direction": "down",
        "harmonic_strictness": 7,
        "allow_experimental": True,
    }
    effektiv = snapshot["candidate_tolerances_by_genre"]["Psytrance"]
    assert {key: effektiv[key] for key in pref_gewichte} == pref_gewichte
    for key in rt.NICHT_GEWICHT_SCHLUESSEL:
        assert effektiv[key] == pytest.approx(basis["Psytrance"][key])
    assert snapshot["candidate_tolerances_fallback"] == {
        key: float(basis[rt.CANONICAL_GENRES[0]][key])
        for key in (
            *rt.KANDIDATEN_GEWICHT_SCHLUESSEL,
            *rt.NICHT_GEWICHT_SCHLUESSEL,
        )
    }
    assert snapshot["candidate_schema_ranks_by_genre"]["Psytrance"] == ["analyzer"]
    assert snapshot["candidate_schema_rank_fallback"] == []
    assert snapshot["candidate_choices"][wahl_key]["blend_bars"] == 8


def test_rank_mit_snapshot_verhindert_jeden_live_fallback(monkeypatch):
    rt = rate_transitions
    a = _ns_track("A.wav")
    b = _ns_track("B.wav")
    key = rt.candidate_choices.schluessel(a.filePath, b.filePath)
    snapshot = {
        "rank_args": {
            "bpm_tolerance": 1.75,
            "energy_direction": "auto",
            "harmonic_strictness": 7,
            "allow_experimental": True,
        },
        "candidate_tolerances_by_genre": {"Psytrance": {"x": 1.0}},
        "candidate_tolerances_fallback": {"fallback": 1.0},
        "candidate_schema_ranks_by_genre": {"Psytrance": ["analyzer"]},
        "candidate_schema_rank_fallback": [],
        "candidate_choices": {key: {"t_out": 1.0, "t_in": 2.0, "blend_bars": 8}},
    }
    gesehen = []
    monkeypatch.setattr(
        rt,
        "rank_pair_candidates",
        lambda _a, _b, **kwargs: gesehen.append(kwargs) or [],
    )

    rt._rank_pair_mit_snapshot(a, b, scoring_snapshot=snapshot)
    unbekannt = _ns_track("unknown.wav", genre="Unknown")
    rt._rank_pair_mit_snapshot(unbekannt, b, scoring_snapshot=snapshot)

    assert gesehen[0] == {
        "bpm_tolerance": 1.75,
        "energy_direction": None,
        "harmonic_strictness": 7,
        "allow_experimental": True,
        "tolerances": {"x": 1.0},
        "schema_rang": ["analyzer"],
        "wahl": {"t_out": 1.0, "t_in": 2.0, "blend_bars": 8},
    }
    assert gesehen[1]["tolerances"] == {"fallback": 1.0}
    assert gesehen[1]["schema_rang"] == []
    assert gesehen[1]["wahl"] == {}


def test_cache_lader_lehnt_nichtleeres_wal_vor_sqlite_ab(
    monkeypatch, tmp_path,
):
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"SQLite")
    Path(f"{cache}-wal").write_bytes(b"pending")
    monkeypatch.setattr(
        rate_transitions.sqlite3,
        "connect",
        lambda *_args, **_kwargs: pytest.fail("SQLite darf nicht geoeffnet werden"),
    )
    with pytest.raises(ValueError, match="WAL"):
        rate_transitions.lade_tracks_aus_cache(str(cache))


def test_cache_lader_nutzt_immutable_uri(tmp_path, monkeypatch):
    cache = tmp_path / "cache mit leerzeichen.db"
    _schreibe_testcache(cache, [])
    original = sqlite3.connect
    gesehen = {}

    def connect(database, *args, **kwargs):
        gesehen["database"] = database
        gesehen["uri"] = kwargs.get("uri")
        return original(database, *args, **kwargs)

    monkeypatch.setattr(rate_transitions.sqlite3, "connect", connect)
    assert rate_transitions.lade_tracks_aus_cache(str(cache)) == []
    assert gesehen["uri"] is True
    assert "mode=ro&immutable=1" in gesehen["database"]
    assert "%20" in gesehen["database"]


def test_cache_fingerprint_ist_deterministisch_und_inhaltsgebunden(tmp_path):
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"abc")
    erster = rate_transitions._fingerprint_cache(cache)
    assert erster == rate_transitions._fingerprint_cache(cache)
    assert erster["size"] == 3
    assert len(erster["sha256"]) == 64
    cache.write_bytes(b"abcd")
    assert rate_transitions._fingerprint_cache(cache) != erster


def test_algorithmus_build_digest_ist_lokal_deterministisch_und_inhaltsgebunden(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "hpg_core" / "nested").mkdir(parents=True)
    (tmp_path / "tools" / "rate_transitions.py").write_bytes(b"producer")
    source = tmp_path / "hpg_core" / "nested" / "algorithm.py"
    source.write_bytes(b"v1")

    first = rate_transitions._algorithm_build_fingerprint(tmp_path)
    assert first == rate_transitions._algorithm_build_fingerprint(tmp_path)
    assert first["scheme"] == rate_transitions.ALGORITHM_BUILD_SCHEME
    assert first["files"] == 2
    assert len(first["sha256"]) == 64
    source.write_bytes(b"v2")
    assert rate_transitions._algorithm_build_fingerprint(tmp_path) != first


def _producer_test_snapshot(bpm_tolerance=2.0):
    return {
        "rank_args": {
            "bpm_tolerance": bpm_tolerance,
            "energy_direction": "auto",
            "harmonic_strictness": 7,
            "allow_experimental": True,
        },
        "candidate_tolerances_by_genre": {},
        "candidate_tolerances_fallback": {},
        "candidate_schema_ranks_by_genre": {},
        "candidate_schema_rank_fallback": [],
        "candidate_choices": {},
    }


def _producer_test_args(tmp_path, cache, *, anzahl=1, max_versionen=2):
    return SimpleNamespace(
        out=tmp_path / "satz",
        cache=str(cache),
        bpm_toleranz=2.0,
        energy_direction=None,
        nur_genre="Psytrance",
        anzahl=anzahl,
        seed=20260820,
        max_versionen_pro_paar=max_versionen,
        transition_type_mode="kontrolliert",
        harmonic_strictness=4,
        allow_experimental=False,
    )


def test_kandidaten_manifest_beschreibt_exakten_publizierten_prefix(
    monkeypatch, tmp_path,
):
    rt = rate_transitions
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"stable-cache")
    a, b = _ns_track("A.wav"), _ns_track("B.wav")
    pcs = [_pc(100.0 + n, 60.0 + n, 8, 0.9 - n / 10) for n in range(2)]
    for rang, pc in enumerate(pcs, start=1):
        pc.rang = rang
    paar = {
        "track_a": a,
        "track_b": b,
        "merkmale": {name: 0.5 for name in rt.KANDIDATEN_TEILWERTE},
        "pair_candidates": pcs,
    }
    snapshot = _producer_test_snapshot()
    monkeypatch.setattr(rt, "lade_tracks_aus_cache", lambda _cache: [a, b])
    monkeypatch.setattr(rt, "_baue_scoring_snapshot", lambda _args: snapshot)
    monkeypatch.setattr(
        rt,
        "sammle_kandidaten",
        lambda *_args, **_kwargs: [paar],
    )

    def render(_a, _b, _pc, pair_id, n, clips, **_kwargs):
        (clips / f"{pair_id}_k{n}.wav").write_bytes(f"clip-{n}".encode())
        return f"clips/{pair_id}_k{n}.wav", "pro_eq_swap"

    monkeypatch.setattr(rt, "rendere_kandidat", render)
    args = _producer_test_args(tmp_path, cache)
    assert rt.befehl_prepare_kandidaten(args) == 0

    manifest = json.loads(
        (args.out / rt.KANDIDATEN_MANIFEST_NAME).read_text(encoding="utf-8")
    )
    assert set(manifest) == {
        "format_version", "app_version", "algorithm_build",
        "hearing_test_contract", "cache", "render_args", "scoring_snapshot", "pairs",
    }
    assert manifest["format_version"] == rt.KANDIDATEN_MANIFEST_VERSION
    assert manifest["app_version"] == rt.APP_VERSION
    assert manifest["algorithm_build"] == rt._algorithm_build_fingerprint()
    assert manifest["hearing_test_contract"] == {
        "harmonic_gate_scope": rt.HARMONIC_GATE_SCOPE,
        "minimum_harmonic_score": rt.MIN_HARMONIC_SCORE,
    }
    assert manifest["cache"] == {
        "version": rt.CACHE_VERSION,
        **rt._fingerprint_cache(cache),
    }
    assert manifest["scoring_snapshot"] == snapshot
    assert manifest["render_args"] == {
        "anzahl": 1,
        "max_versionen_pro_paar": 2,
        "nur_genre": "Psytrance",
        "transition_type_mode": "kontrolliert",
        "seed": 20260820,
    }
    assert manifest["pairs"][0]["track_a"] == "A.wav"
    assert manifest["pairs"][0]["track_b"] == "B.wav"
    assert [clip["clip_id"] for clip in manifest["pairs"][0]["clips"]] == [
        "001_k1", "001_k2",
    ]
    assert [clip["rank"] for clip in manifest["pairs"][0]["clips"]] == [1, 2]
    assert {clip["rendered_transition_type"] for clip in manifest["pairs"][0]["clips"]} == {
        "pro_eq_swap"
    }


def test_prepare_verwirft_codewechsel_waehrend_erzeugung(monkeypatch, tmp_path):
    rt = rate_transitions
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"stable-cache")
    a, b = _ns_track("A.wav"), _ns_track("B.wav")
    pc = _pc(100.0, 60.0, 8, 0.9)
    pc.rang = 1
    monkeypatch.setattr(rt, "lade_tracks_aus_cache", lambda _cache: [a, b])
    monkeypatch.setattr(rt, "_baue_scoring_snapshot", lambda _args: _producer_test_snapshot())
    monkeypatch.setattr(rt, "sammle_kandidaten", lambda *_args, **_kwargs: [{
        "track_a": a,
        "track_b": b,
        "merkmale": {name: 0.5 for name in rt.KANDIDATEN_TEILWERTE},
        "pair_candidates": [pc],
    }])
    monkeypatch.setattr(
        rt,
        "rendere_kandidat",
        lambda _a, _b, _pc, pair_id, n, clips, **_kwargs: (
            (clips / f"{pair_id}_k{n}.wav").write_bytes(b"clip")
            and (f"clips/{pair_id}_k{n}.wav", "pro_eq_swap")
        ),
    )
    builds = iter([
        {"scheme": rt.ALGORITHM_BUILD_SCHEME, "files": 2, "sha256": "a" * 64},
        {"scheme": rt.ALGORITHM_BUILD_SCHEME, "files": 2, "sha256": "b" * 64},
    ])
    monkeypatch.setattr(rt, "_algorithm_build_fingerprint", lambda: next(builds))
    args = _producer_test_args(tmp_path, cache, max_versionen=1)

    with pytest.raises(RuntimeError, match="Build-Dateien"):
        rt.befehl_prepare_kandidaten(args)
    assert not args.out.exists()


def test_renderfehler_verwirft_ganzes_paar_und_nutzt_reserve(
    monkeypatch, tmp_path,
):
    rt = rate_transitions
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"stable-cache")
    a1, b1 = _ns_track("bad-a.wav"), _ns_track("bad-b.wav")
    a2, b2 = _ns_track("good-a.wav"), _ns_track("good-b.wav")

    def pcs():
        result = [_pc(100.0 + n, 60.0 + n, 8, 0.9 - n / 10) for n in range(2)]
        for rang, pc in enumerate(result, start=1):
            pc.rang = rang
        return result

    paare = [
        {"track_a": a1, "track_b": b1, "merkmale": {name: 0.4 for name in rt.KANDIDATEN_TEILWERTE}, "pair_candidates": pcs()},
        {"track_a": a2, "track_b": b2, "merkmale": {name: 0.6 for name in rt.KANDIDATEN_TEILWERTE}, "pair_candidates": pcs()},
    ]
    monkeypatch.setattr(rt, "lade_tracks_aus_cache", lambda _cache: [a1, b1, a2, b2])
    monkeypatch.setattr(rt, "_baue_scoring_snapshot", lambda _args: _producer_test_snapshot())
    monkeypatch.setattr(rt, "sammle_kandidaten", lambda *_args, **_kwargs: paare)
    monkeypatch.setattr(rt, "maximin_auswahl", lambda *_args, **_kwargs: [0, 1])

    def render(a, _b, _pc, pair_id, n, clips, **_kwargs):
        (clips / f"{pair_id}_k{n}.wav").write_bytes(a.filePath.encode())
        if a is a1 and n == 2:
            raise RuntimeError("zweiter Kandidat kaputt")
        return f"clips/{pair_id}_k{n}.wav", "pro_eq_swap"

    monkeypatch.setattr(rt, "rendere_kandidat", render)
    args = _producer_test_args(tmp_path, cache)
    assert rt.befehl_prepare_kandidaten(args) == 0
    clips = sorted((args.out / "clips").iterdir())
    assert [path.name for path in clips] == ["001_k1.wav", "001_k2.wav"]
    assert all(path.read_bytes() == b"good-a.wav" for path in clips)
    manifest = json.loads((args.out / rt.KANDIDATEN_MANIFEST_NAME).read_text())
    assert manifest["pairs"][0]["track_a"] == "good-a.wav"


def test_cacheaenderung_verwirft_gesamtes_staging(monkeypatch, tmp_path):
    rt = rate_transitions
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"stable-cache")
    a, b = _ns_track("A.wav"), _ns_track("B.wav")
    pc = _pc(100.0, 60.0, 8, 0.9)
    pc.rang = 1
    paar = {"track_a": a, "track_b": b, "merkmale": {name: 0.5 for name in rt.KANDIDATEN_TEILWERTE}, "pair_candidates": [pc]}
    monkeypatch.setattr(rt, "lade_tracks_aus_cache", lambda _cache: [a, b])
    monkeypatch.setattr(rt, "_baue_scoring_snapshot", lambda _args: _producer_test_snapshot())
    monkeypatch.setattr(rt, "sammle_kandidaten", lambda *_args, **_kwargs: [paar])
    monkeypatch.setattr(
        rt,
        "rendere_kandidat",
        lambda _a, _b, _pc, pair_id, n, clips, **_kwargs: (
            (clips / f"{pair_id}_k{n}.wav").write_bytes(b"RIFF"),
            (f"clips/{pair_id}_k{n}.wav", "pro_eq_swap"),
        )[1],
    )
    fingerprints = iter([
        {"size": 1, "sha256": "a" * 64},
        {"size": 2, "sha256": "b" * 64},
    ])
    monkeypatch.setattr(rt, "_fingerprint_cache", lambda _cache: next(fingerprints))
    args = _producer_test_args(tmp_path, cache, max_versionen=1)
    with pytest.raises(RuntimeError, match="Cache wurde"):
        rt.befehl_prepare_kandidaten(args)
    assert not args.out.exists()
    assert list(tmp_path.glob(".satz.staging-*")) == []


def test_transition_type_override_ist_eng_und_modusgebunden(monkeypatch, tmp_path):
    rt = rate_transitions
    pc = _pc(100.0, 60.0, 8, 0.8)
    a, b = _ns_track("a.wav"), _ns_track("b.wav")

    def render(_spec, pfad):
        Path(pfad).write_bytes(b"RIFF")

    monkeypatch.setattr(rt, "render_transition_clip", render)
    _clip, transition_type = rt.rendere_kandidat(
        a, b, pc, "001", 1, tmp_path,
        transition_type_mode="produktion",
        transition_type_override="bass_swap",
    )
    assert transition_type == "bass_swap"
    with pytest.raises(ValueError, match="Kontrollierter"):
        rt.rendere_kandidat(
            a, b, pc, "002", 1, tmp_path,
            transition_type_mode="kontrolliert",
            transition_type_override="bass_swap",
        )
    with pytest.raises(ValueError, match="Nicht unterstuetzter"):
        rt.rendere_kandidat(
            a, b, pc, "003", 1, tmp_path,
            transition_type_mode="produktion",
            transition_type_override="unbekannt",
        )


def test_atomare_json_schreibgrenze_verwirft_nan_ohne_rest(tmp_path):
    ziel = tmp_path / "manifest.json"
    with pytest.raises(ValueError):
        rate_transitions._schreibe_json_atomar(ziel, {"wert": float("nan")})
    assert not ziel.exists()
    assert list(tmp_path.iterdir()) == []
