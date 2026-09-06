"""V6-Vertrag: ein unveraenderliches Ergebnis fuer Trackfolge und Mixkette."""

from dataclasses import FrozenInstanceError, replace
import inspect
import unicodedata

import pytest

from hpg_core import candidate_choices, candidate_preferences
from hpg_core import pair_candidates as pc
from hpg_core import playlist as pl
from hpg_core.config import PAAR_BPM_MAX
from hpg_core.mix_candidates import MixCandidate
from hpg_core.models import Track
from tests.fixtures.track_factories import make_track


FACTORS = (
    "harmonic", "bpm", "energy", "genre", "groove", "bass", "timbre",
    "mood", "loudness", "structure",
)


def test_scoring_cache_trennt_pfadgleiche_trackinstanzen():
    first = _track("same.wav")
    second = _track("same.wav")
    target = _track("target.wav")
    second.camelotCode = "2A"
    assert first.track_id == second.track_id

    previous_cache = pl._COMPAT_CACHE
    pl._COMPAT_CACHE = {}
    try:
        first_score = pl.calculate_compatibility(first, target, 3.0)
        second_score = pl.calculate_compatibility(second, target, 3.0)
    finally:
        pl._COMPAT_CACHE = previous_cache

    assert first_score == 100
    assert second_score == pl._calculate_compatibility_inner(second, target, 3.0)
    assert second_score != first_score


def test_partieller_scoring_context_behaelt_kandidatenvertrag(monkeypatch):
    monkeypatch.setattr(candidate_choices, "snapshot", lambda: {})
    tracks = [
        make_track(
            filePath="a.wav", fileName="a.wav",
            genre="Psytrance", detected_genre="Psytrance",
        ),
        make_track(
            filePath="b.wav", fileName="b.wav",
            genre="Psytrance", detected_genre="Psytrance",
        ),
    ]
    for track in tracks:
        track.analysis_coverage = [{"start": 0.0, "end": track.duration}]
    contexts = (None, {}, pl.resolve_scoring_context("Warm-Up", {}))
    results = [
        pl.generate_playlist_result(
            tracks, "Warm-Up", 2.0, scoring_context=context
        )
        for context in contexts
    ]

    assert all(result.boundaries[0].snapshots for result in results)
    assert [result.path_stats.planned for result in results] == [1, 1, 1]
    assert [result.path_stats.total_score for result in results] == pytest.approx(
        [results[0].path_stats.total_score] * 3
    )


def test_vollstaendiger_laufstart_snapshot_wird_nicht_live_neu_geladen(monkeypatch):
    snapshot = pl.resolve_run_scoring_context("Warm-Up", {})

    def fail_live_reload(*args, **kwargs):
        raise RuntimeError("kein Live-Reload nach dem Laufstart")

    monkeypatch.setattr(pl, "resolve_run_scoring_context", fail_live_reload)
    completed = pl._complete_run_scoring_context("Warm-Up", {}, snapshot)
    result = pl.generate_playlist_result(
        [_track("a.wav")],
        "Warm-Up",
        scoring_context=snapshot,
        candidate_choice_snapshot={},
    )

    assert completed == snapshot
    assert result.scoring_context_dict() == snapshot
    assert result.path_stats.planned == 0
    repeated = pl.generate_playlist_result(
        [_track("b.wav")],
        "Warm-Up",
        scoring_context=result.scoring_context_dict(),
        candidate_choice_snapshot={},
    )
    assert repeated.scoring_context_dict() == snapshot


def test_immutable_result_erhaelt_leere_mapping_und_listentypen():
    supplied = {"mapping": {}, "sequence": [], "pairs": [["x", 1]]}

    assert pl._thaw_immutable(pl._freeze_immutable(supplied)) == supplied


def test_partielles_genreprofil_wird_tief_in_laufkontext_gemerged():
    context = pl._complete_run_scoring_context(
        "Warm-Up",
        {},
        {
            "candidate_tolerances_by_genre": {
                "Psytrance": {"kandidaten_groove_weight": 0.3}
            },
            "candidate_schema_ranks_by_genre": {
                "Psytrance": ["sektion", "analyzer"]
            },
        },
    )

    psy = context["candidate_tolerances_by_genre"]["Psytrance"]
    assert psy["kandidaten_groove_weight"] == 0.3
    assert "kandidaten_harmonic_weight" in psy
    assert sum(
        psy[key] for key in candidate_preferences.GEWICHT_SCHLUESSEL
    ) == pytest.approx(1.0)
    assert "Unknown" in context["candidate_tolerances_by_genre"]
    assert context["candidate_schema_ranks_by_genre"]["Psytrance"] == [
        "sektion", "analyzer"
    ]


@pytest.mark.parametrize(
    "ranks",
    [
        None,
        "sektion",
        {"sektion": 1},
        ["sektion", 1],
        ["sektion", "sektion"],
        ["nicht_bekannt"],
    ],
)
def test_ungueltige_schema_snapshots_werden_abgelehnt(ranks):
    with pytest.raises(ValueError, match="eindeutige Liste"):
        pl._complete_run_scoring_context(
            "Warm-Up",
            {},
            {"candidate_schema_ranks_by_genre": {"Psytrance": ranks}},
        )


