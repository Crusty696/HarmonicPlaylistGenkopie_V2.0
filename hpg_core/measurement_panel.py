"""Schreibgeschützte Diagnoseansicht ausschließlich aus RAM-Snapshots."""
from copy import deepcopy
from dataclasses import dataclass

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView, QDialog, QLabel, QPushButton, QTableView,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from .measurement_contract import validate_measurement_diagnostics


_CODES = {
    "unknown": "Unbekannt", "reference_verified": "Referenz bestätigt",
    "invalidinput": "Ungültige Eingabe", "inputshort": "Eingabe zu kurz",
    "fewbeats": "Zu wenige Beats", "incommensurate": "Beatabstände nicht vereinbar",
    "noactivity": "Keine messbare Aktivität", "weakfold": "Schwache Faltungsbindung",
    "voteweak": "Schwache Taktabstimmung", "estimationerror": "Schätzung fehlgeschlagen",
    "ok": "Schätzung abgeschlossen", "nowindows": "Keine Messfenster",
    "duplicategrid": "Doppelte Gitterpunkte", "variablegrid": "Veränderliche Gitterabstände",
    "tempomismatch": "Tempoabweichung", "missingreference": "Referenz fehlt",
    "fewwindows": "Zu wenige geprüfte Fenster", "verified": "Verifiziert",
    "phasemismatch": "Phasenabweichung", "measured": "Gemessen",
    "unverifiable": "Nicht verifizierbar", "unsupported": "Nicht unterstützt",
    "mismatch": "Abweichung", "decode_error": "Fenster nicht dekodiert",
    "input": "Eingabeprüfung", "beat_tracking": "Beat-Erkennung",
    "features": "Merkmalberechnung", "trim": "Beschneiden der Beatfolge",
    "voting": "Taktabstimmung", "fold": "Phasenfaltung",
    "result": "Ergebnis", "reference": "Referenzprüfung",
}
_UNKNOWN = "Unbekannt – möglicherweise alte Analyse"
_INVALID = "Unverifiziert – ungültige Diagnose"
_HEADERS = ("Track", "Dateipfad (nur RAM)", "Gridstatus", "Geprüfte Fenster", "Max. Phasenfehler (ms)")


def _number(value):
    # Null ist eine Messung; None und der -1-Sentinel sind keine Messung.
    return "Nicht gemessen" if value is None or value == -1 else f"{value:.3f}"


def _code(value):
    return _CODES.get(value, "Unbekannt")


@dataclass(frozen=True)
class _Snapshot:
    name: str
    path: str
    diagnostic: dict | None


def _snapshot(track):
    # Keine Trackreferenz behalten und keine Quelle nachladen.
    name = deepcopy(getattr(track, "fileName", ""))
    path = deepcopy(getattr(track, "filePath", ""))
    try:
        diagnostic = deepcopy(getattr(track, "measurement_diagnostics", {}))
        validate_measurement_diagnostics(diagnostic)
    except Exception:
        # Fremde Payloads und Fehlermeldungen niemals anzeigen.
        diagnostic = None
    return _Snapshot(name if isinstance(name, str) else "",
                     path if isinstance(path, str) else "", diagnostic)


