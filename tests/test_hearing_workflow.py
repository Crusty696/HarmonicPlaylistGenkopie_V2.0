"""Native Vorbereitung hat genau eine Publikationsgrenze."""
import csv
import hashlib
import json
from pathlib import Path

import pytest

from hpg_core.hearing_workflow import (
    CancellationToken, HearingCancelledError, HearingOperationError,
    HearingTargetExistsError, HearingValidationError, PrepareConfig, create_set,
)
from hpg_core.transition_renderer import TransitionClipSpec


def _normalize_source_manifest_for_golden(manifest, source_root):
    source_root = Path(source_root).resolve()
    normalized_specs = []
    for _, spec in sorted(manifest["specs"].items()):
        item = dict(spec)
        for key in ("track_a_path", "track_b_path"):
            item[key] = Path(item[key]).resolve().relative_to(source_root).as_posix()
        normalized_specs.append(item)
    normalized_sources = []
    for _, entry in sorted(
        manifest["sources"].items(), key=lambda pair: Path(pair[0]).name,
    ):
        item = dict(entry)
        item["path"] = Path(item["path"]).name
        item["root"] = "$SOURCE_ROOT"
        normalized_sources.append(item)
    return {
        "format": manifest["format"],
        "format_version": manifest["format_version"],
        "mode": manifest["mode"],
        "status": manifest["status"],
        "source_roots": ["$SOURCE_ROOT"],
        "specs": normalized_specs,
        "sources": normalized_sources,
        "immutable_metadata": {
            name: {"size": "$SIZE", "sha256": "$SHA256"}
            for name in manifest["immutable_metadata"]
        },
    }