@pytest.mark.parametrize(
    ("key", "message"),
    [
        ("candidate_tolerances_by_genre", "muss ein Mapping sein"),
        ("candidate_schema_ranks_by_genre", "muss ein Mapping sein"),
    ],
)
def test_explizites_none_fuer_kandidaten_snapshot_wird_abgelehnt(key, message):
    with pytest.raises(ValueError, match=message):
        pl._complete_run_scoring_context("Warm-Up", {}, {key: None})


@pytest.mark.parametrize(
    ("value", "message"),
    [(True, "endliches Gewicht"), (float("nan"), "endliches Gewicht"),
     (-0.1, "endliches Gewicht"), (1.1, "endliches Gewicht")],
)
def test_partielle_genregewichte_werden_strikt_validiert(value, message):
    with pytest.raises(ValueError, match=message):
        pl._complete_run_scoring_context(
            "Warm-Up",
            {},
            {
                "candidate_tolerances_by_genre": {
                    "Psytrance": {"kandidaten_groove_weight": value}
                }
            },
        )


@pytest.mark.parametrize("value", [0.05, 0.2])
def test_vollstaendiges_genreprofil_braucht_gewichtssumme_eins(value):
    invalid = {
        key: value for key in candidate_preferences.GEWICHT_SCHLUESSEL
    }
    with pytest.raises(ValueError, match="summieren"):
        pl._complete_run_scoring_context(
            "Warm-Up", {},
            {"candidate_tolerances_by_genre": {"Psytrance": invalid}},
        )


@pytest.mark.parametrize("ranks", [(), [], ("sektion", "analyzer")])
def test_gueltige_schema_snapshots_werden_defensiv_kopiert(ranks):
    context = pl._complete_run_scoring_context(
        "Warm-Up", {},
        {"candidate_schema_ranks_by_genre": {"Psytrance": ranks}},
    )
    assert context["candidate_schema_ranks_by_genre"]["Psytrance"] == list(ranks)


@pytest.mark.parametrize(
    "key", ["candidate_tolerances_by_genre", "candidate_schema_ranks_by_genre"]
)
@pytest.mark.parametrize("genre", ["Nicht kanonisch", 7])
def test_kandidatenprofile_verwerfen_unbekannte_genres(key, genre):
    value = {} if key == "candidate_tolerances_by_genre" else []
    with pytest.raises(ValueError, match="unbekanntes Genre"):
        pl._complete_run_scoring_context(
            "Warm-Up", {}, {key: {genre: value}}
        )


@pytest.mark.parametrize("key", ["unbekannt", 7])
def test_toleranzprofil_verwirft_unbekannte_profilkeys(key):
    with pytest.raises(ValueError, match="unbekannte Profil-Schluessel"):
        pl._complete_run_scoring_context(
            "Warm-Up",
            {},
            {"candidate_tolerances_by_genre": {"Psytrance": {key: 0.5}}},
        )


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("harmonic_weight", "0.2"),
        ("harmonic_weight", True),
        ("harmonic_weight", -0.1),
        ("harmonic_weight", float("nan")),
        ("harmonic_weight", float("inf")),
        ("harmonic_weight", 1.1),
        ("groove_sim_floor", "0.5"),
        ("groove_sim_floor", False),
        ("groove_sim_floor", -0.1),
        ("groove_sim_floor", float("nan")),
        ("groove_sim_floor", float("inf")),
        ("groove_sim_floor", 1.1),
        ("bass_delta_max", "0.5"),
        ("bass_delta_max", True),
        ("bass_delta_max", 0.0),
        ("bass_delta_max", -0.1),
        ("bass_delta_max", float("nan")),
        ("bass_delta_max", float("inf")),
        ("brightness_delta_max", 0.0),
    ],
)
def test_toleranzprofil_verwirft_semantisch_ungueltige_felder(key, value):
    with pytest.raises(ValueError, match=key):
        pl._complete_run_scoring_context(
            "Warm-Up",
            {},
            {"candidate_tolerances_by_genre": {"Psytrance": {key: value}}},
        )


def test_toleranzprofil_akzeptiert_gueltige_partielle_genre_und_fallbackwerte():
    context = pl._complete_run_scoring_context(
        "Warm-Up",
        {},
        {
            "candidate_tolerances_by_genre": {
                "Psytrance": {
                    "harmonic_weight": 0.2,
                    "kandidaten_groove_weight": 0.3,
                    "groove_sim_floor": 0.7,
                    "bass_delta_max": 0.5,
                    "brightness_delta_max": 50,
                },
                "Unknown": {"brightness_delta_max": 40},
            }
        },
    )

    psy = context["candidate_tolerances_by_genre"]["Psytrance"]
    assert psy["harmonic_weight"] == 0.2
    assert psy["kandidaten_groove_weight"] == 0.3
    assert psy["groove_sim_floor"] == 0.7
    assert psy["bass_delta_max"] == 0.5
    assert psy["brightness_delta_max"] == 50.0
    assert context["candidate_tolerances_by_genre"]["Unknown"][
        "brightness_delta_max"
    ] == 40.0


def _track(name: str, bpm: float = 140.0) -> Track:
    track = Track(filePath=name, fileName=name)
    track.bpm = bpm
    track.duration = 300.0
    track.camelotCode = "8A"
    track.energy = 60
    track.detected_genre = "Psytrance"
    track.phrase_unit = 16
    track.first_downbeat = 0.0
    track.downbeat_confidence = 1.0
    track.sections = [
        {"label": "intro", "start_time": 0.0, "end_time": 60.0},
        {"label": "main", "start_time": 60.0, "end_time": 240.0},
        {"label": "outro", "start_time": 240.0, "end_time": 300.0},
    ]
    track.outro_covered = True
    return track


