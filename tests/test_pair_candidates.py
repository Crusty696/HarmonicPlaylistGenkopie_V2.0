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
