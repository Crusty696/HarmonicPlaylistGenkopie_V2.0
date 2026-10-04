"""Quellreferenzen bleiben Metadaten; Originalaudio bleibt unveraendert."""
import csv
import json
from dataclasses import asdict
from pathlib import Path

import pytest

from hpg_core.hearing_sources import (
    SOURCE_MANIFEST_NAME, SourceRenderSink, SourceValidationError,
    load_source_session, write_source_manifest,
)
from hpg_core.transition_renderer import TransitionClipSpec


@pytest.fixture
def source_fixture(tmp_path):
    audio = tmp_path / "originals"
    audio.mkdir()
    a, b = audio / "a.wav", audio / "b.mp3"
    a.write_bytes(b"synthetic source A")
    b.write_bytes(b"synthetic source B")
    stage = tmp_path / "session"
    stage.mkdir()
    spec = TransitionClipSpec(str(a), str(b), 20.0, 0.0, 8.0)
    sink = SourceRenderSink(stage, (audio,))
    sink.emit(spec, stage / "clips/001.wav")
    from tools import rate_transitions as rt
    columns = ("pair_id", *rt.ALLE_FAKTOREN, "crossfade_sek", *rt.ZUSATZ_SPALTEN,
               *rt.PLAN_AUDIT_SPALTEN, "track_a", "track_b")
    row = dict.fromkeys(columns, "0")
    row.update(pair_id="001", track_a=str(a), track_b=str(b), crossfade_sek="8.0",
               plan_mix_out_sec="20.0", plan_mix_in_sec="0.0", plan_overlap_sec="8.0",
               plan_transition_type="smooth_blend", plan_target_sr="44100", kandidat_rang="1",
               bpm_toleranz="2.0", energy_direction="auto")
    for name, fields, rows in (
        ("merkmale.csv", columns, [row]),
        ("bewertung.csv", ("pair_id", "clip", "bewertung"),
         [{"pair_id": "001", "clip": "clips/001.wav", "bewertung": ""}]),
    ):
        with (stage / name).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    return stage, spec, sink, a, b


def test_emit_records_full_detached_spec_without_audio(source_fixture):
    stage, spec, sink, a, b = source_fixture
    expected = asdict(spec)
    spec.mix_out_sec = 999.0
    assert sink.specs == {"clips/001.wav": expected}
    assert not (stage / "clips").exists()
    assert a.read_bytes() == b"synthetic source A"
    assert b.read_bytes() == b"synthetic source B"


@pytest.mark.parametrize("target", ["../outside.wav", "file.wav", "clips/../escape.wav", "clips/x.mp3"])
def test_emit_rejects_unsafe_target(source_fixture, target):
    stage, spec, sink, *_ = source_fixture
    with pytest.raises(SourceValidationError):
        sink.emit(spec, stage / target)


def test_emit_rejects_duplicate_target(source_fixture):
    stage, spec, sink, a, _ = source_fixture
    with pytest.raises(SourceValidationError, match="[Dd]oppelt"):
        sink.emit(spec, stage / "clips/001.wav")


def test_emit_rejects_changed_source(source_fixture):
    stage, spec, sink, a, _ = source_fixture
    a.write_bytes(b"changed")
    with pytest.raises(SourceValidationError, match="veraendert"):
        sink.emit(spec, stage / "clips/002.wav")


def test_sink_failure_poisons_whole_session(source_fixture):
    stage, spec, sink, *_ = source_fixture
    with pytest.raises(SourceValidationError):
        sink.emit(spec, stage / "clips/001.wav")
    with pytest.raises(SourceValidationError, match="gesamter Satz"):
        write_source_manifest(stage, "einzel", sink)


def test_source_manifest_allows_rating_edits_binds_immutable_metadata(source_fixture):
    stage, _, sink, *_ = source_fixture
    write_source_manifest(stage, "einzel", sink)
    loaded = load_source_session(stage)
    assert loaded.status == "prepared"
    assert loaded.clip_count == loaded.pair_count == 1
    ratings = stage / "bewertung.csv"
    ratings.write_text("pair_id,clip,bewertung\n001,clips/001.wav,5\n", encoding="utf-8")
    assert load_source_session(stage).clip_count == 1
    features = stage / "merkmale.csv"
    features.write_bytes(features.read_bytes() + b"\n")
    with pytest.raises(SourceValidationError, match="Metadaten"):
        load_source_session(stage)