def _candidate(
    t_out: float,
    t_in: float,
    *,
    score: float = 0.8,
    saved: bool = False,
    rank: int = 1,
    schema: str = "se\u0301ktion",
) -> pc.PairCandidate:
    out = MixCandidate(t=t_out, schema=[schema], energy_lokal=50.0, lufs_lokal=-10.0)
    inn = MixCandidate(t=t_in, schema=["pssi_phrase"], energy_lokal=55.0, lufs_lokal=-9.0)
    return pc.PairCandidate(
        out_a=out,
        in_b=inn,
        blend_bars=16,
        overlap_sec=16.0,
        score=score,
        teilwerte={name: 0.8 for name in FACTORS},
        flags={"gespeicherte_wahl": saved, "nested": ["e\u0301", {"x": True}]},
        begruendung="gute U\u0308bergabe",
        rang=rank,
        bpm_relation="direct",
    )


def _identity_strategy(monkeypatch):
    monkeypatch.setitem(
        pl.STRATEGIES,
        "Warm-Up",
        lambda items, bpm_tolerance, **kwargs: list(items),
    )


def test_candidate_snapshot_kanonisiert_und_validiert_key_tief():
    candidate = _candidate(10.024, 20.026)

    snapshot = pc.CandidateSnapshot.from_pair_candidate(
        candidate, original_ordinal=3
    )

    assert snapshot.key == (
        200,
        401,
        16,
        "direct",
        (unicodedata.normalize("NFC", "se\u0301ktion"),),
        ("pssi_phrase",),
        3,
    )
    assert snapshot.begruendung == unicodedata.normalize("NFC", "gute U\u0308bergabe")
    assert isinstance(snapshot.flags, tuple)
    assert isinstance(dict(snapshot.flags)["nested"], tuple)
    with pytest.raises(FrozenInstanceError):
        snapshot.score = 0.1
    with pytest.raises(ValueError, match="key ist nicht kanonisch"):
        replace(snapshot, key=(0,))
    with pytest.raises(ValueError, match="overlap_sec"):
        pc.CandidateSnapshot.from_pair_candidate(
            replace(candidate, overlap_sec=64.001), original_ordinal=0
        )
    with pytest.raises(ValueError, match="score"):
        pc.CandidateSnapshot.from_pair_candidate(
            replace(candidate, score=float("nan")), original_ordinal=0
        )


@pytest.mark.parametrize("tracks", [[], [_track("one.wav")]])
def test_nullfaelle_haben_exakt_null_graph_und_path_stats(monkeypatch, tracks):
    _identity_strategy(monkeypatch)
    calls = 0

    def choices():
        nonlocal calls
        calls += 1
        return {}

    monkeypatch.setattr(candidate_choices, "snapshot", choices)
    monkeypatch.setattr(
        pc,
        "rank_pair_candidates",
        lambda *args, **kwargs: pytest.fail("Kein Boundary-Rank bei N<2"),
    )

    result = pl.generate_playlist_result(
        tracks, "Warm-Up", scoring_context={}
    )

    assert calls == 1
    assert len(result.tracks) == len(tracks)
    assert result.boundaries == result.metrics == result.recommendations == ()
    assert result.graph_stats.boundaries_total == 0
    assert result.graph_stats.candidate_snapshots == 0
    assert result.graph_stats.saved_present == 0
    assert result.path_stats == pl.PathStats(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.0)


def test_result_rankt_jede_feste_kante_einmal_und_friert_legacy_ab(monkeypatch):
    _identity_strategy(monkeypatch)
    tracks = [_track("a.wav"), _track("b.wav"), _track("c.wav")]
    choice_key = candidate_choices.schluessel("a.wav", "b.wav")
    choice_calls = 0
    rank_calls = []

    def choices():
        nonlocal choice_calls
        choice_calls += 1
        return {choice_key: {"marker": "saved"}}

    def rank(a, b, **kwargs):
        rank_calls.append((a.filePath, b.filePath, kwargs["wahl"]))
        index = len(rank_calls)
        return [
            _candidate(
                120.0 + index * 20.0,
                70.0,
                saved=bool(kwargs["wahl"]),
            )
        ]

    monkeypatch.setattr(candidate_choices, "snapshot", choices)
    monkeypatch.setattr(pc, "rank_pair_candidates", rank)

    result = pl.generate_playlist_result(
        tracks,
        "Warm-Up",
        bpm_tolerance=2.0,
        scoring_context={
            "candidate_schema_ranks_by_genre": {
                "Psytrance": ["sektion", "analyzer"]
            }
        },
    )

    assert choice_calls == 1
    assert rank_calls == [
        ("a.wav", "b.wav", {"marker": "saved"}),
        ("b.wav", "c.wav", {}),
    ]
    assert len(result.boundaries) == len(result.recommendations) == 2
    assert all(boundary.selected is not None for boundary in result.boundaries)
    assert all(recommendation.plan is not None for recommendation in result.recommendations)
    assert result.graph_stats == pl.GraphStats(3, 3, 0, 2, 2, 0, 2, 1)
    assert result.path_stats.planned == 2
    assert result.path_stats.unplanned == 0
    assert result.path_stats.saved_honored == 1
    assert result.path_stats.segments == 1
    assert result.path_stats.segment_restarts == 0
    assert result.path_stats.states_retained == 4
    assert result.path_stats.link_checks == 1
    assert result.path_stats.consistent_links == 1
    assert result.path_stats.link_checks <= 144 * max(
        result.path_stats.with_candidates - 1, 0
    )

    legacy = pl.legacy_transition_recommendations(result)
    assert legacy[0].kandidaten[0]["candidate_key"] == result.boundaries[0].selected.key
    legacy[0].kandidaten[0]["flags"]["gespeicherte_wahl"] = False
    legacy[0].notes = "mutiert"
    assert dict(result.boundaries[0].selected.flags)["gespeicherte_wahl"] is True
    assert result.recommendations[0].notes != "mutiert"
    context = result.scoring_context_dict()
    context["candidate_schema_ranks_by_genre"]["Psytrance"][0] = "analyzer"
    assert result.scoring_context_dict()[
        "candidate_schema_ranks_by_genre"
    ]["Psytrance"][0] == "sektion"


