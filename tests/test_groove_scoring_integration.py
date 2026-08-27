"""Integration des ausschliesslich lokalen Paarvertrags ins Scoring."""

import pytest

from hpg_core.playlist import (
    EnergyDirection,
    calculate_enhanced_compatibility,
    calculate_playlist_quality,
    combine_weighted,
    compute_adjacent_transition_metrics,
    reset_pair_candidate_cache,
)
from tests.fixtures.track_factories import make_track


def test_combine_weighted_alle_vorhanden():
    assert combine_weighted({"a": 1.0, "b": 0.0}, {"a": 0.5, "b": 0.5}) == pytest.approx(0.5)


def test_combine_weighted_verteilt_fehlende_um():
    assert combine_weighted({"a": 1.0, "b": None}, {"a": 0.5, "b": 0.5}) == pytest.approx(1.0)


def test_combine_weighted_umverteilung_bleibt_proportional():
    komponenten = {"a": 1.0, "b": 0.0, "c": None}
    gewichte = {"a": 0.2, "b": 0.6, "c": 0.2}
    assert combine_weighted(komponenten, gewichte) == pytest.approx(0.25)


def test_combine_weighted_alles_fehlt_gibt_null():
    assert combine_weighted({"a": None}, {"a": 1.0}) == 0.0


def _gerade():
    return [0.8 if index % 4 == 0 else 0.0 for index in range(16)]


def _leicht_verschieden_aber_passend():
    return [0.7 if index % 4 == 0 else (0.1 if index % 4 == 2 else 0.0) for index in range(16)]


def _offbeat():
    return [0.8 if index % 4 == 2 else 0.0 for index in range(16)]


def _paar(muster_a=None, muster_b=None):
    a = make_track(filePath="a.mp3", fileName="a.mp3", bpm=140.0,
                   camelotCode="8A", energy=60, genre="Psytrance")
    b = make_track(filePath="b.mp3", fileName="b.mp3", bpm=140.0,
                   camelotCode="8A", energy=62, genre="Psytrance")
    for track in (a, b):
        track.detected_genre = "Psytrance"
    a.mix_out_candidates[0].groove_pattern_lokal = muster_a or _gerade()
    a.mix_out_candidates[0].bass_pattern_lokal = muster_a or _gerade()
    b.mix_in_candidates[0].groove_pattern_lokal = muster_b or _gerade()
    b.mix_in_candidates[0].bass_pattern_lokal = muster_b or _gerade()
    reset_pair_candidate_cache()
    return a, b


def test_metrics_tragen_alle_lokalen_faktoren():
    a, b = _paar()
    metrics = calculate_enhanced_compatibility(a, b, bpm_tolerance=6.0)
    for feld in (
        "groove_match", "bass_continuity", "timbre_match", "mood_match",
        "loudness_match", "structure_match",
    ):
        assert getattr(metrics, feld) is not None
    assert metrics.kandidat is not None


def test_verschiedener_kompatibler_groove_ist_erlaubt():
    a, b = _paar(_gerade(), _leicht_verschieden_aber_passend())
    metrics = calculate_enhanced_compatibility(a, b, bpm_tolerance=6.0)
    assert metrics.groove_match >= 0.50
    assert metrics.overall_score >= 0.70


def test_echter_rhythmuskonflikt_verwirft_nur_den_mixpunktkandidaten():
    a, b = _paar(_gerade(), _offbeat())
    metrics = calculate_enhanced_compatibility(a, b, bpm_tolerance=6.0)
    assert metrics.kandidat is None
    assert metrics.overall_score > 0.0


def test_fehlende_lokale_groove_daten_verwerfen_nur_den_mixpunktkandidaten():
    a, b = _paar()
    a.mix_out_candidates[0].groove_pattern_lokal = []
    a.mix_out_candidates[0].bass_pattern_lokal = []
    reset_pair_candidate_cache()
    metrics = calculate_enhanced_compatibility(a, b, bpm_tolerance=6.0)
    assert metrics.kandidat is None
    assert metrics.overall_score > 0.0


def test_trackkante_nutzt_ganztrackwerte_ohne_mixpunktkandidaten():
    a, b = _paar()
    a.mix_out_candidates = []
    b.mix_in_candidates = []
    a.groove_pattern = b.groove_pattern = _gerade()
    a.bass_pattern = b.bass_pattern = _gerade()
    reset_pair_candidate_cache()
    metrics = calculate_enhanced_compatibility(a, b, bpm_tolerance=6.0)
    assert metrics.kandidat is None
    assert metrics.groove_match == pytest.approx(1.0)
    assert metrics.overall_score > 0.0


