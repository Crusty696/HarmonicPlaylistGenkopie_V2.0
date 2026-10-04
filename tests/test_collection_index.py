"""Inventarvertrag mit winzigen Textdateien, niemals mit Originalmusik."""

import builtins
import json
import os
import subprocess
from dataclasses import FrozenInstanceError
from pathlib import Path
from threading import Event

import pytest

from hpg_core.collection_index import (
    CollectionIndexError,
    load_collection_index,
    save_collection_index,
    scan_collection,
)


def _fixture(root, name="track.mp3", text="TEXT FIXTURE - NO AUDIO"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _statuses(index):
    return {Path(entry.path).name: entry.status for entry in index.entries}


def test_recursive_2500_files_overlap_deduplication_and_stat_only(tmp_path, monkeypatch):
    root = tmp_path / "sources"
    nested = root / "nested"
    for number in range(2500):
        _fixture(nested / str(number % 10), f"track-{number}.MP3")
    _fixture(root, "ignored.txt")
    before = {str(p): (p.stat().st_size, p.stat().st_mtime_ns)
              for p in root.rglob("*.MP3")}

    def forbidden_open(*args, **kwargs):
        pytest.fail("Der Inventarscan darf keine Datei oeffnen")

    monkeypatch.setattr(builtins, "open", forbidden_open)
    monkeypatch.setattr(Path, "open", forbidden_open)
    index = scan_collection([root, nested, root])
    assert len(index.entries) == 2500
    assert len({entry.path for entry in index.entries}) == 2500
    assert not index.errors and not index.cancelled
    assert all(entry.status == "new" for entry in index.entries)
    assert {entry.path: (entry.size, entry.mtime_ns) for entry in index.entries} == before
    assert all(Path(entry.path).is_absolute() for entry in index.entries)
    assert before == {str(p): (p.stat().st_size, p.stat().st_mtime_ns)
                      for p in root.rglob("*.MP3")}


def test_frozen_snapshot_and_entry(tmp_path):
    _fixture(tmp_path)
    index = scan_collection([tmp_path])
    assert isinstance(index.entries, tuple)
    assert isinstance(index.roots, tuple)
    with pytest.raises(FrozenInstanceError):
        index.cancelled = True
    with pytest.raises(FrozenInstanceError):
        index.entries[0].size = 100


def test_new_unchanged_changed_missing_and_reappearance(tmp_path):
    changed = _fixture(tmp_path, "changed.aiff")
    missing = _fixture(tmp_path, "missing.wav")
    _fixture(tmp_path, "unchanged.flac")
    first = scan_collection([tmp_path])
    changed.write_text("LONGER TEXT FIXTURE", encoding="utf-8")
    missing.unlink()
    _fixture(tmp_path, "new.aif")
    second = scan_collection([tmp_path], previous=first)
    assert _statuses(second) == {"changed.aiff": "changed", "missing.wav": "missing",
                                 "unchanged.flac": "unchanged", "new.aif": "new"}
    assert _statuses(first) == {name: "new" for name in _statuses(first)}
    _fixture(tmp_path, "missing.wav")
    assert _statuses(scan_collection([tmp_path], previous=second))["missing.wav"] == "new"


def test_mtime_alone_marks_changed(tmp_path):
    path = _fixture(tmp_path)
    first = scan_collection([tmp_path])
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 1_000_000_000))
    assert scan_collection([tmp_path], previous=first).entries[0].status == "changed"


def test_supported_extensions_match_existing_config(tmp_path):
    from hpg_core.config import SUPPORTED_AUDIO_EXTENSIONS
    for number, extension in enumerate(SUPPORTED_AUDIO_EXTENSIONS):
        _fixture(tmp_path, f"track-{number}{extension.upper()}")
    _fixture(tmp_path, "notes.txt")
    _fixture(tmp_path, "playlist.m3u8")
    index = scan_collection([tmp_path])
    assert len(index.entries) == len(SUPPORTED_AUDIO_EXTENSIONS)
    assert {Path(entry.path).suffix.lower() for entry in index.entries} == set(SUPPORTED_AUDIO_EXTENSIONS)


