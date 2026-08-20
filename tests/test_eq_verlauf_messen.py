"""Tests fuer das EQ-Verlauf-Messwerkzeug (reine Logik, keine Audiodateien).

Getestet werden nur die reinen Funktionen. Das Einlesen echter DJ-Mixe laeuft
NICHT im Test — das waere langsam und braeuchte Material, das nicht im Repo
liegt.

Die Zahlen dieses Werkzeugs entscheiden, ob der Renderer einen Bandgain
ueber der Blendkurve faehrt. Ein Rechenfehler hier landete still im Audio —
tatsaechlich hat die Messung 2026-08-20 einen solchen Eingriff verhindert,
weil sie zeigte, dass die Mulde nicht signifikant ist. Deshalb sind die
Kanten hier festgenagelt.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pytest

from tools.eq_verlauf_messen import (
    BAENDER,
    MITTEN_INDEX,
    band_am_punkt,
    blendenbreite,
    muldentiefe,
    muldentiefe_mit_bereich,
)


def _fenster(mitte_wert: float, umfeld_wert: float = 1.0, laenge: int = 121,
             baender: int = 3) -> dict:
    """Ein Fenster mit flachem Umfeld und einem Wert in der Mitte."""
    mitte = laenge // 2
    b = np.full((baender, laenge), umfeld_wert, dtype=float)
    b[:, mitte - 3:mitte + 4] = mitte_wert
    return {"b": b.tolist(), "o": [1.0] * laenge}


# ---------------------------------------------------------------------------
# Bandgrenzen
# ---------------------------------------------------------------------------

def test_baender_decken_die_renderer_crossover():
    """Gemessen werden muss dasselbe Band, das der Renderer anfasst.

    Der pro_eq_swap trennt bei 120 Hz und 2500 Hz. Eine fruehere Fassung mass
    die Mitten als 250-2500 Hz und haette die Oktave 120-250 Hz ungemessen
    mit abgesenkt.
    """
    namen = [n for _lo, _hi, n in BAENDER]
    assert namen[MITTEN_INDEX] == "mitten"
    lo, hi, _ = BAENDER[MITTEN_INDEX]
    assert (lo, hi) == (120, 2500)


def test_baender_ueberlappen_nicht_und_lassen_keine_luecke():
    grenzen = [(lo, hi) for lo, hi, _ in BAENDER]
    for (_lo1, hi1), (lo2, _hi2) in zip(grenzen, grenzen[1:]):
        assert hi1 == lo2


# ---------------------------------------------------------------------------
# band_am_punkt
# ---------------------------------------------------------------------------

def test_band_am_punkt_ist_eins_bei_flachem_verlauf():
    werte = band_am_punkt([_fenster(1.0)], MITTEN_INDEX)
    assert werte[0] == pytest.approx(1.0)


def test_band_am_punkt_misst_gegen_das_eigene_umfeld():
    """Ein generell lauter Uebergang darf nicht als Absenkung erscheinen —
    der Bezug ist das Umfeld desselben Uebergangs, nicht der Mix-Median."""
    leise = band_am_punkt([_fenster(0.5, umfeld_wert=1.0)], MITTEN_INDEX)[0]
    laut = band_am_punkt([_fenster(5.0, umfeld_wert=10.0)], MITTEN_INDEX)[0]
    assert leise == pytest.approx(0.5)
    assert laut == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# blendenbreite
# ---------------------------------------------------------------------------

def test_blendenbreite_null_ohne_erhoehung():
    assert blendenbreite({"b": [], "o": [1.0] * 121}) == 0.0


def test_blendenbreite_misst_den_zusammenhaengenden_block():
    o = [1.0] * 121
    for i in range(55, 66):          # 11 s erhoeht, ueber die Mitte
        o[i] = 2.0
    assert blendenbreite({"b": [], "o": o}) == pytest.approx(11.0)


def test_blendenbreite_ignoriert_erhoehung_abseits_der_mitte():
    """Eine Erhoehung, die die Mitte nicht beruehrt, gehoert nicht zur Blende."""
    o = [1.0] * 121
    for i in range(10, 25):
        o[i] = 2.0
    assert blendenbreite({"b": [], "o": o}) == 0.0


# ---------------------------------------------------------------------------
# muldentiefe
# ---------------------------------------------------------------------------

def test_muldentiefe_null_bei_flacher_kurve():
    fenster = [_fenster(1.0) for _ in range(10)]
    assert muldentiefe(fenster, 20.0) == pytest.approx(0.0, abs=1e-9)


def test_muldentiefe_positiv_wenn_die_mitte_tiefer_liegt():
    """Die Mitte liegt bei 0.8, der Rand bei 1.0 — Faktor 0.2."""
    fenster = [_fenster(0.8, umfeld_wert=1.0) for _ in range(10)]
    assert muldentiefe(fenster, 20.0) == pytest.approx(0.2, abs=1e-9)


def test_muldentiefe_misst_gegen_den_blendenrand_nicht_gegen_das_umfeld():
    """Ein Bandgain waere an den Crossfade-Raendern verankert. Liegt der Rand
    selbst schon tief, ist die Differenz kleiner als die absolute Absenkung —
    genau diese Differenz waere die gesuchte Groesse."""
    laenge, mitte = 121, 60
    b = np.ones((3, laenge))
    b[:, mitte - 10:mitte + 11] = 0.9      # breite Senke, Rand der Blende drin
    b[:, mitte - 3:mitte + 4] = 0.8        # Mitte tiefer
    fenster = [{"b": b.tolist(), "o": [1.0] * laenge} for _ in range(10)]
    # Blende 20 s -> Rand bei Radius 10, also innerhalb der breiten Senke
    tiefe = muldentiefe(fenster, 20.0)
    assert tiefe == pytest.approx(1.0 - 0.8 / 0.9, abs=1e-9)
    assert tiefe < 0.2


def test_muldentiefe_klemmt_den_radius_ins_fenster():
    """Eine Blende laenger als das Messfenster darf nicht ueber den Rand
    hinausgreifen."""
    fenster = [_fenster(0.8) for _ in range(5)]
    assert muldentiefe(fenster, 10_000.0) == pytest.approx(0.2, abs=1e-9)


# ---------------------------------------------------------------------------
# muldentiefe_mit_bereich
# ---------------------------------------------------------------------------

def test_bereich_enthaelt_die_null_wenn_es_keinen_effekt_gibt():
    """Der Entscheidungsfall: traegt eine Gruppe eine Mulde oder nicht?"""
    rng = np.random.default_rng(1)
    fenster = []
    for _ in range(60):
        laenge, mitte = 121, 60
        b = np.ones((3, laenge)) * (1.0 + rng.normal(0, 0.05))
        b[:, mitte - 3:mitte + 4] *= (1.0 + rng.normal(0, 0.05))
        fenster.append({"b": b.tolist(), "o": [1.0] * laenge})
    _punkt, unten, oben = muldentiefe_mit_bereich(fenster, 20.0, ziehungen=200)
    assert unten <= 0.0 <= oben


def test_bereich_schliesst_die_null_aus_bei_klarem_effekt():
    fenster = [_fenster(0.8) for _ in range(60)]
    punkt, unten, oben = muldentiefe_mit_bereich(fenster, 20.0, ziehungen=200)
    assert punkt == pytest.approx(0.2, abs=1e-9)
    assert unten > 0.0
    assert oben >= punkt


def test_bereich_ist_reproduzierbar_bei_gleichem_seed():
    fenster = [_fenster(0.85) for _ in range(30)]
    a = muldentiefe_mit_bereich(fenster, 20.0, ziehungen=100, seed=5)
    b = muldentiefe_mit_bereich(fenster, 20.0, ziehungen=100, seed=5)
    assert a == b
