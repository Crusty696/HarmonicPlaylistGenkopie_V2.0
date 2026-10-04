"""Native Satzsuche/Blindvorbereitung: Metadaten, keine Musikqualitaetspruefung."""

import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QThread
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel

import main
from hpg_core import hearing_jobs, hearing_panel, hearing_sources
from tests.test_hearing_blind import _fixture as blind_fixture
from tests.test_hearing_native_integration import _fingerprints
from tests.test_hearing_sources import source_fixture
from tests.test_main_window import _window


def _trace_jobs(window, monkeypatch, paused):
    trace = SimpleNamespace(starts=[], results=[], finished=[], cleaned=[], status=[], gates=[])
    real_start, real_cleanup = window._start_hearing_worker, window._cleanup_hearing_worker
    for worker_type in paused:
        real_run = worker_type.run
        def run(worker, implementation=real_run):
            implementation(worker)
            assert worker._integration_gate.wait(15), "Eigener Test-Worker nicht freigegeben"
        monkeypatch.setattr(worker_type, "run", run)
    def start(worker, action):
        trace.starts.append((worker, action))
        if isinstance(worker, paused):
            worker._integration_gate = threading.Event()
            trace.gates.append(worker._integration_gate)
        worker.completed.connect(lambda result: trace.results.append(
            (id(worker), action, result, window._hearing_worker is worker)))
        worker.status_update.connect(lambda message: trace.status.append((message, QThread.currentThread())))
        worker.finished.connect(lambda: trace.finished.append((id(worker), worker.isRunning())))
        return real_start(worker, action)
    def cleanup(worker):
        assert not worker.isRunning() and (id(worker), False) in trace.finished
        trace.cleaned.append(id(worker))
        real_cleanup(worker)
    monkeypatch.setattr(window, "_start_hearing_worker", start)
    monkeypatch.setattr(window, "_cleanup_hearing_worker", cleanup)
    return trace


def _release_jobs(window, trace, qtbot):
    for gate in trace.gates:
        gate.set()
    if window._hearing_worker is not None:
        window._hearing_worker.request_cancel()
        qtbot.waitUntil(lambda: window._hearing_worker is None, timeout=30000)


def _ordinary_state(window, tmp_path):
    folder = tmp_path / "ordinary"
    folder.mkdir()
    (folder / "bewertung.csv").write_text("pair_id,clip,bewertung\np,clips/p.wav,4\n")
    window._hearing_set_path = str(folder)
    window._hearing_cache_path = str(tmp_path / "ordinary-cache.db")
    return window._hearing_set_path, window._hearing_cache_path


@pytest.mark.gui
@pytest.mark.integration
@pytest.mark.parametrize("outcome", ["valid", "invalid", "cancel", "close"])
def test_blind_check_button_slow_actual_worker_no_modal_or_state_change(qtbot, monkeypatch, tmp_path, outcome):
    from hpg_core import hearing_blind
    manifest, output, key, root = blind_fixture(tmp_path, count=2)
    public, _ = hearing_blind.prepare_blind_references(manifest, output, key, root, seed=3)
    if outcome == "invalid":
        key.write_text("SECRET invalid key", encoding="utf-8")
    window = _window(qtbot, monkeypatch)
    ordinary = _ordinary_state(window, tmp_path)
    before = _fingerprints(tmp_path)
    worker_type = getattr(hearing_jobs, "HearingBlindCheckWorker", None)
    assert worker_type is not None, "Blind-Integritaetsworker fehlt"
    button = getattr(window.analytics_panel, "hearing_blind_check_button", None)
    assert button is not None, "GUI-Pruefaktion fehlt"
    trace = _trace_jobs(window, monkeypatch, (worker_type,))
    warnings, information, hashes = [], [], []
    monkeypatch.setattr(main.QMessageBox, "warning", lambda *args: warnings.append(args[-1]))
    monkeypatch.setattr(main.QMessageBox, "information", lambda *args: information.append(args[-1]))
    paths = iter([str(public), str(key)])
    def choose(*args):
        assert window._hearing_native_active and not button.isEnabled()
        return next(paths), ""
    monkeypatch.setattr(main.QFileDialog, "getOpenFileName", choose)
    real_hash = hearing_blind._fingerprint
    entered, release = threading.Event(), threading.Event()
    def paused_hash(path, checkpoint):
        hashes.append(QThread.currentThread())
        if outcome in {"cancel", "close"}:
            entered.set()
            assert release.wait(10)
        return real_hash(path, checkpoint)
    monkeypatch.setattr(hearing_blind, "_fingerprint", paused_hash)
    try:
        button.click()
        worker, action = trace.starts[0]
        assert action == "blind_check" and isinstance(worker, worker_type)
        if outcome in {"cancel", "close"}:
            qtbot.waitUntil(entered.is_set, timeout=5000)
            if outcome == "cancel":
                window._cancel_hearing_work()
            else:
                window._close_pending = True
                worker.request_cancel()
            preserved_status = window.analytics_panel.hearing_status.text()
            release.set()
        qtbot.waitUntil(lambda: bool(trace.results), timeout=10000)
        assert worker.isRunning() and window._hearing_worker is worker
        assert not trace.cleaned and not button.isEnabled()
        assert not information
        assert (window._hearing_set_path, window._hearing_cache_path) == ordinary
        if outcome == "valid":
            status = window.analytics_panel.hearing_status.text()
            assert "Integrität" in status and "2" in status and "Keine Bewertung" in status
            assert not warnings and hashes
        elif outcome == "invalid":
            assert warnings and "SECRET" not in warnings[0]
        elif outcome == "cancel":
            assert not warnings and trace.results[0][2]["cancelled"]
        else:
            assert not warnings and window.analytics_panel.hearing_status.text() == preserved_status
        assert all(thread != QThread.currentThread() for thread in hashes)
        trace.gates[0].set()
        qtbot.waitUntil(lambda: window._hearing_worker is None, timeout=10000)
        assert trace.cleaned == [id(worker)] and not information
        assert _fingerprints(tmp_path) == before
        assert (window._hearing_set_path, window._hearing_cache_path) == ordinary
    finally:
        release.set()
        _release_jobs(window, trace, qtbot)
        window._close_pending = False


