"""Mappervertrag ohne Originaldateien, Audio, Datenbank oder echten Importer."""
from collections import Counter
from dataclasses import FrozenInstanceError
import importlib
import os
from types import SimpleNamespace

import pytest


def normalized(path):
    return os.path.normpath(path).lower()


def inventory(*entries):
    return SimpleNamespace(roots=("C:\\fixture",), entries=tuple(
        SimpleNamespace(path="C:\\fixture\\" + name, status=status, size=17, mtime_ns=123)
        for name, status in entries), errors=(), cancelled=False)


def data(content_id="1", bpm=128.0, key="Am", duration=60.0):
    return SimpleNamespace(content_id=content_id, bpm=bpm, key=key,
                           camelot_code="8A" if key else None, duration=duration)


class FakeImporter:
    def __init__(self):
        self.track_cache = {}
        self.basename_cache = {}
        self._ambiguous_paths = set()
        self._beatgrid_cache = {}
        self._phrases_cache = {}
        self.calls = Counter()
        self.available = True
        self.fail_id = None
        self.db = None

    def add(self, path, record):
        self.track_cache[normalized(path)] = record
        self.basename_cache[os.path.basename(normalized(path))] = record

    def is_available(self):
        return self.available

    def get_track_data(self, path):
        path = normalized(path)
        if not self.available or path in self._ambiguous_paths:
            return None
        if path in self.track_cache:
            return self.track_cache[path]
        return self.basename_cache.get(os.path.basename(path))

    def get_track_signature(self, path):
        row = self.get_track_data(path)
        self.calls[("signature", row.content_id)] += 1
        if row.content_id == self.fail_id:
            from hpg_core.rekordbox_readonly import ReadOnlyRekordboxError
            raise ReadOnlyRekordboxError("opaque-sensitive-fixture")
        self.get_beatgrid(path)
        self.get_phrases(path)
        return "signature-" + row.content_id

    def get_beatgrid(self, path):
        row = self.get_track_data(path)
        self.calls[("beatgrid", row.content_id)] += 1
        self._beatgrid_cache[row.content_id] = [{"beat": 1, "time": 0.0}, {"beat": 2, "time": 0.5}]
        return self._beatgrid_cache[row.content_id]

    def get_phrases(self, path):
        row = self.get_track_data(path)
        self.calls[("phrases", row.content_id)] += 1
        self._phrases_cache[(row.content_id, row.duration)] = [{"start": 0.0, "end": row.duration}]
        return self._phrases_cache[(row.content_id, row.duration)]


@pytest.fixture
def mapper():
    return importlib.import_module("hpg_core.collection_rekordbox").map_collection_rekordbox


def test_mapper_api_exists():
    assert importlib.util.find_spec("hpg_core.collection_rekordbox") is not None


def test_exact_basename_ambiguous_missing_provenance(mapper):
    index = inventory(("exact.mp3", "new"), ("moved.mp3", "new"),
                      ("ambiguous.mp3", "new"), ("absent.mp3", "new"))
    importer = FakeImporter()
    importer.add(index.entries[0].path, data())
    importer.add("C:\\elsewhere\\moved.mp3", data("2"))
    importer.basename_cache["ambiguous.mp3"] = None
    result = mapper(index, importer)
    assert result.valid and not result.cancelled
    assert [row.match_status for row in result.rows] == ["exact", "basename", "ambiguous", "missing"]
    assert result.roots == index.roots
    assert result.rows[0].source_roots == index.roots
    assert result.rows[1].source_signature == "signature-2"
    assert result.rows[0].beatgrid_count == 2
    assert result.rows[0].phrases_count == 1
    assert result.rows[2].beatgrid_count is None
    assert result.rows[0].inventory_size == 17
    assert result.rows[0].inventory_mtime_ns == 123
    with pytest.raises(FrozenInstanceError):
        result.rows[0].match_status = "missing"
    with pytest.raises(FrozenInstanceError):
        result.valid = False