def test_expliziter_choice_snapshot_gewinnt_gegen_spaeteren_store(monkeypatch):
    _identity_strategy(monkeypatch)
    tracks = [_track("a.wav"), _track("b.wav")]
    key = candidate_choices.schluessel("a.wav", "b.wav")
    supplied = {key: {"marker": "run-start"}}
    seen = []

    monkeypatch.setattr(
        candidate_choices,
        "snapshot",
        lambda: pytest.fail("Expliziter Run-Snapshot darf Store nicht neu lesen"),
    )

    def rank(*args, **kwargs):
        seen.append(kwargs["wahl"])
        return [_candidate(150.0, 70.0, saved=True)]

    monkeypatch.setattr(pc, "rank_pair_candidates", rank)

    result = pl.generate_playlist_result(
        tracks,
        "Warm-Up",
        scoring_context={},
        candidate_choice_snapshot=supplied,
    )
    supplied[key]["marker"] = "nachtraeglich-mutiert"

    assert seen == [{"marker": "run-start"}]
    assert result.graph_stats.saved_present == 1
    assert isinstance(result.candidate_choice_snapshot, tuple)
    first_copy = result.candidate_choice_snapshot_dict()
    assert first_copy == {key: {"marker": "run-start"}}
    first_copy[key]["marker"] = "Accessor mutiert"
    assert result.candidate_choice_snapshot_dict() == {
        key: {"marker": "run-start"}
    }


def test_choice_snapshot_none_behaelt_live_store_pfad(monkeypatch):
    _identity_strategy(monkeypatch)
    tracks = [_track("a.wav"), _track("b.wav")]
    key = candidate_choices.schluessel("a.wav", "b.wav")
    calls = 0

    def live_snapshot():
        nonlocal calls
        calls += 1
        return {key: {"marker": "live"}}

    monkeypatch.setattr(candidate_choices, "snapshot", live_snapshot)
    monkeypatch.setattr(
        pc,
        "rank_pair_candidates",
        lambda *args, **kwargs: (
            [_candidate(150.0, 70.0, saved=True)]
            if kwargs["wahl"] == {"marker": "live"}
            else pytest.fail("Live-Snapshot wurde nicht durchgereicht")
        ),
    )

    result = pl.generate_playlist_result(
        tracks, "Warm-Up", scoring_context={}, candidate_choice_snapshot=None
    )

    assert calls == 1
    assert result.graph_stats.saved_present == 1


@pytest.mark.parametrize("invalid_snapshot", [[], "ungueltig", 1])
def test_choice_snapshot_lehnt_nicht_mapping_fail_closed_ab(invalid_snapshot):
    with pytest.raises(ValueError, match="candidate_choice_snapshot"):
        pl.generate_playlist_result(
            [],
            "Warm-Up",
            scoring_context={},
            candidate_choice_snapshot=invalid_snapshot,
        )


