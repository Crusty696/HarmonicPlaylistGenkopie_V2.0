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


def test_parse_kandidaten_log():
    from tools.kandidaten_messen import parse_kandidaten_log
    assert parse_kandidaten_log("Kandidaten [fast]: 8 in / 8 out in 18.40s") == ("fast", 18.4)
    assert parse_kandidaten_log("Kandidaten [voll]: 2 in / 1 out in 1.19s") == ("voll", 1.19)
    assert parse_kandidaten_log("Kandidaten [fast] fehlgeschlagen: boom") is None
    assert parse_kandidaten_log("irgendwas") is None


def test_zusammenfassung_mit_kandidaten_sekunden_und_pfaden():
    from tools.kandidaten_messen import zusammenfassung
    tracks = [{"mix_in_candidates": [], "mix_out_candidates": [], "phrases": [], "kandidaten_sekunden": 10.0, "pfad": "fast"},
              {"mix_in_candidates": [], "mix_out_candidates": [], "phrases": [], "kandidaten_sekunden": 20.0, "pfad": "fast"},
              {"mix_in_candidates": [], "mix_out_candidates": [], "phrases": []}]
    z = zusammenfassung(tracks)
    assert z["kandidaten_sekunden_median"] == 15.0 and z["pfade"] == {"fast": 2}
