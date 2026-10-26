"""Uebergangs-Playback erzeugt keine dauerhafte Audiodatei."""

import io
from pathlib import Path

import numpy as np
import soundfile as sf
import pytest


def test_memory_render_returns_readable_wav_without_disk_output(monkeypatch, tmp_path):
    from hpg_core import hearing_playback as playback

    def render(_spec, output):
        sf.write(output, np.zeros((8000, 2), dtype=np.float32), 8000, subtype="PCM_16")
        return output

    monkeypatch.setattr("hpg_core.transition_renderer.render_transition_clip", render)
    before = list(tmp_path.iterdir())
    data = playback.render_wav_bytes({"track_a_path": "a", "track_b_path": "b", "mix_out_sec": 1.0, "mix_in_sec": 1.0, "crossfade_sec": 1.0})
    audio, sample_rate = sf.read(io.BytesIO(data))
    assert sample_rate == 8000
    assert audio.shape == (8000, 2)
    assert list(tmp_path.iterdir()) == before


def test_memory_render_rejects_changed_original_before_dsp(monkeypatch, tmp_path):
    from hpg_core import hearing_playback as playback

    source = tmp_path / "source.bin"
    source.write_bytes(b"changed")
    calls = []
    monkeypatch.setattr("hpg_core.transition_renderer.render_transition_clip", lambda *_args: calls.append(True))
    import pytest
    with pytest.raises(ValueError, match="Quelle"):
        playback.render_wav_bytes({}, [{"path": str(source), "size_bytes": 7, "sha256": "0" * 64}])
    assert calls == []


def test_audio_worker_cancel_before_start_never_spawns(qtbot, monkeypatch):
    from hpg_core.hearing_playback import HearingAudioWorker

    worker = HearingAudioWorker({})
    results = []
    worker.audio_ready.connect(results.append)
    worker.request_cancel()
    worker.start()
    qtbot.waitUntil(lambda: not worker.isRunning(), timeout=3000)
    assert results == []


def test_audio_worker_real_spawn_renders_only_to_memory(tmp_path, qtbot):
    import hashlib
    from dataclasses import asdict
    from hpg_core.transition_renderer import TransitionClipSpec
    from hpg_core.hearing_playback import HearingAudioWorker

    paths = [tmp_path / "a.wav", tmp_path / "b.wav"]
    signal = (0.15 * np.sin(np.arange(8000 * 6) * (2 * np.pi * 330 / 8000))).astype(np.float32)
    for path in paths:
        sf.write(path, np.column_stack((signal, signal)), 8000, subtype="PCM_16")
    hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    spec = TransitionClipSpec(str(paths[0]), str(paths[1]), 2.0, 1.0, 1.0,
        target_sr=8000, pre_roll_sec=1.0, post_roll_sec=1.0, strict_beat_sync=False)
    worker = HearingAudioWorker(asdict(spec), timeout=30)
    ready, errors = [], []
    worker.audio_ready.connect(ready.append)
    worker.audio_error.connect(errors.append)
    worker.start()
    try:
        qtbot.waitUntil(lambda: bool(ready or errors), timeout=40000)
        qtbot.waitUntil(lambda: not worker.isRunning(), timeout=5000)
        assert errors == []
        info = sf.info(io.BytesIO(ready[0]))
        assert info.frames == 8000 * 3
        assert info.channels == 2
        assert set(tmp_path.iterdir()) == set(paths)
        assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths} == hashes
    finally:
        worker.request_cancel()
        assert worker.wait(5000)