def test_ungeplante_kante_bleibt_mit_n_minus_eins_empfehlung_sichtbar(monkeypatch):
    _identity_strategy(monkeypatch)
    tracks = [_track("a.wav"), _track("b.wav"), _track("c.wav")]
    saved_without_match = candidate_choices.schluessel("a.wav", "b.wav")
    monkeypatch.setattr(
        candidate_choices, "snapshot", lambda: {saved_without_match: {"x": 1}}
    )
    calls = 0

    def rank(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return []
        return [_candidate(180.0, 80.0)]

    monkeypatch.setattr(pc, "rank_pair_candidates", rank)

    result = pl.generate_playlist_result(
        tracks, "Warm-Up", scoring_context={}
    )

    assert len(result.boundaries) == len(result.recommendations) == 2
    first = result.boundaries[0]
    assert first.selected is None and first.consistent is False
    assert first.snapshots == ()
    assert first.metrics.overall_score == 0.0
    assert first.metrics.harmonic_score == 0
    assert first.metrics.bpm_smoothness == 0.0
    assert first.metrics.energy_flow == 0.0
    assert first.metrics.kandidat is None
    assert first.recommendation.plan is None
    assert first.recommendation.compatibility_score == 0
    assert first.recommendation.active_candidate_key is None
    assert first.recommendation.candidate_consistent is False
    assert "UNGEPLANT" in first.recommendation.notes
    assert result.boundaries[1].consistent is True
    expected_quality = (
        round(result.boundaries[1].metrics.overall_score * 100) / 2 / 100.0
    )
    assert result.quality_dict()["overall_score"] == pytest.approx(expected_quality)
    assert result.graph_stats.saved_present == 1
    assert result.path_stats.saved_present == 1
    assert result.path_stats.saved_honored == 0
    assert result.path_stats.planned + result.path_stats.unplanned == 2
    assert result.path_stats.segments == 1


def test_graph_stats_bilanzieren_ungueltige_bpm_exakt(monkeypatch):
    _identity_strategy(monkeypatch)
    tracks = [
        _track("valid.wav"),
        _track("zero.wav", bpm=0.0),
        _track("nan.wav", bpm=float("nan")),
    ]
    monkeypatch.setattr(candidate_choices, "snapshot", lambda: {})
    monkeypatch.setattr(
        pc,
        "rank_pair_candidates",
        lambda *args, **kwargs: pytest.fail("Nur ein valider Track hat keine Kante"),
    )

    result = pl.generate_playlist_result(
        tracks, "Warm-Up", scoring_context={}
    )

    assert result.graph_stats.input_tracks == 3
    assert result.graph_stats.valid_tracks == len(result.tracks) == len(result.occurrences) == 1
    assert result.graph_stats.invalid_bpm_excluded == 2
    assert result.graph_stats.input_tracks == (
        result.graph_stats.valid_tracks + result.graph_stats.invalid_bpm_excluded
    )
    assert result.path_stats.boundaries_total == 0


@pytest.mark.parametrize(
    "value",
    [True, False, None, "3", float("nan"), float("inf"), -0.1],
)
def test_generate_result_verwirft_ungueltige_bpm_toleranz(monkeypatch, value):
    monkeypatch.setattr(candidate_choices, "snapshot", lambda: pytest.fail("Kein Snapshot nach ungueltigem API-Wert"))

    with pytest.raises(ValueError, match="bpm_tolerance"):
        pl.generate_playlist_result([], "Warm-Up", bpm_tolerance=value, scoring_context={})


@pytest.mark.parametrize(
    "advanced_params",
    [
        [],
        {"ai_enabled": False},
        {"unbekannt": 1},
        {"energy_direction": True},
        {"energy_direction": "Seitwaerts"},
        {"peak_position": True},
        {"peak_position": 39},
        {"peak_position": 81},
        {"harmonic_strictness": 1.0},
        {"harmonic_strictness": 0},
        {"harmonic_strictness": 11},
        {"allow_experimental": 1},
        {"genre_mixing": "ja"},
        {"genre_weight": True},
        {"genre_weight": float("nan")},
        {"genre_weight": -0.01},
        {"genre_weight": 1.01},
        {"target_energy": True},
        {"target_energy": float("inf")},
        {"target_energy": -0.01},
        {"target_energy": 100.01},
        {"overlap": 16},
    ],
)
def test_generate_result_verwirft_ungueltige_advanced_params_vor_seiteneffekten(
    monkeypatch, advanced_params
):
    monkeypatch.setattr(
        candidate_choices,
        "snapshot",
        lambda: pytest.fail("Kein Snapshot nach ungueltigen Parametern"),
    )
    monkeypatch.setattr(
        pl,
        "key_to_camelot",
        lambda *_args: pytest.fail("Keine Trackmutation nach ungueltigen Parametern"),
    )

    with pytest.raises(ValueError, match="advanced_params"):
        pl.generate_playlist_result(
            [_track("a.wav")],
            "Warm-Up",
            advanced_params=advanced_params,
            scoring_context={},
        )


@pytest.mark.parametrize("bpm_tolerance", [0, 3, 6.0, 15, 100])
def test_generate_result_akzeptiert_gueltige_bpm_toleranzen(
    monkeypatch, bpm_tolerance
):
    monkeypatch.setattr(candidate_choices, "snapshot", lambda: {})
    result = pl.generate_playlist_result(
        [], "Warm-Up", bpm_tolerance=bpm_tolerance, scoring_context={}
    )
    assert result.bpm_tolerance == float(bpm_tolerance)


@pytest.mark.parametrize(
    "advanced_params",
    [
        None,
        {},
        {
            "energy_direction": "Build Up",
            "peak_position": 40,
            "harmonic_strictness": 1,
            "allow_experimental": False,
            "genre_mixing": True,
            "genre_weight": 0,
            "target_energy": None,
        },
        {
            "energy_direction": "maintain",
            "peak_position": 80,
            "harmonic_strictness": 10,
            "allow_experimental": True,
            "genre_mixing": False,
            "genre_weight": 1,
            "target_energy": 100,
        },
    ],
)
def test_generate_result_akzeptiert_advanced_parametergrenzen(
    monkeypatch, advanced_params
):
    monkeypatch.setattr(candidate_choices, "snapshot", lambda: {})
    result = pl.generate_playlist_result(
        [], "Context Flow", advanced_params=advanced_params, scoring_context={}
    )
    assert result.mode == "Context Flow"
    assert "overlap" not in result.scoring_context


@pytest.mark.parametrize("mode", [None, True, 7, object(), "", " ", "Unbekannt"])
def test_generate_result_verwirft_ungueltige_strategie_vor_seiteneffekten(
    monkeypatch, mode
):
    monkeypatch.setattr(
        candidate_choices,
        "snapshot",
        lambda: pytest.fail("Kein Snapshot nach ungueltigem Modus"),
    )
    monkeypatch.setattr(
        pl,
        "key_to_camelot",
        lambda *args: pytest.fail("Keine Trackmutation nach ungueltigem Modus"),
    )

    with pytest.raises(ValueError, match="Playlist-Strategie|mode"):
        pl.generate_playlist_result(
            [_track("a.wav")], mode, scoring_context={}
        )


def test_generate_playlist_propagiert_ungueltige_strategie():
    with pytest.raises(ValueError, match="Playlist-Strategie"):
        pl.generate_playlist([], "Unbekannt", scoring_context={})


@pytest.mark.parametrize("mode", tuple(pl.STRATEGIES))
def test_generate_result_speichert_jede_kanonische_strategie(monkeypatch, mode):
    monkeypatch.setattr(candidate_choices, "snapshot", lambda: {})
    calls = []
    monkeypatch.setitem(
        pl.STRATEGIES,
        mode,
        lambda items, bpm_tolerance, **kwargs: calls.append(mode) or list(items),
    )

    result = pl.generate_playlist_result(
        [_track("a.wav")], mode, scoring_context={}
    )

    assert calls == [mode]
    assert result.mode == mode


@pytest.mark.parametrize("alias, canonical", tuple(pl.STRATEGY_ALIASES.items()))
def test_generate_result_alias_nutzt_und_speichert_kanonischen_modus(
    monkeypatch, alias, canonical
):
    monkeypatch.setattr(candidate_choices, "snapshot", lambda: {})
    calls = []
    monkeypatch.setitem(
        pl.STRATEGIES,
        canonical,
        lambda items, bpm_tolerance, **kwargs: calls.append(canonical) or list(items),
    )

    result = pl.generate_playlist_result(
        [_track("a.wav")], alias, scoring_context={}
    )

    assert calls == [canonical]
    assert result.mode == canonical


def test_oeffentliche_playlist_bpm_defaults_nutzen_paar_gate():
    for funktion in (
        pl.compute_transition_recommendations,
        pl.generate_playlist_result,
        pl.generate_playlist,
    ):
        default = inspect.signature(funktion).parameters["bpm_tolerance"].default
        assert default == PAAR_BPM_MAX == 2.0

    overlap_default = inspect.signature(
        pl.compute_transition_recommendations
    ).parameters["default_overlap"].default
    assert overlap_default == 12.0


@pytest.mark.parametrize("key", ["nested", 7])
def test_scoring_context_verwirft_unbekannte_top_level_keys(key):
    with pytest.raises(ValueError, match="unbekannte Schluessel"):
        pl._complete_run_scoring_context(
            "Warm-Up", {}, {key: {"weights": [0.2, 0.8]}}
        )


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("energy_direction", None),
        ("energy_direction", "Sideways"),
        ("harmonic_strictness", True),
        ("harmonic_strictness", "7"),
        ("harmonic_strictness", 0),
        ("harmonic_strictness", 11),
        ("allow_experimental", "false"),
        ("allow_experimental", 1),
        ("target_energy", True),
        ("target_energy", float("nan")),
        ("target_energy", -0.1),
        ("target_energy", 100.1),
    ],
)
def test_scoring_context_verwirft_falsche_strategy_config_werte(key, value):
    with pytest.raises(ValueError, match=key):
        pl._complete_run_scoring_context("Context Flow", {}, {key: value})