def test_removed_root_does_not_make_unselected_tracks_missing(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    _fixture(a, "a.mp3")
    _fixture(b, "b.mp3")
    previous = scan_collection([a, b])
    result = scan_collection([a], previous=previous)
    assert _statuses(result) == {"a.mp3": "unchanged"}


def test_cancel_before_scan_preserves_previous(tmp_path):
    _fixture(tmp_path)
    previous = scan_collection([tmp_path])
    cancellation = Event()
    cancellation.set()
    result = scan_collection([tmp_path], previous=previous, cancel=cancellation)
    assert result.cancelled
    assert result.entries == previous.entries


def test_cancel_after_progress_preserves_previous(tmp_path):
    _fixture(tmp_path)
    previous = scan_collection([tmp_path])
    for number in range(10):
        _fixture(tmp_path, f"new-{number}.wav")
    cancellation = Event()
    progress = []

    def on_progress(count, path):
        progress.append((count, path))
        cancellation.set()

    result = scan_collection([tmp_path], previous=previous,
                             cancel=cancellation.is_set, progress=on_progress)
    assert progress and result.cancelled
    assert result.entries == previous.entries


def test_inaccessible_root_explicit_error_and_rollback(tmp_path, monkeypatch):
    root = tmp_path / "source"
    _fixture(root)
    previous = scan_collection([root])
    original = os.scandir

    def denied(path):
        if os.path.normcase(os.path.abspath(path)) == os.path.normcase(str(root)):
            raise PermissionError("test denied")
        return original(path)

    monkeypatch.setattr(os, "scandir", denied)
    result = scan_collection([root], previous=previous)
    assert result.errors and "denied" in str(result.errors)
    assert result.entries == previous.entries


def test_missing_root_reports_error_not_missing_tracks(tmp_path):
    root = tmp_path / "source"
    track = _fixture(root)
    previous = scan_collection([root])
    track.unlink()
    root.rmdir()
    result = scan_collection([root], previous=previous)
    assert result.errors
    assert result.entries == previous.entries


def test_error_after_partial_scan_rolls_back_all_entries(tmp_path, monkeypatch):
    root = tmp_path / "source"
    _fixture(root, "old.mp3")
    previous = scan_collection([root])
    inaccessible = root / "denied"
    _fixture(inaccessible, "denied.mp3")
    _fixture(root, "new.mp3")
    original = os.scandir

    def denied(path):
        if os.path.normcase(os.path.abspath(path)) == os.path.normcase(str(inaccessible)):
            raise PermissionError("nested test denied")
        return original(path)

    monkeypatch.setattr(os, "scandir", denied)
    result = scan_collection([root], previous=previous)
    assert result.errors
    assert result.entries == previous.entries


def test_empty_roots_is_explicit_error(tmp_path):
    _fixture(tmp_path)
    previous = scan_collection([tmp_path])
    result = scan_collection([], previous=previous)
    assert result.errors
    assert result.entries == previous.entries


def test_symlink_escape_rejected_and_previous_preserved(tmp_path):
    root, outside = tmp_path / "source", tmp_path / "outside"
    _fixture(root)
    external = _fixture(outside, "secret.mp3")
    previous = scan_collection([root])
    try:
        (root / "escape.mp3").symlink_to(external)
        (root / "linked-dir").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Symlinks auf diesem Testhost nicht erlaubt: {exc}")
    result = scan_collection([root], previous=previous)
    assert result.errors
    assert result.entries == previous.entries
    assert str(external) not in {entry.path for entry in result.entries}


def test_symlink_root_rejected(tmp_path):
    root = tmp_path / "source"
    _fixture(root)
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(root, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Symlinks auf diesem Testhost nicht erlaubt: {exc}")
    result = scan_collection([alias])
    assert result.errors
    assert not result.entries


def test_persistence_default_private_directory_roundtrip(tmp_path, monkeypatch):
    root = tmp_path / "source"
    _fixture(root)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    index = scan_collection([root])
    save_collection_index(index)
    destination = tmp_path / "local" / "HPG" / "collection_index.json"
    assert destination.is_file()
    assert load_collection_index(roots=[root]) == index
    raw = json.loads(destination.read_text(encoding="utf-8"))
    assert raw["kind"] == "hpg_collection_index"
    assert raw["version"] == 1
    assert set(raw) == {"kind", "version", "roots", "entries"}


def test_unknown_existing_format_never_overwritten(tmp_path):
    root = tmp_path / "source"
    _fixture(root)
    destination = tmp_path / "state.json"
    destination.write_text('{"user_data":"preserve"}', encoding="utf-8")
    before = destination.read_bytes()
    with pytest.raises(CollectionIndexError):
        save_collection_index(scan_collection([root]), path=destination)
    assert destination.read_bytes() == before


@pytest.mark.parametrize("mutation", ["outside", "duplicate", "status", "boolean_size", "version"])
def test_load_rejects_invalid_schema_and_paths(tmp_path, mutation):
    root = tmp_path / "source"
    _fixture(root)
    destination = tmp_path / "state.json"
    save_collection_index(scan_collection([root]), path=destination)
    raw = json.loads(destination.read_text(encoding="utf-8"))
    if mutation == "outside":
        raw["entries"][0]["path"] = str(tmp_path / "outside.mp3")
    elif mutation == "duplicate":
        raw["entries"].append(raw["entries"][0])
    elif mutation == "status":
        raw["entries"][0]["status"] = "analyzed"
    elif mutation == "boolean_size":
        raw["entries"][0]["size"] = True
    else:
        raw["version"] = 999
    destination.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CollectionIndexError):
        load_collection_index(path=destination)


@pytest.mark.parametrize("field, value", [
    ("mtime_ns", True), ("mtime_ns", -1), ("mtime_ns", 1.5),
    ("size", -1), ("version", True),
])
def test_strict_integer_schema_rejects_invalid_values(tmp_path, field, value):
    root = tmp_path / "source"
    _fixture(root)
    destination = tmp_path / "state.json"
    save_collection_index(scan_collection([root]), path=destination)
    raw = json.loads(destination.read_text(encoding="utf-8"))
    if field == "version":
        raw[field] = value
    else:
        raw["entries"][0][field] = value
    destination.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CollectionIndexError):
        load_collection_index(path=destination)


