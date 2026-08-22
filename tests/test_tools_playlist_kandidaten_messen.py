"""Tests fuer tools/playlist_kandidaten_messen.py (reine Zusammenfassung)."""
import importlib.util
import os
from types import SimpleNamespace

import pytest

_PFAD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools",
                     "playlist_kandidaten_messen.py")
spec = importlib.util.spec_from_file_location("playlist_kandidaten_messen", _PFAD)
pkm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pkm)


def _track(name, duration=300.0, intro_end=60.0, outro_start=240.0):
    return SimpleNamespace(filePath=name, duration=duration, sections=[
        {"label": "intro", "start_time": 0.0, "end_time": intro_end},
        {"label": "main", "start_time": intro_end, "end_time": outro_start},
        {"label": "outro", "start_time": outro_start, "end_time": duration},
    ])


def _rec(a, b, t_out, t_in, overlap, kand_overlap=None, aktiv=1, typ="pro_eq_swap", score=70, schema_out="pssi_phrase",
         konsistent=True):
    k = {"t_out": t_out, "t_in": t_in, "overlap_sec": kand_overlap if kand_overlap is not None else overlap,
         "out_a": {"schema": [schema_out]}, "in_b": {"schema": ["auto_cue"]}}
    # Rang-1-Attrappe davor, damit kandidat_aktiv=2 den aktiven Kandidaten adressiert
    kand = ([{"t_out": 1.0, "t_in": 1.0, "overlap_sec": 1.0, "out_a": {"schema": ["sektion"]},
              "in_b": {"schema": ["auto_cue"]}}] if aktiv == 2 else []) + ([k] if aktiv else [])
    return SimpleNamespace(from_track=a, to_track=b, kandidaten=kand, kandidat_aktiv=aktiv,
                           kandidat_konsistent=konsistent, transition_type=typ, compatibility_score=score,
                           plan=SimpleNamespace(mix_out_a=t_out, mix_in_b=t_in, overlap=overlap))


def test_zusammenfassung_zaehlt_kandidaten_schemata_und_verletzungen():
    a, b, c = _track("a"), _track("b"), _track("c")
    recs = [
        _rec(a, b, 192.0, 82.3, 27.4, typ="bass_swap"),                     # sauber
        _rec(b, c, 230.0, 50.0, 27.4, kand_overlap=54.9, schema_out="sektion"),  # Blende ins Outro + in_im_intro + overlap_abweichung
    ]
    z = pkm.zusammenfassung(recs, [a, b, c], {"generierung_s": 1.0, "empfehlungen_s": 0.5})
    assert z["tracks"] == 3 and z["paare"] == 2 and z["paare_mit_kandidat"] == 2
    assert z["rang1_schemata_out"] == {"pssi_phrase": 1, "sektion": 1}
    assert z["bass_swap_anteil"] == pytest.approx(0.5)
    assert z["intro_outro_verletzungen"] == 2 and z["overlap_abweichungen"] == 1
    assert z["cue_gate_verletzungen"] == 0                      # 82.3 (in von b) < 230.0 (out von b)
    assert z["score_median"] == 70 and z["dauer"]["generierung_s"] == 1.0


def test_zusammenfassung_cue_gate_und_ohne_kandidat():
    a, b, c = _track("a"), _track("b"), _track("c")
    recs = [_rec(a, b, 192.0, 250.0, 27.4), _rec(b, c, 200.0, 82.3, 27.4)]   # in von b (250) > out von b (200)
    z = pkm.zusammenfassung(recs, [a, b, c], {})
    assert z["cue_gate_verletzungen"] == 1
    z0 = pkm.zusammenfassung([_rec(a, b, 1.0, 2.0, 3.0, aktiv=0)], [a, b], {})
    assert z0["paare_mit_kandidat"] == 0 and z0["bass_swap_anteil"] is None


def test_zusammenfassung_nutzt_aktiven_kandidaten_und_zaehlt_neustarts():
    a, b = _track("a"), _track("b")
    recs = [_rec(a, b, 192.0, 82.3, 27.4, aktiv=2, schema_out="pssi_phrase", konsistent=False)]
    z = pkm.zusammenfassung(recs, [a, b], {})
    assert z["rang1_schemata_out"] == {"pssi_phrase": 1}      # aktiver (Rang 2), nicht die Attrappe
    assert z["overlap_abweichungen"] == 0 and z["kette_neustarts"] == 1
