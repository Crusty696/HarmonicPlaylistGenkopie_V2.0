"""Gezielte Tests fuer Pipelinezustand und einheitlichen Fortschritt."""

from unittest.mock import Mock

from PyQt6.QtCore import Qt

from main import (
  AIAnalysisWorker,
  AdvancedParametersWidget,
  AnalysisProgressWidget,
  MainWindow,
  MixTipsPanel,
  PlaylistPanel,
  RunState,
  StatusBarWidget,
  map_phase_progress,
)
from hpg_core.models import Track


def test_phase_progress_mapping_is_bounded_and_monotonic():
  values = [map_phase_progress(value, 80, 95) for value in range(-10, 111)]

  assert values[0] == 80
  assert values[-1] == 95
  assert values == sorted(values)


def test_progress_widgets_share_zero_to_hundred_contract(qtbot):
  status = StatusBarWidget()
  analysis = AnalysisProgressWidget()
  qtbot.addWidget(status)
  qtbot.addWidget(analysis)

  status.set_progress(80)
  analysis.set_progress(80)

  assert status.progress_bar.maximum() == 100
  assert analysis.progress_bar.maximum() == 100
  assert status.progress_bar.value() == 80
  assert analysis.progress_bar.value() == 80
  assert status.progress_bar.format() == "80%"
  assert analysis.progress_bar.format() == "80%"


def test_cancel_button_visibility_matches_lifecycle(qtbot):
  status = StatusBarWidget()
  qtbot.addWidget(status)

  status.show_progress()
  assert not status.cancel_btn.isHidden()

  status.hide_progress()
  assert status.cancel_btn.isHidden()


def test_cancel_requests_worker_without_claiming_completion(qtbot, monkeypatch):
  monkeypatch.setattr(MainWindow, "check_dependencies_and_warn", lambda self: None)
  window = MainWindow()
  qtbot.addWidget(window)
  worker = Mock()
  worker.isRunning.return_value = True
  window.worker = worker
  window._set_run_state(RunState.AUDIO)

  window.cancel_analysis()

  worker.request_cancel.assert_called_once_with()
  assert window.run_state == RunState.CANCELLING
  assert "angefordert" in window.status_bar.status_label.text()


def test_active_ai_state_blocks_second_start(qtbot, monkeypatch):
  monkeypatch.setattr(MainWindow, "check_dependencies_and_warn", lambda self: None)
  window = MainWindow()
  qtbot.addWidget(window)
  window._set_run_state(RunState.AI)

  window.start_analysis()

  assert window.status_bar.status_label.text() == "Analyse laeuft bereits..."


def test_ai_is_explicitly_opt_in_and_does_not_autostart(qtbot):
  widget = AdvancedParametersWidget()
  qtbot.addWidget(widget)

  assert widget.get_parameters()["ai_enabled"] is False
  assert widget._ai_detect_worker is None
  assert widget.ai_refresh_btn.isEnabled() is False


def test_ai_worker_uses_cache_and_stops_after_first_failure(monkeypatch):
  cached = Track(filePath="C:/cached.wav", fileName="cached.wav")
  pending = Track(filePath="C:/pending.wav", fileName="pending.wav")
  monkeypatch.setattr(
    "hpg_core.ai_engine.ai_metadata_matches",
    lambda track, provider, model: track is cached,
  )
  fetch = Mock(return_value={})
  monkeypatch.setattr("hpg_core.ai_engine.fetch_ai_analysis", fetch)
  worker = AIAnalysisWorker(
    [cached, pending, Track(filePath="C:/never.wav", fileName="never.wav")],
    provider="Ollama",
    model="test-model",
    base_url="http://local/test",
  )

  worker.run()

  fetch.assert_called_once()
  assert "pending.wav" in worker.failure_reason


def test_thousand_transitions_create_no_eager_players_or_render_jobs(qtbot):
  panel = MixTipsPanel()
  qtbot.addWidget(panel)
  transitions = [Mock() for _ in range(1000)]

  panel.setup_transition_previews(transitions)

  assert panel._preview_widgets == {}
  assert panel._render_worker is None
  assert len(panel._preview_buttons) == 1000
  assert len(panel._preview_queue) == 0


def test_reorder_uses_full_track_identity_for_duplicate_basenames(qtbot):
  panel = PlaylistPanel()
  qtbot.addWidget(panel)
  first = Track(
    filePath="C:/set-a/track.wav", fileName="track.wav", bpm=128.0
  )
  second = Track(
    filePath="C:/set-b/track.wav", fileName="track.wav", bpm=128.0
  )
  panel.set_playlist_data([first, second], {})
  first_id = panel.table.item(0, 1).data(Qt.ItemDataRole.UserRole)
  second_id = panel.table.item(1, 1).data(Qt.ItemDataRole.UserRole)
  panel.table.item(0, 1).setData(Qt.ItemDataRole.UserRole, second_id)
  panel.table.item(1, 1).setData(Qt.ItemDataRole.UserRole, first_id)

  panel._on_rows_moved()

  assert [track.track_id for track in panel.playlist] == [
    second.track_id,
    first.track_id,
  ]


def test_strategy_ui_disables_parameters_that_are_not_consumed(qtbot):
  widget = AdvancedParametersWidget()
  qtbot.addWidget(widget)

  widget.apply_strategy_support("Warm-Up")
  assert widget.peak_position_slider.isEnabled() is False
  assert widget.genre_weight.isEnabled() is False
  assert "<b>Warm-Up</b> wertet diese Einstellung nicht aus" in widget.energy_strategy_hint.text()
  assert "#FFD740" in widget.energy_group.styleSheet()

  widget.apply_strategy_support("Peak-Time")
  assert widget.peak_position_slider.isEnabled() is True
  assert widget.genre_weight.isEnabled() is False
  assert "Peak-Time" in widget.harmony_strategy_hint.text()
  assert "#00E676" in widget.harmony_group.styleSheet()