def test_load_root_binding_mismatch(tmp_path):
    root = tmp_path / "source"
    _fixture(root)
    destination = tmp_path / "state.json"
    save_collection_index(scan_collection([root]), path=destination)
    with pytest.raises(CollectionIndexError):
        load_collection_index(path=destination, roots=[tmp_path / "different"])


def test_saved_inventory_load_never_stats_original_roots_or_entries(tmp_path, monkeypatch):
    root = tmp_path / "source"
    _fixture(root)
    destination = tmp_path / "state.json"
    previous = scan_collection([root])
    save_collection_index(previous, path=destination)
    original = os.lstat

    def forbid_source_stat(path, *args, **kwargs):
        normalized = os.path.normcase(os.path.abspath(path))
        if normalized == os.path.normcase(str(root)) or normalized.startswith(os.path.normcase(str(root)) + os.sep):
            pytest.fail("Gespeichertes Inventar darf Musikpfade nicht statten")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", forbid_source_stat)
    assert load_collection_index(path=destination) == previous


def test_duplicate_json_keys_rejected(tmp_path):
    destination = tmp_path / "state.json"
    destination.write_text('{"kind":"user_data","kind":"hpg_collection_index",'
                           '"version":1,"roots":[],"entries":[]}', encoding="utf-8")
    with pytest.raises(CollectionIndexError):
        load_collection_index(path=destination)


def test_state_symlink_target_never_overwritten(tmp_path):
    root = tmp_path / "source"
    _fixture(root)
    target = tmp_path / "user.json"
    target.write_text("USER CONTENT", encoding="utf-8")
    destination = tmp_path / "state.json"
    try:
        destination.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"Symlinks auf diesem Testhost nicht erlaubt: {exc}")
    with pytest.raises(CollectionIndexError):
        save_collection_index(scan_collection([root]), path=destination)
    assert target.read_text(encoding="utf-8") == "USER CONTENT"


def test_failed_atomic_replace_preserves_existing_state(tmp_path, monkeypatch):
    root = tmp_path / "source"
    _fixture(root)
    destination = tmp_path / "state.json"
    first = scan_collection([root])
    save_collection_index(first, path=destination)
    before = destination.read_bytes()
    _fixture(root, "second.mp3")

    def failed_replace(*args):
        raise OSError("test replace failure")

    monkeypatch.setattr(os, "replace", failed_replace)
    with pytest.raises(CollectionIndexError):
        save_collection_index(scan_collection([root], previous=first), path=destination)
    assert destination.read_bytes() == before
    assert set(tmp_path.iterdir()) == {root, destination}