@pytest.mark.parametrize("block", ["first_cancel", "second_cancel", "close", "remote", "native", "worker", "run", "between_close", "between_run", "between_remote"])
def test_blind_check_selection_guards_and_no_ordinary_state_overwrite(qtbot, monkeypatch, tmp_path, block):
    window = _window(qtbot, monkeypatch)
    ordinary = _ordinary_state(window, tmp_path)
    method = getattr(window, "_check_hearing_blind", None)
    assert method is not None, "GUI-Pruefaktion fehlt"
    starts, selections = [], []
    monkeypatch.setattr(window, "_start_hearing_worker", lambda *args: starts.append(args))
    if block == "close":
        window._close_pending = True
    elif block == "remote":
        window._hearing_process = SimpleNamespace(state=lambda: main.QProcess.ProcessState.Running)
    elif block == "native":
        window._hearing_native_active = True
    elif block == "worker":
        window._hearing_worker = QThread(window)
    elif block == "run":
        window._set_run_state(main.RunState.PLAYLIST)
    def choose(*args):
        selections.append(args)
        if block == "between_close":
            window._close_pending = True
        elif block == "between_run":
            window._set_run_state(main.RunState.PLAYLIST)
        elif block == "between_remote":
            window._hearing_process = SimpleNamespace(state=lambda: main.QProcess.ProcessState.Running)
        return ("" if block == "first_cancel" or block == "second_cancel" and len(selections) == 2 else str(tmp_path / "selected.json")), ""
    monkeypatch.setattr(main.QFileDialog, "getOpenFileName", choose)
    try:
        method()
        assert not starts
        assert len(selections) == (0 if block in {"close", "remote", "native", "worker", "run"} else 2 if block == "second_cancel" else 1)
        assert (window._hearing_set_path, window._hearing_cache_path) == ordinary
    finally:
        window._close_pending = False
        window._hearing_process = None
        window._hearing_worker = None
        window._hearing_native_active = False
        window._set_run_state(main.RunState.IDLE)


@pytest.mark.gui
@pytest.mark.integration
@pytest.mark.parametrize("selection", ["valid", "changed_source", "cancel"])
def test_discovery_rows_then_full_load_only_after_finished(qtbot, monkeypatch, tmp_path, source_fixture, selection):
    folder, _, sink, a, _ = source_fixture
    hearing_sources.write_source_manifest(folder, "einzel", sink)
    before = _fingerprints(folder)
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "bewertung.csv").write_text("wrong,header\nx,y\n")
    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "bewertung.csv").write_text("pair_id,clip,bewertung\n")
    window = _window(qtbot, monkeypatch)
    ordinary = _ordinary_state(window, tmp_path)
    trace = _trace_jobs(window, monkeypatch, (hearing_jobs.HearingDiscoveryWorker,))
    gui_thread = QThread.currentThread()
    warnings, shown, full_loads = [], [], []
    monkeypatch.setattr(main.QMessageBox, "warning", lambda *args: warnings.append(args[-1]))
    monkeypatch.setattr(main.QFileDialog, "getExistingDirectory", lambda *args: str(tmp_path))
    real_load = hearing_sources.load_source_session
    def load(path, **kwargs):
        full_loads.append((Path(path), kwargs, QThread.currentThread()))
        return real_load(path, **kwargs)
    monkeypatch.setattr(hearing_sources, "load_source_session", load)
    browser_type = hearing_panel.HearingSetBrowserDialog
    class Browser(browser_type):
        def exec(self):
            qtbot.addWidget(self)
            assert QThread.currentThread() == gui_thread
            assert window._hearing_worker is None and window._hearing_native_active
            assert trace.cleaned[-1] == id(trace.starts[0][0])
            assert not full_loads
            shown.append(self)
            rows = {summary.path: index for index, summary in enumerate(self.summaries)}
            for path, status in ((broken, "error"), (empty, "empty")):
                row = rows[path]
                assert self.table.item(row, 3).text() == status
                self.table.selectRow(row)
                assert not self.open_button.isEnabled()
                self._open_selected()
                assert self.selected_path is None
                if status == "error":
                    assert self.table.item(row, 4).text()
            row = rows[folder]
            assert [self.table.item(row, col).text() for col in (1, 2, 3)] == ["Standard", "0/1", "new"]
            assert any("Kein Quellen- oder Auditnachweis" in label.text() for label in self.findChildren(QLabel))
            self.table.selectRow(row)
            assert self.open_button.isEnabled()
            if selection == "cancel":
                self.reject()
                return QDialog.DialogCode.Rejected
            if selection == "changed_source":
                a.write_bytes(b"X" * a.stat().st_size)
            self._open_selected()
            assert self.selected_path == folder
            return QDialog.DialogCode.Accepted
    monkeypatch.setattr(hearing_panel, "HearingSetBrowserDialog", Browser)
    try:
        window._discover_hearing_sets()
        discovery = trace.starts[0][0]
        assert isinstance(discovery, hearing_jobs.HearingDiscoveryWorker)
        qtbot.waitUntil(lambda: window._hearing_pending_discovery is not None, timeout=10000)
        assert discovery.isRunning() and window._hearing_worker is discovery
        assert not shown and not full_loads
        assert (window._hearing_set_path, window._hearing_cache_path) == ordinary
        assert not window.analytics_panel.hearing_discovery_button.isEnabled()
        assert not window.analytics_panel.hearing_csv_fit_button.isEnabled()
        trace.gates[0].set()
        qtbot.waitUntil(lambda: bool(shown) and window._hearing_worker is None, timeout=15000)
        assert window._hearing_pending_discovery is None and not window._hearing_native_active
        if selection == "cancel":
            assert len(trace.starts) == 1 and not full_loads and not warnings
            assert (window._hearing_set_path, window._hearing_cache_path) == ordinary
        else:
            loader = trace.starts[1][0]
            assert isinstance(loader, hearing_jobs.HearingLoadWorker)
            assert [action for _, action in trace.starts] == ["discover", "open"]
            assert full_loads == [(folder, {"verify_source_contents": True}, loader)]
            assert full_loads[0][2] != gui_thread
            result = trace.results[-1][2]
            if selection == "valid":
                assert result["ok"] and result["session"]["mode"] == "einzel"
                assert result["session"]["groups"][0]["clips"][0]["path"] is None
                assert window._hearing_set_path == str(folder) and not warnings
                assert window._hearing_cache_path == ""
                assert "Kein Render-/Audit-Nachweis" in window.analytics_panel.hearing_status.text()
            else:
                assert not result["ok"] and "veraendert" in result["output"]
                assert (window._hearing_set_path, window._hearing_cache_path) == ordinary
                assert warnings
        assert len(trace.cleaned) == len(trace.starts)
        assert all(owned for _, _, _, owned in trace.results)
        assert all(thread == gui_thread for _, thread in trace.status)
        assert _fingerprints(folder) == before
    finally:
        _release_jobs(window, trace, qtbot)