def test_scoring_context_akzeptiert_typisierte_strategy_config_werte():
    supplied = {
        "energy_direction": "Build Up",
        "harmonic_strictness": 9,
        "allow_experimental": False,
        "target_energy": 75,
    }

    context = pl._complete_run_scoring_context("Context Flow", {}, supplied)

    assert context["energy_direction"] == "Build Up"
    assert context["harmonic_strictness"] == 9
    assert context["allow_experimental"] is False
    assert context["target_energy"] == 75.0
    assert "overlap" not in context


def test_scoring_context_verwirft_wirkungslosen_overlap_parameter():
    with pytest.raises(ValueError, match="unbekannte Schluessel.*overlap"):
        pl._complete_run_scoring_context(
            "Context Flow", {}, {"overlap": 16}
        )


def test_transitionsempfehlung_verwirft_overlap_im_scoring_context():
    with pytest.raises(ValueError, match="unbekannten Schluessel.*overlap"):
        pl.compute_transition_recommendations(
            [],
            scoring_context={"overlap": 16},
        )


def test_scoring_context_verwirft_strategy_fremde_skalare_werte():
    with pytest.raises(ValueError, match="Warm-Up.*harmonic_strictness"):
        pl._complete_run_scoring_context(
            "Warm-Up", {}, {"harmonic_strictness": 1}
        )


@pytest.mark.parametrize(
    "value",
    ["Auto", "Build Up", "Cool Down", "Maintain", "auto", "up", "down", "maintain"],
)
def test_scoring_context_akzeptiert_alle_unterstuetzten_energy_directions(value):
    context = pl._complete_run_scoring_context(
        "Context Flow", {}, {"energy_direction": value}
    )
    assert context["energy_direction"] == value


