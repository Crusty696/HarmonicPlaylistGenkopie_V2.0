"""Native Metadaten-/Referenzintegration; kein DSP-/Musikqualitaetsbeleg."""

from __future__ import annotations

import copy
import hashlib
import io
import threading
import wave
from dataclasses import replace
from pathlib import Path

import pytest
from PyQt6.QtCore import QBuffer, QThread
from PyQt6.QtWidgets import QDialog, QLabel

import main
from hpg_core import hearing_jobs, hearing_panel, hearing_sources
from tests.test_hearing_producer_sink import _source_service_config
from tests.test_main_window import _window


def _fingerprints(root):
    return {p.relative_to(root).as_posix(): (
        p.stat().st_size, p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()
    ) for p in root.rglob("*") if p.is_file()}


def _silence_wav():
    # Nur synthetische RAM-Nutzlast fuer die QBuffer-Grenze, kein Renderer.
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\0" * 3200)
    return buffer.getvalue()


@pytest.mark.gui
@pytest.mark.integration
@pytest.mark.parametrize("mode", ["einzel", "kandidaten", "dreinoten", "dramaturgie"])
def test_native_prepare_load_edit_reopen_source_metadata(qtbot, monkeypatch, tmp_path, mode):
    producer_mode = "kandidaten" if mode == "dreinoten" else mode
    config = _source_service_config(monkeypatch, tmp_path, producer_mode)
    if mode == "dreinoten":
        config = replace(config, three_notes=True)
    root = config.source_roots[0]
    before = _fingerprints(root)
    gui_thread = QThread.currentThread()
    original_open = Path.open
    def readonly_originals(path, mode="r", *args, **kwargs):
        if path.resolve().is_relative_to(root.resolve()):
            assert not any(flag in mode for flag in "wax+"), "Schreibzugriff auf Originalwurzel"
        return original_open(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, "open", readonly_originals)

    def forbidden(*args, **kwargs):
        raise AssertionError("Kein DSP, HTTP, CLI oder produktiver Gewichts-Write in diesem Test")
    from tools import hoertest_server, rate_transitions
    from hpg_core import candidate_preferences, transition_renderer
    monkeypatch.setattr(transition_renderer, "render_transition_clip", forbidden)
    monkeypatch.setattr(hoertest_server, "ThreadingHTTPServer", forbidden)
    monkeypatch.setattr(main.HearingWorkflowWorker, "_run_command", forbidden)
    monkeypatch.setattr(candidate_preferences, "merge_user_preferences_atomically", forbidden)
    monkeypatch.setattr(main.MainWindow, "_start_hearing_server", forbidden)
    warnings = []
    monkeypatch.setattr(main.QMessageBox, "warning", lambda *args: warnings.append(args[-1]))

    # Echte Hashpruefung beobachten, nicht durch ein Fake ersetzen.
    hashes = []
    fingerprint = hearing_sources._fingerprint
    def observe_hash(path):
        if Path(path).resolve().is_relative_to(root.resolve()):
            hashes.append((Path(path), QThread.currentThread()))
        return fingerprint(path)
    monkeypatch.setattr(hearing_sources, "_fingerprint", observe_hash)

    class AcceptedPrepareDialog:
        def __init__(self, parent):
            self.config = config
        def exec(self):
            return QDialog.DialogCode.Accepted
    monkeypatch.setattr(hearing_panel, "HearingPrepareDialog", AcceptedPrepareDialog)
    window = _window(qtbot, monkeypatch)
    starts, results, progress, finished, cleaned, dialogs = [], [], [], [], [], []
    gates = []
    start = window._start_hearing_worker
    cleanup = window._cleanup_hearing_worker
    load_run = hearing_jobs.HearingLoadWorker.run
    def pause_after_real_load(worker):
        load_run(worker)
        gate = getattr(worker, "_integration_gate", None)
        if gate is not None and not gate.wait(15):
            raise AssertionError("Test hat eigenen Load-Worker nicht freigegeben")
    monkeypatch.setattr(hearing_jobs.HearingLoadWorker, "run", pause_after_real_load)
    def observe_start(worker, action):
        starts.append((worker, action))
        if action == "rate" and len([a for _, a in starts if a == "rate"]) == 1:
            worker._integration_gate = threading.Event()
            gates.append(worker._integration_gate)
        worker.completed.connect(lambda result: results.append((id(worker), result, window._hearing_worker is worker)))
        worker.status_update.connect(lambda message: progress.append((id(worker), message, QThread.currentThread())))
        worker.finished.connect(lambda: finished.append((id(worker), worker.isRunning())))
        return start(worker, action)
    def observe_cleanup(worker):
        assert not worker.isRunning()
        assert (id(worker), False) in finished
        cleaned.append(id(worker))
        cleanup(worker)
    monkeypatch.setattr(window, "_start_hearing_worker", observe_start)
    monkeypatch.setattr(window, "_cleanup_hearing_worker", observe_cleanup)

    rating_dialog = hearing_panel.HearingRatingDialog
    class InspectRatingDialog(rating_dialog):
        def exec(self):
            assert QThread.currentThread() == gui_thread
            assert window._hearing_worker is None
            assert cleaned[-1] == id(starts[-1][0])
            assert window._hearing_native_active
            assert not window.analytics_panel.hearing_server_button.isEnabled()
            readonly = len(dialogs) == 2
            dialogs.append(copy.deepcopy(self.session))
            qtbot.addWidget(self)
            assert self.session["mode"] == mode
            assert self.pair_label.text().startswith("Sequenz " if mode == "dramaturgie" else "Paar ")
            assert self.clip_label.text().startswith("Variante ")
            labels = "\n".join(label.text() for label in self.findChildren(QLabel))
            assert all(path.name not in labels for path in root.glob("source-*.wav"))
            assert all(clip["path"] is None and clip["spec"] and clip["sources"]
                       for group in self.session["groups"] for clip in group["clips"])
            dimensions = {"einzel": ("bewertung",), "kandidaten": ("note",),
                          "dreinoten": ("track_note", "technik_note", "gesamt_note"),
                          "dramaturgie": ("track_note", "technik_note", "gesamt_note")}[mode]
            assert tuple(self.rating_boxes) == dimensions
            first = self.rating_boxes[dimensions[0]]
            controls = [*self.rating_boxes.values(), *self.sequence_boxes.values()]
            controls += [getattr(self, name) for name in ("best_button", "no_best_button") if hasattr(self, name)]
            if readonly:
                assert all(not control.isEnabled() for control in controls)
                assert "Nur Höransicht" in self.status_label.text()
            else:
                if len(dialogs) == 1:
                    assert first.currentIndex() == 0
                    assert not first.isEnabled()
                    # Synthetisches RAM-Erfolgssignal pro zu bewertendem Clip;
                    # dieser Test belegt Verkabelung/Persistenz, keinen DSP-Erfolg.
                    monkeypatch.setattr(self.player, "play", lambda: None)
                    data = _silence_wav()
                    if mode == "dramaturgie":
                        for index in range(len(self._group()["clips"])):
                            self.clip_index = index
                            self._show_clip()
                            source = object()
                            self._audio_worker = source
                            self._render_ready(data, source, self._render_generation)
                            self._audio_worker = None
                        self.clip_index = 0
                        self._show_clip()
                    source = object()
                    self._audio_worker = source
                    self._render_ready(data, source, self._render_generation)
                    assert isinstance(self._audio_buffer, QBuffer)
                    assert self._audio_buffer.isOpen()
                    assert bytes(self._audio_buffer.data()) == data
                    assert self.player.sourceDevice() is self._audio_buffer
                    assert first.isEnabled()
                    first.setCurrentIndex(4)
                    assert self._clip()["ratings"][dimensions[0]] == "4"
                    assert self.status_label.text() == "Bewertung gespeichert."
                    if mode == "dramaturgie":
                        assert self.sequence_boxes["dramaturgie_gesamt"].isEnabled()
                        self.sequence_boxes["dramaturgie_gesamt"].setCurrentIndex(4)
                        assert self._group()["ratings"]["dramaturgie_gesamt"] == "4"
                    self._audio_worker = None
                else:
                    assert first.currentIndex() == 4
                    assert not first.isEnabled()
                    if mode == "dramaturgie":
                        assert self.sequence_boxes["dramaturgie_gesamt"].currentIndex() == 4
            self.reject()
            assert self._audio_buffer is None
            assert self.player.sourceDevice() is None
            return QDialog.DialogCode.Rejected
    monkeypatch.setattr(hearing_panel, "HearingRatingDialog", InspectRatingDialog)

    try:
        # Dieser Vertrag prueft den nativen Producer-/Bewertungslebenszyklus.
        # Ordnerdialog und Analyse-Fortsetzung haben eigene Regressionen.
        window._start_hearing_worker(hearing_jobs.HearingPrepareWorker(config, window), "prepare")
        worker, action = starts[-1]
        assert action == "prepare" and isinstance(worker, hearing_jobs.HearingPrepareWorker)
        assert not window.analytics_panel.hearing_prepare_button.isEnabled()
        qtbot.waitUntil(lambda: window._hearing_worker is None, timeout=30000)
        assert results[-1][1]["ok"], results[-1][1]
        assert results[-1][1]["prepared_only"]
        assert results[-1][2]
        assert cleaned[-1] == id(worker)
        assert window._hearing_set_path == str(config.output_dir)
        assert window._hearing_cache_path == str(config.cache)
        assert "Nicht auditiert" in window.analytics_panel.hearing_status.text()
        assert any(message.startswith(f"{producer_mode}:") for _, message, _ in progress)
        assert all(thread == gui_thread for _, _, thread in progress)
        assert config.output_dir.is_dir()
        manifest = hearing_sources.strict_json_bytes((config.output_dir / hearing_sources.SOURCE_MANIFEST_NAME).read_bytes())
        assert manifest["format"] == "hpg_hearing_source_refs" and manifest["format_version"] == 1
        expected = {"einzel": 1, "kandidaten": 2, "dreinoten": 2,
                    "dramaturgie": len(rate_transitions.dramaturgie_varianten()) * 5}[mode]
        assert len(manifest["specs"]) == expected
        immutable_before = {name: (config.output_dir / name).read_bytes()
                            for name in manifest["immutable_metadata"]}
        source_manifest_before = (config.output_dir / hearing_sources.SOURCE_MANIFEST_NAME).read_bytes()

        hash_start = len(hashes)
        window._open_hearing_rating()
        loader = starts[-1][0]
        assert isinstance(loader, hearing_jobs.HearingLoadWorker)
        qtbot.waitUntil(lambda: window._hearing_pending_rating is not None, timeout=30000)
        assert window._hearing_worker is loader and loader.isRunning()
        assert not dialogs and not window._hearing_native_active
        assert not window.analytics_panel.hearing_rating_button.isEnabled()
        load_hashes = hashes[hash_start:]
        assert load_hashes and all(thread == loader and thread != gui_thread for _, thread in load_hashes)
        gates[0].set()
        qtbot.waitUntil(lambda: len(dialogs) == 1 and window._hearing_worker is None, timeout=30000)
        assert not window._hearing_native_active
        saved = {p.name: p.read_bytes() for p in config.output_dir.glob("*.csv")}

        window._open_hearing_rating()
        qtbot.waitUntil(lambda: len(dialogs) == 2 and window._hearing_worker is None, timeout=30000)
        dimension = next(iter(dialogs[1]["groups"][0]["clips"][0]["ratings"]))
        assert dialogs[1]["groups"][0]["clips"][0]["ratings"][dimension] == "4"
        window._open_hearing_preview()
        qtbot.waitUntil(lambda: len(dialogs) == 3 and window._hearing_worker is None, timeout=30000)
        assert saved == {p.name: p.read_bytes() for p in config.output_dir.glob("*.csv")}
        assert [action for _, action in starts] == ["prepare", "rate", "rate", "readonly"]
        assert len(cleaned) == len(finished) == len(starts) == 4
        assert all(result["ok"] and owned for _, result, owned in results)
        assert window._hearing_pending_rating is None and window._hearing_process is None
        assert window.analytics_panel.hearing_prepare_button.isEnabled()
        assert window.analytics_panel.hearing_rating_button.isEnabled()
        assert not window.analytics_panel.hearing_cancel_button.isEnabled()
        assert not warnings
        assert not list(config.output_dir.rglob("*.wav"))
        assert not list(config.output_dir.rglob("*.mp3"))
        assert not list(tmp_path.glob(".result.staging-*"))
        assert all(thread != gui_thread for _, thread in hashes)
        assert immutable_before == {name: (config.output_dir / name).read_bytes()
                                    for name in immutable_before}
        assert (config.output_dir / hearing_sources.SOURCE_MANIFEST_NAME).read_bytes() == source_manifest_before
        assert _fingerprints(root) == before
    finally:
        # Auch bei einem Assert nur eigene Test-Worker freigeben/abwarten.
        for gate in gates:
            gate.set()
        if window._hearing_worker is not None:
            window._hearing_worker.request_cancel()
            qtbot.waitUntil(lambda: window._hearing_worker is None, timeout=30000)