def _canonical_manifest_sha256(manifest):
    raw = json.dumps(
        manifest, sort_keys=True, ensure_ascii=False, allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _csv_content_projection(directory, source_id_map, track_id_map):
    artifacts = {}
    for path in sorted(Path(directory).glob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = []
            for row in reader:
                rows.append({
                    key: source_id_map.get(value, track_id_map.get(value, value))
                    for key, value in row.items()
                })
            artifacts[path.name] = {"columns": reader.fieldnames, "rows": rows}
    return artifacts


def _normalize_candidate_manifest_for_golden(manifest):
    normalized = json.loads(json.dumps(manifest, allow_nan=False))
    normalized["algorithm_build"] = "$ALGORITHM_BUILD"
    for pair in normalized["pairs"]:
        pair["track_a"] = Path(pair["track_a"]).name
        pair["track_b"] = Path(pair["track_b"]).name
    return normalized


def _normalize_dramaturgy_manifest_for_golden(manifest, track_id_map):
    normalized = json.loads(json.dumps(manifest, allow_nan=False))
    normalized["algorithm_build"] = "$ALGORITHM_BUILD"
    normalized["cache"]["size"] = "$CACHE_SIZE"
    normalized["cache"]["sha256"] = "$CACHE_SHA256"
    normalized["ordered_pool_track_ids"] = [
        track_id_map[track_id] for track_id in normalized["ordered_pool_track_ids"]
    ]
    normalized["pool_hash"] = _canonical_manifest_sha256(normalized["ordered_pool_track_ids"])
    for variant in normalized["variants"]:
        variant["pool_hash"] = normalized["pool_hash"]
        variant["ordered_track_ids"] = [
            track_id_map[track_id] for track_id in variant["ordered_track_ids"]
        ]
        for transition in variant["transitions"]:
            transition["from_track_id"] = track_id_map[transition["from_track_id"]]
            transition["to_track_id"] = track_id_map[transition["to_track_id"]]
    return normalized


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


def test_cli_and_native_single_prepare_csv_artifacts_match(config_fixture, monkeypatch, tmp_path):
    """Compare wrapper artifacts with a fixed producer fixture, not real DSP."""
    from dataclasses import replace
    from hpg_core.hearing_calibration import validate_set
    from hpg_core.hearing_sources import SourceRenderSink, load_source_session
    from hpg_core.hearing_workflow import _producer_namespace
    from tools import rate_transitions as rt

    producer = producer_for(
        config_fixture.source_roots[0] / "a.wav",
        config_fixture.source_roots[0] / "b.mp3",
    )

    def render_or_reference(args):
        if args.hpg_render_sink is not None:
            return producer(args)
        def write_test_clip(_spec, destination):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"fixed deterministic test render")
        args.hpg_render_sink = write_test_clip
        try:
            return producer(args)
        finally:
            args.hpg_render_sink = None

    monkeypatch.setattr(rt, "_befehl_prepare_intern", render_or_reference)
    cli_config = replace(config_fixture, output_dir=tmp_path / "cli-set")
    cli_sink_root = tmp_path / "cli-sink"
    cli_sink_root.mkdir()
    cli_sink = SourceRenderSink(cli_sink_root, cli_config.source_roots)
    cli_args = _producer_namespace(
        cli_config, cli_config.output_dir, cli_config.output_dir,
        cli_sink, CancellationToken(), None, None,
    )
    cli_args.hpg_render_sink = None
    assert rt.befehl_prepare(cli_args) == 0
    gui_config = replace(config_fixture, output_dir=tmp_path / "gui-set")
    result = create_set(gui_config)

    assert result.status == "prepared"
    assert validate_set(cli_config.output_dir)
    assert load_source_session(gui_config.output_dir).pair_count == 1
    for name in ("merkmale.csv", "bewertung.csv"):
        assert (cli_config.output_dir / name).read_bytes() == (gui_config.output_dir / name).read_bytes()


@pytest.mark.artifact_contract
@pytest.mark.parametrize(
    ("mode", "three_notes"),
    (("einzel", False), ("kandidaten", False), ("kandidaten", True), ("dramaturgie", False)),
)
def test_real_internal_producer_artifacts_match_cli_and_native_service(
    tmp_path, monkeypatch, mode, three_notes,
):
    """Vergleicht echte Producer beider Einstiegspfade mit synthetischen Quellen."""
    import json
    import wave
    from dataclasses import replace
    from types import SimpleNamespace

    from hpg_core.hearing_sources import (
        SOURCE_MANIFEST_NAME, SourceRenderSink, load_source_session,
    )
    from hpg_core.hearing_workflow import _producer_namespace
    from hpg_core.models import Track
    from hpg_core.playlist import TransitionPlan
    from tools import rate_transitions as rt

    sources = tmp_path / "originals"
    sources.mkdir()
    track_count = 12 if mode == "dramaturgie" else 2
    tracks = []
    for index in range(track_count):
        path = sources / f"track-{index:02d}.wav"
        path.write_bytes(f"synthetic source {index}".encode())
        tracks.append(Track(
            str(path), path.name, duration=100., bpm=120., energy=float(index),
            detected_genre="Psytrance", camelotCode="8A",
            analysis_mode="librosa_full_or_tail",
        ))

    cache = tmp_path / "cache.db"
    cache.write_bytes(b"isolated cache fingerprint")
    monkeypatch.setattr(rt, "lade_tracks_aus_cache", lambda *_: tracks)

    if mode == "dramaturgie":
        track_id_map = {
            hashlib.sha256(
                rt._windows_pfadschluessel(str(sources / f"track-{index:02d}.wav")).encode("utf-8")
            ).hexdigest(): f"$TRACK_{index:02d}"
            for index in range(track_count)
        }
        def playlist(pool, strategy, **options):
            occurrences = [SimpleNamespace(occurrence_id=("fixture", i)) for i in range(len(pool))]
            recommendations = [SimpleNamespace(
                index=i,
                from_occurrence_id=occurrences[i].occurrence_id,
                to_occurrence_id=occurrences[i + 1].occurrence_id,
                plan=TransitionPlan(20., 0., 20., 28., 8., "smooth_blend"),
            ) for i in range(len(pool) - 1)]
            return SimpleNamespace(
                tracks=pool, recommendations=recommendations, occurrences=occurrences,
                scoring_context_dict=lambda: options["scoring_context"],
                candidate_choice_snapshot_dict=lambda: options["candidate_choice_snapshot"],
            )

        monkeypatch.setattr(rt, "generate_playlist_result", playlist)
        config = PrepareConfig(
            "dramaturgie", tmp_path / "native-set", cache, sequence_tracks=12,
            transitions_per_variant=4, source_roots=(sources,),
        )
    else:
        from tests.test_audit_candidate_set import _candidate

        candidate = _candidate()
        candidate.rang = 1
        candidate.out_a.lufs_lokal = -14.
        candidate.in_b.lufs_lokal = -14.
        pair = {
            "track_a": tracks[0], "track_b": tracks[1],
            "merkmale": candidate.teilwerte, "pair_candidates": [candidate],
        }
        monkeypatch.setattr(rt, "sammle_kandidaten", lambda *_a, **_kw: [pair])
        monkeypatch.setattr(rt, "sammle_kandidaten_parallel", lambda *_a, **_kw: [pair])
        if mode == "einzel":
            plan = TransitionPlan(10., 12., 10., 26., 16., "pro_eq_swap")
            recommendation = SimpleNamespace(
                index=0, from_track=tracks[0], to_track=tracks[1], plan=plan,
                kandidat_aktiv=1, kandidaten=[candidate.to_dict()],
            )
            monkeypatch.setattr(
                rt, "compute_transition_recommendations", lambda *_a, **_kw: [recommendation],
            )
        config = PrepareConfig(
            mode, tmp_path / "native-set", cache, count=1,
            max_versions_per_pair=1 if mode == "kandidaten" else 5,
            three_notes=three_notes, source_roots=(sources,),
        )

    def write_synthetic_clip(_spec, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(destination), "wb") as audio:
            audio.setnchannels(2)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(b"\0\0\0\0" * 800)

    monkeypatch.setattr(rt, "_rendere_atomar", write_synthetic_clip)

    native_result = create_set(config)
    assert native_result.status == "prepared"
    native_session = load_source_session(native_result.output_dir)
    native_manifest = json.loads(
        (native_result.output_dir / SOURCE_MANIFEST_NAME).read_text(encoding="utf-8")
    )
    normalized_manifest = _normalize_source_manifest_for_golden(native_manifest, sources)
    golden_path = Path(__file__).parent / "fixtures" / "hearing_source_manifest_content_v3.json"
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    assert _canonical_manifest_sha256(normalized_manifest) == golden["sha256_by_mode"][mode]
    assert native_session.mode == mode
    assert native_session.status == "prepared"

    cli_config = replace(config, output_dir=tmp_path / "cli-set")
    cli_sink_root = tmp_path / "cli-sink"
    cli_sink_root.mkdir()
    cli_sink = SourceRenderSink(cli_sink_root, cli_config.source_roots)
    cli_args = _producer_namespace(
        cli_config, cli_config.output_dir, cli_config.output_dir,
        cli_sink, CancellationToken(), None,
    )
    cli_args.hpg_render_sink = None
    cli_args.out = cli_config.output_dir
    cli_wrapper = {
        "einzel": rt.befehl_prepare,
        "kandidaten": rt.befehl_prepare_kandidaten,
        "dramaturgie": rt.befehl_prepare_dramaturgie,
    }[mode]
    assert cli_wrapper(cli_args) == 0
    if mode == "kandidaten":
        candidate_manifest = json.loads(
            (cli_config.output_dir / rt.KANDIDATEN_MANIFEST_NAME).read_text(encoding="utf-8")
        )
        candidate_golden = json.loads(
            (
                Path(__file__).parent
                / "fixtures"
                / "candidate_manifest_content.json"
            ).read_text(encoding="utf-8")
        )
        candidate_key = "three_notes" if three_notes else "normal"
        assert _canonical_manifest_sha256(
            _normalize_candidate_manifest_for_golden(candidate_manifest)
        ) == candidate_golden["sha256_by_mode"][candidate_key]
        order = json.loads(
            (cli_config.output_dir / "reihenfolge.json").read_text(encoding="utf-8")
        )
        order_golden = json.loads(
            (Path(__file__).parent / "fixtures" / "candidate_order_content.json").read_text(
                encoding="utf-8"
            )
        )
        assert _canonical_manifest_sha256(order) == order_golden["sha256_by_mode"][candidate_key]
    elif mode == "dramaturgie":
        dramaturgy_manifest = json.loads(
            (cli_config.output_dir / rt.DRAMATURGIE_MANIFEST_NAME).read_text(encoding="utf-8")
        )
        dramaturgy_golden = json.loads(
            (Path(__file__).parent / "fixtures" / "dramaturgy_manifest_content.json").read_text(
                encoding="utf-8"
            )
        )
        assert _canonical_manifest_sha256(
            _normalize_dramaturgy_manifest_for_golden(dramaturgy_manifest, track_id_map)
        ) == dramaturgy_golden["sha256"]

    metadata_by_mode = {
        "einzel": {"merkmale.csv", "bewertung.csv"},
        "kandidaten": {
            "merkmale.csv", "bewertung.csv", "reihenfolge.json",
            rt.KANDIDATEN_MANIFEST_NAME, "LIESMICH-kandidaten.txt",
        },
        "dramaturgie": {
            "dramaturgie_manifest.json", "bewertung.csv",
            "dramaturgie_bewertung.csv", "README.md",
        },
    }
    expected_metadata = metadata_by_mode[mode]
    expected_csv_headers_by_mode = {
        "einzel": {
            "bewertung.csv": ("pair_id", "clip", "bewertung"),
            "merkmale.csv": (
                "pair_id", *rt.ALLE_FAKTOREN, "crossfade_sek", *rt.ZUSATZ_SPALTEN,
                *rt.PLAN_AUDIT_SPALTEN, "track_a", "track_b",
            ),
        },
        "kandidaten": {
            "bewertung.csv": (
                rt.BEWERTUNG_DREINOTEN_SPALTEN if three_notes
                else rt.BEWERTUNG_KANDIDATEN_SPALTEN
            ),
            "merkmale.csv": rt.MERKMALE_KANDIDATEN_SPALTEN,
        },
        "dramaturgie": {
            "bewertung.csv": rt.BEWERTUNG_DREINOTEN_SPALTEN,
            "dramaturgie_bewertung.csv": rt.DRAMATURGIE_BEWERTUNG_SPALTEN,
        },
    }
    expected_csv_headers = expected_csv_headers_by_mode[mode]

    source_id_map = {
        str((sources / f"track-{index:02d}.wav").resolve()): f"$TRACK_{index:02d}"
        for index in range(track_count)
    }
    native_csv = _csv_content_projection(native_result.output_dir, source_id_map, track_id_map if mode == "dramaturgie" else {})
    cli_csv = _csv_content_projection(cli_config.output_dir, source_id_map, track_id_map if mode == "dramaturgie" else {})
    assert native_csv == cli_csv
    csv_golden = json.loads(
        (Path(__file__).parent / "fixtures" / "hearing_csv_content.json").read_text(encoding="utf-8")
    )
    csv_mode = "three_notes" if mode == "kandidaten" and three_notes else mode
    assert _canonical_manifest_sha256(cli_csv) == csv_golden["sha256_by_mode"][csv_mode]

    def file_inventory(directory):
        return {
            path.relative_to(directory).as_posix()
            for path in directory.rglob("*")
            if path.is_file()
        }

    native_files = file_inventory(native_result.output_dir)
    assert native_files == expected_metadata | {SOURCE_MANIFEST_NAME}
    cli_files = file_inventory(cli_config.output_dir)
    cli_clip_files = {
        path for path in cli_files if path.startswith("clips/")
    }
    assert cli_files == expected_metadata | cli_clip_files
    assert cli_clip_files

    for directory in (native_result.output_dir, cli_config.output_dir):
        for name, expected_header in expected_csv_headers.items():
            with (directory / name).open(encoding="utf-8", newline="") as handle:
                assert tuple(next(csv.reader(handle))) == tuple(expected_header)

    from hpg_core.hearing_ratings import load_session as load_rating_session

    def logical_session(session):
        return (
            session["mode"],
            tuple(
                (
                    group["id"],
                    tuple(
                        (
                            clip["pair_id"], clip["clip_id"],
                            clip["ratings"], clip["gewaehlt"],
                        )
                        for clip in group["clips"]
                    ),
                    group["ratings"],
                )
                for group in session["groups"]
            ),
        )

    native_view = load_rating_session(native_result.output_dir)
    cli_view = load_rating_session(cli_config.output_dir)
    assert logical_session(native_view) == logical_session(cli_view)

    def flattened_clips(session):
        return [clip for group in session["groups"] for clip in group["clips"]]

    native_clips = flattened_clips(native_view)
    cli_clips = flattened_clips(cli_view)
    assert len(native_clips) == native_session.clip_count == len(cli_clips)
    assert native_session.source_contents_verified is True
    assert len(native_session.playback_paths) == native_session.clip_count
    assert set(native_session.playback_paths) == set(native_session.specs)
    assert all(clip["path"] is None and isinstance(clip.get("spec"), dict)
               for clip in native_clips)
    assert not list(native_result.output_dir.rglob("*.wav"))

    cli_paths = [Path(clip["path"]) for clip in cli_clips]
    assert len({path.resolve() for path in cli_paths}) == native_session.clip_count
    assert all(path.is_file() and path.suffix.lower() == ".wav" for path in cli_paths)
    for path in cli_paths:
        with wave.open(str(path), "rb") as audio:
            assert audio.getnchannels() == 2
            assert audio.getnframes() > 0

    if mode == "einzel":
        from hpg_core.hearing_calibration import validate_set
        assert validate_set(cli_config.output_dir)
        common_files = ("merkmale.csv", "bewertung.csv")
    elif mode == "kandidaten":
        rt.validiere_kandidaten_csvs(
            rt.lies_csv(cli_config.output_dir / "merkmale.csv"),
            rt.lies_csv(cli_config.output_dir / "bewertung.csv"),
        )
        common_files = (
            "merkmale.csv", "bewertung.csv", "reihenfolge.json", rt.KANDIDATEN_MANIFEST_NAME,
        )
    else:
        common_files = ("bewertung.csv", "dramaturgie_bewertung.csv")
        cli_manifest = json.loads((cli_config.output_dir / rt.DRAMATURGIE_MANIFEST_NAME).read_text())
        native_manifest = json.loads((native_result.output_dir / rt.DRAMATURGIE_MANIFEST_NAME).read_text())
        for manifest in (cli_manifest, native_manifest):
            for variant in manifest["variants"]:
                for transition in variant["transitions"]:
                    transition["clip"] = {"path": transition["clip"]["path"]}
        assert cli_manifest == native_manifest

    for name in common_files:
        assert (cli_config.output_dir / name).read_bytes() == (native_result.output_dir / name).read_bytes()

    if mode == "kandidaten":
        import numpy as np
        import soundfile as sf

        from hpg_core import hearing_calibration, transition_renderer
        from tools import audit_candidate_set as audit
        from tests.test_audit_candidate_set import _copy_render

        for set_dir in (cli_config.output_dir, native_result.output_dir):
            ratings = rt.lies_csv(set_dir / "bewertung.csv")
            for rating in ratings:
                if three_notes:
                    rating.update(track_note="4", technik_note="4", gesamt_note="4")
                else:
                    rating["note"] = "4"
            columns = rt.BEWERTUNG_DREINOTEN_SPALTEN if three_notes else rt.BEWERTUNG_KANDIDATEN_SPALTEN
            rt.schreibe_csv(set_dir / "bewertung.csv", columns, ratings)

        def render_synthetic_ram(_spec, destination):
            signal = np.zeros((800, 2), dtype=np.float32)
            transition_renderer._synchronize_and_verify_kicks(signal, signal, 8000, 120., 800)
            sf.write(destination, signal, 8000, subtype="PCM_16", format="WAV")

        monkeypatch.setattr(transition_renderer, "render_transition_clip", render_synthetic_ram)
        monkeypatch.setattr(transition_renderer, "_synchronize_and_verify_kicks", lambda a, b, *args, **kwargs: b)
        monkeypatch.setattr(transition_renderer, "_kick_lags_across_overlap", lambda *args: [0., 0., 0.])
        monkeypatch.setattr(audit, "_load_tracks_immutable", lambda *_args: tracks)
        monkeypatch.setattr(audit, "rank_pair_candidates", lambda *_args, **_kwargs: [candidate])
        audit_report = audit.audit_set(
            cli_config.output_dir, cache, render=_copy_render(cli_config.output_dir),
        )
        audit_path = tmp_path / "cli-audit.json"
        audit_path.write_text(json.dumps(audit_report), encoding="utf-8")
        operation_root = tmp_path / "native-fit-operation"
        operation_root.mkdir()
        monkeypatch.setenv(
            "HPG_CANDIDATE_PREFERENCES_FILE",
            str(operation_root / "child_preferences.json"),
        )
        native_fit = hearing_calibration.compute_proposal(
            native_result.output_dir, cache, operation_root=operation_root,
            operation_id="6" * 32, seed=config.seed,
        )
        assert rt.befehl_fit_kandidaten(SimpleNamespace(
            dir=cli_config.output_dir, cache=cache, audit_report=audit_path, seed=config.seed,
        )) == 0
        output_name = "dreinoten_fit_bericht.json" if three_notes else "candidate_preferences_entwurf.json"
        cli_draft = json.loads((cli_config.output_dir / output_name).read_bytes())
        assert cli_draft == native_fit["candidate_report"]["ergebnis"]
        assert not (operation_root / "child_preferences.json").exists()

    assert all(path.read_bytes().startswith(b"synthetic source") for path in sources.iterdir())
    assert cache.read_bytes() == b"isolated cache fingerprint"


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
    from hpg_core.hearing_sources import load_source_session
    session = load_source_session(result.output_dir)
    assert session.mode == mode
    assert session.status == "prepared"
    assert session.clip_count == session.pair_count == 1
    if mode == "einzel":
        from hpg_core.hearing_calibration import validate_set
        assert validate_set(result.output_dir)
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
