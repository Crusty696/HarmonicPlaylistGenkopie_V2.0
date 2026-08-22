"""Direkte Tests fuer kritische Worker- und MainWindow-Vertragspfade."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from PyQt6.QtGui import QShortcut
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


def test_ai_analysis_worker_persists_metadata_off_gui_thread(monkeypatch):
  track = Track(filePath="C:/a.wav", fileName="a.wav")
  metadata = {"moods": ["driving"], "sub_genre": "Peak Techno"}
  cached = []
  monkeypatch.setattr(
    "hpg_core.ai_engine.ai_metadata_matches", lambda *args: False
  )
  monkeypatch.setattr(
    "hpg_core.ai_engine.fetch_ai_analysis", lambda *args, **kwargs: metadata
  )
  monkeypatch.setattr("hpg_core.caching.generate_cache_key", lambda *args: "key")
  monkeypatch.setattr(
    "hpg_core.caching.cache_track", lambda key, value: cached.append((key, value))
  )
  worker = main.AIAnalysisWorker(
    [track], provider="Ollama", model="model", base_url="http://local"
  )

  worker.run()

  assert track.ai_metadata == metadata
  assert cached == [("key", track)]


def test_detect_worker_passes_cooperative_cancel(monkeypatch):
  captured = {}

  def detect_and_start(**kwargs):
    captured.update(kwargs)
    return None

  monkeypatch.setattr("hpg_core.ai_launcher.detect_and_start", detect_and_start)
  worker = main.AIDetectWorker("Ollama", "model")
  worker.run()

  assert captured["cancel_check"] == worker.isInterruptionRequested


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


def test_render_worker_reports_temp_directory_failure(monkeypatch):
  worker = main.TransitionRenderWorker([Mock()])
  errors = []
  worker.clip_error.connect(lambda *args: errors.append(args))
  monkeypatch.setattr(
    main.tempfile, "mkdtemp", Mock(side_effect=OSError("disk full"))
  )

  worker.run()

  assert errors and errors[0][0] == 0
  assert "disk full" in errors[0][1]


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


def test_final_generation_reuses_one_adjacent_metrics_snapshot(qtbot, monkeypatch):
  window = _window(qtbot, monkeypatch)
  tracks = [
    Track(filePath="C:/a.wav", fileName="a.wav", bpm=128.0),
    Track(filePath="C:/b.wav", fileName="b.wav", bpm=129.0),
  ]
  metrics = [Mock()]
  quality = {"overall_score": 0.8}
  compute_metrics = Mock(return_value=metrics)
  calculate_quality = Mock(return_value=quality)
  recommendations = Mock(return_value=[])
  monkeypatch.setattr("hpg_core.playlist.generate_playlist", lambda *a, **k: tracks)
  monkeypatch.setattr(
    "hpg_core.playlist.compute_adjacent_transition_metrics", compute_metrics
  )
  monkeypatch.setattr(
    "hpg_core.playlist.calculate_playlist_quality", calculate_quality
  )
  monkeypatch.setattr(
    "hpg_core.playlist.compute_transition_recommendations", recommendations
  )
  window.analyzed_raw_tracks = tracks
  window._run_settings = {
    "folder": "C:/",
    "strategy": "Harmonic Flow",
    "bpm_tolerance": 3.0,
    "advanced_params": {"ai_enabled": False},
  }

  window.on_ai_worker_finished(ai_completed=False, finalize=True)

  compute_metrics.assert_called_once()
  assert calculate_quality.call_args.kwargs["transition_metrics"] is metrics
  assert recommendations.call_args.kwargs["transition_metrics"] is metrics


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


def _dependency_stub():
  """Minimales MainWindow-Double: _on_dependencies_checked fasst nur
  _dependency_worker und status_bar an."""
  recorded = {"status": None, "tooltip": None}
  status_bar = SimpleNamespace(
    set_status=lambda text: recorded.__setitem__("status", text),
    setToolTip=lambda text: recorded.__setitem__("tooltip", text),
    setStyleSheet=lambda text: None,
  )
  window = SimpleNamespace(_dependency_worker=None, status_bar=status_bar)
  return window, recorded


def test_running_rekordbox_produces_stale_metadata_warning():
  window, recorded = _dependency_stub()

  main.MainWindow._on_dependencies_checked(
    window, True, True, True, "LM Studio"
  )

  assert recorded["status"] is not None
  assert "Rekordbox laeuft" in recorded["tooltip"]
  assert "schliessen" in recorded["tooltip"]


def test_closed_rekordbox_produces_no_warning():
  window, recorded = _dependency_stub()

  main.MainWindow._on_dependencies_checked(
    window, True, True, False, "LM Studio"
  )

  assert recorded["status"] is None
  assert recorded["tooltip"] is None


def test_dependency_worker_emits_rekordbox_state(monkeypatch):
  monkeypatch.setattr(requests, "get", lambda *a, **k: SimpleNamespace())
  monkeypatch.setattr(
    "hpg_core.rekordbox_importer.is_rekordbox_running", lambda: True
  )
  worker = main.DependencyCheckWorker("LM Studio", "http://localhost:1234/v1")
  emitted = []
  worker.checked.connect(lambda *args: emitted.append(args))

  worker.run()

  assert emitted and emitted[0][2] is True


def test_real_window_shows_rekordbox_warning_end_to_end(qtbot, monkeypatch):
  """Vollstaendige Kette: Worker-Signal (3 Argumente) -> Lambda -> Handler ->
  Statuszeile. Faengt Signaturbrueche, die Unit-Doubles durchlassen."""
  # Original sichern, bevor _window() die Methode fuer den Aufbau stilllegt.
  check = main.MainWindow.check_dependencies_and_warn
  window = _window(qtbot, monkeypatch)

  monkeypatch.setattr(requests, "get", lambda *a, **k: SimpleNamespace())
  monkeypatch.setattr(
    "hpg_core.rekordbox_importer.is_rekordbox_running", lambda: True
  )
  check(window)

  qtbot.waitUntil(
    lambda: "Rekordbox laeuft" in window.status_bar.toolTip(), timeout=5000
  )


# --- Rekordbox-Abdeckung nach dem Lauf --------------------------------------


def _coverage(**kwargs):
  from hpg_core.rekordbox_importer import RekordboxCoverage

  defaults = dict(available=True, total=34, with_analysis=15)
  defaults.update(kwargs)
  return RekordboxCoverage(**defaults)


def test_hint_survives_later_status_updates(qtbot, monkeypatch):
  """Der Befund darf nicht von 'Complete — N tracks' ueberschrieben werden."""
  window = _window(qtbot, monkeypatch)
  window.status_bar.set_hint("Rekordbox: 19/34 ohne Daten", "Details")

  window.status_bar.set_status("Complete — 34 tracks, Quality 82%")

  # isVisible() ist False, solange das Fenster selbst nicht gezeigt wird —
  # isHidden() prueft den gesetzten Zustand statt der Bildschirmsichtbarkeit.
  assert not window.status_bar.hint_label.isHidden()
  assert "19/34" in window.status_bar.hint_label.text()
  assert window.status_bar.status_label.text().startswith("Complete")


def test_unanalyzed_collection_tracks_produce_hint(qtbot, monkeypatch):
  window = _window(qtbot, monkeypatch)

  window._on_rekordbox_coverage(
    _coverage(without_analysis=19, examples_without_analysis=["Antinomy.aiff"])
  )

  assert not window.status_bar.hint_label.isHidden()
  assert "19/34" in window.status_bar.hint_label.text()
  tooltip = window.status_bar.hint_label.toolTip()
  assert "nicht analysiert" in tooltip
  assert "Antinomy.aiff" in tooltip


def test_ambiguous_records_produce_hint(qtbot, monkeypatch):
  window = _window(qtbot, monkeypatch)

  window._on_rekordbox_coverage(
    _coverage(ambiguous=2, examples_ambiguous=["Doppelt.aiff"])
  )

  assert "mehrdeutige" in window.status_bar.hint_label.toolTip()
  assert "Doppelt.aiff" in window.status_bar.hint_label.toolTip()


def test_tracks_outside_collection_are_not_a_finding(qtbot, monkeypatch):
  """497 fremde Tracks sind normal — dafuer darf keine Warnung erscheinen."""
  window = _window(qtbot, monkeypatch)

  window._on_rekordbox_coverage(
    _coverage(total=1400, with_analysis=903, not_in_collection=497)
  )

  assert window.status_bar.hint_label.isHidden()


def test_no_hint_without_rekordbox(qtbot, monkeypatch):
  window = _window(qtbot, monkeypatch)
  window._on_rekordbox_coverage(
    _coverage(available=False, total=0, with_analysis=0, without_analysis=0)
  )
  assert window.status_bar.hint_label.isHidden()


def test_worker_emits_coverage_for_analyzed_paths(monkeypatch, tmp_path):
  captured = {}

  def fake_summarize(paths):
    captured["paths"] = list(paths)
    return _coverage(without_analysis=19)

  monkeypatch.setattr(
    "hpg_core.rekordbox_importer.get_rekordbox_importer",
    lambda: SimpleNamespace(summarize_coverage=fake_summarize),
  )
  worker = main.AnalysisWorker(str(tmp_path))
  emitted = []
  worker.rekordbox_coverage.connect(emitted.append)

  worker._report_rekordbox_coverage(
    [Track(filePath="C:/x/a.wav", fileName="a.wav")]
  )

  assert captured["paths"] == ["C:/x/a.wav"]
  assert emitted and emitted[0].without_analysis == 19


def test_coverage_failure_never_breaks_a_finished_run(monkeypatch, tmp_path):
  """Ein Diagnose-Fehler darf ein fertiges Analyseergebnis nicht kippen."""
  def boom():
    raise RuntimeError("DB weg")

  monkeypatch.setattr(
    "hpg_core.rekordbox_importer.get_rekordbox_importer", boom
  )
  worker = main.AnalysisWorker(str(tmp_path))
  emitted = []
  worker.rekordbox_coverage.connect(emitted.append)

  worker._report_rekordbox_coverage(
    [Track(filePath="C:/x/a.wav", fileName="a.wav")]
  )

  assert emitted == []



# --- Kandidaten in der GUI (Teil 4): reine Helfer ohne Widgets ----------------

def test_kandidat_teilwerte_kurzform():
  from main import kandidat_teilwerte_kurz
  txt = kandidat_teilwerte_kurz({"harmonic": 0.75, "bpm": 1.0, "energy": 0.98, "genre": 1.0, "groove": 0.83,
                                 "bass": 0.6, "timbre": 0.72, "mood": 0.99, "loudness": None, "structure": 0.07})
  assert txt == "H .75 T 1.0 E .98 G 1.0 Gr .83 B .60 K .72 S .99 L - St .07"
  assert kandidat_teilwerte_kurz({}) == "H - T - E - G - Gr - B - K - S - L - St -"


def test_mixpunkt_quelle_aus_empfehlungen():
  from types import SimpleNamespace
  from main import mixpunkte_fuer_tabelle
  recs = [SimpleNamespace(plan=SimpleNamespace(mix_out_a=192.0, mix_in_b=82.3), kandidat_aktiv=1)]
  t0 = SimpleNamespace(mix_in_point=60.0, mix_out_point=200.0)
  t1 = SimpleNamespace(mix_in_point=50.0, mix_out_point=210.0)
  assert mixpunkte_fuer_tabelle(0, t0, recs) == (60.0, "Analyse", 192.0, "Kandidat Rang 1")
  assert mixpunkte_fuer_tabelle(1, t1, recs) == (82.3, "Kandidat Rang 1", 210.0, "Analyse")
  assert mixpunkte_fuer_tabelle(1, t1, []) == (50.0, "Analyse", 210.0, "Analyse")
  # kandidat_aktiv 0 -> Track-Werte
  recs0 = [SimpleNamespace(plan=SimpleNamespace(mix_out_a=1.0, mix_in_b=2.0), kandidat_aktiv=0)]
  assert mixpunkte_fuer_tabelle(0, t0, recs0) == (60.0, "Analyse", 200.0, "Analyse")



# --- Kandidatentabelle im MixTipsPanel + Wahl im MainWindow (Teil 4, qtbot) ---

def _rec_mit_kandidaten(index=0):
  from hpg_core.playlist import TransitionPlan, TransitionRecommendation
  a = Track(filePath="C:/a.wav", fileName="a.wav", bpm=140.0)
  b = Track(filePath="C:/b.wav", fileName="b.wav", bpm=140.0)
  kand = [
    {"rang": 1, "t_out": 164.6, "t_in": 82.3, "blend_bars": 16, "overlap_sec": 27.4, "score": 0.71,
     "teilwerte": {"harmonic": 0.75, "bpm": 1.0}, "flags": {"bass_swap_pflicht": False},
     "begruendung": "Harmonie stark; Blende 16 Takte", "out_a": {"schema": ["pssi_phrase"]},
     "in_b": {"schema": ["auto_cue"]}},
    {"rang": 2, "t_out": 164.6, "t_in": 82.3, "blend_bars": 32, "overlap_sec": 54.9, "score": 0.71,
     "teilwerte": {"harmonic": 0.75, "bpm": 1.0}, "flags": {"bass_swap_pflicht": False},
     "begruendung": "Harmonie stark; Blende 32 Takte", "out_a": {"schema": ["pssi_phrase"]},
     "in_b": {"schema": ["auto_cue"]}},
  ]
  plan = TransitionPlan(mix_out_a=164.6, mix_in_b=82.3, fade_out_start=164.6, fade_out_end=192.0,
                        overlap=27.4, transition_type="pro_eq_swap")
  return TransitionRecommendation(
    index=index, from_track=a, to_track=b, fade_out_start=164.6, fade_out_end=192.0,
    fade_in_start=82.3, mix_entry=82.3, overlap=27.4, bpm_delta=0.0, energy_delta=0,
    compatibility_score=71, risk_level="low", notes="", transition_type="pro_eq_swap",
    dj_rec=None, plan=plan, kandidaten=kand, kandidat_aktiv=1)


def test_mix_tips_panel_zeigt_kandidatentabelle_und_sendet_wahl(qtbot):
  panel = main.MixTipsPanel()
  qtbot.addWidget(panel)
  panel.set_recommendations([_rec_mit_kandidaten()])
  assert 0 in panel._kandidaten_tabellen
  tabelle = panel._kandidaten_tabellen[0]
  assert tabelle.rowCount() == 2 and tabelle.columnCount() == len(panel.KANDIDATEN_SPALTEN)
  assert [tabelle.item(0, c).text() for c in range(3)] == ["1", "164.6 s", "82.3 s"]
  assert tabelle.item(0, 7).text().startswith("Harmonie stark")      # Begruendung sichtbar
  assert [r.row() for r in tabelle.selectionModel().selectedRows()] == [0]   # aktive Zeile
  empfangen = []
  panel.candidate_chosen.connect(lambda i, r: empfangen.append((i, r)))
  tabelle.selectRow(1)
  assert empfangen == [(0, 2)]


def test_on_candidate_chosen_merkt_wahl_und_rechnet_neu(qtbot, monkeypatch, tmp_path):
  from hpg_core import candidate_choices as cc
  monkeypatch.setenv("HPG_CANDIDATE_CHOICES_FILE", str(tmp_path / "choices.json"))
  cc.reset_cache()
  window = _window(qtbot, monkeypatch)
  rec = _rec_mit_kandidaten()
  window.playlist = [rec.from_track, rec.to_track]
  window.playlist_panel.playlist = window.playlist
  window.playlist_panel.transition_recommendations = [rec]
  aufrufe = {"berechne": 0, "verteile": 0, "verworfen": []}
  monkeypatch.setattr(window, "_berechne_uebergaenge",
                      lambda bpm, ctx: aufrufe.__setitem__("berechne", aufrufe["berechne"] + 1) or (None, {}, [rec]))
  monkeypatch.setattr(window, "_verteile_uebergaenge",
                      lambda plan, bpm, ctx: aufrufe.__setitem__("verteile", aufrufe["verteile"] + 1))
  monkeypatch.setattr(window.mix_tips_panel, "verwerfe_preview", lambda i: aufrufe["verworfen"].append(i))
  window._on_candidate_chosen(0, 2)
  w = cc.hole("C:/a.wav", "C:/b.wav")
  assert w and w["blend_bars"] == 32 and w["t_out"] == 164.6
  assert aufrufe == {"berechne": 1, "verteile": 1, "verworfen": [0]}
  cc.reset_cache()


def test_app_bpm_default_ist_zwei(qtbot, monkeypatch):
  window = _window(qtbot, monkeypatch)
  assert window.library_panel.bpm_tolerance_slider.value() == 2
  assert window.library_panel.bpm_value_label.text() == "\u00b12"
  assert window.current_bpm_tolerance == 2.0
  assert window.playlist_panel.bpm_tolerance == 2.0
