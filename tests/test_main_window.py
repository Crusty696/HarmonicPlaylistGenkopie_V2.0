"""Regressionstests fuer den GUI-gesteuerten Hoertest-Ablauf."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QMessageBox

import main


class _MemorySettings:
    def value(self, _key, default=None):
        return default

    def setValue(self, _key, _value):
        pass

    def sync(self):
        pass

    def status(self):
        from PyQt6.QtCore import QSettings
        return QSettings.Status.NoError


def _window(qtbot, monkeypatch):
    monkeypatch.setattr(main.MainWindow, "check_dependencies_and_warn", lambda _self: None)
    window = main.MainWindow(settings=_MemorySettings())
    qtbot.addWidget(window)
    return window


def test_quality_panel_exposes_existing_hearing_workflow(qtbot):
    panel = main.AnalyticsPanel()
    qtbot.addWidget(panel)
    actions = []
    panel.hearing_prepare_requested.connect(lambda: actions.append("prepare"))
    panel.hearing_open_requested.connect(lambda: actions.append("open"))
    panel.hearing_prepare_button.click()
    panel.hearing_open_button.click()

    assert actions == ["prepare", "open"]
    assert panel.hearing_fit_button.isEnabled() is False
    assert panel.hearing_server_button.isEnabled() is False


def test_quality_panel_actions_reach_mainwindow_handlers(qtbot, monkeypatch):
    actions = []
    handlers = (
        "_open_collection_dialog",
        "_open_measurement_dialog",
        "_prepare_hearing_set",
        "_open_hearing_set",
        "_discover_hearing_sets",
        "_prepare_hearing_blind",
        "_check_hearing_blind",
        "_open_hearing_preview",
        "_open_hearing_rating",
        "_fit_hearing_set",
        "_fit_hearing_csv_set",
        "_cancel_hearing_work",
        "_start_hearing_server",
    )

    for handler in handlers:
        def capture(_self, *args, _handler=handler, **kwargs):
            actions.append((_handler, args, kwargs))

        monkeypatch.setattr(main.MainWindow, handler, capture)

    window = _window(qtbot, monkeypatch)
    panel = window.analytics_panel
    buttons = (
        ("collection_button", "_open_collection_dialog", {}),
        ("measurement_button", "_open_measurement_dialog", {}),
        ("hearing_prepare_button", "_prepare_hearing_set", {}),
        ("hearing_open_button", "_open_hearing_set", {}),
        ("hearing_discovery_button", "_discover_hearing_sets", {}),
        ("hearing_blind_button", "_prepare_hearing_blind", {}),
        ("hearing_blind_check_button", "_check_hearing_blind", {}),
        ("hearing_preview_button", "_open_hearing_preview", {}),
        ("hearing_rating_button", "_open_hearing_rating", {}),
        ("hearing_fit_button", "_fit_hearing_set", {}),
        ("hearing_csv_fit_button", "_fit_hearing_csv_set", {}),
        ("hearing_audit_button", "_fit_hearing_set", {"audit_only": True}),
        ("hearing_cancel_button", "_cancel_hearing_work", {}),
        ("hearing_server_button", "_start_hearing_server", {}),
    )

    for button_name, _handler, _kwargs in buttons:
        button = getattr(panel, button_name)
        button.setEnabled(True)
        button.click()

    assert actions == [
        (handler, (), kwargs) for _button, handler, kwargs in buttons
    ]


def test_portable_blind_selection_starts_native_export_worker(qtbot, monkeypatch, tmp_path):
    from hpg_core import hearing_jobs, hearing_panel

    window = _window(qtbot, monkeypatch)
    config = {
        "manifest": tmp_path / "manifest.csv",
        "output_dir": tmp_path / "session",
        "key_path": tmp_path / "private" / "key.csv",
        "source_root": tmp_path,
        "seed": 23,
        "delivery_mode": "portable_copy",
    }

    class AcceptedDialog:
        def __init__(self, _parent):
            self.config = config

        def exec(self):
            return main.QDialog.DialogCode.Accepted

    monkeypatch.setattr(hearing_panel, "HearingBlindPrepareDialog", AcceptedDialog)
    starts = []
    monkeypatch.setattr(window, "_start_hearing_worker", lambda worker, action: starts.append((worker, action)))

    window._prepare_hearing_blind()

    worker, action = starts[0]
    assert isinstance(worker, hearing_jobs.HearingBlindExportWorker)
    assert action == "blind_export"
    assert worker.config == {key: value for key, value in config.items() if key != "delivery_mode"}


def test_portable_blind_integrity_selection_starts_csv_checker(qtbot, monkeypatch, tmp_path):
    from hpg_core import hearing_jobs

    window = _window(qtbot, monkeypatch)
    public = tmp_path / "session" / "blind_session.csv"
    key = tmp_path / "private" / "blind_key.csv"
    selections = iter(((str(public), "CSV (*.csv)"), (str(key), "CSV (*.csv)")))
    monkeypatch.setattr(main.QFileDialog, "getOpenFileName", lambda *_args: next(selections))
    starts = []
    monkeypatch.setattr(window, "_start_hearing_worker", lambda worker, action: starts.append((worker, action)))

    window._check_hearing_blind()

    worker, action = starts[0]
    assert isinstance(worker, hearing_jobs.HearingBlindExportCheckWorker)
    assert (worker.public_path, worker.key_path) == (public, key)
    assert action == "blind_export_check"


def test_fit_requires_confirmation_and_cancel_keeps_preferences_untouched(
    qtbot, monkeypatch, tmp_path
):
    from hpg_core import hearing_panel, hearing_jobs
    window = _window(qtbot, monkeypatch)
    set_dir = tmp_path / "rated-set"
    set_dir.mkdir()
    Path(str(set_dir) + ".audit.json").write_text('{"ok":true}')
    (set_dir / "bewertung.csv").write_text("pair_id,clip_id,note,gewaehlt,zeit\n")
    window._hearing_set_path = str(set_dir)
    window._hearing_cache_path = str(tmp_path / "cache.db")
    starts = []
    monkeypatch.setattr(window, "_start_hearing_worker", lambda worker, action: starts.append((worker, action)))
    answers = iter((main.QDialog.DialogCode.Rejected, main.QDialog.DialogCode.Accepted))
    class FitDialog:
        def __init__(self, _cache, **_kwargs):
            self.cache = Path(window._hearing_cache_path)
            self.seed = 42
            self.genres = ()
        def exec(self):
            return next(answers)
    monkeypatch.setattr(hearing_panel, "HearingFitDialog", FitDialog)

    window._fit_hearing_set()
    assert starts == []

    window._fit_hearing_set()
    worker, action = starts[0]
    assert action == "fit"
    assert isinstance(worker, hearing_jobs.HearingCalibrationWorker)
    assert worker.fit is True
    assert worker.cache == window._hearing_cache_path
    assert worker.directory == str(set_dir)
    assert worker.seed == 42


def test_fit_button_waits_for_complete_ratings_and_pair_choice(qtbot, monkeypatch, tmp_path):
    window = _window(qtbot, monkeypatch)
    set_dir = tmp_path / "rated-set"
    set_dir.mkdir()
    Path(str(set_dir) + ".audit.json").write_text('{"ok":true}')
    (set_dir / "bewertung.csv").write_text(
        "pair_id,clip_id,note,gewaehlt,zeit\n"
        "p1,c1,4,1,now\np1,c2,5,0,now\n",
        encoding="utf-8",
    )
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"db")
    window._hearing_set_path = str(set_dir)
    window._hearing_cache_path = str(cache)
    window._update_hearing_buttons()
    assert window.analytics_panel.hearing_fit_button.isEnabled()

    (set_dir / "bewertung.csv").write_text(
        "pair_id,clip_id,note,gewaehlt,zeit\np1,c1,,1,now\np1,c2,5,0,now\n",
        encoding="utf-8",
    )
    window._update_hearing_buttons()
    assert not window.analytics_panel.hearing_fit_button.isEnabled()


@pytest.mark.parametrize(
    ("winning_note", "other_choice"),
    [("1", "0"), ("4", "x")],
    ids=("winner-note-one", "invalid-other-choice"),
)
def test_fit_button_rejects_invalid_candidate_choice(
    qtbot, monkeypatch, tmp_path, winning_note, other_choice
):
    window = _window(qtbot, monkeypatch)
    set_dir = tmp_path / "rated-set"
    set_dir.mkdir()
    Path(str(set_dir) + ".audit.json").write_text('{"ok":true}', encoding="utf-8")
    (set_dir / "bewertung.csv").write_text(
        "pair_id,clip_id,note,gewaehlt,zeit\n"
        f"p1,c1,{winning_note},1,now\n"
        f"p1,c2,5,{other_choice},now\n",
        encoding="utf-8",
    )
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"db")
    window._hearing_set_path = str(set_dir)
    window._hearing_cache_path = str(cache)

    window._update_hearing_buttons()

    assert not window.analytics_panel.hearing_fit_button.isEnabled()


@pytest.mark.parametrize(
    ("ratings_csv", "expected"),
    [
        (
            "pair_id,clip_id,note,gewaehlt,zeit\n"
            "p1,c1,1,0,now\np1,c2,5,0,now\n",
            True,
        ),
        (
            "pair_id,clip_id,track_note,technik_note,gesamt_note,gewaehlt,zeit\n"
            "p1,c1,3,4,5,,now\n",
            True,
        ),
        (
            "pair_id,clip_id,note,gewaehlt,zeit,extra\n"
            "p1,c1,4,1,now,unexpected\np1,c2,5,0,now,unexpected\n",
            False,
        ),
        ("pair_id,clip_id,note,gewaehlt,zeit\n", False),
    ],
    ids=("explicit-no-best", "three-note", "extra-column", "empty"),
)
def test_hearing_rating_precheck_respects_schema_and_completion(
    qtbot, monkeypatch, tmp_path, ratings_csv, expected
):
    window = _window(qtbot, monkeypatch)
    set_dir = tmp_path / "rated-set"
    set_dir.mkdir()
    (set_dir / "bewertung.csv").write_text(ratings_csv, encoding="utf-8")
    window._hearing_set_path = str(set_dir)

    assert window._hearing_ratings_complete() is expected


def test_hearing_server_retries_only_owned_process_and_stops_on_close(
    qtbot, monkeypatch, tmp_path
):
    class Signal:
        def connect(self, callback):
            self.callback = callback

    class FakeProcess:
        class ProcessState:
            NotRunning = 0
            Running = 1

        instances = []

        def __init__(self, _parent=None):
            self.started = Signal()
            self.errorOccurred = Signal()
            self.finished = Signal()
            self.readyReadStandardError = Signal()
            self._state = self.ProcessState.NotRunning
            self.arguments = []
            self.terminated = False
            self.deleted = False
            self.__class__.instances.append(self)

        def setProgram(self, value):
            self.program = value

        def setArguments(self, value):
            self.arguments = list(value)

        def start(self):
            self._state = self.ProcessState.Running

        def state(self):
            return self._state

        def terminate(self):
            self.terminated = True
            self._state = self.ProcessState.NotRunning

        def kill(self):
            self._state = self.ProcessState.NotRunning

        def waitForFinished(self, _timeout):
            self._state = self.ProcessState.NotRunning
            return True

        def deleteLater(self):
            self.deleted = True

    class FakeSocket:
        next_port = 17891

        def __init__(self, *_args):
            self.port = FakeSocket.next_port
            FakeSocket.next_port += 1

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def bind(self, address):
            assert address == ("127.0.0.1", 0)

        def getsockname(self):
            return "127.0.0.1", self.port

    monkeypatch.setattr(main, "QProcess", FakeProcess)
    monkeypatch.setattr(main.socket, "socket", FakeSocket)
    monkeypatch.setattr(main.QTimer, "singleShot", lambda _ms, callback: callback())
    window = _window(qtbot, monkeypatch)
    window._hearing_set_path = str(tmp_path / "set")
    window._hearing_cache_path = str(tmp_path / "cache.db")

    window._start_hearing_server()
    first = window._hearing_process
    assert "17891" in first.arguments
    assert first.arguments[first.arguments.index("--dir") + 1] == window._hearing_set_path

    # A stale process completion cannot stop or replace the currently owned process.
    stale = FakeProcess()
    current = window._hearing_process
    window._hearing_server_finished(stale, 1)
    assert window._hearing_process is current
    assert not stale.deleted

    # Bind/start failure retries with a fresh ephemeral loopback port.
    window._hearing_server_finished(first, 1)
    second = window._hearing_process
    assert second is not first
    assert "17892" in second.arguments
    assert window._hearing_port_attempts == 2

    # Closing HPG terminates only the process held as its own child.
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted()
    assert second.terminated
    assert window._hearing_process is None


def test_hearing_retry_cannot_start_remote_writer_during_native_dialog(qtbot, monkeypatch):
    window = _window(qtbot, monkeypatch)
    window._hearing_native_active = True
    monkeypatch.setattr(main, "QProcess", lambda *_args: pytest.fail("Remote writer started during native rating"))
    window._launch_hearing_server_attempt("")
    assert window._hearing_process is None


def test_native_prepare_calls_service_worker_not_cli(qtbot, monkeypatch, tmp_path):
    from hpg_core import hearing_panel, hearing_jobs
    from hpg_core.hearing_workflow import PrepareConfig

    window = _window(qtbot, monkeypatch)
    config = PrepareConfig("einzel", tmp_path / "set", tmp_path / "cache.db", source_roots=(tmp_path / "sources",))
    config.source_roots[0].mkdir()
    class AcceptedDialog:
        def __init__(self, _parent, *, folder=""):
            self.config = config
        def exec(self):
            return main.QDialog.DialogCode.Accepted
    monkeypatch.setattr(hearing_panel, "HearingPrepareDialog", AcceptedDialog)
    starts = []
    monkeypatch.setattr(window, "_start_hearing_worker", lambda worker, action: starts.append((worker, action)))
    # Kein DSP in diesem Steuerungstest; Start muss eine neue Analyse binden.
    source = SimpleNamespace(isRunning=lambda: False)
    def start_analysis(*, cache_policy="reuse", _hearing_config=None):
        assert cache_policy == "fresh"
        window.worker = source
        window._run_id = "hearing-test-run"
        window._hearing_analysis_pending = (_hearing_config, source, window._run_id)
        return True
    monkeypatch.setattr(window, "start_analysis", start_analysis)
    window._prepare_hearing_set()
    assert not starts
    assert window._hearing_analysis_pending == (config, source, "hearing-test-run")
    window.worker = None
    snapshot_folder = str(config.source_roots[0])
    if os.name == "nt":
        snapshot_folder = snapshot_folder.upper()
    window._hearing_analysis_snapshot = (snapshot_folder, ("metadata",), window._run_id)
    window._set_run_state(main.RunState.SUCCESS)
    window._resume_hearing_analysis(source)
    worker, action = starts[0]
    assert action == "prepare"
    assert isinstance(worker, hearing_jobs.HearingPrepareWorker)
    assert worker.config is config
    assert worker.managed_metadata == ("metadata",)
    assert callable(worker.request_cancel)


@pytest.mark.parametrize(("persisted", "effective", "expected_pending"), [
    (True, True, True), (True, False, True), (False, False, False),
])
def test_apply_result_schedules_ranking_refresh_only_after_persist(
    qtbot, monkeypatch, persisted, effective, expected_pending
):
    window = _window(qtbot, monkeypatch)
    result = {"ok": True, "apply_state": {
        "persisted": persisted, "effective_reload": effective,
        "error": "reload failed" if persisted and not effective else "",
    }}
    window._hearing_completed(result, "apply")
    assert window._hearing_refresh_pending is expected_pending
    assert ("Gewichte gespeichert: JA" if persisted else "Gewichte gespeichert: NEIN") in window.analytics_panel.hearing_status.text()
    if persisted and not effective:
        assert "effektiver Reload: NEIN" in window.analytics_panel.hearing_status.text()


def test_apply_refresh_uses_new_scoring_context(qtbot, monkeypatch):
    window = _window(qtbot, monkeypatch)
    window.analyzed_raw_tracks = [SimpleNamespace(filePath="synthetic-track")]
    refreshed = []
    from hpg_core import candidate_preferences, candidate_choices
    monkeypatch.setattr(candidate_preferences, "reset_cache", lambda: refreshed.append("cache-reset"))
    monkeypatch.setattr(candidate_choices, "snapshot", lambda: {"fresh": True})
    monkeypatch.setattr(window.library_panel, "get_current_settings", lambda: {
        "strategy": "balanced", "advanced_params": {}, "bpm_tolerance": 6,
    })
    monkeypatch.setattr(main.StrategyConfig, "from_mapping", lambda _value: object())
    monkeypatch.setattr(main, "resolve_run_scoring_context", lambda strategy, _params: {"revision": "new"})
    monkeypatch.setattr(main, "PlaylistGenerationWorker", lambda *args, **kwargs: _FakePlaylistWorker(refreshed))
    window._refresh_hearing_ranking()
    assert refreshed[0] == "cache-reset"
    assert window._run_settings["scoring_context"] == {"revision": "new"}
    assert window._run_settings["candidate_choice_snapshot"] == {"fresh": True}
    assert "worker-start" in refreshed
    assert window._hearing_refresh_worker is window.playlist_worker


class _FakePlaylistWorker:
    def __init__(self, events):
        from PyQt6.QtCore import QObject, pyqtSignal
        class Signals(QObject):
            generation_done = pyqtSignal(object)
            generation_failed = pyqtSignal(str)
            finished = pyqtSignal()
        self.signals = Signals()
        self.generation_done = self.signals.generation_done
        self.generation_failed = self.signals.generation_failed
        self.finished = self.signals.finished
        self.events = events
    def start(self):
        self.events.append("worker-start")
    def isRunning(self):
        return False


def test_failed_ranking_refresh_does_not_claim_success(qtbot, monkeypatch):
    window = _window(qtbot, monkeypatch)
    worker = _FakePlaylistWorker([])
    window.playlist_worker = worker
    window._hearing_refresh_worker = worker
    window._on_playlist_generation_failed("synthetic scoring failure", worker)
    assert window._hearing_refresh_worker is None
    assert "fehlgeschlagen" in window.analytics_panel.hearing_status.text()
    assert "Ranking-Neuberechnung fehlgeschlagen" in window.analytics_panel.hearing_status.text()
