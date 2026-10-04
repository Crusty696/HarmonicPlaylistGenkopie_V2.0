"""Qt-Inventartests ohne Benutzer-GUI oder Originalmusik."""

from threading import Event
import os

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QDialog, QFileDialog, QWidget

from hpg_core.collection_index import save_collection_index, scan_collection
from hpg_core.collection_jobs import CollectionIndexWorker, LIVE_WORKERS
from hpg_core.collection_panel import CollectionDialog

pytestmark = pytest.mark.gui


@pytest.fixture(autouse=True)
def isolated_collection_state(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))


@pytest.fixture
def dialog(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    widget = CollectionDialog()
    qtbot.addWidget(widget)
    return widget


def test_add_multiple_roots_deduplicate_and_remove(dialog, tmp_path, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    selected = iter([str(a), str(b), str(a), ""])
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **kw: next(selected))
    for _ in range(4):
        dialog.add_button.click()
    assert dialog.roots_list.count() == 2
    dialog.roots_list.setCurrentRow(0)
    dialog.remove_button.click()
    assert dialog.roots_list.count() == 1


def _mapping_index():
    from hpg_core.collection_index import CollectionIndex, CollectionEntry
    return CollectionIndex(("C:\\fixture",), (CollectionEntry("C:\\fixture\\a.mp3", 17, 123, "new"),))


def test_mapping_worker_closes_private_importer_before_result(qtbot, monkeypatch):
    from hpg_core import collection_jobs
    events = []

    class Importer:
        def close(self):
            events.append("close")

    def mapped(index, importer, **kwargs):
        from hpg_core.collection_rekordbox import map_collection_rekordbox
        importer.is_available = lambda: False
        return map_collection_rekordbox(index, importer)

    monkeypatch.setattr(collection_jobs, "map_collection_rekordbox", mapped, raising=False)
    worker = collection_jobs.CollectionRekordboxWorker(_mapping_index(), importer_factory=Importer)
    worker.mapping_done.connect(lambda result: events.append("result"))
    with qtbot.waitSignal(worker.finished, timeout=5000):
        worker.start()
    qtbot.waitUntil(lambda: "result" in events)
    assert events == ["close", "result"]


def test_mapping_unknown_counts_are_not_displayed_as_zero(dialog):
    from hpg_core.collection_rekordbox import CollectionRekordboxMap, CollectionRekordboxRow
    from hpg_core.caching import CACHE_VERSION
    index = _mapping_index()
    dialog.index = index
    dialog.roots_list.addItems(list(index.roots))
    worker = CollectionIndexWorker(previous=index)
    worker.index = index
    dialog.worker = worker
    row = CollectionRekordboxRow(index.entries[0].path, index.roots, 17, 123, "exact",
                                True, False, 2, None, None, ("detail_read_status_unverified",))
    result = CollectionRekordboxMap(index.roots, (row,), CACHE_VERSION, valid=True)
    dialog._on_mapping_done(result, source_worker=worker)
    assert dialog.table.item(0, 7).text() == "2"
    assert "unbekannt" in dialog.table.item(0, 8).text().lower()
    assert "BPM vorhanden" == dialog.table.horizontalHeaderItem(5).text()
    assert "Exact: 1" in dialog.mapping_label.text()
    dialog._invalidate_mapping()
    assert dialog.mapping is None
    assert "nicht geprüft" in dialog.mapping_label.text()
    assert dialog.table.item(0, 7).text() == ""
    dialog.worker = None


@pytest.mark.parametrize("moment", ["before", "close"])
def test_mapping_cancel_never_publishes_confirmed_result(qtbot, monkeypatch, moment):
    from hpg_core import collection_jobs
    from hpg_core.collection_rekordbox import CollectionRekordboxMap
    from hpg_core.caching import CACHE_VERSION
    calls, results = [], []

    class Importer:
        def __init__(self):
            calls.append("open")

        def close(self):
            calls.append("close")
            if moment == "close":
                worker.request_cancel()

    monkeypatch.setattr(collection_jobs, "map_collection_rekordbox",
                        lambda index, importer, **kw: CollectionRekordboxMap(
                            index.roots, (), CACHE_VERSION, valid=not bool(kw.get("cancel") and kw["cancel"].is_set()),
                            cancelled=bool(kw.get("cancel") and kw["cancel"].is_set())))
    worker = collection_jobs.CollectionRekordboxWorker(_mapping_index(), importer_factory=Importer)
    worker.mapping_done.connect(results.append)
    if moment == "before":
        worker.request_cancel()
    with qtbot.waitSignal(worker.finished, timeout=5000):
        worker.start()
    qtbot.waitUntil(lambda: bool(results))
    assert not results[0].valid and results[0].cancelled
    assert calls == ([] if moment == "before" else ["open", "close"])


def test_mapping_stale_result_and_root_change_cannot_confirm_old_map(dialog):
    from hpg_core.collection_rekordbox import CollectionRekordboxMap
    from hpg_core.caching import CACHE_VERSION
    index = _mapping_index()
    dialog.index = index
    dialog.roots_list.addItems(list(index.roots))
    stale = CollectionIndexWorker(previous=index)
    stale.index = index
    current = CollectionIndexWorker(previous=index)
    current.index = index
    dialog.worker = current
    dialog._on_mapping_done(CollectionRekordboxMap(index.roots, (), CACHE_VERSION, valid=True), source_worker=stale)
    assert dialog.mapping is None
    dialog.worker = None
    dialog.mapping = object()
    dialog.roots_list.setCurrentRow(0)
    dialog._remove_roots()
    assert dialog.mapping is None
    assert not dialog.mapping_button.isEnabled()


def test_mapping_cancel_after_emission_before_gui_slot_is_not_confirmed(dialog):
    from hpg_core.collection_rekordbox import CollectionRekordboxMap, CollectionRekordboxRow
    from hpg_core.caching import CACHE_VERSION
    index = _mapping_index()
    dialog.index = index
    worker = CollectionIndexWorker(previous=index)
    worker.index = index
    dialog.worker = worker
    row = CollectionRekordboxRow(index.entries[0].path, index.roots, 17, 123, "exact")
    result = CollectionRekordboxMap(index.roots, (row,), CACHE_VERSION, valid=True)
    worker.request_cancel()
    try:
        dialog._on_mapping_done(result, source_worker=worker)
        assert dialog.mapping is None
    finally:
        dialog.worker = None


def test_worker_inventory_signal_and_finished_are_distinct(qtbot, tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    (root / "track.mp3").write_text("TEXT FIXTURE", encoding="utf-8")
    worker = CollectionIndexWorker([root])
    assert worker.scan_done is not worker.finished
    results = []
    worker.scan_done.connect(results.append)
    with qtbot.waitSignal(worker.finished, timeout=5000):
        worker.start()
    if sip.isdeleted(worker):
        assert worker not in LIVE_WORKERS
    else:
        assert worker.wait(2000)
    qtbot.waitUntil(lambda: bool(results), timeout=2000)
    assert len(results[0].entries) == 1
    if not sip.isdeleted(worker):
        worker.deleteLater()


def test_worker_cancel_before_start_preserves_snapshot(qtbot, tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    (root / "track.mp3").write_text("TEXT FIXTURE", encoding="utf-8")
    previous = scan_collection([root])
    worker = CollectionIndexWorker([root], previous=previous)
    results = []
    worker.scan_done.connect(results.append)
    worker.request_cancel()
    with qtbot.waitSignal(worker.finished, timeout=5000):
        worker.start()
    if sip.isdeleted(worker):
        assert worker not in LIVE_WORKERS
    else:
        assert worker.wait(2000)
    qtbot.waitUntil(lambda: bool(results), timeout=2000)
    assert results[0].cancelled
    assert results[0].entries == previous.entries
    if not sip.isdeleted(worker):
        worker.deleteLater()


def test_native_dialog_scan_counts_and_cleanup(dialog, qtbot, tmp_path, monkeypatch):
    root = tmp_path / "source"
    root.mkdir()
    (root / "track.mp3").write_text("TEXT FIXTURE", encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **kw: str(root))
    dialog.add_button.click()
    dialog.start_button.click()
    qtbot.waitUntil(lambda: dialog.worker is None, timeout=5000)
    assert dialog.table.rowCount() == 1
    assert "1" in dialog.status_label.text()
    assert "Inventar" in dialog.status_label.text()
    assert dialog.start_button.isEnabled()
    assert not dialog.cancel_button.isEnabled()
    assert (tmp_path / "local" / "HPG" / "collection_index.json").is_file()


def test_stale_callbacks_cannot_update_dialog(dialog):
    current, stale = object(), object()
    dialog.worker = current
    before = dialog.status_label.text()
    dialog._on_progress(50, "stale path", source_worker=stale)
    dialog._on_scan_done(None, source_worker=stale)
    dialog._cleanup_worker(source_worker=stale)
    assert dialog.status_label.text() == before
    assert dialog.worker is current
    dialog.worker = None


def test_callbacks_without_current_worker_do_nothing(dialog):
    before = dialog.status_label.text()
    dialog._on_progress(1, "unowned")
    dialog._on_scan_done(None)
    dialog._cleanup_worker()
    assert dialog.worker is None
    assert dialog.status_label.text() == before


def test_saved_inventory_load_restores_roots_and_table_without_scan(dialog, qtbot, tmp_path, monkeypatch):
    from hpg_core import collection_jobs
    root = tmp_path / "source"
    root.mkdir()
    (root / "track.mp3").write_text("TEXT FIXTURE", encoding="utf-8")
    saved = scan_collection([root])
    save_collection_index(saved)
    original = os.lstat

    def forbid_source_stat(path, *args, **kwargs):
        normalized = os.path.normcase(os.path.abspath(path))
        if normalized == os.path.normcase(str(root)) or normalized.startswith(os.path.normcase(str(root)) + os.sep):
            pytest.fail("Laden darf keine Musikpfade statten")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", forbid_source_stat)
    monkeypatch.setattr(collection_jobs, "scan_collection",
                        lambda *args, **kwargs: pytest.fail("Laden darf keinen Scan starten"))
    dialog.load_button.click()
    qtbot.waitUntil(lambda: dialog.worker is None, timeout=5000)
    assert dialog.index == saved
    assert dialog.roots_list.count() == 1
    assert dialog.roots_list.item(0).text() == str(root)
    assert dialog.table.rowCount() == 1
    assert "Gespeichertes Inventar" in dialog.status_label.text()
    assert "nicht frisch geprüft" in dialog.status_label.text()


def test_next_scan_compares_against_restored_inventory(dialog, qtbot, tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    (root / "track.mp3").write_text("TEXT FIXTURE", encoding="utf-8")
    save_collection_index(scan_collection([root]))
    dialog.load_button.click()
    qtbot.waitUntil(lambda: dialog.worker is None, timeout=5000)
    dialog.start_button.click()
    qtbot.waitUntil(lambda: dialog.worker is None, timeout=5000)
    assert dialog.index.entries[0].status == "unchanged"


def test_unknown_saved_format_is_visible_and_never_overwritten(dialog, qtbot, tmp_path):
    destination = tmp_path / "local" / "HPG" / "collection_index.json"
    destination.parent.mkdir(parents=True)
    destination.write_text('{"user_data":"preserve"}', encoding="utf-8")
    before = destination.read_bytes()
    dialog.load_button.click()
    qtbot.waitUntil(lambda: dialog.worker is None, timeout=5000)
    assert "Unbekanntes Inventarformat" in dialog.status_label.text()
    assert dialog.index is None
    assert dialog.roots_list.count() == 0
    assert destination.read_bytes() == before


class _ControlledWorker(QThread):
    scan_done = pyqtSignal(object)
    progress_update = pyqtSignal(int, str)

    def __init__(self, roots, previous=None, parent=None):
        super().__init__(parent)
        self.roots = roots
        self.previous = previous
        self.cancel = Event()
        self.release = Event()

    def request_cancel(self):
        self.cancel.set()

    def run(self):
        self.scan_done.emit(scan_collection(self.roots, previous=self.previous,
                                             cancel=self.cancel.is_set))
        self.release.wait(3)


def test_result_does_not_cleanup_running_thread(dialog, qtbot, tmp_path, monkeypatch):
    from hpg_core import collection_panel
    root = tmp_path / "source"
    root.mkdir()
    monkeypatch.setattr(collection_panel, "CollectionIndexWorker", _ControlledWorker)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **kw: str(root))
    dialog.add_button.click()
    dialog.start_button.click()
    worker = dialog.worker
    try:
        qtbot.waitUntil(lambda: "Inventar" in dialog.status_label.text(), timeout=2000)
        assert dialog.worker is worker
        assert worker.isRunning()
        assert not dialog.start_button.isEnabled()
    finally:
        worker.release.set()
        qtbot.waitUntil(lambda: dialog.worker is None, timeout=5000)


@pytest.mark.parametrize("route, expected", [
    ("accept", QDialog.DialogCode.Accepted),
    ("reject", QDialog.DialogCode.Rejected),
    ("done_accept", QDialog.DialogCode.Accepted),
    ("done_reject", QDialog.DialogCode.Rejected),
    ("close", QDialog.DialogCode.Rejected),
])
def test_all_dialog_exit_routes_wait_for_thread_finished(
    dialog, qtbot, tmp_path, monkeypatch, route, expected
):
    from hpg_core import collection_panel
    root = tmp_path / "source"
    root.mkdir()
    monkeypatch.setattr(collection_panel, "CollectionIndexWorker", _ControlledWorker)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **kw: str(root))
    dialog.add_button.click()
    exits = []
    dialog.finished.connect(exits.append)
    dialog.show()
    dialog.start_button.click()
    worker = dialog.worker
    try:
        # Der Ergebnis-Callback ist absichtlich frueher als das Thread-Ende.
        qtbot.waitUntil(lambda: "Inventar" in dialog.status_label.text(), timeout=2000)
        if route.startswith("done_"):
            dialog.done(int(expected))
        else:
            getattr(dialog, route)()
        assert worker.cancel.is_set()
        assert worker.isRunning()
        assert dialog.worker is worker
        assert dialog.isVisible()
        assert exits == []
        assert not dialog.start_button.isEnabled()
        assert not dialog.add_button.isEnabled()
        assert not dialog.remove_button.isEnabled()
    finally:
        worker.release.set()
        qtbot.waitUntil(lambda: dialog.worker is None, timeout=5000)
    qtbot.waitUntil(lambda: bool(exits), timeout=2000)
    assert exits == [int(expected)]
    assert not dialog.isVisible()


def test_repeated_close_does_not_release_worker_early(dialog, qtbot, tmp_path, monkeypatch):
    from hpg_core import collection_panel
    root = tmp_path / "source"
    root.mkdir()
    monkeypatch.setattr(collection_panel, "CollectionIndexWorker", _ControlledWorker)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **kw: str(root))
    dialog.add_button.click()
    exits = []
    dialog.finished.connect(exits.append)
    dialog.show()
    dialog.start_button.click()
    worker = dialog.worker
    try:
        dialog.close()
        dialog.reject()
        dialog.done(int(QDialog.DialogCode.Rejected))
        assert worker.cancel.is_set()
        assert dialog.worker is worker
        assert dialog.isVisible()
        assert exits == []
    finally:
        worker.release.set()
        qtbot.waitUntil(lambda: dialog.worker is None, timeout=5000)
    qtbot.waitUntil(lambda: bool(exits), timeout=2000)
    assert exits == [int(QDialog.DialogCode.Rejected)]


def test_root_controls_remain_disabled_until_finished(dialog, qtbot, tmp_path, monkeypatch):
    from hpg_core import collection_panel
    root = tmp_path / "source"
    root.mkdir()
    monkeypatch.setattr(collection_panel, "CollectionIndexWorker", _ControlledWorker)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **kw: str(root))
    dialog.add_button.click()
    dialog.start_button.click()
    worker = dialog.worker
    try:
        qtbot.waitUntil(lambda: "Inventar" in dialog.status_label.text(), timeout=2000)
        assert not dialog.add_button.isEnabled()
        assert not dialog.remove_button.isEnabled()
        assert not dialog.start_button.isEnabled()
        dialog.cancel_button.click()
        assert worker.cancel.is_set()
        assert dialog.worker is worker
    finally:
        worker.release.set()
        qtbot.waitUntil(lambda: dialog.worker is None, timeout=5000)
    assert dialog.add_button.isEnabled()
    assert dialog.remove_button.isEnabled()
    assert dialog.start_button.isEnabled()


