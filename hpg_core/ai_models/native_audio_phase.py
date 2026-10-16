"""Kurze Audio-Attacks an einer nativen Beat-Referenz frei vermessen.

Die Referenz begrenzt nur die Ereignisfamilie. Der gemessene Zeitpunkt wird
nicht auf das Grid gezogen. Native Taktnummern bleiben davon unabhängig.
"""
import math
from functools import lru_cache
from pathlib import Path
import numpy as np
from scipy.signal import butter, sosfiltfilt
from scipy.ndimage import uniform_filter1d


def _fold(audio, sr, period):
    envelope = np.abs(sosfiltfilt(butter(4, 300., fs=sr,
                                       btype='highpass', output='sos'), audio))
    envelope = uniform_filter1d(envelope, size=max(3, round(.001*sr) | 1))
    bins = np.minimum(1023, (np.mod(np.arange(len(audio))/sr, period)/period*1024).astype(int))
    profile = np.bincount(bins, weights=envelope, minlength=1024)/np.maximum(
        1, np.bincount(bins, minlength=1024))
    gradient = uniform_filter1d(profile-np.roll(profile, 1), size=3, mode='wrap')
    return profile, gradient


def measure(y, sr, period, expected, *, minimum_beats=8):
    if (not all(math.isfinite(v) for v in (sr, period, expected))
            or sr <= 600 or period <= 0):
        return None, 0.
    audio = np.asarray(y, dtype=np.float64)
    if (audio.ndim != 1 or len(audio) < minimum_beats*period*sr
            or not np.isfinite(audio).all()):
        return None, 0.
    # Basskörper können ihren Schwerpunkt im Song verschieben. Der kurze
    # breitbandige Anschlag bleibt als eigenständige Messgröße erhalten.
    profile, gradient = _fold(audio, sr, period)
    if np.max(profile) <= 1e-12:
        return None, 0.
    positions = np.arange(1024)*period/1024
    distance = (positions-expected+period/2) % period-period/2
    candidates = np.flatnonzero(np.abs(distance) < period/8)
    peak = int(candidates[np.argmax(gradient[candidates])])
    # Kein Rauschen als Attack behandeln: deutlicher Anstieg gegenüber der
    # robusten Streuung der Ableitung über die gesamte Periode erforderlich.
    noise = float(np.median(np.abs(gradient-np.median(gradient))))
    if gradient[peak] <= max(1e-12, 6*noise):
        return None, 0.
    attack = peak
    for step in range(128):
        index = (peak-step) % 1024
        if gradient[index] <= gradient[peak]*.1:
            attack = index
            break
    else:
        return None, 0.
    lock = float(np.clip((np.max(profile)-np.min(profile))/np.max(profile), 0., 1.))
    return float(attack)*period/1024, lock


def supports_window(track, start, duration):
    """Nur lokal lesend; Wiederverwendung an aktuelle Quellidentität binden."""
    from .native_phrase_worker import _source_identity
    try:
        path = Path(track.filePath).resolve(strict=True)
        identity = tuple(_source_identity(path))
        if identity != tuple(track.native_beat_analysis['source_identity']):
            return False
        return _supports_window(str(path), identity, track.bpm,
                                track.first_downbeat, start, duration)
    except (OSError, ValueError, KeyError):
        return False


@lru_cache(maxsize=512)
def _supports_window(path, identity, bpm, anchor, start, duration):
    # Dieselben zusammenhängenden Vier-Beat-Fenster wie im Referenzrenderer.
    # Nur boolesche Resultate cachen; keine Audio-Datei oder Audiodaten halten.
    import soundfile as sf
    from ..downbeat import EXACT_BEAT_SYNC_TOLERANCE_SECONDS, BEATGRID_MIN_FOLD_LOCK
    from .native_phrase_worker import _source_identity
    period = 60./bpm
    try:
        with sf.SoundFile(path) as source:
            sr = source.samplerate
            frames = round(duration*sr)
            window = math.ceil(4*period*sr)
            if start < 0 or frames < window:
                return False
            source.seek(round(start*sr))
            audio = source.read(frames, dtype='float64', always_2d=True)
        if len(audio) != frames:
            return False
        starts = list(range(0, frames-window+1, window))
        if starts[-1] != frames-window:
            starts.append(frames-window)
        for offset in starts:
            expected = (anchor-start-offset/sr) % period
            phase, lock = measure(audio[offset:offset+window].mean(axis=1),
                                  sr, period, expected, minimum_beats=4)
            if (phase is None or lock < BEATGRID_MIN_FOLD_LOCK
                    or abs((phase-expected+period/2) % period-period/2)
                    > EXACT_BEAT_SYNC_TOLERANCE_SECONDS):
                return False
        return tuple(_source_identity(Path(path))) == identity
    except (OSError, ValueError, RuntimeError):
        return False
