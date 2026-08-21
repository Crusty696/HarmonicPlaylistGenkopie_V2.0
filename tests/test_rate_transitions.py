"""Tests fuer das Hoertest-Werkzeug tools/rate_transitions.py.

Geprueft wird ausschliesslich die REINE Logik: Maximin-Auswahl, CSV-Verbinden,
Log-Likelihood, Bootstrap, Gewichtsableitung und das Datenlage-Urteil.

Kein Test rendert Audio und kein Test liest die Cache-Datenbank des Nutzers —
beides waere langsam, nicht reproduzierbar und wuerde fremde Daten anfassen.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import math
import pathlib

import numpy as np
import pytest

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


def test_rendere_paar_reicht_das_beatgrid_an_den_renderer_durch(monkeypatch):
    """Ohne diese Felder schaetzt der Renderer den ersten Beat statt das
    bekannte Rekordbox-Beatgrid zu nutzen — und alignt nur auf Beat-Ebene."""
    a = _FakeTrack("A.wav", 140.0, 400.0, first_downbeat=0.0123, confidence=1.0)
    b = _FakeTrack("B.wav", 140.0, 400.0, first_downbeat=0.0456, confidence=1.0)
    gesehen = {}

    monkeypatch.setattr(
        rate_transitions, "calculate_paired_mix_points", lambda x, y: (300.0, 30.0))
    monkeypatch.setattr(
        rate_transitions, "geplanter_overlap", lambda *a_, **k: 32.0)
    monkeypatch.setattr(
        rate_transitions, "render_transition_clip",
        lambda spec, ziel: gesehen.setdefault("spec", spec))

    rate_transitions.rendere_paar(
        {"track_a": a, "track_b": b}, "001", pathlib.Path("."))

    spec = gesehen["spec"]
    assert spec.first_downbeat_a == pytest.approx(0.0123)
    assert spec.first_downbeat_b == pytest.approx(0.0456)
    assert spec.downbeat_reliable_a is True
    assert spec.downbeat_reliable_b is True
    assert spec.bar_phase_reliable_a is True
    assert spec.bar_phase_reliable_b is True
    assert spec.transition_type == rate_transitions.HOERTEST_TRANSITION_TYPE


def test_rendere_paar_meldet_unsicheres_beatgrid_als_unsicher(monkeypatch):
    """Ohne Referenz-Beatgrid darf NICHT auf Taktebene aligned werden —
    eine Taktverschiebung auf Basis einer Schaetzung waere riskanter als
    der Beat-Fehler, den sie korrigieren soll (D-03)."""
    a = _FakeTrack("A.wav", 140.0, 400.0, first_downbeat=0.5, confidence=0.62)
    b = _FakeTrack("B.wav", 140.0, 400.0, first_downbeat=0.7, confidence=0.11)
    gesehen = {}

    monkeypatch.setattr(
        rate_transitions, "calculate_paired_mix_points", lambda x, y: (300.0, 30.0))
    monkeypatch.setattr(
        rate_transitions, "geplanter_overlap", lambda *a_, **k: 32.0)
    monkeypatch.setattr(
        rate_transitions, "render_transition_clip",
        lambda spec, ziel: gesehen.setdefault("spec", spec))

    rate_transitions.rendere_paar(
        {"track_a": a, "track_b": b}, "002", pathlib.Path("."))

    spec = gesehen["spec"]
    assert spec.downbeat_reliable_a is True    # 0.62 >= DOWNBEAT_RELIABLE_MIN
    assert spec.downbeat_reliable_b is False   # 0.11 darunter
    assert spec.bar_phase_reliable_a is False  # kein Referenz-Beatgrid
    assert spec.bar_phase_reliable_b is False


class _FakePlan:
    def __init__(self, mix_out_a, mix_in_b):
        self.mix_out_a = mix_out_a
        self.mix_in_b = mix_in_b


class _FakeEmpfehlung:
    def __init__(self, overlap, plan, dj_rec=object()):
        self.overlap = overlap
        self.plan = plan
        self.dj_rec = dj_rec


def test_geplanter_overlap_nimmt_den_wert_der_empfehlung(monkeypatch):
    """Regelfall: Empfehlung passt zu den Mixpunkten -> ihr Overlap gilt."""
    monkeypatch.setattr(
        rate_transitions, "compute_transition_recommendations",
        lambda tracks, **_kw: [_FakeEmpfehlung(46.1, _FakePlan(400.0, 100.0))],
    )
    assert rate_transitions.geplanter_overlap(
        object(), object(), 400.0, 100.0
    ) == pytest.approx(46.1)


def test_geplanter_overlap_faellt_zurueck_bei_fremden_mixpunkten(monkeypatch):
    """Die Empfehlung steht auf anderen Punkten — ihr Overlap gehoert nicht
    zu diesem Clip."""
    monkeypatch.setattr(
        rate_transitions, "compute_transition_recommendations",
        lambda tracks, **_kw: [_FakeEmpfehlung(12.0, _FakePlan(380.0, 60.0))],
    )
    assert rate_transitions.geplanter_overlap(
        object(), object(), 400.0, 100.0
    ) == pytest.approx(CROSSFADE_SEK)


def test_geplanter_overlap_faellt_zurueck_ohne_dj_brain(monkeypatch):
    """Ohne DJ-Brain-Empfehlung stammt der Overlap aus dem Default-Pfad —
    auch wenn die Ersatz-Mixpunkte zufaellig passen."""
    monkeypatch.setattr(
        rate_transitions, "compute_transition_recommendations",
        lambda tracks, **_kw: [_FakeEmpfehlung(12.0, _FakePlan(400.0, 100.0), dj_rec=None)],
    )
    assert rate_transitions.geplanter_overlap(
        object(), object(), 400.0, 100.0
    ) == pytest.approx(CROSSFADE_SEK)


def test_geplanter_overlap_faellt_zurueck_ohne_empfehlung(monkeypatch):
    monkeypatch.setattr(
        rate_transitions, "compute_transition_recommendations",
        lambda tracks, **_kw: [],
    )
    assert rate_transitions.geplanter_overlap(
        object(), object(), 400.0, 100.0
    ) == pytest.approx(CROSSFADE_SEK)


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
            "harmonic": 0.8, "bpm": 0.9, "energy": 0.8, "genre": 1.0}


def test_sammle_kandidaten_bpm_grenze_ist_zwei_scoring_app_default():
    assert rate_transitions.STANDARD_BPM_TOLERANZ == 2.0
    assert rate_transitions.SCORING_BPM_TOLERANZ == 3.0


def test_sammle_kandidaten_scoring_nutzt_app_toleranz_nicht_das_gate(monkeypatch):
    """Das Gate ist 2 BPM hart, das Scoring rechnet mit dem App-Default —
    sonst prueft der Hoertest einen Vertrag, den die App nie benutzt."""
    gesehen = {}
    def fake_enhanced(x, y, tol):
        gesehen["tol"] = tol
        return _Metrik()
    monkeypatch.setattr(rate_transitions, "calculate_enhanced_compatibility", fake_enhanced)
    monkeypatch.setattr(rate_transitions, "_faktoren_vollstaendig",
                        lambda x, y, m: _faktoren_mit(0.8))
    rate_transitions.sammle_kandidaten([_GateTrack("A.wav", 140.0), _GateTrack("B.wav", 141.0)], 2.0)
    assert gesehen["tol"] == rate_transitions.SCORING_BPM_TOLERANZ


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
        monkeypatch.setattr(rate_transitions, "calculate_enhanced_compatibility",
                            lambda x, y, tol, _m=metrik: _m)
        monkeypatch.setattr(rate_transitions, "_faktoren_vollstaendig",
                            lambda x, y, m, _g=groove: _faktoren_mit(_g))
        kandidaten = rate_transitions.sammle_kandidaten([a, b], 2.0)
        assert (len(kandidaten) > 0) is erwartet, (metrik.overall_score, groove)


def test_sammle_kandidaten_schreibt_zusatzwerte(monkeypatch):
    a = _GateTrack("A.wav", 140.0, lufs=-8.0)
    b = _GateTrack("B.wav", 141.0, lufs=-11.5)
    monkeypatch.setattr(rate_transitions, "calculate_enhanced_compatibility",
                        lambda x, y, tol: _Metrik(overall=0.75))
    monkeypatch.setattr(rate_transitions, "_faktoren_vollstaendig",
                        lambda x, y, m: _faktoren_mit(0.8))
    kandidaten = rate_transitions.sammle_kandidaten([a, b], 2.0)
    zusatz = kandidaten[0]["zusatz"]
    assert zusatz["overall_score"] == pytest.approx(0.75)
    assert zusatz["lufs_delta"] == pytest.approx(3.5)
    assert set(zusatz) == set(rate_transitions.ZUSATZ_SPALTEN)


def test_sammle_kandidaten_bpm_grenze_inklusive(monkeypatch):
    monkeypatch.setattr(rate_transitions, "calculate_enhanced_compatibility",
                        lambda x, y, tol: _Metrik())
    monkeypatch.setattr(rate_transitions, "_faktoren_vollstaendig",
                        lambda x, y, m: _faktoren_mit(0.8))
    a = _GateTrack("A.wav", 140.0)
    assert rate_transitions.sammle_kandidaten([a, _GateTrack("B.wav", 142.0)]) != []
    assert rate_transitions.sammle_kandidaten([a, _GateTrack("C.wav", 142.5)]) == []