def test_close_requests_cooperative_cancel_without_destroying_worker(dialog, qtbot, tmp_path, monkeypatch):
    from hpg_core import collection_panel
    root = tmp_path / "source"
    root.mkdir()
    monkeypatch.setattr(collection_panel, "CollectionIndexWorker", _ControlledWorker)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **kw: str(root))
    dialog.add_button.click()
    dialog.start_button.click()
    worker = dialog.worker
    try:
        dialog.reject()
        assert worker.cancel.is_set()
        assert dialog.worker is worker
    finally:
        worker.release.set()
        qtbot.waitUntil(lambda: dialog.worker is None, timeout=5000)


def test_forced_parent_deletion_keeps_actual_worker_alive_until_finished(qtbot, tmp_path, monkeypatch):
    from hpg_core import collection_jobs
    root = tmp_path / "source"
    root.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    release, started = Event(), Event()
    workers = []

    def paused_run(worker):
        workers.append(worker)
        started.set()
        release.wait(5)
        # Spaetes Ergebnis darf kein geloeschtes Widget mehr beruehren.
        worker.progress_update.emit(1, "late")
        worker.scan_done.emit(scan_collection([root], cancel=worker.cancel))

    monkeypatch.setattr(CollectionIndexWorker, "run", paused_run)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **kw: str(root))
    parent = QWidget()
    widget = CollectionDialog(parent)
    widget.add_button.click()
    widget.start_button.click()
    worker = widget.worker
    assert worker.parent() is None
    try:
        qtbot.waitUntil(started.is_set, timeout=2000)
        parent.deleteLater()
        qtbot.waitUntil(lambda: sip.isdeleted(parent), timeout=2000)
        assert sip.isdeleted(widget)
        assert not sip.isdeleted(worker)
        assert worker.isRunning()
        assert worker.cancel.is_set()
        assert worker in collection_jobs.LIVE_WORKERS
    finally:
        release.set()
        qtbot.waitUntil(lambda: worker not in collection_jobs.LIVE_WORKERS, timeout=5000)
    qtbot.waitUntil(lambda: sip.isdeleted(worker), timeout=2000)


