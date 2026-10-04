"""Native Blindreferenzen: temporaeres synthetisches Audio, keine Kopien."""
import csv
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from hpg_core.hearing_workflow import CancellationToken


def _fixture(tmp_path, count=1):
    root = tmp_path / "sources"
    root.mkdir()
    rows = []
    for i in range(count):
        a, b = root / f"hpg_{i}.wav", root / f"baseline_{i}.wav"
        sf.write(a, np.full(800, .01 + i / 30), 8000)
        sf.write(b, np.full(800, .02 + i / 30), 8000)
        rows.append({"pair_id": f"original_{i}", "hpg_clip": a.name, "baseline_clip": b.name})
    manifest = root / "manifest.csv"
    _rows(manifest, rows)
    return manifest, tmp_path / "session", tmp_path / "private/key.json", root


def _rows(path, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=("pair_id", "hpg_clip", "baseline_clip"))
        writer.writeheader()
        writer.writerows(rows)


def _hashes(root):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.is_file()}


@pytest.mark.parametrize("count", [1, 4, 5])
def test_prepare_refs_balance_private_ids_no_audio(tmp_path, count):
    from hpg_core.hearing_blind import prepare_blind_references, load_blind_references
    manifest, output, key, root = _fixture(tmp_path, count)
    before = _hashes(root)
    public_path, returned_key = prepare_blind_references(manifest, output, key, root, seed=3)
    public = load_blind_references(public_path, key)
    private = json.loads(key.read_text(encoding="utf-8"))
    assert returned_key == key
    assert public["format"] == "hpg_local_ui_blind_refs"
    assert public["format_version"] == 1
    assert public["scope"] == "local_ui_blind" and public["metadata_blinded"] is False
    assert [p["pair_id"] for p in public["pairs"]] == [f"pair_{i:03d}" for i in range(1, count + 1)]
    assert "original_" not in public_path.read_text(encoding="utf-8")
    hpg_a = sum(p["candidate_a_system"] == "HPG" for p in private["pairs"])
    assert hpg_a == count // 2
    assert {p["original_pair_id"] for p in private["pairs"]} == {f"original_{i}" for i in range(count)}
    if count > 1:
        assert [p["original_pair_id"] for p in private["pairs"]] != [f"original_{i}" for i in range(count)]
    assert not list(output.rglob("*.wav")) and not list(output.rglob("*.mp3"))
    assert _hashes(root) == before
    assert not list(tmp_path.glob(".session.staging-*"))
    assert not list(key.parent.glob(".key.json.*"))


@pytest.mark.parametrize("fault", ["empty", "duplicate_id", "duplicate_pair", "identical", "outside", "missing", "samplerate", "channels", "duration"])
def test_original_validation_contract(tmp_path, fault):
    from hpg_core.hearing_blind import prepare_blind_references
    manifest, output, key, root = _fixture(tmp_path)
    rows = list(csv.DictReader(manifest.open(encoding="utf-8")))
    if fault == "empty":
        rows = []
    elif fault == "duplicate_id":
        rows += [dict(rows[0])]
    elif fault == "duplicate_pair":
        rows += [dict(rows[0], pair_id="other", hpg_clip=rows[0]["baseline_clip"], baseline_clip=rows[0]["hpg_clip"])]
    elif fault == "identical":
        rows[0]["baseline_clip"] = rows[0]["hpg_clip"]
    elif fault == "outside":
        outside = tmp_path / "outside.wav"
        sf.write(outside, np.zeros(800), 8000)
        rows[0]["hpg_clip"] = str(outside)
    elif fault == "missing":
        rows[0]["hpg_clip"] = "missing.wav"
    else:
        audio = np.full((800, 2) if fault == "channels" else (1000 if fault == "duration" else 800,), .3)
        sf.write(root / "baseline_0.wav", audio, 16000 if fault == "samplerate" else 8000)
    _rows(manifest, rows)
    with pytest.raises(ValueError):
        prepare_blind_references(manifest, output, key, root)
    assert not output.exists() and not key.exists()


@pytest.mark.parametrize("frames,accepted", [(879, True), (880, True), (881, False)])
def test_duration_boundary(tmp_path, frames, accepted):
    from hpg_core.hearing_blind import prepare_blind_references
    args = _fixture(tmp_path)
    sf.write(args[3] / "baseline_0.wav", np.full(frames, .2), 8000)
    if accepted:
        prepare_blind_references(*args)
    else:
        with pytest.raises(ValueError):
            prepare_blind_references(*args)


