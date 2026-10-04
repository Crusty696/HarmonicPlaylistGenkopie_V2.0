"""Isolierter On-Demand-Render in RAM; keine dauerhaften WAV-Artefakte."""

import io
import multiprocessing
import threading
import time
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal


MAX_PLAYBACK_BYTES = 128 * 1024 * 1024


class _NamedWavBuffer(io.BytesIO):
    name = "preview.wav"


def _check_sources(sources):
    from .hearing_sources import _fingerprint
    for source in sources:
        path = Path(source["path"])
        canonical = path.resolve(strict=True)
        if canonical != path:
            raise ValueError("Quellpfad wurde umgeleitet")
        if source.get("root"):
            root = Path(source["root"])
            if root.resolve(strict=True) != root or root not in canonical.parents:
                raise ValueError("Quelle liegt außerhalb des freigegebenen Musikordners")
        if not path.is_file() or path.stat().st_size != source["size_bytes"]:
            raise ValueError("Quelle fehlt oder hat sich geändert")
        fingerprint = _fingerprint(path)
        if fingerprint != {"size": source["size_bytes"], "sha256": source["sha256"]}:
            raise ValueError("Quelle hat sich geändert")


def render_wav_bytes(spec, sources=()):
    """Benutzt unverändert den gemeinsamen DSP-Renderer und bindet Quellen."""
    from hpg_core.transition_renderer import TransitionClipSpec, render_transition_clip

    _check_sources(sources)
    with _NamedWavBuffer() as buffer:
        render_transition_clip(TransitionClipSpec(**spec), buffer)
        data = buffer.getvalue()
    if not data or len(data) > MAX_PLAYBACK_BYTES:
        raise ValueError("Audioausgabe leer oder über dem Playback-Limit")
    _check_sources(sources)
    return data


def _render_child(connection, spec, sources):
    """Kindprozess sendet begrenzte Bytes; Eltern liest vor dem Join."""
    try:
        connection.send((True, render_wav_bytes(spec, sources)))
    except Exception as exc:
        connection.send((False, f"{type(exc).__name__}: {exc}"))
    finally:
        connection.close()


class HearingAudioWorker(QThread):
    """QThread steuert ausschließlich seinen eigenen Renderprozess."""

    audio_ready = pyqtSignal(bytes)
    audio_error = pyqtSignal(str)

    def __init__(self, spec, sources=(), parent=None, timeout=120.0):
        super().__init__(parent)
        self.spec = dict(spec)
        self.sources = list(sources)
        self.timeout = float(timeout)
        self._cancel = threading.Event()

    def request_cancel(self):
        self._cancel.set()

    def run(self):
        if self._cancel.is_set():
            return
        context = multiprocessing.get_context("spawn")
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(target=_render_child, args=(sender, self.spec, self.sources), daemon=True)
        started = False
        try:
            if self._cancel.is_set():
                return
            process.start()
            started = True
            sender.close()
            deadline = time.monotonic() + self.timeout
            while not self._cancel.is_set():
                if receiver.poll(0.1):
                    ok, payload = receiver.recv()
                    if self._cancel.is_set():
                        return
                    if ok:
                        if not isinstance(payload, bytes) or len(payload) > MAX_PLAYBACK_BYTES:
                            raise ValueError("Ungültige Playback-Ausgabe")
                        self.audio_ready.emit(payload)
                    else:
                        self.audio_error.emit(str(payload))
                    return
                if not process.is_alive():
                    raise RuntimeError(f"Renderprozess beendet ohne Ergebnis ({process.exitcode})")
                if time.monotonic() >= deadline:
                    raise TimeoutError("Übergangsrender überschreitet Zeitlimit")
        except Exception as exc:
            if not self._cancel.is_set():
                self.audio_error.emit(str(exc))
        finally:
            receiver.close()
            sender.close()
            if started:
                process.join(timeout=0.1)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=2.0)
                if process.is_alive():
                    process.kill()
                    process.join()
                process.close()
