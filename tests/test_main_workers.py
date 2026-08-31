"""Direkte Tests fuer kritische Worker- und MainWindow-Vertragspfade."""

import json
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from PyQt6.QtCore import QModelIndex, QSettings, QThread, QTimer
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


def test_sparse_timeline_plaene_behalten_paarindex():
  plan = SimpleNamespace(mix_out_a=190.0, mix_in_b=80.0)
  tracks = [object(), object(), object()]

  plans = main.transition_plans_fuer_timeline(
    tracks, [SimpleNamespace(index=1, plan=plan)]
  )

  assert plans == [None, plan]


def test_zeitformat_traegt_hundertstel_ueber_minutengrenze():
  assert main.format_seconds_centiseconds(0.0) == "00:00.00"
  assert main.format_seconds_centiseconds(59.999) == "01:00.00"
  assert main.format_seconds_centiseconds(61.234) == "01:01.23"
  assert main.format_mix_point_display(59.999, 8) == "01:00.00 (8 bars)"


def test_timeline_panel_zeigt_planstatus_overlap_und_praezision(qtbot):
  panel = main.TimelinePanel()
  qtbot.addWidget(panel)
  tracks = [
    Track(filePath="C:/a.wav", fileName="a.wav", title="A", duration=100.0),
    Track(filePath="C:/b.wav", fileName="b.wav", title="B", duration=100.0),
    Track(filePath="C:/c.wav", fileName="c.wav", title="C", duration=100.0),
  ]
  plan = SimpleNamespace(mix_out_a=59.999, mix_in_b=10.0, overlap=12.345)
  rec = SimpleNamespace(index=0, plan=plan)

  panel.set_timeline(tracks, [rec])

  text = panel.text_edit.toPlainText()
  assert "01:00.00" in text
  assert "12.35s" in text
  assert "UNGEPLANT" in text
  assert "—" in text


def test_timeline_panel_meldet_ungueltige_kante_ohne_fallback(
  qtbot, monkeypatch
):
  reporter = Mock()
  monkeypatch.setattr(main, "get_error_reporter", lambda: reporter)
  panel = main.TimelinePanel()
  qtbot.addWidget(panel)
  tracks = [
    Track(filePath="C:/a.wav", fileName="a.wav", title="A", duration=100.0),
    Track(filePath="C:/b.wav", fileName="b.wav", title="B", duration=100.0),
  ]
  invalid = SimpleNamespace(
    index=0,
    plan=SimpleNamespace(mix_out_a=95.0, mix_in_b=10.0, overlap=10.0),
  )

  panel.set_timeline(tracks, [invalid])

  text = panel.text_edit.toPlainText()
  assert "Timeline ungültig" in text
  assert "Kante 1->2" in text
  reporter.log_error.assert_called_once()


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
  assert emitted == []

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


def test_ai_analysis_worker_provider_setup_cancel_is_silent(monkeypatch):
  worker = main.AIAnalysisWorker(
    [Track(filePath="C:/a.wav", fileName="a.wav")],
    provider="Ollama",
    model="model",
  )

  def detect_and_start(**_kwargs):
    worker.request_cancel()
    raise InterruptedError("abgebrochen")

  monkeypatch.setattr("hpg_core.ai_launcher.detect_and_start", detect_and_start)
  failures = []
  progress = []
  worker.failed.connect(failures.append)
  worker.progress.connect(lambda current, total: progress.append((current, total)))

  worker.run()

  assert failures == []
  assert progress == []


def test_ai_analysis_worker_cancel_after_response_discards_result(monkeypatch):
  track = Track(filePath="C:/a.wav", fileName="a.wav")
  worker = main.AIAnalysisWorker(
    [track], provider="Ollama", model="model", base_url="http://local"
  )
  metadata = {"moods": ["driving"], "sub_genre": "Peak Techno"}

  def fetch(*_args, **_kwargs):
    worker.request_cancel()
    return metadata

  monkeypatch.setattr("hpg_core.ai_engine.ai_metadata_matches", lambda *_args: False)
  monkeypatch.setattr("hpg_core.ai_engine.fetch_ai_analysis", fetch)
  failures = []
  finished = []
  progress = []
  worker.failed.connect(failures.append)
  worker.ai_finished.connect(lambda *args: finished.append(args))
  worker.progress.connect(lambda current, total: progress.append((current, total)))

  worker.run()

  assert failures == []
  assert finished == []
  assert progress == [(0, 1)]
  assert track.ai_metadata == {}


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
    "hpg_core.caching.merge_cached_ai_metadata",
    lambda key, path, value: cached.append((key, path, value)) or True,
  )
  worker = main.AIAnalysisWorker(
    [track], provider="Ollama", model="model", base_url="http://local"
  )
  finished = []
  worker.ai_finished.connect(lambda *args: finished.append(args))

  worker.run()

  assert track.ai_metadata == metadata
  assert cached == [("key", track.filePath, metadata)]
  assert finished == [(track.filePath, metadata)]


@pytest.mark.parametrize("merge_result", [False, None])
def test_ai_analysis_worker_publiziert_nicht_bei_unbestaetigter_persistenz(
  monkeypatch, merge_result,
):
  track = Track(filePath="C:/a.wav", fileName="a.wav")
  metadata = {"moods": ["driving"], "sub_genre": "Peak Techno"}
  monkeypatch.setattr("hpg_core.ai_engine.ai_metadata_matches", lambda *_args: False)
  monkeypatch.setattr(
    "hpg_core.ai_engine.fetch_ai_analysis", lambda *_args, **_kwargs: metadata
  )
  monkeypatch.setattr("hpg_core.caching.generate_cache_key", lambda *_args: "key")
  monkeypatch.setattr(
    "hpg_core.caching.merge_cached_ai_metadata",
    lambda *_args: merge_result,
  )
  worker = main.AIAnalysisWorker(
    [track], provider="Ollama", model="model", base_url="http://local"
  )
  failures = []
  finished = []
  progress = []
  worker.failed.connect(failures.append)
  worker.ai_finished.connect(lambda *args: finished.append(args))
  worker.progress.connect(lambda *args: progress.append(args))

  worker.run()

  assert len(failures) == 1
  assert "nicht bestaetigt persistiert" in failures[0]
  assert finished == []
  assert progress == [(0, 1)]
  assert track.ai_metadata == {}


def test_ai_analysis_worker_publiziert_nicht_bei_persistenz_exception(monkeypatch):
  track = Track(filePath="C:/a.wav", fileName="a.wav")
  metadata = {"moods": ["driving"], "sub_genre": "Peak Techno"}
  monkeypatch.setattr("hpg_core.ai_engine.ai_metadata_matches", lambda *_args: False)
  monkeypatch.setattr(
    "hpg_core.ai_engine.fetch_ai_analysis", lambda *_args, **_kwargs: metadata
  )
  monkeypatch.setattr("hpg_core.caching.generate_cache_key", lambda *_args: "key")

  def fail_merge(*_args):
    raise RuntimeError("cache kaputt")

  monkeypatch.setattr("hpg_core.caching.merge_cached_ai_metadata", fail_merge)
  worker = main.AIAnalysisWorker(
    [track], provider="Ollama", model="model", base_url="http://local"
  )
  failures = []
  finished = []
  progress = []
  worker.failed.connect(failures.append)
  worker.ai_finished.connect(lambda *args: finished.append(args))
  worker.progress.connect(lambda *args: progress.append(args))

  worker.run()

  assert failures == [
    "KI-Metadaten fuer 'a.wav' konnten nicht persistiert werden: cache kaputt"
  ]
  assert finished == []
  assert progress == [(0, 1)]
  assert track.ai_metadata == {}


def test_ai_analysis_worker_publiziert_nicht_ohne_cache_key(monkeypatch):
  track = Track(filePath="C:/a.wav", fileName="a.wav")
  metadata = {"moods": ["driving"], "sub_genre": "Peak Techno"}
  merge = Mock(return_value=True)
  monkeypatch.setattr("hpg_core.ai_engine.ai_metadata_matches", lambda *_args: False)
  monkeypatch.setattr(
    "hpg_core.ai_engine.fetch_ai_analysis", lambda *_args, **_kwargs: metadata
  )
  monkeypatch.setattr("hpg_core.caching.generate_cache_key", lambda *_args: None)
  monkeypatch.setattr("hpg_core.caching.merge_cached_ai_metadata", merge)
  worker = main.AIAnalysisWorker(
    [track], provider="Ollama", model="model", base_url="http://local"
  )
  failures = []
  finished = []
  progress = []
  worker.failed.connect(failures.append)
  worker.ai_finished.connect(lambda *args: finished.append(args))
  worker.progress.connect(lambda *args: progress.append(args))

  worker.run()

  assert failures == [
    "KI-Metadaten fuer 'a.wav' konnten nicht persistiert werden: "
    "kein sicherer Cache-Key"
  ]
  merge.assert_not_called()
  assert finished == []
  assert progress == [(0, 1)]
  assert track.ai_metadata == {}


def test_ai_analysis_worker_publiziert_commit_vor_nachlaufendem_cancel(monkeypatch):
  track = Track(filePath="C:/a.wav", fileName="a.wav")
  metadata = {"moods": ["driving"], "sub_genre": "Peak Techno"}
  monkeypatch.setattr("hpg_core.ai_engine.ai_metadata_matches", lambda *_args: False)
  monkeypatch.setattr(
    "hpg_core.ai_engine.fetch_ai_analysis", lambda *_args, **_kwargs: metadata
  )
  monkeypatch.setattr("hpg_core.caching.generate_cache_key", lambda *_args: "key")
  worker = main.AIAnalysisWorker(
    [track], provider="Ollama", model="model", base_url="http://local"
  )

  def persist_and_cancel(*_args):
    worker.request_cancel()
    return True

  monkeypatch.setattr(
    "hpg_core.caching.merge_cached_ai_metadata", persist_and_cancel
  )
  finished = []
  failures = []
  progress = []
  worker.ai_finished.connect(lambda *args: finished.append(args))
  worker.failed.connect(failures.append)
  worker.progress.connect(lambda *args: progress.append(args))

  worker.run()

  assert failures == []
  assert finished == [(track.filePath, metadata)]
  assert progress == [(0, 1)]
  assert track.ai_metadata == metadata


def test_ai_analysis_worker_reicht_cancel_durch_und_meldet_keinen_fehler(
  monkeypatch,
):
  track = Track(filePath="C:/a.wav", fileName="a.wav")
  worker = main.AIAnalysisWorker(
    [track], provider="Ollama", model="model", base_url="http://local"
  )
  captured = {}

  def fetch(*_args, **kwargs):
    captured["cancel_check"] = kwargs["cancel_check"]
    worker.request_cancel()
    raise InterruptedError("abgebrochen")

  monkeypatch.setattr("hpg_core.ai_engine.ai_metadata_matches", lambda *_args: False)
  monkeypatch.setattr("hpg_core.ai_engine.fetch_ai_analysis", fetch)
  failures = []
  progress = []
  worker.failed.connect(failures.append)
  worker.progress.connect(lambda current, total: progress.append((current, total)))

  worker.run()

  assert captured["cancel_check"] == worker.isInterruptionRequested
  assert failures == []
  assert progress == [(0, 1)]


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


def test_render_worker_weist_planlose_transition_ohne_subprozess_ab(
  monkeypatch, tmp_path
):
  worker = main.TransitionRenderWorker([SimpleNamespace(plan=None)])
  errors = []
  worker.clip_error.connect(lambda *args: errors.append(args))
  monkeypatch.setattr(main.tempfile, "mkdtemp", lambda **_kwargs: str(tmp_path))

  worker.run()

  assert errors == [(0, "Ungeplant: kein ausfuehrbarer TransitionPlan")]
  assert worker._executor is None


def test_analysis_worker_empty_folder(tmp_path):
  worker = main.AnalysisWorker(str(tmp_path))
  finished = []
  statuses = []
  worker.analysis_done.connect(lambda tracks, quality: finished.append((tracks, quality)))
  worker.status_update.connect(statuses.append)

  worker.run()

  assert finished == [([], {})]
  assert any("No audio files" in status for status in statuses)


def test_product_audio_extensions_are_explicit_and_complete():
  assert main.hpg_config.SUPPORTED_AUDIO_EXTENSIONS == (
    ".wav", ".aiff", ".aif", ".mp3", ".flac"
  )


def test_analysis_worker_routes_mixed_case_aif_to_parallel_analyzer(
  tmp_path, monkeypatch
):
  source = tmp_path / "track.AiF"
  source.write_bytes(b"fixture")
  track = Track(
    filePath=str(source), fileName=source.name,
    analysis_mode="librosa_full_or_tail",
  )
  captured = {}

  class CapturingAnalyzer:
    def analyze_files(self, files, progress_callback, **kwargs):
      captured["files"] = list(files)
      return [track]

  monkeypatch.setattr(main, "ParallelAnalyzer", CapturingAnalyzer)
  monkeypatch.setattr(main, "apply_resource_limits", lambda tracks: tracks)
  monkeypatch.setattr(
    main.AnalysisWorker,
    "_report_rekordbox_coverage",
    lambda self, analyzed_tracks: None,
  )
  worker = main.AnalysisWorker(str(tmp_path))
  finished = []
  worker.analysis_done.connect(lambda tracks, quality: finished.append((tracks, quality)))

  worker.run()

  assert captured["files"] == [str(source.resolve())]
  assert finished == [([track], {})]


def test_analysis_worker_success_and_analyzer_failure(tmp_path, monkeypatch):
  (tmp_path / "track.wav").write_bytes(b"fixture")
  track = Track(
    filePath=str(tmp_path / "track.wav"), fileName="track.wav",
    analysis_mode="librosa_full_or_tail",
  )

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


def test_analysis_worker_filtert_degradierte_tracks_und_emittiert_issues_zuerst(
  tmp_path, monkeypatch
):
  (tmp_path / "valid.wav").write_bytes(b"fixture")
  valid = Track(
    filePath=str(tmp_path / "valid.wav"), fileName="valid.wav",
    analysis_mode="librosa_full_or_tail",
  )
  degraded = Track(
    filePath=str(tmp_path / "broken.wav"), fileName="broken.wav",
    analysis_mode="rekordbox_degraded", energy=50,
  )
  invalid = Track(
    filePath=str(tmp_path / "invalid.wav"), fileName="invalid.wav",
    analysis_mode="invented_mode", energy=50,
  )

  class MixedAnalyzer:
    def analyze_files(self, *_args, **_kwargs):
      return [valid, degraded, invalid]

  monkeypatch.setattr(main, "ParallelAnalyzer", MixedAnalyzer)
  monkeypatch.setattr(main, "apply_resource_limits", lambda tracks: tracks)
  monkeypatch.setattr(
    main.AnalysisWorker, "_report_rekordbox_coverage",
    lambda self, analyzed_tracks: None,
  )
  worker = main.AnalysisWorker(str(tmp_path))
  events = []
  worker.analysis_issues.connect(lambda issues: events.append(("issues", issues)))
  worker.analysis_done.connect(
    lambda tracks, quality: events.append(("done", tracks, quality))
  )

  worker.run()

  assert events[0][0] == "issues"
  assert events[0][1] == (
    main.AnalysisIssue(
      "rekordbox_decode_degraded",
      degraded.filePath,
      "Audio-Decode fehlgeschlagen; Track wurde sicher ausgeschlossen.",
    ),
    main.AnalysisIssue(
      "invalid_analysis_mode",
      invalid.filePath,
      "Ungueltiger Analysemodus 'invented_mode'; Track wurde sicher ausgeschlossen.",
    ),
  )
  assert events[1] == ("done", [valid], {})
  assert degraded not in events[1][1]
  assert invalid not in events[1][1]


