"""Isolierte Vertraege fuer private Hoertest-Snapshots."""
import json
from dataclasses import replace

import pytest

from hpg_core.models import Track


def test_snapshot_is_detached_and_filters_other_folders(tmp_path):
    from hpg_core.hearing_managed import freeze_tracks
    root = tmp_path / "music"
    root.mkdir()
    track = Track(str(root / "a.wav"), "a.wav", duration=120., bpm=120., analysis_mode="librosa_full_or_tail")
    other = Track(str(tmp_path / "other.wav"), "other.wav", duration=120., bpm=120.)
    snapshots = freeze_tracks([track, other], root)
    track.fileName = "changed"
    assert len(snapshots) == 1
    assert json.loads(snapshots[0])["fileName"] == "a.wav"


def test_private_database_strict_reader_and_reopen_binding(tmp_path, monkeypatch):
    from hpg_core.hearing_managed import freeze_tracks, managed_config, write_snapshot, bind_set, resolve_association
    from tools.rate_transitions import lade_tracks_aus_cache
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    root = tmp_path / "music"
    root.mkdir()
    track = Track(str(root / "a.wav"), "a.wav", duration=120., bpm=120., analysis_mode="librosa_full_or_tail")
    config = managed_config(root, mode="einzel")
    write_snapshot(config, freeze_tracks([track], root))
    assert [t.filePath for t in lade_tracks_aus_cache(config.cache)] == [track.filePath]
    config.output_dir.mkdir()
    (config.output_dir / "hearing_source_manifest.json").write_text("{}")
    bind_set(config)
    assert resolve_association(config.output_dir) == config.cache
    assert not (config.output_dir / "association.json").exists()
    with config.cache.open("ab") as stream:
        stream.write(b"tamper")
    with pytest.raises(ValueError, match="Hash"):
        resolve_association(config.output_dir)


def test_private_writer_rejects_escape_and_reuse(tmp_path, monkeypatch):
    from hpg_core.hearing_managed import freeze_tracks, managed_config, write_snapshot
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    root = tmp_path / "music"
    root.mkdir()
    snapshots = freeze_tracks([Track(str(root / "a.wav"), "a.wav", duration=120., bpm=120., analysis_mode="librosa_full_or_tail")], root)
    config = managed_config(root, mode="einzel")
    with pytest.raises(ValueError):
        write_snapshot(replace(config, cache=tmp_path / "escape.sqlite"), snapshots)
    write_snapshot(config, snapshots)
    before = config.cache.read_bytes()
    with pytest.raises(FileExistsError):
        write_snapshot(config, snapshots)
    assert config.cache.read_bytes() == before


def test_old_set_has_no_implicit_cache(tmp_path, monkeypatch):
    from hpg_core.hearing_managed import resolve_association
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    old = tmp_path / "set"
    old.mkdir()
    assert resolve_association(old) is None


def test_failed_prepare_removes_only_its_private_snapshot(tmp_path, monkeypatch):
    from hpg_core.hearing_managed import managed_config, freeze_tracks
    from hpg_core.hearing_jobs import HearingPrepareWorker
    from hpg_core import hearing_workflow
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    root = tmp_path / "music"
    root.mkdir()
    config = managed_config(root, mode="einzel")
    track = Track(str(root / "a.wav"), "a.wav", duration=120., bpm=120., analysis_mode="librosa_full_or_tail")
    def fail(*args, **kwargs):
        raise ValueError("prepare failed")
    monkeypatch.setattr(hearing_workflow, "create_set", fail)
    worker = HearingPrepareWorker(config, managed_metadata=freeze_tracks([track], root))
    results = []
    worker.completed.connect(results.append)
    worker.run()
    assert results and not results[0]["ok"]
    assert not config.cache.parent.exists()


