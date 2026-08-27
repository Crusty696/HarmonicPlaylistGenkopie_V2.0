"""Enger Vertrag fuer die reine ID3-BPM-Faktorkorrektur."""

import ast
import inspect
import math

import pytest

from hpg_core.analysis import (
    ID3_BPM_FACTOR_CANDIDATES,
    _correct_id3_bpm_factor,
)
from hpg_core import analysis
from hpg_core.caching import CACHE_VERSION


def test_faktoren_enthalten_drei_viertel_und_vier_drittel():
    assert 3.0 / 4.0 in ID3_BPM_FACTOR_CANDIDATES
    assert 4.0 / 3.0 in ID3_BPM_FACTOR_CANDIDATES


def test_geaenderter_bpm_vertrag_ist_in_cache_version_43_enthalten():
    assert CACHE_VERSION == 43


@pytest.mark.parametrize(
    ("tag_bpm", "measured_bpm", "expected"),
    [
        (105.0, 143.5547, 140.0),
        (140.0, 92.3, 140.0),
        (93.0, 136.0, 139.5),
    ],
)
def test_psytrance_korrigiert_nur_plausible_faktorfehler(
    tag_bpm, measured_bpm, expected
):
    assert _correct_id3_bpm_factor(
        tag_bpm, measured_bpm, "Psy-Trance"
    ) == expected


@pytest.mark.parametrize("genre", ["", "Unknown", "Ambient", None])
def test_unbekanntes_oder_fehlendes_id3_genre_korrigiert_nie(genre):
    assert _correct_id3_bpm_factor(105.0, 143.5547, genre) == 105.0


def test_direkte_abweichung_von_exakt_acht_prozent_bleibt_unveraendert():
    measured = 105.0 / 0.92
    assert math.isclose(abs(105.0 - measured) / measured, 0.08)
    assert _correct_id3_bpm_factor(105.0, measured, "Psytrance") == 105.0


def test_faktorabweichung_ueber_sechs_prozent_bleibt_unveraendert():
    measured = 143.7
    assert abs(180.0 * 0.75 - measured) / measured > 0.06
    assert _correct_id3_bpm_factor(180.0, measured, "Psytrance") == 180.0


def test_faktorabweichung_von_exakt_sechs_prozent_wird_korrigiert():
    measured = 140.0 / 0.94
    assert math.isclose(abs(140.0 - measured) / measured, 0.06)
    assert _correct_id3_bpm_factor(105.0, measured, "Psytrance") == 140.0


def test_nur_faktoren_im_genrebereich_konkurrieren_um_beste_abgleichung():
    measured = 141.51
    assert abs(100.0 * (4.0 / 3.0) - measured) < abs(150.0 - measured)
    assert abs(150.0 - measured) / measured <= 0.06
    assert _correct_id3_bpm_factor(100.0, measured, "Psytrance") == 150.0


@pytest.mark.parametrize("measured", [None, 0.0, -1.0, float("nan"), float("inf")])
def test_ungueltige_audiomessung_bleibt_unveraendert(measured):
    assert _correct_id3_bpm_factor(105.0, measured, "Psytrance") == 105.0


def test_analyse_nutzt_id3_genre_erst_hinter_dem_rekordbox_fastpath():
    source = inspect.getsource(analysis.analyze_track)
    tree = ast.parse(source)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_correct_id3_bpm_factor"
    ]
    assert len(calls) == 1
    assert isinstance(calls[0].args[2], ast.Name)
    assert calls[0].args[2].id == "genre_id3"
    assert source.index("if rekordbox_data and rekordbox_data.bpm:") < source.index(
        "_correct_id3_bpm_factor("
    )
