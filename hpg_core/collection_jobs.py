"""Qt-Worker fuer das Inventar, unabhaengig von der Lebensdauer eines Dialogs."""

from threading import Event
from dataclasses import replace
from copy import deepcopy
from time import time_ns

from PyQt6 import sip
from PyQt6.QtCore import QThread, Qt, pyqtSignal

from .collection_index import (
    CollectionIndex, load_collection_index, save_collection_index, scan_collection,
)
from .collection_rekordbox import map_collection_rekordbox
from .collection_mapping_state import (
    make_mapping_state, load_collection_mapping_state, save_collection_mapping_state,
)


LIVE_WORKERS = set()


def _finish_worker(worker):
    """Nur das echte Thread-Ende gibt die unabhaengige Referenz frei."""
    if sip.isdeleted(worker):
        LIVE_WORKERS.discard(worker)
        return
    if worker.isRunning() or not worker.wait(2000):
        return
    LIVE_WORKERS.discard(worker)
    worker.deleteLater()


def cancel_worker(worker):
    if worker is not None and not sip.isdeleted(worker):
        worker.request_cancel()


class CollectionIndexWorker(QThread):
    progress_update = pyqtSignal(int, str)
    scan_done = pyqtSignal(object)

    def __init__(self, roots=(), previous=None, parent=None, *, mode="scan"):
        # QObject-Parent darf einen noch laufenden Thread nicht zerstoeren.
        super().__init__(None)
        self.roots = tuple(roots)
        self.previous = previous
        self.mode = mode
        self.cancel = Event()
        self.finished.connect(lambda: _finish_worker(self), Qt.ConnectionType.QueuedConnection)

    def start(self, priority=QThread.Priority.InheritPriority):
        LIVE_WORKERS.add(self)
        try:
            super().start(priority)
        except Exception:
            LIVE_WORKERS.discard(self)
            raise

    def request_cancel(self):
        self.cancel.set()

    def run(self):
        previous = self.previous
        try:
            if self.cancel.is_set():
                result = CollectionIndex(previous.roots if previous else tuple(self.roots),
                                         previous.entries if previous else (), cancelled=True)
            elif self.mode == "load":
                result = load_collection_index()
                if self.cancel.is_set():
                    result = CollectionIndex(previous.roots if previous else (),
                                             previous.entries if previous else (), cancelled=True)
            else:
                if self.mode != "scan":
                    raise ValueError("Unbekannter Inventarauftrag")
                if previous is None:
                    previous = load_collection_index()
                result = scan_collection(
                    self.roots, previous=previous, cancel=self.cancel,
                    progress=lambda count, path: self.progress_update.emit(count, path),
                )
                if not result.errors and not result.cancelled:
                    save_collection_index(result, cancel=self.cancel)
        except InterruptedError:
            result = CollectionIndex(previous.roots if previous else tuple(self.roots),
                                     previous.entries if previous else (), cancelled=True)
        except Exception as exc:
            result = CollectionIndex(previous.roots if previous else tuple(self.roots),
                                     previous.entries if previous else (), (str(exc),))
        self.scan_done.emit(result)


class _UnavailableImporter:
    def is_available(self):
        return False


class CollectionRekordboxWorker(CollectionIndexWorker):
    """Eigener Importer pro Auftrag; Ergebnis erst nach dessen Schliessen."""
    mapping_done = pyqtSignal(object)

    def __init__(self, index, parent=None, *, importer_factory=None):
        super().__init__(previous=index, mode="mapping")
        self.index = index
        self.importer_factory = importer_factory
        self.observed_at_ns = None

    def run(self):
        importer = None
        result = None
        try:
            if self.cancel.is_set():
                result = map_collection_rekordbox(self.index, _UnavailableImporter(), cancel=self.cancel)
            else:
                factory = self.importer_factory
                if factory is None:
                    from .rekordbox_importer import RekordboxImporter
                    factory = RekordboxImporter
                importer = factory()
                result = map_collection_rekordbox(
                    self.index, importer, cancel=self.cancel,
                    progress=lambda count, path: self.progress_update.emit(count, path),
                )
        except Exception:
            result = replace(map_collection_rekordbox(self.index, _UnavailableImporter()),
                             errors=("mapping_operation_failed",))
        finally:
            if importer is not None:
                try:
                    importer.close()
                except Exception:
                    result = replace(map_collection_rekordbox(self.index, _UnavailableImporter()),
                                     errors=("importer_close_failed",))
        if self.cancel.is_set():
            result = map_collection_rekordbox(self.index, _UnavailableImporter(), cancel=self.cancel)
        # Beobachtungsende, kein gemeinsamer DB-/ANLZ-Snapshot und keine Speicherzeit.
        self.observed_at_ns = time_ns()
        self.mapping_done.emit(result)


def mapping_index_binding(index, cache_version):
    """Vollständige RAM-Bindung, ohne Dateioperation oder Signaturberechnung."""
    return (tuple(index.roots),
            tuple((entry.path, entry.size, entry.mtime_ns, entry.status) for entry in index.entries),
            cache_version)


class CollectionMappingStateWorker(CollectionIndexWorker):
    """Eigene Mapping-JSON nur im Thread laden/speichern; Registry erben."""
    mapping_state_done = pyqtSignal(object)

    def __init__(self, index, parent=None, *, action, mapping=None,
                 observed_at_ns=None, expected_cache_version):
        super().__init__(previous=index, mode="mapping_" + action)
        self.index = index
        self.action = action
        self.mapping = mapping
        self.observed_at_ns = observed_at_ns
        self.expected_cache_version = expected_cache_version

    def run(self):
        result = {"action": self.action, "indexSnapshot": None, "mapSnapshot": None,
                  "provenance": None, "committed": False, "cancelled": False,
                  "opaqueerror": None}
        try:
            if self.cancel.is_set():
                raise InterruptedError()
            if type(self.expected_cache_version) is not int or self.expected_cache_version <= 0:
                raise ValueError()
            # Auch manuell mit Listen konstruierte Frozen-Dataclasses entkoppeln.
            index = deepcopy(self.index)
            if self.action == "save":
                snapshot = make_mapping_state(index, deepcopy(self.mapping), observed_at_ns=self.observed_at_ns)
                if snapshot.cache_version != self.expected_cache_version:
                    raise ValueError()
                save_collection_mapping_state(snapshot, cancel=self.cancel)
                result.update(indexSnapshot=snapshot.index_snapshot, mapSnapshot=snapshot.mapping,
                              provenance="observed_in_session", committed=True)
            elif self.action == "load":
                saved = load_collection_mapping_state(index=index, expected_cache_version=self.expected_cache_version)
                if saved is not None:
                    self.observed_at_ns = saved.state.observed_at_ns
                    result.update(indexSnapshot=saved.state.index_snapshot, mapSnapshot=saved.state.mapping,
                                  provenance=saved.provenance)
            else:
                raise ValueError()
        except InterruptedError:
            result["cancelled"] = True
        except Exception:
            # Keine fremde Payload oder Original-Exception an die Oberfläche geben.
            result["opaqueerror"] = "mapping_state_operation_failed"
        if self.cancel.is_set() and not result["committed"]:
            result.update(indexSnapshot=None, mapSnapshot=None, provenance=None,
                          cancelled=True, opaqueerror=None)
        self.mapping_state_done.emit(result)
