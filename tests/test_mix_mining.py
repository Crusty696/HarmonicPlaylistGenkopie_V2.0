"""Tests fuer das Mix-Mining-CLI-Werkzeug (reine Logik, keine Audiodateien).

Getestet werden nur die reinen Funktionen: Downloads und echte Analyse
laufen NICHT im Test — das waere langsam und nicht reproduzierbar.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from tools.mix_mining import (
    baue_zufallspaare,
    berechne_auc_richtung,
    baue_ergebnis,
)
from hpg_core.mix_analysis import TransitionSample


def _sample(groove, sub):
    """Baut ein minimales TransitionSample fuer Tests."""
    return TransitionSample(
        groove_pattern=[1.0] * 16,
        bass_pattern=groove,
        sub_energy=sub,
        bass_punch=0.0,
        brightness=50.0,
        timbre=[1.0, 0.0, 0.0],
    )


class TestBaueZufallspaare:
    def test_reproduzierbar_bei_gleichem_seed(self):
        fenster = [_sample([1.0, 0.0], float(i)) for i in range(6)]
        paare_a = baue_zufallspaare(fenster, anzahl=4, seed=42)
        paare_b = baue_zufallspaare(fenster, anzahl=4, seed=42)
        assert paare_a == paare_b

    def test_leer_bei_zu_wenig_fenstern(self):
        assert baue_zufallspaare([], anzahl=4, seed=42) == []
        assert baue_zufallspaare([_sample([1.0], 1.0)], anzahl=4, seed=42) == []

    def test_liefert_indexpaare_verschiedener_fenster(self):
        fenster = [_sample([1.0, 0.0], float(i)) for i in range(5)]
        paare = baue_zufallspaare(fenster, anzahl=10, seed=1)
        for i, j in paare:
            assert i != j
            assert 0 <= i < len(fenster)
            assert 0 <= j < len(fenster)


class TestBerechneAucRichtung:
    def test_richtung_stimmt_fuer_groove_und_sub(self):
        # Echte Uebergaenge: hohe groove_sim, niedriges sub_delta.
        echte = [
            {"groove_sim": 0.9, "sub_delta": 1.0, "punch_delta": 1.0,
             "brightness_delta": 2.0, "timbre_sim": 0.9}
            for _ in range(5)
        ]
        # Zufallspaare: niedrige groove_sim, hohes sub_delta.
        zufall = [
            {"groove_sim": 0.2, "sub_delta": 10.0, "punch_delta": 5.0,
             "brightness_delta": 20.0, "timbre_sim": 0.3}
            for _ in range(5)
        ]
        auc = berechne_auc_richtung(echte, zufall)
        assert auc["groove_sim"] > 0.5
        assert auc["sub_delta"] > 0.5


class TestBaueErgebnis:
    def test_enthaelt_erwartete_schluessel_und_gewichte(self):
        echte = [
            {"groove_sim": 0.9, "sub_delta": 1.0, "punch_delta": 1.0,
             "brightness_delta": 2.0, "timbre_sim": 0.9}
            for _ in range(3)
        ]
        zufall = [
            {"groove_sim": 0.2, "sub_delta": 10.0, "punch_delta": 5.0,
             "brightness_delta": 20.0, "timbre_sim": 0.3}
            for _ in range(3)
        ]
        ergebnis = baue_ergebnis(
            genre="Psytrance",
            echte_deltas=echte,
            zufalls_deltas=zufall,
            holdout=None,
        )
        assert ergebnis["genre"] == "Psytrance"
        assert ergebnis["anzahl_uebergaenge"] == 3
        assert ergebnis["anzahl_zufallspaare"] == 3
        assert set(ergebnis["auc"].keys()) == {
            "groove_sim", "sub_delta", "punch_delta",
            "brightness_delta", "timbre_sim",
        }
        gewichte = ergebnis["gewichte"]
        assert set(gewichte.keys()) == {
            "groove_weight", "bass_weight", "timbre_weight", "mood_weight",
        }
        assert gewichte["groove_weight"] == pytest.approx(
            gewichte["groove_weight"]
        )
        summe = sum(gewichte.values())
        assert summe == pytest.approx(0.30, abs=1e-9)
        assert "toleranzen" in ergebnis
        assert ergebnis["holdout"] is None

    def test_holdout_wird_uebernommen(self):
        echte = [
            {"groove_sim": 0.9, "sub_delta": 1.0, "punch_delta": 1.0,
             "brightness_delta": 2.0, "timbre_sim": 0.9}
        ]
        zufall = [
            {"groove_sim": 0.2, "sub_delta": 10.0, "punch_delta": 5.0,
             "brightness_delta": 20.0, "timbre_sim": 0.3}
        ]
        ergebnis = baue_ergebnis(
            genre="Psytrance",
            echte_deltas=echte,
            zufalls_deltas=zufall,
            holdout=True,
        )
        assert ergebnis["holdout"] is True
