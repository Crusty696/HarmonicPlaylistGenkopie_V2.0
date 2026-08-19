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
    zufallsdeltas_je_mix,
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


class TestZufallspaareBleibenImMix:
    """FIX 1: Die Negativklasse darf nicht mix-uebergreifend gezogen werden."""

    def test_echte_uebergaenge_sind_keine_zufallspaare(self):
        # alle_fenster liegt als [vor0, nach0, vor1, nach1, ...] — das Paar
        # (2k, 2k+1) IST Uebergang k und gehoert nicht in die Negativklasse.
        fenster = [_sample([1.0, 0.0], float(i)) for i in range(4)]
        paare = baue_zufallspaare(fenster, anzahl=50, seed=42)
        assert paare, "es muss gueltige Paare geben"
        for i, j in paare:
            assert {i, j} not in ({0, 1}, {2, 3})

    def test_keine_duplikate(self):
        fenster = [_sample([1.0, 0.0], float(i)) for i in range(6)]
        paare = baue_zufallspaare(fenster, anzahl=100, seed=7)
        als_mengen = [frozenset(p) for p in paare]
        assert len(als_mengen) == len(set(als_mengen))

    def test_deltas_stammen_aus_demselben_mix(self):
        # Mix A hat kleine sub_energy, Mix B eine sehr grosse. Ein
        # mix-uebergreifendes Paar wuerde ein sub_delta um 1000 erzeugen.
        mix_a = [_sample([1.0, 0.0], float(i)) for i in range(6)]
        mix_b = [_sample([1.0, 0.0], 1000.0 + i) for i in range(6)]
        echte_je_mix = [[{}] * 3, [{}] * 3]
        deltas_je_mix = zufallsdeltas_je_mix([mix_a, mix_b], echte_je_mix)
        assert len(deltas_je_mix) == 2
        for deltas in deltas_je_mix:
            assert deltas
            for d in deltas:
                assert d["sub_delta"] < 100.0


class TestBaueErgebnisMitGrenzen:
    """FIX 4: mit Konfidenzgrenzen kommt das Budget aus der Effektstaerke."""

    _ECHTE = [
        {"groove_sim": 0.9, "sub_delta": 1.0, "punch_delta": 1.0,
         "brightness_delta": 2.0, "timbre_sim": 0.9}
    ]
    _ZUFALL = [
        {"groove_sim": 0.2, "sub_delta": 10.0, "punch_delta": 5.0,
         "brightness_delta": 20.0, "timbre_sim": 0.3}
    ]

    def test_grenzen_landen_im_json(self):
        grenzen = {
            "groove_sim": (0.646, 0.570, 0.723),
            "timbre_sim": (0.674, 0.599, 0.748),
            "sub_delta": (0.627, 0.550, 0.705),
            "punch_delta": (0.535, 0.454, 0.615),
            "brightness_delta": (0.536, 0.455, 0.616),
        }
        ergebnis = baue_ergebnis(
            genre="Psytrance", echte_deltas=self._ECHTE,
            zufalls_deltas=self._ZUFALL, holdout=None, grenzen=grenzen,
        )
        assert set(ergebnis["auc_grenzen"]) == set(grenzen)
        assert ergebnis["auc_grenzen"]["groove_sim"] == [0.646, 0.57, 0.723]
        # Budget skaliert mit timbre_sim (untere Grenze 0,599 -> roh 0,198).
        summe = sum(ergebnis["gewichte"].values())
        assert summe == pytest.approx(0.30 * 0.198, abs=1e-6)
        assert summe < 0.30

    def test_ohne_gesicherten_faktor_bleibt_alles_null(self):
        grenzen = {
            faktor: (0.52, 0.44, 0.60)
            for faktor in ("groove_sim", "timbre_sim", "sub_delta",
                           "punch_delta", "brightness_delta")
        }
        ergebnis = baue_ergebnis(
            genre="Techno", echte_deltas=self._ECHTE,
            zufalls_deltas=self._ZUFALL, holdout=None, grenzen=grenzen,
        )
        assert sum(ergebnis["gewichte"].values()) == pytest.approx(0.0)