@pytest.mark.parametrize("mutation", ["orphan", "missing", "audio", "rating_id", "source"])
def test_source_loader_rejects_broken_bindings(source_fixture, mutation):
    stage, _, sink, a, _ = source_fixture
    write_source_manifest(stage, "einzel", sink)
    path = stage / SOURCE_MANIFEST_NAME
    data = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "orphan":
        data["specs"]["clips/002.wav"] = data["specs"]["clips/001.wav"]
    elif mutation == "missing":
        data["specs"] = {}
    elif mutation == "audio":
        (stage / "clips").mkdir()
        (stage / "clips/001.wav").write_bytes(b"forbidden")
    elif mutation == "rating_id":
        (stage / "bewertung.csv").write_text("pair_id,clip,bewertung\n002,clips/001.wav,5\n")
    else:
        a.write_bytes(b"modified source")
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(SourceValidationError):
        load_source_session(stage)


@pytest.mark.parametrize("field,value", [("strict_beat_sync", 1), ("target_sr", True),
    ("crossfade_sec", float("nan")), ("bpm_a", None), ("tempo_ratio", "1.0")])
def test_emit_rejects_wrong_spec_types(source_fixture, field, value):
    stage, spec, sink, *_ = source_fixture
    setattr(spec, field, value)
    with pytest.raises(SourceValidationError):
        sink.emit(spec, stage / "clips/002.wav")


@pytest.mark.parametrize("raw", ['{"format":1,"format":2}', '{"value":NaN}', '{"value":1e999}'])
def test_source_loader_rejects_duplicate_and_nonfinite_json(source_fixture, raw):
    stage, *_ = source_fixture
    (stage / SOURCE_MANIFEST_NAME).write_text(raw, encoding="utf-8")
    with pytest.raises(SourceValidationError):
        load_source_session(stage)


def test_emit_requires_containment_in_selected_roots(source_fixture, tmp_path):
    stage, spec, _, *_ = source_fixture
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(SourceValidationError):
        SourceRenderSink(stage, (other,)).emit(spec, stage / "clips/001.wav")


def test_structural_loading_skips_only_original_content_proof(source_fixture, monkeypatch):
    import hpg_core.hearing_sources as hs
    stage, _, sink, a, _ = source_fixture
    write_source_manifest(stage, "einzel", sink)
    original = hs._fingerprint
    def forbid_original_reads(path):
        assert path.parent != a.parent, "Strukturladen darf Originalinhalte nicht lesen"
        return original(path)
    monkeypatch.setattr(hs, "_fingerprint", forbid_original_reads)
    result = load_source_session(stage, verify_source_contents=False)
    assert not result.source_contents_verified
    assert result.verification_scope == "structural only, no original content integrity proof"


def test_structural_loading_checks_sizes_but_cannot_detect_same_size_content_change(source_fixture):
    stage, _, sink, a, _ = source_fixture
    write_source_manifest(stage, "einzel", sink)
    a.write_bytes(b"X" * a.stat().st_size)
    assert not load_source_session(stage, verify_source_contents=False).source_contents_verified
    with pytest.raises(SourceValidationError):
        load_source_session(stage)
    a.write_bytes(b"different size")
    with pytest.raises(SourceValidationError):
        load_source_session(stage, verify_source_contents=False)


def test_source_session_has_deep_immutable_snapshots_and_detached_views(source_fixture):
    stage, _, sink, *_ = source_fixture
    write_source_manifest(stage, "einzel", sink)
    session = load_source_session(stage)
    with pytest.raises(TypeError):
        session.manifest["specs"]["clips/001.wav"]["mix_out_sec"] = 99.
    detached = session.specs
    detached["clips/001.wav"]["mix_out_sec"] = 99.
    assert session.specs["clips/001.wav"]["mix_out_sec"] == 20.