def test_ambiguous_exact_path_never_basename_fallback(mapper):
    index = inventory(("a.mp3", "new"))
    importer = FakeImporter()
    importer.add(index.entries[0].path, data())
    importer._ambiguous_paths.add(normalized(index.entries[0].path))
    assert mapper(index, importer).rows[0].match_status == "ambiguous"
    assert not importer.calls


def test_missing_inventory_skip_and_unavailable(mapper):
    index = inventory(("gone.mp3", "missing"), ("a.mp3", "new"))
    importer = FakeImporter()
    importer.available = False
    result = mapper(index, importer)
    assert [row.match_status for row in result.rows] == ["missing", "unavailable"]
    assert not importer.calls


def test_aliases_call_signature_and_nested_readers_only_once(mapper):
    index = inventory(("a.mp3", "new"), ("b.mp3", "new"))
    importer = FakeImporter()
    record = data()
    for entry in index.entries:
        importer.add(entry.path, record)
    result = mapper(index, importer)
    assert len(result.rows) == 2
    assert importer.calls == Counter({("signature", "1"): 1, ("beatgrid", "1"): 1, ("phrases", "1"): 1})


def test_guard_failure_invalidates_previously_mapped_rows(mapper):
    index = inventory(("a.mp3", "new"), ("b.mp3", "new"))
    importer = FakeImporter()
    importer.add(index.entries[0].path, data("1"))
    importer.add(index.entries[1].path, data("2"))
    importer.fail_id = "2"
    result = mapper(index, importer)
    assert not result.valid
    assert all(row.match_status == "unavailable" for row in result.rows)
    assert all(row.beatgrid_count is None and row.source_signature is None for row in result.rows)
    assert result.errors
    assert "opaque-sensitive-fixture" not in repr(result)


def test_cancel_rolls_back_and_progress_has_no_confirmed_rows(mapper):
    from threading import Event
    cancel = Event()
    index = inventory(("a.mp3", "new"), ("b.mp3", "new"))
    importer = FakeImporter()
    for entry in index.entries:
        importer.add(entry.path, data())
    progress = []
    def notify(count, path):
        progress.append((count, path))
        cancel.set()
    result = mapper(index, importer, cancel=cancel, progress=notify)
    assert result.cancelled and not result.valid
    assert progress == [(1, index.entries[0].path)]
    assert all(row.match_status == "unavailable" for row in result.rows)


def test_presence_is_not_analysis_claim(mapper):
    index = inventory(("a.mp3", "new"))
    importer = FakeImporter()
    importer.add(index.entries[0].path, data(bpm=0.0, key=None))
    row = mapper(index, importer).rows[0]
    assert row.match_status == "exact"
    assert not row.bpm_present and not row.key_present
    assert row.beatgrid_count == 2


def test_mapper_does_not_open_inventory_files(mapper, monkeypatch):
    import builtins
    from pathlib import Path
    index = inventory(("a.mp3", "new"))
    importer = FakeImporter()
    importer.add(index.entries[0].path, data())
    def forbidden(*args, **kwargs):
        pytest.fail("Mapper darf keine Originaldatei oeffnen")
    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    assert mapper(index, importer).valid


def test_exact_wins_over_ambiguous_basename(mapper):
    index = inventory(("a.mp3", "new"))
    importer = FakeImporter()
    importer.add(index.entries[0].path, data())
    importer.basename_cache["a.mp3"] = None
    assert mapper(index, importer).rows[0].match_status == "exact"


@pytest.mark.parametrize("kind", ["outside", "prefix_sibling", "error", "cancelled"])
def test_invalid_index_never_reads_importer(mapper, kind):
    index = inventory(("a.mp3", "new"))
    if kind == "outside":
        index.entries[0].path = "D:\\outside\\a.mp3"
    elif kind == "prefix_sibling":
        index.entries[0].path = "C:\\fixture-other\\a.mp3"
    elif kind == "error":
        index.errors = ("opaque-sensitive-index",)
    else:
        index.cancelled = True
    importer = FakeImporter()
    importer.add(index.entries[0].path, data())
    result = mapper(index, importer)
    assert not result.valid
    assert not importer.calls
    assert result.rows[0].match_status == "unavailable"
    assert "opaque-sensitive-index" not in repr(result)


