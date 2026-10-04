"""Inventardialog ohne Audioanalyse; Rekordbox nur im geschuetzten Worker lesen."""

import os

from PyQt6 import sip
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView, QDialog, QFileDialog, QHBoxLayout, QLabel,
    QListWidget, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from . import caching
from .collection_jobs import (
    CollectionIndexWorker, CollectionRekordboxWorker, CollectionMappingStateWorker,
    cancel_worker, mapping_index_binding,
)


_STATUS_LABELS = {"new": "Neu", "unchanged": "Unverändert",
                  "changed": "Geändert", "missing": "Fehlend"}


class CollectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.index = None
        self.mapping = None
        self.mapping_provenance = None
        self.mapping_observed_at_ns = None
        self._mapping_binding = None
        self._mapping_version = 0
        self._updating_roots = False
        self._pending_exit = None
        self.setWindowTitle("Sammlungsinventar")
        self.resize(900, 600)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Musikordner – Inventar prüft nur Pfad, Größe und Änderungszeit. Keine Audioanalyse."))
        self.roots_list = QListWidget()
        self.roots_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.roots_list)
        controls = QHBoxLayout()
        self.add_button = QPushButton("Ordner hinzufügen")
        self.remove_button = QPushButton("Auswahl entfernen")
        self.start_button = QPushButton("Inventar prüfen")
        self.load_button = QPushButton("Letztes Inventar laden")
        self.mapping_button = QPushButton("Rekordbox zuordnen")
        self.mapping_button.setEnabled(False)
        self.mapping_button.setToolTip(
            "Konfigurierte Rekordbox-Quelle geschützt lesen und dem Inventar zuordnen. "
            "Keine Audioanalyse und keine Änderung an Musik oder Rekordbox."
        )
        self.save_mapping_button = QPushButton("Zuordnung speichern")
        self.load_mapping_button = QPushButton("Gespeicherte Zuordnung laden")
        self.save_mapping_button.setEnabled(False)
        self.load_mapping_button.setEnabled(False)
        self.cancel_button = QPushButton("Abbrechen")
        self.cancel_button.setEnabled(False)
        for button in (self.add_button, self.remove_button, self.load_button, self.start_button,
                       self.mapping_button, self.save_mapping_button, self.load_mapping_button, self.cancel_button):
            controls.addWidget(button)
        layout.addLayout(controls)
        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels([
            "Dateipfad", "Größe (Bytes)", "Änderungszeit (ns)", "Inventarstatus",
            "Rekordbox-Zuordnung", "BPM vorhanden", "Key vorhanden", "Beatgrid-Punkte",
            "Phrasen", "Quellsignatur", "Detailstatus",
        ])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setColumnWidth(0, 500)
        layout.addWidget(self.table)
        self.status_label = QLabel("Inventar noch nicht geprüft. Keine Aussage über Analysequalität.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.mapping_label = QLabel("Rekordbox-Zuordnung nicht geprüft. Keine Audioanalyse.")
        self.mapping_label.setWordWrap(True)
        layout.addWidget(self.mapping_label)
        close_button = QPushButton("Schließen")
        close_button.clicked.connect(self.reject)
        layout.addWidget(close_button)
        self.add_button.clicked.connect(self._add_root)
        self.remove_button.clicked.connect(self._remove_roots)
        self.start_button.clicked.connect(self._start_scan)
        self.load_button.clicked.connect(self._load_saved)
        self.mapping_button.clicked.connect(self._start_mapping)
        self.save_mapping_button.clicked.connect(self._save_mapping)
        self.load_mapping_button.clicked.connect(self._load_mapping)
        self.cancel_button.clicked.connect(self._cancel_scan)
        model = self.roots_list.model()
        for signal in (model.rowsInserted, model.rowsRemoved, model.rowsMoved, model.dataChanged, model.modelReset):
            signal.connect(self._on_roots_changed)

    def _add_root(self):
        if self.worker is not None:
            return
        selected = QFileDialog.getExistingDirectory(self, "Musikordner hinzufügen")
        if not selected:
            return
        root = os.path.abspath(os.path.normpath(selected))
        existing = {os.path.normcase(self.roots_list.item(i).text())
                    for i in range(self.roots_list.count())}
        if os.path.normcase(root) not in existing:
            self.roots_list.addItem(root)
            self._invalidate_mapping()

    def _remove_roots(self):
        if self.worker is not None:
            return
        for item in self.roots_list.selectedItems():
            self.roots_list.takeItem(self.roots_list.row(item))
        self._invalidate_mapping()

    def _mapping_ready(self):
        roots = {os.path.normcase(self.roots_list.item(i).text()) for i in range(self.roots_list.count())}
        return bool(self.index is not None and not self.index.errors and not self.index.cancelled
                    and roots == {os.path.normcase(root) for root in self.index.roots})

    def _current_mapping_binding(self):
        if not self._mapping_ready():
            return None
        return mapping_index_binding(self.index, caching.CACHE_VERSION)

    def _map_matches_index(self, mapping):
        return bool(self._mapping_ready() and mapping is not None
                    and mapping.cache_version == caching.CACHE_VERSION
                    and tuple(mapping.roots) == tuple(self.index.roots)
                    and tuple((row.path, row.inventory_size, row.inventory_mtime_ns, tuple(row.source_roots))
                              for row in mapping.rows) ==
                    tuple((entry.path, entry.size, entry.mtime_ns,
                           tuple(root for root in self.index.roots if self._contains(root, entry.path)))
                          for entry in self.index.entries))

    @staticmethod
    def _contains(root, path):
        try:
            return os.path.commonpath((os.path.normcase(root), os.path.normcase(path))) == os.path.normcase(root)
        except ValueError:
            return False

    def _fresh_mapping_ready(self):
        return bool(self.mapping_provenance == "observed_in_session"
                    and self.mapping is not None and self.mapping.valid
                    and not self.mapping.cancelled and not self.mapping.errors
                    and type(self.mapping_observed_at_ns) is int and self.mapping_observed_at_ns >= 0
                    and self._mapping_binding == self._current_mapping_binding()
                    and self._map_matches_index(self.mapping))

    def _mapping_value_binding(self):
        # Listen in manuell konstruierten Dataclasses nur als RAM-Werte binden.
        mapping = self.mapping
        if mapping is None:
            return None
        return (tuple(mapping.roots), mapping.cache_version, mapping.source_db_path,
                mapping.valid, mapping.cancelled, tuple(mapping.errors),
                tuple((row.path, tuple(row.source_roots), row.inventory_size, row.inventory_mtime_ns,
                       row.match_status, row.bpm_present, row.key_present, row.beatgrid_count,
                       row.phrases_count, row.source_signature, tuple(row.errors)) for row in mapping.rows))

    def _on_roots_changed(self, *_):
        if not self._updating_roots:
            self._invalidate_mapping()

    def _invalidate_mapping(self):
        self._mapping_version += 1
        self.mapping = None
        self.mapping_provenance = None
        self.mapping_observed_at_ns = None
        self._mapping_binding = None
        if getattr(self.worker, "mode", None) in ("mapping", "mapping_save", "mapping_load"):
            cancel_worker(self.worker)
        self.mapping_label.setText("Rekordbox-Zuordnung nicht geprüft. Vorheriger Stand nicht aktuell bestätigt.")
        for row in range(self.table.rowCount()):
            for column in range(4, self.table.columnCount()):
                self.table.setItem(row, column, QTableWidgetItem(""))
        self.mapping_button.setEnabled(self.worker is None and self._mapping_ready())
        self.save_mapping_button.setEnabled(False)
        self.load_mapping_button.setEnabled(self.worker is None and self._mapping_ready())

    def _set_busy(self, busy):
        for button in (self.add_button, self.remove_button, self.load_button, self.start_button):
            button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.mapping_button.setEnabled(not busy and self._mapping_ready())
        self.save_mapping_button.setEnabled(not busy and self._fresh_mapping_ready())
        self.load_mapping_button.setEnabled(not busy and self._mapping_ready())

    def _start_scan(self):
        if self.worker is not None:
            return
        roots = [self.roots_list.item(i).text() for i in range(self.roots_list.count())]
        if not roots:
            self.status_label.setText("Bitte mindestens einen Musikordner hinzufügen.")
            return
        self._invalidate_mapping()
        worker = CollectionIndexWorker(roots, previous=self.index)
        self._launch_worker(worker, "Inventar wird geprüft …")

    def _load_saved(self):
        if self.worker is not None:
            return
        self._invalidate_mapping()
        worker = CollectionIndexWorker(previous=self.index, mode="load")
        self._launch_worker(worker, "Gespeichertes Inventar wird geladen …")

    def _start_mapping(self):
        if self.worker is not None or not self._mapping_ready():
            return
        self._invalidate_mapping()
        worker = CollectionRekordboxWorker(self.index)
        self._launch_worker(worker, "Rekordbox-Zuordnung wird geprüft …")

    def _save_mapping(self):
        if self.worker is not None:
            return
        if not self._fresh_mapping_ready():
            self.mapping_label.setText("Keine gültige neue RAM-Zuordnung zum aktuellen Inventar vorhanden.")
            return
        worker = CollectionMappingStateWorker(
            self.index, action="save", mapping=self.mapping,
            observed_at_ns=self.mapping_observed_at_ns, expected_cache_version=caching.CACHE_VERSION)
        self._launch_worker(worker, "Zuordnung wird gespeichert …")

    def _load_mapping(self):
        if self.worker is not None:
            return
        if not self._mapping_ready():
            self.mapping_label.setText("Bitte zuerst ein passendes Inventar laden oder prüfen. Keine Ersatzquelle.")
            return
        self._invalidate_mapping()
        worker = CollectionMappingStateWorker(self.index, action="load", expected_cache_version=caching.CACHE_VERSION)
        self._launch_worker(worker, "Gespeicherte Zuordnung wird geladen …")

    def _launch_worker(self, worker, message):
        self._pending_exit = None
        self.worker = worker
        worker.panel_binding = self._current_mapping_binding()
        worker.panel_index = self.index
        worker.panel_mapping_version = self._mapping_version
        worker.panel_mapping_identity = self.mapping
        worker.panel_mapping_values = self._mapping_value_binding()
        worker.progress_update.connect(
            lambda count, path, w=worker: self._on_progress(count, path, source_worker=w),
            Qt.ConnectionType.QueuedConnection,
        )
        if getattr(worker, "mode", None) in ("mapping_save", "mapping_load"):
            signal, handler = worker.mapping_state_done, self._on_mapping_state_done
        elif getattr(worker, "mode", None) == "mapping":
            signal, handler = worker.mapping_done, self._on_mapping_done
        else:
            signal, handler = worker.scan_done, self._on_scan_done
        signal.connect(
            lambda result, w=worker, handle=handler: handle(result, source_worker=w),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.finished.connect(
            lambda w=worker: self._cleanup_worker(source_worker=w),
            Qt.ConnectionType.QueuedConnection,
        )
        # Das Registry haelt Worker auch nach erzwungener Parent-Loeschung.
        self.destroyed.connect(lambda _obj=None, w=worker: cancel_worker(w))
        self.status_label.setText(message)
        self._set_busy(True)
        worker.start()

    def _cancel_scan(self):
        if self.worker is not None:
            cancel_worker(self.worker)
            self.status_label.setText("Inventar-Abbruch angefordert …")
            self.cancel_button.setEnabled(False)

    def _on_progress(self, count, path, source_worker=None):
        if (sip.isdeleted(self) or source_worker is None or source_worker is not self.worker
                or self._pending_exit is not None):
            return
        if not source_worker.cancel.is_set():
            phase = "Rekordbox-Zuordnung" if getattr(source_worker, "mode", None) == "mapping" else "Inventar"
            self.status_label.setText(f"{phase}: {count} Dateien geprüft – {path}")

    def _on_mapping_done(self, result, source_worker=None):
        if (sip.isdeleted(self) or source_worker is None or source_worker is not self.worker
                or source_worker.index is not self.index or self._pending_exit is not None
                or getattr(source_worker, "panel_binding", self._current_mapping_binding()) != self._current_mapping_binding()
                or getattr(source_worker, "panel_mapping_version", self._mapping_version) != self._mapping_version):
            return
        if result is None or not result.valid or result.cancelled or result.errors or source_worker.cancel.is_set():
            self._invalidate_mapping()
            self.mapping_label.setText("Rekordbox-Zuordnung abgebrochen oder nicht verfügbar. Keine Teilzuordnung bestätigt.")
            return
        if not self._map_matches_index(result):
            self._invalidate_mapping()
            self.mapping_label.setText("Rekordbox-Ergebnis passt nicht zum Inventar; nicht übernommen.")
            return
        self._render_mapping(result, provenance="observed_in_session",
                             observed_at_ns=getattr(source_worker, "observed_at_ns", None))

    def _render_mapping(self, result, *, provenance, observed_at_ns):
        self._mapping_version += 1
        self.mapping = result
        self.mapping_provenance = provenance
        self.mapping_observed_at_ns = observed_at_ns
        self._mapping_binding = self._current_mapping_binding()
        saved = provenance == "saved_not_fresh"
        self.table.setRowCount(len(self.index.entries))
        counts = dict.fromkeys(("exact", "basename", "ambiguous", "missing", "unavailable"), 0)
        labels = {"exact": "Exact", "basename": "Nur Dateiname", "ambiguous": "Mehrdeutig",
                  "missing": "Fehlend", "unavailable": "Nicht verfügbar"}
        def display(value):
            if value is None:
                return "unbekannt / unverifiziert"
            if type(value) is bool:
                return "Ja" if value else "Nein"
            return str(value)
        for row_number, (entry, row) in enumerate(zip(self.index.entries, result.rows)):
            counts[row.match_status] += 1
            values = (entry.path, str(entry.size), str(entry.mtime_ns), _STATUS_LABELS[entry.status],
                      labels[row.match_status], display(row.bpm_present), display(row.key_present),
                      display(row.beatgrid_count), display(row.phrases_count), display(row.source_signature),
                      "Gespeichert – nicht frisch geprüft" if saved else
                      "Details unverifiziert" if row.errors else "Gelesener Zuordnungsstand")
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if saved and column >= 4:
                    item.setToolTip("Gespeicherte Angabe – nicht frisch geprüft; keine aktuelle Quellenbestätigung.")
                self.table.setItem(row_number, column, item)
        summary = ", ".join(f"{labels[key]}: {count}" for key, count in counts.items())
        self.mapping_label.setText(
            f"{summary}. Quelle: {result.source_db_path or 'nicht belegt'}. "
            + (f"Gespeicherte Zuordnung – nicht frisch geprüft. Beobachtungszeit (ns): {observed_at_ns}. "
               if saved else "Nur aktueller RAM-Stand, nicht gespeichert. ")
            + "Kein gemeinsamer DB-/ANLZ-Snapshot; keine Audioanalyse."
        )

    def _on_mapping_state_done(self, result, source_worker=None):
        if (sip.isdeleted(self) or source_worker is None or source_worker is not self.worker
                or self._pending_exit is not None
                or source_worker.panel_index is not self.index
                or source_worker.panel_binding != self._current_mapping_binding()
                or source_worker.panel_mapping_version != self._mapping_version
                or source_worker.panel_mapping_identity is not self.mapping
                or source_worker.panel_mapping_values != self._mapping_value_binding()):
            return
        if result["action"] == "save" and result["committed"]:
            # Auch später Cancel macht den bereits erfolgten Commit nicht rückgängig.
            self.mapping_label.setText("Beobachtungsstand gespeichert; Quellen nicht erneut geprüft.")
            return
        if result["cancelled"] or source_worker.cancel.is_set():
            self._invalidate_mapping()
            self.mapping_label.setText("Zuordnungs-Persistenz abgebrochen. Keine neue Bestätigung.")
            return
        if result["opaqueerror"] is not None:
            self.mapping_label.setText("Zuordnung nicht gespeichert." if result["action"] == "save" else
                                       "Gespeicherte Zuordnung nicht geladen. Format oder Bindung nicht verifiziert.")
            return
        if result["action"] == "load":
            if result["mapSnapshot"] is None:
                self.mapping_label.setText("Keine gespeicherte Zuordnung vorhanden.")
            elif (result["provenance"] == "saved_not_fresh"
                  and result["indexSnapshot"] == self.index
                  and self._map_matches_index(result["mapSnapshot"])):
                self._render_mapping(result["mapSnapshot"], provenance="saved_not_fresh",
                                     observed_at_ns=source_worker.observed_at_ns)
            else:
                self.mapping_label.setText("Gespeicherte Zuordnung passt nicht zum Inventar; nicht übernommen.")

    def _on_scan_done(self, result, source_worker=None):
        if (sip.isdeleted(self) or source_worker is None or source_worker is not self.worker
                or self._pending_exit is not None):
            return
        loaded = getattr(source_worker, "mode", "scan") == "load"
        if result is None:
            self.status_label.setText("Kein gespeichertes Inventar vorhanden. Musikordner hinzufügen und Inventar prüfen.")
            return
        if result.cancelled:
            self.status_label.setText("Inventar abgebrochen. Vorherige Einträge erhalten.")
            return
        if result.errors:
            self.status_label.setText("Inventar nicht aktualisiert; vorherige Einträge erhalten. " + " | ".join(result.errors))
            return
        self.index = result
        if loaded:
            self._updating_roots = True
            try:
                self.roots_list.clear()
                self.roots_list.addItems(list(result.roots))
            finally:
                self._updating_roots = False
        self.table.setRowCount(len(result.entries))
        counts = dict.fromkeys(_STATUS_LABELS, 0)
        for row, entry in enumerate(result.entries):
            counts[entry.status] += 1
            values = (entry.path, str(entry.size), str(entry.mtime_ns), _STATUS_LABELS[entry.status])
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        summary = ", ".join(f"{_STATUS_LABELS[status]}: {count}" for status, count in counts.items())
        prefix = "Gespeichertes Inventar – nicht frisch geprüft" if loaded else "Inventar"
        self.status_label.setText(f"{prefix}: {len(result.entries)} Einträge. {summary}. Keine Audioanalyse.")

    def _cleanup_worker(self, source_worker=None):
        if sip.isdeleted(self) or source_worker is None or source_worker is not self.worker:
            return
        if not sip.isdeleted(source_worker):
            if source_worker.isRunning() or not source_worker.wait(2000):
                return
            source_worker.deleteLater()
        self.worker = None
        if self._pending_exit is not None:
            result = self._pending_exit
            self._pending_exit = None
            super().done(result)
        else:
            self._set_busy(False)

    def done(self, result):
        if self.worker is not None:
            if self._pending_exit is None:
                self._pending_exit = int(result)
            self._cancel_scan()
            return
        super().done(result)

    def accept(self):
        self.done(int(QDialog.DialogCode.Accepted))

    def reject(self):
        self.done(int(QDialog.DialogCode.Rejected))

    def closeEvent(self, event):
        if self.worker is not None:
            self.done(int(QDialog.DialogCode.Rejected))
            event.ignore()
        else:
            super().closeEvent(event)
