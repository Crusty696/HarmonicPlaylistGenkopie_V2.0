"""Tests fuer das Laden der Uebergangs-Toleranzen."""
import json

import pytest

from hpg_core.genres import CANONICAL_GENRES, GENRE_TRANSITION_TOLERANCES
from hpg_core.tolerances import get_tolerances, load_tolerances


def test_alle_kanonischen_genres_haben_toleranzen():
    assert set(GENRE_TRANSITION_TOLERANCES) == set(CANONICAL_GENRES)


def test_gewichte_summieren_auf_eins():
    for genre, werte in GENRE_TRANSITION_TOLERANCES.items():
        summe = sum(
            werte[k] for k in (
                "harmonic_weight", "bpm_weight", "energy_weight", "genre_weight",
                "groove_weight", "bass_weight", "timbre_weight", "mood_weight",
            )
        )
        assert summe == pytest.approx(1.0, abs=1e-6), f"{genre}: {summe}"


def test_get_tolerances_unbekanntes_genre_faellt_auf_default():
    werte = get_tolerances("Gibt Es Nicht")
    assert "groove_weight" in werte


def test_override_datei_schlaegt_default(tmp_path, monkeypatch):
    datei = tmp_path / "transition_tolerances.json"
    datei.write_text(
        json.dumps({"Psytrance": {"groove_weight": 0.42}}), encoding="utf-8"
    )
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))

    werte = load_tolerances()

    assert werte["Psytrance"]["groove_weight"] == 0.42
    # nicht ueberschriebene Schluessel bleiben erhalten
    assert "harmonic_weight" in werte["Psytrance"]


def test_kaputtes_json_faellt_auf_defaults_ohne_ausnahme(tmp_path, monkeypatch):
    datei = tmp_path / "transition_tolerances.json"
    datei.write_text("{ das ist kein json", encoding="utf-8")
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))

    werte = load_tolerances()

    assert set(werte) == set(CANONICAL_GENRES)


def test_write_override_haelt_summe_bei_eins(tmp_path, monkeypatch):
    from hpg_core.tolerances import reset_cache, write_override

    datei = tmp_path / "transition_tolerances.json"
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))
    write_override({"groove_weight": 0.20, "bass_weight": 0.10,
                    "timbre_weight": 0.05, "mood_weight": 0.05})
    reset_cache()

    werte = load_tolerances()
    summe = sum(werte["Psytrance"][k] for k in (
        "harmonic_weight", "bpm_weight", "energy_weight", "genre_weight",
        "groove_weight", "bass_weight", "timbre_weight", "mood_weight"))
    assert summe == pytest.approx(1.0, abs=1e-6)


def test_write_override_kandidaten_haelt_summe_eins(tmp_path, monkeypatch):
    from hpg_core.tolerances import (
        KANDIDATEN_GEWICHT_SCHLUESSEL, reset_cache, write_override, write_override_kandidaten,
    )
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(tmp_path / "tol.json"))
    reset_cache()
    write_override_kandidaten({"kandidaten_loudness_weight": 0.20})
    reset_cache()
    w = get_tolerances("Psytrance")
    assert w["kandidaten_loudness_weight"] == pytest.approx(0.20)
    assert sum(w[k] for k in KANDIDATEN_GEWICHT_SCHLUESSEL) == pytest.approx(1.0)
    assert w["groove_weight"] == pytest.approx(0.300)          # Track-Gewichte unberuehrt
    with pytest.raises(ValueError):
        write_override_kandidaten({"kandidaten_loudness_weight": 1.2})
    with pytest.raises(ValueError):
        write_override_kandidaten({"groove_weight": 0.3})
    # Track-Regler danach: Kandidaten-Gewichte ueberleben write_override
    write_override({"groove_weight": 0.4, "bass_weight": 0.1, "timbre_weight": 0.05, "mood_weight": 0.05})
    reset_cache()
    w2 = get_tolerances("Psytrance")
    assert w2["kandidaten_loudness_weight"] == pytest.approx(0.20)
    assert w2["groove_weight"] == pytest.approx(0.4)
    reset_cache()