def make_candidate_metadata(stage, a, b, sink, *, three_notes=False):
    from tools import rate_transitions as rt
    from tools import audit_candidate_set as audit
    cid = "001_k1"
    spec = TransitionClipSpec(str(a), str(b), 10., 12., 16., transition_type="pro_eq_swap")
    sink.emit(spec, stage / f"clips/{cid}.wav")
    row = dict.fromkeys(rt.MERKMALE_KANDIDATEN_SPALTEN, "")
    row.update(pair_id="001", clip_id=cid, clip=f"clips/{cid}.wav", score="0.8",
               blend_bars="8", t_out="10", t_in="12", crossfade_sek="16",
               confidence_out="1", confidence_in="1", bpm_a="120", bpm_b="120",
               bpm_toleranz="2", energy_direction="auto", rendered_transition_type="pro_eq_swap",
               transition_type_mode="kontrolliert", track_a=str(a), track_b=str(b))
    row.update({key: "0.5" for key in rt.KANDIDATEN_TEILWERTE})
    rating_columns = rt.BEWERTUNG_DREINOTEN_SPALTEN if three_notes else rt.BEWERTUNG_KANDIDATEN_SPALTEN
    rt.schreibe_csv(stage / "merkmale.csv", rt.MERKMALE_KANDIDATEN_SPALTEN, [row])
    rt.schreibe_csv(stage / "bewertung.csv", rating_columns,
                   [dict.fromkeys(rating_columns, "") | {"pair_id": "001", "clip_id": cid}])
    (stage / "reihenfolge.json").write_text(json.dumps({"001": rt.reihenfolge_fuer_paar("001", [cid], 0)}))
    (stage / "LIESMICH-kandidaten.txt").write_text("Source refs")
    profile = dict.fromkeys(audit.KANDIDATEN_GEWICHT_SCHLUESSEL, 0.1) | {
        "groove_sim_floor": 0.5, "bass_delta_max": 6., "brightness_delta_max": 1200.}
    manifest = {
        "format_version": 2 if three_notes else 1, "app_version": rt.APP_VERSION,
        "algorithm_build": rt._algorithm_build_fingerprint(),
        "hearing_test_contract": {"harmonic_gate_scope": rt.HARMONIC_GATE_SCOPE,
                                  "minimum_harmonic_score": rt.MIN_HARMONIC_SCORE},
        "cache": {"version": rt.CACHE_VERSION, "size": 0, "sha256": "0" * 64},
        "render_args": {"anzahl": 1, "max_versionen_pro_paar": 1, "nur_genre": None,
                        "transition_type_mode": "kontrolliert", "seed": 0},
        "scoring_snapshot": {
            "rank_args": {"bpm_tolerance": 2., "energy_direction": "auto", "harmonic_strictness": 7,
                          "allow_experimental": True},
            "candidate_tolerances_by_genre": dict.fromkeys(rt.CANONICAL_GENRES, profile),
            "candidate_tolerances_fallback": profile,
            "candidate_schema_ranks_by_genre": dict.fromkeys(rt.CANONICAL_GENRES, []),
            "candidate_schema_rank_fallback": [], "candidate_choices": {},
        },
        "pairs": [{"pair_id": "001", "track_a": str(a), "track_b": str(b), "clips": [{
            "clip_id": cid, "rank": 1, "t_out": 10., "t_in": 12., "blend_bars": 8,
            "overlap_sec": 16., "rendered_transition_type": "pro_eq_swap"}]}],
    }
    if three_notes:
        manifest["rating_schema"] = "three_notes_v1"
    (stage / "kandidaten_manifest.json").write_text(json.dumps(manifest))


@pytest.mark.parametrize("three_notes", [False, True])
def test_candidate_source_schema_preserves_legacy_manifest_and_ratings(tmp_path, three_notes):
    originals = tmp_path / "sources"
    originals.mkdir()
    a, b = originals / "a.wav", originals / "b.mp3"
    a.write_bytes(b"A")
    b.write_bytes(b"B")
    stage = tmp_path / "set"
    stage.mkdir()
    sink = SourceRenderSink(stage, (originals,))
    make_candidate_metadata(stage, a, b, sink, three_notes=three_notes)
    before = {path.name: path.read_bytes() for path in stage.iterdir()}
    write_source_manifest(stage, "kandidaten", sink)
    loaded = load_source_session(stage)
    assert loaded.clip_count == loaded.pair_count == 1
    assert loaded.playback_paths == ("clips/001_k1.wav",)
    assert set(loaded.sources) == {str(a), str(b)}
    assert all((stage / name).read_bytes() == content for name, content in before.items())
    assert not (stage / "clips").exists()