@pytest.mark.gui
@pytest.mark.integration
@pytest.mark.parametrize("seed", [None, -17])
@pytest.mark.parametrize("outcome", ["success", "existing_output", "key_inside"])
def test_blind_form_exact_mapping_real_worker_preserves_ordinary_set(qtbot, monkeypatch, tmp_path, seed, outcome):
    import soundfile as sf
    from hpg_core import hearing_blind, transition_renderer
    manifest, output, key, root = blind_fixture(tmp_path, count=2)
    before = _fingerprints(root)
    if outcome == "existing_output":
        output.mkdir()
        (output / "valuable.txt").write_text("keep")
    elif outcome == "key_inside":
        key = output / "private.json"
    expected = {"manifest": manifest, "output_dir": output, "key_path": key,
                "source_root": root, "seed": seed}
    window = _window(qtbot, monkeypatch)
    ordinary = _ordinary_state(window, tmp_path)
    ordinary_before = _fingerprints(Path(ordinary[0]))
    trace = _trace_jobs(window, monkeypatch, (hearing_jobs.HearingBlindWorker,))
    gui_thread = QThread.currentThread()
    warnings, hashes = [], []
    monkeypatch.setattr(main.QMessageBox, "warning", lambda *args: warnings.append(args[-1]))
    def forbidden(*args, **kwargs):
        raise AssertionError("Blindvorbereitung darf Audio weder rendern noch kopieren/dekodieren")
    monkeypatch.setattr(sf, "write", forbidden)
    monkeypatch.setattr(sf, "read", forbidden)
    monkeypatch.setattr(transition_renderer, "render_transition_clip", forbidden)
    fingerprint = hearing_blind._fingerprint
    def observe_hash(path, checkpoint):
        hashes.append(QThread.currentThread())
        return fingerprint(path, checkpoint)
    monkeypatch.setattr(hearing_blind, "_fingerprint", observe_hash)
    form_type = hearing_panel.HearingBlindPrepareDialog
    class Form(form_type):
        def exec(self):
            qtbot.addWidget(self)
            assert not self.seed_box.isEnabled()
            for name, path in expected.items():
                if name != "seed":
                    self.edits[name].setText(f" {path} ")
            self.seed_enabled.setChecked(seed is not None)
            assert self.seed_box.isEnabled() is (seed is not None)
            if seed is not None:
                self.seed_box.setValue(seed)
            notice = "\n".join(label.text() for label in self.findChildren(QLabel))
            assert "LOCAL UI BLIND" in notice and "Nicht metadatenblind, nicht portabel" in notice
            self._accept_config()
            assert self.config == expected
            assert self.result() == QDialog.DialogCode.Accepted
            return self.result()
    monkeypatch.setattr(hearing_panel, "HearingBlindPrepareDialog", Form)
    try:
        window._prepare_hearing_blind()
        worker, action = trace.starts[0]
        assert isinstance(worker, hearing_jobs.HearingBlindWorker) and action == "blind"
        assert worker.config == expected
        qtbot.waitUntil(lambda: bool(trace.results), timeout=15000)
        assert worker.isRunning() and window._hearing_worker is worker
        assert not window.analytics_panel.hearing_blind_button.isEnabled()
        assert not window.analytics_panel.hearing_csv_fit_button.isEnabled()
        assert (window._hearing_set_path, window._hearing_cache_path) == ordinary
        assert window._hearing_pending_discovery is None and window._hearing_pending_rating is None
        trace.gates[0].set()
        qtbot.waitUntil(lambda: window._hearing_worker is None, timeout=10000)
        result = trace.results[0][2]
        if outcome == "success":
            assert result["ok"] and not warnings
            assert result["public_path"] == str(output / hearing_blind.PUBLIC_NAME)
            assert result["key_path"] == str(key)
            public = json.loads((output / hearing_blind.PUBLIC_NAME).read_text())
            assert public["format"] == "hpg_local_ui_blind_refs" and public["scope"] == "local_ui_blind"
            assert public["metadata_blinded"] is False and len(public["pairs"]) == 2
            assert [p["pair_id"] for p in public["pairs"]] == ["pair_001", "pair_002"]
            assert key.is_file() and not key.is_relative_to(output)
            assert hashes and all(thread == worker and thread != gui_thread for thread in hashes)
            assert "LOCAL UI BLIND vorbereitet" in window.analytics_panel.hearing_status.text()
        else:
            assert not result["ok"] and warnings and not key.exists()
            if outcome == "existing_output":
                assert (output / "valuable.txt").read_text() == "keep"
                assert set(p.name for p in output.iterdir()) == {"valuable.txt"}
            else:
                assert not output.exists()
        assert trace.cleaned == [id(worker)] and trace.finished == [(id(worker), False)]
        assert all(owned for _, _, _, owned in trace.results)
        assert all(thread == gui_thread for _, thread in trace.status)
        assert (window._hearing_set_path, window._hearing_cache_path) == ordinary
        assert _fingerprints(Path(ordinary[0])) == ordinary_before
        assert _fingerprints(root) == before
        assert not list(output.rglob("*.wav")) and not list(output.rglob("*.mp3"))
        assert not list(tmp_path.glob(".session.staging-*"))
        assert window.analytics_panel.hearing_blind_button.isEnabled()
    finally:
        _release_jobs(window, trace, qtbot)