def _persist_sample(tmp_path):
    from hpg_core.collection_index import CollectionIndex, CollectionEntry
    from hpg_core.collection_rekordbox import CollectionRekordboxMap, CollectionRekordboxRow
    from hpg_core.caching import CACHE_VERSION
    root = str(tmp_path / "never-open-music")
    path = str(tmp_path / "never-open-music" / "track.aiff")
    index = CollectionIndex((root,), (CollectionEntry(path, 17, 123, "new"),))
    row = CollectionRekordboxRow(path, (root,), 17, 123, "exact", True, False, 0, None,
                                "opaque", ("detail_read_status_unverified",))
    return index, CollectionRekordboxMap((root,), (row,), CACHE_VERSION,
                                       str(tmp_path / "never-open.db"), True)


def _install_fresh(dialog, index, mapping):
    dialog.index = index
    dialog.roots_list.addItems(list(index.roots))
    worker = CollectionIndexWorker(previous=index)
    worker.index = index
    worker.observed_at_ns = 0
    dialog.worker = worker
    dialog._on_mapping_done(mapping, source_worker=worker)
    dialog.worker = None
    worker.deleteLater()
    dialog._set_busy(False)


def _run_state_worker(qtbot, index, *, action, mapping=None):
    from hpg_core.collection_jobs import CollectionMappingStateWorker
    from hpg_core.caching import CACHE_VERSION
    worker = CollectionMappingStateWorker(index, action=action, mapping=mapping,
                                          observed_at_ns=0, expected_cache_version=CACHE_VERSION)
    results = []
    worker.mapping_state_done.connect(results.append)
    with qtbot.waitSignal(worker.finished, timeout=5000):
        worker.start()
    qtbot.waitUntil(lambda: bool(results))
    return results[0]


