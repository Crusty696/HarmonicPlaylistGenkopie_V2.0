"""Tonarthinweise müssen die lokale Quelle des aktiven Paarplans erklären."""
import pytest

from hpg_core import candidate_choices, pair_candidates as pc, playlist as pl
from hpg_core.dj_brain import DJRecommendation
from hpg_core.mix_candidates import MixCandidate
from hpg_core.models import CAMELOT_MAP, Track
from hpg_core.transition_notes import bind_candidate_recommendation


POSITIONS = (
    (410.4346258503401, 139.13015873015874),
    (271.30419501133787, 83.47798185941043),
)
FACTORS = (
    "harmonic", "bpm", "energy", "genre", "groove", "bass", "timbre",
    "mood", "loudness", "structure",
)


def _track(name, code):
    track = Track(filePath=name, fileName=name)
    track.bpm = 138.0
    track.duration = 600.0
    # Der Result-Einstieg leitet Camelot erneut aus diesen Quellfeldern ab.
    # Die Fixture muss denselben konsistenten Tonartvertrag wie echte Tracks halten.
    track.keyNote, track.keyMode = next(
        key for key, camelot in CAMELOT_MAP.items() if camelot == code
    )
    track.camelotCode = code
    track.energy = 60
    track.detected_genre = "Psytrance"
    track.phrase_unit = 16
    track.first_downbeat = 0.0
    track.downbeat_confidence = 1.0
    track.outro_covered = True
    track.sections = [{"label": "main", "start_time": 0.0, "end_time": 600.0}]
    return track


def _candidate(t_out, t_in, codes=("6A", "6A")):
    out_a = MixCandidate(t=t_out, schema=["sektion"], camelot_lokal=codes[0],
                         key_confidence_lokal=0.6, energy_lokal=60.0, lufs_lokal=-10.0)
    in_b = MixCandidate(t=t_in, schema=["sektion"], camelot_lokal=codes[1],
                        key_confidence_lokal=0.6, energy_lokal=60.0, lufs_lokal=-10.0)
    factors = {name: 0.8 for name in FACTORS}
    factors["harmonic"] = pc._teil_harmonie(
        out_a, in_b, harmonic_strictness=7, allow_experimental=True,
    )
    return pc.PairCandidate(out_a, in_b, blend_bars=16,
                            overlap_sec=16 * 240.0 / 138.0, score=0.8,
                            teilwerte=factors, rang=1)


def _dj_recommendation():
    return DJRecommendation(
        genre_pair="Psytrance -> Psytrance", genre_compatibility=1.0,
        mix_technique="Pro EQ Swap", eq_advice="", transition_bars=16,
        outgoing_section="main", incoming_section="main", structure_note="",
        key_advice="GLOBALER TONARTHINWEIS", bpm_advice="Tempo angleichen",
        risk_notes=["Tonart-Clash (Camelot-Distanz: 4) -- EQ/Filter nutzen",
                    "Bass-Kollision beachten"],
    )