def test_preflight_child_accepts_only_actual_render_and_classifies_beat_sync(tmp_path):
    import hashlib
    from hpg_core.transition_renderer import TransitionClipSpec
    from hpg_core.hearing_playback import preflight_renderability

    paths = [tmp_path / "a.wav", tmp_path / "b.wav"]
    signal = (0.15 * np.sin(np.arange(8000 * 6) * (2 * np.pi * 330 / 8000))).astype(np.float32)
    for path in paths:
        sf.write(path, np.column_stack((signal, signal)), 8000, subtype="PCM_16")
    sources = [{"path": str(path), "root": str(tmp_path), "size_bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in paths]
    base = dict(target_sr=8000, pre_roll_sec=1.0, post_roll_sec=1.0)
    allowed = TransitionClipSpec(str(paths[0]), str(paths[1]), 2.0, 1.0, 1.0,
                                 strict_beat_sync=False, **base)
    rejected = TransitionClipSpec(str(paths[0]), str(paths[1]), 2.0, 1.0, 1.0,
                                  strict_beat_sync=True, **base)
    assert preflight_renderability(allowed, sources, lambda: None, timeout=30) is True
    assert preflight_renderability(rejected, sources, lambda: None, timeout=30) is False
    assert set(tmp_path.iterdir()) == set(paths)
    assert all(hashlib.sha256(Path(source["path"]).read_bytes()).hexdigest() == source["sha256"]
               for source in sources)


def test_preflight_decode_error_is_not_a_pair_rejection(tmp_path):
    import hashlib
    import pytest
    from hpg_core.transition_renderer import TransitionClipSpec
    from hpg_core.hearing_playback import preflight_renderability

    paths = [tmp_path / "a.wav", tmp_path / "b.wav"]
    for path in paths:
        path.write_bytes(b"kein gueltiges WAV")
    sources = [{"path": str(path), "root": str(tmp_path), "size_bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in paths]
    spec = TransitionClipSpec(str(paths[0]), str(paths[1]), 2.0, 1.0, 1.0,
                              target_sr=8000, pre_roll_sec=1.0, post_roll_sec=1.0)
    with pytest.raises(RuntimeError, match="Preflight-Renderfehler"):
        preflight_renderability(spec, sources, lambda: None, timeout=30)
    assert set(tmp_path.iterdir()) == set(paths)


def test_preflight_rejects_nonfinite_timeout_before_spawn(monkeypatch):
    import pytest
    from hpg_core import hearing_playback as playback

    monkeypatch.setattr(playback.multiprocessing, "get_context", lambda *_args: pytest.fail("Kindprozess gestartet"))
    for timeout in (float("nan"), float("inf"), 0, -1, True):
        with pytest.raises(ValueError, match="Preflight-Vertrag"):
            playback.preflight_renderability(None, (), lambda: None, timeout=timeout)


def test_preflight_child_accepts_strict_synchronized_synthetic_kicks(tmp_path):
    import hashlib
    from hpg_core.transition_renderer import TransitionClipSpec
    from hpg_core.hearing_playback import preflight_renderability

    sr = 8000
    mono = np.zeros(sr * 20, dtype=np.float32)
    burst_t = np.arange(int(0.12 * sr), dtype=np.float32) / sr
    burst = np.sin(2 * np.pi * 60.0 * burst_t) * np.exp(-28.0 * burst_t)
    for start in range(0, len(mono), sr // 2):
        mono[start:start + len(burst)] += burst
    paths = [tmp_path / "a.wav", tmp_path / "b.wav"]
    for path in paths:
        sf.write(path, np.column_stack((mono, mono)), sr, subtype="PCM_16")
    sources = [{"path": str(path), "root": str(tmp_path), "size_bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in paths]
    spec = TransitionClipSpec(str(paths[0]), str(paths[1]), 8.0, 8.0, 6.0,
        target_sr=sr, pre_roll_sec=1.0, post_roll_sec=1.0, bpm_a=120.0, bpm_b=120.0,
        first_downbeat_a=0.0, first_downbeat_b=0.0,
        downbeat_reliable_a=True, downbeat_reliable_b=True,
        bar_phase_reliable_a=True, bar_phase_reliable_b=True,
        beatgrid_status_a="verified", beatgrid_status_b="verified",
        strict_beat_sync=True)
    assert preflight_renderability(spec, sources, lambda: None, timeout=30) is True
    assert set(tmp_path.iterdir()) == set(paths)


def test_preflight_running_child_times_out_and_keeps_sources(tmp_path):
    import hashlib
    import pytest
    from hpg_core.transition_renderer import TransitionClipSpec
    from hpg_core.hearing_playback import preflight_renderability

    paths = [tmp_path / "a.wav", tmp_path / "b.wav"]
    for path in paths:
        sf.write(path, np.zeros((8000, 2), dtype=np.float32), 8000)
    sources = [{"path": str(path), "root": str(tmp_path), "size_bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in paths]
    spec = TransitionClipSpec(str(paths[0]), str(paths[1]), 0.4, 0.4, 0.2,
                              target_sr=8000, strict_beat_sync=False)
    with pytest.raises(TimeoutError, match="Zeitlimit"):
        preflight_renderability(spec, sources, lambda: None, timeout=0.001)
    assert set(tmp_path.iterdir()) == set(paths)
    assert all(hashlib.sha256(Path(source["path"]).read_bytes()).hexdigest() == source["sha256"]
               for source in sources)


@pytest.mark.parametrize("scenario,error,message", [
    ("late", TimeoutError, "Zeitlimit"),
    ("error_exit", RuntimeError, "fehlerhaft beendet \\(7\\)"),
    ("no_result", RuntimeError, "ohne Ergebnis \\(9\\)"),
    ("cancel", InterruptedError, "Testabbruch"),
])
def test_preflight_process_contract_rejects_failed_children_and_cleans_up(
        monkeypatch, scenario, error, message):
    """Parent-Vertrag mit steuerbaren Doubles; kein nativer Rendernachweis."""
    from types import SimpleNamespace
    from hpg_core import hearing_playback as playback
    from hpg_core.transition_renderer import TransitionClipSpec

    events = []
    clock = [0.0]

    class Process:
        exitcode = None
        alive = False
        started = False

        def start(self):
            self.started = self.alive = True
            events.append("start")

        def is_alive(self):
            return self.alive

        def join(self, timeout):
            events.append("join")

        def terminate(self):
            events.append("terminate")
            self.alive, self.exitcode = False, -15

        def kill(self):
            pytest.fail("Terminate muss diesen eigenen Prozess beenden")

        def close(self):
            assert not self.alive
            events.append("process_close")

    process = Process()

    class Pipe:
        def __init__(self, name):
            self.name = name

        def poll(self, timeout):
            if scenario == "late":
                clock[0] = 2.0  # Antwort erst nach der einsekündigen Deadline.
                return True
            process.alive = False
            process.exitcode = 7 if scenario == "error_exit" else 9
            return scenario == "error_exit"

        def recv(self):
            events.append("recv")
            return ("ok", 100)

        def close(self):
            events.append(self.name + "_close")

    receiver, sender = Pipe("receiver"), Pipe("sender")
    context = SimpleNamespace(Pipe=lambda **kwargs: (receiver, sender),
                              Process=lambda **kwargs: process)
    monkeypatch.setattr(playback.multiprocessing, "get_context", lambda method: context)
    monkeypatch.setattr(playback.time, "monotonic", lambda: clock[0])

    def checkpoint():
        if scenario == "cancel" and process.started:
            raise InterruptedError("Testabbruch nach Kindstart")

    spec = TransitionClipSpec("a", "b", 1.0, 1.0, 1.0)
    with pytest.raises(error, match=message):
        playback.preflight_renderability(spec, (), checkpoint, timeout=1.0)
    assert events[0] == "start"
    assert "join" in events
    assert "receiver_close" in events and "sender_close" in events
    assert events[-1] == "process_close"
    assert not process.alive
    assert ("terminate" in events) == (scenario in {"late", "cancel"})
    assert ("recv" in events) == (scenario in {"late", "error_exit"})
