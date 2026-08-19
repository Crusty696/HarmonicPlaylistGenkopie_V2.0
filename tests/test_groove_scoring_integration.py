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


# ── HPG-001-Vertrag: alle Konsumenten sehen dieselben acht Faktoren ────────

def test_adjacent_metrics_tragen_die_vier_neuen_faktoren(monkeypatch):
    """compute_adjacent_transition_metrics ist die Quelle fuer Anzeige,
    Quality und Empfehlungen — es muss dieselben Felder liefern wie die
    Sortierung."""
    import hpg_core.playlist as pl

    monkeypatch.setattr(pl, "TRANSITION_FEATURES_ENABLED", True)
    a, b = _paar()
    for t in (a, b):
        t.groove_pattern = t.bass_pattern = _gerade()
        t.timbre_fingerprint = [1.0, 2.0, 3.0]
        t.brightness = 50

    metriken = pl.compute_adjacent_transition_metrics([a, b], bpm_tolerance=6.0)

    assert len(metriken) == 1
    m = metriken[0]
    assert m.groove_match is not None
    assert m.timbre_match is not None
    assert m.mood_match is not None


def test_quality_und_sortierziel_stimmen_ueberein(monkeypatch):
    """HPG-001: die angezeigte Qualitaet darf nicht gegen ein anderes Ziel
    optimieren als die Sortierung. Beide muessen durch dieselbe
    Zielfunktion laufen."""
    import hpg_core.playlist as pl

    monkeypatch.setattr(pl, "TRANSITION_FEATURES_ENABLED", True)
    a, b = _paar()
    for t in (a, b):
        t.groove_pattern = t.bass_pattern = _gerade()
        t.timbre_fingerprint = [1.0, 2.0, 3.0]
        t.brightness = 50

    paar_score = pl.calculate_enhanced_compatibility(
        a, b, bpm_tolerance=6.0
    ).overall_score
    quality = pl.calculate_playlist_quality([a, b], bpm_tolerance=6.0)

    # calculate_playlist_quality mittelt bewusst die GERUNDETEN 0-100-Werte,
    # damit die Gesamtzahl in der UI nicht um einen Punkt neben der einzelnen
    # Empfehlung liegt. Der Vertrag ist also "gleiche Zielfunktion nach
    # Anzeige-Rundung", nicht "gleicher Float".
    assert quality["overall_score"] == pytest.approx(
        round(paar_score * 100) / 100.0, abs=1e-6
    )


def test_schalter_bewegt_auch_die_angezeigte_qualitaet(monkeypatch):
    """Waere die Anzeige vom Schalter unabhaengig, liefe die Sortierung
    gegen acht Faktoren, waehrend der Nutzer eine Zahl aus vieren sieht."""
    import hpg_core.playlist as pl

    a, b = _paar()
    a.groove_pattern, a.bass_pattern = _gerade(), _gerade()
    b.groove_pattern, b.bass_pattern = _offbeat(), _offbeat()

    monkeypatch.setattr(pl, "TRANSITION_FEATURES_ENABLED", False)
    aus = pl.calculate_playlist_quality([a, b], bpm_tolerance=6.0)["overall_score"]
    monkeypatch.setattr(pl, "TRANSITION_FEATURES_ENABLED", True)
    an = pl.calculate_playlist_quality([a, b], bpm_tolerance=6.0)["overall_score"]

    assert an != pytest.approx(aus, abs=1e-6)
