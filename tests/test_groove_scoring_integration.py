"""Tests fuer die Integration der vier neuen Faktoren ins Scoring."""
import pytest

from hpg_core.playlist import combine_weighted


def test_combine_weighted_alle_vorhanden():
    komponenten = {"a": 1.0, "b": 0.0}
    gewichte = {"a": 0.5, "b": 0.5}
    assert combine_weighted(komponenten, gewichte) == pytest.approx(0.5)


def test_combine_weighted_verteilt_fehlende_um():
    # b fehlt -> a traegt allein, Ergebnis ist a selbst, nicht a*0.5
    komponenten = {"a": 1.0, "b": None}
    gewichte = {"a": 0.5, "b": 0.5}
    assert combine_weighted(komponenten, gewichte) == pytest.approx(1.0)


def test_combine_weighted_umverteilung_bleibt_proportional():
    komponenten = {"a": 1.0, "b": 0.0, "c": None}
    gewichte = {"a": 0.2, "b": 0.6, "c": 0.2}
    # verfuegbar: a=0.2, b=0.6 -> Summe 0.8 -> (0.2*1.0 + 0.6*0.0)/0.8 = 0.25
    assert combine_weighted(komponenten, gewichte) == pytest.approx(0.25)


def test_combine_weighted_alles_fehlt_gibt_null():
    assert combine_weighted({"a": None}, {"a": 1.0}) == 0.0
