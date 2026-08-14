"""Direkte Tests fuer kritische Worker- und MainWindow-Vertragspfade."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QApplication

import main
from hpg_core.exporters import ExportReport
from hpg_core.models import Track


def test_resolve_transition_mix_points_prefers_plan_and_dj_values():
  plan = SimpleNamespace(mix_out_a=200.0, mix_in_b=16.0, overlap=32.0)
  transition = SimpleNamespace(plan=plan)
  assert main.resolve_transition_mix_points(transition) == (200.0, 16.0, 32.0)

  transition = SimpleNamespace(
    plan=None,
    dj_rec=SimpleNamespace(
      adjusted_mix_out_a=180.0,
      adjusted_mix_in_b=8.0,
      overlap_seconds=24.0,
    ),
    from_track=Track(
      filePath="C:/a.wav", fileName="a.wav", mix_out_point=210.0
    ),
    to_track=Track(filePath="C:/b.wav", fileName="b.wav", mix_in_point=12.0),
    overlap=16.0,
  )
  assert main.resolve_transition_mix_points(transition) == (180.0, 8.0, 24.0)


def test_ai_analysis_worker_reports_missing_provider():
  worker = main.AIAnalysisWorker([Track(filePath="C:/a.wav", fileName="a.wav")])
  failures = []
  progress = []
  worker.failed.connect(failures.append)
  worker.progress.connect(lambda current, total: progress.append((current, total)))
  worker._ensure_ready = Mock(return_value=False)

  worker.run()

  assert failures == ["Kein einsatzbereiter KI-Provider oder kein Modell verfuegbar."]
  assert progress[-1] == (1, 1)


def test_ai_analysis_worker_cancel_and_exception(monkeypatch):
  track = Track(filePath="C:/a.wav", fileName="a.wav")
  worker = main.AIAnalysisWorker(
    [track], provider="Ollama", model="model", base_url="http://local"
  )
  worker.request_cancel()
  emitted = []
  worker.progress.connect(lambda current, total: emitted.append((current, total)))
  worker.run()
  assert emitted[-1] == (1, 1)

  worker = main.AIAnalysisWorker(
    [track], provider="Ollama", model="model", base_url="http://local"
  )
  monkeypatch.setattr(
    "hpg_core.ai_engine.ai_metadata_matches",
    lambda *args: (_ for _ in ()).throw(RuntimeError("schema crash")),
  )
  failures = []
  worker.failed.connect(failures.append)
  worker.run()
  assert failures == ["KI-Verarbeitung gestoppt: schema crash"]


def test_detect_worker_emits_success_and_failure(monkeypatch):
  status = SimpleNamespace(running=True)
  monkeypatch.setattr(
    "hpg_core.ai_launcher.detect_and_start", lambda **kwargs: status
  )
  worker = main.AIDetectWorker("Ollama", "model")
  emitted = []
  worker.detected.connect(emitted.append)
  worker.run()
  assert emitted == [status]

  monkeypatch.setattr(
    "hpg_core.ai_launcher.detect_and_start",
    lambda **kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
  )
  worker = main.AIDetectWorker()
  emitted = []
  worker.detected.connect(emitted.append)
  worker.run()
  assert emitted == [None]


class _Response:
  def __init__(self, payload, error=None):
    self.payload = payload
    self.error = error

  def raise_for_status(self):
    if self.error:
      raise self.error

  def json(self):
    return self.payload


def test_ai_test_worker_success_empty_and_error(monkeypatch):
  monkeypatch.setattr(
    requests,
    "post",
    lambda *args, **kwargs: _Response(
      {"model": "actual", "choices": [{"message": {"content": " OK "}}]}
    ),
  )
  worker = main.AITestWorker("Ollama", "requested", "http://local")
  emitted = []
  worker.test_finished.connect(lambda *args: emitted.append(args))
  worker.run()
  assert emitted[0][0:3] == (True, "OK", "actual")

  monkeypatch.setattr(requests, "post", lambda *args, **kwargs: _Response({}))
  worker = main.AITestWorker("LM Studio", "model", "")
  emitted = []
  worker.test_finished.connect(lambda *args: emitted.append(args))
  worker.run()
  assert emitted[0][0] is False
  assert "choices" in emitted[0][1]

  monkeypatch.setattr(
    requests,
    "post",
    lambda *args, **kwargs: (_ for _ in ()).throw(requests.ConnectionError("down")),
  )
  worker = main.AITestWorker("Ollama", "model", "")
  emitted = []
  worker.test_finished.connect(lambda *args: emitted.append(args))
  worker.run()
  assert emitted[0][0] is False
  assert "down" in emitted[0][1]


@pytest.mark.parametrize("outcome", [True, False])
def test_ai_pull_worker_reports_outcome(monkeypatch, outcome):
  # HPG-003: ollama_pull akzeptiert jetzt cancel_check (kooperativer Abbruch)
  monkeypatch.setattr(
    "hpg_core.ai_launcher.ollama_pull",
    lambda _model, cancel_check=None: outcome,
  )
  worker = main.AIPullWorker("model")
  emitted = []
  worker.pull_finished.connect(lambda *args: emitted.append(args))

  worker.run()

  assert emitted[0][0] is outcome


def test_ai_pull_worker_real_qthread_lifecycle(qtbot, monkeypatch):
  monkeypatch.setattr(
    "hpg_core.ai_launcher.ollama_pull",
    lambda _model, cancel_check=None: True,
  )
  worker = main.AIPullWorker("model")

  with qtbot.waitSignal(worker.pull_finished, timeout=2000) as signal:
    worker.start()

  assert signal.args[0] is True
  assert worker.wait(1000)


def test_dependency_check_worker_keeps_http_probe_out_of_mainwindow(monkeypatch):
  calls = []

  def fake_get(*args, **kwargs):
    calls.append((args, kwargs))
    return SimpleNamespace()

  monkeypatch.setattr(requests, "get", fake_get)
  worker = main.DependencyCheckWorker(
    "Ollama", "http://localhost:11434/v1/chat/completions"
  )
  emitted = []
  worker.checked.connect(lambda *args: emitted.append(args))

  worker.run()

  assert emitted and emitted[0][1] is True
  assert calls[0][1]["timeout"] == (0.3, 0.3)


def test_render_executor_terminates_children_before_shutdown():
  events = []
  process = Mock()
  process.terminate.side_effect = lambda: events.append("terminate")
  executor = SimpleNamespace(_processes={1: process}, shutdown=Mock())
  executor.shutdown.side_effect = lambda **kwargs: events.append("shutdown")

  main.TransitionRenderWorker._terminate_executor(executor)

  process.terminate.assert_called_once_with()
  executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)
  assert events == ["terminate", "shutdown"]


def test_analysis_worker_empty_folder(tmp_path):
  worker = main.AnalysisWorker(str(tmp_path))
  finished = []
  statuses = []
  worker.analysis_done.connect(lambda tracks, quality: finished.append((tracks, quality)))
  worker.status_update.connect(statuses.append)

  worker.run()

  assert finished == [([], {})]
  assert any("No audio files" in status for status in statuses)


def test_analysis_worker_success_and_analyzer_failure(tmp_path, monkeypatch):
  (tmp_path / "track.wav").write_bytes(b"fixture")
  track = Track(filePath=str(tmp_path / "track.wav"), fileName="track.wav")

  class SuccessfulAnalyzer:
    def analyze_files(self, files, progress_callback, **kwargs):
      progress_callback(1, 1, "done")
      return [track]

  monkeypatch.setattr(main, "ParallelAnalyzer", SuccessfulAnalyzer)
  monkeypatch.setattr(main, "apply_resource_limits", lambda tracks: tracks)
  worker = main.AnalysisWorker(str(tmp_path))
  finished = []
  worker.analysis_done.connect(lambda tracks, quality: finished.append((tracks, quality)))
  worker.run()
  assert finished == [([track], {})]

  class FailingAnalyzer:
    def analyze_files(self, files, progress_callback, **kwargs):
      raise RuntimeError("decoder failed")

  reporter = Mock()
  monkeypatch.setattr(main, "ParallelAnalyzer", FailingAnalyzer)
  monkeypatch.setattr(main, "get_error_reporter", lambda: reporter)
  worker = main.AnalysisWorker(str(tmp_path))
  finished = []
  worker.analysis_done.connect(lambda tracks, quality: finished.append((tracks, quality)))
  worker.run()
  assert finished == [([], {})]
  reporter.log_error.assert_called_once()


def test_analysis_worker_cancel_during_scan(tmp_path):
  (tmp_path / "track.wav").write_bytes(b"fixture")
  worker = main.AnalysisWorker(str(tmp_path))
  worker.request_cancel()
  finished = []
  worker.analysis_done.connect(lambda tracks, quality: finished.append((tracks, quality)))

  worker.run()

  assert finished == [([], {})]


def _window(qtbot, monkeypatch):
  monkeypatch.setattr(main.MainWindow, "check_dependencies_and_warn", lambda self: None)
  window = main.MainWindow()
  qtbot.addWidget(window)
  return window


def test_mainwindow_terminal_state_and_empty_analysis(qtbot, monkeypatch):
  window = _window(qtbot, monkeypatch)
  window._set_run_state(main.RunState.AUDIO)
  window._finish_run(main.RunState.ERROR, "failed")
  assert window.run_state == main.RunState.ERROR
  assert window.library_panel.start_button.isEnabled()

  window._set_run_state(main.RunState.AUDIO)
  window.analysis_finished([], {})
  assert window.run_state == main.RunState.ERROR
  assert "no results" in window.status_bar.status_label.text().lower()


def test_shortcuts_use_window_scoped_ctrl_navigation(qtbot, monkeypatch):
  window = _window(qtbot, monkeypatch)
  shortcuts = {
    shortcut.key().toString(): shortcut.context()
    for shortcut in window.findChildren(QShortcut)
  }

  assert all(f"Ctrl+{index}" in shortcuts for index in range(1, 6))
  assert all(f"{index}" not in shortcuts for index in range(1, 6))
  assert all(
    shortcuts[f"Ctrl+{index}"]
    == main.Qt.ShortcutContext.WindowShortcut
    for index in range(1, 6)
  )


def test_cue_heuristic_checkbox_is_not_exposed(qtbot):
  panel = main.LibraryPanel()
  qtbot.addWidget(panel)

  assert not hasattr(panel, "force_custom_cues")
  assert not hasattr(panel, "_on_force_cues_changed")


def test_preview_error_shows_message_in_widget_and_allows_retry(qtbot):
  transition = SimpleNamespace(
    from_track=Track(filePath="C:/a.wav", fileName="a.wav"),
    to_track=Track(filePath="C:/b.wav", fileName="b.wav"),
    plan=SimpleNamespace(mix_out_a=30.0, mix_in_b=0.0, overlap=8.0),
    transition_type="blend",
  )
  panel = main.MixTipsPanel()
  qtbot.addWidget(panel)
  widget = main.TransitionPreviewWidget(0, transition, panel)
  button = main.QPushButton("laufend")
  panel._preview_widgets[0] = widget
  panel._preview_buttons[0] = button

  panel._on_clip_error(0, "decoder")

  # Widget bleibt stehen und zeigt den Fehler an (set_error ist verdrahtet)
  assert panel._preview_widgets[0] is widget
  assert widget._error_msg == "decoder"
  assert not widget._play_btn.isEnabled()
  assert widget._time_label.text() == "Fehler"
  assert "⚠" in widget._title_label.text()
  assert widget._title_label.toolTip() == "decoder"
  assert "decoder" in widget._waveform._placeholder
  assert button.isEnabled()
  assert "erneut" in button.text()

  # Zweiter Fehlschlag haengt kein zweites ⚠ an
  panel._on_clip_error(0, "decoder")
  assert widget._title_label.text().count("⚠") == 1

  widget.deleteLater()
  button.deleteLater()


def test_ai_auxiliary_worker_guards_and_cleanup(qtbot):
  widget = main.AdvancedParametersWidget()
  qtbot.addWidget(widget)
  stale = Mock()
  current = Mock()
  widget._test_worker = current
  widget.test_ai_btn.setEnabled(False)

  widget._on_test_finished(False, "stale", "model", 0.1, stale)
  assert not widget.test_ai_btn.isEnabled()

  widget._cleanup_ai_worker("_test_worker", current)

  current.deleteLater.assert_called_once_with()
  assert widget._test_worker is None


def test_mainwindow_m3u8_and_partial_xml_export(qtbot, monkeypatch, tmp_path):
  window = _window(qtbot, monkeypatch)
  window.playlist = [Track(filePath="C:/a.wav", fileName="a.wav")]
  window.current_playlist_mode = "Harmonic Flow"
  m3u8_exporter = Mock()
  # Beide Exporter liefern denselben Typ: ExportReport (nicht None, nicht dict).
  m3u8_exporter.export.return_value = ExportReport(
    status="success",
    output_path=str(tmp_path / "set.m3u8"),
    tracks_written=1,
    cues_written=0,
    beatgrids_written=0,
  )
  monkeypatch.setattr(main, "M3U8Exporter", lambda: m3u8_exporter)
  info = Mock()
  warning = Mock()
  monkeypatch.setattr(main.QMessageBox, "information", info)
  monkeypatch.setattr(main.QMessageBox, "warning", warning)
  window._export_m3u8(str(tmp_path / "set.m3u8"))
  m3u8_exporter.export.assert_called_once()
  info.assert_called_once()

  report = SimpleNamespace(
    status="partial",
    tracks_written=1,
    cues_written=0,
    beatgrids_written=0,
    errors=["cue rejected"],
  )
  xml_exporter = Mock()
  xml_exporter.export.return_value = report
  monkeypatch.setattr(main, "RekordboxXMLExporter", lambda: xml_exporter)
  window._export_rekordbox_xml(str(tmp_path / "set.xml"))
  warning.assert_called_once()


def test_restart_and_close_without_workers(qtbot, monkeypatch):
  window = _window(qtbot, monkeypatch)
  window.playlist = [Track(filePath="C:/a.wav", fileName="a.wav")]
  window.restart_app()
  assert window.playlist == []
  event = Mock()
  window.closeEvent(event)
  event.accept.assert_called_once()


@pytest.mark.slow
@pytest.mark.gui
def test_mainwindow_repeated_widget_start_close_smoke(qapp, monkeypatch):
  """Prueft wiederholtes Erzeugen und Schliessen von Fenster und Audioplayer."""
  monkeypatch.setattr(main.MainWindow, "check_dependencies_and_warn", lambda self: None)
  transition = SimpleNamespace(
    from_track=Track(filePath="C:/a.wav", fileName="a.wav"),
    to_track=Track(filePath="C:/b.wav", fileName="b.wav"),
    plan=SimpleNamespace(mix_out_a=30.0, mix_in_b=0.0, overlap=8.0),
    transition_type="blend",
  )

  for _ in range(30):
    window = main.MainWindow()
    assert window.run_state == main.RunState.IDLE
    assert window.library_panel is not None
    preview = main.TransitionPreviewWidget(0, transition, window)
    assert preview._player is not None
    assert preview._audio_out is not None
    window.show()
    QApplication.processEvents()
    window.close()
    window.deleteLater()
    QApplication.sendPostedEvents()
    QApplication.processEvents()