@pytest.mark.parametrize("entrypoint", ["result", "legacy"])
@pytest.mark.parametrize("positions", POSITIONS)
@pytest.mark.parametrize("with_dj", [True, False])
def test_aktive_planposition_nutzt_lokale_tonart_in_beiden_einstiegen(
    monkeypatch, entrypoint, positions, with_dj,
):
    tracks = [_track("dream.wav", "6A"), _track("neural.wav", "10B")]
    candidate = _candidate(*positions)
    before = candidate.to_dict()
    monkeypatch.setitem(pl.STRATEGIES, "Warm-Up", lambda items, *a, **kw: list(items))
    monkeypatch.setattr(pc, "rank_pair_candidates", lambda *a, **kw: [candidate])
    monkeypatch.setattr(pl, "_kandidaten_fuer_paar", lambda *a, **kw: [candidate])
    monkeypatch.setattr(candidate_choices, "snapshot", lambda: {})
    monkeypatch.setattr(pl, "generate_dj_recommendation",
                        lambda *a: _dj_recommendation() if with_dj else None)

    if entrypoint == "result":
        result = pl.generate_playlist_result(tracks, "Warm-Up", 2.0)
        rec = pl.legacy_transition_recommendations(result)[0]
    else:
        rec = pl.compute_transition_recommendations(tracks, 2.0)[0]

    assert (rec.plan.mix_out_a, rec.plan.mix_in_b) == positions
    assert "Lokale Tonarten (Mix-Out/Mix-In): 6A -> 6A" in rec.notes
    assert "Messkonfidenz: 0,6 / 0,6" in rec.notes
    assert "Trackweite Tonarten: 6A -> 10B" in rec.notes
    assert "Tonart-Clash" not in rec.notes
    assert "Perfekte Tonart" not in rec.notes
    assert "GLOBALER TONARTHINWEIS" not in rec.notes
    if with_dj:
        assert "Bass-Kollision beachten" in rec.notes
        assert "Tempo angleichen" in rec.notes
        assert "Struktur: main -> main" in rec.notes
    assert candidate.to_dict() == before
    assert candidate.teilwerte["harmonic"] == 1.0
    assert [track.camelotCode for track in tracks] == ["6A", "10B"]


def test_lokaler_konflikt_bleibt_trotz_gleicher_tracktonarten_sichtbar():
    tracks = [_track("a.wav", "6A"), _track("b.wav", "6A")]
    candidate = _candidate(*POSITIONS[0], codes=("6A", "10B"))
    recommendation = _dj_recommendation()
    bind_candidate_recommendation(recommendation, *tracks, candidate, "pro_eq_swap")

    assert "Lokale Tonarten (Mix-Out/Mix-In): 6A -> 10B" in recommendation.key_advice
    assert "Lokale Harmonie gering" in recommendation.key_advice
    assert "Trackweite Tonarten: 6A -> 6A" in recommendation.key_advice
    assert recommendation.risk_notes == ["Bass-Kollision beachten"]


@pytest.mark.parametrize("codes", [("", "6A"), ("6A", ""), ("", "")])
def test_fehlende_lokale_tonart_wird_nicht_durch_trackmetadaten_ersetzt(codes):
    tracks = [_track("a.wav", "6A"), _track("b.wav", "6A")]
    candidate = _candidate(*POSITIONS[0], codes=codes)
    recommendation = _dj_recommendation()
    bind_candidate_recommendation(recommendation, *tracks, candidate, "pro_eq_swap")

    assert "Lokale Tonart nicht vollständig bestimmt" in recommendation.key_advice
    assert "Trackweite Tonarten: 6A -> 6A" in recommendation.key_advice
    assert "Lokale Harmonie stark" not in recommendation.key_advice


def test_beschreibung_ohne_lokale_quelle_behauptet_keine_perfekte_tonart():
    tracks = [_track("a.wav", "6A"), _track("b.wav", "6A")]
    params = pl.TransitionDescriptionParams(
        compatibility_score=80, bpm_delta=0, bpm_tolerance=2, energy_delta=0,
        metrics=pl.TransitionMetrics(100, 1.0, 1.0, 1.0, 0.8),
        from_track=tracks[0], to_track=tracks[1],
    )
    text = pl._build_transition_description(params)
    assert "Lokale Tonart nicht vollständig bestimmt" in text
    assert "Perfekte Tonart" not in text


def test_fehlende_konfidenz_bleibt_unbekannt():
    tracks = [_track("a.wav", "6A"), _track("b.wav", "10B")]
    candidate = _candidate(*POSITIONS[1])
    candidate.in_b.key_confidence_lokal = None
    recommendation = _dj_recommendation()
    bind_candidate_recommendation(recommendation, *tracks, candidate, "pro_eq_swap")
    assert "Messkonfidenz: 0,6 / unbekannt" in recommendation.key_advice