def test_analysis_worker_emittiert_leeres_issue_tuple_vor_ergebnis(
  tmp_path, monkeypatch
):
  source = tmp_path / "valid.wav"
  source.write_bytes(b"fixture")
  valid = Track(
    filePath=str(source), fileName=source.name,
    analysis_mode="librosa_full_or_tail",
  )

  class ValidAnalyzer:
    def analyze_files(self, *_args, **_kwargs):
      return [valid]

  monkeypatch.setattr(main, "ParallelAnalyzer", ValidAnalyzer)
  monkeypatch.setattr(main, "apply_resource_limits", lambda tracks: tracks)
  monkeypatch.setattr(
    main.AnalysisWorker, "_report_rekordbox_coverage",
    lambda self, analyzed_tracks: None,
  )
  worker = main.AnalysisWorker(str(tmp_path))
  events = []
  worker.analysis_issues.connect(lambda issues: events.append(("issues", issues)))
  worker.analysis_done.connect(lambda *_args: events.append(("done",)))

  worker.run()

  assert events == [("issues", ()), ("done",)]


def test_analysis_worker_cancel_during_scan(tmp_path):
  (tmp_path / "track.wav").write_bytes(b"fixture")
  worker = main.AnalysisWorker(str(tmp_path))
  worker.request_cancel()
  finished = []
  worker.analysis_done.connect(lambda tracks, quality: finished.append((tracks, quality)))

  worker.run()

  assert finished == [([], {})]


class _MemorySettings:
  def __init__(self, values=None):
    self.values = dict(values or {})

  def value(self, key, default=None):
    return self.values.get(key, default)

  def setValue(self, key, value):
    self.values[key] = value

  def sync(self):
    pass

  def status(self):
    return QSettings.Status.NoError


def _window(qtbot, monkeypatch, settings=None):
  monkeypatch.setattr(main.MainWindow, "check_dependencies_and_warn", lambda self: None)
  window = main.MainWindow(settings=settings or _MemorySettings())
  qtbot.addWidget(window)
  return window


def _deliver_current_analysis(window, tracks, quality=None):
  worker = Mock()
  window.worker = worker
  window.analysis_finished(tracks, quality or {}, worker)
  return worker


def _wait_playlist_worker(qtbot, window):
  qtbot.waitUntil(lambda: window.playlist_worker is None, timeout=5000)


def _move_table_rows(panel, first=0, second=1):
  destination = second + 1 if first < second else second
  moved = panel.table.model().moveRows(
    QModelIndex(), first, 1, QModelIndex(), destination
  )
  assert moved is True


def _playlist_table_item_snapshot(table):
  assert table.columnCount() == 16
  roles = tuple(main.Qt.ItemDataRole) + (main.TRACK_FILE_PATH_ROLE,)
  return tuple(
    tuple(
      None
      if (item := table.item(row, column)) is None
      else (
        item.flags(),
        tuple((int(role), item.data(role)) for role in roles),
      )
      for column in range(table.columnCount())
    )
    for row in range(table.rowCount())
  )


def test_mainwindow_terminal_state_and_empty_analysis(qtbot, monkeypatch):
  window = _window(qtbot, monkeypatch)
  window._set_run_state(main.RunState.AUDIO)
  window._finish_run(main.RunState.ERROR, "failed")
  assert window.run_state == main.RunState.ERROR
  assert window.library_panel.start_button.isEnabled()

  window._set_run_state(main.RunState.AUDIO)
  _deliver_current_analysis(window, [])
  assert window.run_state == main.RunState.ERROR
  assert "no results" in window.status_bar.status_label.text().lower()


def test_mainwindow_meldet_alle_degradierten_tracks_konkret(qtbot, monkeypatch):
  window = _window(qtbot, monkeypatch)
  window._analysis_issues = (
    main.AnalysisIssue("rekordbox_decode_degraded", "C:/a.wav", "decode"),
    main.AnalysisIssue("rekordbox_decode_degraded", "C:/b.wav", "decode"),
  )
  window._set_run_state(main.RunState.AUDIO)

  _deliver_current_analysis(window, [])

  assert window.run_state == main.RunState.ERROR
  status = window.status_bar.status_label.text()
  assert "Alle 2 Tracks" in status
  assert "Audio-Decodefehler" in status


def test_analysis_finished_akzeptiert_nur_aktuellen_worker_nach_ownership_wechsel(
  qtbot, monkeypatch
):
  window = _window(qtbot, monkeypatch)
  old_tracks = [Track(filePath="C:/old.wav", fileName="old.wav")]
  new_tracks = [Track(filePath="C:/new.wav", fileName="new.wav")]
  stale_worker = Mock()
  current_worker = Mock()
  window.worker = current_worker
  window.analyzed_raw_tracks = old_tracks
  window._run_settings = {
    "advanced_params": {},
    "ai_enabled": False,
  }
  window._set_run_state(main.RunState.AUDIO)
  window.status_bar.set_progress(17)
  window.library_panel.progress_widget.set_progress(17)
  start_next = Mock()
  monkeypatch.setattr(window, "on_ai_worker_finished", start_next)

  window.analysis_finished(new_tracks, {}, stale_worker)
  window.analysis_finished(new_tracks, {}, None)

  assert window.status_bar.progress_bar.value() == 17
  assert window.library_panel.progress_widget.progress_bar.value() == 17
  assert window.analyzed_raw_tracks == old_tracks
  start_next.assert_not_called()

  window.analysis_finished(new_tracks, {}, current_worker)

  assert window.status_bar.progress_bar.value() == 80
  assert window.library_panel.progress_widget.progress_bar.value() == 80
  assert window.analyzed_raw_tracks == new_tracks
  start_next.assert_called_once_with(ai_completed=False)


def test_start_analysis_bindet_analysis_done_an_konkreten_worker(
  qtbot, monkeypatch
):
  window = _window(qtbot, monkeypatch)
  settings = window.library_panel.get_current_settings()
  settings["folder"] = "C:/fixture"
  monkeypatch.setattr(
    window.library_panel, "get_current_settings", lambda: settings
  )
  monkeypatch.setattr(main.candidate_choices, "snapshot", lambda: {})
  monkeypatch.setattr(main.AnalysisWorker, "start", Mock())
  receive = Mock()
  monkeypatch.setattr(window, "analysis_finished", receive)

  window.start_analysis()
  worker = window.worker
  tracks = [Track(filePath="C:/new.wav", fileName="new.wav")]
  worker.analysis_done.emit(tracks, {"overall_score": 0.5})

  receive.assert_called_once_with(
    tracks, {"overall_score": 0.5}, worker
  )


@pytest.mark.parametrize("source_kind", ["missing", "stale"])
def test_on_ai_finished_verwirft_fehlende_und_stale_source(
  qtbot, monkeypatch, source_kind
):
  window = _window(qtbot, monkeypatch)
  current_worker = Mock()
  window.ai_worker = current_worker
  window._set_run_state(main.RunState.AI)
  track = Track(filePath="C:/a.wav", fileName="a.wav")
  track.ai_metadata = {"generation": 1}
  window.analyzed_raw_tracks = [track]
  source = None if source_kind == "missing" else Mock()

  window.on_ai_finished(
    track.filePath, {"generation": 2}, source
  )

  assert track.ai_metadata == {"generation": 1}


@pytest.mark.parametrize(
  "state", [main.RunState.CANCELLING, main.RunState.CANCELLED]
)
def test_on_ai_finished_verwirft_passende_source_in_cancel_zustaenden(
  qtbot, monkeypatch, state
):
  window = _window(qtbot, monkeypatch)
  current_worker = Mock()
  window.ai_worker = current_worker
  window._set_run_state(state)
  track = Track(filePath="C:/a.wav", fileName="a.wav")
  track.ai_metadata = {"generation": 1}
  window.analyzed_raw_tracks = [track]

  window.on_ai_finished(
    track.filePath, {"generation": 2}, current_worker
  )

  assert track.ai_metadata == {"generation": 1}


def test_on_ai_finished_akzeptiert_aktuelle_source_im_ai_zustand(
  qtbot, monkeypatch
):
  window = _window(qtbot, monkeypatch)
  current_worker = Mock()
  window.ai_worker = current_worker
  window._set_run_state(main.RunState.AI)
  track = Track(filePath="C:/a.wav", fileName="a.wav")
  window.analyzed_raw_tracks = [track]

  window.on_ai_finished(
    track.filePath, {"generation": 2}, current_worker
  )

  assert track.ai_metadata == {"generation": 2}


def test_result_candidate_choice_nutzt_key_snapshot_und_einen_rebuild(
  qtbot, monkeypatch
):
  from hpg_core import playlist as playlist_module

  window = _window(qtbot, monkeypatch)
  from_track = Track(filePath="C:/a.wav", fileName="a.wav", bpm=128.0)
  to_track = Track(filePath="C:/b.wav", fileName="b.wav", bpm=129.0)
  key = (100, 50, 16, "direct", ("out",), ("in",), 0)
  candidate = SimpleNamespace(
    key=key, t_out=5.0, t_in=2.5, blend_bars=16,
    overlap_sec=30.0, rang=2,
  )
  occurrence_a = SimpleNamespace(occurrence_id=("run", 0), track=from_track)
  occurrence_b = SimpleNamespace(occurrence_id=("run", 1), track=to_track)
  boundary = SimpleNamespace(
    index=0,
    from_occurrence_id=occurrence_a.occurrence_id,
    to_occurrence_id=occurrence_b.occurrence_id,
    snapshots=(candidate,),
  )
  directed_key = main.candidate_choices.schluessel("C:/a.wav", "C:/b.wav")
  untouched_key = main.candidate_choices.schluessel("C:/x.wav", "C:/y.wav")
  old_snapshot = {
    directed_key: {"t_out": 1.0, "marker": "alt"},
    untouched_key: {"t_out": 9.0, "marker": "unberuehrt"},
  }
  old_result = SimpleNamespace(
    boundaries=(boundary,), occurrences=(occurrence_a, occurrence_b),
    candidate_choice_snapshot_dict=lambda: {
      item_key: dict(item_value)
      for item_key, item_value in old_snapshot.items()
    },
  )
  new_result = object()
  window.current_generation_result = old_result
  merke = Mock()
  monkeypatch.setattr(main.candidate_choices, "hole", lambda *_args: None)
  monkeypatch.setattr(main.candidate_choices, "merke", merke)
  live_snapshot = Mock(
    side_effect=AssertionError("GUI-Neuwahl darf den Live-Store nicht lesen")
  )
  monkeypatch.setattr(main.candidate_choices, "snapshot", live_snapshot)
  rebuild = Mock(return_value=new_result)
  monkeypatch.setattr(playlist_module, "rebuild_result_for_order", rebuild)
  publish = Mock()
  monkeypatch.setattr(window, "_publiziere_generation_result", publish)

  window._on_candidate_chosen(0, list(key))

  merke.assert_called_once_with(
    "C:/a.wav", "C:/b.wav",
    t_out=5.0, t_in=2.5, blend_bars=16,
    bpm_a=128.0, bpm_b=129.0, overlap_sec=30.0,
  )
  rebuild.assert_called_once()
  rebuild_args = rebuild.call_args
  assert rebuild_args.args == (old_result, (("run", 0), ("run", 1)))
  rebuilt_snapshot = rebuild_args.kwargs["choice_snapshot"]
  assert rebuilt_snapshot == {
    directed_key: {
      "t_out": 5.0,
      "t_in": 2.5,
      "blend_bars": 16,
      "version": 2,
      "bpm_a": 128.0,
      "bpm_b": 129.0,
      "overlap_sec": 30.0,
    },
    untouched_key: {"t_out": 9.0, "marker": "unberuehrt"},
  }
  assert "external-live-key" not in rebuilt_snapshot
  live_snapshot.assert_not_called()
  publish.assert_called_once_with(new_result)

  rollback_state = object()
  merke.return_value = rollback_state
  rebuild.side_effect = RuntimeError("Rebuild fehlgeschlagen")
  restore = Mock()
  monkeypatch.setattr(main.candidate_choices, "stelle_wieder_her", restore)

  window._on_candidate_chosen(0, list(key))

  restore.assert_called_once_with(rollback_state)
  assert "wiederhergestellt" in window.status_bar.status_label.text()


def _beatgrid_track(name, status="verified", error_ms=-1.0):
  return Track(
    filePath=f"C:/{name}",
    fileName=name,
    bpm=128.0,
    analysis_mode="librosa_full_or_tail",
    beatgrid_source="rekordbox",
    beatgrid_status=status,
    beatgrid_windows_checked=3,
    beatgrid_max_phase_error_ms=error_ms,
  )


def test_analysis_finished_zeigt_keinen_modal_dialog_fuer_beatgrid_diagnose(
  qtbot, monkeypatch
):
  window = _window(qtbot, monkeypatch)
  warning = Mock()
  monkeypatch.setattr(main.QMessageBox, "warning", warning)
  monkeypatch.setattr(window, "on_ai_worker_finished", Mock())
  window._run_settings = {"ai_enabled": False}
  tracks = [
    _beatgrid_track("gut.wav"),
    _beatgrid_track("falsch.wav", "mismatch", 18.75),
    _beatgrid_track("unklar.wav", "unverifiable"),
  ]

  _deliver_current_analysis(window, tracks)

  warning.assert_not_called()


def test_analysis_finished_zeigt_bei_nur_verified_keinen_beatgrid_dialog(
  qtbot, monkeypatch
):
  window = _window(qtbot, monkeypatch)
  warning = Mock()
  monkeypatch.setattr(main.QMessageBox, "warning", warning)
  monkeypatch.setattr(window, "on_ai_worker_finished", Mock())
  window._run_settings = {"ai_enabled": False}

  _deliver_current_analysis(window, [_beatgrid_track("gut.wav")])

  warning.assert_not_called()


def test_final_generation_verwendet_genau_ein_unveraenderliches_result(
  qtbot, monkeypatch
):
  window = _window(qtbot, monkeypatch)
  tracks = [
    Track(filePath="C:/a.wav", fileName="a.wav", bpm=128.0),
    Track(filePath="C:/b.wav", fileName="b.wav", bpm=129.0),
  ]
  result = SimpleNamespace(tracks=tuple(tracks))
  generate = Mock(return_value=result)
  publish = Mock()
  monkeypatch.setattr("hpg_core.playlist.generate_playlist_result", generate)
  monkeypatch.setattr(window, "_publiziere_generation_result", publish)
  window.analyzed_raw_tracks = tracks
  window._run_settings = {
    "folder": "C:/",
    "strategy": "Harmonic Flow",
    "bpm_tolerance": 3.0,
    "advanced_params": {},
    "ai_enabled": False,
  }

  window.on_ai_worker_finished(ai_completed=False, finalize=True)
  _wait_playlist_worker(qtbot, window)

  generate.assert_called_once()
  publish.assert_called_once_with(result)