def test_mapping_state_actual_workers_roundtrip_fixed_keys_detached(qtbot, tmp_path):
    from dataclasses import replace, FrozenInstanceError
    index, mapping = _persist_sample(tmp_path)
    mutable = replace(mapping, rows=list(mapping.rows))
    result = _run_state_worker(qtbot, index, action="save", mapping=mutable)
    assert set(result) == {"action", "indexSnapshot", "mapSnapshot", "provenance",
                           "committed", "cancelled", "opaqueerror"}
    assert result["action"] == "save" and result["committed"]
    mutable.rows.clear()
    assert len(result["mapSnapshot"].rows) == 1
    with pytest.raises(FrozenInstanceError):
        result["mapSnapshot"].rows[0].beatgrid_count = 1
    loaded = _run_state_worker(qtbot, index, action="load")
    assert loaded["mapSnapshot"] == mapping
    assert loaded["indexSnapshot"] == index
    assert loaded["provenance"] == "saved_not_fresh"
    assert not loaded["committed"] and not loaded["cancelled"]


def test_mapping_state_panel_save_load_real_json_no_gui_io(dialog, qtbot, tmp_path, monkeypatch):
    from hpg_core import collection_jobs
    from PyQt6.QtCore import QCoreApplication
    index, mapping = _persist_sample(tmp_path)
    _install_fresh(dialog, index, mapping)
    assert dialog.save_mapping_button.isEnabled()
    original_save, original_load = collection_jobs.save_collection_mapping_state, collection_jobs.load_collection_mapping_state
    threads = []

    def off_gui(function):
        def run(*args, **kwargs):
            threads.append(QThread.currentThread() is QCoreApplication.instance().thread())
            return function(*args, **kwargs)
        return run

    monkeypatch.setattr(collection_jobs, "save_collection_mapping_state", off_gui(original_save))
    monkeypatch.setattr(collection_jobs, "load_collection_mapping_state", off_gui(original_load))
    dialog.save_mapping_button.click()
    qtbot.waitUntil(lambda: dialog.worker is None)
    assert "gespeichert" in dialog.mapping_label.text()
    dialog._invalidate_mapping()
    dialog.load_mapping_button.click()
    qtbot.waitUntil(lambda: dialog.worker is None)
    assert threads == [False, False]
    assert dialog.mapping == mapping
    assert dialog.mapping_provenance == "saved_not_fresh"
    assert dialog.mapping_observed_at_ns == 0
    assert "nicht frisch geprüft" in dialog.mapping_label.text()
    assert "Gespeichert" in dialog.table.item(0, 10).text()
    assert "nicht frisch" in dialog.table.item(0, 7).toolTip()
    assert not dialog.save_mapping_button.isEnabled()


