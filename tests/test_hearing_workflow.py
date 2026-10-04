"""Native Vorbereitung hat genau eine Publikationsgrenze."""
import csv
from pathlib import Path

import pytest

from hpg_core.hearing_workflow import (
    CancellationToken, HearingCancelledError, HearingOperationError,
    HearingTargetExistsError, HearingValidationError, PrepareConfig, create_set,
)
from hpg_core.transition_renderer import TransitionClipSpec


def producer_for(source_a, source_b):
    def produce(args):
        from tools import rate_transitions as rt
        args.hpg_progress("prepare", 0, 1)
        args.hpg_render_sink(TransitionClipSpec(str(source_a), str(source_b), 20., 0., 8.),
                             args.out / "clips/001.wav")
        columns = ("pair_id", *rt.ALLE_FAKTOREN, "crossfade_sek", *rt.ZUSATZ_SPALTEN,
                   *rt.PLAN_AUDIT_SPALTEN, "track_a", "track_b")
        row = dict.fromkeys(columns, "0")
        row.update(pair_id="001", track_a=str(source_a), track_b=str(source_b),
                   crossfade_sek="8", plan_mix_out_sec="20", plan_mix_in_sec="0",
                   plan_overlap_sec="8", plan_transition_type="smooth_blend",
                   plan_target_sr="44100", kandidat_rang="1", bpm_toleranz="2",
                   energy_direction="auto")
        rt.schreibe_csv(args.out / "merkmale.csv", columns, [row])
        rt.schreibe_csv(args.out / "bewertung.csv", ("pair_id", "clip", "bewertung"),
                       [{"pair_id": "001", "clip": "clips/001.wav", "bewertung": ""}])
        args.hpg_progress("prepare", 1, 1)
        return 0
    return produce


@pytest.fixture
def config_fixture(tmp_path, monkeypatch):
    from tools import rate_transitions as rt
    sources = tmp_path / "sources"
    sources.mkdir()
    a, b = sources / "a.wav", sources / "b.mp3"
    a.write_bytes(b"source A")
    b.write_bytes(b"source B")
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"cache fixture")
    monkeypatch.setattr(rt, "_befehl_prepare_intern", producer_for(a, b))
    return PrepareConfig("einzel", tmp_path / "result", cache, count=1, source_roots=(sources,))


def test_create_set_publishes_prepared_virtual_counts(config_fixture):
    updates = []
    result = create_set(config_fixture, progress=updates.append)
    assert result.status == "prepared"
    assert result.mode == "einzel"
    assert result.clip_count == result.pair_count == 1
    assert result.manifest_path.is_file()
    assert result.source_roots == config_fixture.source_roots
    assert not list(result.output_dir.rglob("*.wav"))
    assert not list(result.output_dir.parent.glob(".result.staging-*"))
    assert updates[-1].phase == "prepared"


@pytest.mark.parametrize("field,value", [("count", True), ("count", 0),
    ("workers", 5), ("bpm_tolerance", float("nan")), ("allow_experimental", 1),
    ("max_versions_per_pair", 6), ("harmonic_strictness", 11), ("seed", False),
    ("storage", "wav"), ("energy_direction", "invalid"), ("three_notes", True),
    ("source_roots", ())])
def test_config_rejects_invalid_values_before_staging(config_fixture, field, value):
    from dataclasses import replace
    with pytest.raises(HearingValidationError):
        create_set(replace(config_fixture, **{field: value}))
    assert not config_fixture.output_dir.exists()
    assert not list(config_fixture.output_dir.parent.glob(".result.staging-*"))


def test_existing_target_is_untouched(config_fixture):
    config_fixture.output_dir.mkdir()
    marker = config_fixture.output_dir / "user.txt"
    marker.write_bytes(b"preserve")
    with pytest.raises(HearingTargetExistsError):
        create_set(config_fixture)
    assert marker.read_bytes() == b"preserve"


def test_cancel_before_publish_removes_only_owned_staging(config_fixture, monkeypatch):
    from tools import rate_transitions as rt
    token = CancellationToken()
    producer = rt._befehl_prepare_intern
    def cancel_after(args):
        status = producer(args)
        token.request_cancel()
        return status
    monkeypatch.setattr(rt, "_befehl_prepare_intern", cancel_after)
    with pytest.raises(HearingCancelledError):
        create_set(config_fixture, cancel=token)
    assert not config_fixture.output_dir.exists()
    assert not list(config_fixture.output_dir.parent.glob(".result.staging-*"))
    assert (config_fixture.source_roots[0] / "a.wav").read_bytes() == b"source A"


