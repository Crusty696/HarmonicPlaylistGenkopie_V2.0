"""Kalibrierung trennt Berechnung, Gates und produktive Uebernahme."""
import json
from pathlib import Path

import pytest

from tests.test_hearing_sources import source_fixture
from tests.test_audit_candidate_set import candidate_set


def _csv_single(tmp_path, *, rated=False):
    # Nur CSV-Vertrag: keine Audiodatei, kein Cache und keine Qualitaetsbehauptung.
    import csv
    from tools import rate_transitions as rate
    root = tmp_path / "csv-single"
    root.mkdir()
    for name, fields, rows in (
        ("merkmale.csv", ("pair_id", *rate.ALLE_FAKTOREN), [
            {"pair_id": str(i), **{f: (i + 1) / 4 for f in rate.ALLE_FAKTOREN}}
            for i in range(2)]),
        ("bewertung.csv", ("pair_id", "clip", "bewertung"), [
            {"pair_id": str(i), "clip": f"clips/{i}.wav", "bewertung": str(2 + 2 * i) if rated else ""}
            for i in range(2)]),
    ):
        with (root / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    return root


def test_csv_single_existing_clips_are_never_traversed_read_hashed_or_copied(tmp_path, monkeypatch):
    from hpg_core import hearing_sources
    from hpg_core.hearing_calibration import compute_proposal, validate_proposal
    root = _csv_single(tmp_path, rated=True)
    clips = root / "clips"
    nested = clips / "nested"
    nested.mkdir(parents=True)
    audio = nested / "valuable.wav"
    audio.write_bytes(b"synthetic existing audio must remain untouched")
    (root / "gewichte.json").write_bytes(b"old output")
    real_rglob, real_iterdir = Path.rglob, Path.iterdir
    real_read, real_open = Path.read_bytes, Path.open
    real_fingerprint = hearing_sources._fingerprint
    def guard(path):
        if path == clips or clips in path.parents:
            pytest.fail("Legacy CSV-Fit darf den Clips-Unterbaum nicht betreten")
    def rglob(path, *args, **kwargs):
        # Rekursive Enumeration der Satzwurzel betritt ebenfalls clips/**.
        if path == root:
            pytest.fail("Legacy CSV-Fit darf die Satzwurzel nicht rekursiv durchlaufen")
        guard(path)
        return real_rglob(path, *args, **kwargs)
    def iterdir(path):
        guard(path)
        return real_iterdir(path)
    def read(path):
        guard(path)
        return real_read(path)
    def open_file(path, *args, **kwargs):
        guard(path)
        return real_open(path, *args, **kwargs)
    def fingerprint(path, *args, **kwargs):
        guard(Path(path))
        return real_fingerprint(path, *args, **kwargs)
    monkeypatch.setattr(Path, "rglob", rglob)
    monkeypatch.setattr(Path, "iterdir", iterdir)
    monkeypatch.setattr(Path, "read_bytes", read)
    monkeypatch.setattr(Path, "open", open_file)
    monkeypatch.setattr(hearing_sources, "_fingerprint", fingerprint)
    op = tmp_path / "operation"
    op.mkdir()
    monkeypatch.setenv("HPG_CANDIDATE_PREFERENCES_FILE", str(op / "child_preferences.json"))
    proposal = compute_proposal(root, None, operation_root=op, operation_id="1" * 32, seed=1)
    validate_proposal(proposal)
    assert proposal["fit_status"] == "passed"
    assert set(proposal["binding"]["files"]) == {"merkmale.csv", "bewertung.csv", "gewichte.json"}
    assert not list(op.rglob("*.wav"))
    with real_open(audio, "rb") as handle:
        assert handle.read() == b"synthetic existing audio must remain untouched"


@pytest.mark.parametrize("name", ["private.json", "extra.wav", "nested"])
def test_csv_single_rejects_unknown_root_metadata_without_traversal(tmp_path, name):
    from hpg_core.hearing_calibration import snapshot
    root = _csv_single(tmp_path)
    extra = root / name
    if name == "nested":
        extra.mkdir()
    else:
        extra.write_bytes(b"unknown root data")
    with pytest.raises(ValueError):
        snapshot(root, None, seed=1, genres=())


def test_csv_single_rejects_metadata_link(tmp_path):
    from hpg_core.hearing_calibration import snapshot
    root = _csv_single(tmp_path)
    metadata = root / "merkmale.csv"
    outside = tmp_path / "outside.csv"
    metadata.replace(outside)
    try:
        metadata.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"Metadaten-Link auf diesem Host nicht verfuegbar: {exc}")
    with pytest.raises(ValueError):
        snapshot(root, None, seed=1, genres=())


