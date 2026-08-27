"""Gezielte Tests fuer Pipelinezustand und einheitlichen Fortschritt."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QModelIndex, Qt, QSettings, QThread
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QLabel, QPushButton

import main
from main import (
  AIAnalysisWorker,
  AdvancedParametersWidget,
  AnalysisProgressWidget,
  MainWindow,
  MixTipsPanel,
  PlaylistPanel,
  RunState,
  StatusBarWidget,
  TransitionPreviewWidget,
  WaveformWidget,
  map_phase_progress,
)
from hpg_core.models import Track
from hpg_core.playlist import TransitionPlan, TransitionRecommendation


class _MemorySettings:
  def __init__(self):
    self.values = {}

  def value(self, key, default=None):
    return self.values.get(key, default)

  def setValue(self, key, value):
    self.values[key] = value

  def sync(self):
    pass

  def status(self):
    return QSettings.Status.NoError


def _worker_double(*, running=True):
  return SimpleNamespace(
    isRunning=Mock(return_value=running),
    request_cancel=Mock(),
    wait=Mock(return_value=True),
    deleteLater=Mock(),
    get_temp_dir=Mock(return_value=None),
    get_temp_files=Mock(return_value=[]),
    progress=Mock(),
    status_update=Mock(),
    analysis_issues=Mock(),
    analysis_done=Mock(),
  )


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


@pytest.mark.parametrize(
  "active_state", sorted(main.ACTIVE_RUN_STATES, key=lambda state: state.value)
)
def test_aktive_berechnung_sperrt_reorder_bis_terminalzustand(
  qtbot, monkeypatch, active_state
):
  monkeypatch.setattr(MainWindow, "check_dependencies_and_warn", lambda self: None)
  window = MainWindow(settings=_MemorySettings())
  qtbot.addWidget(window)

  window._set_run_state(active_state)
  assert (
    window.playlist_panel.table.dragDropMode()
    == window.playlist_panel.table.DragDropMode.NoDragDrop
  )

  window._set_run_state(RunState.SUCCESS)
  assert (
    window.playlist_panel.table.dragDropMode()
    == window.playlist_panel.table.DragDropMode.InternalMove
  )


def test_reorder_slot_verwirft_queued_signal_in_aktivem_zustand(
  qtbot, monkeypatch
):
  monkeypatch.setattr(MainWindow, "check_dependencies_and_warn", lambda self: None)
  window = MainWindow(settings=_MemorySettings())
  qtbot.addWidget(window)
  verteile = Mock()
  monkeypatch.setattr(window, "_verteile_uebergaenge", verteile)
  window._set_run_state(RunState.PREVIEW)

  window._on_playlist_reordered(
    main.LegacyReorderRequest((), {}, (), 2.0, {})
  )

  verteile.assert_not_called()
  assert "gesperrt" in window.status_bar.status_label.text()


def test_cancel_requests_worker_without_claiming_completion(qtbot, monkeypatch):
  monkeypatch.setattr(MainWindow, "check_dependencies_and_warn", lambda self: None)
  window = MainWindow(settings=_MemorySettings())
  qtbot.addWidget(window)
  worker = Mock()
  worker.isRunning.return_value = True
  window.worker = worker
  window._set_run_state(RunState.AUDIO)

  window.cancel_analysis()

  worker.request_cancel.assert_called_once_with()
  assert window.run_state == RunState.CANCELLING
  assert "angefordert" in window.status_bar.status_label.text()


def test_cancel_preview_ende_vor_playlist_bleibt_bis_playlist_finished(
  qtbot, monkeypatch
):
  monkeypatch.setattr(MainWindow, "check_dependencies_and_warn", lambda self: None)
  window = MainWindow(settings=_MemorySettings())
  qtbot.addWidget(window)
  playlist_worker = _worker_double()
  preview_worker = _worker_double()
  window.playlist_worker = playlist_worker
  window.mix_tips_panel._render_worker = preview_worker
  window.mix_tips_panel._render_workers = [preview_worker]
  window._set_run_state(RunState.PLAYLIST)

  window.cancel_analysis()
  # QThread kann bereits False melden, obwohl sein queued finished-Cleanup
  # die MainWindow-Ownership noch nicht auf None gesetzt hat.
  playlist_worker.isRunning.return_value = False
  preview_worker.isRunning.return_value = False
  window.mix_tips_panel._on_preview_worker_finished(preview_worker)

  assert window.run_state == RunState.CANCELLING
  window._cleanup_playlist_worker(playlist_worker)
  assert window.run_state == RunState.CANCELLED


def test_cancel_playlist_ende_vor_preview_bleibt_bis_preview_finished(
  qtbot, monkeypatch
):
  monkeypatch.setattr(MainWindow, "check_dependencies_and_warn", lambda self: None)
  window = MainWindow(settings=_MemorySettings())
  qtbot.addWidget(window)
  playlist_worker = _worker_double()
  preview_worker = _worker_double()
  window.playlist_worker = playlist_worker
  window.mix_tips_panel._render_worker = preview_worker
  window.mix_tips_panel._render_workers = [preview_worker]
  window._set_run_state(RunState.PLAYLIST)

  window.cancel_analysis()
  playlist_worker.isRunning.return_value = False
  window._cleanup_playlist_worker(playlist_worker)

  assert window.run_state == RunState.CANCELLING
  preview_worker.isRunning.return_value = False
  window.mix_tips_panel._on_preview_worker_finished(preview_worker)
  assert window.run_state == RunState.CANCELLED


def test_cancel_analysis_done_ist_noch_nicht_qthread_finished(qtbot, monkeypatch):
  monkeypatch.setattr(MainWindow, "check_dependencies_and_warn", lambda self: None)
  window = MainWindow(settings=_MemorySettings())
  qtbot.addWidget(window)
  worker = _worker_double()
  window.worker = worker
  window._set_run_state(RunState.CANCELLING)

  window.analysis_finished([], {}, worker)

  assert window.run_state == RunState.CANCELLING
  worker.isRunning.return_value = False
  window._cleanup_analysis_worker(worker)
  assert window.run_state == RunState.CANCELLED


def test_active_ai_state_blocks_second_start(qtbot, monkeypatch):
  monkeypatch.setattr(MainWindow, "check_dependencies_and_warn", lambda self: None)
  window = MainWindow(settings=_MemorySettings())
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


def test_peak_worker_class_is_module_level_and_drains(qtbot):
  """Regression: _PeakWorker lag frueher IN WaveformWidget.load() — jeder
  Aufruf erzeugte ein neues Klassenobjekt (eigenes pyqtSignal/QMetaObject)."""
  import main as main_module

  assert isinstance(main_module._PeakWorker, type)
  assert issubclass(main_module._PeakWorker, QThread)

  widget = WaveformWidget()
  qtbot.addWidget(widget)
  # Nicht existierender Pfad: run() faellt in den Fehlerzweig, der Lifecycle
  # (Registrierung + finished -> discard) ist derselbe.
  seen = []
  for _ in range(3):
    widget.load("C:/does-not-exist-peak-probe.wav", 8.0)
    worker = widget._peak_worker
    seen.append(type(worker))
    assert worker.parent() is None  # nie am Widget haengen
    assert worker in main_module._PEAK_WORKERS
    qtbot.waitUntil(lambda: len(main_module._PEAK_WORKERS) == 0, timeout=5000)

  assert len({id(cls) for cls in seen}) == 1
  assert seen[0] is main_module._PeakWorker

  main_module.stop_peaks()
  assert len(main_module._PEAK_WORKERS) == 0


def test_preview_error_keeps_widget_and_retry_clears_it(qtbot):
  """Regression: set_error() war toter Code — der Fehlerpfad loeschte das
  Widget, statt die dokumentierte Fehlermeldung darin anzuzeigen."""
  transition = SimpleNamespace(
    from_track=Track(filePath="C:/a.wav", fileName="a.wav"),
    to_track=Track(filePath="C:/b.wav", fileName="b.wav"),
    plan=SimpleNamespace(mix_out_a=30.0, mix_in_b=0.0, overlap=8.0),
    transition_type="blend",
  )
  panel = MixTipsPanel()
  qtbot.addWidget(panel)
  widget = TransitionPreviewWidget(0, transition, panel)
  panel._preview_widgets[0] = widget
  panel._preview_buttons[0] = QPushButton("laufend")

  panel._on_clip_error(0, "render abgebrochen")

  assert panel._preview_widgets[0] is widget
  assert widget._error_msg == "render abgebrochen"
  assert not widget._play_btn.isEnabled()
  assert not widget._slider.isEnabled()
  assert "render abgebrochen" in widget._waveform._placeholder

  widget.clear_error()
  assert widget._error_msg is None
  assert widget._title_label.text() == widget._base_title
  assert widget._waveform._placeholder == "Wellenform wird geladen …"


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
  requests = []
  panel.playlist_reordered.connect(requests.append)

  assert panel.table.model().moveRows(
    QModelIndex(), 0, 1, QModelIndex(), 2
  ) is True

  assert [track.track_id for track in panel.playlist] == [
    first.track_id,
    second.track_id,
  ]
  assert [track.track_id for track in requests[0].playlist] == [
    second.track_id,
    first.track_id,
  ]


def test_generation_result_reorder_nutzt_occurrences_bei_gleichem_pfad(
  qtbot, monkeypatch
):
  from hpg_core.playlist import generate_playlist_result

  monkeypatch.setattr(MainWindow, "check_dependencies_and_warn", lambda self: None)
  window = MainWindow(settings=_MemorySettings())
  qtbot.addWidget(window)
  first = Track(
    filePath="C:/same/track.wav", fileName="first.wav", bpm=128.0,
    duration=300.0,
  )
  second = Track(
    filePath="C:/same/track.wav", fileName="second.wav", bpm=129.0,
    duration=300.0,
  )
  result = generate_playlist_result(
    [first, second], "Harmonic Flow", bpm_tolerance=2.0
  )
  window._publiziere_generation_result(result)
  ids = [
    window.playlist_panel.table.item(row, 1).data(Qt.ItemDataRole.UserRole)
    for row in range(2)
  ]

  assert ids[0] != ids[1]
  assert all(
    window.playlist_panel.table.item(row, 1).data(main.TRACK_FILE_PATH_ROLE)
    == "C:/same/track.wav"
    for row in range(2)
  )

  assert window.playlist_panel.table.model().moveRows(
    QModelIndex(), 0, 1, QModelIndex(), 2
  ) is True

  assert tuple(
    occurrence.occurrence_id
    for occurrence in window.current_generation_result.occurrences
  ) == (ids[1], ids[0])
  assert [track.fileName for track in window.playlist] == ["second.wav", "first.wav"]


def test_neuer_analysestart_behaelt_altes_result_bis_zum_publish(
  qtbot, monkeypatch, tmp_path
):
  from hpg_core.playlist import generate_playlist_result

  monkeypatch.setattr(MainWindow, "check_dependencies_and_warn", lambda self: None)
  monkeypatch.setattr(main.AnalysisWorker, "start", lambda self: None)
  window = MainWindow(settings=_MemorySettings())
  qtbot.addWidget(window)
  old_track = Track(
    filePath="C:/old.wav", fileName="old.wav", bpm=128.0, duration=300.0
  )
  old_result = generate_playlist_result([old_track], "Harmonic Flow", 2.0)
  window._publiziere_generation_result(old_result)
  window.library_panel.set_folder_path(str(tmp_path))

  window.start_analysis()

  assert window.current_generation_result is old_result
  assert window.playlist == [old_track]
  assert window.playlist_panel.generation_result is old_result
  assert window.run_state == RunState.AUDIO


def test_playlist_shows_unplanned_transition_without_executable_plan(qtbot):
  from hpg_core.theme import transition_score_style

  panel = PlaylistPanel()
  qtbot.addWidget(panel)
  tracks = [
    Track(filePath="C:/set/a.wav", fileName="a.wav", bpm=128.0),
    Track(filePath="C:/set/b.wav", fileName="b.wav", bpm=128.0),
  ]

  panel.set_playlist_data(tracks, {})

  assert panel.table.horizontalHeaderItem(14).text() == "Passung"
  assert panel.table.item(0, 14).text() == "—"
  score_item = panel.table.item(1, 14)
  score = score_item.data(Qt.ItemDataRole.UserRole)
  assert score == 0.0
  assert score_item.text() == "0% · UNGEPLANT"
  accent_color, _, _ = transition_score_style(0.0)
  assert score_item.background().color().name() == QColor(accent_color).name()


def test_playlist_repopulation_preserves_ai_insights(qtbot):
  panel = PlaylistPanel()
  qtbot.addWidget(panel)
  track = Track(
    filePath="C:/set/a.wav",
    fileName="a.wav",
    bpm=128.0,
    ai_metadata={
      "moods": ["dark", "driving"],
      "sub_genre": "Peak Techno",
      "description": "late-night",
    },
  )

  panel.set_playlist_data([track], {})

  assert panel.table.item(0, 15).text() == "[Peak Techno] dark, driving"
  assert panel.table.item(0, 15).toolTip() == "late-night"


def test_preview_temp_directory_is_removed_after_cache_cleanup(qtbot, tmp_path):
  panel = MixTipsPanel()
  qtbot.addWidget(panel)
  directory = tmp_path / "hpg_preview_test"
  directory.mkdir()
  clip = directory / "preview.wav"
  clip.write_bytes(b"wav")
  worker = main.TransitionRenderWorker([])
  worker._temp_dir = str(directory)
  worker._temp_files = [str(clip)]
  panel._render_worker = worker
  panel._render_workers = [worker]
  panel._preview_cache[0] = str(clip)

  panel._on_preview_worker_finished(worker)
  assert directory.exists()

  panel._cleanup_existing_previews()
  assert not clip.exists()
  assert not directory.exists()


def test_preview_state_controls_cancel_visibility(qtbot, monkeypatch):
  monkeypatch.setattr(MainWindow, "check_dependencies_and_warn", lambda self: None)
  window = MainWindow(settings=_MemorySettings())
  qtbot.addWidget(window)

  window._on_preview_state_changed(True)
  assert window.run_state == RunState.PREVIEW
  assert not window.status_bar.cancel_btn.isHidden()

  window._on_preview_state_changed(False)
  assert window.run_state == RunState.SUCCESS
  assert window.status_bar.cancel_btn.isHidden()


def test_mix_tip_uses_same_transition_fit_color(qtbot):
  from hpg_core.theme import transition_score_style

  panel = MixTipsPanel()
  qtbot.addWidget(panel)
  recommendation = TransitionRecommendation(
    index=0,
    from_track=Track(filePath="C:/set/a.wav", fileName="a.wav", bpm=128.0),
    to_track=Track(filePath="C:/set/b.wav", fileName="b.wav", bpm=129.0),
    fade_out_start=30.0,
    fade_out_end=40.0,
    fade_in_start=0.0,
    mix_entry=0.0,
    overlap=10.0,
    bpm_delta=1.0,
    energy_delta=2,
    compatibility_score=75,
    risk_level="medium-low",
    notes="",
    plan=TransitionPlan(
      mix_out_a=30.0,
      mix_in_b=0.0,
      fade_out_start=30.0,
      fade_out_end=40.0,
      overlap=10.0,
      transition_type="standard_crossfade",
    ),
  )

  panel.set_recommendations([recommendation])

  summary = next(
    label
    for label in panel.findChildren(QLabel)
    if "Score 75/100" in label.text()
  )
  accent_color, _, label = transition_score_style(0.75)
  assert label in summary.text()
  assert accent_color in summary.styleSheet()
  assert accent_color in summary.parentWidget().styleSheet()


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
  assert "● AKTIV" in widget.energy_strategy_hint.text()
  assert "Peak Position" in widget.energy_strategy_hint.text()
  assert "#00E676" in widget.energy_group.styleSheet()
  assert "Peak-Time" in widget.harmony_strategy_hint.text()
  assert "#00E676" in widget.harmony_group.styleSheet()


def test_bass_header_tooltip_beschreibt_anzeige_und_eq_sektionskontext(qtbot):
  panel = PlaylistPanel()
  qtbot.addWidget(panel)

  tooltip = panel.table.horizontalHeaderItem(12).toolTip()

  assert "Trackweiter Mittelwert" in tooltip
  assert "Mix-Out-/Mix-In-Sektionen" in tooltip
  assert "Genre-Flow" not in tooltip