def make_dramaturgy_metadata(stage, paths, sink):
    from tools import rate_transitions as rt
    from hpg_core.playlist import TransitionPlan, resolve_run_scoring_context
    ids = [rt.hashlib.sha256(rt._windows_pfadschluessel(str(p)).encode()).hexdigest() for p in paths]
    pool_hash = rt._kanonischer_json_hash(ids)
    variants, ratings, variant_ratings = [], [], []
    for contract in rt.dramaturgie_varianten():
        variant_id = contract["variant_id"]
        cid = f"{variant_id}__t001"
        ref = f"clips/{variant_id}/{cid}.wav"
        sink.emit(TransitionClipSpec(str(paths[0]), str(paths[1]), 20., 0., 8.), stage / ref)
        plan = TransitionPlan(20., 0., 20., 28., 8., "smooth_blend")
        variants.append(contract | {
            "scoring_context": rt._json_roundtrip_strikt(resolve_run_scoring_context(
                contract["canonical_strategy"], contract["effective_strategy_parameters"])),
            "pool_hash": pool_hash, "ordered_track_ids": ids,
            "transitions": [{"transition_id": cid, "index": 0, "from_track_id": ids[0], "to_track_id": ids[1],
                             "plan": asdict(plan), "clip": {"path": ref, "representation": "source_reference_v1"}}],
        })
        ratings.append(dict.fromkeys(rt.BEWERTUNG_DREINOTEN_SPALTEN, "") | {"pair_id": cid, "clip_id": cid})
        variant_ratings.append(dict.fromkeys(rt.DRAMATURGIE_BEWERTUNG_SPALTEN, "") | {"variant_id": variant_id})
    manifest = {"format_version": rt.DRAMATURGIE_MANIFEST_VERSION, "contract": rt.DRAMATURGIE_CONTRACT,
                "app_version": rt.APP_VERSION, "algorithm_build": rt._algorithm_build_fingerprint(),
                "cache": {"version": rt.CACHE_VERSION, "size": 0, "sha256": "0" * 64},
                "pool_hash": pool_hash, "ordered_pool_track_ids": ids,
                "candidate_choice_hash": rt._kanonischer_json_hash({}), "variants": variants}
    (stage / "dramaturgie_manifest.json").write_text(json.dumps(manifest))
    rt.schreibe_csv(stage / "bewertung.csv", rt.BEWERTUNG_DREINOTEN_SPALTEN, ratings)
    rt.schreibe_csv(stage / "dramaturgie_bewertung.csv", rt.DRAMATURGIE_BEWERTUNG_SPALTEN, variant_ratings)
    (stage / "README.md").write_text("source refs")
    return manifest


@pytest.mark.parametrize("mutation", [None, "fake_wav", "source_swap", "plan", "matrix", "rating"])
def test_dramaturgy_source_validator_retains_non_wav_contracts(tmp_path, mutation):
    sources = tmp_path / "sources"
    sources.mkdir()
    paths = [sources / f"{i}.wav" for i in range(12)]
    for path in paths:
        path.write_bytes(b"synthetic")
    stage = tmp_path / "session"
    stage.mkdir()
    sink = SourceRenderSink(stage, (sources,))
    manifest = make_dramaturgy_metadata(stage, paths, sink)
    transition = manifest["variants"][0]["transitions"][0]
    if mutation == "fake_wav":
        transition["clip"] = {"path": transition["clip"]["path"], "sha256": "0" * 64, "size_bytes": 1}
    elif mutation == "source_swap":
        sink._specs[transition["clip"]["path"]]["track_a_path"] = str(paths[1])
    elif mutation == "plan":
        transition["plan"]["mix_out_a"] = 99.
    elif mutation == "matrix":
        manifest["variants"].pop()
    elif mutation == "rating":
        rating_path = stage / "dramaturgie_bewertung.csv"
        rating_path.write_text(rating_path.read_text().replace(
            manifest["variants"][0]["variant_id"], "unknown", 1))
    (stage / "dramaturgie_manifest.json").write_text(json.dumps(manifest))
    if mutation:
        with pytest.raises(SourceValidationError):
            write_source_manifest(stage, "dramaturgie", sink)
    else:
        write_source_manifest(stage, "dramaturgie", sink)
        loaded = load_source_session(stage)
        assert loaded.clip_count == len(manifest["variants"])
        assert loaded.status == "prepared"
        assert not list(stage.rglob("*.wav"))


@pytest.fixture
def frozen_dramaturgy(tmp_path):
    originals = tmp_path / "sources"
    originals.mkdir()
    paths = [originals / f"{i}.wav" for i in range(12)]
    for path in paths:
        path.write_bytes(b"synthetic")
    stage = tmp_path / "session"
    stage.mkdir()
    sink = SourceRenderSink(stage, (originals,))
    manifest = make_dramaturgy_metadata(stage, paths, sink)
    write_source_manifest(stage, "dramaturgie", sink)
    return stage, sink, manifest