class _TrackModel(QAbstractTableModel):
    def __init__(self, snapshots, parent=None):
        super().__init__(parent)
        self._snapshots = snapshots

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._snapshots)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(_HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return _HEADERS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return None
        record = self._snapshots[index.row()]
        diag = record.diagnostic
        if index.column() < 2:
            return (record.name, record.path)[index.column()]
        if diag is None:
            return _INVALID if index.column() == 2 else "Nicht gemessen"
        if not diag:
            return _UNKNOWN if index.column() == 2 else "Nicht gemessen"
        grid = diag["grid"]
        if role == Qt.ItemDataRole.ToolTipRole:
            return (f"{_code(grid['status'])} ({grid['status']}); "
                    f"{_code(grid['reason'])} ({grid['reason']}). "
                    "Gespeicherte Messdiagnose, keine erneute Prüfung.")
        return (_code(grid["status"]), str(grid["windows_checked"]),
                _number(grid["max_phase_error_ms"]))[index.column() - 2]


class MeasurementDialog(QDialog):
    """Alle übergebenen Tracks anzeigen; Details nur für die aktuelle Auswahl."""
    def __init__(self, tracks, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Messdiagnosen")
        self.resize(1000, 650)
        self._snapshots = tuple(_snapshot(track) for track in tracks)
        layout = QVBoxLayout(self)
        self.status_label = QLabel(
            f"{len(self._snapshots)} Tracks – gespeicherte RAM-Diagnosen, nicht frisch geprüft."
            if self._snapshots else "Keine analysierten Tracks übergeben. Keine Messdiagnosen verfügbar.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.track_table = QTableView(self)
        self.track_table.setModel(_TrackModel(self._snapshots, self))
        self.track_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.track_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.track_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.track_table.setColumnWidth(0, 220)
        self.track_table.setColumnWidth(1, 280)
        self.track_table.setColumnWidth(2, 270)
        layout.addWidget(self.track_table)
        self.detail_label = QLabel("Keine Trackauswahl.")
        self.detail_label.setTextFormat(Qt.TextFormat.PlainText)
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.detail_label)
        self.window_table = QTableWidget(0, 6, self)
        self.window_table.setHorizontalHeaderLabels([
            "Offset (s)", "Dauer (s)", "Lokale Phase (s)", "Faltungsbindung (Fold-Lock)",
            "Phasenfehler (ms)", "Fenstergrund"])
        self.window_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.window_table)
        self.decode_label = QLabel("Keine Trackauswahl.")
        self.decode_label.setTextFormat(Qt.TextFormat.PlainText)
        self.decode_label.setWordWrap(True)
        layout.addWidget(self.decode_label)
        close = QPushButton("Schließen", self)
        close.clicked.connect(self.reject)
        layout.addWidget(close)
        self.track_table.selectionModel().selectionChanged.connect(self._show_selection)
        if self._snapshots:
            self.track_table.selectRow(0)

    def _show_selection(self, *_):
        self.window_table.setRowCount(0)
        selected = self.track_table.selectionModel().selectedRows()
        if not selected:
            self.detail_label.setText("Keine Trackauswahl.")
            self.decode_label.setText("Keine Trackauswahl.")
            return
        diag = self._snapshots[selected[0].row()].diagnostic
        if not diag:
            self.detail_label.setText(_INVALID if diag is None else _UNKNOWN)
            self.detail_label.setToolTip(self.detail_label.text())
            self.decode_label.setText("Dekodierdiagnose nicht verfügbar.")
            return
        downbeat, grid = diag["downbeat"], diag["grid"]
        self.detail_label.setText(
            f"Downbeat: {_code(downbeat['reason'])}; Schritt: {_code(downbeat['stage'])}. "
            f"Faltungsbindung: {_number(downbeat.get('fold_lock'))}; "
            f"lokale Phase: {_number(downbeat.get('phase_seconds'))} s. "
            f"Grid: {_code(grid['status'])}; {_code(grid['reason'])}; "
            f"maximaler Phasenfehler: {_number(grid['max_phase_error_ms'])} ms.")
        self.detail_label.setToolTip(
            f"Grund {downbeat['reason']}: {_code(downbeat['reason'])}; "
            f"Schritt {downbeat['stage']}: {_code(downbeat['stage'])}. "
            "Fold-Lock beschreibt die Faltungsbindung (0 bis 1), nicht die musikalische Qualität.")
        windows = grid["window_diagnostics"]
        self.window_table.setRowCount(len(windows))
        for row, window in enumerate(windows):
            values = [_number(window[key]) for key in (
                "offset_seconds", "duration_seconds", "phase_seconds", "fold_lock", "phase_error_ms")]
            values.append(_code(window["reason"]))
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setToolTip(f"{_code(window['reason'])} ({window['reason']}); "
                                "Phase ist fensterlokal. Nicht gemessen ist nicht Null.")
                self.window_table.setItem(row, column, item)
        failures = grid["decode_failures"]
        self.decode_label.setText(
            "Nicht dekodierte Fenster – Offsets: " + ", ".join(
                f"{_number(failure['offset_seconds'])} s" for failure in failures)
            if failures else "Keine gespeicherten Dekodierfehler.")
        self.decode_label.setToolTip("decode_error: Fenster konnte nicht dekodiert werden; keine Fehlertexte gespeichert.")
