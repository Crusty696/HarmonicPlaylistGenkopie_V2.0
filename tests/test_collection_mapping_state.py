"""Eigene JSON-Persistenz mit RAM-Fixtures, niemals Originalquellen."""
from dataclasses import FrozenInstanceError, replace
import io
import json
import os
from pathlib import Path
import subprocess
from threading import Event

import pytest

from hpg_core.collection_index import CollectionEntry, CollectionIndex
from hpg_core.collection_rekordbox import CollectionRekordboxMap, CollectionRekordboxRow
from hpg_core import collection_mapping_state as module
from hpg_core.collection_mapping_state import (
    CollectionMappingStateError, make_mapping_state,
    load_collection_mapping_state, save_collection_mapping_state,
)


@pytest.fixture
def sample(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    root = str(tmp_path / "music")
    path = str(tmp_path / "music" / "not-opened.aiff")
    entry = CollectionEntry(path, 7, 123, "new")
    index = CollectionIndex((root,), (entry,))
    row = CollectionRekordboxRow(path, (root,), 7, 123, "exact",
                                False, True, 0, None, "opaque-not-hex",
                                ("detail_read_status_unverified",))
    mapping = CollectionRekordboxMap((root,), (row,), 46,
                                    str(tmp_path / "never-open.db"), True)
    return index, mapping


def state(sample, timestamp=0):
    return make_mapping_state(*sample, observed_at_ns=timestamp)


def destination():
    return Path(os.environ["LOCALAPPDATA"]) / "HPG" / "collection_mapping.json"


def write_raw(raw):
    destination().write_text(json.dumps(raw, allow_nan=True), encoding="utf-8")


def test_missing_saved_file_is_none(sample):
    assert load_collection_mapping_state() is None


def test_frozen_detached_roundtrip_preserves_unknown_and_zero(sample):
    index, mapping = sample
    mutable_index = replace(index, roots=list(index.roots), entries=list(index.entries))
    mutable_row = replace(mapping.rows[0], source_roots=list(index.roots), errors=list(mapping.rows[0].errors))
    mutable_map = replace(mapping, roots=list(mapping.roots), rows=[mutable_row], errors=[])
    snapshot = make_mapping_state(mutable_index, mutable_map, observed_at_ns=0)
    mutable_index.entries.clear()
    mutable_row.errors.clear()
    mutable_map.rows.clear()
    assert len(snapshot.index_snapshot.entries) == 1
    assert snapshot.mapping.rows[0].errors == ("detail_read_status_unverified",)
    with pytest.raises(FrozenInstanceError):
        snapshot.observed_at_ns = 1
    with pytest.raises(FrozenInstanceError):
        snapshot.mapping.rows[0].beatgrid_count = 1
    save_collection_mapping_state(snapshot)
    restored = load_collection_mapping_state(index=index, expected_cache_version=46)
    assert restored.state == snapshot
    assert restored.provenance == "saved_not_fresh"
    assert restored.state.observed_at_ns == 0
    assert restored.state.mapping.rows[0].beatgrid_count == 0
    assert restored.state.mapping.rows[0].phrases_count is None
    assert restored.state.mapping.rows[0].bpm_present is False
    assert restored.state.mapping.rows[0].source_signature == "opaque-not-hex"


@pytest.mark.parametrize("bad", [True, -1, 0.0, float("nan"), float("inf")])
def test_observation_time_is_exact_nonnegative_integer(sample, bad):
    with pytest.raises(CollectionMappingStateError):
        make_mapping_state(*sample, observed_at_ns=bad)


@pytest.mark.parametrize("code", ["unknown", "mapping_operation_failed", "importer_close_failed"])
def test_failed_worker_reports_remain_saveable(sample, code):
    index, mapping = sample
    row = replace(mapping.rows[0], match_status="unavailable", bpm_present=None,
                  key_present=None, beatgrid_count=None, phrases_count=None,
                  source_signature=None, errors=(code,))
    failed = replace(mapping, valid=False, errors=(code,), rows=(row,))
    saved = make_mapping_state(index, failed, observed_at_ns=0)
    save_collection_mapping_state(saved)
    assert load_collection_mapping_state().state.mapping == failed


@pytest.mark.parametrize("mutation", ["valid_global_errors", "invalid_confirmed", "cancelled_valid",
                                       "missing_inventory_exact", "missing_inventory_ambiguous"])
def test_false_confirmations_are_rejected(sample, mutation):
    index, mapping = sample
    if mutation == "valid_global_errors":
        mapping = replace(mapping, errors=("unknown",))
    elif mutation == "invalid_confirmed":
        mapping = replace(mapping, valid=False)
    elif mutation == "cancelled_valid":
        mapping = replace(mapping, cancelled=True)
    else:
        index = replace(index, entries=(replace(index.entries[0], status="missing"),))
        if mutation.endswith("ambiguous"):
            mapping = replace(mapping, rows=(replace(mapping.rows[0], match_status="ambiguous",
                bpm_present=None, key_present=None, beatgrid_count=None,
                phrases_count=None, source_signature=None),))
    with pytest.raises(CollectionMappingStateError):
        make_mapping_state(index, mapping, observed_at_ns=0)


@pytest.mark.parametrize("status", ["unavailable", "ambiguous", "missing"])
@pytest.mark.parametrize("field,value", [("bpm_present", False), ("key_present", True),
                                         ("beatgrid_count", 0), ("phrases_count", 1),
                                         ("source_signature", "signature")])
def test_unconfirmed_rows_cannot_contain_detail_confirmations(sample, status, field, value):
    index, mapping = sample
    row = replace(mapping.rows[0], match_status=status, bpm_present=None,
                  key_present=None, beatgrid_count=None, phrases_count=None, source_signature=None)
    row = replace(row, **{field: value})
    with pytest.raises(CollectionMappingStateError):
        make_mapping_state(index, replace(mapping, rows=(row,)), observed_at_ns=0)


@pytest.mark.parametrize("location,key,bad", [
    ("top", "map_version", True), ("top", "map_version", 2),
    ("top", "cache_version", True), ("top", "observed_at_ns", float("nan")),
    ("entry", "size", True), ("entry", "mtime_ns", False),
    ("entry", "mtime_ns", -1), ("entry", "status", "guessed"),
    ("row", "inventory_size", True), ("row", "beatgrid_count", True),
    ("row", "phrases_count", float("inf")), ("row", "bpm_present", 1),
    ("row", "source_signature", ""), ("row", "errors", ["private exception"]),
    ("mapping", "source_db_path", "relative.db"),
    ("mapping", "source_db_path", "C:/bad\x00.db"),
    ("mapping", "source_db_path", "C:\\folder\\..\\source.db"),
    ("mapping", "valid", 1), ("mapping", "cancelled", 0),
])
def test_strict_schema_rejects_bad_scalars(sample, location, key, bad):
    save_collection_mapping_state(state(sample))
    raw = json.loads(destination().read_text(encoding="utf-8"))
    target = {"top": raw, "entry": raw["index_snapshot"]["entries"][0],
              "row": raw["mapping"]["rows"][0], "mapping": raw["mapping"]}[location]
    target[key] = bad
    write_raw(raw)
    with pytest.raises(CollectionMappingStateError):
        load_collection_mapping_state()


@pytest.mark.parametrize("location", ["top", "index", "entry", "mapping", "row"])
@pytest.mark.parametrize("change", ["extra", "missing"])
def test_exact_keys_everywhere(sample, location, change):
    save_collection_mapping_state(state(sample))
    raw = json.loads(destination().read_text(encoding="utf-8"))
    target = {"top": raw, "index": raw["index_snapshot"],
              "entry": raw["index_snapshot"]["entries"][0],
              "mapping": raw["mapping"], "row": raw["mapping"]["rows"][0]}[location]
    if change == "extra":
        target["unexpected"] = None
    else:
        target.pop(next(iter(target)))
    write_raw(raw)
    with pytest.raises(CollectionMappingStateError):
        load_collection_mapping_state()


def test_duplicate_json_key_and_unknown_format_never_overwritten(sample):
    destination().parent.mkdir(parents=True)
    for content in ('{"kind":"other"}', '{"kind":1,"kind":2}', 'not json'):
        destination().write_text(content, encoding="utf-8")
        before = destination().read_bytes()
        with pytest.raises(CollectionMappingStateError):
            save_collection_mapping_state(state(sample))
        assert destination().read_bytes() == before
        assert list(destination().parent.iterdir()) == [destination()]


def test_older_cache_version_is_known_format_but_not_current(sample):
    snapshot = state(sample)
    older = replace(snapshot, cache_version=45, mapping=replace(snapshot.mapping, cache_version=45))
    save_collection_mapping_state(older)
    assert load_collection_mapping_state().state.cache_version == 45
    with pytest.raises(CollectionMappingStateError):
        load_collection_mapping_state(expected_cache_version=46)
    save_collection_mapping_state(snapshot)
    assert load_collection_mapping_state(expected_cache_version=46).state == snapshot


@pytest.mark.parametrize("change", ["roots", "path", "size", "mtime_ns", "status"])
def test_optional_index_requires_complete_snapshot_match(sample, change):
    index, _ = sample
    save_collection_mapping_state(state(sample))
    if change == "roots":
        index = replace(index, roots=(str(Path(index.roots[0]).parent),))
    else:
        value = {"path": str(Path(index.entries[0].path).with_name("other.aiff")),
                 "size": 8, "mtime_ns": 124, "status": "changed"}[change]
        index = replace(index, entries=(replace(index.entries[0], **{change: value}),))
    with pytest.raises(CollectionMappingStateError):
        load_collection_mapping_state(index=index)


def test_2500_rows_and_order_are_preserved_without_limit(sample):
    index, mapping = sample
    entries = tuple(replace(index.entries[0], path=str(Path(index.roots[0]) / f"{i:04}.mp3"))
                    for i in range(2500))
    rows = tuple(replace(mapping.rows[0], path=entry.path) for entry in entries)
    index, mapping = replace(index, entries=entries), replace(mapping, rows=rows)
    snapshot = make_mapping_state(index, mapping, observed_at_ns=10)
    save_collection_mapping_state(snapshot)
    assert load_collection_mapping_state(index=index).state == snapshot
    with pytest.raises(CollectionMappingStateError):
        make_mapping_state(index, replace(mapping, rows=rows[::-1]), observed_at_ns=10)
    with pytest.raises(CollectionMappingStateError):
        load_collection_mapping_state(index=replace(index, entries=entries[::-1]))


@pytest.mark.parametrize("change", ["outside", "duplicate", "row_missing", "row_extra", "source_roots"])
def test_path_key_count_and_root_binding(sample, change):
    index, mapping = sample
    if change == "outside":
        entry = replace(index.entries[0], path=str(Path(index.roots[0]).parent / "outside.mp3"))
        index = replace(index, entries=(entry,))
        mapping = replace(mapping, rows=(replace(mapping.rows[0], path=entry.path),))
    elif change == "duplicate":
        index = replace(index, entries=index.entries * 2)
        mapping = replace(mapping, rows=mapping.rows * 2)
    elif change == "source_roots":
        mapping = replace(mapping, rows=(replace(mapping.rows[0], source_roots=()),))
    else:
        mapping = replace(mapping, rows=() if change == "row_missing" else mapping.rows * 2)
    with pytest.raises(CollectionMappingStateError):
        make_mapping_state(index, mapping, observed_at_ns=0)


@pytest.mark.parametrize("checkpoint", [1, 2, 3])
def test_cancel_at_every_checkpoint_preserves_old_and_cleans_own_temp(sample, checkpoint):
    save_collection_mapping_state(state(sample))
    before = destination().read_bytes()
    calls = []

    def cancel():
        calls.append(True)
        return len(calls) == checkpoint

    with pytest.raises(InterruptedError):
        save_collection_mapping_state(state(sample, 1), cancel=cancel)
    assert destination().read_bytes() == before
    assert list(destination().parent.iterdir()) == [destination()]


@pytest.mark.parametrize("operation", ["fsync", "replace"])
def test_atomic_failure_rolls_back_and_preserves_other_temp(sample, monkeypatch, operation):
    save_collection_mapping_state(state(sample))
    before = destination().read_bytes()
    other = destination().parent / ".not-our-temp"
    other.write_text("KEEP", encoding="utf-8")

    def fail(*args):
        raise OSError("injected")

    monkeypatch.setattr(module.os, operation, fail)
    with pytest.raises(CollectionMappingStateError):
        save_collection_mapping_state(state(sample, 1))
    assert destination().read_bytes() == before
    assert set(destination().parent.iterdir()) == {destination(), other}


def test_cancel_after_replace_is_committed_not_rollback(sample, monkeypatch):
    save_collection_mapping_state(state(sample))
    cancelled = Event()
    real = module.os.replace

    def commit(*args):
        real(*args)
        cancelled.set()

    monkeypatch.setattr(module.os, "replace", commit)
    save_collection_mapping_state(state(sample, 1), cancel=cancelled)
    assert load_collection_mapping_state().state.observed_at_ns == 1


def test_cancel_after_final_destination_validation_preserves_old(sample, monkeypatch):
    save_collection_mapping_state(state(sample))
    before = destination().read_bytes()
    cancelled = Event()
    original = module._load_own
    calls = []

    def checked(*args):
        result = original(*args)
        calls.append(True)
        if len(calls) == 2:
            cancelled.set()
        return result

    monkeypatch.setattr(module, "_load_own", checked)
    with pytest.raises(InterruptedError):
        save_collection_mapping_state(state(sample, 1), cancel=cancelled)
    assert destination().read_bytes() == before
    assert list(destination().parent.iterdir()) == [destination()]


def test_unknown_format_appearing_before_commit_is_not_overwritten(sample, monkeypatch):
    save_collection_mapping_state(state(sample))
    original = module._load_own
    calls = []

    def changed(*args):
        calls.append(True)
        if len(calls) == 2:
            destination().write_text("FOREIGN USER FILE", encoding="utf-8")
        return original(*args)

    monkeypatch.setattr(module, "_load_own", changed)
    with pytest.raises(CollectionMappingStateError):
        save_collection_mapping_state(state(sample, 1))
    assert destination().read_text(encoding="utf-8") == "FOREIGN USER FILE"
    assert list(destination().parent.iterdir()) == [destination()]


@pytest.mark.parametrize("bad", ["errors", "cancelled", "cancelled_bool"])
def test_failed_or_cancelled_index_is_not_a_snapshot_basis(sample, bad):
    index, mapping = sample
    changes = {"errors": {"errors": ("read error",)},
               "cancelled": {"cancelled": True}, "cancelled_bool": {"cancelled": 0}}[bad]
    with pytest.raises(CollectionMappingStateError):
        make_mapping_state(replace(index, **changes), mapping, observed_at_ns=0)


def test_overlapping_root_order_is_bound_and_unconfirmed_missing_is_allowed(sample):
    index, mapping = sample
    broad = str(Path(index.roots[0]).parent)
    roots = (index.roots[0], broad)
    entry = replace(index.entries[0], status="missing")
    row = replace(mapping.rows[0], source_roots=roots, match_status="missing",
                  bpm_present=None, key_present=None, beatgrid_count=None,
                  phrases_count=None, source_signature=None)
    index = replace(index, roots=roots, entries=(entry,))
    mapping = replace(mapping, roots=roots, rows=(row,))
    snapshot = make_mapping_state(index, mapping, observed_at_ns=0)
    # Für diesen RAM-Vertrag nicht speichern: broad enthält auch den Temp-State.
    assert snapshot.index_snapshot.roots == roots
    assert snapshot.mapping.rows[0].source_roots == roots
    with pytest.raises(CollectionMappingStateError):
        make_mapping_state(index, replace(mapping, rows=(replace(row, source_roots=roots[::-1]),)),
                           observed_at_ns=0)


def test_load_rejects_root_order_mismatch_without_source_access(sample):
    index, mapping = sample
    nested = str(Path(index.roots[0]) / "nested")
    roots = (nested, index.roots[0])
    entry = replace(index.entries[0], path=str(Path(nested) / "a.mp3"))
    row = replace(mapping.rows[0], path=entry.path, source_roots=roots)
    index = replace(index, roots=roots, entries=(entry,))
    snapshot = make_mapping_state(index, replace(mapping, roots=roots, rows=(row,)), observed_at_ns=0)
    save_collection_mapping_state(snapshot)
    with pytest.raises(CollectionMappingStateError):
        load_collection_mapping_state(index=replace(index, roots=roots[::-1]))


def test_direct_state_tampering_cannot_bypass_binding_validation(sample):
    snapshot = state(sample)
    with pytest.raises(CollectionMappingStateError):
        save_collection_mapping_state(replace(snapshot, cache_version=47))
    with pytest.raises(CollectionMappingStateError):
        save_collection_mapping_state(replace(snapshot, map_version=True))


def test_save_and_load_never_stat_or_open_audio_or_database(sample, monkeypatch):
    import builtins
    original_open, original_stat, original_lstat = builtins.open, os.stat, os.lstat
    forbidden = {sample[0].entries[0].path, sample[1].source_db_path}

    def guarded(function):
        def call(path, *args, **kwargs):
            if isinstance(path, (str, os.PathLike)) and os.fspath(path) in forbidden:
                raise AssertionError("Originalquelle angefasst")
            return function(path, *args, **kwargs)
        return call

    monkeypatch.setattr(builtins, "open", guarded(original_open))
    monkeypatch.setattr(io, "open", guarded(io.open))
    monkeypatch.setattr(os, "stat", guarded(original_stat))
    monkeypatch.setattr(os, "lstat", guarded(original_lstat))
    snapshot = state(sample)
    save_collection_mapping_state(snapshot)
    roots = sample[0].roots
    original_lstat = os.lstat

    def no_music_stat(path, *args, **kwargs):
        if os.fspath(path) in roots:
            raise AssertionError("Load darf Roots nicht statten")
        return original_lstat(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", no_music_stat)
    assert load_collection_mapping_state(index=sample[0]).state == snapshot


@pytest.mark.skipif(os.name != "nt", reason="Windows-Reparse-Vertrag")
def test_load_rejects_linked_state_ancestor_without_reading_target(sample, tmp_path, monkeypatch):
    save_collection_mapping_state(state(sample))
    before = destination().read_bytes()
    junction = tmp_path / "local-link"
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), os.environ["LOCALAPPDATA"]],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    monkeypatch.setenv("LOCALAPPDATA", str(junction))
    with pytest.raises(CollectionMappingStateError):
        load_collection_mapping_state()
    assert destination().read_bytes() == before