def test_playlist_generation_laeuft_im_worker_und_gui_bleibt_responsiv(
  qtbot, monkeypatch
):
  window = _window(qtbot, monkeypatch)
  tracks = [Track(filePath="C:/a.wav", fileName="a.wav", bpm=128.0)]
  result = SimpleNamespace(tracks=tuple(tracks), mode="Harmonic Flow")
  gestartet = threading.Event()
  freigabe = threading.Event()
  worker_thread = []

  def generate(*_args, **_kwargs):
    worker_thread.append(QThread.currentThread())
    gestartet.set()
    assert freigabe.wait(3.0)
    return result

  monkeypatch.setattr("hpg_core.playlist.generate_playlist_result", generate)
  publish = Mock()
  monkeypatch.setattr(window, "_publiziere_generation_result", publish)
  window.analyzed_raw_tracks = tracks
  window._run_settings = {
    "folder": "C:/", "strategy": "Harmonic Flow", "bpm_tolerance": 3.0,
    "advanced_params": {}, "ai_enabled": False,
  }

  window.on_ai_worker_finished(ai_completed=False, finalize=True)
  qtbot.waitUntil(gestartet.is_set, timeout=3000)
  active_worker = window.playlist_worker
  gui_tick = []
  QTimer.singleShot(0, lambda: gui_tick.append(True))
  qtbot.waitUntil(lambda: bool(gui_tick), timeout=1000)

  assert active_worker is not None and active_worker.isRunning()
  assert worker_thread == [active_worker]
  publish.assert_not_called()

  freigabe.set()
  _wait_playlist_worker(qtbot, window)
  publish.assert_called_once_with(result)


def test_playlist_worker_bricht_innerhalb_der_berechnung_ohne_signal_ab(
  monkeypatch,
):
  track = Track(filePath="C:/a.wav", fileName="a.wav", bpm=128.0)
  worker = main.PlaylistGenerationWorker(
    [track],
    mode="Harmonic Flow",
    bpm_tolerance=3.0,
    advanced_params={},
    scoring_context={},
    candidate_choice_snapshot={},
  )
  captured = {}
  cancelled = {"value": False}
  monkeypatch.setattr(
    worker, "isInterruptionRequested", lambda: cancelled["value"]
  )

  def generate(*_args, **kwargs):
    captured["cancel_check"] = kwargs["cancel_check"]
    cancelled["value"] = True
    assert kwargs["cancel_check"]()
    raise InterruptedError("abgebrochen")

  monkeypatch.setattr("hpg_core.playlist.generate_playlist_result", generate)
  done, failed = [], []
  worker.generation_done.connect(done.append)
  worker.generation_failed.connect(failed.append)

  worker.run()

  assert captured["cancel_check"] == worker.isInterruptionRequested
  assert done == []
  assert failed == []


def test_stale_playlist_worker_result_und_fehler_werden_ignoriert(
  qtbot, monkeypatch
):
  window = _window(qtbot, monkeypatch)
  current = Mock()
  stale = Mock()
  window.playlist_worker = current
  publish = Mock()
  reporter = Mock()
  monkeypatch.setattr(window, "_publiziere_generation_result", publish)
  monkeypatch.setattr(main, "get_error_reporter", lambda: reporter)
  result = SimpleNamespace(tracks=(object(),), mode="Harmonic Flow")

  window._on_playlist_generation_done(result, stale)
  window._on_playlist_generation_failed("alt", stale)

  publish.assert_not_called()
  reporter.log_error.assert_not_called()


def test_ai_lifecycle_generiert_und_publiziert_result_erst_nach_worker_ende(
  qtbot, monkeypatch
):
  window = _window(qtbot, monkeypatch)
  tracks = [Track(filePath="C:/a.wav", fileName="a.wav", bpm=128.0)]
  result = SimpleNamespace(tracks=tuple(tracks))
  generate = Mock(return_value=result)
  publish = Mock()
  monkeypatch.setattr("hpg_core.playlist.generate_playlist_result", generate)
  monkeypatch.setattr(window, "_publiziere_generation_result", publish)
  monkeypatch.setattr(main.AIAnalysisWorker, "start", Mock())
  window._run_settings = {
    "folder": "C:/",
    "strategy": "Harmonic Flow",
    "bpm_tolerance": 3.0,
    "advanced_params": {},
    "ai_enabled": True,
    "ai_provider": "Ollama",
    "ai_model": "local-model",
    "ai_base_url": "http://127.0.0.1:11434",
  }

  _deliver_current_analysis(window, tracks)

  generate.assert_not_called()
  publish.assert_not_called()
  worker = window.ai_worker
  assert worker is not None

  window.on_ai_worker_finished(worker)
  _wait_playlist_worker(qtbot, window)

  generate.assert_called_once()
  publish.assert_called_once_with(result)


def test_ai_worker_verwendet_auch_leere_model_und_base_url_laufsnapshots(
  qtbot, monkeypatch
):
  window = _window(qtbot, monkeypatch)
  tracks = [Track(filePath="C:/a.wav", fileName="a.wav", bpm=128.0)]
  captured = {}

  class _Signal:
    def connect(self, _slot):
      pass

    def disconnect(self):
      pass

  class _AIWorker:
    def __init__(self, worker_tracks, *, provider, model, base_url):
      captured.update(
        tracks=worker_tracks, provider=provider, model=model, base_url=base_url
      )
      self.ai_finished = _Signal()
      self.progress = _Signal()
      self.failed = _Signal()
      self.finished = _Signal()
      self.start = Mock()

    def isRunning(self):
      return False

    def deleteLater(self):
      pass

  monkeypatch.setattr(main, "AIAnalysisWorker", _AIWorker)
  window._run_settings = {
    "advanced_params": {},
    "ai_enabled": True,
    "ai_provider": "Ollama",
    "ai_model": "",
    "ai_base_url": None,
  }
  advanced = window.library_panel.advanced_params
  advanced.model_combo.addItem("spaeteres-live-modell")
  advanced.model_combo.setCurrentText("spaeteres-live-modell")
  advanced.detected_base_url = "http://spaeter-live"

  _deliver_current_analysis(window, tracks)

  assert captured == {
    "tracks": tracks,
    "provider": "Ollama",
    "model": "",
    "base_url": None,
  }
  window.ai_worker.start.assert_called_once_with()


def test_final_generation_rolls_back_when_generation_fails(qtbot, monkeypatch):
  reporter = Mock()
  monkeypatch.setattr(main, "get_error_reporter", lambda: reporter)
  window = _window(qtbot, monkeypatch)
  old = [Track(filePath="C:/old.wav", fileName="old.wav", bpm=128.0)]
  new = [Track(filePath="C:/new.wav", fileName="new.wav", bpm=129.0)]
  window.playlist = old
  window.playlist_panel.set_playlist_data(old, {"overall_score": 0.4}, [])
  window.quality_metrics = {"overall_score": 0.4}
  window.analyzed_raw_tracks = new
  window._run_settings = {
    "folder": "C:/", "strategy": "Harmonic Flow", "bpm_tolerance": 3.0,
    "advanced_params": {}, "ai_enabled": False,
  }
  monkeypatch.setattr(
    "hpg_core.playlist.generate_playlist_result",
    Mock(side_effect=RuntimeError("generation kaputt")),
  )

  window.on_ai_worker_finished(ai_completed=False, finalize=True)
  _wait_playlist_worker(qtbot, window)

  assert window.playlist == old
  assert window.playlist_panel.playlist == old
  assert window.quality_metrics == {"overall_score": 0.4}
  assert window.run_state == main.RunState.ERROR
  assert window.library_panel.start_button.isEnabled()
  reporter.log_error.assert_called_once()


def test_final_generation_rolls_back_when_atomic_publish_fails(qtbot, monkeypatch):
  reporter = Mock()
  monkeypatch.setattr(main, "get_error_reporter", lambda: reporter)
  window = _window(qtbot, monkeypatch)
  old = [Track(filePath="C:/old.wav", fileName="old.wav", bpm=128.0)]
  new = [Track(filePath="C:/new.wav", fileName="new.wav", bpm=129.0)]
  window.playlist = old
  window.quality_metrics = {"overall_score": 0.4}
  window.playlist_panel.set_playlist_data(old, window.quality_metrics, [])
  window.analyzed_raw_tracks = new
  window._run_settings = {
    "folder": "C:/", "strategy": "Harmonic Flow", "bpm_tolerance": 3.0,
    "advanced_params": {}, "ai_enabled": False,
  }
  result = SimpleNamespace(tracks=tuple(new))
  monkeypatch.setattr(
    "hpg_core.playlist.generate_playlist_result", Mock(return_value=result)
  )
  monkeypatch.setattr(
    window, "_publiziere_generation_result",
    Mock(side_effect=RuntimeError("publish kaputt")),
  )

  window.on_ai_worker_finished(ai_completed=False, finalize=True)
  _wait_playlist_worker(qtbot, window)

  assert window.playlist == old
  assert window.playlist_panel.playlist == old
  assert window.quality_metrics == {"overall_score": 0.4}
  assert window.run_state == main.RunState.ERROR
  reporter.log_error.assert_called_once()


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


def test_preview_cancel_leert_queue_und_stellt_buttons_wieder_her(qtbot):
  panel = main.MixTipsPanel()
  qtbot.addWidget(panel)
  worker = Mock()
  panel._render_worker = worker
  panel._active_preview_index = 0
  panel._preview_queue.extend([1, 2])
  for index in range(3):
    button = main.QPushButton("Vorschau wird vorbereitet …")
    button.setEnabled(False)
    panel._preview_buttons[index] = button

  panel.cancel_previews()

  assert list(panel._preview_queue) == []
  worker.request_cancel.assert_called_once_with()
  assert all(button.isEnabled() for button in panel._preview_buttons.values())
  assert all(
    button.text() == "Vorschau bei Bedarf rendern"
    for button in panel._preview_buttons.values()
  )


def test_stale_preview_signale_nach_rebuild_veraendern_neue_ui_nicht(
  qtbot, tmp_path
):
  panel = main.MixTipsPanel()
  qtbot.addWidget(panel)
  current_worker = object()
  stale_worker = object()
  panel._render_worker = current_worker
  widget = Mock()
  button = Mock()
  panel._preview_widgets[0] = widget
  panel._preview_buttons[0] = button
  stale_clip = tmp_path / "stale.wav"
  stale_clip.write_bytes(b"stale")

  panel._on_clip_ready(0, str(stale_clip), stale_worker)
  panel._on_clip_error(0, "alt", stale_worker)

  assert not stale_clip.exists()
  assert 0 not in panel._preview_cache
  widget.set_wav_path.assert_not_called()
  widget.set_error.assert_not_called()
  button.setText.assert_not_called()
  panel._render_worker = None


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


@pytest.mark.parametrize("changed", ["provider", "model", "base_url"])
def test_stale_ai_test_result_does_not_overwrite_current_selection(
  qtbot, monkeypatch, changed
):
  widget = main.AdvancedParametersWidget()
  qtbot.addWidget(widget)
  widget.ai_enabled_checkbox.blockSignals(True)
  widget.ai_enabled_checkbox.setChecked(True)
  widget.ai_enabled_checkbox.blockSignals(False)
  widget.ollama_radio.blockSignals(True)
  widget.lmstudio_radio.blockSignals(True)
  widget.ollama_radio.setChecked(True)
  widget.lmstudio_radio.setChecked(False)
  widget.ollama_radio.blockSignals(False)
  widget.lmstudio_radio.blockSignals(False)
  widget.model_combo.blockSignals(True)
  widget.model_combo.clear()
  widget.model_combo.addItem("old-model")
  widget.model_combo.setCurrentText("old-model")
  widget.model_combo.blockSignals(False)
  widget.detected_provider = "Ollama"
  widget.detected_base_url = "http://old/v1/chat/completions"
  worker = main.AITestWorker(
    "Ollama", "old-model", "http://old/v1/chat/completions"
  )
  widget._test_worker = worker

  if changed == "provider":
    widget.ollama_radio.blockSignals(True)
    widget.lmstudio_radio.blockSignals(True)
    widget.ollama_radio.setChecked(False)
    widget.lmstudio_radio.setChecked(True)
    widget.ollama_radio.blockSignals(False)
    widget.lmstudio_radio.blockSignals(False)
    widget.detected_provider = "LM Studio"
  elif changed == "model":
    widget.model_combo.setCurrentText("new-model")
    widget.model_combo.addItem("new-model")
    widget.model_combo.setCurrentText("new-model")
  else:
    widget.detected_base_url = "http://new/v1/chat/completions"

  widget.ai_status_label.setText("aktueller Zustand")
  widget.test_ai_btn.setEnabled(False)
  widget.ai_refresh_btn.setEnabled(False)
  information = Mock()
  critical = Mock()
  question = Mock()
  monkeypatch.setattr(main.QMessageBox, "information", information)
  monkeypatch.setattr(main.QMessageBox, "critical", critical)
  monkeypatch.setattr(main.QMessageBox, "question", question)

  widget._on_test_finished(True, "OK", "old-model", 0.1, worker)

  assert widget.ai_status_label.text() == "aktueller Zustand"
  assert widget.test_ai_btn.isEnabled()
  assert widget.ai_refresh_btn.isEnabled()
  information.assert_not_called()
  critical.assert_not_called()
  question.assert_not_called()


def test_stale_ai_test_result_leaves_new_detect_worker_authoritative(
  qtbot, monkeypatch
):
  widget = main.AdvancedParametersWidget()
  qtbot.addWidget(widget)
  widget.ai_enabled_checkbox.blockSignals(True)
  widget.ai_enabled_checkbox.setChecked(True)
  widget.ai_enabled_checkbox.blockSignals(False)
  widget.model_combo.addItem("new-model")
  widget.detected_provider = "LM Studio"
  widget.detected_base_url = "http://new/v1/chat/completions"
  worker = main.AITestWorker(
    "Ollama", "old-model", "http://old/v1/chat/completions"
  )
  widget._test_worker = worker
  detect_worker = Mock()
  detect_worker.isRunning.return_value = True
  widget._ai_detect_worker = detect_worker
  widget.ai_status_label.setText("neue Erkennung laeuft")
  widget.test_ai_btn.setEnabled(False)
  widget.ai_refresh_btn.setEnabled(False)
  information = Mock()
  monkeypatch.setattr(main.QMessageBox, "information", information)

  widget._on_test_finished(True, "OK", "old-model", 0.1, worker)

  assert widget.ai_status_label.text() == "neue Erkennung laeuft"
  assert not widget.test_ai_btn.isEnabled()
  assert not widget.ai_refresh_btn.isEnabled()
  information.assert_not_called()
  widget._ai_detect_worker = None


@pytest.mark.parametrize("changed", ["disabled", "provider", "model"])
def test_stale_ai_pull_result_does_not_overwrite_current_state(
  qtbot, monkeypatch, changed
):
  widget = main.AdvancedParametersWidget()
  qtbot.addWidget(widget)
  widget.ai_enabled_checkbox.blockSignals(True)
  widget.ai_enabled_checkbox.setChecked(changed != "disabled")
  widget.ai_enabled_checkbox.blockSignals(False)
  widget.ollama_radio.blockSignals(True)
  widget.lmstudio_radio.blockSignals(True)
  widget.ollama_radio.setChecked(changed != "provider")
  widget.lmstudio_radio.setChecked(changed == "provider")
  widget.ollama_radio.blockSignals(False)
  widget.lmstudio_radio.blockSignals(False)
  widget.model_combo.blockSignals(True)
  widget.model_combo.clear()
  current_model = "new-model" if changed == "model" else "old-model"
  widget.model_combo.addItem(current_model)
  widget.model_combo.setCurrentText(current_model)
  widget.model_combo.blockSignals(False)
  widget.detected_provider = (
    "LM Studio" if changed == "provider" else "Ollama"
  )
  widget.detected_base_url = "http://current/v1/chat/completions"
  worker = main.AIPullWorker("old-model")
  widget._pull_worker = worker
  widget.ai_status_label.setText("aktueller Zustand")
  widget.test_ai_btn.setEnabled(False)
  widget.ai_refresh_btn.setEnabled(False)
  test_connection = Mock()
  refresh = Mock()
  information = Mock()
  critical = Mock()
  monkeypatch.setattr(widget, "test_ai_connection", test_connection)
  monkeypatch.setattr(widget, "refresh_ai_providers", refresh)
  monkeypatch.setattr(main.QMessageBox, "information", information)
  monkeypatch.setattr(main.QMessageBox, "critical", critical)

  widget._on_pull_finished(True, "", worker)

  assert widget.ai_status_label.text() == "aktueller Zustand"
  if changed == "disabled":
    assert not widget.test_ai_btn.isEnabled()
    assert not widget.ai_refresh_btn.isEnabled()
  else:
    assert widget.test_ai_btn.isEnabled()
    assert widget.ai_refresh_btn.isEnabled()
  test_connection.assert_not_called()
  refresh.assert_not_called()
  information.assert_not_called()
  critical.assert_not_called()