@pytest.mark.parametrize("target", ["output", "key", "key_inside"])
def test_existing_and_key_boundaries(tmp_path, target):
    from hpg_core.hearing_blind import prepare_blind_references
    manifest, output, key, root = _fixture(tmp_path)
    if target == "output":
        output.mkdir()
    elif target == "key":
        key.parent.mkdir()
        key.write_text("foreign", encoding="utf-8")
    else:
        key = output / "key.json"
    with pytest.raises((ValueError, FileExistsError)):
        prepare_blind_references(manifest, output, key, root)
    if target == "key":
        assert key.read_text(encoding="utf-8") == "foreign"


@pytest.mark.parametrize("fault", ["public", "version", "key", "source", "manifest_original_changed"])
def test_resume_frozen_binding_and_tamper(tmp_path, fault):
    from hpg_core.hearing_blind import prepare_blind_references, load_blind_references
    manifest, output, key, root = _fixture(tmp_path)
    public, _ = prepare_blind_references(manifest, output, key, root)
    if fault == "public":
        data = json.loads(public.read_text(encoding="utf-8"))
        data["pairs"][0]["pair_id"] = "altered"
        public.write_text(json.dumps(data), encoding="utf-8")
    elif fault == "version":
        data = json.loads(public.read_text(encoding="utf-8"))
        data["format_version"] = 2
        public.write_text(json.dumps(data), encoding="utf-8")
    elif fault == "key":
        data = json.loads(key.read_text(encoding="utf-8"))
        data["pairs"][0]["original_pair_id"] = "altered"
        key.write_text(json.dumps(data), encoding="utf-8")
    elif fault == "source":
        sf.write(root / "hpg_0.wav", np.full(800, .4), 8000)
    else:
        manifest.write_text("changed original manifest", encoding="utf-8")
        assert load_blind_references(public, key)["pairs"]
        return
    with pytest.raises(ValueError):
        load_blind_references(public, key)


def test_racing_key_never_clobbered(tmp_path, monkeypatch):
    from hpg_core import hearing_blind as blind
    manifest, output, key, root = _fixture(tmp_path)
    real_link = os.link
    def race(src, dst, **kw):
        key.write_text("foreign", encoding="utf-8")
        return real_link(src, dst, **kw)
    monkeypatch.setattr(blind.os, "link", race)
    with pytest.raises(FileExistsError):
        blind.prepare_blind_references(manifest, output, key, root)
    assert key.read_text(encoding="utf-8") == "foreign" and not output.exists()


@pytest.mark.parametrize("replace_key", [False, True])
def test_publication_failure_rollback_owns_only_key(tmp_path, monkeypatch, replace_key):
    from hpg_core import hearing_blind as blind
    from tools import rate_transitions as rate
    args = _fixture(tmp_path)
    key = args[2]
    def fail(stage, target):
        if replace_key:
            key.unlink()
            key.write_text("foreign", encoding="utf-8")
        raise OSError("publish failed")
    monkeypatch.setattr(rate, "_publiziere_staging", fail)
    with pytest.raises(OSError, match="orphan|publish failed"):
        blind.prepare_blind_references(*args)
    assert not args[1].exists()
    if replace_key:
        assert key.read_text(encoding="utf-8") == "foreign"
    else:
        assert not key.exists()
    assert not list(tmp_path.glob(".session.staging-*"))


@pytest.mark.parametrize("boundary", ["entry", "hash", "before_publish", "after_begin"])
def test_cancellation_boundaries(tmp_path, monkeypatch, boundary):
    from hpg_core import hearing_blind as blind
    from hpg_core.hearing_workflow import HearingCancelledError
    args = _fixture(tmp_path)
    token = CancellationToken()
    if boundary == "entry":
        token.request_cancel()
    elif boundary == "hash":
        real = blind._fingerprint
        def fingerprint(path, checkpoint):
            token.request_cancel()
            return real(path, checkpoint)
        monkeypatch.setattr(blind, "_fingerprint", fingerprint)
    elif boundary == "before_publish":
        real = token.begin_publish
        def begin():
            token.request_cancel()
            return real()
        monkeypatch.setattr(token, "begin_publish", begin)
    else:
        real = blind.os.link
        def link(*a, **k):
            assert token.state == token.PUBLISHING
            assert token.request_cancel() is False
            return real(*a, **k)
        monkeypatch.setattr(blind.os, "link", link)
        blind.prepare_blind_references(*args, cancel=token)
        assert token.state == token.COMPLETE
        return
    with pytest.raises(HearingCancelledError):
        blind.prepare_blind_references(*args, cancel=token)
    assert not args[1].exists() and not args[2].exists()