def test_failed_fsync_preserves_existing_state_and_removes_only_own_temp(tmp_path, monkeypatch):
    root = tmp_path / "source"
    _fixture(root)
    destination = tmp_path / "state.json"
    first = scan_collection([root])
    save_collection_index(first, path=destination)
    before = destination.read_bytes()
    other = tmp_path / "other.tmp"
    other.write_text("USER TEMP CONTENT", encoding="utf-8")
    _fixture(root, "second.mp3")

    def failed_fsync(*args):
        raise OSError("test fsync failure")

    monkeypatch.setattr(os, "fsync", failed_fsync)
    with pytest.raises(CollectionIndexError):
        save_collection_index(scan_collection([root], previous=first), path=destination)
    assert destination.read_bytes() == before
    assert other.read_text(encoding="utf-8") == "USER TEMP CONTENT"
    assert set(tmp_path.iterdir()) == {root, destination, other}


def test_cancel_on_last_progress_rolls_back_before_publication(tmp_path):
    _fixture(tmp_path)
    previous = scan_collection([tmp_path])
    cancellation = Event()
    result = scan_collection([tmp_path], previous=previous, cancel=cancellation,
                             progress=lambda *_args: cancellation.set())
    assert result.cancelled
    assert result.entries == previous.entries


def test_cancel_after_last_state_validation_preserves_old_file(tmp_path, monkeypatch):
    from hpg_core import collection_index
    root = tmp_path / "source"
    _fixture(root)
    destination = tmp_path / "state.json"
    previous = scan_collection([root])
    save_collection_index(previous, path=destination)
    before = destination.read_bytes()
    _fixture(root, "new.mp3")
    cancellation = Event()
    original = collection_index.load_collection_index
    validations = []

    def cancel_after_final_validation(*args, **kwargs):
        result = original(*args, **kwargs)
        validations.append(True)
        if len(validations) == 2:
            cancellation.set()
        return result

    monkeypatch.setattr(collection_index, "load_collection_index", cancel_after_final_validation)
    with pytest.raises(InterruptedError):
        save_collection_index(scan_collection([root], previous=previous),
                              path=destination, cancel=cancellation)
    assert destination.read_bytes() == before
    assert set(tmp_path.iterdir()) == {root, destination}


@pytest.mark.skipif(os.name != "nt", reason="Windows-Reparse-Vertrag")
@pytest.mark.parametrize("kind", ["child", "root", "ancestor"])
def test_windows_junction_rejected_including_linked_ancestors(tmp_path, kind):
    root, outside = tmp_path / "source", tmp_path / "target"
    _fixture(root)
    _fixture(outside / "nested", "outside.mp3")
    junction = (root / "junction") if kind == "child" else tmp_path / "junction"
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    previous = scan_collection([root]) if kind != "child" else None
    selected = root if kind == "child" else junction
    if kind == "ancestor":
        selected = junction / "nested"
    index = scan_collection([selected], previous=previous)
    assert index.errors
    assert index.entries == (previous.entries if previous else ())


@pytest.mark.skipif(os.name != "nt", reason="Windows-Reparse-Vertrag")
def test_state_linked_ancestor_rejected_without_writing_target(tmp_path):
    root, target = tmp_path / "source", tmp_path / "state-target"
    _fixture(root)
    target.mkdir()
    junction = tmp_path / "state-link"
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(target)],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    with pytest.raises(CollectionIndexError):
        save_collection_index(scan_collection([root]), path=junction / "state.json")
    assert list(target.iterdir()) == []


def test_cancelled_or_failed_index_never_persisted(tmp_path):
    root = tmp_path / "source"
    _fixture(root)
    previous = scan_collection([root])
    result = scan_collection([root], previous=previous, cancel=lambda: True)
    with pytest.raises(CollectionIndexError):
        save_collection_index(result, path=tmp_path / "state.json")
    assert not (tmp_path / "state.json").exists()


def test_failed_index_never_persisted(tmp_path):
    root = tmp_path / "source"
    _fixture(root)
    previous = scan_collection([root])
    result = scan_collection([tmp_path / "nonexistent"], previous=previous)
    assert result.errors
    with pytest.raises(CollectionIndexError):
        save_collection_index(result, path=tmp_path / "state.json")
    assert not (tmp_path / "state.json").exists()


def test_state_destination_inside_source_rejected(tmp_path):
    _fixture(tmp_path)
    with pytest.raises(CollectionIndexError):
        save_collection_index(scan_collection([tmp_path]), path=tmp_path / "collection_index.json")
    assert not (tmp_path / "collection_index.json").exists()