@pytest.mark.parametrize("old_output", [False, True])
def test_csv_single_real_fit_without_cache_audio_preserves_old_output(tmp_path, monkeypatch, old_output):
    from hpg_core.hearing_calibration import compute_proposal, validate_proposal, export_proposal
    root = _csv_single(tmp_path, rated=True)
    if old_output:
        (root / "gewichte.json").write_bytes(b"old output stays untouched")
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    op = tmp_path / "operation"
    op.mkdir()
    monkeypatch.setenv("HPG_CANDIDATE_PREFERENCES_FILE", str(op / "child_preferences.json"))
    proposal = compute_proposal(root, None, operation_root=op, operation_id="1" * 32, seed=1)
    validate_proposal(proposal)
    assert proposal["fit_status"] == "passed"
    assert proposal["single_proposal"]
    assert proposal["binding"]["cache_path"] is None
    assert proposal["binding"]["cache"] is None
    assert proposal["binding"]["sources"] == {}
    assert not proposal["audit_passed"] and not proposal["gate_updates"]
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before
    assert not list(op.rglob("*.wav"))
    export_proposal(proposal, tmp_path / "report.json")


@pytest.mark.parametrize("change", ["mutation", "creation", "removal"])
def test_csv_single_old_output_inventory_is_bound(tmp_path, change):
    from hpg_core.hearing_calibration import snapshot, verify_binding, _materialize
    root = _csv_single(tmp_path)
    old = root / "gewichte.json"
    if change != "creation":
        old.write_bytes(b"old")
    binding = snapshot(root, None, seed=1, genres=())
    op = tmp_path / "operation"
    op.mkdir()
    staged = _materialize(binding, op)
    assert not (staged / "gewichte.json").exists()
    if change == "removal":
        old.unlink()
    else:
        old.write_bytes(b"changed")
    with pytest.raises(ValueError):
        verify_binding(binding)


def test_csv_single_failed_real_fit_cannot_return_previous_output(tmp_path, monkeypatch):
    from hpg_core.hearing_calibration import compute_proposal, validate_proposal
    root = _csv_single(tmp_path)
    (root / "gewichte.json").write_text('{"old":true}')
    op = tmp_path / "operation"
    op.mkdir()
    monkeypatch.setenv("HPG_CANDIDATE_PREFERENCES_FILE", str(op / "child_preferences.json"))
    proposal = compute_proposal(root, None, operation_root=op, operation_id="1" * 32)
    validate_proposal(proposal)
    assert proposal["fit_status"] == "rejected"
    assert proposal["single_proposal"] is None
    assert not (op / "snapshot" / "gewichte.json").exists()
    assert (root / "gewichte.json").read_text() == '{"old":true}'


@pytest.mark.parametrize("cache_value", ["", "None", "missing.db"])
def test_csv_single_supplied_invalid_cache_is_not_ignored(tmp_path, cache_value):
    from hpg_core.hearing_calibration import snapshot
    root = _csv_single(tmp_path)
    with pytest.raises((ValueError, OSError)):
        snapshot(root, tmp_path / cache_value if cache_value == "missing.db" else cache_value, seed=1, genres=())


def test_source_single_without_cache_still_binds_originals(source_fixture):
    from hpg_core.hearing_calibration import snapshot, verify_binding
    root = _source_set(source_fixture)
    bound = snapshot(root, None, seed=1, genres=())
    assert bound["sources"]
    source_fixture[3].write_bytes(b"changed source")
    with pytest.raises(ValueError):
        verify_binding(bound)


def test_present_broken_source_manifest_never_falls_back_to_csv(tmp_path):
    from hpg_core.hearing_calibration import snapshot
    from hpg_core.hearing_sources import SOURCE_MANIFEST_NAME
    root = _csv_single(tmp_path)
    (root / SOURCE_MANIFEST_NAME).write_bytes(b"not a manifest")
    with pytest.raises(ValueError):
        snapshot(root, None, seed=1, genres=())