@pytest.mark.gui
@pytest.mark.parametrize("guard", ["busy", "native", "remote", "closing"])
def test_discovery_blind_and_open_guards_preserve_ordinary_state(qtbot, monkeypatch, tmp_path, guard):
    window = _window(qtbot, monkeypatch)
    ordinary = _ordinary_state(window, tmp_path)
    before = _fingerprints(Path(ordinary[0]))
    def forbidden(*args, **kwargs):
        raise AssertionError("Gesperrte Auswahl darf weder Dialog noch Worker starten")
    monkeypatch.setattr(main.QFileDialog, "getExistingDirectory", forbidden)
    monkeypatch.setattr(hearing_panel, "HearingSetBrowserDialog", forbidden)
    monkeypatch.setattr(hearing_panel, "HearingBlindPrepareDialog", forbidden)
    monkeypatch.setattr(window, "_start_hearing_worker", forbidden)
    if guard == "busy":
        window._hearing_worker = QThread(window)
    elif guard == "native":
        window._hearing_native_active = True
    elif guard == "remote":
        window._hearing_process = SimpleNamespace(state=lambda: main.QProcess.ProcessState.Running)
    else:
        window._close_pending = True
    try:
        window._discover_hearing_sets()
        window._prepare_hearing_blind()
        window._show_hearing_discovery(())
        window._open_hearing_set()
        assert (window._hearing_set_path, window._hearing_cache_path) == ordinary
        assert window._hearing_pending_discovery is None
        assert _fingerprints(Path(ordinary[0])) == before
    finally:
        window._hearing_worker = None
        window._hearing_native_active = False
        window._hearing_process = None


@pytest.mark.gui
@pytest.mark.parametrize("kind", ["prepare", "blind"])
def test_accepted_prepare_modal_rechecks_shutdown(qtbot, monkeypatch, tmp_path, kind):
    window = _window(qtbot, monkeypatch)
    ordinary = _ordinary_state(window, tmp_path)
    monkeypatch.setattr(window, "_managed_workers_for_close", lambda: [])
    def forbidden(*args, **kwargs):
        raise AssertionError("Nach Close darf kein Prepare-Worker entstehen")
    class Form:
        def __init__(self, parent):
            self.config = object()
        def exec(self):
            assert window._hearing_native_active
            event = QCloseEvent()
            window.closeEvent(event)
            assert event.isAccepted()
            return QDialog.DialogCode.Accepted
    monkeypatch.setattr(hearing_panel, "HearingPrepareDialog" if kind == "prepare" else "HearingBlindPrepareDialog", Form)
    monkeypatch.setattr(hearing_jobs, "HearingPrepareWorker" if kind == "prepare" else "HearingBlindWorker", forbidden)
    getattr(window, "_prepare_hearing_set" if kind == "prepare" else "_prepare_hearing_blind")()
    assert window._close_pending and window._hearing_worker is None
    assert (window._hearing_set_path, window._hearing_cache_path) == ordinary