@pytest.mark.parametrize("verify", [False, True])
def test_frozen_dramaturgy_load_ignores_later_live_calibration(frozen_dramaturgy, monkeypatch, verify):
    from hpg_core import candidate_preferences as cp, tolerances, playlist
    stage, _, manifest = frozen_dramaturgy
    keys = cp.GEWICHT_SCHLUESSEL
    snapshot = manifest["variants"][0]["scoring_context"]
    weights = {key: snapshot["candidate_tolerances_by_genre"]["Techno"][key] for key in keys}
    weights[keys[0]], weights[keys[1]] = weights[keys[1]], weights[keys[0]]
    monkeypatch.setattr(cp, "kandidaten_gewichte", lambda genre: weights)
    original_tolerances = tolerances.get_tolerances
    def later_override(genre):
        profile = dict(original_tolerances(genre))
        profile["bass_delta_max"] += 1.0
        return profile
    monkeypatch.setattr(tolerances, "get_tolerances", later_override)
    before = {p.name: p.read_bytes() for p in stage.iterdir() if p.is_file()}
    session = load_source_session(stage, verify_source_contents=verify)
    from hpg_core.hearing_sources import _thaw
    assert _thaw(session.producer_manifest)["variants"][0]["scoring_context"] == manifest["variants"][0]["scoring_context"]
    assert before == {p.name: p.read_bytes() for p in stage.iterdir() if p.is_file()}
    def forbidden(*args, **kwargs):
        pytest.fail("Frozen source validation must not access live calibration/preferences")
    monkeypatch.setattr(playlist, "resolve_run_scoring_context", forbidden)
    monkeypatch.setattr(cp, "kandidaten_gewichte", forbidden)
    monkeypatch.setattr(cp, "schema_rangfolge", forbidden)
    monkeypatch.setattr(tolerances, "get_tolerances", forbidden)
    assert load_source_session(stage, verify_source_contents=verify).status == "prepared"


@pytest.mark.parametrize("mutation", ["partial", "genre", "weight_type", "sum", "rank", "scalar", "extra"])
def test_frozen_dramaturgy_context_schema_remains_strict(frozen_dramaturgy, mutation):
    stage, sink, manifest = frozen_dramaturgy
    context = manifest["variants"][0]["scoring_context"]
    from hpg_core.candidate_preferences import GEWICHT_SCHLUESSEL
    if mutation == "partial":
        context["candidate_tolerances_by_genre"]["Techno"].pop(GEWICHT_SCHLUESSEL[0])
    elif mutation == "genre":
        context["candidate_tolerances_by_genre"]["not-a-genre"] = context["candidate_tolerances_by_genre"].pop("Techno")
    elif mutation == "weight_type":
        context["candidate_tolerances_by_genre"]["Techno"][GEWICHT_SCHLUESSEL[0]] = True
    elif mutation == "sum":
        context["candidate_tolerances_by_genre"]["Techno"][GEWICHT_SCHLUESSEL[0]] = 0.99
    elif mutation == "rank":
        context["candidate_schema_ranks_by_genre"]["Techno"] = ["not-a-schema"]
    elif mutation == "scalar":
        context["harmonic_strictness"] = 9
    else:
        context["unrecognized"] = 1
    (stage / "dramaturgie_manifest.json").write_text(json.dumps(manifest))
    # Auch bei neuem Hash-Anker bleibt der gespeicherte Kontextvertrag strikt.
    with pytest.raises(SourceValidationError):
        write_source_manifest(stage, "dramaturgie", sink)


def test_frozen_dramaturgy_hash_anchor_is_not_weakened(frozen_dramaturgy):
    stage, _, manifest = frozen_dramaturgy
    profile = manifest["variants"][0]["scoring_context"]["candidate_tolerances_by_genre"]["Techno"]
    from hpg_core.candidate_preferences import GEWICHT_SCHLUESSEL
    a, b = GEWICHT_SCHLUESSEL[:2]
    profile[a], profile[b] = profile[b], profile[a]
    (stage / "dramaturgie_manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(SourceValidationError, match="Metadaten"):
        load_source_session(stage, verify_source_contents=False)