@pytest.mark.parametrize("mutation", ["cache_path", "cache", "sources", "source_marker", "candidate", "empty_file", "nonstring_file", "clip_binding"])
def test_csv_single_binding_exception_cannot_weaken_other_modes(tmp_path, monkeypatch, mutation):
    from hpg_core.hearing_calibration import compute_proposal, validate_proposal, _digest
    from hpg_core.hearing_sources import SOURCE_MANIFEST_NAME
    root = _csv_single(tmp_path)
    op = tmp_path / "operation"
    op.mkdir()
    monkeypatch.setenv("HPG_CANDIDATE_PREFERENCES_FILE", str(op / "child_preferences.json"))
    proposal = compute_proposal(root, None, operation_root=op, operation_id="1" * 32)
    bound = proposal["binding"]
    if mutation == "cache_path":
        bound["cache_path"] = str(tmp_path / "cache.db")
    elif mutation == "cache":
        bound["cache"] = {}
    elif mutation == "sources":
        bound["sources"] = []
    elif mutation == "source_marker":
        bound["files"][SOURCE_MANIFEST_NAME] = bound["files"]["merkmale.csv"]
    elif mutation == "empty_file":
        bound["files"][""] = bound["files"]["merkmale.csv"]
    elif mutation == "nonstring_file":
        bound["files"] = {7: bound["files"]["merkmale.csv"]}
    elif mutation == "clip_binding":
        bound["files"]["clips/old.wav"] = bound["files"]["merkmale.csv"]
    else:
        bound["mode"] = "kandidaten"
    proposal["proposal_sha256"] = _digest({k: v for k, v in proposal.items() if k != "proposal_sha256"})
    with pytest.raises(ValueError):
        validate_proposal(proposal)


def test_candidate_snapshot_cannot_drop_cache(candidate_set):
    from hpg_core.hearing_calibration import snapshot
    with pytest.raises(ValueError):
        snapshot(candidate_set[0], None, seed=1, genres=())


def test_source_single_proposal_cannot_drop_sources(source_fixture, tmp_path, monkeypatch):
    from hpg_core.hearing_calibration import validate_proposal, _digest
    proposal = _rejected_proposal(source_fixture, tmp_path, monkeypatch)
    proposal["binding"]["sources"] = {}
    proposal["proposal_sha256"] = _digest({k: v for k, v in proposal.items() if k != "proposal_sha256"})
    with pytest.raises(ValueError):
        validate_proposal(proposal)


def test_csv_single_supplied_valid_cache_remains_bound(tmp_path):
    from hpg_core.hearing_calibration import snapshot, verify_binding
    root = _csv_single(tmp_path)
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"isolated cache")
    bound = snapshot(root, cache, seed=1, genres=())
    assert bound["cache_path"] == str(cache)
    assert bound["cache"] is not None
    cache.write_bytes(b"changed cache")
    with pytest.raises(ValueError):
        verify_binding(bound)


def _source_set(source_fixture):
    from hpg_core.hearing_sources import write_source_manifest
    root, _spec, sink, *_ = source_fixture
    write_source_manifest(root, "einzel", sink)
    return root


@pytest.mark.parametrize("changed", ["rating", "original", "cache"])
def test_binding_rejects_rating_and_original_mutation(source_fixture, tmp_path, changed):
    from hpg_core.hearing_calibration import snapshot, verify_binding
    root = _source_set(source_fixture)
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"isolated cache")
    bound = snapshot(root, cache, seed=1, genres=())
    verify_binding(bound)
    target = root / "bewertung.csv" if changed == "rating" else source_fixture[3] if changed == "original" else cache
    target.write_bytes(target.read_bytes() + b"changed")
    with pytest.raises(ValueError):
        verify_binding(bound)


def _rejected_proposal(source_fixture, tmp_path, monkeypatch):
    from hpg_core.hearing_calibration import compute_proposal
    from tools import rate_transitions as rate
    root = _source_set(source_fixture)
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"isolated cache")
    op = tmp_path / "operation"
    op.mkdir()
    monkeypatch.setenv("HPG_CANDIDATE_PREFERENCES_FILE", str(op / "child_preferences.json"))
    monkeypatch.setattr(rate, "befehl_fit", lambda _args: 1)
    proposal = compute_proposal(root, cache, operation_root=op, operation_id="1" * 32, seed=1)
    monkeypatch.setenv("HPG_CANDIDATE_PREFERENCES_FILE", str(tmp_path / "live.json"))
    return proposal


