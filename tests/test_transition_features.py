"""Tests fuer die paarweisen Uebergangs-Vergleiche."""
import pytest

from hpg_core.models import Track
from hpg_core.transition_features import (
    bass_continuity,
    cosine_similarity,
    groove_match,
    mood_match,
    timbre_match,
)


@pytest.fixture(autouse=True)
def feste_toleranzen(monkeypatch):
    """Entkoppelt diese Tests von den ausgelieferten Kalibrierdaten.

    `mood_match` und `bass_continuity` lesen ihre Schwellen ueber
    `get_tolerances` aus `hpg_core/data/transition_tolerances.json`. Diese
    Datei wird aus echten DJ-Mixen neu gelernt — als die gemessenen Werte
    einzogen, fiel `brightness_delta_max` von 60 auf 11,3 und ein Test
    kippte, obwohl die geprueften Funktionen sich nicht geaendert hatten.

    Diese Datei prueft das VERHALTEN der Vergleichsfunktionen, nicht den
    Stand der Kalibrierung. Deshalb hier fest die Defaults aus genres.py.
    Wer die gelernten Werte pruefen will, tut das in test_tolerances.py.
    """
    import hpg_core.transition_features as tf
    from hpg_core.genres import GENRE_TRANSITION_TOLERANCES

    monkeypatch.setattr(
        tf, "get_tolerances", lambda genre: GENRE_TRANSITION_TOLERANCES.get(
            genre, GENRE_TRANSITION_TOLERANCES["Psytrance"]
        )
    )


def _track(**kwargs) -> Track:
    t = Track(filePath=kwargs.pop("path", "a.mp3"), fileName="a.mp3")
    for k, v in kwargs.items():
        setattr(t, k, v)
    return t


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


def test_cosine_similarity_identisch_ist_eins():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_ist_null():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_leer_ist_none():
    assert cosine_similarity([], [1.0]) is None


def test_groove_match_gleiches_muster_ist_hoch():
    a = _track(groove_pattern=_gerade(), bass_pattern=_gerade())
    b = _track(groove_pattern=_gerade(), bass_pattern=_gerade())
    assert groove_match(a, b, "Psytrance") > 0.95


def test_groove_match_offbeat_gegen_gerade_ist_niedrig():
    a = _track(groove_pattern=_gerade(), bass_pattern=_gerade())
    b = _track(groove_pattern=_offbeat(), bass_pattern=_offbeat())
    assert groove_match(a, b, "Psytrance") < 0.2


def test_groove_match_ohne_muster_ist_none():
    a = _track(groove_pattern=[], bass_pattern=[])
    b = _track(groove_pattern=_gerade(), bass_pattern=_gerade())
    assert groove_match(a, b, "Psytrance") is None


def test_bass_continuity_gleicher_druck_ist_hoch():
    a = _track(sub_energy=0.30, bass_punch=3.0)
    b = _track(sub_energy=0.30, bass_punch=3.0)
    assert bass_continuity(a, b, "Psytrance") > 0.95


def test_bass_continuity_grosser_sprung_ist_niedrig():
    a = _track(sub_energy=0.05, bass_punch=1.2)
    b = _track(sub_energy=0.50, bass_punch=6.0)
    assert bass_continuity(a, b, "Psytrance") < 0.5


def test_bass_continuity_ohne_werte_ist_none():
    a = _track(sub_energy=0.0, bass_punch=0.0)
    b = _track(sub_energy=0.0, bass_punch=0.0)
    assert bass_continuity(a, b, "Psytrance") is None


def test_timbre_match_ohne_fingerprint_ist_none():
    a = _track(timbre_fingerprint=[])
    b = _track(timbre_fingerprint=[1.0, 2.0])
    assert timbre_match(a, b, "Psytrance") is None


def test_timbre_match_identisch_ist_hoch():
    fp = [1.0, 2.0, 3.0, 4.0]
    assert timbre_match(_track(timbre_fingerprint=fp),
                        _track(timbre_fingerprint=fp), "Psytrance") > 0.95


def test_mood_match_gleiche_stimmung_ist_hoch(feste_toleranzen):
    a = _track(brightness=50, spectral_flatness=0.05, keyMode="Minor")
    b = _track(brightness=52, spectral_flatness=0.05, keyMode="Minor")
    assert mood_match(a, b, "Psytrance") > 0.9


def test_mood_match_heller_sprung_ist_niedriger():
    a = _track(brightness=10, spectral_flatness=0.02, keyMode="Minor")
    b = _track(brightness=95, spectral_flatness=0.02, keyMode="Major")
    assert mood_match(a, b, "Psytrance") < 0.5


def test_mood_match_ohne_brightness_ist_none():
    a = _track(brightness=0, spectral_flatness=0.0)
    b = _track(brightness=0, spectral_flatness=0.0)
    assert mood_match(a, b, "Psytrance") is None


def test_ein_track_ohne_groove_daten_macht_alle_faktoren_unbestimmbar():
    """Regression: frueher pruefte die None-Bedingung mit UND statt ODER.

    compute_groove_fields liefert bei zu niedriger downbeat_confidence ein
    leeres GrooveFeatures() — sub_energy und bass_punch sind dann 0.0, und
    analysis.py setzt brightness bei gescheiterter Feature-Phase auf 0. Ein
    solcher Track gegen einen normal analysierten ergab 0.0 bzw. 0.2, also
    die haerteste Strafe fuer genau die Tracks, die die Umverteilung
    schuetzen soll.
    """
    voll = _track(groove_pattern=_gerade(), bass_pattern=_gerade(),
                  sub_energy=0.5, bass_punch=2.0, brightness=55,
                  spectral_flatness=0.05, timbre_fingerprint=[1.0, 2.0, 3.0])
    leer = _track(groove_pattern=[], bass_pattern=[],
                  sub_energy=0.0, bass_punch=0.0, brightness=0,
                  spectral_flatness=0.0, timbre_fingerprint=[])

    assert groove_match(voll, leer, "Psytrance") is None
    assert bass_continuity(voll, leer, "Psytrance") is None
    assert mood_match(voll, leer, "Psytrance") is None
    assert timbre_match(voll, leer, "Psytrance") is None
    # und in der Gegenrichtung
    assert bass_continuity(leer, voll, "Psytrance") is None
    assert mood_match(leer, voll, "Psytrance") is None
