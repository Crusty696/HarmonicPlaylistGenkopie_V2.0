"""Zeilen-DnD ohne den destruktiven Item-Move-Fallback von QTableWidget."""
from PyQt6.QtCore import QModelIndex, Qt
from PyQt6.QtGui import QDrag
from PyQt6.QtWidgets import QTableWidget


class PlaylistTable(QTableWidget):
    """Verschiebt nur ganze Zeilen durch den bestehenden Modellvertrag."""

    def deleteLater(self):
        # Der Snapshot-Rollback ersetzt die Tabelle noch innerhalb des Drops.
        # Die Drag-Quelle muss bis zur Rueckkehr aus QDrag.exec weiterleben.
        if getattr(self, "_drag_rows", ()):
            self._delete_after_drag = True
        else:
            super().deleteLater()

    def startDrag(self, supported_actions):
        rows = sorted(index.row() for index in self.selectionModel().selectedRows())
        if (self.dragDropMode() != self.DragDropMode.InternalMove or not rows
                or rows != list(range(rows[0], rows[-1] + 1))):
            return
        self._drag_rows = tuple(rows)
        drag = QDrag(self)
        drag.setMimeData(self.model().mimeData(self.selectedIndexes()))
        try:
            # Kein QAbstractItemView.startDrag: dessen Cleanup kann Items nach
            # einem Drop leeren, obwohl das Result noch unveraendert ist.
            drag.exec(Qt.DropAction.MoveAction)
        finally:
            self._drag_rows = ()
            drag.deleteLater()
            if getattr(self, "_delete_after_drag", False):
                super().deleteLater()

    def _internal_drag(self, event):
        return (event.source() is self
                and self.dragDropMode() == self.DragDropMode.InternalMove
                and bool(getattr(self, "_drag_rows", ())))

    def dragEnterEvent(self, event):
        if self._internal_drag(event):
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._internal_drag(event):
            super().dragMoveEvent(event)
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not self._internal_drag(event):
            event.ignore()
            return
        rows = self._drag_rows
        position = event.position().toPoint()
        index = self.indexAt(position)
        destination = self.rowCount()
        if index.isValid():
            destination = index.row()
            if position.y() > self.visualRect(index).center().y():
                destination += 1
        if rows[0] <= destination <= rows[-1] + 1:
            event.ignore()
            return
        # Snapshot, Permutationspruefung und Replanung bleiben an den
        # rowsAboutToBeMoved/rowsMoved-Signalen des vorhandenen Modells.
        moved = self.model().moveRows(
            QModelIndex(), rows[0], len(rows), QModelIndex(), destination,
        )
        if moved:
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        else:
            event.ignore()