def test_publish_state_rejects_cancel_and_publishes_once(config_fixture, monkeypatch):
    from tools import rate_transitions as rt
    token = CancellationToken()
    original = rt._publiziere_staging
    calls = []
    def publish(stage, target):
        calls.append((stage, target))
        assert not token.request_cancel()
        original(stage, target)
    monkeypatch.setattr(rt, "_publiziere_staging", publish)
    create_set(config_fixture, cancel=token)
    assert len(calls) == 1
    assert token.state == "complete"


def test_partial_producer_aborts_whole_set(config_fixture, monkeypatch):
    from tools import rate_transitions as rt
    producer = rt._befehl_prepare_intern
    def partial(args):
        producer(args)
        return 1
    monkeypatch.setattr(rt, "_befehl_prepare_intern", partial)
    with pytest.raises(HearingOperationError):
        create_set(config_fixture)
    assert not config_fixture.output_dir.exists()
    assert not list(config_fixture.output_dir.parent.glob(".result.staging-*"))


def test_interrupted_error_is_controlled_cancellation(config_fixture, monkeypatch):
    from tools import rate_transitions as rt
    def interrupted(args):
        raise InterruptedError("cancel")
    monkeypatch.setattr(rt, "_befehl_prepare_intern", interrupted)
    with pytest.raises(HearingCancelledError):
        create_set(config_fixture)
    assert not config_fixture.output_dir.exists()


@pytest.mark.parametrize("mode,three_notes", [("einzel", False), ("kandidaten", False), ("kandidaten", True)])
def test_service_uses_real_internal_producers_with_source_sink(tmp_path, monkeypatch, mode, three_notes):
    from types import SimpleNamespace
    from tools import rate_transitions as rt
    from tests.test_audit_candidate_set import _candidate
    from hpg_core.models import Track
    from hpg_core.playlist import TransitionPlan
    sources = tmp_path / "originals"
    sources.mkdir()
    paths = [sources / "a.wav", sources / "b.mp3"]
    for path in paths:
        path.write_bytes(b"synthetic original; no decode required")
    tracks = [Track(str(p), p.name, duration=100., bpm=120., detected_genre="Psytrance",
                    camelotCode="8A", analysis_mode="librosa_full_or_tail") for p in paths]
    candidate = _candidate()
    candidate.rang = 1
    candidate.out_a.lufs_lokal = -14.
    candidate.in_b.lufs_lokal = -14.
    pair = {"track_a": tracks[0], "track_b": tracks[1], "merkmale": candidate.teilwerte,
            "pair_candidates": [candidate]}
    monkeypatch.setattr(rt, "lade_tracks_aus_cache", lambda *_: tracks)
    monkeypatch.setattr(rt, "sammle_kandidaten", lambda *_a, **_kw: [pair])
    monkeypatch.setattr(rt, "sammle_kandidaten_parallel", lambda *_a, **_kw: [pair])
    plan = TransitionPlan(10., 12., 10., 26., 16., "pro_eq_swap")
    monkeypatch.setattr(rt, "compute_transition_recommendations", lambda *_a, **_kw: [SimpleNamespace(
        index=0, from_track=tracks[0], to_track=tracks[1], plan=plan,
        kandidat_aktiv=1, kandidaten=[candidate.to_dict()])])
    def forbidden(*_args, **_kwargs):
        pytest.fail("Quellmodus darf weder rendern noch CLI-Wrapper aufrufen")
    monkeypatch.setattr(rt, "_rendere_atomar", forbidden)
    monkeypatch.setattr(rt, "_prepare_atomar", forbidden)
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"isolated fingerprint fixture")
    options = {"three_notes": three_notes}
    if mode == "kandidaten":
        options["max_versions_per_pair"] = 1
    config = PrepareConfig(mode, tmp_path / "set", cache, count=1, source_roots=(sources,), **options)
    result = create_set(config)
    assert result.status == "prepared"
    assert result.clip_count == result.pair_count == 1
    assert not list(result.output_dir.rglob("*.wav"))
    assert all(p.read_bytes() == b"synthetic original; no decode required" for p in paths)


def test_namespace_has_exact_ui_to_parser_mapping(config_fixture):
    from dataclasses import replace
    from hpg_core.hearing_sources import SourceRenderSink
    from hpg_core.hearing_workflow import _producer_namespace
    config = replace(config_fixture, mode="kandidaten", count=7, seed=42,
                     bpm_tolerance=1.5, energy_direction="down", harmonic_strictness=4,
                     allow_experimental=False, only_genre="Psytrance", max_versions_per_pair=3,
                     three_notes=True, tracks_once=True, workers=2, transition_type_mode="produktion")
    stage = config.output_dir.parent / "staging"
    stage.mkdir()
    sink = SourceRenderSink(stage, config.source_roots)
    args = _producer_namespace(config, stage, config.output_dir, sink, CancellationToken(), None)
    assert vars(args) | {} == {
        "modus": "kandidaten", "out": stage, "anzeige_out": config.output_dir, "cache": str(config.cache),
        "anzahl": 7, "bpm_toleranz": 1.5, "energy_direction": "down", "harmonic_strictness": 4,
        "allow_experimental": False, "seed": 42, "nur_genre": "Psytrance", "sequenz_tracks": 16,
        "uebergaenge_pro_variante": 5, "max_versionen_pro_paar": 3, "dreinoten_pilot": True,
        "tracks_einmalig": True, "auswahlprofil": None, "workers": 2, "transition_type_mode": "produktion",
        "storage": "source_refs", "source_roots": sink.source_roots, "hpg_render_sink": sink.emit,
        "hpg_cancel": args.hpg_cancel, "hpg_progress": args.hpg_progress,
    }


