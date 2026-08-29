"""Regression: Rundungsrauschen darf keinen Mixpunkt um eine Phrase verschieben."""
from hpg_core.models import QUANTIZE_TOLERANCE_SEC, quantize_to_grid

# Psytrance bei 140 BPM, phrase_unit 16 — das Raster aus dem realen Fall.
GRID = 27.428571428571427
ANKER = 0.001


def test_ceil_springt_nicht_wegen_millisekunden_eine_phrase_weiter():
    """Realfall aus dem Hoertest (Paar 001, 2026-08-20).

    Das Intro-Ende kommt als 82.29 s gerundet aus der Analyse; drei Phrasen
    sind exakt 82.2867 s. Die 3.3 ms Ueberschuss liessen `ceil` auf die
    VIERTE Phrase springen — der Mix-In landete 27 s spaeter mitten im Drop
    statt am Intro-Ende. Hoerbar als "an der falschen Stelle gemixt".
    """
    gerundet = quantize_to_grid(82.29, GRID, ANKER, "ceil")
    exakt = quantize_to_grid(82.2867, GRID, ANKER, "ceil")
    assert gerundet == exakt
    assert gerundet < 100.0


def test_floor_faellt_nicht_wegen_millisekunden_eine_phrase_zurueck():
    """Dieselbe Falle in die Gegenrichtung — betrifft den Mix-Out."""
    knapp_davor = quantize_to_grid(82.2840, GRID, ANKER, "floor")
    exakt = quantize_to_grid(82.2867, GRID, ANKER, "floor")
    assert knapp_davor == exakt


def test_echte_grenze_wird_weiterhin_respektiert():
    """Die Toleranz darf keine echte Phrasengrenze verschlucken."""
    # eine halbe Phrase dahinter ist eindeutig die naechste Grenze
    assert quantize_to_grid(0.5 * GRID, GRID, 0.0, "ceil") == GRID
    # und knapp ausserhalb der Toleranz ebenfalls
    assert quantize_to_grid(2 * QUANTIZE_TOLERANCE_SEC, GRID, 0.0, "ceil") == GRID


def test_toleranz_bleibt_unter_der_hoerbaren_flam_grenze():
    """1/8 Beat sind 54 ms bei 138 BPM (siehe downbeat.py).

    Darueber nimmt ein Hoerer zwei Kicks nicht mehr als einen mit Flam wahr,
    sondern als zwei. Die Toleranz muss darunter bleiben, sonst koennte sie
    einen echten Versatz kaschieren statt Rundungsrauschen aufzufangen.
    """
    assert QUANTIZE_TOLERANCE_SEC < 0.054


def test_round_modus_bleibt_unveraendert():
    """Nur ceil und floor bekommen Spielraum — round hatte das Problem nie."""
    assert quantize_to_grid(1.4 * GRID, GRID, 0.0, "round") == GRID
    assert quantize_to_grid(1.6 * GRID, GRID, 0.0, "round") == 2 * GRID