@pytest.mark.gui
@pytest.mark.parametrize("persisted,effective_reload", [(True, False), (True, True), (False, False)])
def test_apply_persistence_schedules_refresh_only_after_own_cleanup(qtbot, monkeypatch, persisted, effective_reload):
    # GUI-Ergebnisvertrag pruefen; kein echter Praeferenz-Write in diesem Test.
    window = _window(qtbot, monkeypatch)
    worker = QThread(window)
    window._hearing_worker = worker
    refreshed = []
    monkeypatch.setattr(window, "_refresh_hearing_ranking", lambda: refreshed.append(
        (window._hearing_worker, window._hearing_refresh_pending)
    ))
    state = {"persisted": persisted, "effective_reload": effective_reload,
             "error": "synthetic reload failure" if persisted and not effective_reload else ""}
    window._hearing_completed({"ok": True, "apply_state": state}, "apply", worker)
    assert window._hearing_worker is worker
    assert window._hearing_refresh_pending is persisted
    assert not refreshed
    status = window.analytics_panel.hearing_status.text()
    assert f"Gewichte gespeichert: {'JA' if persisted else 'NEIN'}" in status
    assert f"effektiver Reload: {'JA' if effective_reload else 'NEIN'}" in status
    if state["error"]:
        assert state["error"] in status
    window._cleanup_hearing_worker(worker)
    assert window._hearing_worker is None
    assert window._hearing_refresh_pending is False
    assert refreshed == ([(None, False)] if persisted else [])