@pytest.mark.parametrize("mutation", ["operation", "mode", "seed", "sources", "cache", "audit", "state"])
def test_proposal_rejects_malformed_schema_even_with_recomputed_digest(source_fixture, tmp_path, monkeypatch, mutation):
    from hpg_core.hearing_calibration import validate_proposal, _digest
    proposal = _rejected_proposal(source_fixture, tmp_path, monkeypatch)
    if mutation == "operation":
        proposal["operation_id"] = 7
    elif mutation == "mode":
        proposal["binding"]["mode"] = []
    elif mutation == "seed":
        proposal["binding"]["seed"] = True
    elif mutation == "sources":
        next(iter(proposal["binding"]["sources"].values()))["size"] = False
    elif mutation == "cache":
        proposal["binding"]["cache"] = {}
    elif mutation == "audit":
        proposal["audit_passed"] = "yes"
    else:
        proposal["fit_status"] = []
    proposal["proposal_sha256"] = _digest({k: v for k, v in proposal.items() if k != "proposal_sha256"})
    with pytest.raises(ValueError):
        validate_proposal(proposal)


def test_proposal_parent_operation_identity_is_required(source_fixture, tmp_path, monkeypatch):
    from hpg_core.hearing_calibration import validate_proposal
    proposal = _rejected_proposal(source_fixture, tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        validate_proposal(proposal, expected_operation_id="2" * 32)


@pytest.mark.parametrize("mode,status", [("einzel", "passed"), ("einzel", "not_requested"), ("kandidaten", "passed")])
def test_proposal_rejects_impossible_mode_state(source_fixture, tmp_path, monkeypatch, mode, status):
    from hpg_core.hearing_calibration import validate_proposal, _digest
    proposal = _rejected_proposal(source_fixture, tmp_path, monkeypatch)
    proposal["binding"]["mode"] = mode
    proposal["fit_status"] = status
    proposal["proposal_sha256"] = _digest({k: v for k, v in proposal.items() if k != "proposal_sha256"})
    with pytest.raises(ValueError):
        validate_proposal(proposal)


@pytest.mark.parametrize("target_kind", ["existing", "music", "session", "preferences", "audio_suffix"])
def test_export_cannot_overwrite_or_write_into_source_and_state(source_fixture, tmp_path, monkeypatch, target_kind):
    from hpg_core.hearing_calibration import export_proposal
    proposal = _rejected_proposal(source_fixture, tmp_path, monkeypatch)
    targets = {"existing": tmp_path / "valuable.json", "music": source_fixture[3].parent / "report.json",
               "session": source_fixture[0] / "report.json", "preferences": tmp_path / "live.json",
               "audio_suffix": tmp_path / "report.wav"}
    target = targets[target_kind]
    if target_kind == "existing":
        target.write_bytes(b"valuable")
    before = target.read_bytes() if target.exists() else None
    with pytest.raises(ValueError):
        export_proposal(proposal, target)
    assert (target.read_bytes() if target.exists() else None) == before


def test_export_new_report_is_no_clobber(source_fixture, tmp_path, monkeypatch):
    from hpg_core.hearing_calibration import export_proposal
    proposal = _rejected_proposal(source_fixture, tmp_path, monkeypatch)
    target = tmp_path / "report.json"
    assert export_proposal(proposal, target) == target
    assert json.loads(target.read_bytes()) == json.loads(json.dumps(proposal))
    with pytest.raises(ValueError):
        export_proposal(proposal, target)
    assert not list(tmp_path.glob(".hpg-report-*.tmp"))


@pytest.mark.parametrize("name", ["extra.wav", "extra.mp3", "private.json", "extra.db"])
def test_snapshot_rejects_extra_files_before_copy(source_fixture, tmp_path, name):
    from hpg_core.hearing_calibration import snapshot
    root = _source_set(source_fixture)
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"isolated cache")
    (root / name).write_bytes(b"valuable must remain")
    with pytest.raises(ValueError):
        snapshot(root, cache, seed=1, genres=())
    assert (root / name).read_bytes() == b"valuable must remain"


def test_stdout_buffer_is_bounded_in_bytes_and_entries():
    from hpg_core.hearing_calibration import _BoundedText
    stream = _BoundedText()
    stream.write("x" * 64000)
    for _ in range(10000):
        stream.write("overflow")
        stream.write("")
    assert len(stream.getvalue()) == 64000
    assert len(stream.parts) == 1