@pytest.mark.gui
def test_failed_direct_load_retains_set_and_cache(qtbot, monkeypatch, tmp_path):
    window = _window(qtbot, monkeypatch)
    ordinary = _ordinary_state(window, tmp_path)
    broken = tmp_path / "broken-load"
    broken.mkdir()
    (broken / "bewertung.csv").write_text("invalid,header\nx,y\n")
    warnings = []
    monkeypatch.setattr(main.QFileDialog, "getExistingDirectory", lambda *args: str(broken))
    monkeypatch.setattr(main.QMessageBox, "warning", lambda *args: warnings.append(args))
    trace = _trace_jobs(window, monkeypatch, ())
    window._open_hearing_set()
    qtbot.waitUntil(lambda: window._hearing_worker is None, timeout=10000)
    assert isinstance(trace.starts[0][0], hearing_jobs.HearingLoadWorker)
    assert not trace.results[0][2]["ok"] and warnings
    assert len(trace.cleaned) == 1
    assert (window._hearing_set_path, window._hearing_cache_path) == ordinary


@pytest.mark.gui
@pytest.mark.parametrize("accepts_cancel", [False, True, None])
def test_cancel_status_respects_publication_boundary(qtbot, monkeypatch, tmp_path, accepts_cancel):
    from hpg_core.hearing_workflow import CancellationToken
    window = _window(qtbot, monkeypatch)
    token = CancellationToken()
    if accepts_cancel is False:
        assert token.begin_publish()
    worker = SimpleNamespace(request_cancel=(lambda: None) if accepts_cancel is None else token.request_cancel)
    window._hearing_worker = worker
    try:
        window._cancel_hearing_work()
        text = window.analytics_panel.hearing_status.text()
        if accepts_cancel is False:
            assert "Publikation" in text and "Abbruch angefordert" not in text
            assert token.state == token.PUBLISHING
            result = {"ok": True, "prepared_only": True, "set_path": str(tmp_path / "published"),
                      "cache_path": "selected-cache", "output": "Quellenreferenzen vorbereitet. Nicht auditiert."}
            window._hearing_completed(result, "prepare", worker)
            assert window._hearing_set_path == result["set_path"]
            assert "vorbereitet" in window.analytics_panel.hearing_status.text()
        else:
            assert "Abbruch angefordert" in text
    finally:
        window._hearing_worker = None


@pytest.mark.gui
@pytest.mark.parametrize("action", ["open", "prepare", "discover", "fit", "apply", "error"])
def test_completion_during_close_has_no_ui_or_state_effect(qtbot, monkeypatch, tmp_path, action):
    window = _window(qtbot, monkeypatch)
    ordinary = _ordinary_state(window, tmp_path)
    worker = QThread(window)
    window._hearing_worker = worker
    window._close_pending = True
    status = window.analytics_panel.hearing_status.text()
    def forbidden(*args, **kwargs):
        raise AssertionError("Shutdown darf keinen Ergebnisdialog anzeigen")
    monkeypatch.setattr(main.QMessageBox, "warning", forbidden)
    result = {"ok": action != "error", "set_path": "new", "cache_path": "new-cache",
              "session": {"mode": "einzel"}, "summaries": (), "proposal": {},
              "apply_state": {"persisted": True, "effective_reload": True, "error": ""}}
    try:
        window._hearing_completed(result, action, worker)
        assert (window._hearing_set_path, window._hearing_cache_path) == ordinary
        assert window.analytics_panel.hearing_status.text() == status
        assert window._hearing_pending_discovery is None
        assert window._hearing_pending_rating is None and window._hearing_pending_proposal is None
        assert not window._hearing_refresh_pending
    finally:
        window._hearing_worker = None


@pytest.mark.gui
def test_close_flag_precedes_wait_and_survives_acceptance(qtbot, monkeypatch):
    window = _window(qtbot, monkeypatch)
    observations = []
    hearing_worker = QThread(window)
    window._hearing_worker = hearing_worker
    window._hearing_pending_discovery = ()
    window._hearing_pending_rating = ({}, "folder", False)
    window._hearing_pending_proposal = ({}, "")
    status = window.analytics_panel.hearing_status.text()
    def forbidden(*args, **kwargs):
        raise AssertionError("Reentrantes Cleanup waehrend Close darf kein Modal oeffnen")
    for name in ("_show_hearing_discovery", "_show_hearing_rating", "_show_hearing_proposal"):
        monkeypatch.setattr(window, name, forbidden)
    def wait(_timeout):
        observations.append(window._close_pending)
        # Simuliert die Zustellung von Ergebnis/finished innerhalb eines Waits.
        window._hearing_status("spaetes Ergebnis", hearing_worker)
        window._hearing_completed({"ok": True, "summaries": ()}, "discover", hearing_worker)
        window._cleanup_hearing_worker(hearing_worker)
        return True
    states = iter([True, False])
    worker = SimpleNamespace(isRunning=lambda: next(states), requestInterruption=lambda: None, wait=wait)
    monkeypatch.setattr(window, "_managed_workers_for_close", lambda: [worker])
    event = QCloseEvent()
    window.closeEvent(event)
    assert observations == [True]
    assert event.isAccepted() and window._close_pending
    assert window._hearing_worker is None
    assert window._hearing_pending_discovery is None and window._hearing_pending_rating is None
    assert window._hearing_pending_proposal is None
    assert window.analytics_panel.hearing_status.text() == status
    monkeypatch.setattr(window, "_managed_workers_for_close", lambda: [])