def test_dp_priorisiert_wahl_vor_score_und_tiebreakt_kleineren_key():
    tracks = (_track("a.wav"), _track("b.wav"))
    occurrences = tuple(
        pl.TrackOccurrence("run", index, track)
        for index, track in enumerate(tracks)
    )
    high = pc.CandidateSnapshot.from_pair_candidate(
        _candidate(140.0, 70.0, score=0.99, rank=1), original_ordinal=0
    )
    saved = pc.CandidateSnapshot.from_pair_candidate(
        _candidate(160.0, 70.0, score=0.10, saved=True, rank=2),
        original_ordinal=1,
    )

    selected, consistent, checks, passed, states = pl._select_snapshot_path(
        ((high, saved),), occurrences
    )

    assert selected == (saved,)
    assert consistent == (True,)
    assert checks == passed == 0
    assert states == 3

    left = replace(high, score=0.5)
    right_candidate = _candidate(150.0, 70.0, score=0.5, rank=2)
    right = pc.CandidateSnapshot.from_pair_candidate(
        right_candidate, original_ordinal=1
    )
    selected, *_ = pl._select_snapshot_path(((right, left),), occurrences)
    assert selected == (min((left, right), key=lambda item: item.key),)


def test_result_score_folgt_dp_wahl_rang_zwei_bei_getrenntem_ordering(monkeypatch):
    _identity_strategy(monkeypatch)
    tracks = [_track("a.wav"), _track("b.wav")]
    rank_one = _candidate(140.0, 70.0, score=0.9, rank=1)
    rank_two_base = _candidate(180.0, 80.0, score=0.1, saved=True, rank=2)
    rank_two = replace(
        rank_two_base,
        out_a=replace(rank_two_base.out_a, energy_lokal=0.0),
        in_b=replace(rank_two_base.in_b, energy_lokal=100.0),
    )
    tracks[0].mix_out_candidates = [rank_one.out_a, rank_two.out_a]
    tracks[1].mix_in_candidates = [rank_one.in_b, rank_two.in_b]
    monkeypatch.setattr(candidate_choices, "snapshot", lambda: {})
    monkeypatch.setattr(
        pc, "rank_pair_candidates", lambda *args, **kwargs: [rank_one, rank_two]
    )

    result = pl.generate_playlist_result(
        tracks, "Warm-Up", scoring_context={}, candidate_choice_snapshot={}
    )
    context = result.scoring_context_dict()
    ordering_score = pl._calculate_track_edge_metrics(
        tracks[0], tracks[1], result.bpm_tolerance, None, context, rank_one
    )
    selected_score = pl._calculate_track_edge_metrics(
        tracks[0], tracks[1], result.bpm_tolerance, None, context, rank_two
    )

    boundary = result.boundaries[0]
    assert boundary.selected.key == boundary.snapshots[1].key
    assert boundary.recommendation.plan.mix_out_a == rank_two.out_a.t
    assert boundary.metrics.kandidat.key == boundary.selected.key
    assert boundary.metrics.overall_score == pytest.approx(selected_score.overall_score)
    assert boundary.metrics.overall_score != pytest.approx(ordering_score.overall_score)
    assert boundary.recommendation.compatibility_score == round(
        selected_score.overall_score * 100
    )
    assert result.quality_dict()["overall_score"] == pytest.approx(
        round(selected_score.overall_score * 100) / 100.0
    )
    ordering_metrics = pl.calculate_enhanced_compatibility(
        tracks[0], tracks[1], result.bpm_tolerance, **context
    )
    assert ordering_metrics.kandidat["rang"] == 1
    assert ordering_metrics.kandidat["t_out"] == rank_one.out_a.t
    assert ordering_metrics.overall_score == pytest.approx(ordering_score.overall_score)


@pytest.mark.parametrize("strategy", tuple(pl.STRATEGIES.values()))
def test_alle_strategien_pruefen_cancel_check_am_einstieg(strategy):
    with pytest.raises(InterruptedError, match="Playlist-Generierung abgebrochen"):
        strategy([_track("a.wav"), _track("b.wav")], 2.0, cancel_check=lambda: True)


def test_boundary_ranking_bricht_vor_naechstem_teilergebnis_ab(monkeypatch):
    occurrences = tuple(
        pl.TrackOccurrence("run", index, _track(f"{index}.wav"))
        for index in range(3)
    )
    calls = 0

    def cancel_check():
        nonlocal calls
        calls += 1
        return calls >= 3

    ranking_calls = 0

    def rank(*args, **kwargs):
        nonlocal ranking_calls
        ranking_calls += 1
        return []

    monkeypatch.setattr(pc, "rank_pair_candidates", rank)

    with pytest.raises(InterruptedError, match="Playlist-Generierung abgebrochen"):
        pl._rank_fixed_boundaries(
            occurrences,
            2.0,
            pl.resolve_run_scoring_context("Warm-Up", {}),
            {},
            cancel_check,
        )
    assert ranking_calls == 1


def test_dp_zaehlt_exakt_144_links_und_behaelt_geplante_inkonsistenz():
    tracks = (_track("a.wav"), _track("b.wav"), _track("c.wav"))
    occurrences = tuple(
        pl.TrackOccurrence("run", index, track)
        for index, track in enumerate(tracks)
    )
    first = tuple(
        pc.CandidateSnapshot.from_pair_candidate(
            _candidate(120.0 + ordinal, 100.0, score=0.5),
            original_ordinal=ordinal,
        )
        for ordinal in range(12)
    )
    second = tuple(
        pc.CandidateSnapshot.from_pair_candidate(
            _candidate(130.0 + ordinal, 70.0, score=0.5),
            original_ordinal=ordinal,
        )
        for ordinal in range(12)
    )

    selected, consistent, checks, passed, states = pl._select_snapshot_path(
        (first, second), occurrences
    )

    assert all(item is not None for item in selected)
    assert consistent == (True, False)
    assert checks == 144
    assert passed == 0
    assert states == 26
    assert checks <= 144 * (2 - 1)


