"""RAM-Vertrag: synthetische Signale, Textquellen und kein SQLite/WAV-Artefakt."""
import csv
import hashlib
import io
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from hpg_core import hearing_calibration as calibration
from hpg_core import transition_renderer as renderer
from hpg_core.hearing_sources import SourceRenderSink, write_source_manifest
from hpg_core.models import Track
from tests.test_audit_candidate_set import _candidate
from tools import audit_candidate_set as audit, rate_transitions as rate

_REAL_RENDER = renderer.render_transition_clip
_REAL_SYNC = renderer._synchronize_and_verify_kicks
_REAL_LAGS = renderer._kick_lags_across_overlap


def _csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def ram_set(tmp_path, monkeypatch):
    root, sources = tmp_path / "set", tmp_path / "sources"
    root.mkdir()
    sources.mkdir()
    paths = [sources / "a.txt", sources / "b.txt"]
    for path in paths:
        path.write_text("synthetic source identity", encoding="utf-8")
    cache = tmp_path / "cache-identity.txt"
    cache.write_text("synthetic cache identity; not SQLite", encoding="utf-8")
    tracks = [Track(str(path), path.name, duration=100., bpm=bpm,
                    detected_genre="Psytrance", camelotCode="8A")
              for path, bpm in zip(paths, (120., 122.))]
    monkeypatch.setattr(audit, "_load_tracks_immutable", lambda _: tracks)
    monkeypatch.setattr(audit, "rank_pair_candidates", lambda *a, **k: [_candidate()])
    row = dict.fromkeys(rate.MERKMALE_KANDIDATEN_SPALTEN, "")
    row.update(pair_id="001", clip_id="001_k1", clip="clips/001_k1.wav",
               score="0.8", blend_bars="8", t_out="10.0", t_in="12.0",
               confidence_out="1", confidence_in="1", crossfade_sek="16.0",
               bpm_a="120", bpm_b="122", bpm_toleranz="2.0", energy_direction="auto",
               rendered_transition_type="pro_eq_swap", transition_type_mode="kontrolliert",
               track_a=str(paths[0]), track_b=str(paths[1]), schema_out="pssi_phrase",
               schema_in="analyzer", schemata_out="pssi_phrase", schemata_in="analyzer",
               provenance_out="rekordbox_pssi", provenance_in="hpg_analyzer",
               bpm_relation="direct", genre_a="Psytrance", genre_b="Psytrance",
               key_a="8A", key_b="8A")
    row.update({f: "0.8" if f in {"harmonic", "groove"} else "0.5" for f in audit.FAKTOREN})
    rating = dict.fromkeys(rate.BEWERTUNG_KANDIDATEN_SPALTEN, "")
    rating.update(pair_id="001", clip_id="001_k1", note="4", gewaehlt="1")
    _csv(root / "merkmale.csv", rate.MERKMALE_KANDIDATEN_SPALTEN, [row])
    _csv(root / "bewertung.csv", rate.BEWERTUNG_KANDIDATEN_SPALTEN, [rating])
    (root / "reihenfolge.json").write_text(json.dumps({"001": {"seed": 1, "clips": ["001_k1"]}}))
    (root / "LIESMICH-kandidaten.txt").write_text("Synthetic RAM contract")
    profile = {**{key: .1 for key in audit.KANDIDATEN_GEWICHT_SCHLUESSEL},
               "groove_sim_floor": .5, "bass_delta_max": 6., "brightness_delta_max": 1200.}
    size, digest = audit._fingerprint_file(cache)
    manifest = {
        "format_version": 1, "app_version": audit.APP_VERSION,
        "algorithm_build": audit._algorithm_build_fingerprint(),
        "hearing_test_contract": {"harmonic_gate_scope": audit.HARMONIC_GATE_SCOPE,
                                  "minimum_harmonic_score": audit.MIN_HARMONIC_SCORE},
        "cache": {"version": audit.CACHE_VERSION, "size": size, "sha256": digest},
        "render_args": {"anzahl": 1, "max_versionen_pro_paar": 1, "nur_genre": "Psytrance",
                        "transition_type_mode": "kontrolliert", "seed": 0},
        "scoring_snapshot": {
            "rank_args": {"bpm_tolerance": 2., "energy_direction": "auto",
                          "harmonic_strictness": 7, "allow_experimental": True},
            "candidate_tolerances_by_genre": {g: profile for g in audit.CANONICAL_GENRES},
            "candidate_tolerances_fallback": profile,
            "candidate_schema_ranks_by_genre": {g: [] for g in audit.CANONICAL_GENRES},
            "candidate_schema_rank_fallback": [], "candidate_choices": {}},
        "pairs": [{"pair_id": "001", "track_a": str(paths[0]), "track_b": str(paths[1]),
                   "clips": [{"clip_id": "001_k1", "rank": 1, "t_out": 10., "t_in": 12.,
                              "blend_bars": 8, "overlap_sec": 16.,
                              "rendered_transition_type": "pro_eq_swap"}]}]}
    (root / rate.KANDIDATEN_MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
    sink = SourceRenderSink(root, (sources,))
    rate.rendere_kandidat(*tracks, _candidate(), "001", 1, root / "clips", render_sink=sink.emit)
    write_source_manifest(root, "kandidaten", sink)
    calls = []

    def synthetic_render(spec, output):
        # Dieser Guard ist der RED-Nachweis gegen den bisherigen Dateitransport.
        assert not isinstance(output, (str, Path)), "WAV-Dateischreiben verboten"
        calls.append(spec)
        signal = np.zeros((800, 2), dtype=np.float32)
        signal[::100] = .5
        renderer._synchronize_and_verify_kicks(signal, signal, 8000, 120., 800)
        sf.write(output, signal, 8000, subtype="PCM_16", format="WAV")

    monkeypatch.setattr(renderer, "render_transition_clip", synthetic_render)
    monkeypatch.setattr(renderer, "_synchronize_and_verify_kicks", lambda a, b, *args: b)
    monkeypatch.setattr(renderer, "_kick_lags_across_overlap", lambda *args: [0., 0., 0.])
    op = tmp_path / "operation"
    op.mkdir()
    monkeypatch.setenv("HPG_CANDIDATE_PREFERENCES_FILE", str(op / "child_preferences.json"))
    return root, cache, op, calls, tracks


def test_native_no_wav_write(ram_set):
    root, cache, op, calls, _ = ram_set
    result = calibration.compute_proposal(root, cache, operation_root=op,
                                         operation_id="1" * 32, fit=False)
    calibration.validate_proposal(result)
    assert result["audit_passed"]
    assert len(calls) == 1
    assert result["version"] == 2
    assert result["binding"]["purpose"] == "regular"
    assert result["audit"]["version"] == 2
    assert result["audit"]["evidence_kind"] == "spec_verified_ram_replay"
    assert "reference_pcm_sha256" not in result["audit"]["candidates"][0]
    assert not list(op.rglob("*.wav"))


def test_cli_audit_render_uses_same_producer_and_ram_sink(ram_set):
    root, _, op, calls, tracks = ram_set
    pcm, lags = audit._render_with_diagnostics(*tracks, _candidate(), "001", 1, op,
                                             rendered_transition_type="pro_eq_swap",
                                             transition_type_mode="kontrolliert", bpm_toleranz=2., energy_direction=None)
    assert type(pcm) is bytes
    assert audit._validate_lags("001_k1", lags) == [0., 0., 0.]
    assert len(calls) == 1
    assert not list(op.rglob("*.wav"))
    assert audit._compare_wav(pcm, pcm, "001_k1")["channels"] == 2


def test_native_fit_is_pure_and_does_not_render_again(ram_set, monkeypatch):
    from hpg_core import candidate_preferences as cp
    root, cache, op, calls, _ = ram_set
    monkeypatch.setattr(cp, "merge_user_preferences_atomically", lambda *a, **k: pytest.fail("native Fit schreibt Praeferenzen"))
    result = calibration.compute_proposal(root, cache, operation_root=op, operation_id="1" * 32)
    assert result["fit_status"] == "passed"
    assert result["gate_updates"] == {}
    assert len(calls) == 1
    assert not (op / "child_preferences.json").exists()


def test_inputs_and_receipt_are_detached_immutable(ram_set):
    root, cache, *_ = ram_set
    inputs = audit.prepare_candidate_inputs(root, cache)
    receipt = audit.audit_candidates(inputs)
    with pytest.raises(FrozenInstanceError):
        inputs.payload = b"changed"
    data = receipt.as_dict()
    data["candidates"].clear()
    assert len(receipt.as_dict()["candidates"]) == 1


def test_spec_mismatch_rejected_before_any_dsp(ram_set):
    from hpg_core.hearing_sources import SOURCE_MANIFEST_NAME
    root, cache, _, calls, _ = ram_set
    path = root / SOURCE_MANIFEST_NAME
    data = json.loads(path.read_bytes())
    data["specs"]["clips/001_k1.wav"]["bpm_a"] = 121.
    path.write_text(json.dumps(data), encoding="utf-8")
    inputs = audit.prepare_candidate_inputs(root, cache)
    with pytest.raises(ValueError, match="SourceSpec"):
        audit.audit_candidates(inputs)
    assert calls == []


def test_native_receipt_digest_matches_actual_single_replay(ram_set, monkeypatch):
    root, cache, _, calls, _ = ram_set
    original = renderer.render_transition_clip

    buffers = []
    def record_replay(spec, output):
        original(spec, output)
        buffers.append(output.getvalue())
    monkeypatch.setattr(renderer, "render_transition_clip", record_replay)
    receipt = audit.audit_candidates(audit.prepare_candidate_inputs(root, cache)).as_dict()
    pcm, sr = sf.read(io.BytesIO(buffers[0]), dtype="int16", always_2d=True)
    candidate = receipt["candidates"][0]
    assert candidate["replay_pcm_sha256"] == hashlib.sha256(pcm.astype("<i2").tobytes()).hexdigest()
    assert candidate["pcm"]["frames"] == len(pcm)
    assert candidate["pcm"]["samplerate"] == sr
    assert "reference_pcm_sha256" not in candidate
    assert len(calls) == len(buffers) == 1


@pytest.mark.parametrize("lags", [[0., None, 0.], [0., float("nan"), 0.], [0., .006001, 0.], [0., 0.]])
def test_actual_lag_errors_reject_and_restore_renderer_hook(ram_set, monkeypatch, lags):
    root, cache, *_ = ram_set
    original = renderer._synchronize_and_verify_kicks
    monkeypatch.setattr(renderer, "_kick_lags_across_overlap", lambda *a: lags)
    with pytest.raises(ValueError):
        audit.audit_candidates(audit.prepare_candidate_inputs(root, cache))
    assert renderer._synchronize_and_verify_kicks is original


def _proposal(ram_set):
    root, cache, op, *_ = ram_set
    return calibration.compute_proposal(root, cache, operation_root=op, operation_id="1" * 32, fit=False)


@pytest.mark.parametrize("mutation", ["version", "transport", "old_report", "order", "topn", "manifest",
                                     "source_manifest", "source_digest", "pcm_digest", "pcm_type", "lag",
                                     "before", "after", "rating_binding", "cache_binding", "build_binding"])
def test_receipt_tampering_rejected_by_validate_apply_and_export(ram_set, tmp_path, mutation):
    proposal = _proposal(ram_set)
    receipt = proposal["audit"]
    candidate = receipt["candidates"][0]
    if mutation == "version":
        receipt["version"] = True
    elif mutation == "transport":
        receipt["transport"] = "legacy_wav_ram"
    elif mutation == "old_report":
        proposal["audit"] = {"format_version": 1, "ok": True, "status": "passed",
                             "algorithm_build": proposal["binding"]["build"]}
    elif mutation == "order":
        candidate["clip_id"] = "001_k2"
    elif mutation == "topn":
        receipt["clips"] = 2
    elif mutation == "manifest":
        receipt["manifest_text"] += " "
    elif mutation == "source_manifest":
        receipt["source_manifest_text"] += " "
    elif mutation == "source_digest":
        candidate["source_spec_sha256"] = candidate["replay_spec_sha256"] = "0" * 64
    elif mutation == "pcm_digest":
        # Native hat keinen Referenzdigest: hier strikt SHA-Schema pruefen.
        candidate["replay_pcm_sha256"] = "not-a-sha256"
    elif mutation == "pcm_type":
        candidate["pcm"]["channels"] = True
    elif mutation == "lag":
        candidate["kick_lag_seconds"][1] = .006001
    elif mutation in {"before", "after"}:
        receipt[f"{mutation}_sha256"] = "0" * 64
    elif mutation == "rating_binding":
        receipt["binding"]["files"]["bewertung.csv"]["sha256"] = "0" * 64
    elif mutation == "cache_binding":
        receipt["binding"]["cache"][""][1] = "0" * 64
    else:
        receipt["binding"]["build"]["sha256"] = "0" * 64
    proposal["proposal_sha256"] = calibration._digest({k: v for k, v in proposal.items() if k != "proposal_sha256"})
    target = tmp_path / "export.json"
    for check in (lambda: calibration.validate_proposal(proposal),
                  lambda: calibration.apply_proposal(proposal),
                  lambda: calibration.export_proposal(proposal, target)):
        with pytest.raises(ValueError):
            check()
    assert not target.exists()


@pytest.mark.parametrize("target", ["rating", "source", "cache", "wal", "build"])
def test_bound_inputs_reject_mutation_before_audit_without_dsp(ram_set, monkeypatch, target):
    root, cache, _, calls, tracks = ram_set
    inputs = audit.prepare_candidate_inputs(root, cache)
    if target == "rating":
        path = root / "bewertung.csv"
        path.write_bytes(path.read_bytes().replace(b",4,", b",3,"))
    elif target == "source":
        Path(tracks[0].filePath).write_bytes(b"changed source identity")
    elif target == "cache":
        cache.write_bytes(b"changed cache identity")
    elif target == "wal":
        Path(str(cache) + "-wal").write_bytes(b"pending transaction")
    else:
        original = rate._algorithm_build_fingerprint
        monkeypatch.setattr(rate, "_algorithm_build_fingerprint", lambda: {**original(), "sha256": "0" * 64})
    with pytest.raises(ValueError):
        audit.audit_candidates(inputs)
    assert calls == []


@pytest.mark.parametrize("when", ["during_audit", "before_fit", "during_fit"])
def test_ratings_rechecked_after_audit_and_fit(ram_set, monkeypatch, when):
    root, cache, *_ = ram_set
    inputs = audit.prepare_candidate_inputs(root, cache)
    rating_path = root / "bewertung.csv"

    def mutate():
        rating_path.write_bytes(rating_path.read_bytes().replace(b",4,", b",3,"))

    if when == "during_audit":
        original = renderer.render_transition_clip
        def render(*args):
            original(*args)
            mutate()
        monkeypatch.setattr(renderer, "render_transition_clip", render)
        with pytest.raises(ValueError):
            audit.audit_candidates(inputs)
        return
    receipt = audit.audit_candidates(inputs)
    if when == "before_fit":
        mutate()
    else:
        original = rate._compute_candidate_fit
        def fit(*args):
            value = original(*args)
            mutate()
            return value
        monkeypatch.setattr(rate, "_compute_candidate_fit", fit)
    with pytest.raises(ValueError):
        rate.fit_candidates(inputs, receipt)


@pytest.mark.parametrize("mismatch", [False, True])
def test_legacy_transport_reads_reference_once_and_renders_once(ram_set, monkeypatch, mismatch):
    # Transport-Unit-Test: virtueller Legacy-Lesebackend, keine WAV-Datei/DB.
    root, cache, _, calls, _ = ram_set
    data = audit.prepare_candidate_inputs(root, cache).as_dict()
    from hpg_core.hearing_sources import SOURCE_MANIFEST_NAME
    data["binding"]["files"].pop(SOURCE_MANIFEST_NAME)
    data.update(transport="legacy_wav_ram", specs={}, source_manifest_text=None)
    inputs = audit.CandidateInputs(audit._json_bytes(data))
    monkeypatch.setattr(audit, "verify_candidate_inputs", lambda _: None)
    signal = np.zeros((800, 2), dtype=np.float32)
    signal[::100] = .5
    if mismatch:
        signal[0, 0] += .001
    reference = io.BytesIO()
    sf.write(reference, signal, 8000, subtype="PCM_16", format="WAV")
    actual_compare = audit._pcm_evidence
    reads = []
    def compare(path, replay, cid):
        assert path == root / "clips/001_k1.wav"
        reads.append(path)
        return actual_compare(io.BytesIO(reference.getvalue()), replay, cid)
    monkeypatch.setattr(audit, "_pcm_evidence", compare)
    if mismatch:
        with pytest.raises(ValueError, match="PCM stimmt nicht"):
            audit.audit_candidates(inputs)
        assert len(calls) == len(reads) == 1
        return
    receipt = audit.audit_candidates(inputs)
    assert receipt.as_dict()["transport"] == "legacy_wav_ram"
    assert receipt.as_dict()["evidence_kind"] == "reference_pcm_verified_replay"
    candidate = receipt.as_dict()["candidates"][0]
    assert candidate["reference_pcm_sha256"] == candidate["replay_pcm_sha256"]
    assert len(calls) == len(reads) == 1
    rate.fit_candidates(inputs, receipt)
    assert len(calls) == len(reads) == 1
    for mutation in ("pcm", "purpose", "kind", "source_field"):
        altered = receipt.as_dict()
        if mutation == "pcm":
            altered["candidates"][0]["reference_pcm_sha256"] = "0" * 64
        elif mutation == "purpose":
            altered["purpose"] = "research"
        elif mutation == "kind":
            altered["evidence_kind"] = "spec_verified_ram_replay"
        else:
            altered["candidates"][0]["source_spec_sha256"] = "0" * 64
        with pytest.raises(ValueError):
            audit.validate_ram_receipt(altered, data["binding"])
        with pytest.raises(ValueError):
            rate.fit_candidates(inputs, audit.CandidateAuditReceipt(audit._json_bytes(altered)))
    assert len(calls) == len(reads) == 1


@pytest.mark.parametrize("gate", ["harmonic", "overall", "groove", "topn"])
def test_producer_gates_not_relaxed_in_ram(ram_set, monkeypatch, gate):
    root, cache, _, calls, _ = ram_set
    candidate = _candidate()
    if gate == "harmonic":
        candidate.teilwerte["harmonic"] = 0.
    elif gate == "overall":
        candidate.score = 0.
    elif gate == "groove":
        candidate.teilwerte["groove"] = 0.
    else:
        # Zwei Replay-Kandidaten bei einem publizierten Top-N mit Maximum zwei.
        path = root / rate.KANDIDATEN_MANIFEST_NAME
        manifest = json.loads(path.read_bytes())
        manifest["render_args"]["max_versionen_pro_paar"] = 2
        path.write_text(json.dumps(manifest))
        from hpg_core.hearing_sources import SOURCE_MANIFEST_NAME, _fingerprint
        source_path = root / SOURCE_MANIFEST_NAME
        source_manifest = json.loads(source_path.read_bytes())
        source_manifest["immutable_metadata"][rate.KANDIDATEN_MANIFEST_NAME] = _fingerprint(path)
        source_path.write_text(json.dumps(source_manifest))
    monkeypatch.setattr(audit, "rank_pair_candidates", lambda *a, **k: [candidate] * (2 if gate == "topn" else 1))
    with pytest.raises(ValueError, match="Gate|Top-N"):
        audit.audit_candidates(audit.prepare_candidate_inputs(root, cache))
    assert calls == []


def test_fit_requires_receipt_and_complete_human_ratings(ram_set):
    root, cache, *_ = ram_set
    inputs = audit.prepare_candidate_inputs(root, cache)
    with pytest.raises(ValueError, match="Receipt"):
        rate.fit_candidates(inputs, None)
    path = root / "bewertung.csv"
    path.write_bytes(path.read_bytes().replace(b",4,", b",,"))
    inputs = audit.prepare_candidate_inputs(root, cache)
    receipt = audit.audit_candidates(inputs)
    with pytest.raises(ValueError):
        rate.fit_candidates(inputs, receipt)


def test_real_dsp_ram_replay_has_one_render_two_loads_and_actual_lags(ram_set, monkeypatch):
    """Echter DSP auf RAM-Signalen; nur Quell-Loader und Cache-Ranking sind Fixtures."""
    from hpg_core.hearing_sources import SOURCE_MANIFEST_NAME
    root, cache, op, _, tracks = ram_set
    for track in tracks:
        track.bpm = 120.
        track.first_downbeat = 0.
        track.downbeat_confidence = .5
    path = root / "merkmale.csv"
    rows = rate.lies_csv(path)
    rows[0]["bpm_b"] = "120"
    _csv(path, rate.MERKMALE_KANDIDATEN_SPALTEN, rows)
    # Nur das eigene synthetische Quellmanifest fuer diese Fixture neu erfassen.
    (root / SOURCE_MANIFEST_NAME).unlink()
    sink = SourceRenderSink(root, (Path(tracks[0].filePath).parent,))
    rate.rendere_kandidat(*tracks, _candidate(), "001", 1, root / "clips", render_sink=sink.emit)
    write_source_manifest(root, "kandidaten", sink)
    loads, renders = [], []

    def load(path, start, duration, sr):
        loads.append((path, start, duration, sr))
        time = start + np.arange(int(round(duration * sr))) / sr
        phase = np.mod(time, .5)
        signal = .4 * np.sin(2 * np.pi * 60 * phase) * np.exp(-phase * 35)
        return np.column_stack((signal, signal)).astype(np.float32)

    def render(spec, output):
        assert not isinstance(output, (Path, str))
        renders.append(spec)
        return _REAL_RENDER(spec, output)

    monkeypatch.setattr(renderer, "_load_segment", load)
    monkeypatch.setattr(renderer, "render_transition_clip", render)
    monkeypatch.setattr(renderer, "_synchronize_and_verify_kicks", _REAL_SYNC)
    monkeypatch.setattr(renderer, "_kick_lags_across_overlap", _REAL_LAGS)
    proposal = calibration.compute_proposal(root, cache, operation_root=op, operation_id="1" * 32)
    calibration.validate_proposal(proposal)
    assert len(renders) == 1
    assert len(loads) == 2
    candidate = proposal["audit"]["candidates"][0]
    assert len(candidate["kick_lag_seconds"]) == 3
    assert all(abs(lag) <= renderer.KICK_SYNC_MAX_ERROR_SECONDS for lag in candidate["kick_lag_seconds"])
    assert candidate["source_spec_sha256"] == candidate["replay_spec_sha256"]
    assert len(candidate["replay_pcm_sha256"]) == 64
    assert "reference_pcm_sha256" not in candidate
    assert not list(op.rglob("*.wav"))


@pytest.mark.parametrize("schema", ["legacy", "three_notes"])
def test_native_gate_pass_returns_updates_without_publishing(ram_set, monkeypatch, schema):
    from hpg_core import candidate_preferences as cp
    from hpg_core.hearing_sources import SOURCE_MANIFEST_NAME, _fingerprint
    root, cache, op, calls, _ = ram_set
    if schema == "three_notes":
        manifest_path = root / rate.KANDIDATEN_MANIFEST_NAME
        manifest = json.loads(manifest_path.read_bytes())
        manifest.update(format_version=2, rating_schema="three_notes_v1")
        manifest_path.write_text(json.dumps(manifest))
        _csv(root / "bewertung.csv", rate.BEWERTUNG_DREINOTEN_SPALTEN, [{
            "pair_id": "001", "clip_id": "001_k1", "track_note": "4", "technik_note": "4",
            "gesamt_note": "4", "gewaehlt": "1", "zeit": ""}])
        source_path = root / SOURCE_MANIFEST_NAME
        source = json.loads(source_path.read_bytes())
        source["immutable_metadata"][rate.KANDIDATEN_MANIFEST_NAME] = _fingerprint(manifest_path)
        source_path.write_text(json.dumps(source))
        monkeypatch.setattr(rate, "fit_dreinoten_genre", lambda *a: (
            {f: .1 for f in rate.KANDIDATEN_TEILWERTE}, {"uebernommen": True, "grund": "synthetic gate pass"}))
    else:
        monkeypatch.setattr(rate, "_fit_kandidaten_genre", lambda *a: (
            {f: .1 for f in rate.KANDIDATEN_TEILWERTE}, ["pssi_phrase"],
            {"uebernommen": True, "grund": "synthetic gate pass"}))
    monkeypatch.setattr(cp, "merge_user_preferences_atomically", lambda *a, **k: pytest.fail("Fit darf nicht publizieren"))
    result = calibration.compute_proposal(root, cache, operation_root=op, operation_id="1" * 32)
    calibration.validate_proposal(result)
    assert result["fit_status"] == "passed"
    assert set(result["gate_updates"]) == {"Psytrance"}
    assert len(calls) == 1
    assert not (op / "child_preferences.json").exists()


def test_existing_ram_size_limit_is_enforced(ram_set, monkeypatch):
    from hpg_core import hearing_playback
    root, cache, *_ = ram_set
    monkeypatch.setattr(hearing_playback, "MAX_PLAYBACK_BYTES", 64)
    with pytest.raises(ValueError, match="Playback-Limit"):
        audit.audit_candidates(audit.prepare_candidate_inputs(root, cache))


def test_genre_argument_keeps_existing_candidate_fit_semantics(ram_set, monkeypatch):
    root, cache, op, *_ = ram_set
    monkeypatch.setattr(rate, "_fit_kandidaten_genre", lambda *a: (
        {f: .1 for f in rate.KANDIDATEN_TEILWERTE}, None, {"uebernommen": True, "grund": "synthetic gate pass"}))
    result = calibration.compute_proposal(root, cache, operation_root=op, operation_id="1" * 32,
                                         genres=("Techno",))
    assert set(result["gate_updates"]) == {"Psytrance"}


@pytest.mark.parametrize("target", ["source", "cache", "wal"])
def test_source_and_cache_mutations_during_fit_are_rejected(ram_set, monkeypatch, target):
    root, cache, _, _, tracks = ram_set
    inputs = audit.prepare_candidate_inputs(root, cache)
    receipt = audit.audit_candidates(inputs)
    original = rate._compute_candidate_fit
    def fit(*args):
        value = original(*args)
        path = Path(tracks[0].filePath) if target == "source" else cache if target == "cache" else Path(str(cache) + "-wal")
        path.write_bytes(b"changed during fit")
        return value
    monkeypatch.setattr(rate, "_compute_candidate_fit", fit)
    with pytest.raises(ValueError):
        rate.fit_candidates(inputs, receipt)


def test_export_valid_native_receipt_and_canonical_binding_roundtrip(ram_set, tmp_path):
    result = _proposal(ram_set)
    target = calibration.export_proposal(result, tmp_path / "report.json")
    roundtrip = json.loads(target.read_bytes())
    calibration.validate_proposal(roundtrip)
    calibration.verify_binding(roundtrip["binding"])
    assert roundtrip["audit"]["transport"] == "source_refs_ram"


def test_pure_three_notes_result_never_claims_activation(ram_set, monkeypatch):
    root, cache, *_ = ram_set
    inputs = audit.prepare_candidate_inputs(root, cache).as_dict()
    manifest = inputs["manifest"] | {"rating_schema": "three_notes_v1"}
    ratings = [{"pair_id": "001", "clip_id": "001_k1", "track_note": "4", "technik_note": "4",
                "gesamt_note": "4", "gewaehlt": "1", "zeit": ""}]
    monkeypatch.setattr(rate, "fit_dreinoten_genre", lambda *a: (
        {f: .1 for f in rate.KANDIDATEN_TEILWERTE}, {"uebernommen": True, "grund": "synthetic pass"}))
    value = rate._compute_candidate_fit(inputs["rows"], ratings, manifest,
                                       {p.lower(): "Psytrance" for p in inputs["binding"]["sources"]}, 1)
    assert value["gate_updates"]
    assert value["ergebnis"]["aktiviert_candidate_preferences"] is False


@pytest.mark.parametrize("stale", ["build", "cache"])
def test_stale_binding_is_hard_rejected_without_touching_ratings_or_data(ram_set, stale):
    from hpg_core.hearing_sources import SOURCE_MANIFEST_NAME, _fingerprint
    root, cache, _, calls, _ = ram_set
    manifest_path = root / rate.KANDIDATEN_MANIFEST_NAME
    manifest = json.loads(manifest_path.read_bytes())
    if stale == "build":
        manifest["algorithm_build"]["sha256"] = "0" * 64
        reason = "Algorithmus-/Build-Digest"
    else:
        manifest["cache"]["version"] = audit.CACHE_VERSION - 1
        reason = "cache.version"
    manifest_path.write_text(json.dumps(manifest))
    source_path = root / SOURCE_MANIFEST_NAME
    source = json.loads(source_path.read_bytes())
    source["immutable_metadata"][rate.KANDIDATEN_MANIFEST_NAME] = _fingerprint(manifest_path)
    source_path.write_text(json.dumps(source))
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    with pytest.raises(ValueError, match=reason):
        audit.prepare_candidate_inputs(root, cache)
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before
    assert calls == []


def test_research_status_is_rejected_by_normal_ram_fit_entry(ram_set):
    from hpg_core.hearing_sources import SOURCE_MANIFEST_NAME
    root, cache, op, calls, _ = ram_set
    path = root / SOURCE_MANIFEST_NAME
    source = json.loads(path.read_bytes())
    source["status"] = "experimental_research"
    path.write_text(json.dumps(source))
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    with pytest.raises(ValueError):
        calibration.compute_proposal(root, cache, operation_root=op, operation_id="1" * 32)
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before
    assert calls == []
    assert not (op / "child_preferences.json").exists()


@pytest.mark.parametrize("purpose", [None, True, "research", "experimental_research", "", "REGULAR", "missing"])
def test_delta_purpose_rejected_by_audit_fit_validate_apply_export(ram_set, tmp_path, purpose):
    root, cache, op, calls, _ = ram_set
    inputs = audit.prepare_candidate_inputs(root, cache)
    receipt = audit.audit_candidates(inputs)
    data = inputs.as_dict()
    report = receipt.as_dict()
    proposal = {"format": "hpg_calibration_proposal", "version": 2, "operation_id": "1" * 32,
                "binding": data["binding"], "audit_passed": True, "audit": report,
                "fit_status": "not_requested", "gate_updates": {}, "diagnose": {},
                "single_proposal": None, "live_applied": False, "output": ""}
    if purpose == "missing":
        data["binding"].pop("purpose")
        report.pop("purpose")
        report["binding"].pop("purpose")
    else:
        data["binding"]["purpose"] = purpose
        report["binding"]["purpose"] = report["purpose"] = purpose
    # Auch mit konsistent neu berechneten Digests darf kein Zweck umgedeutet werden.
    report["before_sha256"] = report["after_sha256"] = calibration._digest(report["binding"])
    proposal["proposal_sha256"] = calibration._digest(proposal)
    bad_inputs = audit.CandidateInputs(audit._json_bytes(data))
    bad_receipt = audit.CandidateAuditReceipt(audit._json_bytes(report))
    count = len(calls)
    target = tmp_path / "purpose-report.json"
    for check in (lambda: audit.audit_candidates(bad_inputs),
                  lambda: rate.fit_candidates(inputs, bad_receipt),
                  lambda: calibration.validate_proposal(proposal),
                  lambda: calibration.apply_proposal(proposal),
                  lambda: calibration.export_proposal(proposal, target)):
        with pytest.raises(ValueError):
            check()
    assert len(calls) == count == 1
    assert not target.exists()
    assert not (op / "child_preferences.json").exists()


@pytest.mark.parametrize("mutation", ["receipt_v1", "proposal_v1", "input_v1", "input_extra",
                                     "native_reference_pcm", "evidence_kind", "source_digest_mismatch"])
def test_delta_versions_and_evidence_contract_fail_closed(ram_set, tmp_path, mutation):
    root, cache, *_ = ram_set
    inputs = audit.prepare_candidate_inputs(root, cache)
    proposal = _proposal(ram_set)
    report = proposal["audit"]
    if mutation.startswith("input_"):
        data = inputs.as_dict()
        if mutation == "input_v1":
            data["version"] = 1
        else:
            data["research"] = True
        with pytest.raises(ValueError):
            audit.audit_candidates(audit.CandidateInputs(audit._json_bytes(data)))
        return
    if mutation == "receipt_v1":
        report["version"] = 1
    elif mutation == "proposal_v1":
        proposal["version"] = 1
    elif mutation == "native_reference_pcm":
        report["candidates"][0]["reference_pcm_sha256"] = report["candidates"][0]["replay_pcm_sha256"]
    elif mutation == "evidence_kind":
        report["evidence_kind"] = "reference_pcm_verified_replay"
    else:
        report["candidates"][0]["source_spec_sha256"] = "0" * 64
    proposal["proposal_sha256"] = calibration._digest({k: v for k, v in proposal.items() if k != "proposal_sha256"})
    target = tmp_path / "version-report.json"
    for check in (lambda: calibration.validate_proposal(proposal),
                  lambda: calibration.apply_proposal(proposal),
                  lambda: calibration.export_proposal(proposal, target)):
        with pytest.raises(ValueError):
            check()
    if mutation != "proposal_v1":
        with pytest.raises(ValueError):
            rate.fit_candidates(inputs, audit.CandidateAuditReceipt(audit._json_bytes(report)))
    assert not target.exists()


@pytest.mark.parametrize("mutation", ["source_version", "source_purpose", "producer_version", "producer_purpose"])
def test_delta_regular_derivation_requires_exact_existing_schemas(ram_set, mutation):
    from hpg_core.hearing_sources import SOURCE_MANIFEST_NAME, _fingerprint
    root, cache, _, calls, _ = ram_set
    source_path = root / SOURCE_MANIFEST_NAME
    source = json.loads(source_path.read_bytes())
    if mutation.startswith("source_"):
        if mutation == "source_version":
            source["format_version"] = 99
        else:
            source["purpose"] = "research"
    else:
        path = root / rate.KANDIDATEN_MANIFEST_NAME
        producer = json.loads(path.read_bytes())
        if mutation == "producer_version":
            producer["format_version"] = 99
        else:
            producer["purpose"] = "research"
        path.write_text(json.dumps(producer))
        source["immutable_metadata"][rate.KANDIDATEN_MANIFEST_NAME] = _fingerprint(path)
    source_path.write_text(json.dumps(source))
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    with pytest.raises(ValueError):
        audit.prepare_candidate_inputs(root, cache)
    assert calls == []
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before


@pytest.mark.parametrize("mutation", ["version", "purpose"])
def test_delta_unknown_legacy_producer_is_not_defaulted_to_regular(ram_set, monkeypatch, mutation):
    from hpg_core.hearing_sources import SOURCE_MANIFEST_NAME
    from hpg_core import hearing_ratings
    root, cache, _, calls, _ = ram_set
    # Virtuelle Legacy-Eingabe prueft das Manifest-Gate vor jeder Audioanforderung.
    (root / SOURCE_MANIFEST_NAME).unlink()
    (root / "clips").mkdir()
    monkeypatch.setattr(hearing_ratings, "load_session", lambda _: {"mode": "kandidaten"})
    path = root / rate.KANDIDATEN_MANIFEST_NAME
    manifest = json.loads(path.read_bytes())
    if mutation == "version":
        manifest["format_version"] = 99
    else:
        manifest["purpose"] = "research"
    path.write_text(json.dumps(manifest))
    ratings = (root / "bewertung.csv").read_bytes()
    with pytest.raises(ValueError, match="Manifest|format_version"):
        calibration.snapshot(root, cache, seed=1, genres=())
    assert (root / "bewertung.csv").read_bytes() == ratings
    assert calls == []


def test_delta_lags_are_measured_from_single_actual_replay_not_cached(ram_set, monkeypatch):
    root, cache, _, calls, _ = ram_set
    measured = []
    def lags(*args):
        measured.append(args)
        return [.001, -.002, .003]
    monkeypatch.setattr(renderer, "_kick_lags_across_overlap", lags)
    inputs = audit.prepare_candidate_inputs(root, cache)
    receipt = audit.audit_candidates(inputs)
    assert receipt.as_dict()["candidates"][0]["kick_lag_seconds"] == [.001, -.002, .003]
    rate.fit_candidates(inputs, receipt)
    assert len(calls) == len(measured) == 1


def test_delta_actual_pcm_digest_tamper_breaks_proposal_checksum(ram_set):
    proposal = _proposal(ram_set)
    proposal["audit"]["candidates"][0]["replay_pcm_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="veraendert"):
        calibration.validate_proposal(proposal)