@pytest.mark.gui
def test_close_pending_blocks_low_level_start_and_server(qtbot, monkeypatch):
    window = _window(qtbot, monkeypatch)
    window._close_pending = True
    starts = []
    worker = SimpleNamespace(start=lambda: starts.append(True))
    assert window._start_hearing_worker(worker, "prepare") is False
    assert window._hearing_worker is None and not starts
    def forbidden(*args, **kwargs):
        raise AssertionError("Shutdown darf keinen Remote-Prozess starten")
    monkeypatch.setattr(window, "_launch_hearing_server_attempt", forbidden)
    window._hearing_set_path = "selected"
    window._start_hearing_server()


@pytest.mark.gui
def test_single_csv_quality_entry_preserves_selection_and_passes_true_none(qtbot, monkeypatch, tmp_path):
    window = _window(qtbot, monkeypatch)
    ordinary = _ordinary_state(window, tmp_path)
    selected = tmp_path / "csv-only"
    selected.mkdir()
    (selected / "bewertung.csv").write_text("pair_id,clip,bewertung\np,missing.wav,4\n")
    calls, starts = [], []
    monkeypatch.setattr(main.QFileDialog, "getExistingDirectory", lambda *args: str(selected))
    class Form(hearing_panel.HearingFitDialog):
        def __init__(self, cache, **kwargs):
            calls.append((cache, kwargs))
            super().__init__(cache, **kwargs)
        def exec(self):
            qtbot.addWidget(self)
            assert window._hearing_native_active
            assert self.cache_edit.text() == ""
            self.seed_box.setValue(-17)
            self.genres_edit.setText("Techno")
            self.findChild(QDialogButtonBox).accepted.emit()
            assert self.result() == QDialog.DialogCode.Accepted and self.cache is None
            return self.result()
    monkeypatch.setattr(hearing_panel, "HearingFitDialog", Form)
    monkeypatch.setattr(window, "_start_hearing_worker", lambda worker, action: starts.append((worker, action)))
    button = window.analytics_panel.hearing_csv_fit_button
    assert button.text() == "Einzel-CSV auswerten" and button.isEnabled()
    button.click()
    assert calls == [(None, {"audit_only": False, "single": True, "parent": window})]
    worker, action = starts[0]
    assert isinstance(worker, hearing_jobs.HearingCalibrationWorker)
    assert worker.directory == str(selected) and worker.cache is None
    assert worker.seed == -17 and worker.genres == ("Techno",) and worker.fit and action == "fit"
    assert (window._hearing_set_path, window._hearing_cache_path) == ordinary
    assert not window._hearing_native_active and not (selected / "missing.wav").exists()


@pytest.mark.gui
@pytest.mark.parametrize("schema", ["candidates", "three", "drama", "wrong", "duplicate", "audit"])
def test_single_csv_override_rejects_other_schemas_and_audit(qtbot, monkeypatch, tmp_path, schema):
    from tools import hoertest_server as hs
    window = _window(qtbot, monkeypatch)
    ordinary = _ordinary_state(window, tmp_path)
    selected = tmp_path / "override"
    selected.mkdir()
    headers = {"candidates": hs.BEWERTUNG_KANDIDATEN_SPALTEN, "three": hs.BEWERTUNG_DREINOTEN_SPALTEN,
               "drama": hs.DRAMATURGIE_BEWERTUNG_SPALTEN, "wrong": ("wrong", "header"),
               "duplicate": ("pair_id", "clip", "bewertung", "bewertung"), "audit": hs.BEWERTUNG_SPALTEN}
    (selected / "bewertung.csv").write_text(",".join(headers[schema]) + "\n")
    warnings = []
    monkeypatch.setattr(main.QMessageBox, "warning", lambda *args: warnings.append(args))
    def forbidden(*args, **kwargs):
        raise AssertionError("Falsches CSV-Schema/Audit-Override darf keinen Dialog oder Worker starten")
    monkeypatch.setattr(hearing_panel, "HearingFitDialog", forbidden)
    monkeypatch.setattr(hearing_jobs, "HearingCalibrationWorker", forbidden)
    window._fit_hearing_set(directory=selected, audit_only=schema == "audit")
    assert warnings
    assert (window._hearing_set_path, window._hearing_cache_path) == ordinary