def test_bpm_hard_gate_bleibt_wirksam():
    a, b = _paar()
    b.bpm = 175.0
    reset_pair_candidate_cache()
    assert calculate_enhanced_compatibility(a, b, bpm_tolerance=6.0).overall_score == 0.0


def test_bpm_hard_gate_gilt_auch_fuer_adjacent_metrics():
    a = make_track(
        filePath="a.mp3", bpm=140.0, genre="Psytrance", detected_genre="Psytrance"
    )
    b = make_track(
        filePath="b.mp3", bpm=141.5, genre="Psytrance", detected_genre="Psytrance"
    )
    reset_pair_candidate_cache()
    assert compute_adjacent_transition_metrics(
        [a, b], bpm_tolerance=2.0
    )[0].kandidat is not None

    metrics = compute_adjacent_transition_metrics([a, b], bpm_tolerance=1.0)

    assert metrics[0].overall_score == 0.0
    assert metrics[0].kandidat is None


def test_energy_direction_wird_fuer_alle_kandidatenpfade_normalisiert():
    import hpg_core.playlist as playlist_modul

    a, b = _paar()
    a.mix_out_candidates[0].energy_lokal = 40
    b.mix_in_candidates[0].energy_lokal = 90
    b.mix_in_candidates[0].energy_trend = "rising"

    als_preset = compute_adjacent_transition_metrics(
        [a, b], bpm_tolerance=6.0, scoring_context={"energy_direction": "Build Up"}
    )[0]
    cache_eintraege = len(playlist_modul._PAIR_CANDIDATE_CACHE)
    als_enum = calculate_enhanced_compatibility(
        a, b, bpm_tolerance=6.0, energy_direction=EnergyDirection.UP
    )

    assert als_preset.energy_flow == pytest.approx(als_enum.energy_flow)
    assert als_preset.overall_score == pytest.approx(als_enum.overall_score)
    assert len(playlist_modul._PAIR_CANDIDATE_CACHE) == cache_eintraege


def test_pair_cache_ist_an_die_konkreten_trackobjekte_gebunden():
    a, b = _paar()
    zuerst = calculate_enhanced_compatibility(a, b, bpm_tolerance=6.0)
    assert zuerst.energy_delta == pytest.approx(2.0)

    a_neu = make_track(
        filePath="a.mp3", fileName="a.mp3", bpm=140.0, energy=20,
        genre="Psytrance", detected_genre="Psytrance",
    )
    b_neu = make_track(
        filePath="b.mp3", fileName="b.mp3", bpm=140.0, energy=80,
        genre="Psytrance", detected_genre="Psytrance",
    )
    a_neu.mix_out_candidates[0].energy_lokal = 20
    b_neu.mix_in_candidates[0].energy_lokal = 80

    danach = calculate_enhanced_compatibility(a_neu, b_neu, bpm_tolerance=6.0)

    assert danach.energy_delta == pytest.approx(60.0)


def test_quality_und_aktive_lokale_metrik_stimmen_ueberein():
    a, b = _paar()
    metrics = compute_adjacent_transition_metrics([a, b], bpm_tolerance=6.0)
    quality = calculate_playlist_quality(
        [a, b], bpm_tolerance=6.0, transition_metrics=metrics
    )
    assert quality["overall_score"] == pytest.approx(
        round(metrics[0].overall_score * 100) / 100.0
    )
    assert quality["energy_consistency"] == pytest.approx(metrics[0].energy_flow)
    assert quality["bpm_smoothness"] == pytest.approx(metrics[0].bpm_smoothness)


def test_quality_meldet_echte_lokale_spruenge_statt_score_inversion():
    a = make_track(
        filePath="a.mp3", bpm=140.0, energy=35,
        genre="Psytrance", detected_genre="Psytrance",
    )
    b = make_track(
        filePath="b.mp3", bpm=141.5, energy=47,
        genre="Psytrance", detected_genre="Psytrance",
    )
    a.mix_out_candidates[0].energy_lokal = 35
    b.mix_in_candidates[0].energy_lokal = 47
    reset_pair_candidate_cache()
    metrics = compute_adjacent_transition_metrics([a, b], bpm_tolerance=6.0)

    quality = calculate_playlist_quality(
        [a, b], bpm_tolerance=6.0, transition_metrics=metrics
    )

    assert quality["avg_energy_jump"] == pytest.approx(12.0)
    assert quality["avg_bpm_jump"] == pytest.approx(1.5)