def test_callback_failure_invalidates_all(mapper):
    index = inventory(("a.mp3", "new"))
    importer = FakeImporter()
    importer.add(index.entries[0].path, data())
    def fail(count, path):
        raise ValueError("opaque-sensitive-callback")
    result = mapper(index, importer, progress=fail)
    assert not result.valid and result.errors
    assert result.rows[0].source_signature is None
    assert result.rows[0].match_status == "unavailable"
    assert "opaque-sensitive-callback" not in repr(result)


def test_final_progress_cancel_invalidates_last_row(mapper):
    from threading import Event
    stop = Event()
    index = inventory(("a.mp3", "new"))
    importer = FakeImporter()
    importer.add(index.entries[0].path, data())
    result = mapper(index, importer, cancel=stop.is_set, progress=lambda count, path: stop.set())
    assert result.cancelled and not result.valid
    assert result.rows[0].beatgrid_count is None


@pytest.mark.parametrize("field,value", [
    ("duration", 120.0), ("bpm", 130.0), ("key", "Dm"),
    ("cue_points", [{"time": 1.5, "name": "MIX IN"}]), ("genre", "Techno"),
])
def test_memo_context_includes_entire_signature_metadata(mapper, field, value):
    index = inventory(("a.mp3", "new"), ("b.mp3", "new"))
    importer = FakeImporter()
    first, second = data(), data()
    setattr(second, field, value)
    importer.add(index.entries[0].path, first)
    importer.add(index.entries[1].path, second)
    result = mapper(index, importer)
    assert result.valid
    assert importer.calls[("signature", "1")] == 2
    assert importer.calls[("beatgrid", "1")] == 2
    assert importer.calls[("phrases", "1")] == 2


def test_swallowed_empty_detail_is_unverified_not_zero(mapper):
    index = inventory(("a.mp3", "new"))
    importer = FakeImporter()
    importer.add(index.entries[0].path, data())
    def swallowed(path):
        importer._beatgrid_cache["1"] = []
        importer._phrases_cache[("1", 60.0)] = []
        return "signature-with-unknown-empty"
    importer.get_track_signature = swallowed
    row = mapper(index, importer).rows[0]
    assert row.match_status == "exact"
    assert row.beatgrid_count is None and row.phrases_count is None
    assert row.source_signature is None
    assert "detail_read_status_unverified" in row.errors


def test_missing_memo_is_not_empty_success(mapper):
    index = inventory(("a.mp3", "new"))
    importer = FakeImporter()
    importer.add(index.entries[0].path, data())
    importer.get_track_signature = lambda path: "signature-no-memos"
    row = mapper(index, importer).rows[0]
    assert row.beatgrid_count is None and row.phrases_count is None
    assert row.errors


def test_optional_confirmed_missing_status_allows_zero_protocol_only(mapper):
    # Belegt nur den vorgeschlagenen Statusvertrag, keine echte Importerintegration.
    index = inventory(("a.mp3", "new"))
    importer = FakeImporter()
    importer.add(index.entries[0].path, data())
    def empty(path):
        importer._beatgrid_cache["1"] = []
        importer._phrases_cache[("1", 60.0)] = []
        return "signature-confirmed-empty"
    importer.get_track_signature = empty
    importer.get_track_read_status = lambda path: {"beatgrid": "missing", "phrases": "missing"}
    row = mapper(index, importer).rows[0]
    assert row.beatgrid_count == 0 and row.phrases_count == 0
    assert row.source_signature == "signature-confirmed-empty"


