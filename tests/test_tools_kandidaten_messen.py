"""Tests fuer tools/kandidaten_messen.py (nur Auswertung, kein Audio)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


def test_zusammenfassung_zaehlt_schemata_und_leere_seiten():
    from tools.kandidaten_messen import zusammenfassung
    tracks = [
        {"fileName": "a", "duration": 300.0, "mix_in_candidates": [{"t": 30.0, "schema": ["analyzer", "sektion"]}],
         "mix_out_candidates": [], "phrases": [], "analyse_sekunden": 12.5},
        {"fileName": "b", "duration": 300.0, "mix_in_candidates": [{"t": 30.0, "schema": ["pssi_phrase"]}],
         "mix_out_candidates": [{"t": 250.0, "schema": ["auto_cue"]}], "phrases": [{"label": "Intro"}], "analyse_sekunden": 20.0},
    ]
    z = zusammenfassung(tracks)
    assert z["tracks"] == 2 and z["ohne_out"] == 1 and z["mit_pssi"] == 1
    assert z["schemata_in"]["analyzer"] == 1 and z["schemata_out"]["auto_cue"] == 1
    assert z["kandidaten_in_median"] == 1 and z["analyse_sekunden_median"] == pytest.approx(16.25)


def test_cache_modus_ohne_datei_meldet_fehler_und_legt_nichts_an(tmp_path, monkeypatch, capsys):
    from hpg_core import caching
    from tools import kandidaten_messen
    pfad = tmp_path / "nix.db"
    monkeypatch.setattr(caching, "CACHE_FILE", str(pfad))
    monkeypatch.setattr(sys, "argv", ["x", "--cache"])
    assert kandidaten_messen.main() == 1
    assert str(pfad) in capsys.readouterr().err
    assert not pfad.exists()
