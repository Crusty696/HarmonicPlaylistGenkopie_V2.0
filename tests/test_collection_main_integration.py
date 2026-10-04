"""Native Sammlungsanschluesse bleiben nach View-Austausch funktionsfaehig."""
from types import SimpleNamespace

import pytest
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QDialog

import main


class _Settings:
    def value(self, key, default=None):
        return default

    def setValue(self, key, value):
        pass

    def sync(self):
        pass

    def status(self):
        from PyQt6.QtCore import QSettings
        return QSettings.Status.NoError


@pytest.fixture
def window(qtbot, monkeypatch):
    monkeypatch.setattr(main.MainWindow, "check_dependencies_and_warn", lambda self: None)
    widget = main.MainWindow(settings=_Settings())
    qtbot.addWidget(widget)
    return widget


def test_quality_collection_button_opens_exactly_one_native_dialog(window, monkeypatch):
    from hpg_core import collection_panel
    calls = []

    class Dialog(QDialog):
        worker = None

        def __init__(self, parent=None):
            super().__init__(parent)
            calls.append(parent)

        def exec(self):
            return 0

    monkeypatch.setattr(collection_panel, "CollectionDialog", Dialog)
    before = (window.playlist, window.current_generation_result, window.worker)
    window.analytics_panel.collection_button.click()
    assert calls == [window]
    assert window._collection_dialog is None
    assert (window.playlist, window.current_generation_result, window.worker) == before
    assert "keine Audioanalyse" in window.analytics_panel.collection_button.toolTip()


def test_reentry_raises_existing_dialog_without_second_instance(window):
    calls = []
    window._collection_dialog = SimpleNamespace(
        raise_=lambda: calls.append("raise"), activateWindow=lambda: calls.append("activate"), worker=None,
    )
    window._open_collection_dialog()
    assert calls == ["raise", "activate"]
    window._collection_dialog = None


def test_parent_close_requests_cancel_without_early_accept(window):
    calls = []
    worker = SimpleNamespace(isRunning=lambda: True, wait=lambda ms: False,
                             request_cancel=lambda: calls.append("cancel"))
    window._collection_dialog = SimpleNamespace(worker=worker, reject=lambda: calls.append("reject"))
    assert worker in window._managed_workers_for_close()
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted()
    assert "cancel" in calls
    assert "reject" in calls
    window._collection_dialog = None
    window._close_pending = False