def test_binding_failure_reports_published_artifact(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from hpg_core import hearing_managed, hearing_workflow
    from hpg_core.hearing_jobs import HearingPrepareWorker
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    root = tmp_path / "music"
    root.mkdir()
    config = hearing_managed.managed_config(root, mode="einzel")
    track = Track(str(root / "a.wav"), "a.wav", duration=120., bpm=120., analysis_mode="librosa_full_or_tail")
    def publish(*args, **kwargs):
        config.output_dir.mkdir()
        return SimpleNamespace(pair_count=1, clip_count=1, warnings=[])
    def fail(config, **kwargs):
        raise OSError("binding failed")
    monkeypatch.setattr(hearing_workflow, "create_set", publish)
    monkeypatch.setattr(hearing_managed, "bind_set", fail)
    results = []
    worker = HearingPrepareWorker(config, managed_metadata=hearing_managed.freeze_tracks([track], root))
    worker.completed.connect(results.append)
    worker.run()
    assert results[0].get("published_unbound") is True
    assert config.cache.exists() and config.output_dir.exists()


def test_folder_only_dialog_prepares_paths_and_explanations(qtbot, tmp_path, monkeypatch):
    from hpg_core.hearing_panel import HearingPrepareDialog
    from PyQt6.QtWidgets import QDialog
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    music = tmp_path / "music"
    music.mkdir()
    dialog = HearingPrepareDialog(folder=str(music))
    qtbot.addWidget(dialog)
    dialog._accept_config()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.config.source_roots == (music.resolve(),)
    assert dialog.config.cache.parent == dialog.config.output_dir.parent
    assert not dialog.config.cache.exists()
    assert dialog.folder_edit.toolTip() and dialog.count_box.toolTip()
    assert dialog.harmonic_box.toolTip() and dialog.mode_box.toolTip()


def test_pending_hearing_analysis_skips_llm_and_playlist(qtbot, tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    import main
    from tests.test_main_window import _window
    from hpg_core.hearing_managed import managed_config
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    root = tmp_path / "music"
    root.mkdir()
    config = managed_config(root, mode="einzel")
    window = _window(qtbot, monkeypatch)
    signals = {key: Mock() for key in ("progress", "status_update", "analysis_issues", "analysis_done")}
    source = SimpleNamespace(folder_path=str(root), isRunning=lambda: False, **signals)
    window.worker = source
    window._run_id = "managed-run"
    window._hearing_analysis_pending = (config, source, window._run_id)
    window._run_settings = {"ai_enabled": True}
    window._set_run_state(main.RunState.AUDIO)
    old_playlist = window.playlist
    monkeypatch.setattr(main, "AIAnalysisWorker", lambda *a, **k: pytest.fail("Unnoetiger LLM-Lauf"))
    monkeypatch.setattr(window, "on_ai_worker_finished", lambda *a, **k: pytest.fail("Unnoetige Playlist-Suche"))
    track = Track(str(root / "a.wav"), "a.wav", duration=120., bpm=120., analysis_mode="librosa_full_or_tail")
    window.analysis_finished([track], {}, source)
    assert window.run_state == main.RunState.SUCCESS
    assert window.playlist is old_playlist
    assert window._hearing_analysis_snapshot[2] == "managed-run"
    starts = []
    monkeypatch.setattr(window, "_start_hearing_worker", lambda worker, action: starts.append((worker, action)))
    window.worker = None
    window._resume_hearing_analysis(source)
    assert len(starts) == 1 and starts[0][1] == "prepare"
    assert json.loads(starts[0][0].managed_metadata[0])["filePath"] == track.filePath


def test_cleanup_validation_failure_still_reports_original_error(tmp_path, monkeypatch):
    from hpg_core import hearing_managed, hearing_workflow
    from hpg_core.hearing_jobs import HearingPrepareWorker
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    root = tmp_path / "music"
    root.mkdir()
    config = hearing_managed.managed_config(root, mode="einzel")
    track = Track(str(root / "a.wav"), "a.wav", duration=120., bpm=120., analysis_mode="librosa_full_or_tail")
    def fail(*args, **kwargs): raise ValueError("original preparation failure")
    def cleanup(*args): raise ValueError("unsafe cleanup path")
    monkeypatch.setattr(hearing_workflow, "create_set", fail)
    monkeypatch.setattr(hearing_managed, "discard_unpublished_snapshot", cleanup)
    worker = HearingPrepareWorker(config, managed_metadata=hearing_managed.freeze_tracks([track], root))
    results = []
    worker.completed.connect(results.append)
    worker.run()
    assert not results[0]["ok"]
    assert "original preparation failure" in results[0]["output"]
    assert "unsafe cleanup path" in results[0]["cleanup_warning"]
    assert config.cache.exists()


def _ownership_input(tmp_path, monkeypatch):
    from hpg_core import hearing_managed as managed
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    music = tmp_path / "music"
    music.mkdir()
    config = managed.managed_config(music, mode="einzel")
    track = Track(str(music / "metadata-only.wav"), "metadata-only.wav",
                  duration=120., bpm=120., analysis_mode="librosa_full_or_tail")
    return config, managed.freeze_tracks([track], music)


@pytest.mark.parametrize("replacement", ["root", "directory", "file", "journal"])
def test_ownership_worker_preserves_replaced_objects(tmp_path, monkeypatch, replacement):
    from hpg_core import hearing_workflow
    from hpg_core.hearing_jobs import HearingPrepareWorker
    config, snapshots = _ownership_input(tmp_path, monkeypatch)
    foreign = config.cache
    def fail(*args, **kwargs):
        nonlocal foreign
        if replacement == "root":
            config.cache.parent.parent.rename(tmp_path / "original-root")
            config.cache.parent.mkdir(parents=True)
        elif replacement == "directory":
            config.cache.parent.rename(tmp_path / "original-directory")
            config.cache.parent.mkdir()
        elif replacement == "file":
            config.cache.rename(tmp_path / "original.sqlite")
        else:
            foreign = config.cache.with_name("analysis.sqlite-journal")
        foreign.write_bytes(b"foreign metadata must survive")
        raise ValueError("producer failed")
    monkeypatch.setattr(hearing_workflow, "create_set", fail)
    results = []
    worker = HearingPrepareWorker(config, managed_metadata=snapshots)
    worker.completed.connect(results.append)
    worker.run()
    assert foreign.exists(), "Cleanup deleted an unowned replacement"
    assert foreign.read_bytes() == b"foreign metadata must survive"
    assert config.cache.exists(), "Unknown journal must prevent partial cleanup"
    assert len(results) == 1 and not results[0]["ok"]
    assert "producer failed" in results[0]["output"]
    assert results[0].get("cleanup_warning")


def test_ownership_association_collision_never_unlinks_foreign_file(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from hpg_core import hearing_managed as managed
    config, snapshots = _ownership_input(tmp_path, monkeypatch)
    managed.write_snapshot(config, snapshots)
    config.output_dir.mkdir()
    (config.output_dir / "hearing_source_manifest.json").write_text("{}")
    monkeypatch.setattr(managed.uuid, "uuid4", lambda: SimpleNamespace(hex="collision"))
    foreign = config.cache.parent / ".association-collision.tmp"
    foreign.write_bytes(b"existing foreign metadata")
    with pytest.raises(FileExistsError):
        managed.bind_set(config)
    assert foreign.exists(), "Exclusive-open failure must never authorize unlink"
    assert foreign.read_bytes() == b"existing foreign metadata"


def test_ownership_association_replaced_temp_preserved_after_link(tmp_path, monkeypatch):
    from pathlib import Path
    from hpg_core import hearing_managed as managed
    config, snapshots = _ownership_input(tmp_path, monkeypatch)
    managed.write_snapshot(config, snapshots)
    config.output_dir.mkdir()
    (config.output_dir / "hearing_source_manifest.json").write_text("{}")
    real_link = managed.os.link
    replaced = []
    def link_then_replace(source, target):
        real_link(source, target)
        path = Path(source)
        path.rename(tmp_path / "own-association.tmp")
        path.write_bytes(b"foreign replacement")
        replaced.append(path)
    monkeypatch.setattr(managed.os, "link", link_then_replace)
    warning = managed.bind_set(config)
    assert replaced[0].exists(), "Replaced temporary file was deleted"
    assert replaced[0].read_bytes() == b"foreign replacement"
    assert warning
    assert managed.resolve_association(config.output_dir) == config.cache


@pytest.mark.parametrize("field", ["root_identity", "directory_identity", "file_identity", "born_ns"])
def test_ownership_missing_or_birth_mismatch_refuses_cleanup(tmp_path, monkeypatch, field):
    from hpg_core import hearing_managed as managed
    config, snapshots = _ownership_input(tmp_path, monkeypatch)
    owner = managed.write_snapshot(config, snapshots)
    before = config.cache.read_bytes()
    altered = (replace(owner, file_identity=replace(owner.file_identity, born_ns=owner.file_identity.born_ns + 1))
               if field == "born_ns" else replace(owner, **{field: None}))
    with pytest.raises(ValueError):
        managed.discard_unpublished_snapshot(altered)
    assert config.cache.read_bytes() == before
    managed.discard_unpublished_snapshot(owner)
    assert not config.cache.parent.exists()


def test_ownership_is_frozen_and_missing_birth_rejected(tmp_path, monkeypatch):
    from dataclasses import FrozenInstanceError
    from types import SimpleNamespace
    from hpg_core import hearing_managed as managed
    config, snapshots = _ownership_input(tmp_path, monkeypatch)
    owner = managed.write_snapshot(config, snapshots)
    with pytest.raises(FrozenInstanceError):
        owner.directory = tmp_path
    observed = config.cache.stat()
    missing_birth = SimpleNamespace(st_dev=observed.st_dev, st_ino=observed.st_ino,
                                    st_mode=observed.st_mode)
    with pytest.raises(ValueError, match="identitaet"):
        managed._identity_from_stat(missing_birth, managed.stat.S_IFREG)


def test_ownership_partial_creation_cleans_only_owned_empty_directory(tmp_path, monkeypatch):
    from pathlib import Path
    from hpg_core import hearing_managed as managed
    config, snapshots = _ownership_input(tmp_path, monkeypatch)
    original_open = Path.open
    def fail_open(path, *args, **kwargs):
        if path == config.cache:
            raise OSError("exclusive file creation failed")
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", fail_open)
    with pytest.raises(OSError, match="exclusive file creation failed"):
        managed.write_snapshot(config, snapshots)
    assert not config.cache.parent.exists()


def test_ownership_file_capture_failure_preserves_unknown_file(tmp_path, monkeypatch):
    from hpg_core import hearing_managed as managed
    config, snapshots = _ownership_input(tmp_path, monkeypatch)
    original = managed._identity_from_stat
    def fail_file(value, kind):
        if kind == managed.stat.S_IFREG:
            raise ValueError("file identity unavailable")
        return original(value, kind)
    monkeypatch.setattr(managed, "_identity_from_stat", fail_file)
    with pytest.raises(ValueError, match="file identity unavailable") as error:
        managed.write_snapshot(config, snapshots)
    assert config.cache.exists()
    assert any("Snapshot blieb erhalten" in note for note in error.value.__notes__)


def test_ownership_association_replaced_before_publish_is_not_linked(tmp_path, monkeypatch):
    from hpg_core import hearing_managed as managed
    config, snapshots = _ownership_input(tmp_path, monkeypatch)
    owner = managed.write_snapshot(config, snapshots)
    config.output_dir.mkdir()
    (config.output_dir / "hearing_source_manifest.json").write_text("{}")
    original_identity = managed._require_identity
    replaced = []
    def replace_before_check(path, expected):
        if path.name.startswith(".association-") and not replaced:
            path.rename(tmp_path / "original-association.tmp")
            path.write_bytes(b"foreign before publication")
            replaced.append(path)
        return original_identity(path, expected)
    monkeypatch.setattr(managed, "_require_identity", replace_before_check)
    with pytest.raises(ValueError, match="Objektidentitaet"):
        managed.bind_set(config, ownership=owner)
    assert replaced[0].read_bytes() == b"foreign before publication"
    assert not (config.cache.parent / "association.json").exists()


def test_ownership_cancel_after_snapshot_cleans_and_emits_once(tmp_path, monkeypatch):
    from hpg_core import hearing_managed as managed
    from hpg_core.hearing_jobs import HearingPrepareWorker
    config, snapshots = _ownership_input(tmp_path, monkeypatch)
    original_write = managed.write_snapshot
    def write_then_cancel(*args, **kwargs):
        owner = original_write(*args, **kwargs)
        kwargs["cancel"].request_cancel()
        return owner
    monkeypatch.setattr(managed, "write_snapshot", write_then_cancel)
    worker = HearingPrepareWorker(config, managed_metadata=snapshots)
    results = []
    worker.completed.connect(results.append)
    worker.run()
    assert len(results) == 1 and results[0]["cancelled"] and not results[0]["ok"]
    assert not config.cache.parent.exists()


def _multiroot_input(tmp_path, monkeypatch):
    from hpg_core import hearing_managed as managed
    from hpg_core.caching import track_to_dict
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    roots = (tmp_path / "music-a", tmp_path / "music-b")
    for root in roots:
        root.mkdir()
    config = managed.managed_config_from_roots(roots, mode="einzel", count=2)
    tracks = tuple(Track(str(root / "metadata-only.wav"), "metadata-only.wav",
                         duration=120., bpm=120., analysis_mode="librosa_full_or_tail") for root in roots)
    snapshots = tuple(json.dumps(track_to_dict(track), allow_nan=False) for track in tracks)
    return config, snapshots


def _multiroot_publish(config, roots=None):
    config.output_dir.mkdir()
    manifest = config.output_dir / "hearing_source_manifest.json"
    manifest.write_text(json.dumps({"source_roots": [str(root) for root in (roots or config.source_roots)]}),
                        encoding="utf-8")
    return manifest


def test_multiroot_config_normalizes_order_and_private_uuid_without_writes(tmp_path, monkeypatch):
    from pathlib import Path
    from hpg_core import hearing_managed as managed
    config, _ = _multiroot_input(tmp_path, monkeypatch)
    roots = config.source_roots
    second = managed.managed_config_from_roots((roots[1], roots[0] / ".", roots[1]), mode="einzel", count=3)
    assert second.source_roots == (roots[1], roots[0])
    assert second.count == 3
    assert config.cache.parent != second.cache.parent
    assert second.cache == second.output_dir.parent / "analysis.sqlite"
    assert second.cache.parent.parent == managed.managed_root()
    assert not second.cache.parent.exists()
    with pytest.raises(ValueError):
        managed.managed_config_from_roots((), mode="einzel")
    with pytest.raises(ValueError):
        managed.managed_config_from_roots((Path(roots[0].anchor),), mode="einzel")


def test_multiroot_private_snapshot_and_v2_association_roundtrip(tmp_path, monkeypatch):
    import sqlite3
    from hpg_core import hearing_managed as managed
    config, snapshots = _multiroot_input(tmp_path, monkeypatch)
    owner = managed.write_snapshot(config, snapshots)
    with sqlite3.connect(config.cache) as connection:
        rows = connection.execute("SELECT filepath,data FROM cache WHERE key <> 'version'").fetchall()
    assert {row[0] for row in rows} == {json.loads(raw)["filePath"] for raw in snapshots}
    assert {row[1] for row in rows} == set(snapshots)
    _multiroot_publish(config)
    managed.bind_set(config, ownership=owner)
    association = json.loads((config.cache.parent / "association.json").read_text(encoding="utf-8"))
    assert set(association) == {"format", "cache_version", "cache", "set", "source_roots",
                                "cache_sha256", "manifest_sha256"}
    assert association["format"] == "hpg-hearing-association-v2"
    assert association["source_roots"] == [str(root) for root in config.source_roots]
    assert managed.resolve_association(config.output_dir) == config.cache


@pytest.mark.parametrize("kind", ["duplicate", "outside"])
def test_multiroot_snapshot_rejects_duplicate_or_outsider_before_private_write(tmp_path, monkeypatch, kind):
    from hpg_core import hearing_managed as managed
    config, snapshots = _multiroot_input(tmp_path, monkeypatch)
    if kind == "duplicate":
        snapshots = snapshots + (snapshots[0],)
    else:
        data = json.loads(snapshots[0])
        data["filePath"] = str(tmp_path / "outside.wav")
        snapshots = (json.dumps(data),)
    with pytest.raises(ValueError, match="fremde|doppelte"):
        managed.write_snapshot(config, snapshots)
    assert not config.cache.parent.exists()


def test_multiroot_snapshot_rejects_empty_roots(tmp_path, monkeypatch):
    from hpg_core import hearing_managed as managed
    config, snapshots = _multiroot_input(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        managed.write_snapshot(replace(config, source_roots=()), snapshots)
    assert not config.cache.parent.exists()


@pytest.mark.parametrize("moment", ["before", "during_private_write"])
def test_multiroot_cancel_cleans_only_owned_snapshot(tmp_path, monkeypatch, moment):
    from hpg_core import hearing_managed as managed
    from hpg_core.hearing_workflow import CancellationToken
    config, snapshots = _multiroot_input(tmp_path, monkeypatch)
    token = CancellationToken()
    if moment == "before":
        token.request_cancel()
    else:
        original_connect = managed.sqlite3.connect

        def connect(*args, **kwargs):
            token.request_cancel()
            return original_connect(*args, **kwargs)

        monkeypatch.setattr(managed.sqlite3, "connect", connect)
    with pytest.raises(InterruptedError):
        managed.write_snapshot(config, snapshots, cancel=token)
    assert not config.cache.parent.exists()


@pytest.mark.parametrize("change", ["association_order", "association_ancestor", "manifest_order"])
def test_multiroot_root_tampering_rejected_even_with_current_hash(tmp_path, monkeypatch, change):
    import hashlib
    from hpg_core import hearing_managed as managed
    config, snapshots = _multiroot_input(tmp_path, monkeypatch)
    managed.write_snapshot(config, snapshots)
    manifest = _multiroot_publish(config)
    managed.bind_set(config)
    target = config.cache.parent / "association.json"
    association = json.loads(target.read_text(encoding="utf-8"))
    if change == "association_order":
        association["source_roots"].reverse()
    elif change == "association_ancestor":
        association["source_roots"] = [str(tmp_path), str(config.source_roots[1])]
    else:
        manifest.write_text(json.dumps({"source_roots": [str(root) for root in config.source_roots[::-1]]}),
                            encoding="utf-8")
        association["manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    target.write_text(json.dumps(association), encoding="utf-8")
    with pytest.raises(ValueError):
        managed.resolve_association(config.output_dir)


def test_multiroot_bind_refuses_manifest_root_mismatch_before_publication(tmp_path, monkeypatch):
    from hpg_core import hearing_managed as managed
    config, snapshots = _multiroot_input(tmp_path, monkeypatch)
    managed.write_snapshot(config, snapshots)
    _multiroot_publish(config, config.source_roots[::-1])
    with pytest.raises(ValueError):
        managed.bind_set(config)
    assert not (config.cache.parent / "association.json").exists()
    assert not tuple(config.cache.parent.glob(".association-*.tmp"))


@pytest.mark.parametrize("field,bad", [
    ("format", True), ("format", "hpg-hearing-association-v3"),
    ("cache_version", True), ("cache_version", 46.0),
    ("source_roots", []), ("source_roots", ["relative", "elsewhere"]),
    ("source_roots", ["C:\\bad\x00", "C:\\other"]),
    ("source_roots", "not a list"), ("source_roots", [True, False]),
])
def test_multiroot_association_strict_version_and_root_schema(tmp_path, monkeypatch, field, bad):
    from hpg_core import hearing_managed as managed
    config, snapshots = _multiroot_input(tmp_path, monkeypatch)
    managed.write_snapshot(config, snapshots)
    _multiroot_publish(config)
    managed.bind_set(config)
    target = config.cache.parent / "association.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    data[field] = bad
    target.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        managed.resolve_association(config.output_dir)


def test_multiroot_duplicate_root_and_mixed_version_keys_rejected(tmp_path, monkeypatch):
    from hpg_core import hearing_managed as managed
    config, snapshots = _multiroot_input(tmp_path, monkeypatch)
    managed.write_snapshot(config, snapshots)
    _multiroot_publish(config)
    managed.bind_set(config)
    target = config.cache.parent / "association.json"
    original = json.loads(target.read_text(encoding="utf-8"))
    for altered in (dict(original, source_roots=[str(config.source_roots[0])] * 2),
                    dict(original, source_folder=str(config.source_roots[0]))):
        target.write_text(json.dumps(altered), encoding="utf-8")
        with pytest.raises(ValueError):
            managed.resolve_association(config.output_dir)


def test_multiroot_existing_unknown_association_is_never_overwritten(tmp_path, monkeypatch):
    from hpg_core import hearing_managed as managed
    config, snapshots = _multiroot_input(tmp_path, monkeypatch)
    managed.write_snapshot(config, snapshots)
    _multiroot_publish(config)
    foreign = config.cache.parent / "association.json"
    foreign.write_bytes(b"UNKNOWN USER FORMAT")
    with pytest.raises(FileExistsError):
        managed.bind_set(config)
    assert foreign.read_bytes() == b"UNKNOWN USER FORMAT"
    assert not tuple(config.cache.parent.glob(".association-*.tmp"))
    with pytest.raises(ValueError):
        managed.resolve_association(config.output_dir)


def test_multiroot_never_opens_or_writes_source_media(tmp_path, monkeypatch):
    from pathlib import Path
    from hpg_core import hearing_managed as managed
    config, snapshots = _multiroot_input(tmp_path, monkeypatch)
    original = Path.open

    def guarded(path, *args, **kwargs):
        if any(path.is_relative_to(root) for root in config.source_roots):
            pytest.fail("Quellmedium wurde geöffnet")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    managed.write_snapshot(config, snapshots)
    _multiroot_publish(config)
    managed.bind_set(config)
    assert managed.resolve_association(config.output_dir) == config.cache
    assert all(list(root.iterdir()) == [] for root in config.source_roots)