def test_calibration_setup_failure_is_reported_without_lost_signal(tmp_path, monkeypatch, qtbot):
    import tempfile
    from hpg_core.hearing_jobs import HearingCalibrationWorker
    def fail(**kwargs):
        raise OSError("synthetic temp setup failure")
    monkeypatch.setattr(tempfile, "mkdtemp", fail)
    worker = HearingCalibrationWorker(tmp_path, tmp_path / "cache.db")
    with qtbot.waitSignal(worker.completed, timeout=5000) as signal:
        worker.start()
    assert worker.wait(5000)
    assert not signal.args[0]["ok"]
    assert "synthetic temp setup failure" in signal.args[0]["output"]


def test_export_racing_target_preserves_foreign_bytes_and_cleans_owned_temp(source_fixture, tmp_path, monkeypatch):
    import os
    from hpg_core.hearing_calibration import export_proposal
    proposal = _rejected_proposal(source_fixture, tmp_path, monkeypatch)
    real_link = os.link
    target = tmp_path / "race.json"
    def racing_link(source, destination):
        Path(destination).write_bytes(b"foreign valuable data")
        return real_link(source, destination)
    monkeypatch.setattr(os, "link", racing_link)
    with pytest.raises(FileExistsError):
        export_proposal(proposal, target)
    assert target.read_bytes() == b"foreign valuable data"
    assert not list(tmp_path.glob(".hpg-report-*.tmp"))


def _waiting_calibration_child(connection, directory, cache, root, operation_id, fit, seed, genres):
    # Ausschliesslich synthetisches temporäres Audio als Cleanup-Vertragsfixture.
    import os
    import time
    import numpy as np
    import soundfile as sf
    sf.write(Path(root) / "synthetic-replay.wav", np.zeros(80), 8000)
    (Path(root) / "ready.json").write_text(json.dumps({"pid": os.getpid()}))
    while True:
        time.sleep(.1)


@pytest.mark.parametrize("termination", ["cancel", "timeout"])
def test_live_child_ends_before_own_temporary_audio_cleanup(tmp_path, monkeypatch, qtbot, termination):
    import multiprocessing
    import tempfile
    from hpg_core import hearing_calibration
    from hpg_core.hearing_jobs import HearingCalibrationWorker
    root = tmp_path / "owned-operation"
    root.mkdir()
    monkeypatch.setattr(tempfile, "mkdtemp", lambda **kwargs: str(root))
    monkeypatch.setattr(hearing_calibration, "calibration_child", _waiting_calibration_child)
    worker = HearingCalibrationWorker(tmp_path, tmp_path / "cache.db", timeout=2 if termination == "timeout" else 30)
    outputs = []
    worker.completed.connect(outputs.append)
    worker.start()
    qtbot.waitUntil(lambda: (root / "ready.json").exists(), timeout=10000)
    pid = json.loads((root / "ready.json").read_text())["pid"]
    assert (root / "synthetic-replay.wav").exists()
    if termination == "cancel":
        worker.request_cancel()
    qtbot.waitUntil(lambda: bool(outputs), timeout=10000)
    assert worker.wait(5000)
    assert not outputs[0]["ok"]
    assert outputs[0]["cancelled"] is (termination == "cancel")
    assert not root.exists()
    assert pid not in [child.pid for child in multiprocessing.active_children()]


def test_single_proposal_does_not_render_unneeded_audio(source_fixture, tmp_path, monkeypatch):
    from hpg_core.hearing_calibration import compute_proposal, validate_proposal
    from hpg_core import transition_renderer
    from tools import rate_transitions as rate
    root = _source_set(source_fixture)
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"isolated cache")
    op = tmp_path / "operation"
    op.mkdir()
    monkeypatch.setenv("HPG_CANDIDATE_PREFERENCES_FILE", str(op / "child_preferences.json"))
    monkeypatch.setattr(transition_renderer, "render_transition_clip", lambda *_args: pytest.fail("Einzel-Fit benoetigt kein Render-Audio"))
    def fit(args):
        (args.dir / "gewichte.json").write_text('{"diagnose":"synthetic service proof"}')
        return 0
    monkeypatch.setattr(rate, "befehl_fit", fit)
    proposal = compute_proposal(root, cache, operation_root=op, operation_id="1" * 32, seed=1)
    validate_proposal(proposal)
    assert proposal["fit_status"] == "passed"
    assert proposal["live_applied"] is False
    assert proposal["gate_updates"] == {}
    assert proposal["audit_passed"] is False
    assert not list(op.rglob("*.wav"))
    assert not (op / "child_preferences.json").exists()


