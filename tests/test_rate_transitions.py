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

import numpy as np
import pytest

from tools.rate_transitions import (
    ALLE_FAKTOREN,
    BUDGET_MAX,
    CROSSFADE_SEK,
    POST_ROLL_SEK,
    PRE_ROLL_SEK,
    crossfade_reserve,
    L2_STAERKE,
    MIN_EREIGNISSE_JE_MERKMAL,
    NEUE_FAKTOREN,
    baue_genre_gewichte,
    bootstrap_intervalle,
    datenlage_urteil,
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
    rest_a, rest_b = crossfade_reserve(mix_out_a=400.0, dauer_b=420.0, mix_in_b=100.0)
    assert rest_a == pytest.approx(400.0 - PRE_ROLL_SEK)
    assert rest_b == pytest.approx(420.0 - 100.0 - POST_ROLL_SEK)
    assert min(rest_a, rest_b) >= CROSSFADE_SEK


def test_crossfade_reserve_erkennt_zu_spaeten_mix_in():
    """Mix-In dicht am Ende von Track B — die Blende passt nicht mehr."""
    _rest_a, rest_b = crossfade_reserve(mix_out_a=400.0, dauer_b=420.0, mix_in_b=418.0)
    assert rest_b < CROSSFADE_SEK


def test_streuung_leer():
    werte = streuung([])
    assert werte == {"min": None, "median": None, "max": None}