def _unexpected_dialog(monkeypatch, *, raises=False):
    from threading import Event
    from hpg_core import collection_panel
    from hpg_core.collection_jobs import CollectionIndexWorker
    stop = Event()
    instances = []

    class Worker(CollectionIndexWorker):
        def run(self):
            stop.wait(10)
            self.scan_done.emit(None)

    class Dialog(collection_panel.CollectionDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            instances.append(self)

        def exec(self):
            if len(instances) == 1:
                self._launch_worker(Worker(), "Kontrollierter laufender Worker")
                if raises:
                    raise RuntimeError("controlled unexpected modal end")
            return 0

    monkeypatch.setattr(collection_panel, "CollectionDialog", Dialog)
    return stop, instances


@pytest.mark.parametrize("raises", [False, True])
def test_unexpected_modal_end_releases_reference_after_real_worker_end(window, qtbot, monkeypatch, raises):
    stop, instances = _unexpected_dialog(monkeypatch, raises=raises)
    try:
        if raises:
            with pytest.raises(RuntimeError, match="unexpected modal end"):
                window._open_collection_dialog()
        else:
            window._open_collection_dialog()
        assert window._collection_dialog is instances[0]
        assert instances[0].worker is not None
        stop.set()
        qtbot.waitUntil(lambda: window._collection_dialog is None)
        window._open_collection_dialog()
        assert len(instances) == 2
        assert window._collection_dialog is None
    finally:
        stop.set()
        qtbot.waitUntil(lambda: instances[0].worker is None)


def test_parent_close_retry_accepts_only_after_real_worker_cleanup(window, qtbot, monkeypatch):
    stop, instances = _unexpected_dialog(monkeypatch)
    callbacks, accepted = [], []
    monkeypatch.setattr(main.QTimer, "singleShot", lambda ms, callback: callbacks.append(callback))

    def retry_close():
        event = QCloseEvent()
        window.closeEvent(event)
        accepted.append(event.isAccepted())

    monkeypatch.setattr(window, "close", retry_close)
    try:
        window._open_collection_dialog()
        first = QCloseEvent()
        window.closeEvent(first)
        assert not first.isAccepted()
        assert window._collection_dialog is instances[0]
        assert instances[0].worker.cancel.is_set()
        assert callbacks
        stop.set()
        qtbot.waitUntil(lambda: window._collection_dialog is None)
        callbacks[-1]()
        assert accepted == [True]
        assert instances[0].worker is None
    finally:
        stop.set()
        qtbot.waitUntil(lambda: instances[0].worker is None)


def test_prepared_quality_panel_has_live_hearing_and_collection_signals(window, monkeypatch):
    seen = []
    monkeypatch.setattr(window, "_open_collection_dialog", lambda: seen.append("collection"))
    monkeypatch.setattr(window, "_open_hearing_set", lambda: seen.append("hearing"))
    prepared = window._prepare_uebergangs_views([], {}, [], 2.0, None)
    try:
        panel = prepared[3]
        panel.collection_button.click()
        panel.hearing_open_button.click()
        assert seen == ["collection", "hearing"]
    finally:
        for widget in prepared:
            widget.deleteLater()


def test_existing_hearing_open_survives_quality_panel_replacement(window, monkeypatch):
    seen = []
    monkeypatch.setattr(window, "_open_hearing_set", lambda: seen.append("hearing"))
    prepared = window._prepare_uebergangs_views([], {}, [], 2.0, None)
    window._commit_uebergangs_views(prepared, [], {}, None)
    window.analytics_panel.hearing_open_button.click()
    assert seen == ["hearing"]


def test_loaded_hearing_session_controls_survive_view_publication(window, tmp_path):
    window._hearing_set_path = str(tmp_path)
    window._update_hearing_buttons()
    assert window.analytics_panel.hearing_rating_button.isEnabled()
    old_status = "Vorhandener Satz: nicht erneut erstellen."
    window.analytics_panel.hearing_status.setText(old_status)
    prepared = window._prepare_uebergangs_views([], {}, [], 2.0, None)
    window._commit_uebergangs_views(prepared, [], {}, None)
    assert window.analytics_panel.hearing_rating_button.isEnabled()
    assert window.analytics_panel.hearing_status.text() == old_status


def test_failed_publication_keeps_previous_hearing_connection(window, monkeypatch):
    seen = []
    original = window.analytics_panel
    monkeypatch.setattr(window, "_open_hearing_set", lambda: seen.append("old"))
    # Anfangsanschluss neu herstellen, ohne vorherige Verbindung zu verdoppeln.
    original.hearing_open_requested.disconnect()
    original.hearing_open_requested.connect(window._open_hearing_set)
    prepared = window._prepare_uebergangs_views([], {}, [], 2.0, None)
    replace = window._right_layout.replaceWidget

    def fail(old, new):
        if new is prepared[4]:
            raise RuntimeError("controlled publication failure")
        return replace(old, new)

    monkeypatch.setattr(window._right_layout, "replaceWidget", fail)
    with pytest.raises(RuntimeError, match="controlled publication"):
        window._commit_uebergangs_views(prepared, [], {}, None)
    assert window.analytics_panel is original
    original.hearing_open_button.click()
    assert seen == ["old"]


def test_measurement_signal_survives_quality_publication(window, monkeypatch):
    calls = []
    monkeypatch.setattr(window, "_open_measurement_dialog", lambda: calls.append("diagnosis"), raising=False)
    prepared = window._prepare_uebergangs_views([], {}, [], 2.0, None)
    window._commit_uebergangs_views(prepared, [], {}, None)
    window.analytics_panel.measurement_button.click()
    assert calls == ["diagnosis"]


@pytest.mark.parametrize("has_analysis", [False, True])
def test_measurement_dialog_uses_analysis_snapshot_never_playlist_fallback(window, monkeypatch, has_analysis):
    from hpg_core.measurement_panel import MeasurementDialog
    from hpg_core.models import Track
    analyzed = Track(fileName="Neue Analyse", filePath="Z:/not opened/new.aiff")
    window.analyzed_raw_tracks = [analyzed] if has_analysis else []
    window.playlist = [Track(fileName="Alte Playlist", filePath="Z:/not opened/old.aiff")]
    rows = []

    def inspect(dialog):
        model = dialog.track_table.model()
        rows.append((model.rowCount(), model.index(0, 0).data() if model.rowCount() else None))
        return 0

    monkeypatch.setattr(MeasurementDialog, "exec", inspect)
    window.analytics_panel.measurement_button.click()
    assert rows == [(1, "Neue Analyse")] if has_analysis else rows == [(0, None)]
    assert analyzed.measurement_diagnostics == {}