def test_mapping_state_save_unknown_format_is_visible_preserved(dialog, qtbot, tmp_path):
    index, mapping = _persist_sample(tmp_path)
    _install_fresh(dialog, index, mapping)
    destination = tmp_path / "local" / "HPG" / "collection_mapping.json"
    destination.parent.mkdir(parents=True)
    destination.write_text('{"private":"KEEP SECRET"}', encoding="utf-8")
    before = destination.read_bytes()
    dialog.save_mapping_button.click()
    qtbot.waitUntil(lambda: dialog.worker is None)
    assert "nicht gespeichert" in dialog.mapping_label.text()
    assert "KEEP SECRET" not in dialog.mapping_label.text()
    assert destination.read_bytes() == before


def test_mapping_state_load_missing_index_has_no_source_fallback(dialog, monkeypatch):
    from hpg_core import collection_panel
    monkeypatch.setattr(collection_panel, "CollectionMappingStateWorker",
                        lambda *args, **kw: pytest.fail("Kein Index, kein Worker"))
    dialog._load_mapping()
    assert dialog.worker is None
    assert not dialog.load_mapping_button.isEnabled()
    assert "Inventar" in dialog.mapping_label.text()


def test_mapping_state_load_never_accesses_originals(dialog, qtbot, tmp_path, monkeypatch):
    import io
    from hpg_core import collection_jobs
    from hpg_core.collection_mapping_state import make_mapping_state, save_collection_mapping_state
    index, mapping = _persist_sample(tmp_path)
    save_collection_mapping_state(make_mapping_state(index, mapping, observed_at_ns=0))
    dialog.index = index
    dialog.roots_list.addItems(list(index.roots))
    dialog._set_busy(False)
    forbidden = {index.roots[0], index.entries[0].path, mapping.source_db_path}

    def guarded(function):
        def call(path, *args, **kwargs):
            if isinstance(path, (str, os.PathLike)) and os.fspath(path) in forbidden:
                raise AssertionError("Originalzugriff beim Laden")
            return function(path, *args, **kwargs)
        return call

    monkeypatch.setattr(os, "stat", guarded(os.stat))
    monkeypatch.setattr(os, "lstat", guarded(os.lstat))
    monkeypatch.setattr(io, "open", guarded(io.open))
    monkeypatch.setattr(collection_jobs, "map_collection_rekordbox", lambda *a, **k: pytest.fail("Kein Mapper beim Laden"))
    dialog.load_mapping_button.click()
    qtbot.waitUntil(lambda: dialog.worker is None)
    assert dialog.mapping == mapping