def test_stale_ai_pull_result_leaves_new_detect_worker_authoritative(
  qtbot, monkeypatch
):
  widget = main.AdvancedParametersWidget()
  qtbot.addWidget(widget)
  widget.ai_enabled_checkbox.blockSignals(True)
  widget.ai_enabled_checkbox.setChecked(True)
  widget.ai_enabled_checkbox.blockSignals(False)
  widget.model_combo.addItem("new-model")
  worker = main.AIPullWorker("old-model")
  widget._pull_worker = worker
  detect_worker = Mock()
  detect_worker.isRunning.return_value = True
  widget._ai_detect_worker = detect_worker
  widget.ai_status_label.setText("neue Erkennung laeuft")
  widget.test_ai_btn.setEnabled(False)
  widget.ai_refresh_btn.setEnabled(False)
  information = Mock()
  monkeypatch.setattr(main.QMessageBox, "information", information)

  widget._on_pull_finished(True, "", worker)

  assert widget.ai_status_label.text() == "neue Erkennung laeuft"
  assert not widget.test_ai_btn.isEnabled()
  assert not widget.ai_refresh_btn.isEnabled()
  information.assert_not_called()
  widget._ai_detect_worker = None


@pytest.mark.parametrize("success", [True, False])
def test_current_ai_pull_result_keeps_success_and_error_paths(
  qtbot, monkeypatch, success
):
  widget = main.AdvancedParametersWidget()
  qtbot.addWidget(widget)
  widget.ai_enabled_checkbox.blockSignals(True)
  widget.ai_enabled_checkbox.setChecked(True)
  widget.ai_enabled_checkbox.blockSignals(False)
  widget.ollama_radio.blockSignals(True)
  widget.ollama_radio.setChecked(True)
  widget.ollama_radio.blockSignals(False)
  widget.model_combo.blockSignals(True)
  widget.model_combo.clear()
  widget.model_combo.addItem("current-model")
  widget.model_combo.setCurrentText("current-model")
  widget.model_combo.blockSignals(False)
  worker = main.AIPullWorker("current-model")
  widget._pull_worker = worker
  test_connection = Mock()
  refresh = Mock()
  information = Mock()
  critical = Mock()
  monkeypatch.setattr(widget, "test_ai_connection", test_connection)
  monkeypatch.setattr(widget, "refresh_ai_providers", refresh)
  monkeypatch.setattr(main.QMessageBox, "information", information)
  monkeypatch.setattr(main.QMessageBox, "critical", critical)

  widget._on_pull_finished(success, "download error", worker)

  assert widget.test_ai_btn.isEnabled()
  assert widget.ai_refresh_btn.isEnabled()
  if success:
    assert "Download abgeschlossen" in widget.ai_status_label.text()
    test_connection.assert_called_once_with()
    refresh.assert_called_once_with()
    information.assert_called_once()
    critical.assert_not_called()
  else:
    assert "Fehler beim Download" in widget.ai_status_label.text()
    test_connection.assert_not_called()
    refresh.assert_not_called()
    information.assert_not_called()
    critical.assert_called_once()


def test_mainwindow_m3u8_and_partial_xml_export(qtbot, monkeypatch, tmp_path):
  window = _window(qtbot, monkeypatch)
  window.playlist = [Track(filePath="C:/a.wav", fileName="a.wav")]
  window.current_playlist_mode = "Harmonic Flow"
  window.current_generation_result = SimpleNamespace(mode="Warm-Up")
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
  assert m3u8_exporter.export.call_args.args[2] == "HPG - Warm-Up"
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
  assert xml_exporter.export.call_args.args[2] == "HPG - Warm-Up"
  warning.assert_called_once()


def test_restart_and_close_without_workers(qtbot, monkeypatch):
  window = _window(qtbot, monkeypatch)
  window.playlist = [Track(filePath="C:/a.wav", fileName="a.wav")]
  window.current_generation_result = object()
  window.restart_app()
  assert window.playlist == []
  assert window.current_generation_result is None
  event = Mock()
  window.closeEvent(event)
  event.accept.assert_called_once()


def test_close_ignore_wenn_worker_wait_false_liefert(qtbot, monkeypatch):
  window = _window(qtbot, monkeypatch)
  worker = Mock()
  worker.isRunning.return_value = True
  worker.wait.return_value = False
  window.playlist_worker = worker
  monkeypatch.setattr(main.QTimer, "singleShot", Mock())
  event = Mock()

  window.closeEvent(event)

  worker.request_cancel.assert_called_once_with()
  worker.wait.assert_called_once_with(50)
  event.ignore.assert_called_once_with()
  event.accept.assert_not_called()
  assert not hasattr(worker, "terminate") or not worker.terminate.called

  worker.isRunning.return_value = False
  finished_event = Mock()
  window.closeEvent(finished_event)
  finished_event.accept.assert_called_once_with()
  finished_event.ignore.assert_not_called()


def test_close_gate_erfasst_superseded_render_worker_bis_finished(
  qtbot, monkeypatch
):
  window = _window(qtbot, monkeypatch)
  panel = window.mix_tips_panel
  worker = SimpleNamespace(
    isRunning=Mock(return_value=True),
    wait=Mock(return_value=False),
    request_cancel=Mock(),
    get_temp_dir=Mock(return_value=None),
    get_temp_files=Mock(return_value=[]),
    deleteLater=Mock(),
  )
  panel._render_workers = [worker]
  panel._render_worker = None
  monkeypatch.setattr(main.QTimer, "singleShot", Mock())

  first_event = Mock()
  window.closeEvent(first_event)
  first_event.ignore.assert_called_once_with()
  first_event.accept.assert_not_called()
  worker.request_cancel.assert_called_once_with()
  worker.wait.assert_called_once_with(50)

  worker.isRunning.return_value = False
  second_event = Mock()
  window.closeEvent(second_event)
  second_event.accept.assert_called_once_with()

  panel._on_preview_worker_finished(worker)
  panel._on_preview_worker_finished(worker)
  assert panel._render_workers == []
  worker.deleteLater.assert_called_once_with()


def test_cancel_superseded_preview_weckt_drain_genau_einmal(qtbot, monkeypatch):
  window = _window(qtbot, monkeypatch)
  panel = window.mix_tips_panel
  worker = SimpleNamespace(
    isRunning=Mock(return_value=True),
    request_cancel=Mock(),
    get_temp_dir=Mock(return_value=None),
    get_temp_files=Mock(return_value=[]),
    deleteLater=Mock(),
  )
  panel._render_worker = None
  panel._render_workers = [worker]
  window._set_run_state(main.RunState.CANCELLING)

  assert window._try_finish_cancelled_run() is False
  worker.isRunning.return_value = False
  panel._on_preview_worker_finished(worker)

  assert window.run_state == main.RunState.CANCELLED
  panel._on_preview_worker_finished(worker)
  worker.deleteLater.assert_called_once_with()


def test_cancel_retired_preview_weckt_drain_nach_finished(qtbot, monkeypatch):
  window = _window(qtbot, monkeypatch)
  retired = main.MixTipsPanel()
  qtbot.addWidget(retired)
  worker = SimpleNamespace(
    isRunning=Mock(return_value=True),
    get_temp_dir=Mock(return_value=None),
    get_temp_files=Mock(return_value=[]),
    deleteLater=Mock(),
  )
  retired._render_worker = None
  retired._render_workers = [worker]
  window._retired_mix_tips_panels.add(retired)
  window._set_run_state(main.RunState.CANCELLING)

  assert window._try_finish_cancelled_run() is False
  worker.isRunning.return_value = False
  retired._on_preview_worker_finished(worker)
  assert window.run_state == main.RunState.CANCELLING

  window._finish_retired_mix_tips_panel(retired)
  assert window.run_state == main.RunState.CANCELLED
  assert retired not in window._retired_mix_tips_panels


def test_run_guard_erfasst_laufenden_superseded_render_worker(qtbot, monkeypatch):
  window = _window(qtbot, monkeypatch)
  worker = SimpleNamespace(isRunning=Mock(return_value=True))
  window.mix_tips_panel._render_worker = None
  window.mix_tips_panel._render_workers = [worker]

  assert window._run_is_active() is True

  worker.isRunning.return_value = False
  assert window._run_is_active() is False


def test_run_guard_erfasst_laufenden_retired_render_worker(qtbot, monkeypatch):
  window = _window(qtbot, monkeypatch)
  retired = main.MixTipsPanel()
  qtbot.addWidget(retired)
  worker = SimpleNamespace(isRunning=Mock(return_value=True))
  retired._render_worker = None
  retired._render_workers = [worker]
  window._retired_mix_tips_panels.add(retired)

  assert window._run_is_active() is True

  worker.isRunning.return_value = False
  assert window._run_is_active() is False


def test_cancel_ai_finished_wartet_auf_current_preview(qtbot, monkeypatch):
  window = _window(qtbot, monkeypatch)
  ai_worker = SimpleNamespace(
    isRunning=Mock(return_value=False),
    deleteLater=Mock(),
    failure_reason="",
  )
  preview_worker = SimpleNamespace(
    isRunning=Mock(return_value=True),
    get_temp_dir=Mock(return_value=None),
    get_temp_files=Mock(return_value=[]),
    deleteLater=Mock(),
  )
  window.ai_worker = ai_worker
  window.mix_tips_panel._render_worker = preview_worker
  window.mix_tips_panel._render_workers = [preview_worker]
  window._set_run_state(main.RunState.CANCELLING)

  window.on_ai_worker_finished(ai_worker)

  assert window.ai_worker is None
  assert window.run_state == main.RunState.CANCELLING
  preview_worker.isRunning.return_value = False
  window.mix_tips_panel._on_preview_worker_finished(preview_worker)
  assert window.run_state == main.RunState.CANCELLED


def test_cancel_stale_ai_und_playlist_sources_bleiben_wirkungslos(
  qtbot, monkeypatch
):
  window = _window(qtbot, monkeypatch)
  current_ai = Mock()
  current_playlist = Mock()
  current_ai.isRunning.return_value = False
  current_playlist.isRunning.return_value = False
  window.ai_worker = current_ai
  window.playlist_worker = current_playlist
  window._set_run_state(main.RunState.CANCELLING)

  window.on_ai_worker_finished(Mock())
  window._cleanup_playlist_worker(Mock())

  assert window.ai_worker is current_ai
  assert window.playlist_worker is current_playlist
  assert window.run_state == main.RunState.CANCELLING


def test_cancel_core_ownership_bleibt_bis_finished_cleanup_fail_closed(
  qtbot, monkeypatch
):
  window = _window(qtbot, monkeypatch)
  worker = Mock()
  worker.isRunning.return_value = False
  window.playlist_worker = worker
  window._set_run_state(main.RunState.CANCELLING)

  assert window._try_finish_cancelled_run() is False
  assert window.run_state == main.RunState.CANCELLING
  worker.isRunning.assert_not_called()


def test_queued_ergebnisse_nach_cancelled_starten_und_publizieren_nichts(
  qtbot, monkeypatch
):
  window = _window(qtbot, monkeypatch)
  old_tracks = [Track(filePath="C:/old.wav", fileName="old.wav", bpm=128.0)]
  new_tracks = [Track(filePath="C:/new.wav", fileName="new.wav", bpm=129.0)]
  window.analyzed_raw_tracks = old_tracks
  window._set_run_state(main.RunState.CANCELLED)
  real_on_ai_worker_finished = window.on_ai_worker_finished
  start_playlist = Mock()
  publish = Mock()
  monkeypatch.setattr(window, "on_ai_worker_finished", start_playlist)
  monkeypatch.setattr(window, "_publiziere_generation_result", publish)

  window.analysis_finished(new_tracks, {}, None)

  assert window.analyzed_raw_tracks == old_tracks
  start_playlist.assert_not_called()

  # Echter AI-finished-Slot darf im terminalen Zustand keinen Playlist-Worker
  # mehr anlegen, auch wenn der Callback verspätet zugestellt wird.
  monkeypatch.setattr(
    window, "on_ai_worker_finished", real_on_ai_worker_finished
  )
  assert window.playlist_worker is None
  window.on_ai_worker_finished(ai_completed=False)
  assert window.playlist_worker is None

  playlist_worker = Mock()
  window.playlist_worker = playlist_worker
  result = SimpleNamespace(tracks=tuple(new_tracks))
  publish = Mock()
  monkeypatch.setattr(window, "_publiziere_generation_result", publish)
  window._on_playlist_generation_done(result, playlist_worker)
  window._on_playlist_generation_failed("queued", playlist_worker)

  publish.assert_not_called()
  assert window.run_state == main.RunState.CANCELLED


def test_close_gate_erfasst_peak_worker_bis_stopp_bestaetigt(
  qtbot, monkeypatch
):
  class PeakWorkerDouble:
    def __init__(self):
      self.isRunning = Mock(return_value=True)
      self.wait = Mock(return_value=False)
      self.requestInterruption = Mock()
      self.deleteLater = Mock()

  window = _window(qtbot, monkeypatch)
  worker = PeakWorkerDouble()
  main._PEAK_WORKERS.add(worker)
  monkeypatch.setattr(main.QTimer, "singleShot", Mock())
  try:
    first_event = Mock()
    window.closeEvent(first_event)
    first_event.ignore.assert_called_once_with()
    first_event.accept.assert_not_called()
    worker.requestInterruption.assert_called_once_with()
    worker.wait.assert_called_once_with(50)

    worker.isRunning.return_value = False
    worker.wait.return_value = True
    second_event = Mock()
    window.closeEvent(second_event)
    second_event.accept.assert_called_once_with()

    main._cleanup_peak_worker(worker)
    assert worker not in main._PEAK_WORKERS
    worker.deleteLater.assert_called_once_with()
  finally:
    main._PEAK_WORKERS.discard(worker)


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
    window = main.MainWindow(settings=_MemorySettings())
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
  quelle = "TransitionPlan · Kandidat Rang 1"
  assert mixpunkte_fuer_tabelle(0, t0, recs) == (60.0, "Analyse", 192.0, quelle)
  assert mixpunkte_fuer_tabelle(1, t1, recs) == (82.3, quelle, 210.0, "Analyse")
  assert mixpunkte_fuer_tabelle(1, t1, []) == (50.0, "Analyse", 210.0, "Analyse")
  # TransitionPlan bleibt SSOT, auch ohne Kandidatenrang.
  recs0 = [SimpleNamespace(plan=SimpleNamespace(mix_out_a=1.0, mix_in_b=2.0), kandidat_aktiv=0)]
  assert mixpunkte_fuer_tabelle(0, t0, recs0) == (60.0, "Analyse", 1.0, "TransitionPlan")
  sparse = [SimpleNamespace(
    index=1, plan=SimpleNamespace(mix_out_a=180.0, mix_in_b=70.0), kandidat_aktiv=2,
  )]
  assert mixpunkte_fuer_tabelle(0, t0, sparse) == (60.0, "Analyse", 200.0, "Analyse")
  assert mixpunkte_fuer_tabelle(1, t1, sparse)[2:] == (
    180.0, "TransitionPlan · Kandidat Rang 2"
  )



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


