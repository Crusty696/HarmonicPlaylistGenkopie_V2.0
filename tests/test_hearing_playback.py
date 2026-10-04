"""Uebergangs-Playback erzeugt keine dauerhafte Audiodatei."""

import io

import numpy as np
import soundfile as sf


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