def test_tampered_proposal_rejected_before_apply(source_fixture, tmp_path, monkeypatch):
    from hpg_core.hearing_calibration import compute_proposal, apply_proposal
    from tools import rate_transitions as rate
    root = _source_set(source_fixture)
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"isolated cache")
    op = tmp_path / "operation"
    op.mkdir()
    monkeypatch.setenv("HPG_CANDIDATE_PREFERENCES_FILE", str(op / "child_preferences.json"))
    monkeypatch.setattr(rate, "befehl_fit", lambda _args: 1)
    proposal = compute_proposal(root, cache, operation_root=op, operation_id="1" * 32, seed=1)
    proposal["live_applied"] = True
    with pytest.raises(ValueError, match="veraendert"):
        apply_proposal(proposal)


def test_real_spawn_fit_rejection_leaves_parent_environment_unchanged(source_fixture, tmp_path, monkeypatch, qtbot):
    from hpg_core.hearing_jobs import HearingCalibrationWorker
    root = _source_set(source_fixture)
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"isolated cache")
    live = tmp_path / "live-preferences.json"
    live.write_text('{"valuable":"untouched"}')
    monkeypatch.setenv("HPG_CANDIDATE_PREFERENCES_FILE", str(live))
    worker = HearingCalibrationWorker(root, cache, seed=1, timeout=30)
    with qtbot.waitSignal(worker.completed, timeout=35000) as signal:
        worker.start()
    assert worker.wait(5000)
    result = signal.args[0]
    assert result["ok"]
    assert result["proposal"]["fit_status"] == "rejected"
    assert not result["proposal"]["gate_updates"]
    assert live.read_text() == '{"valuable":"untouched"}'
    import os
    assert os.environ["HPG_CANDIDATE_PREFERENCES_FILE"] == str(live)
    assert "cleanup_warning" not in result


def test_calibration_cancel_before_start_returns_no_proposal(tmp_path, qtbot):
    from hpg_core.hearing_jobs import HearingCalibrationWorker
    worker = HearingCalibrationWorker(tmp_path, tmp_path / "missing.db")
    worker.request_cancel()
    with qtbot.waitSignal(worker.completed, timeout=5000) as signal:
        worker.start()
    assert worker.wait(5000)
    assert signal.args[0]["cancelled"]
    assert "proposal" not in signal.args[0]


def test_real_candidate_audit_fit_red_gates_returns_no_active_updates(candidate_set, tmp_path, monkeypatch):
    import numpy as np
    import soundfile as sf
    from tests.test_audit_candidate_set import _candidate, _write_csv
    from tools import rate_transitions as rate, audit_candidate_set as audit
    from hpg_core.hearing_calibration import compute_proposal, apply_proposal

    root, cache, _features, ratings = candidate_set
    for i, row in enumerate(ratings):
        row.update(note="4" if i < 15 else "2", gewaehlt="1")
    _write_csv(root / "bewertung.csv", rate.BEWERTUNG_KANDIDATEN_SPALTEN, ratings)
    monkeypatch.setattr(audit, "rank_pair_candidates", lambda *_args, **_kwargs: [_candidate()])
    signal = np.zeros((800, 2), dtype=np.float32)
    signal[::100] = .5
    def synthetic_render(a, b, pc, pid, n, output, **kwargs):
        path = output / f"{pid}_k{n}.wav"
        sf.write(path, signal, 8000, subtype="PCM_16")
        return path
    def producer(*args, **kwargs):
        path = synthetic_render(*args, **kwargs)
        return f"clips/{path.name}", "pro_eq_swap"
    monkeypatch.setattr(rate, "rendere_kandidat", producer)
    real_audit = audit.audit_set
    monkeypatch.setattr(audit, "audit_set", lambda directory, db: real_audit(directory, db, render=lambda *a, **k: (synthetic_render(*a, **k), [0., 0., 0.])))
    op = tmp_path / "operation"
    op.mkdir()
    monkeypatch.setenv("HPG_CANDIDATE_PREFERENCES_FILE", str(op / "child_preferences.json"))
    before = audit._fingerprint_tree(root)
    proposal = compute_proposal(root, cache, operation_root=op, operation_id="1" * 32, seed=1)
    assert proposal["audit_passed"] is True
    assert proposal["fit_status"] == "passed"
    assert proposal["gate_updates"] == {}
    assert proposal["live_applied"] is False
    assert proposal["diagnose"]
    assert audit._fingerprint_tree(root) == before
    assert not (op / "child_preferences.json").exists()
    with pytest.raises(ValueError, match="gatebestandener"):
        apply_proposal(proposal)