def _panel_generation_result(rec, metrics, occurrence_ids=(("run", 0), ("run", 1))):
  occurrences = tuple(
    SimpleNamespace(occurrence_id=occurrence_id, track=track)
    for occurrence_id, track in zip(
      occurrence_ids, (rec.from_track, rec.to_track), strict=True
    )
  )
  recommendation = SimpleNamespace(plan=rec.plan)
  boundary = SimpleNamespace(
    index=0,
    from_occurrence_id=occurrence_ids[0],
    to_occurrence_id=occurrence_ids[1],
    recommendation=recommendation,
    metrics=metrics,
  )
  return SimpleNamespace(
    occurrences=occurrences,
    boundaries=(boundary,),
  )


def test_playlist_result_zeigt_autoritative_zehn_paarmetriken_im_tooltip(
  qtbot, monkeypatch
):
  rec = _rec_mit_kandidaten(index=0)
  metrics = SimpleNamespace(
    harmonic_score=83,
    bpm_smoothness=0.71,
    energy_flow=0.62,
    genre_compatibility=0.53,
    groove_match=0.44,
    bass_continuity=0.35,
    timbre_match=0.26,
    mood_match=0.17,
    loudness_match=0.88,
    structure_match=0.99,
  )
  result = _panel_generation_result(rec, metrics)
  monkeypatch.setattr(
    main, "calculate_enhanced_compatibility",
    Mock(side_effect=AssertionError("Result-Metriken duerfen nicht neu berechnet werden")),
  )
  panel = main.PlaylistPanel()
  qtbot.addWidget(panel)

  panel.set_playlist_data(
    [rec.from_track, rec.to_track], {}, [rec], generation_result=result
  )

  assert panel.table.item(1, 14).toolTip().splitlines() == [
    "Passung im Detail:",
    "Harmonik: 83 %",
    "BPM: 71 %",
    "Energie: 62 %",
    "Genre: 53 %",
    "Groove: 44 %",
    "Bassdruck: 35 %",
    "Klangfarbe: 26 %",
    "Stimmung: 17 %",
    "Lautheit: 88 %",
    "Struktur: 99 %",
  ]


def test_playlist_result_tooltip_folgt_neu_publizierter_reorder_kante(qtbot):
  import dataclasses

  rec = _rec_mit_kandidaten(index=0)
  panel = main.PlaylistPanel()
  qtbot.addWidget(panel)
  alt = SimpleNamespace(
    harmonic_score=81, bpm_smoothness=0.80, energy_flow=0.79,
    genre_compatibility=0.78, groove_match=0.77, bass_continuity=0.76,
    timbre_match=0.75, mood_match=0.74, loudness_match=0.73,
    structure_match=0.72,
  )
  panel.set_playlist_data(
    [rec.from_track, rec.to_track], {}, [rec],
    generation_result=_panel_generation_result(rec, alt),
  )
  assert "Harmonik: 81 %" in panel.table.item(1, 14).toolTip()

  reordered = dataclasses.replace(
    rec, from_track=rec.to_track, to_track=rec.from_track
  )
  neu = SimpleNamespace(
    harmonic_score=63, bpm_smoothness=0.62, energy_flow=0.61,
    genre_compatibility=0.60, groove_match=0.59, bass_continuity=0.58,
    timbre_match=0.57, mood_match=0.56, loudness_match=0.55,
    structure_match=0.54,
  )
  panel.set_playlist_data(
    [reordered.from_track, reordered.to_track], {}, [reordered],
    generation_result=_panel_generation_result(
      reordered, neu, (("run", 1), ("run", 0))
    ),
  )

  tooltip = panel.table.item(1, 14).toolTip()
  assert "Harmonik: 63 %" in tooltip
  assert "Harmonik: 81 %" not in tooltip


def test_playlist_result_verwirft_fremde_oder_planlose_detailmetrik(qtbot):
  import dataclasses

  rec = _rec_mit_kandidaten(index=0)
  metrics = SimpleNamespace(
    harmonic_score=99, bpm_smoothness=0.99, energy_flow=0.99,
    genre_compatibility=0.99, groove_match=0.99, bass_continuity=0.99,
    timbre_match=0.99, mood_match=0.99, loudness_match=0.99,
    structure_match=0.99,
  )
  panel = main.PlaylistPanel()
  qtbot.addWidget(panel)
  foreign = _panel_generation_result(rec, metrics)
  foreign.boundaries[0].to_occurrence_id = ("other", 1)
  panel.set_playlist_data(
    [rec.from_track, rec.to_track], {}, [rec], generation_result=foreign
  )
  foreign_tooltip = panel.table.item(1, 14).toolTip()
  assert "71% Passung zum vorherigen Track" in foreign_tooltip
  assert "Passung im Detail" not in foreign_tooltip

  other_tracks = [
    Track(filePath="C:/x.wav", fileName="x.wav", bpm=140.0),
    Track(filePath="C:/y.wav", fileName="y.wav", bpm=140.0),
  ]
  matching_ids = _panel_generation_result(rec, metrics)
  panel.set_playlist_data(
    other_tracks, {}, [rec], generation_result=matching_ids
  )
  assert "Passung im Detail" not in panel.table.item(1, 14).toolTip()

  unplanned = dataclasses.replace(rec, plan=None, compatibility_score=99)
  result = _panel_generation_result(unplanned, metrics)
  panel.set_playlist_data(
    [unplanned.from_track, unplanned.to_track], {}, [unplanned],
    generation_result=result,
  )
  item = panel.table.item(1, 14)
  assert item.text() == "0% · UNGEPLANT"
  assert item.toolTip().startswith("Ungeplant:")


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


def test_mix_tips_panel_sperrt_kandidatentabellen_waehrend_lauf(qtbot):
  panel = main.MixTipsPanel()
  qtbot.addWidget(panel)
  panel.set_recommendations([_rec_mit_kandidaten()])
  empfangen = []
  panel.candidate_chosen.connect(lambda i, r: empfangen.append((i, r)))

  panel.set_candidate_choices_enabled(False)
  tabelle = panel._kandidaten_tabellen[0]
  tabelle.selectRow(1)

  assert not tabelle.isEnabled()
  assert empfangen == []


def test_candidate_choice_handler_blockiert_waehrend_audio_lauf(
  qtbot, monkeypatch
):
  window = _window(qtbot, monkeypatch)
  merke = Mock()
  monkeypatch.setattr(main.candidate_choices, "merke", merke)

  window._set_run_state(main.RunState.AUDIO)
  window._on_candidate_chosen(0, 2)

  merke.assert_not_called()
  assert "laufenden Vorgangs gesperrt" in window.status_bar.status_label.text()


def test_on_candidate_chosen_merkt_wahl_und_rechnet_neu(qtbot, monkeypatch, tmp_path):
  from hpg_core import candidate_choices as cc
  monkeypatch.setenv("HPG_CANDIDATE_CHOICES_FILE", str(tmp_path / "choices.json"))
  cc.reset_cache()
  window = _window(qtbot, monkeypatch)
  rec = _rec_mit_kandidaten(index=1)
  window.playlist = [rec.from_track, rec.to_track]
  window.playlist_panel.playlist = window.playlist
  window.playlist_panel.transition_recommendations = [rec]
  aufrufe = {"berechne": 0, "verteile": 0, "verworfen": []}
  monkeypatch.setattr(window, "_berechne_uebergaenge",
                      lambda bpm, ctx: aufrufe.__setitem__("berechne", aufrufe["berechne"] + 1) or (None, {}, [rec]))
  monkeypatch.setattr(window, "_verteile_uebergaenge",
                      lambda plan, bpm, ctx, **kwargs: aufrufe.__setitem__("verteile", aufrufe["verteile"] + 1))
  monkeypatch.setattr(window.mix_tips_panel, "verwerfe_preview", lambda i: aufrufe["verworfen"].append(i))
  window._on_candidate_chosen(1, 2)
  w = cc.hole("C:/a.wav", "C:/b.wav")
  assert w and w["blend_bars"] == 32 and w["t_out"] == 164.6
  assert w["version"] == 2
  assert w["bpm_a"] == 140.0 and w["bpm_b"] == 140.0
  assert w["overlap_sec"] == 54.9
  assert aufrufe == {"berechne": 1, "verteile": 1, "verworfen": [1]}
  assert "2→3" in window.status_bar.status_label.text()
  cc.reset_cache()


def test_candidate_choice_nutzt_panel_snapshot_statt_live_controls(
  qtbot, monkeypatch, tmp_path
):
  from hpg_core import candidate_choices as cc
  monkeypatch.setenv("HPG_CANDIDATE_CHOICES_FILE", str(tmp_path / "choices.json"))
  cc.reset_cache()
  window = _window(qtbot, monkeypatch)
  rec = _rec_mit_kandidaten(index=0)
  window.playlist = [rec.from_track, rec.to_track]
  window.playlist_panel.playlist = window.playlist
  window.playlist_panel.transition_recommendations = [rec]
  window.playlist_panel.bpm_tolerance = 1.25
  window.playlist_panel.scoring_context = {"nested": {"wert": 7}}
  window.current_bpm_tolerance = 2.0
  window.current_scoring_context = {"nested": {"wert": 99}}
  gesehen = {}

  def berechne(bpm, context):
    gesehen["bpm"] = bpm
    gesehen["context"] = context
    context["nested"]["wert"] = -1
    return [], {}, [rec]

  monkeypatch.setattr(window, "_berechne_uebergaenge", berechne)
  monkeypatch.setattr(window, "_verteile_uebergaenge", lambda *args, **kwargs: None)
  monkeypatch.setattr(window.mix_tips_panel, "verwerfe_preview", lambda _index: None)

  window._on_candidate_chosen(0, 2)

  assert gesehen["bpm"] == 1.25
  assert gesehen["context"]["nested"]["wert"] == -1
  assert window.playlist_panel.scoring_context == {"nested": {"wert": 7}}
  cc.reset_cache()


def test_playlist_panel_loest_scoring_context_tief_vom_aufrufer(qtbot):
  panel = main.PlaylistPanel()
  qtbot.addWidget(panel)
  context = {"candidate_tolerances_by_genre": {"Psytrance": {"marker": 1}}}

  panel.set_playlist_data([], {}, transition_recommendations=[], scoring_context=context)
  context["candidate_tolerances_by_genre"]["Psytrance"]["marker"] = 2

  assert panel.scoring_context["candidate_tolerances_by_genre"]["Psytrance"]["marker"] == 1


def test_candidate_choice_rolls_back_persistence_on_calculation_error(
  qtbot, monkeypatch, tmp_path
):
  from hpg_core import candidate_choices as cc
  monkeypatch.setenv("HPG_CANDIDATE_CHOICES_FILE", str(tmp_path / "choices.json"))
  cc.reset_cache()
  cc.merke("C:/a.wav", "C:/b.wav", t_out=10.0, t_in=20.0, blend_bars=8)
  reporter = Mock()
  monkeypatch.setattr(main, "get_error_reporter", lambda: reporter)
  window = _window(qtbot, monkeypatch)
  rec = _rec_mit_kandidaten(index=0)
  window.playlist = [rec.from_track, rec.to_track]
  window.playlist_panel.playlist = window.playlist
  window.playlist_panel.transition_recommendations = [rec]
  monkeypatch.setattr(
    window, "_berechne_uebergaenge",
    Mock(side_effect=RuntimeError("Berechnung fehlgeschlagen")),
  )

  window._on_candidate_chosen(0, 2)

  assert cc.hole("C:/a.wav", "C:/b.wav")["blend_bars"] == 8
  assert "fehlgeschlagen" in window.status_bar.status_label.text()
  reporter.log_error.assert_called_once()
  cc.reset_cache()


def test_candidate_choice_handles_initial_persistence_error(qtbot, monkeypatch):
  reporter = Mock()
  monkeypatch.setattr(main, "get_error_reporter", lambda: reporter)
  window = _window(qtbot, monkeypatch)
  rec = _rec_mit_kandidaten(index=0)
  window.playlist_panel.transition_recommendations = [rec]
  monkeypatch.setattr(main.candidate_choices, "hole", lambda *args: None)
  vergiss = Mock()
  monkeypatch.setattr(main.candidate_choices, "vergiss", vergiss)
  monkeypatch.setattr(
    main.candidate_choices, "merke", Mock(side_effect=OSError("Datei gesperrt"))
  )
  berechne = Mock()
  monkeypatch.setattr(window, "_berechne_uebergaenge", berechne)

  window._on_candidate_chosen(0, 2)

  berechne.assert_not_called()
  vergiss.assert_not_called()
  assert "fehlgeschlagen" in window.status_bar.status_label.text()
  reporter.log_error.assert_called_once()


def test_candidate_choice_does_not_retry_when_persistence_throws(qtbot, monkeypatch):
  reporter = Mock()
  monkeypatch.setattr(main, "get_error_reporter", lambda: reporter)
  window = _window(qtbot, monkeypatch)
  rec = _rec_mit_kandidaten(index=0)
  window.playlist_panel.transition_recommendations = [rec]
  alte_wahl = {"t_out": 10.0, "t_in": 20.0, "blend_bars": 8}
  monkeypatch.setattr(main.candidate_choices, "hole", lambda *args: alte_wahl)
  merke = Mock(side_effect=OSError("Schreibvorgang fehlgeschlagen"))
  monkeypatch.setattr(main.candidate_choices, "merke", merke)

  window._on_candidate_chosen(0, 2)

  merke.assert_called_once()
  assert "fehlgeschlagen" in window.status_bar.status_label.text()
  reporter.log_error.assert_called_once()


def test_candidate_choice_reports_failed_rollback_without_crashing(qtbot, monkeypatch):
  reporter = Mock()
  monkeypatch.setattr(main, "get_error_reporter", lambda: reporter)
  window = _window(qtbot, monkeypatch)
  rec = _rec_mit_kandidaten(index=0)
  window.playlist_panel.transition_recommendations = [rec]
  rollback_state = object()
  monkeypatch.setattr(
    main.candidate_choices,
    "merke",
    Mock(return_value=rollback_state),
  )
  restore = Mock(side_effect=OSError("Rollback-Datei gesperrt"))
  monkeypatch.setattr(main.candidate_choices, "stelle_wieder_her", restore)
  monkeypatch.setattr(
    window, "_berechne_uebergaenge",
    Mock(side_effect=RuntimeError("Berechnung fehlgeschlagen")),
  )

  window._on_candidate_chosen(0, 2)

  restore.assert_called_once_with(rollback_state)
  assert "Rollback fehlgeschlagen" in window.status_bar.status_label.text()
  assert reporter.log_error.call_count == 2


def test_candidate_choice_rolls_back_after_distribution_error(
  qtbot, monkeypatch, tmp_path
):
  from hpg_core import candidate_choices as cc
  monkeypatch.setenv("HPG_CANDIDATE_CHOICES_FILE", str(tmp_path / "choices.json"))
  cc.reset_cache()
  cc.merke("C:/a.wav", "C:/b.wav", t_out=10.0, t_in=20.0, blend_bars=8)
  reporter = Mock()
  monkeypatch.setattr(main, "get_error_reporter", lambda: reporter)
  window = _window(qtbot, monkeypatch)
  rec = _rec_mit_kandidaten(index=0)
  window.playlist_panel.transition_recommendations = [rec]
  monkeypatch.setattr(
    window, "_berechne_uebergaenge", lambda *args: ([], {}, [rec])
  )
  monkeypatch.setattr(
    window, "_verteile_uebergaenge",
    Mock(side_effect=RuntimeError("Verteilung fehlgeschlagen")),
  )

  window._on_candidate_chosen(0, 2)

  assert cc.hole("C:/a.wav", "C:/b.wav")["blend_bars"] == 8
  assert "fehlgeschlagen" in window.status_bar.status_label.text()
  reporter.log_error.assert_called_once()
  cc.reset_cache()


