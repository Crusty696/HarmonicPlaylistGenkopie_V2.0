import pytest

from hpg_core.genres import CANONICAL_GENRES
from hpg_core.playlist import (
    calculate_enhanced_compatibility,
    calculate_track_edge_score,
    generate_playlist_result,
    rebuild_result_for_order,
)
from tests.fixtures.track_factories import make_track


def _track(name, *, genre="Psytrance", energy=50):
    return make_track(
        filePath=f"C:/{name}.wav",
        fileName=f"{name}.wav",
        bpm=140.0,
        camelotCode="8A",
        genre=genre,
        detected_genre=genre,
        energy=energy,
        groove_pattern=[1.0, 0.0],
        bass_pattern=[1.0, 0.0],
        timbre_fingerprint=[1.0, 0.0],
        sub_energy=0.5,
        bass_punch=2.0,
        brightness=50.0,
        spectral_flatness=0.1,
    )


def _track_profiles(*, groove_weight):
    profile = {
        "harmonic_weight": 0.0,
        "bpm_weight": 0.0,
        "energy_weight": 0.0,
        "genre_weight": 0.0,
        "groove_weight": groove_weight,
        "bass_weight": 1.0 - groove_weight,
        "timbre_weight": 0.0,
        "mood_weight": 0.0,
    }
    return {genre: dict(profile) for genre in (*CANONICAL_GENRES, "Unknown")}


def test_track_edge_score_uses_source_genre_weight_snapshot():
    source = _track("source", genre="Psytrance")
    target = _track("target", genre="Techno")
    target.groove_pattern = [0.0, 1.0]

    groove_only = calculate_track_edge_score(
        source, target, 2.0,
        track_tolerances_by_genre=_track_profiles(groove_weight=1.0),
    )
    bass_only = calculate_track_edge_score(
        source, target, 2.0,
        track_tolerances_by_genre=_track_profiles(groove_weight=0.0),
    )

    assert groove_only.overall_score < bass_only.overall_score


def test_candidate_score_does_not_replace_track_edge_score():
    source = _track("source")
    target = _track("target")
    metrics = calculate_enhanced_compatibility(source, target, 2.0)

    assert metrics.kandidat is not None
    assert metrics.overall_score != pytest.approx(metrics.kandidat["score"])


def test_run_and_rebuild_keep_frozen_track_weight_snapshot():
    tracks = [_track("a"), _track("b")]
    profile = _track_profiles(groove_weight=1.0)
    result = generate_playlist_result(
        tracks,
        "Warm-Up",
        scoring_context={"track_tolerances_by_genre": profile},
    )
    before = result.metrics[0].overall_score
    profile["Psytrance"]["groove_weight"] = 0.0
    profile["Psytrance"]["bass_weight"] = 1.0

    rebuilt = rebuild_result_for_order(
        result, [occurrence.occurrence_id for occurrence in result.occurrences]
    )

    assert result.scoring_context_dict()["track_tolerances_by_genre"]["Psytrance"]["groove_weight"] == 1.0
    assert rebuilt.metrics[0].overall_score == pytest.approx(before)


@pytest.mark.parametrize("bad", [float("nan"), -0.1, 0.9])
def test_track_weight_snapshot_rejects_invalid_or_incomplete_sum(bad):
    source, target = _track("source"), _track("target")
    profiles = _track_profiles(groove_weight=1.0)
    profiles["Psytrance"]["harmonic_weight"] = bad

    with pytest.raises(ValueError, match="Gewicht"):
        calculate_track_edge_score(
            source, target, 2.0, track_tolerances_by_genre=profiles
        )