def test_dp_trennt_dag_link_checks_von_links_des_gewinnerpfads():
    tracks = (_track("a.wav"), _track("b.wav"), _track("c.wav"))
    occurrences = tuple(
        pl.TrackOccurrence("run", index, track)
        for index, track in enumerate(tracks)
    )
    first = tuple(
        pc.CandidateSnapshot.from_pair_candidate(
            _candidate(120.0 + ordinal, 70.0, score=0.5),
            original_ordinal=ordinal,
        )
        for ordinal in range(2)
    )
    second = tuple(
        pc.CandidateSnapshot.from_pair_candidate(
            _candidate(150.0 + ordinal, 80.0, score=0.5),
            original_ordinal=ordinal,
        )
        for ordinal in range(2)
    )

    selected, consistent, checks, path_links, states = pl._select_snapshot_path(
        (first, second), occurrences
    )

    assert all(item is not None for item in selected)
    assert consistent == (True, True)
    assert checks == 4
    assert path_links == 1
    assert path_links <= len(selected) - 1
    assert states == 6


def test_occurrence_ids_unterscheiden_dieselbe_trackinstanz(monkeypatch):
    _identity_strategy(monkeypatch)
    track = _track("same.wav")
    monkeypatch.setattr(candidate_choices, "snapshot", lambda: {})
    monkeypatch.setattr(pc, "rank_pair_candidates", lambda *args, **kwargs: [])

    result = pl.generate_playlist_result(
        [track, track, track], "Warm-Up", scoring_context={}
    )

    assert result.tracks == (track, track, track)
    ids = tuple(item.occurrence_id for item in result.occurrences)
    assert len(set(ids)) == 3
    assert tuple(item.ordinal for item in result.occurrences) == (0, 1, 2)
    assert len(result.boundaries) == 2


def test_rebuild_akzeptiert_nur_exakte_permutation_und_ruft_keine_strategie(
    monkeypatch,
):
    _identity_strategy(monkeypatch)
    tracks = [_track("a.wav"), _track("b.wav"), _track("c.wav")]
    monkeypatch.setattr(candidate_choices, "snapshot", lambda: {})
    monkeypatch.setattr(pc, "rank_pair_candidates", lambda *args, **kwargs: [])
    original = pl.generate_playlist_result(
        tracks, "Warm-Up", scoring_context={}
    )
    requested = tuple(
        item.occurrence_id for item in reversed(original.occurrences)
    )
    monkeypatch.setitem(
        pl.STRATEGIES,
        "Warm-Up",
        lambda *args, **kwargs: pytest.fail("Rebuild darf keine Strategie ausfuehren"),
    )
    rank_calls = 0

    def rank(*args, **kwargs):
        nonlocal rank_calls
        rank_calls += 1
        assert kwargs["wahl"] == {}
        return []

    monkeypatch.setattr(pc, "rank_pair_candidates", rank)

    rebuilt = pl.rebuild_result_for_order(
        original, requested, choice_snapshot={}
    )

    assert rebuilt.run_id == original.run_id
    assert tuple(item.occurrence_id for item in rebuilt.occurrences) == requested
    assert rebuilt.tracks == tuple(reversed(original.tracks))
    assert rank_calls == 2
    with pytest.raises(ValueError, match="exakte Occurrence-ID-Permutation"):
        pl.rebuild_result_for_order(original, requested[:-1], choice_snapshot={})
    with pytest.raises(ValueError, match="Duplikate"):
        pl.rebuild_result_for_order(
            original,
            (requested[0], requested[0], requested[2]),
            choice_snapshot={},
        )


def test_rebuild_ohne_override_nutzt_result_snapshot_und_nie_live_store(
    monkeypatch,
):
    _identity_strategy(monkeypatch)
    tracks = [_track("a.wav"), _track("b.wav")]
    key = candidate_choices.schluessel("a.wav", "b.wav")
    supplied = {key: {"marker": "result-snapshot"}}
    seen = []

    def rank(*_args, **kwargs):
        seen.append(kwargs["wahl"])
        return [_candidate(150.0, 70.0, saved=True)]

    monkeypatch.setattr(pc, "rank_pair_candidates", rank)
    original = pl.generate_playlist_result(
        tracks,
        "Warm-Up",
        scoring_context={},
        candidate_choice_snapshot=supplied,
    )
    monkeypatch.setattr(
        candidate_choices,
        "snapshot",
        lambda: pytest.fail("Rebuild darf den Live-Store nie lesen"),
    )

    rebuilt = pl.rebuild_result_for_order(
        original, tuple(item.occurrence_id for item in original.occurrences)
    )

    assert seen == [
        {"marker": "result-snapshot"},
        {"marker": "result-snapshot"},
    ]
    assert rebuilt.candidate_choice_snapshot_dict() == supplied


def test_generate_playlist_bleibt_reiner_listen_wrapper(monkeypatch):
    expected = [_track("a.wav"), _track("b.wav")]
    sentinel = object()
    monkeypatch.setattr(
        pl,
        "generate_playlist_result",
        lambda *args, **kwargs: type("R", (), {"tracks": tuple(expected), "x": sentinel})(),
    )

    result = pl.generate_playlist(expected, "Warm-Up")

    assert isinstance(result, list)
    assert result == expected