@pytest.mark.parametrize("changed", ["source", "manifest"])
def test_reread_before_publication_rejects_mutation(tmp_path, monkeypatch, changed):
    from hpg_core import hearing_blind as blind
    args = _fixture(tmp_path)
    original = blind.load_blind_references
    def mutate_then_validate(*a, **k):
        if changed == "source":
            sf.write(args[3] / "hpg_0.wav", np.full(800, .5), 8000)
        else:
            args[0].write_text("changed", encoding="utf-8")
        return original(*a, **k)
    monkeypatch.setattr(blind, "load_blind_references", mutate_then_validate)
    with pytest.raises(ValueError):
        blind.prepare_blind_references(*args)
    assert not args[1].exists() and not args[2].exists()
    assert not list(tmp_path.glob(".session.staging-*"))


@pytest.mark.parametrize("action", ["cancel", "mutate"])
def test_hash_checks_each_block_and_source_stability(tmp_path, action):
    from hpg_core.hearing_blind import _fingerprint
    path = tmp_path / "synthetic.bin"
    path.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    calls = []
    def checkpoint():
        calls.append(None)
        if len(calls) == 3:
            if action == "cancel":
                raise InterruptedError("inside hash")
            with path.open("ab") as f:
                f.write(b"changed")
    with pytest.raises(InterruptedError if action == "cancel" else ValueError):
        _fingerprint(path, checkpoint)
    assert len(calls) >= 3


def test_racing_output_preserved_key_rolled_back(tmp_path, monkeypatch):
    from hpg_core import hearing_blind as blind
    from tools import rate_transitions as rate
    args = _fixture(tmp_path)
    real = rate._publiziere_staging
    def race(stage, target):
        target.mkdir()
        (target / "foreign.txt").write_text("foreign", encoding="utf-8")
        return real(stage, target)
    monkeypatch.setattr(rate, "_publiziere_staging", race)
    with pytest.raises(FileExistsError):
        blind.prepare_blind_references(*args)
    assert (args[1] / "foreign.txt").read_text(encoding="utf-8") == "foreign"
    assert not args[2].exists()


@pytest.mark.parametrize("fault", ["duplicate_json", "bool_version", "extra_field", "wrong_key_version", "frozen_bytes"])
def test_loader_strict_schemas(tmp_path, fault):
    from hpg_core.hearing_blind import prepare_blind_references, load_blind_references
    args = _fixture(tmp_path)
    public, key = prepare_blind_references(*args)
    data = json.loads(public.read_text(encoding="utf-8"))
    private = json.loads(key.read_text(encoding="utf-8"))
    if fault == "duplicate_json":
        public.write_text('{"format": "x",' + public.read_text(encoding="utf-8")[1:], encoding="utf-8")
    elif fault == "wrong_key_version":
        private["format_version"] = 2
        key.write_text(json.dumps(private), encoding="utf-8")
    elif fault == "frozen_bytes":
        private["manifest"]["bytes_base64"] = "eA=="
        key.write_text(json.dumps(private), encoding="utf-8")
    else:
        if fault == "bool_version":
            data["format_version"] = True
        else:
            data["extra"] = "x"
        public.write_text(json.dumps(data), encoding="utf-8")
        private["public_sha256"] = hashlib.sha256(public.read_bytes()).hexdigest()
        key.write_text(json.dumps(private), encoding="utf-8")
    with pytest.raises(ValueError):
        load_blind_references(public, key)


def test_sfinfo_mutation_rejected(tmp_path, monkeypatch):
    from hpg_core import hearing_blind as blind
    args = _fixture(tmp_path)
    real = blind.sf.info
    def mutate(path):
        info = real(path)
        with Path(path).open("ab") as f:
            f.write(b"changed")
        return info
    monkeypatch.setattr(blind.sf, "info", mutate)
    with pytest.raises(ValueError, match="sf.info"):
        blind.prepare_blind_references(*args)
    assert not args[1].exists() and not args[2].exists()