@pytest.mark.gui
@pytest.mark.parametrize("initial", [main.RunState.CANCELLED, main.RunState.PLAYLIST])
def test_refresh_resets_cancelled_before_ranking_but_preserves_active_run(qtbot, monkeypatch, initial):
    from hpg_core import candidate_preferences
    window = _window(qtbot, monkeypatch)
    window.analyzed_raw_tracks = [object()]
    window._set_run_state(initial)
    settings = {"strategy": "Harmonic Flow", "advanced_params": {}}
    context = {"synthetic_scoring_context": True}
    choices = {"synthetic_choice_snapshot": True}
    events = []
    monkeypatch.setattr(candidate_preferences, "reset_cache", lambda: events.append("reset"))
    monkeypatch.setattr(window.library_panel, "get_current_settings", lambda: dict(settings))
    monkeypatch.setattr(main, "resolve_run_scoring_context", lambda strategy, parameters: context)
    monkeypatch.setattr(main.candidate_choices, "snapshot", lambda: choices)
    monkeypatch.setattr(window, "on_ai_worker_finished", lambda *, ai_completed: events.append(
        ("ranking", window.run_state, ai_completed, window._run_settings)
    ))
    window._refresh_hearing_ranking()
    if initial == main.RunState.CANCELLED:
        assert window.run_state == main.RunState.IDLE
        # Der KI-Schalter ist separate Metadaten des genehmigten Refresh-Vertrags.
        assert events == ["reset", ("ranking", main.RunState.IDLE, False,
                                   settings | {"ai_enabled": False, "scoring_context": context, "candidate_choice_snapshot": choices})]
        # Der Start-Helfer ist beobachtet, nicht ausgefuehrt: kein Ranking-Beleg.
        assert window.playlist_worker is None
        assert "Sichtbares Ranking nicht aktualisiert" in window.analytics_panel.hearing_status.text()
    else:
        assert window.run_state == main.RunState.PLAYLIST
        assert not events
    window._set_run_state(main.RunState.IDLE)