@pytest.mark.parametrize("action", ["save", "load"])
def test_mapping_state_result_waits_actual_finished_and_parent_delete(qtbot, tmp_path, monkeypatch, action):
    from hpg_core import collection_jobs
    from hpg_core.collection_mapping_state import make_mapping_state, save_collection_mapping_state
    index, mapping = _persist_sample(tmp_path)
    save_collection_mapping_state(make_mapping_state(index, mapping, observed_at_ns=0))
    parent = QWidget()
    widget = CollectionDialog(parent)
    _install_fresh(widget, index, mapping)
    release, started = Event(), Event()
    original = collection_jobs.CollectionMappingStateWorker.run

    def delayed(worker):
        started.set()
        release.wait(5)
        original(worker)

    monkeypatch.setattr(collection_jobs.CollectionMappingStateWorker, "run", delayed)
    getattr(widget, "_save_mapping" if action == "save" else "_load_mapping")()
    worker = widget.worker
    try:
        qtbot.waitUntil(started.is_set)
        assert worker.parent() is None
        parent.deleteLater()
        qtbot.waitUntil(lambda: sip.isdeleted(widget))
        assert worker in LIVE_WORKERS and worker.isRunning()
        assert worker.cancel.is_set()
    finally:
        release.set()
        qtbot.waitUntil(lambda: worker not in LIVE_WORKERS, timeout=5000)
    qtbot.waitUntil(lambda: sip.isdeleted(worker))