@pytest.mark.gui
@pytest.mark.parametrize("override", [False, True])
@pytest.mark.parametrize("after", ["analysis", "playlist", "closing", "busy", "remote"])
def test_fit_modal_rechecks_lifecycle_before_worker(qtbot, monkeypatch, tmp_path, override, after):
    window = _window(qtbot, monkeypatch)
    ordinary = _ordinary_state(window, tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError("Nach Lifecycle-Wechsel darf kein Fit-Worker entstehen")
    class Form:
        def __init__(self, *args, **kwargs):
            self.cache, self.seed, self.genres = None, 1, ()
        def exec(self):
            assert window._hearing_native_active
            if after == "closing":
                window._close_pending = True
            elif after == "busy":
                window._hearing_worker = QThread(window)
            elif after == "remote":
                window._hearing_process = SimpleNamespace(state=lambda: main.QProcess.ProcessState.Running)
            else:
                window._set_run_state(main.RunState.AUDIO if after == "analysis" else main.RunState.PLAYLIST)
            return QDialog.DialogCode.Accepted
    monkeypatch.setattr(hearing_panel, "HearingFitDialog", Form)
    monkeypatch.setattr(hearing_jobs, "HearingCalibrationWorker", forbidden)
    try:
        window._fit_hearing_set(**({"directory": Path(ordinary[0])} if override else {}))
        assert (window._hearing_set_path, window._hearing_cache_path) == ordinary
        assert not window._hearing_native_active
    finally:
        window._hearing_worker = None
        window._hearing_process = None
        window._set_run_state(main.RunState.IDLE)


@pytest.mark.gui
@pytest.mark.parametrize("guard", ["closing", "busy", "native", "remote", "analysis"])
def test_single_csv_button_and_slot_guards(qtbot, monkeypatch, guard):
    window = _window(qtbot, monkeypatch)
    if guard == "closing":
        window._close_pending = True
    elif guard == "busy":
        window._hearing_worker = QThread(window)
    elif guard == "native":
        window._hearing_native_active = True
    elif guard == "remote":
        window._hearing_process = SimpleNamespace(state=lambda: main.QProcess.ProcessState.Running)
    else:
        window._set_run_state(main.RunState.AUDIO)
    def forbidden(*args, **kwargs):
        raise AssertionError("Gesperrter CSV-Einstieg darf keinen Picker oeffnen")
    monkeypatch.setattr(main.QFileDialog, "getExistingDirectory", forbidden)
    try:
        window._update_hearing_buttons()
        assert not window.analytics_panel.hearing_csv_fit_button.isEnabled()
        window._fit_hearing_csv_set()
    finally:
        window._hearing_worker = None
        window._hearing_process = None
        window._hearing_native_active = False
        window._set_run_state(main.RunState.IDLE)


@pytest.mark.gui
@pytest.mark.parametrize("guard", ["closing", "busy", "native", "remote"])
def test_proposal_modal_preselection_guard(qtbot, monkeypatch, tmp_path, guard):
    window = _window(qtbot, monkeypatch)
    ordinary = _ordinary_state(window, tmp_path)
    if guard == "closing":
        window._close_pending = True
    elif guard == "busy":
        window._hearing_worker = QThread(window)
    elif guard == "native":
        window._hearing_native_active = True
    else:
        window._hearing_process = SimpleNamespace(state=lambda: main.QProcess.ProcessState.Running)
    def forbidden(*args, **kwargs):
        raise AssertionError("Gesperrte Ergebnisansicht darf keinen Dialog/Apply-Worker erzeugen")
    monkeypatch.setattr(hearing_panel, "HearingCalibrationResultDialog", forbidden)
    monkeypatch.setattr(hearing_jobs, "HearingApplyWorker", forbidden)
    try:
        window._show_hearing_proposal({})
        assert (window._hearing_set_path, window._hearing_cache_path) == ordinary
    finally:
        window._hearing_worker = None
        window._hearing_process = None
        window._hearing_native_active = False


@pytest.mark.gui
@pytest.mark.parametrize("retry_origin", ["failed", "finished"])
@pytest.mark.parametrize("outcome", ["accept", "reject", "closing", "remote", "busy", "active", "exception"])
def test_proposal_modal_blocks_queued_server_and_rechecks_apply(qtbot, monkeypatch, tmp_path, retry_origin, outcome):
    window = _window(qtbot, monkeypatch)
    ordinary = _ordinary_state(window, tmp_path)
    proposal = {"test": "GUI routing only; no real apply"}
    queued, starts, constructed, button_states = [], [], [], []
    real_update = window._update_hearing_buttons
    def update():
        real_update()
        button_states.append((window._hearing_native_active, window.analytics_panel.hearing_server_button.isEnabled()))
    monkeypatch.setattr(window, "_update_hearing_buttons", update)
    monkeypatch.setattr(main.QTimer, "singleShot", lambda delay, callback: queued.append((delay, callback)))
    def forbidden(*args, **kwargs):
        raise AssertionError("Ergebnis-Modal muss Portpruefung/Prozessstart verhindern")
    monkeypatch.setattr(main.socket, "socket", forbidden)
    monkeypatch.setattr(window, "_start_hearing_worker", lambda worker, action: starts.append((worker, action)))
    process = SimpleNamespace(deleteLater=lambda: None)
    window._hearing_process = process
    window._hearing_port_attempts = 1
    window._hearing_server_stop_requested = False
    if retry_origin == "failed":
        window._hearing_server_failed(process)
    else:
        window._hearing_server_finished(process, exit_code=1)
    assert len(queued) == 1 and window._hearing_process is None
    class Form:
        def __init__(self, value, parent, cleanup_warning=""):
            constructed.append((value, parent, cleanup_warning))
        def exec(self):
            assert window._hearing_native_active and window._hearing_worker is None
            assert not window.analytics_panel.hearing_server_button.isEnabled()
            assert not window.analytics_panel.hearing_csv_fit_button.isEnabled()
            # Retry wurde vor dem Modal eingereiht und wird im Modal zugestellt.
            real_process_type = main.QProcess
            monkeypatch.setattr(main, "QProcess", forbidden)
            try:
                queued[0][1]()
            finally:
                monkeypatch.setattr(main, "QProcess", real_process_type)
            assert window._hearing_process is None and window._hearing_port_attempts == 1
            if outcome == "exception":
                raise RuntimeError("synthetic result-modal failure")
            if outcome == "closing":
                window._close_pending = True
            elif outcome == "remote":
                window._hearing_process = SimpleNamespace(state=lambda: main.QProcess.ProcessState.Running)
            elif outcome == "busy":
                window._hearing_worker = QThread(window)
            elif outcome == "active":
                window._set_run_state(main.RunState.PLAYLIST)
            return QDialog.DialogCode.Rejected if outcome == "reject" else QDialog.DialogCode.Accepted
    monkeypatch.setattr(hearing_panel, "HearingCalibrationResultDialog", Form)
    try:
        if outcome == "exception":
            with pytest.raises(RuntimeError, match="synthetic result-modal failure"):
                window._show_hearing_proposal(proposal, "owned temp retained")
        else:
            window._show_hearing_proposal(proposal, "owned temp retained")
        assert constructed == [(proposal, window, "owned temp retained")]
        assert not window._hearing_native_active
        assert button_states[0] == (True, False) and button_states[-1][0] is False
        if outcome == "accept":
            assert len(starts) == 1
            worker, action = starts[0]
            assert isinstance(worker, hearing_jobs.HearingApplyWorker) and action == "apply"
            assert worker.proposal == proposal
        else:
            assert not starts
        if outcome in {"accept", "reject", "exception"}:
            assert window.analytics_panel.hearing_server_button.isEnabled()
        else:
            assert not window.analytics_panel.hearing_csv_fit_button.isEnabled()
        assert (window._hearing_set_path, window._hearing_cache_path) == ordinary
    finally:
        window._hearing_worker = None
        window._hearing_process = None
        window._hearing_native_active = False
        window._set_run_state(main.RunState.IDLE)


@pytest.mark.gui
@pytest.mark.parametrize("cancelled", [False, True])
def test_failed_result_keeps_cleanup_rest_path_visible(qtbot, monkeypatch, tmp_path, cancelled):
    window = _window(qtbot, monkeypatch)
    ordinary = _ordinary_state(window, tmp_path)
    before = _fingerprints(Path(ordinary[0]))
    rest_path = tmp_path / ".blind.staging-retained"
    output = "Blindvorbereitung abgebrochen." if cancelled else "Blindvorbereitung fehlgeschlagen."
    cleanup_warning = f"Aufraeumen fehlgeschlagen; Restpfad: {rest_path}"
    warnings = []
    monkeypatch.setattr(main.QMessageBox, "warning", lambda *args: warnings.append(args))
    worker = QThread(window)
    window._hearing_worker = worker
    try:
        window._hearing_completed(
            {"ok": False, "cancelled": cancelled, "output": output,
             "cleanup_warning": cleanup_warning}, "blind", worker)
        message = window.analytics_panel.hearing_status.text()
        assert message == output + "\n" + cleanup_warning
        assert str(rest_path) in message and "Audio entfernt" not in message
        assert warnings == ([] if cancelled else [(window, "Hörtest", message)])
        assert (window._hearing_set_path, window._hearing_cache_path) == ordinary
        assert window._hearing_pending_discovery is None and window._hearing_pending_rating is None
        window._cleanup_hearing_worker(worker)
        assert window._hearing_worker is None
        assert window.analytics_panel.hearing_status.text() == message
        assert _fingerprints(Path(ordinary[0])) == before
        assert not rest_path.exists()
    finally:
        window._hearing_worker = None


@pytest.mark.gui
@pytest.mark.parametrize("retry_origin", ["failed", "finished"])
@pytest.mark.parametrize("guard", ["busy", "native", "closing"])
def test_queued_remote_retry_rechecks_worker_and_native_guard(qtbot, monkeypatch, tmp_path, retry_origin, guard):
    window = _window(qtbot, monkeypatch)
    ordinary = _ordinary_state(window, tmp_path)
    before = _fingerprints(Path(ordinary[0]))
    queued, deleted, warnings = [], [], []
    monkeypatch.setattr(main.QTimer, "singleShot", lambda delay, callback: queued.append((delay, callback)))
    monkeypatch.setattr(main.QMessageBox, "warning", lambda *args: warnings.append(args))
    def forbidden(*args, **kwargs):
        raise AssertionError("Gesperrter Retry darf weder Port sondieren noch Prozess erzeugen")
    monkeypatch.setattr(main.socket, "socket", forbidden)
    monkeypatch.setattr(main, "QProcess", forbidden)
    process = SimpleNamespace(deleteLater=lambda: deleted.append(True))
    window._hearing_process = process
    window._hearing_port_attempts = 1
    window._hearing_server_stop_requested = False
    if retry_origin == "failed":
        window._hearing_server_failed(process)
    else:
        window._hearing_server_finished(process, exit_code=1)
    assert deleted == [True] and window._hearing_process is None
    assert len(queued) == 1 and queued[0][0] == 150
    # Die Sperre entsteht erst nach dem Einreihen: der Callback muss neu pruefen.
    if guard == "busy":
        window._hearing_worker = QThread(window)
    elif guard == "native":
        window._hearing_native_active = True
    else:
        window._close_pending = True
    status = window.analytics_panel.hearing_status.text()
    try:
        queued[0][1]()
        assert window._hearing_process is None and window._hearing_port_attempts == 1
        assert not warnings and len(queued) == 1
        assert window.analytics_panel.hearing_status.text() == status
        assert (window._hearing_set_path, window._hearing_cache_path) == ordinary
        assert _fingerprints(Path(ordinary[0])) == before
    finally:
        window._hearing_worker = None
        window._hearing_native_active = False
