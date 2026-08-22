"""Tests fuer die Persistenz der Kandidaten-Wahl je Paar (Teil 4)."""
import json

import pytest

from hpg_core import candidate_choices as cc


@pytest.fixture(autouse=True)
def _datei(monkeypatch, tmp_path):
    monkeypatch.setenv("HPG_CANDIDATE_CHOICES_FILE", str(tmp_path / "choices.json"))
    cc.reset_cache()
    yield
    cc.reset_cache()


def test_schluessel_ist_pfadnormiert_und_gerichtet():
    k1 = cc.schluessel("C:/Musik/A.mp3", "c:\\musik\\b.mp3")
    k2 = cc.schluessel("c:\\MUSIK\\a.mp3", "C:/Musik/B.mp3")
    assert k1 == k2
    assert cc.schluessel("a.mp3", "b.mp3") != cc.schluessel("b.mp3", "a.mp3")


def test_merke_und_hole_roundtrip(tmp_path):
    assert cc.hole("a.mp3", "b.mp3") is None
    cc.merke("a.mp3", "b.mp3", t_out=160.0, t_in=80.0, blend_bars=16)
    w = cc.hole("a.mp3", "b.mp3")
    assert w["t_out"] == 160.0 and w["t_in"] == 80.0 and w["blend_bars"] == 16 and w["zeit"]
    daten = json.loads((tmp_path / "choices.json").read_text(encoding="utf-8"))
    assert len(daten) == 1
    cc.reset_cache()
    assert cc.hole("a.mp3", "b.mp3")["t_out"] == 160.0        # neu geladen


def test_vergiss_entfernt_nur_das_paar():
    cc.merke("a.mp3", "b.mp3", t_out=1.0, t_in=2.0, blend_bars=8)
    cc.merke("a.mp3", "c.mp3", t_out=3.0, t_in=4.0, blend_bars=8)
    cc.vergiss("a.mp3", "b.mp3")
    assert cc.hole("a.mp3", "b.mp3") is None and cc.hole("a.mp3", "c.mp3")["t_out"] == 3.0


def test_kaputte_datei_wird_als_leer_behandelt(tmp_path):
    (tmp_path / "choices.json").write_text("{kaputt", encoding="utf-8")
    cc.reset_cache()
    assert cc.hole("a.mp3", "b.mp3") is None
    cc.merke("a.mp3", "b.mp3", t_out=1.0, t_in=2.0, blend_bars=8)   # ueberschreibt sauber
    assert cc.hole("a.mp3", "b.mp3")["t_out"] == 1.0
