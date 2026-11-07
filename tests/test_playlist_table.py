"""Drop in die Leerflaeche und Abbruch duerfen keine Trackzellen leeren."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QTableWidgetItem, QTableWidgetSelectionRange

from hpg_core.ui import playlist_table

pytestmark = pytest.mark.gui


def _table(qtbot):
    table = playlist_table.PlaylistTable(2, 2)
    qtbot.addWidget(table)
    table.setDragDropMode(table.DragDropMode.InternalMove)
    table.setSelectionBehavior(table.SelectionBehavior.SelectRows)
    for row, title in enumerate(("W", "Deep Sky")):
        for column in range(2):
            table.setItem(row, column, QTableWidgetItem(f"{title}:{column}"))
    table.resize(400, 300)
    table.show()
    table.selectRow(0)
    return table


@pytest.mark.parametrize("action", ["drop", "cancel", "foreign", "same_row"])
def test_native_drag_lifecycle_keeps_complete_rows(qtbot, monkeypatch, action):
    table = _table(qtbot)
    rows_moved = Mock()
    table.model().rowsMoved.connect(rows_moved)
    event = SimpleNamespace(source=lambda: object() if action == "foreign" else table,
        position=lambda: QPointF(15, 5 if action == "same_row" else 200),
        accept=Mock(), ignore=Mock(), setDropAction=Mock())
    drag = Mock()

    def execute(_actions):
        if action != "cancel":
            table.dropEvent(event)
        return Qt.DropAction.MoveAction if action == "drop" else Qt.DropAction.IgnoreAction

    drag.exec.side_effect = execute
    monkeypatch.setattr(playlist_table, "QDrag", lambda source: drag)
    table.startDrag(Qt.DropAction.MoveAction)

    expected = ("Deep Sky", "W") if action == "drop" else ("W", "Deep Sky")
    assert [[table.item(row, column).text() for column in range(2)]
            for row in range(2)] == [[f"{title}:0", f"{title}:1"] for title in expected]
    assert rows_moved.call_count == (1 if action == "drop" else 0)
    assert not table._drag_rows
    if action == "drop":
        event.accept.assert_called_once()


def test_native_drop_uses_panel_snapshot_before_rejected_reorder(qtbot, monkeypatch):
    import main
    from hpg_core.models import Track

    panel = main.PlaylistPanel()
    qtbot.addWidget(panel)
    panel.set_playlist_data([
        Track(filePath="C:/w.wav", fileName="W", bpm=127.0),
        Track(filePath="C:/deep.wav", fileName="Deep Sky", bpm=125.0),
    ], {})
    table = panel.table
    table.resize(400, 300)
    table.selectRow(0)
    drag = Mock()
    event = SimpleNamespace(source=lambda: table, position=lambda: QPointF(15, 200),
        accept=Mock(), ignore=Mock(), setDropAction=Mock())
    drag.exec.side_effect = lambda _actions: table.dropEvent(event)
    monkeypatch.setattr(playlist_table, "QDrag", lambda source: drag)
    monkeypatch.setattr(main, "calculate_playlist_quality",
                        Mock(side_effect=RuntimeError("Replanung abgelehnt")))
    table.startDrag(Qt.DropAction.MoveAction)

    assert panel.table is not table
    assert isinstance(panel.table, playlist_table.PlaylistTable)
    assert [panel.table.item(row, 1).text() for row in range(2)] == ["W", "Deep Sky"]
    assert [track.fileName for track in panel.playlist] == ["W", "Deep Sky"]


@pytest.mark.parametrize("rows", [(0, 1), (0, 2)])
def test_drag_contiguous_selection_moves_as_block_other_selection_stays(qtbot, monkeypatch, rows):
    table = _table(qtbot)
    table.setRowCount(4)
    for row in range(4):
        for column in range(2):
            table.setItem(row, column, QTableWidgetItem(f"{row}:{column}"))
    table.clearSelection()
    for row in rows:
        table.setRangeSelected(QTableWidgetSelectionRange(row, 0, row, 1), True)
    event = SimpleNamespace(source=lambda: table, position=lambda: QPointF(15, 200),
        accept=Mock(), ignore=Mock(), setDropAction=Mock())
    drag = Mock()
    drag.exec.side_effect = lambda _actions: table.dropEvent(event)
    monkeypatch.setattr(playlist_table, "QDrag", lambda source: drag)

    table.startDrag(Qt.DropAction.MoveAction)

    expected = (2, 3, 0, 1) if rows == (0, 1) else (0, 1, 2, 3)
    assert [[table.item(row, column).text() for column in range(2)]
            for row in range(4)] == [[f"{value}:0", f"{value}:1"] for value in expected]
    assert drag.exec.call_count == (1 if rows == (0, 1) else 0)