@pytest.mark.parametrize(
  ("panel_type", "method_name"),
  [
    (main.PlaylistPanel, "set_playlist_data"),
    (main.MixTipsPanel, "set_recommendations"),
    (main.MixTipsPanel, "setup_transition_previews"),
    (main.TimelinePanel, "set_timeline"),
    (main.AnalyticsPanel, "set_analytics"),
    (main.ToolbarWidget, "set_quality"),
  ],
)
def test_transition_publish_prepare_error_preserves_complete_old_state(
  qtbot, monkeypatch, tmp_path, panel_type, method_name
):
  from hpg_core.playlist import generate_playlist_result

  window = _window(qtbot, monkeypatch)
  old_track = Track(
    filePath="C:/old.wav", fileName="old.wav", bpm=128.0, duration=300.0
  )
  new_track = Track(
    filePath="C:/new.wav", fileName="new.wav", bpm=130.0, duration=300.0
  )
  old_result = generate_playlist_result([old_track], "Harmonic Flow", 2.0)
  new_result = generate_playlist_result([new_track], "Harmonic Flow", 2.0)
  window._publiziere_generation_result(old_result)
  old_panels = (
    window.playlist_panel,
    window.mix_tips_panel,
    window.timeline_panel,
    window.analytics_panel,
    window.toolbar,
  )
  old_mix = window.mix_tips_panel
  preview_dir = tmp_path / "old-preview"
  preview_dir.mkdir()
  preview_wav = preview_dir / "old.wav"
  preview_wav.write_bytes(b"wav")
  old_mix._preview_cache[0] = str(preview_wav)
  old_mix._preview_temp_dirs.add(str(preview_dir))
  worker = main.TransitionRenderWorker([], old_mix)
  worker.request_cancel = Mock()
  worker.deleteLater = Mock()
  old_mix._render_worker = worker
  old_mix._render_workers = [worker]

  original_method = getattr(panel_type, method_name)

  def fail_prepare(panel, *args, **kwargs):
    original_method(panel, *args, **kwargs)
    raise RuntimeError(f"{method_name} fehlgeschlagen")

  monkeypatch.setattr(panel_type, method_name, fail_prepare)

  with pytest.raises(RuntimeError, match="fehlgeschlagen"):
    window._publiziere_generation_result(new_result)

  assert window.current_generation_result is old_result
  assert window.playlist_panel.generation_result is old_result
  current_panels = (
    window.playlist_panel, window.mix_tips_panel, window.timeline_panel,
    window.analytics_panel, window.toolbar,
  )
  assert all(current is old for current, old in zip(current_panels, old_panels))
  assert window.playlist == [old_track]
  assert preview_wav.exists()
  assert old_mix._preview_cache == {0: str(preview_wav)}
  assert old_mix._render_worker is worker
  assert old_mix._render_workers == [worker]
  worker.request_cancel.assert_not_called()
  worker.deleteLater.assert_not_called()


def test_transition_publish_success_releases_old_preview_state_once(
  qtbot, monkeypatch, tmp_path
):
  from hpg_core.playlist import generate_playlist_result

  window = _window(qtbot, monkeypatch)
  old_result = generate_playlist_result(
    [Track(filePath="C:/old.wav", fileName="old.wav", bpm=128.0, duration=300.0)],
    "Harmonic Flow",
    2.0,
  )
  new_result = generate_playlist_result(
    [Track(filePath="C:/new.wav", fileName="new.wav", bpm=130.0, duration=300.0)],
    "Harmonic Flow",
    2.0,
  )
  window._publiziere_generation_result(old_result)
  old_mix = window.mix_tips_panel
  preview_dir = tmp_path / "old-preview"
  preview_dir.mkdir()
  preview_wav = preview_dir / "old.wav"
  preview_wav.write_bytes(b"wav")
  old_mix._preview_cache[0] = str(preview_wav)
  old_mix._preview_temp_dirs.add(str(preview_dir))
  cleanup = Mock(wraps=old_mix._cleanup_existing_previews)
  monkeypatch.setattr(old_mix, "_cleanup_existing_previews", cleanup)

  window._publiziere_generation_result(new_result)

  assert window.current_generation_result is new_result
  assert window.mix_tips_panel is not old_mix
  cleanup.assert_called_once_with()
  assert old_mix._preview_cache == {}
  assert not preview_wav.exists()
  assert not preview_dir.exists()


@pytest.mark.parametrize(
  ("operation", "fail_at"),
  [
    ("remove", 1), ("remove", 2), ("remove", 3), ("remove", 4),
    ("insert", 1), ("insert", 2), ("insert", 3), ("insert", 4),
    ("toolbar", 1),
  ],
)
def test_transition_publish_structure_error_restores_every_widget(
  qtbot, monkeypatch, operation, fail_at
):
  from hpg_core.playlist import generate_playlist_result

  window = _window(qtbot, monkeypatch)
  old_result = generate_playlist_result(
    [Track(filePath="C:/old.wav", fileName="old.wav", bpm=128.0, duration=300.0)],
    "Harmonic Flow", 2.0,
  )
  new_result = generate_playlist_result(
    [Track(filePath="C:/new.wav", fileName="new.wav", bpm=130.0, duration=300.0)],
    "Harmonic Flow", 2.0,
  )
  window._publiziere_generation_result(old_result)
  old_panels = (
    window.playlist_panel, window.mix_tips_panel,
    window.timeline_panel, window.analytics_panel,
  )
  old_toolbar = window.toolbar
  prepared = []
  original_prepare = window._prepare_uebergangs_views

  def remember_prepared(*args, **kwargs):
    value = original_prepare(*args, **kwargs)
    prepared.append(value)
    return value

  monkeypatch.setattr(window, "_prepare_uebergangs_views", remember_prepared)
  target = (
    window.content_stack.removeWidget
    if operation == "remove"
    else window.content_stack.insertWidget
    if operation == "insert"
    else window._right_layout.replaceWidget
  )
  calls = 0

  def fail_after_structure_step(*args, **kwargs):
    nonlocal calls
    result = target(*args, **kwargs)
    calls += 1
    if calls == fail_at:
      raise RuntimeError(f"{operation}-{fail_at} fehlgeschlagen")
    return result

  if operation == "remove":
    monkeypatch.setattr(window.content_stack, "removeWidget", fail_after_structure_step)
  elif operation == "insert":
    monkeypatch.setattr(window.content_stack, "insertWidget", fail_after_structure_step)
  else:
    monkeypatch.setattr(window._right_layout, "replaceWidget", fail_after_structure_step)

  with pytest.raises(RuntimeError, match="fehlgeschlagen"):
    window._publiziere_generation_result(new_result)

  assert window.current_generation_result is old_result
  assert window.playlist_panel is old_panels[0]
  assert window.mix_tips_panel is old_panels[1]
  assert window.timeline_panel is old_panels[2]
  assert window.analytics_panel is old_panels[3]
  assert window.toolbar is old_toolbar
  assert tuple(window.content_stack.widget(index) for index in range(1, 5)) == old_panels
  assert window._right_layout.indexOf(old_toolbar) >= 0
  for widget in prepared[0]:
    assert window.content_stack.indexOf(widget) < 0
    assert window._right_layout.indexOf(widget) < 0


def test_transition_publish_retirement_error_does_not_reject_commit(
  qtbot, monkeypatch
):
  from hpg_core.playlist import generate_playlist_result

  class SlowRenderWorker(QThread):
    def run(self):
      self.msleep(250)

    def request_cancel(self):
      pass

    def get_temp_dir(self):
      return None

    def get_temp_files(self):
      return []

  reporter = Mock()
  monkeypatch.setattr(main, "get_error_reporter", lambda: reporter)
  window = _window(qtbot, monkeypatch)
  old_result = generate_playlist_result(
    [Track(filePath="C:/old.wav", fileName="old.wav", bpm=128.0, duration=300.0)],
    "Harmonic Flow", 2.0,
  )
  new_result = generate_playlist_result(
    [Track(filePath="C:/new.wav", fileName="new.wav", bpm=130.0, duration=300.0)],
    "Harmonic Flow", 2.0,
  )
  window._publiziere_generation_result(old_result)
  old_mix = window.mix_tips_panel
  worker = SlowRenderWorker(old_mix)
  old_mix._render_worker = worker
  old_mix._render_workers = [worker]
  worker.finished.connect(
    lambda source=worker: old_mix._on_preview_worker_finished(source)
  )
  worker.start()
  qtbot.waitUntil(worker.isRunning, timeout=1000)
  monkeypatch.setattr(
    old_mix, "_cleanup_existing_previews",
    Mock(side_effect=RuntimeError("Retirement fehlgeschlagen")),
  )

  window._publiziere_generation_result(new_result)

  assert window.current_generation_result is new_result
  assert window.mix_tips_panel is not old_mix
  assert old_mix in window._retired_mix_tips_panels
  assert worker in window._managed_workers_for_close()
  reporter.log_error.assert_called_once()
  qtbot.waitUntil(
    lambda: old_mix not in window._retired_mix_tips_panels,
    timeout=2000,
  )


def test_transition_publish_keeps_retired_running_worker_until_finished(
  qtbot, monkeypatch
):
  from hpg_core.playlist import generate_playlist_result

  class SlowRenderWorker(QThread):
    def __init__(self, parent):
      super().__init__(parent)
      self.cancel_calls = 0

    def run(self):
      self.msleep(250)

    def request_cancel(self):
      self.cancel_calls += 1

    def get_temp_dir(self):
      return None

    def get_temp_files(self):
      return []

  window = _window(qtbot, monkeypatch)
  old_result = generate_playlist_result(
    [Track(filePath="C:/old.wav", fileName="old.wav", bpm=128.0, duration=300.0)],
    "Harmonic Flow", 2.0,
  )
  new_result = generate_playlist_result(
    [Track(filePath="C:/new.wav", fileName="new.wav", bpm=130.0, duration=300.0)],
    "Harmonic Flow", 2.0,
  )
  window._publiziere_generation_result(old_result)
  old_mix = window.mix_tips_panel
  worker = SlowRenderWorker(old_mix)
  old_mix._render_worker = worker
  old_mix._render_workers = [worker]
  worker.finished.connect(
    lambda source=worker: old_mix._on_preview_worker_finished(source)
  )
  worker.start()
  qtbot.waitUntil(worker.isRunning, timeout=1000)

  window._publiziere_generation_result(new_result)

  assert old_mix in window._retired_mix_tips_panels
  assert worker in window._managed_workers_for_close()
  assert worker.cancel_calls == 1
  qtbot.waitUntil(
    lambda: old_mix not in window._retired_mix_tips_panels,
    timeout=2000,
  )
  assert worker not in old_mix._render_workers


def test_reorder_late_calculation_error_restores_table(qtbot, monkeypatch):
  reporter = Mock()
  monkeypatch.setattr(main, "get_error_reporter", lambda: reporter)
  rec = _rec_mit_kandidaten(index=0)
  panel = main.PlaylistPanel()
  qtbot.addWidget(panel)
  old_playlist = [rec.from_track, rec.to_track]
  panel.set_playlist_data(old_playlist, {"overall_score": 0.5}, [rec])
  monkeypatch.setattr(
    main, "calculate_playlist_quality",
    Mock(side_effect=RuntimeError("Quality fehlgeschlagen")),
  )
  failed, reordered = [], []
  panel.reorder_failed.connect(failed.append)
  panel.playlist_reordered.connect(lambda _snapshot: reordered.append(True))

  _move_table_rows(panel)

  assert panel.playlist == old_playlist
  assert [panel.table.item(i, 1).text() for i in range(2)] == [
    rec.from_track.fileName, rec.to_track.fileName,
  ]
  assert failed == ["Quality fehlgeschlagen"]
  assert reordered == []


def test_reorder_downstream_error_restores_main_panel_and_views(qtbot, monkeypatch):
  reporter = Mock()
  monkeypatch.setattr(main, "get_error_reporter", lambda: reporter)
  window = _window(qtbot, monkeypatch)
  old_rec = _rec_mit_kandidaten(index=0)
  old_playlist = [old_rec.from_track, old_rec.to_track]
  old_quality = {"overall_score": 0.4}
  window.playlist = old_playlist
  window.quality_metrics = old_quality
  window.playlist_panel.set_playlist_data(
    old_playlist, old_quality, [old_rec], bpm_tolerance=2.0,
  )
  old_panels = (
    window.playlist_panel, window.mix_tips_panel,
    window.timeline_panel, window.analytics_panel, window.toolbar,
  )
  original_timeline = main.TimelinePanel.set_timeline

  def fail_after_timeline(panel, *args, **kwargs):
    original_timeline(panel, *args, **kwargs)
    raise RuntimeError("Timeline fehlgeschlagen")

  monkeypatch.setattr(main.TimelinePanel, "set_timeline", fail_after_timeline)

  _move_table_rows(window.playlist_panel)

  assert window.playlist == old_playlist
  assert window.quality_metrics == old_quality
  assert window.playlist_panel.playlist == old_playlist
  assert window.playlist_panel.quality_metrics == old_quality
  assert window.playlist_panel.transition_recommendations == [old_rec]
  current_panels = (
    window.playlist_panel, window.mix_tips_panel,
    window.timeline_panel, window.analytics_panel, window.toolbar,
  )
  assert all(current is old for current, old in zip(current_panels, old_panels))
  assert "unveraenderte" in window.status_bar.status_label.text()
  assert sum(
    call.args[0] == "playlist_reorder_views"
    for call in reporter.log_error.call_args_list
  ) == 1


@pytest.mark.parametrize("failure_stage", ["prepare", "commit"])
def test_result_reorder_publish_error_does_not_republish_old_result(
  qtbot, monkeypatch, failure_stage
):
  from hpg_core.playlist import generate_playlist_result

  reporter = Mock()
  monkeypatch.setattr(main, "get_error_reporter", lambda: reporter)
  window = _window(qtbot, monkeypatch)
  old_result = generate_playlist_result(
    [
      Track(filePath="C:/a.wav", fileName="a.wav", bpm=128.0, duration=300.0),
      Track(filePath="C:/b.wav", fileName="b.wav", bpm=129.0, duration=300.0),
    ],
    "Harmonic Flow",
    2.0,
  )
  window._publiziere_generation_result(old_result)
  old_panels = (window.playlist_panel, window.mix_tips_panel, window.toolbar)
  old_rows = _playlist_table_item_snapshot(window.playlist_panel.table)
  if failure_stage == "prepare":
    monkeypatch.setattr(
      window, "_prepare_uebergangs_views",
      Mock(side_effect=RuntimeError("Neu fehlgeschlagen")),
    )
  else:
    original_insert = window.content_stack.insertWidget
    insert_calls = 0

    def fail_after_insert(*args, **kwargs):
      nonlocal insert_calls
      result = original_insert(*args, **kwargs)
      insert_calls += 1
      if insert_calls == 1:
        raise RuntimeError("Commit fehlgeschlagen")
      return result

    monkeypatch.setattr(window.content_stack, "insertWidget", fail_after_insert)
  publish = Mock(wraps=window._publiziere_generation_result)
  monkeypatch.setattr(window, "_publiziere_generation_result", publish)

  _move_table_rows(window.playlist_panel)

  publish.assert_called_once()
  assert window.current_generation_result is old_result
  assert window.playlist_panel is old_panels[0]
  assert window.mix_tips_panel is old_panels[1]
  assert window.toolbar is old_panels[2]
  restored_rows = _playlist_table_item_snapshot(window.playlist_panel.table)
  assert restored_rows == old_rows
  assert "unveraenderte" in window.status_bar.status_label.text()
  reporter.log_error.assert_called_once()


