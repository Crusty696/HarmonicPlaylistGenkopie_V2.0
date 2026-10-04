"""Regressionen fuer Preview-Ergebnisse und Worker-Fehlerkategorien."""
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QPushButton
import main


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    # Nur die unabhaengige Dependency-Meldung entfaellt in diesen Unit-Tests.
    monkeypatch.setattr(main.MainWindow, "check_dependencies_and_warn", lambda self: None)
    instance = main.MainWindow(settings=QSettings(
        str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(instance)
    return instance


@pytest.mark.parametrize("successes,failures,expected", [
    (1, 0, main.RunState.SUCCESS),
    (1, 1, main.RunState.PARTIAL),
    (0, 1, main.RunState.ERROR),
    (0, 0, main.RunState.ERROR),
])
def test_current_batch_result(window, successes, failures, expected):
    panel = window.mix_tips_panel
    panel._preview_batch_successes = successes
    panel._preview_batch_failures = failures
    panel._preview_batch_cancelled = False
    window._on_preview_state_changed(True)
    window._on_preview_state_changed(False)
    assert window.run_state == expected
    assert window.status_bar.cancel_btn.isHidden()


def test_previous_cache_success_does_not_hide_new_failure(window):
    panel = window.mix_tips_panel
    panel._preview_cache[999] = "C:/nonexistent/old-preview.wav"
    panel._preview_batch_successes = 0
    panel._preview_batch_failures = 1
    panel._preview_batch_cancelled = False
    window._on_preview_state_changed(True)
    window._on_preview_state_changed(False)
    assert window.run_state == main.RunState.ERROR
    panel._preview_cache.clear()


def test_stale_panel_cannot_finish_current_preview(window, qtbot):
    old = main.MixTipsPanel()
    qtbot.addWidget(old)
    old.preview_state_changed.connect(window._on_preview_state_changed)
    window._on_preview_state_changed(True)
    old.preview_state_changed.emit(False)
    assert window.run_state == main.RunState.PREVIEW
    window.mix_tips_panel._preview_batch_cancelled = True
    window._on_preview_state_changed(False)
    assert window.run_state == main.RunState.CANCELLED


def test_late_error_after_cancel_is_ignored(window):
    panel = window.mix_tips_panel
    source = SimpleNamespace()
    panel._render_worker = source
    panel._preview_batch_active = False
    panel._preview_batch_cancelled = True
    panel._preview_buttons[0] = QPushButton("Abgebrochen")
    panel._on_clip_error(0, "spaeter Fehler", source)
    assert panel._preview_batch_failures == 0
    assert panel._preview_buttons[0].text() == "Abgebrochen"
    panel._render_worker = None


def test_current_error_is_counted_once_per_signal(window):
    panel = window.mix_tips_panel
    source = SimpleNamespace()
    panel._render_worker = source
    panel._preview_batch_active = True
    panel._preview_batch_cancelled = False
    panel._on_clip_error(0, "Fehler", source)
    assert panel._preview_batch_failures == 1
    panel._render_worker = None


@pytest.mark.parametrize("exception_type,category,message", [
    (main.BeatSyncError, "transition_render_rejected", "Vorschau abgelehnt: Testfehler"),
    (RuntimeError, "transition_render_crash", "Format-Absturz (Datei beschaedigt)"),
])
def test_worker_exception_dispatch(qtbot, tmp_path, monkeypatch,
                                   exception_type, category, message):
    from unittest.mock import Mock
    import concurrent.futures
    from hpg_core.models import Track

    # Nur die Prozessgrenze simulieren; echte Spezifikation und Exception-Typen.
    future = Mock()
    future.result.side_effect = exception_type("Testfehler")
    executor = Mock()
    executor._processes = {}
    executor.submit.return_value = future
    factory = Mock(return_value=executor)
    monkeypatch.setattr(concurrent.futures, "ProcessPoolExecutor", factory)
    reporter = Mock()
    monkeypatch.setattr(main, "get_error_reporter", lambda: reporter)
    private_dir = tmp_path / "preview"
    private_dir.mkdir()
    monkeypatch.setattr(main.tempfile, "mkdtemp", lambda **kwargs: str(private_dir))
    transition = SimpleNamespace(
        from_track=Track(filePath=str(tmp_path / "a.wav"), fileName="a.wav", bpm=120),
        to_track=Track(filePath=str(tmp_path / "b.wav"), fileName="b.wav", bpm=120),
        plan=SimpleNamespace(mix_out_a=60.0, mix_in_b=0.0, overlap=16.0,
                             transition_type="smooth_blend", target_sr=44100),
    )
    worker = main.TransitionRenderWorker([transition])
    errors, ready = [], []
    worker.clip_error.connect(lambda i, error: errors.append((i, error)))
    worker.clip_ready.connect(lambda i, path: ready.append((i, path)))
    try:
        worker.run()
        assert errors == [(0, message)]
        assert ready == []
        reporter.log_error.assert_called_once_with(category, "Testfehler", {"clip": 0})
        factory.assert_called_once_with(max_workers=1)
        executor.submit.assert_called_once()
        future.result.assert_called_once_with(timeout=60.0)
        executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)
        assert worker._executor is None
    finally:
        worker.cleanup()