def test_swallowed_sink_failure_never_publishes(config_fixture, monkeypatch):
    from tools import rate_transitions as rt
    producer = rt._befehl_prepare_intern
    def swallowed(args):
        producer(args)
        try:
            args.hpg_render_sink(TransitionClipSpec("relative.wav", "relative.mp3", 20., 0., 8.),
                                 args.out / "clips/002.wav")
        except ValueError:
            pass
        return 0
    monkeypatch.setattr(rt, "_befehl_prepare_intern", swallowed)
    with pytest.raises(HearingValidationError):
        create_set(config_fixture)
    assert not config_fixture.output_dir.exists()


def test_cache_mutation_prevents_publication(config_fixture, monkeypatch):
    from tools import rate_transitions as rt
    producer = rt._befehl_prepare_intern
    def changed(args):
        status = producer(args)
        config_fixture.cache.write_bytes(b"changed cache")
        return status
    monkeypatch.setattr(rt, "_befehl_prepare_intern", changed)
    with pytest.raises(HearingValidationError, match="Cache"):
        create_set(config_fixture)
    assert not config_fixture.output_dir.exists()


def test_service_uses_real_dramaturgy_producer_without_audio(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from tools import rate_transitions as rt
    from hpg_core.models import Track
    from hpg_core.playlist import TransitionPlan
    sources = tmp_path / "originals"
    sources.mkdir()
    tracks = []
    for i in range(12):
        path = sources / f"{i:02d}.wav"
        path.write_bytes(b"synthetic source")
        tracks.append(Track(str(path), path.name, duration=100., bpm=120., energy=i,
                            analysis_mode="librosa_full_or_tail"))
    monkeypatch.setattr(rt, "lade_tracks_aus_cache", lambda *_: tracks)
    def playlist(pool, strategy, **options):
        occurrences = [SimpleNamespace(occurrence_id=("fixture", i)) for i in range(len(pool))]
        recommendations = [SimpleNamespace(index=i,
            from_occurrence_id=occurrences[i].occurrence_id,
            to_occurrence_id=occurrences[i + 1].occurrence_id,
            plan=TransitionPlan(20., 0., 20., 28., 8., "smooth_blend")) for i in range(len(pool) - 1)]
        return SimpleNamespace(tracks=pool, recommendations=recommendations, occurrences=occurrences,
            scoring_context_dict=lambda: options["scoring_context"],
            candidate_choice_snapshot_dict=lambda: options["candidate_choice_snapshot"])
    monkeypatch.setattr(rt, "generate_playlist_result", playlist)
    def forbidden(*_args, **_kwargs):
        pytest.fail("Dramaturgie-Quellmodus darf weder WAV rendern noch alten WAV-Validator aufrufen")
    monkeypatch.setattr(rt, "_rendere_atomar", forbidden)
    monkeypatch.setattr(rt, "_validiere_dramaturgie_satz", forbidden)
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"isolated cache fingerprint")
    result = create_set(PrepareConfig("dramaturgie", tmp_path / "set", cache,
                                     sequence_tracks=12, transitions_per_variant=4, source_roots=(sources,)))
    assert result.status == "prepared"
    assert result.clip_count == 4 * len(rt.dramaturgie_varianten())
    assert not list(result.output_dir.rglob("*.wav"))


def test_progress_callback_error_cannot_publish(config_fixture):
    def fail(_update):
        raise RuntimeError("observer failure")
    with pytest.raises(HearingOperationError, match="observer failure"):
        create_set(config_fixture, progress=fail)
    assert not config_fixture.output_dir.exists()
    assert not list(config_fixture.output_dir.parent.glob(".result.staging-*"))


def test_source_change_in_final_progress_callback_cannot_publish(config_fixture):
    def change_source(update):
        if update.phase == "prepared":
            (config_fixture.source_roots[0] / "a.wav").write_bytes(b"source X")
    with pytest.raises(HearingValidationError):
        create_set(config_fixture, progress=change_source)
    assert not config_fixture.output_dir.exists()
