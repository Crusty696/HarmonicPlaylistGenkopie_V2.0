"""Abbrechbarer Einmalprozess fuer Playlist-Reserve und RAM-Vorschau."""
import copy
import math
import multiprocessing
import threading
import time
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal


def _child(sender, result, index, timeout):
    try:
        from .render_selection import render_with_reserve
        from .hearing_sources import _fingerprint
        deadline = time.monotonic() + timeout
        def checkpoint():
            if time.monotonic() >= deadline:
                raise TimeoutError('Renderreserve ueberschreitet Zeitlimit')
        sources = []
        for track in result.tracks[index:index+2]:
            path = Path(track.filePath).resolve(strict=True)
            fingerprint = _fingerprint(path)
            sources.append(dict(path=str(path), size_bytes=fingerprint['size'],
                                sha256=fingerprint['sha256']))
        selected = render_with_reserve(result, index, sources, checkpoint)
        # Wellenformdaten im Kindprozess berechnen, niemals im GUI-Thread.
        import io
        import numpy as np
        import soundfile as sf
        audio, sr = sf.read(io.BytesIO(selected.audio), always_2d=True)
        peaks = [float(np.max(np.abs(block))) for block in np.array_split(audio, 512) if len(block)]
        sender.send((True, selected, peaks, len(audio)/sr))
    except Exception as error:
        sender.send((False, f'{type(error).__name__}: {error}', None, None))
    finally:
        sender.close()


class RenderSelectionWorker(QThread):
    clip_error = pyqtSignal(int, str)

    def __init__(self, result, index, parent=None, timeout=120.):
        if (type(timeout) not in (int, float) or not math.isfinite(timeout)
                or timeout <= 0):
            raise ValueError('Ungueltiges Renderzeitlimit')
        super().__init__(parent)
        self.base_result = result
        self._snapshot = copy.deepcopy(result)
        self.index = index
        self.timeout = timeout
        self.selection = None
        self.peaks = None
        self.duration = None
        self._cancel = threading.Event()

    def request_cancel(self):
        self._cancel.set()

    def get_temp_dir(self):
        return None

    def get_temp_files(self):
        return []

    def run(self):
        receiver = sender = process = None
        started = False
        try:
            if self._cancel.is_set():
                return
            ctx = multiprocessing.get_context('spawn')
            receiver, sender = ctx.Pipe(duplex=False)
            process = ctx.Process(target=_child,
                args=(sender, self._snapshot, self.index, self.timeout), daemon=True)
            process.start()
            started = True
            sender.close()
            deadline = time.monotonic()+self.timeout
            while not self._cancel.is_set():
                if time.monotonic() >= deadline:
                    raise TimeoutError('Renderreserve ueberschreitet Zeitlimit')
                if receiver.poll(.1):
                    ok, payload, peaks, duration = receiver.recv()
                    if self._cancel.is_set():
                        return
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Renderreserve ueberschreitet Zeitlimit')
                    if not ok:
                        raise RuntimeError(payload)
                    # Empfang allein beweist keinen erfolgreichen Prozesslauf.
                    # Erst sauber beendete Ergebnisse fuer die GUI freigeben.
                    process.join(timeout=min(2., max(0., deadline-time.monotonic())))
                    if self._cancel.is_set():
                        return
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Renderreserve ueberschreitet Zeitlimit')
                    if process.is_alive() or process.exitcode != 0:
                        raise RuntimeError('Renderprozess nach Ergebnis nicht sauber beendet')
                    self.selection, self.peaks, self.duration = payload, peaks, duration
                    return
                if not process.is_alive():
                    raise RuntimeError(f'Renderprozess ohne Ergebnis beendet: {process.exitcode}')
                if time.monotonic() >= deadline:
                    raise TimeoutError('Renderreserve ueberschreitet Zeitlimit')
        except Exception as error:
            if not self._cancel.is_set():
                self.clip_error.emit(self.index, str(error))
        finally:
            if receiver is not None:
                receiver.close()
            if sender is not None:
                sender.close()
            if started:
                process.join(timeout=.1)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=2.)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=2.)
                if process.is_alive():
                    self.selection = None
                    self.clip_error.emit(self.index, 'Renderprozess konnte nicht beendet werden')
                else:
                    process.close()
            if self._cancel.is_set():
                self.selection = self.peaks = self.duration = None
