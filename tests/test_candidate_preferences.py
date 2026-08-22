"""Tests fuer den Lader der Kandidaten-Praeferenzen (Hoertest Teil 3)."""
import json

import pytest

from hpg_core import candidate_preferences as cp


@pytest.fixture(autouse=True)
def _frisch(monkeypatch, tmp_path):
    monkeypatch.setenv("HPG_CANDIDATE_PREFERENCES_FILE", str(tmp_path / "prefs.json"))
    cp.reset_cache()
    yield
    cp.reset_cache()


def test_ohne_datei_leer():
    assert cp.load_candidate_preferences() == {}
    assert cp.kandidaten_gewichte("Psytrance") is None
    assert cp.schema_rangfolge("Psytrance") == []


def test_override_wird_gelesen_und_validiert(tmp_path):
    gewichte = {f"kandidaten_{f}_weight": 0.1 for f in (
        "harmonic", "bpm", "energy", "genre", "groove", "bass", "timbre", "mood", "loudness", "structure")}
    (tmp_path / "prefs.json").write_text(json.dumps({
        "_diagnose": {"quelle": "test"},
        "Psytrance": {**gewichte, "schema_rang": ["pssi_phrase", "auto_cue"]},
        "Unbekanntes Genre": {"kandidaten_bpm_weight": 1.0},
    }), encoding="utf-8")
    cp.reset_cache()
    assert cp.kandidaten_gewichte("Psytrance") == pytest.approx(gewichte)
    assert cp.schema_rangfolge("Psytrance") == ["pssi_phrase", "auto_cue"]
    assert cp.kandidaten_gewichte("Unbekanntes Genre") is None   # nicht kanonisch -> ignoriert
    assert cp.kandidaten_gewichte("Techno") is None


def test_gewichte_mit_falscher_summe_werden_verworfen(tmp_path, caplog):
    (tmp_path / "prefs.json").write_text(json.dumps({
        "Psytrance": {"kandidaten_bpm_weight": 0.5, "kandidaten_groove_weight": 0.2}}), encoding="utf-8")
    cp.reset_cache()
    assert cp.kandidaten_gewichte("Psytrance") is None