@pytest.mark.parametrize("route", ["reject", "close", "done"])
def test_mapping_state_close_pending_never_revives_ui(dialog, qtbot, tmp_path, monkeypatch, route):
    from hpg_core import collection_jobs
    index, mapping = _persist_sample(tmp_path)
    _install_fresh(dialog, index, mapping)
    release, emitted = Event(), Event()
    original = collection_jobs.CollectionMappingStateWorker.run

    def emit_then_hold(worker):
        original(worker)
        emitted.set()
        release.wait(5)

    monkeypatch.setattr(collection_jobs.CollectionMappingStateWorker, "run", emit_then_hold)
    dialog._save_mapping()
    worker = dialog.worker
    try:
        # Ergebnis ist queued; Schließen geschieht deterministisch vor dem UI-Slot.
        assert emitted.wait(3)
        if route == "done":
            dialog.done(int(QDialog.DialogCode.Rejected))
        else:
            getattr(dialog, route)()
        before = dialog.mapping_label.text()
        qtbot.waitUntil(lambda: worker.isRunning())
        assert dialog.mapping_label.text() == before
        assert dialog.worker is worker and not dialog.save_mapping_button.isEnabled()
    finally:
        release.set()
        qtbot.waitUntil(lambda: dialog.worker is None, timeout=5000)
    assert dialog.mapping_label.text() == before
    assert not dialog.save_mapping_button.isEnabled()


@pytest.mark.parametrize("action", ["save", "load"])
def test_mapping_state_late_cancel_save_commit_load_reject(dialog, qtbot, tmp_path, monkeypatch, action):
    from hpg_core import collection_jobs
    from hpg_core.collection_mapping_state import make_mapping_state, save_collection_mapping_state
    index, mapping = _persist_sample(tmp_path)
    save_collection_mapping_state(make_mapping_state(index, mapping, observed_at_ns=0))
    _install_fresh(dialog, index, mapping)
    original = collection_jobs.CollectionMappingStateWorker.run

    def cancelled_after_emit(worker):
        original(worker)
        worker.request_cancel()

    monkeypatch.setattr(collection_jobs.CollectionMappingStateWorker, "run", cancelled_after_emit)
    getattr(dialog, "_save_mapping" if action == "save" else "_load_mapping")()
    qtbot.waitUntil(lambda: dialog.worker is None)
    if action == "save":
        assert "gespeichert" in dialog.mapping_label.text()
        assert "Quellen nicht erneut geprüft" in dialog.mapping_label.text()
    else:
        assert dialog.mapping is None
        assert "abgebrochen" in dialog.mapping_label.text()