@pytest.mark.parametrize(
  "stage", ["replace_before", "replace_after", "hide", "detach", "delete"]
)
def test_reorder_table_snapshot_survives_each_retirement_step_error(
  qtbot, monkeypatch, stage
):
  panel = main.PlaylistPanel()
  qtbot.addWidget(panel)
  tracks = [
    Track(filePath="C:/a.wav", fileName="a.wav", bpm=128.0),
    Track(filePath="C:/b.wav", fileName="b.wav", bpm=129.0),
  ]
  panel.set_playlist_data(tracks, {})
  old_rows = tuple(panel.table.item(row, 1).text() for row in range(2))
  moved_table = panel.table

  if stage.startswith("replace"):
    original = panel.layout().replaceWidget

    def fail_after(*args, **kwargs):
      result = None
      if stage == "replace_after":
        result = original(*args, **kwargs)
      raise RuntimeError("replace fehlgeschlagen")

    monkeypatch.setattr(panel.layout(), "replaceWidget", fail_after)
  else:
    method_name = {"hide": "hide", "detach": "setParent", "delete": "deleteLater"}[stage]
    original = getattr(moved_table, method_name)

    def fail_after(*args, **kwargs):
      result = original(*args, **kwargs)
      raise RuntimeError(f"{stage} fehlgeschlagen")

    monkeypatch.setattr(moved_table, method_name, fail_after)

  assert moved_table.model().moveRows(
    QModelIndex(), 0, 1, QModelIndex(), 2
  ) is True

  assert panel.table is not moved_table
  assert tuple(panel.table.item(row, 1).text() for row in range(2)) == old_rows


def test_reorder_slot_without_about_to_move_snapshot_fails_closed(qtbot):
  panel = main.PlaylistPanel()
  qtbot.addWidget(panel)
  panel.set_playlist_data(
    [Track(filePath="C:/a.wav", fileName="a.wav", bpm=128.0)], {}
  )

  with pytest.raises(RuntimeError, match="rowsMoved ohne rowsAboutToBeMoved"):
    panel._on_rows_moved()


@pytest.mark.parametrize("with_result", [False, True])
def test_qt_model_move_emits_about_before_and_moved_after_mutation(
  qtbot, with_result
):
  from hpg_core.playlist import generate_playlist_result, legacy_transition_recommendations

  panel = main.PlaylistPanel()
  qtbot.addWidget(panel)
  tracks = [
    Track(filePath="C:/a.wav", fileName="a.wav", bpm=128.0, duration=300.0),
    Track(filePath="C:/b.wav", fileName="b.wav", bpm=129.0, duration=300.0),
  ]
  if with_result:
    result = generate_playlist_result(tracks, "Harmonic Flow", 2.0)
    panel.set_playlist_data(
      tracks, result.quality_dict(), legacy_transition_recommendations(result),
      bpm_tolerance=2.0, scoring_context=result.scoring_context_dict(),
      generation_result=result,
    )
  else:
    panel.set_playlist_data(tracks, {})
  source_table = panel.table
  events = []
  source_table.model().rowsAboutToBeMoved.connect(
    lambda *_args: events.append(
      ("about", tuple(source_table.item(row, 1).text() for row in range(2)))
    )
  )
  source_table.model().rowsMoved.connect(
    lambda *_args: events.append(
      ("moved", tuple(source_table.item(row, 1).text() for row in range(2)))
    )
  )

  assert source_table.model().moveRows(
    QModelIndex(), 0, 1, QModelIndex(), 2
  ) is True

  assert events == [
    ("about", ("a.wav", "b.wav")),
    ("moved", ("b.wav", "a.wav")),
  ]
  assert tuple(panel.table.item(row, 1).text() for row in range(2)) == (
    "a.wav", "b.wav",
  )


def test_app_bpm_default_ist_zwei(qtbot, monkeypatch):
  window = _window(qtbot, monkeypatch)
  assert window.library_panel.bpm_tolerance_slider.value() == 2
  assert window.library_panel.bpm_value_label.text() == "\u00b12"
  assert window.current_bpm_tolerance == 2.0
  assert window.playlist_panel.bpm_tolerance == 2.0


def test_gui_settings_roundtrip_validiert_und_wird_weitergeleitet(
  qtbot, monkeypatch, tmp_path
):
  monkeypatch.setattr(main.MainWindow, "check_dependencies_and_warn", lambda self: None)
  monkeypatch.setattr(
    main.AdvancedParametersWidget, "refresh_ai_providers", lambda self: None
  )
  settings_path = tmp_path / "gui.ini"
  first = main.MainWindow(
    settings=QSettings(str(settings_path), QSettings.Format.IniFormat)
  )
  qtbot.addWidget(first)
  ap = first.library_panel.advanced_params
  first.library_panel.set_folder_path(str(tmp_path))
  first.library_panel.strategy_combo.setCurrentText("Context Flow")
  first.library_panel.bpm_tolerance_slider.setValue(1)
  ap.energy_direction.setCurrentText("Build Up")
  ap.peak_position_slider.setValue(63)
  ap.harmonic_strictness.setValue(9)
  ap.allow_experimental.setChecked(False)
  ap.genre_mixing.setChecked(False)
  ap.genre_weight.setValue(44)
  ap.lmstudio_radio.setChecked(True)
  ap.model_combo.addItem("local-model")
  ap.model_combo.setCurrentText("local-model")
  assert first._save_ui_settings()

  second = main.MainWindow(
    settings=QSettings(str(settings_path), QSettings.Format.IniFormat)
  )
  qtbot.addWidget(second)
  restored = second.library_panel.get_current_settings()
  restored_ap = second.library_panel.advanced_params
  assert restored["folder"] == str(tmp_path)
  assert restored["strategy"] == "Context Flow"
  assert restored["bpm_tolerance"] == 1.0
  assert restored["advanced_params"] == {
    "ai_enabled": False,
    "energy_direction": "Build Up",
    "peak_position": 63,
    "harmonic_strictness": 9,
    "allow_experimental": False,
    "genre_mixing": False,
    "genre_weight": 0.44,
  }
  assert restored_ap.lmstudio_radio.isChecked()
  assert restored_ap.model_combo.currentText() == "local-model"

  class _Signal:
    def connect(self, _slot):
      pass

  captured = {}

  class _AnalysisWorker:
    def __init__(self, **kwargs):
      captured.update(kwargs)
      for name in (
        "progress", "phase_changed", "status_update", "rekordbox_coverage",
        "analysis_issues", "analysis_done", "finished",
      ):
        setattr(self, name, _Signal())
      self.start = Mock()

    def isRunning(self):
      return False

  monkeypatch.setattr(main, "AnalysisWorker", _AnalysisWorker)
  second.start_analysis()
  assert captured == {"folder_path": str(tmp_path)}
  assert second._run_settings["ai_enabled"] is False
  assert second._run_settings["ai_provider"] == "LM Studio"
  assert second._run_settings["ai_model"] == "local-model"
  assert "candidate_tolerances_by_genre" in second._run_settings["scoring_context"]
  assert "Unknown" in second._run_settings["scoring_context"]["candidate_tolerances_by_genre"]
  second.library_panel.advanced_params.harmonic_strictness.setValue(1)
  assert second._run_settings["advanced_params"]["harmonic_strictness"] == 9


def test_laufsnapshot_verwirft_erkannten_endpoint_des_vorherigen_providers(
  qtbot, monkeypatch, tmp_path
):
  window = _window(qtbot, monkeypatch)
  window.library_panel.set_folder_path(str(tmp_path))
  advanced = window.library_panel.advanced_params
  advanced.detected_provider = "Ollama"
  advanced.detected_base_url = "http://127.0.0.1:11434/api/generate"
  advanced.lmstudio_radio.blockSignals(True)
  advanced.lmstudio_radio.setChecked(True)
  advanced.lmstudio_radio.blockSignals(False)

  class _Signal:
    def connect(self, _slot):
      pass

  class _AnalysisWorker:
    def __init__(self, **_kwargs):
      for name in (
        "progress", "phase_changed", "status_update", "rekordbox_coverage",
        "analysis_issues", "analysis_done", "finished",
      ):
        setattr(self, name, _Signal())
      self.start = Mock()

    def isRunning(self):
      return False

  monkeypatch.setattr(main, "AnalysisWorker", _AnalysisWorker)

  window.start_analysis()

  assert window._run_settings["ai_provider"] == "LM Studio"
  assert window._run_settings["ai_base_url"] is None


def test_laufsnapshot_bleibt_bis_generate_und_publish_unveraendert(
  qtbot, monkeypatch, tmp_path, request
):
  from copy import deepcopy

  from hpg_core import candidate_preferences

  monkeypatch.setenv(
    "HPG_CANDIDATE_PREFERENCES_FILE", str(tmp_path / "preferences.json")
  )
  candidate_preferences.reset_cache()
  request.addfinalizer(candidate_preferences.reset_cache)
  keys = candidate_preferences.GEWICHT_SCHLUESSEL
  start_weights = {key: 0.1 for key in keys}
  changed_weights = {
    key: (0.19 if index == 0 else 0.09)
    for index, key in enumerate(keys)
  }
  start_schema = ["sektion", "analyzer"]
  changed_schema = ["benannter_cue", "pssi_phrase"]
  candidate_preferences.merge_user_preferences_atomically({
    "Psytrance": {**start_weights, "schema_rang": start_schema}
  })

  window = _window(qtbot, monkeypatch)
  window.library_panel.set_folder_path(str(tmp_path))

  class _Signal:
    def connect(self, _slot):
      pass

  class _AnalysisWorker:
    def __init__(self, **_kwargs):
      for name in (
        "progress", "phase_changed", "status_update", "rekordbox_coverage",
        "analysis_issues", "analysis_done", "finished",
      ):
        setattr(self, name, _Signal())
      self.start = Mock()

    def isRunning(self):
      return False

  monkeypatch.setattr(main, "AnalysisWorker", _AnalysisWorker)
  window.start_analysis()
  start_context = deepcopy(window._run_settings["scoring_context"])
  assert {
    key: start_context["candidate_tolerances_by_genre"]["Psytrance"][key]
    for key in keys
  } == start_weights
  assert start_context["candidate_schema_ranks_by_genre"]["Psytrance"] == start_schema

  candidate_preferences.merge_user_preferences_atomically({
    "Psytrance": {**changed_weights, "schema_rang": changed_schema}
  })
  assert candidate_preferences.kandidaten_gewichte("Psytrance") == changed_weights
  assert candidate_preferences.schema_rangfolge("Psytrance") == changed_schema

  tracks = [Track(filePath="C:/a.wav", fileName="a.wav", bpm=128.0)]
  window.analyzed_raw_tracks = tracks
  generated = {}

  def _generate(*_args, scoring_context, **_kwargs):
    generated["context"] = deepcopy(scoring_context)
    return SimpleNamespace(
      tracks=tuple(tracks),
      scoring_context_dict=lambda: deepcopy(scoring_context),
    )

  published = {}

  def _publish(result):
    published["result"] = result
    window.playlist = list(result.tracks)
    window.quality_metrics = {}

  monkeypatch.setattr("hpg_core.playlist.generate_playlist_result", _generate)
  monkeypatch.setattr(window, "_publiziere_generation_result", _publish)
  window.on_ai_worker_finished(ai_completed=False, finalize=False)
  _wait_playlist_worker(qtbot, window)

  assert generated["context"] == start_context
  assert published["result"].scoring_context_dict() == start_context
  assert window._run_settings["scoring_context"] == start_context


def test_kandidatenwahlen_sind_laufstart_snapshot_bis_playlist_generation(
  qtbot, monkeypatch, tmp_path
):
  window = _window(qtbot, monkeypatch)
  window.library_panel.set_folder_path(str(tmp_path))
  live_snapshot = {
    ("C:/a.wav", "C:/b.wav"): {
      "t_out": 10.0, "t_in": 20.0, "blend_bars": 8
    }
  }
  monkeypatch.setattr(
    main.candidate_choices, "snapshot", lambda: live_snapshot
  )

  class _Signal:
    def connect(self, _slot):
      pass

  class _AnalysisWorker:
    def __init__(self, **_kwargs):
      for name in (
        "progress", "phase_changed", "status_update", "rekordbox_coverage",
        "analysis_issues", "analysis_done", "finished",
      ):
        setattr(self, name, _Signal())
      self.start = Mock()

    def isRunning(self):
      return False

  monkeypatch.setattr(main, "AnalysisWorker", _AnalysisWorker)
  window.start_analysis()
  run_snapshot = window._run_settings["candidate_choice_snapshot"]
  assert run_snapshot == live_snapshot
  assert run_snapshot is not live_snapshot

  live_snapshot[("C:/a.wav", "C:/b.wav")]["blend_bars"] = 32
  tracks = [Track(filePath="C:/a.wav", fileName="a.wav", bpm=128.0)]
  window.analyzed_raw_tracks = tracks
  generated = {}

  def _generate(*_args, candidate_choice_snapshot, **_kwargs):
    generated["choices"] = candidate_choice_snapshot
    return SimpleNamespace(tracks=tuple(tracks))

  monkeypatch.setattr("hpg_core.playlist.generate_playlist_result", _generate)
  monkeypatch.setattr(window, "_publiziere_generation_result", lambda _result: None)
  window.on_ai_worker_finished(ai_completed=False, finalize=False)
  _wait_playlist_worker(qtbot, window)

  assert generated["choices"][("C:/a.wav", "C:/b.wav")]["blend_bars"] == 8
  assert generated["choices"] is not run_snapshot


def test_ungueltiger_kandidaten_snapshot_verhindert_laufstart(
  qtbot, monkeypatch, tmp_path
):
  window = _window(qtbot, monkeypatch)
  window.library_panel.set_folder_path(str(tmp_path))
  monkeypatch.setattr(
    main.candidate_choices,
    "snapshot",
    Mock(side_effect=ValueError("Teilungueltige Kandidatenwahl-Datei")),
  )
  worker = Mock()
  monkeypatch.setattr(main, "AnalysisWorker", worker)

  window.start_analysis()

  worker.assert_not_called()
  assert getattr(window, "analysis_worker", None) is None
  assert "nicht gestartet" in window.status_bar.status_label.text()
  assert "Teilungueltige" in window.status_bar.status_label.text()


def test_echter_nichtleerer_kandidaten_snapshot_durchlaeuft_start_analysis(
  qtbot, monkeypatch, tmp_path
):
  from hpg_core import candidate_choices as cc

  monkeypatch.setenv(
    "HPG_CANDIDATE_CHOICES_FILE", str(tmp_path / "choices.json")
  )
  cc.reset_cache()
  cc.merke(
    "C:/a.wav", "C:/b.wav",
    t_out=10.0, t_in=2.0, blend_bars=8,
    bpm_a=138.0, bpm_b=139.0, overlap_sec=16.0,
  )
  window = _window(qtbot, monkeypatch)
  window.library_panel.set_folder_path(str(tmp_path))

  class _Signal:
    def connect(self, _slot):
      pass

  erstellt = []

  class _AnalysisWorker:
    def __init__(self, **_kwargs):
      erstellt.append(self)
      for name in (
        "progress", "phase_changed", "status_update", "rekordbox_coverage",
        "analysis_issues", "analysis_done", "finished",
      ):
        setattr(self, name, _Signal())
      self.start = Mock()

    def isRunning(self):
      return False

  monkeypatch.setattr(main, "AnalysisWorker", _AnalysisWorker)

  window.start_analysis()

  assert len(erstellt) == 1
  erstellt[0].start.assert_called_once_with()
  key = cc.schluessel("C:/a.wav", "C:/b.wav")
  assert window._run_settings["candidate_choice_snapshot"][key]["t_out"] == 10.0
  cc.reset_cache()


