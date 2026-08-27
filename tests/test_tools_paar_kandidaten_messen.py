"""Tests fuer tools/paar_kandidaten_messen.py (reine Zusammenfassung)."""
import importlib.util
import os

import pytest

_PFAD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "paar_kandidaten_messen.py")
spec = importlib.util.spec_from_file_location("paar_kandidaten_messen", _PFAD)
pkm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pkm)


def test_zusammenfassung_zaehlt_paare_gates_und_raenge():
    ergebnisse = [
        {"paar": ("a", "b"), "anzahl": 4, "gate_gruende": {}, "rang1_schema_out": "pssi_phrase",
         "rang1_schema_in": "auto_cue", "rang1_score": 0.8, "blenden": [16, 32]},
        {"paar": ("a", "c"), "anzahl": 0, "gate_gruende": {"bpm": 3, "gitter_out": 1},
         "rang1_schema_out": "", "rang1_schema_in": "", "rang1_score": None, "blenden": []},
    ]
    z = pkm.zusammenfassung(ergebnisse)
    assert z["paare"] == 2 and z["paare_mit_kandidaten"] == 1
    assert z["gate_gruende"] == {"bpm": 3, "gitter_out": 1}
    assert z["rang1_schemata_out"] == {"pssi_phrase": 1}
    assert z["kandidaten_median"] == 4
    assert z["rang1_score_median"] == pytest.approx(0.8)


def test_lade_tracks_json_liest_kandidaten_messen_ausgabe(tmp_path):
    import json
    from hpg_core.caching import track_to_dict
    from hpg_core.mix_candidates import MixCandidate
    from hpg_core.models import Track
    t = Track(filePath="x.mp3", fileName="x.mp3")
    t.bpm = 140.0
    t.mix_in_candidates = [
        MixCandidate(
            t=30.0, schema=["sektion"], provenance="test_fixture"
        ).to_dict()
    ]
    pfad = tmp_path / "k.json"
    pfad.write_text(json.dumps({"zusammenfassung": {}, "tracks": [track_to_dict(t)]}), encoding="utf-8")
    tracks = pkm._lade_tracks_json(str(pfad))
    assert len(tracks) == 1 and tracks[0].bpm == 140.0
    assert tracks[0].mix_in_candidates[0]["t"] == 30.0