@pytest.mark.parametrize("change", ["index", "roots", "mapping", "mapping_identity", "mapping_values", "cache", "source"])
def test_mapping_state_stale_context_is_rejected(dialog, qtbot, tmp_path, monkeypatch, change):
    from dataclasses import replace
    from hpg_core import collection_jobs, collection_panel
    index, mapping = _persist_sample(tmp_path)
    if change == "mapping_values":
        mapping = replace(mapping, rows=list(mapping.rows))
    _install_fresh(dialog, index, mapping)
    release, emitted = Event(), Event()
    original = collection_jobs.CollectionMappingStateWorker.run

    def emit_hold(worker):
        original(worker)
        emitted.set()
        release.wait(5)

    monkeypatch.setattr(collection_jobs.CollectionMappingStateWorker, "run", emit_hold)
    dialog._save_mapping()
    worker = dialog.worker
    try:
        # Keine Qt-Pumps zwischen Emission und Kontextwechsel.
        assert emitted.wait(3)
        if change == "index":
            dialog.index = replace(index, entries=(replace(index.entries[0], status="changed"),))
        elif change == "roots":
            dialog.roots_list.clear()
        elif change == "mapping":
            dialog._invalidate_mapping()
        elif change == "mapping_identity":
            dialog.mapping = replace(mapping, source_db_path=None)
        elif change == "mapping_values":
            mapping.rows[0] = replace(mapping.rows[0], source_signature="changed-in-ram")
        elif change == "cache":
            monkeypatch.setattr(collection_panel.caching, "CACHE_VERSION", mapping.cache_version + 1)
        else:
            dialog.worker = object()
        before = dialog.mapping_label.text()
        dialog._on_mapping_state_done({"action": "save", "indexSnapshot": index,
            "mapSnapshot": mapping, "provenance": "observed_in_session", "committed": True,
            "cancelled": False, "opaqueerror": None}, source_worker=worker)
        assert dialog.mapping_label.text() == before
        if change == "roots":
            assert dialog.mapping is None
    finally:
        dialog.worker = worker
        release.set()
        qtbot.waitUntil(lambda: dialog.worker is None, timeout=5000)


@pytest.mark.parametrize("action", ["save", "load"])
def test_mapping_state_cancel_before_start_performs_no_json_io(qtbot, tmp_path, monkeypatch, action):
    from hpg_core import collection_jobs
    from hpg_core.caching import CACHE_VERSION
    index, mapping = _persist_sample(tmp_path)
    worker = collection_jobs.CollectionMappingStateWorker(index, action=action, mapping=mapping,
        observed_at_ns=0, expected_cache_version=CACHE_VERSION)
    monkeypatch.setattr(collection_jobs, "save_collection_mapping_state", lambda *a, **k: pytest.fail("Save trotz Cancel"))
    monkeypatch.setattr(collection_jobs, "load_collection_mapping_state", lambda *a, **k: pytest.fail("Load trotz Cancel"))
    results = []
    worker.mapping_state_done.connect(results.append)
    worker.request_cancel()
    with qtbot.waitSignal(worker.finished, timeout=5000):
        worker.start()
    qtbot.waitUntil(lambda: bool(results))
    assert results[0]["cancelled"] and not results[0]["committed"]
    assert results[0]["mapSnapshot"] is None


def test_mapping_state_saved_invalid_report_is_never_fresh_or_saveable(dialog, qtbot, tmp_path):
    from dataclasses import replace
    from hpg_core.collection_mapping_state import make_mapping_state, save_collection_mapping_state
    index, mapping = _persist_sample(tmp_path)
    row = replace(mapping.rows[0], match_status="unavailable", bpm_present=None, key_present=None,
                  beatgrid_count=None, phrases_count=None, source_signature=None, errors=("unknown",))
    failed = replace(mapping, rows=(row,), valid=False, errors=("mapping_operation_failed",))
    save_collection_mapping_state(make_mapping_state(index, failed, observed_at_ns=0))
    dialog.index = index
    dialog.roots_list.addItems(list(index.roots))
    dialog._set_busy(False)
    dialog.load_mapping_button.click()
    qtbot.waitUntil(lambda: dialog.worker is None)
    assert dialog.mapping == failed
    assert dialog.mapping_provenance == "saved_not_fresh"
    assert not dialog.save_mapping_button.isEnabled()
    assert "nicht frisch geprüft" in dialog.mapping_label.text()


def test_mapping_state_save_rejects_changed_snapshot_before_launch(dialog, tmp_path, monkeypatch):
    from dataclasses import replace
    from hpg_core import collection_panel
    index, mapping = _persist_sample(tmp_path)
    _install_fresh(dialog, index, mapping)
    dialog.index = replace(index, entries=(replace(index.entries[0], mtime_ns=124),))
    monkeypatch.setattr(collection_panel, "CollectionMappingStateWorker",
                        lambda *a, **k: pytest.fail("Stale Mapping darf nicht gespeichert werden"))
    dialog._save_mapping()
    assert dialog.worker is None
    assert "Keine gültige" in dialog.mapping_label.text()