def test_gui_settings_verwirft_falsche_version_und_nan(qtbot, monkeypatch):
  raw = json.dumps({
    "version": 999,
    "strategy": "Nicht vorhanden",
    "bpm_tolerance": float("nan"),
  })
  window = _window(
    qtbot, monkeypatch, _MemorySettings({main.GUI_SETTINGS_KEY: raw})
  )
  assert window.library_panel.strategy_combo.currentText() == "Harmonic Flow"
  assert window.library_panel.bpm_tolerance_slider.value() == 2


@pytest.mark.parametrize("legacy, canonical", main.STRATEGY_ALIASES.items())
def test_gui_settings_migriert_strategie_alias(legacy, canonical):
  state = main.MainWindow._validated_ui_state({
    "version": main.GUI_SETTINGS_SCHEMA_VERSION,
    "strategy": legacy,
  })

  assert state["strategy"] == canonical


@pytest.mark.parametrize("invalid", ["Nicht vorhanden", ["Harmonic Flow"], {}])
def test_gui_settings_verwirft_ungueltige_strategie_ohne_absturz(invalid):
  state = main.MainWindow._validated_ui_state({
    "version": main.GUI_SETTINGS_SCHEMA_VERSION,
    "strategy": invalid,
  })

  assert "strategy" not in state


def test_gui_settings_stellt_alias_kanonisch_wieder_her(qtbot, monkeypatch):
  raw = json.dumps({
    "version": main.GUI_SETTINGS_SCHEMA_VERSION,
    "strategy": "Harmonic Flow Enhanced",
  })

  window = _window(
    qtbot, monkeypatch, _MemorySettings({main.GUI_SETTINGS_KEY: raw})
  )

  assert window.library_panel.strategy_combo.currentText() == "Harmonic Flow"
  assert window.current_playlist_mode == "Harmonic Flow"


def test_genre_regler_tooltip_beschreibt_getrennte_wirkungen(qtbot):
  widget = main.AdvancedParametersWidget()
  qtbot.addWidget(widget)

  tooltip = widget.genre_weight.toolTip()

  assert "Genre-Prioritaet in der Sortierung" in tooltip
  assert "lokale Uebergangskandidatenscore" in tooltip
  assert "komplett ignoriert" not in tooltip
  assert "wichtigster Faktor" not in tooltip


def test_gui_settings_klemmt_alte_bpm_toleranz_auf_paarvertrag(qtbot, monkeypatch):
  raw = json.dumps({
    "version": main.GUI_SETTINGS_SCHEMA_VERSION,
    "bpm_tolerance": 15,
  })
  window = _window(
    qtbot, monkeypatch, _MemorySettings({main.GUI_SETTINGS_KEY: raw})
  )
  assert window.library_panel.bpm_tolerance_slider.maximum() == 2
  assert window.library_panel.bpm_tolerance_slider.value() == 2
  assert window.current_bpm_tolerance == 2.0


def test_weight_save_meldet_atomaren_schreibfehler_ohne_falschen_erfolg(
  qtbot, monkeypatch, tmp_path
):
  from hpg_core import tolerances
  override = tmp_path / "weights.json"
  vorher = b'{"vorher": true}'
  override.write_bytes(vorher)
  monkeypatch.setenv("HPG_TOLERANCES_FILE", str(override))
  widget = main.AdvancedParametersWidget()
  qtbot.addWidget(widget)

  monkeypatch.setattr(
    tolerances, "write_overrides_atomically", Mock(side_effect=OSError("gesperrt"))
  )
  widget.transition_weight_sliders["kandidaten_groove_weight"].setValue(20)

  assert override.read_bytes() == vorher
  assert "nicht gespeichert" in widget.transition_weight_status.text()
  assert widget.transition_weight_sliders["kandidaten_groove_weight"].value() == 26


def test_weight_reset_meldet_atomaren_schreibfehler_ohne_datenverlust(
  qtbot, monkeypatch, tmp_path
):
  from hpg_core import tolerances
  override = tmp_path / "weights.json"
  vorher = {
    "Psytrance": {
      "groove_weight": 0.25,
      "kandidaten_groove_weight": 0.20,
    }
  }
  override.write_text(json.dumps(vorher), encoding="utf-8")
  monkeypatch.setenv("HPG_TOLERANCES_FILE", str(override))
  widget = main.AdvancedParametersWidget()
  qtbot.addWidget(widget)
  monkeypatch.setattr(
    tolerances,
    "remove_candidate_overrides",
    Mock(side_effect=OSError("gesperrt")),
  )

  widget._on_transition_weights_reset()

  assert "nicht verworfen" in widget.transition_weight_status.text()
  assert json.loads(override.read_text(encoding="utf-8")) == vorher


def test_table_und_camelot_nutzen_empfehlungs_score_statt_rank1_recalc(
  qtbot, monkeypatch
):
  rec = _rec_mit_kandidaten(index=0)
  monkeypatch.setattr(
    main, "calculate_enhanced_compatibility",
    Mock(side_effect=AssertionError("darf nicht neu berechnen")),
  )
  panel = main.PlaylistPanel()
  qtbot.addWidget(panel)
  panel.set_playlist_data(
    [rec.from_track, rec.to_track], {}, transition_recommendations=[rec]
  )
  assert panel.table.item(1, 14).data(main.Qt.ItemDataRole.UserRole) == 71.0

  wheel = main.CamelotWheelWidget()
  qtbot.addWidget(wheel)
  wheel.set_playlist([rec.from_track, rec.to_track], 2.0, [rec], {})
  color = wheel._edge_color(rec.from_track, rec.to_track, 0)
  assert color == main.QColor(main.COLORS["accent_success"])


def test_planlose_empfehlung_bleibt_ungeplant_und_score_null(qtbot, monkeypatch):
  import dataclasses

  rec = dataclasses.replace(_rec_mit_kandidaten(index=0), plan=None,
                            compatibility_score=99)
  monkeypatch.setattr(
    main, "calculate_enhanced_compatibility",
    Mock(side_effect=AssertionError("planlos darf nicht neu berechnet werden")),
  )
  panel = main.PlaylistPanel()
  qtbot.addWidget(panel)
  panel.set_playlist_data(
    [rec.from_track, rec.to_track], {}, transition_recommendations=[rec]
  )
  score_item = panel.table.item(1, 14)
  assert score_item.data(main.Qt.ItemDataRole.UserRole) == 0.0
  assert "UNGEPLANT" in score_item.text()

  wheel = main.CamelotWheelWidget()
  qtbot.addWidget(wheel)
  wheel.set_playlist([rec.from_track, rec.to_track], 2.0, [rec], {})
  assert wheel._edge_color(rec.from_track, rec.to_track, 0) == main.QColor(
    main.COLORS["accent_danger"]
  )

  tips = main.MixTipsPanel()
  qtbot.addWidget(tips)
  tips.set_recommendations([rec])
  labels = [label.text() for label in tips.layout().itemAt(0).widget().findChildren(main.QLabel)]
  assert any("UNGEPLANT" in text for text in labels)
  tips.setup_transition_previews([rec])
  preview = tips._preview_buttons[0]
  assert not preview.isEnabled()
  assert "Ungeplant" in preview.text()


def test_real_uebersprungene_empfehlung_erscheint_im_mix_tips_panel(qtbot):
  panel = main.MixTipsPanel()
  qtbot.addWidget(panel)
  tracks = [
    Track(filePath="C:/a.wav", fileName="a.wav", bpm=140.0),
    Track(filePath="C:/b.wav", fileName="b.wav", bpm=140.0),
  ]

  panel.set_recommendations([], tracks)

  texte = [label.text() for label in panel.findChildren(main.QLabel)]
  assert any("a.wav → b.wav" in text and "UNGEPLANT" in text for text in texte)


def test_mix_tips_leeren_verwirft_auch_die_alte_playlist(qtbot):
  panel = main.MixTipsPanel()
  qtbot.addWidget(panel)
  tracks = [
    Track(filePath="C:/a.wav", fileName="a.wav", bpm=140.0),
    Track(filePath="C:/b.wav", fileName="b.wav", bpm=140.0),
  ]
  panel.set_recommendations([], tracks)

  panel.set_recommendations([], [])

  texte = [label.text() for label in panel.findChildren(main.QLabel)]
  assert "No transition tips available yet." in texte
  assert not any("UNGEPLANT" in text for text in texte)


def test_mix_tips_ordnet_geplante_und_ungeplante_paare_nach_playlist(qtbot):
  panel = main.MixTipsPanel()
  qtbot.addWidget(panel)
  rec = _rec_mit_kandidaten(index=1)
  erster_track = Track(filePath="C:/start.wav", fileName="start.wav", bpm=140.0)

  panel.set_recommendations([rec], [erster_track, rec.from_track, rec.to_track])
  panel.setup_transition_previews([rec])

  erster_eintrag = panel.container_layout.itemAt(0).widget()
  zweite_karte = panel.container_layout.itemAt(1).widget()
  assert isinstance(erster_eintrag, main.QLabel)
  assert "start.wav" in erster_eintrag.text()
  assert rec.from_track.fileName in erster_eintrag.text()
  assert "UNGEPLANT" in erster_eintrag.text()
  assert not isinstance(zweite_karte, main.QLabel)
  assert 1 in panel._preview_buttons
  assert panel._preview_buttons[1].parent() is zweite_karte

  empfangen = []
  panel.candidate_chosen.connect(lambda index, rang: empfangen.append((index, rang)))
  panel._kandidaten_tabellen[1].selectRow(1)
  assert empfangen == [(1, 2)]


def test_preview_dialog_und_xml_export_nutzen_aktiven_paarvertrag(
  qtbot, monkeypatch, tmp_path
):
  rec = _rec_mit_kandidaten(index=0)
  window = _window(qtbot, monkeypatch)
  window.playlist = [rec.from_track, rec.to_track]
  window.playlist_panel.transition_recommendations = [rec]
  monkeypatch.setattr(
    main, "calculate_enhanced_compatibility",
    Mock(side_effect=AssertionError("darf nicht neu berechnen")),
  )

  shown = {}

  class _MessageBox:
    def __init__(self, _parent):
      pass

    def setWindowTitle(self, value):
      shown["title"] = value

    def setText(self, value):
      shown["text"] = value

    def setDetailedText(self, value):
      shown["details"] = value

    def exec(self):
      shown["exec"] = True

  monkeypatch.setattr(main, "QMessageBox", _MessageBox)
  window.preview_transitions()
  assert "Score: 71%" in shown["details"]
  assert "Kandidat Rang 1" in shown["details"]
  assert "Mix-Out: 164.6s" in shown["details"]

  exporter = Mock()
  exporter.export.return_value = ExportReport(
    status="success", output_path=str(tmp_path / "set.xml"),
    tracks_written=2, cues_written=2, beatgrids_written=2,
  )
  monkeypatch.setattr(main, "RekordboxXMLExporter", lambda: exporter)
  monkeypatch.setattr(main, "QMessageBox", SimpleNamespace(information=Mock(), warning=Mock(), critical=Mock()))
  window._export_rekordbox_xml(str(tmp_path / "set.xml"))
  assert exporter.export.call_args.kwargs["transitions"] == [rec]


def test_stale_ai_detect_und_progress_ergebnisse_werden_ignoriert(qtbot, monkeypatch):
  widget = main.AdvancedParametersWidget()
  qtbot.addWidget(widget)
  widget.ai_enabled_checkbox.blockSignals(True)
  widget.ai_enabled_checkbox.setChecked(True)
  widget.ai_enabled_checkbox.blockSignals(False)
  stale = Mock(preferred="Ollama", preferred_model="old")
  stale.isRunning.return_value = True
  widget._ai_detect_worker = stale
  widget._ai_detect_workers = [stale]
  widget.detected_provider = "Ollama"
  widget.detected_base_url = "http://127.0.0.1:11434/api/generate"
  widget.detected_active_model = "old"
  widget.model_combo.addItem("old")
  widget.lmstudio_radio.blockSignals(True)
  widget.lmstudio_radio.setChecked(True)
  widget.lmstudio_radio.blockSignals(False)

  class _Signal:
    def connect(self, _slot):
      pass

  replacement = SimpleNamespace(
    preferred="LM Studio", preferred_model=None,
    detected=_Signal(), finished=_Signal(), start=Mock(), deleteLater=Mock(),
  )
  detected_args = {}

  def _replacement_worker(**kwargs):
    detected_args.update(kwargs)
    return replacement

  monkeypatch.setattr(main, "AIDetectWorker", _replacement_worker)
  widget.refresh_ai_providers()
  stale.requestInterruption.assert_called_once_with()
  assert widget.detected_provider is None
  assert widget.detected_base_url is None
  assert widget.detected_active_model is None
  assert widget.model_combo.count() == 0
  assert detected_args["preferred"] == "LM Studio"
  assert detected_args["preferred_model"] is None
  assert replacement.preferred_model is None
  assert widget._ai_detect_worker is replacement
  assert widget._ai_detect_workers == [stale, replacement]

  window = _window(qtbot, monkeypatch)
  current = Mock()
  window.ai_worker = current
  window._set_run_state(main.RunState.AI)
  before = window.status_bar.status_label.text()
  window._on_ai_progress(1, 2, Mock())
  assert window.status_bar.status_label.text() == before


def test_close_erfasst_auch_superseded_ai_detect_worker(qtbot, monkeypatch):
  window = _window(qtbot, monkeypatch)
  advanced = window.library_panel.advanced_params
  stale = SimpleNamespace(
    isRunning=Mock(return_value=True),
    wait=Mock(return_value=False),
    requestInterruption=Mock(),
  )
  current = SimpleNamespace(
    isRunning=Mock(return_value=True),
    wait=Mock(return_value=False),
    requestInterruption=Mock(),
  )
  advanced._ai_detect_workers = [stale, current]
  advanced._ai_detect_worker = current
  monkeypatch.setattr(main.QTimer, "singleShot", Mock())
  event = Mock()

  window.closeEvent(event)

  stale.requestInterruption.assert_called_once_with()
  current.requestInterruption.assert_called_once_with()
  event.ignore.assert_called_once_with()
  event.accept.assert_not_called()


def test_reorder_setzt_mixpunkt_spalten_aus_neuen_empfehlungen(qtbot, monkeypatch):
  """Waechter Tor 2 Teil 4: nach Drag-Drop muessen Spalten 10/11 den Plan der
  neuen Empfehlungen zeigen, nicht den alten Partner."""
  rec = _rec_mit_kandidaten()
  panel = main.PlaylistPanel()
  qtbot.addWidget(panel)
  monkeypatch.setattr(main, "compute_transition_recommendations", lambda *a, **k: [rec])
  panel.set_playlist_data([rec.from_track, rec.to_track], {}, transition_recommendations=[rec], bpm_tolerance=2.0)
  assert panel.table.item(1, 10).toolTip() == "Quelle: TransitionPlan · Kandidat Rang 1"
  assert panel.table.item(1, 10).text().startswith("01:22") and panel.table.item(0, 11).text().startswith("02:44")
  import dataclasses
  rec2 = dataclasses.replace(rec, plan=dataclasses.replace(rec.plan, mix_in_b=109.7, mix_out_a=219.4))
  monkeypatch.setattr(main, "compute_transition_recommendations", lambda *a, **k: [rec2])
  panel._update_table_after_reorder()
  assert panel.transition_recommendations == [rec2]
  assert panel.table.item(1, 10).text().startswith("01:49") and panel.table.item(0, 11).text().startswith("03:39")
