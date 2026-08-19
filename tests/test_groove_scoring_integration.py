"""Tests fuer die Integration der vier neuen Faktoren ins Scoring."""
import pytest

from hpg_core.playlist import combine_weighted


def test_combine_weighted_alle_vorhanden():
    komponenten = {"a": 1.0, "b": 0.0}
    gewichte = {"a": 0.5, "b": 0.5}
    assert combine_weighted(komponenten, gewichte) == pytest.approx(0.5)


def test_combine_weighted_verteilt_fehlende_um():
    # b fehlt -> a traegt allein, Ergebnis ist a selbst, nicht a*0.5
    komponenten = {"a": 1.0, "b": None}
    gewichte = {"a": 0.5, "b": 0.5}
    assert combine_weighted(komponenten, gewichte) == pytest.approx(1.0)


def test_combine_weighted_umverteilung_bleibt_proportional():
    komponenten = {"a": 1.0, "b": 0.0, "c": None}
    gewichte = {"a": 0.2, "b": 0.6, "c": 0.2}
    # verfuegbar: a=0.2, b=0.6 -> Summe 0.8 -> (0.2*1.0 + 0.6*0.0)/0.8 = 0.25
    assert combine_weighted(komponenten, gewichte) == pytest.approx(0.25)


def test_combine_weighted_alles_fehlt_gibt_null():
    assert combine_weighted({"a": None}, {"a": 1.0}) == 0.0


from hpg_core.models import Track
from hpg_core.playlist import calculate_enhanced_compatibility


def _paar():
    a = Track(filePath="a.mp3", fileName="a.mp3")
    a.bpm, a.camelotCode, a.energy, a.detected_genre = 140.0, "8A", 60, "Psytrance"
    b = Track(filePath="b.mp3", fileName="b.mp3")
    b.bpm, b.camelotCode, b.energy, b.detected_genre = 140.0, "8A", 62, "Psytrance"
    return a, b


def _gerade():
    p = [0.0] * 16
    for s in (0, 4, 8, 12):
        p[s] = 0.25
    return p


def _offbeat():
    p = [0.0] * 16
    for s in (2, 6, 10, 14):
        p[s] = 0.25
    return p


def test_metrics_hat_vier_neue_felder():
    a, b = _paar()
    m = calculate_enhanced_compatibility(a, b, bpm_tolerance=6.0)
    for feld in ("groove_match", "bass_continuity", "timbre_match", "mood_match"):
        assert hasattr(m, feld)


def test_schalter_aus_ist_identisch_zum_altstand(monkeypatch):
    """Bei ausgeschaltetem Schalter darf sich der Score nicht bewegen."""
    import hpg_core.playlist as pl

    a, b = _paar()
    monkeypatch.setattr(pl, "TRANSITION_FEATURES_ENABLED", False)
    ohne = calculate_enhanced_compatibility(a, b, bpm_tolerance=6.0).overall_score

    # Altwert: Harmonik 100, BPM-Diff 0, Energy-Diff 2, Genre gleich
    erwartet = (0.8 * 0.44) * 1.0 + (0.8 * 0.28) * 1.0 + (0.8 * 0.28) * 0.98 + 0.2 * 1.0
    assert ohne == pytest.approx(min(1.0, erwartet), abs=1e-6)


def test_schalter_an_beruecksichtigt_groove(monkeypatch):
    import hpg_core.playlist as pl

    monkeypatch.setattr(pl, "TRANSITION_FEATURES_ENABLED", True)
    a, b = _paar()
    a.groove_pattern, a.bass_pattern = _gerade(), _gerade()
    b.groove_pattern, b.bass_pattern = _gerade(), _gerade()
    passend = calculate_enhanced_compatibility(a, b, bpm_tolerance=6.0).overall_score

    b.groove_pattern, b.bass_pattern = _offbeat(), _offbeat()
    beissend = calculate_enhanced_compatibility(a, b, bpm_tolerance=6.0).overall_score

    assert passend > beissend


def test_fehlende_groove_daten_werden_nicht_bestraft(monkeypatch):
    """Ein Track ohne Muster darf nicht schlechter dastehen als einer mit
    perfekt passendem Muster minus Rundung — das Gewicht wird umverteilt."""
    import hpg_core.playlist as pl

    monkeypatch.setattr(pl, "TRANSITION_FEATURES_ENABLED", True)
    a, b = _paar()
    a.groove_pattern = a.bass_pattern = []
    b.groove_pattern = b.bass_pattern = []
    ohne_daten = calculate_enhanced_compatibility(a, b, bpm_tolerance=6.0).overall_score

    a.groove_pattern, a.bass_pattern = _gerade(), _gerade()
    b.groove_pattern, b.bass_pattern = _offbeat(), _offbeat()
    mit_konflikt = calculate_enhanced_compatibility(a, b, bpm_tolerance=6.0).overall_score

    assert ohne_daten > mit_konflikt


def test_bpm_hard_gate_bleibt_wirksam(monkeypatch):
    import hpg_core.playlist as pl

    monkeypatch.setattr(pl, "TRANSITION_FEATURES_ENABLED", True)
    a, b = _paar()
    b.bpm = 175.0
    assert calculate_enhanced_compatibility(a, b, bpm_tolerance=6.0).overall_score == 0.0