def test_fake_ordinary_error_is_local_not_reader_integration_proof(mapper):
    from hpg_core.rekordbox_readonly import RekordboxAnlzReadError
    index = inventory(("a.mp3", "new"), ("b.mp3", "new"))
    importer = FakeImporter()
    importer.add(index.entries[0].path, data("1"))
    importer.add(index.entries[1].path, data("2"))
    original = importer.get_track_signature
    def optional_failure(path):
        if path == index.entries[0].path:
            raise RekordboxAnlzReadError("opaque-sensitive-parse")
        return original(path)
    importer.get_track_signature = optional_failure
    result = mapper(index, importer)
    assert result.valid
    assert result.rows[0].match_status == "exact" and result.rows[0].errors
    assert result.rows[0].beatgrid_count is None
    assert result.rows[1].beatgrid_count == 2
    assert "opaque-sensitive-parse" not in repr(result)


def test_actual_cache_version_no_guessed_source_path(mapper, monkeypatch):
    from hpg_core import caching
    index = inventory(("a.mp3", "new"))
    importer = FakeImporter()
    importer.add(index.entries[0].path, data())
    importer.db = SimpleNamespace(_path="C:\\untrusted\\guess.db")
    monkeypatch.setattr(caching, "CACHE_VERSION", 987)
    result = mapper(index, importer)
    assert result.cache_version == 987
    assert result.source_db_path is None


def test_mapper_never_connects_database_or_stats_source(mapper, monkeypatch):
    import sqlite3
    from sqlcipher3 import dbapi2
    from pathlib import Path
    index = inventory(("a.mp3", "new"))
    importer = FakeImporter()
    importer.add(index.entries[0].path, data())
    def forbidden(*args, **kwargs):
        pytest.fail("Mapper darf weder DB verbinden noch Quelldateien statten")
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(dbapi2, "connect", forbidden)
    monkeypatch.setattr(Path, "stat", forbidden)
    assert mapper(index, importer).valid


def test_one_unverified_detail_does_not_erase_other_nonempty_detail(mapper):
    index = inventory(("a.mp3", "new"))
    importer = FakeImporter()
    importer.add(index.entries[0].path, data())
    original = importer.get_track_signature
    def partially_empty(path):
        signature = original(path)
        importer._phrases_cache[("1", 60.0)] = []
        return signature
    importer.get_track_signature = partially_empty
    row = mapper(index, importer).rows[0]
    assert row.beatgrid_count == 2
    assert row.phrases_count is None and row.source_signature is None


def test_status_error_overrides_stale_nonempty_memos(mapper):
    index = inventory(("a.mp3", "new"))
    importer = FakeImporter()
    importer.add(index.entries[0].path, data())
    importer.get_track_read_status = lambda path: {"beatgrid": "error", "phrases": "error"}
    row = mapper(index, importer).rows[0]
    assert row.beatgrid_count is None and row.phrases_count is None
    assert row.source_signature is None


def test_same_metadata_different_dict_order_reuses_context(mapper):
    index = inventory(("a.mp3", "new"), ("b.mp3", "new"))
    importer = FakeImporter()
    first = data()
    second = SimpleNamespace(**dict(reversed(list(vars(first).items()))))
    importer.add(index.entries[0].path, first)
    importer.add(index.entries[1].path, second)
    assert mapper(index, importer).valid
    assert importer.calls[("signature", "1")] == 1


def test_inconsistent_missing_status_cannot_confirm_nonempty_memo(mapper):
    index = inventory(("a.mp3", "new"))
    importer = FakeImporter()
    importer.add(index.entries[0].path, data())
    importer.get_track_read_status = lambda path: {"beatgrid": "missing", "phrases": "missing"}
    row = mapper(index, importer).rows[0]
    assert row.beatgrid_count is None and row.phrases_count is None
    assert row.source_signature is None


def test_negative_inventory_mtime_rejected_before_importer_read(mapper):
    index = inventory(("a.mp3", "new"))
    index.entries[0].mtime_ns = -1
    importer = FakeImporter()
    importer.add(index.entries[0].path, data())
    result = mapper(index, importer)
    assert not result.valid and result.errors == ("index_invalid",)
    assert result.rows[0].match_status == "unavailable"
    assert not importer.calls
