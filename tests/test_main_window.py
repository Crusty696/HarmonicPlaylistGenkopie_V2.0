"""Regressionstests fuer den GUI-gesteuerten Hoertest-Ablauf."""

from __future__ import annotations

import json
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


def test_hearing_prepare_uses_exact_cache_audits_then_publishes(tmp_path, monkeypatch):
    cache = tmp_path / "selected-cache.db"
    cache.write_bytes(b"cache")
    target = tmp_path / "new-hearing-set"
    calls = []

    def run_command(self, label, args):
        calls.append((label, list(args)))
        if args[0].endswith("rate_transitions.py"):
            assert args[args.index("--cache") + 1] == str(cache)
            stage = Path(args[args.index("--out") + 1])
            assert stage.parent == target.parent
            assert stage.name.endswith(".staging")
            (stage / "bewertung.csv").write_text("pair_id,clip_id,note,gewaehlt,zeit\n")
        else:
            report = Path(args[args.index("--report") + 1])
            report.write_text(json.dumps({"ok": True}))
            audited = Path(args[args.index("--set-dir") + 1])
            assert audited.is_dir()
        return "ok"

    monkeypatch.setattr(main.HearingWorkflowWorker, "_run_command", run_command)
    worker = main.HearingWorkflowWorker(tmp_path, cache, target, 7)
    results = []
    worker.completed.connect(results.append)
    worker.run()

    assert results[0]["ok"] is True
    assert Path(results[0]["set_path"]) == target
    assert results[0]["cache_path"] == str(cache)
    assert target.is_dir()
    assert (tmp_path / "new-hearing-set.audit.json").is_file()
    audit_calls = [args for _label, args in calls if args[0].endswith("audit_candidate_set.py")]
    assert len(audit_calls) == 2
    assert Path(audit_calls[0][audit_calls[0].index("--set-dir") + 1]).name.endswith(".staging")
    assert Path(audit_calls[1][audit_calls[1].index("--set-dir") + 1]) == target


def test_hearing_prepare_refuses_existing_destination_without_touching_it(tmp_path, monkeypatch):
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"cache")
    target = tmp_path / "already-rated"
    target.mkdir()
    rating = target / "bewertung.csv"
    rating.write_text("valuable ratings")
    invoked = []
    monkeypatch.setattr(
        main.HearingWorkflowWorker,
        "_run_command",
        lambda *_args: invoked.append(True),
    )
    worker = main.HearingWorkflowWorker(tmp_path, cache, target, 5)
    results = []
    worker.completed.connect(results.append)
    worker.run()

    assert results[0]["ok"] is False
    assert not invoked
    assert rating.read_text() == "valuable ratings"


def test_hearing_prepare_rolls_back_if_final_path_audit_fails(tmp_path, monkeypatch):
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"cache")
    target = tmp_path / "not-published"
    audit_count = 0

    def run_command(self, _label, args):
        nonlocal audit_count
        if args[0].endswith("rate_transitions.py"):
            stage = Path(args[args.index("--out") + 1])
            (stage / "bewertung.csv").write_text("candidate data")
            return "prepared"
        audit_count += 1
        report = Path(args[args.index("--report") + 1])
        report.write_text('{"ok":false}')
        if audit_count == 2:
            raise RuntimeError("final audit failed")
        return "stage audit passed"

    monkeypatch.setattr(main.HearingWorkflowWorker, "_run_command", run_command)
    worker = main.HearingWorkflowWorker(tmp_path, cache, target, 3)
    results = []
    worker.completed.connect(results.append)
    worker.run()

    assert results[0]["ok"] is False
    assert not target.exists()
    recovery = Path(results[0]["staging_path"])
    assert recovery.is_dir()
    assert (recovery / "bewertung.csv").read_text() == "candidate data"


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


def test_hearing_fit_passes_exact_cache_and_audit_after_rating_validation(
    tmp_path, monkeypatch
):
    import tools.hoertest_server as server
    import tools.rate_transitions as rating_tool

    cache = tmp_path / "cache-v45.db"
    cache.write_bytes(b"cache")
    set_dir = tmp_path / "set"
    set_dir.mkdir()
    audit = Path(str(set_dir) + ".audit.json")
    audit.write_text('{"ok":true}')
    (set_dir / "bewertung.csv").write_text("validated by existing tool")
    monkeypatch.setattr(rating_tool, "lies_csv", lambda _path: [{"note": "5"}])
    monkeypatch.setattr(
        rating_tool, "validiere_vollstaendige_kandidatenbewertung", lambda _rows: None
    )
    monkeypatch.setattr(server, "bewertungsschema", lambda _path: ("pair_id", "clip_id", "note"))
    calls = []
    monkeypatch.setattr(
        main.HearingWorkflowWorker,
        "_run_command",
        lambda _self, _label, args: calls.append(list(args)) or "Fit-Bericht erstellt",
    )
    worker = main.HearingWorkflowWorker(tmp_path, cache, set_dir, 0, fit=True)
    results = []
    worker.completed.connect(results.append)
    worker.run()

    assert results[0]["ok"] is True
    args = calls[0]
    assert args[:4] == ["tools/rate_transitions.py", "fit", "--modus", "kandidaten"]
    assert args[args.index("--cache") + 1] == str(cache)
    assert args[args.index("--audit-report") + 1] == str(audit)
    assert "request_cancel" not in dir(worker)


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
    class AcceptedDialog:
        def __init__(self, _parent):
            self.config = config
        def exec(self):
            return main.QDialog.DialogCode.Accepted
    monkeypatch.setattr(hearing_panel, "HearingPrepareDialog", AcceptedDialog)
    starts = []
    monkeypatch.setattr(window, "_start_hearing_worker", lambda worker, action: starts.append((worker, action)))
    window._prepare_hearing_set()
    worker, action = starts[0]
    assert action == "prepare"
    assert isinstance(worker, hearing_jobs.HearingPrepareWorker)
    assert worker.config is config
    assert callable(worker.request_cancel)