def test_destination_inside_music_root_rejected(sample, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", sample[0].roots[0])
    with pytest.raises(CollectionMappingStateError):
        save_collection_mapping_state(state(sample))
    assert not destination().exists()


@pytest.mark.parametrize("value", [None, "relative"])
def test_no_localappdata_fallback(sample, monkeypatch, value):
    if value is None:
        monkeypatch.delenv("LOCALAPPDATA")
    else:
        monkeypatch.setenv("LOCALAPPDATA", value)
    with pytest.raises(CollectionMappingStateError):
        load_collection_mapping_state()


@pytest.mark.skipif(os.name != "nt", reason="Windows-Reparse-Vertrag")
@pytest.mark.parametrize("location", ["state_parent", "root", "root_ancestor"])
def test_windows_junctions_and_linked_ancestors_are_rejected(sample, tmp_path, monkeypatch, location):
    target = tmp_path / "target"
    target.mkdir()
    junction = tmp_path / "junction"
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(target)],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    if location == "state_parent":
        monkeypatch.setenv("LOCALAPPDATA", str(junction / "nested"))
        snapshot = state(sample)
    else:
        root = str(junction if location == "root" else junction / "nested")
        index, mapping = sample
        entry = replace(index.entries[0], path=str(Path(root) / "a.mp3"))
        row = replace(mapping.rows[0], path=entry.path, source_roots=(root,))
        snapshot = make_mapping_state(replace(index, roots=(root,), entries=(entry,)),
                                     replace(mapping, roots=(root,), rows=(row,)), observed_at_ns=0)
    with pytest.raises(CollectionMappingStateError):
        save_collection_mapping_state(snapshot)
    assert list(target.iterdir()) == []
