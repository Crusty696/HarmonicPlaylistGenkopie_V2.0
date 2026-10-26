"""Bassreiche Messfenster wählen, ohne Beatphase oder Restfehler zu verwenden."""
import math

import numpy as np
from scipy.signal import butter, sosfilt


def second_energy(audio, sr):
    """Bandenergie je vollständiger Sekunde; keine zeitliche Kickmessung."""
    values = np.asarray(audio, dtype=np.float64)
    if values.ndim != 1 or sr <= 300 or not np.isfinite(values).all():
        raise ValueError('Invalid energy input')
    width = round(sr)
    count = len(values) // width
    if not count:
        return np.empty(0)
    filtered = sosfilt(butter(4, [35., 150.], fs=sr, btype='bandpass',
                              output='sos'), values)
    return np.mean(filtered[:count * width].reshape(count, width) ** 2, axis=1)


def eligible_starts(energy, span):
    """Alle Sekunden des Fensters müssen kräftige Bassenergie enthalten.

    Relative Schwelle macht die Auswahl unabhängig vom Mastering-Pegel.
    Keine Referenzphase, kein Synchronfehler und kein Verifikationsstatus
    fließen in diese Auswahl ein.
    """
    values = np.asarray(energy, dtype=np.float64)
    if (values.ndim != 1 or not np.isfinite(values).all()
            or np.any(values < 0) or not math.isfinite(span) or span <= 0):
        raise ValueError('Invalid energy window')
    width = math.ceil(span)
    if len(values) < width:
        return frozenset()
    reference = float(np.percentile(values, 75))
    if reference <= 1e-12:
        return frozenset()
    # 3 dB unter dem oberen Energiequartil, vor jeder Phasenprüfung.
    valid = values >= reference * .5
    counts = np.convolve(valid.astype(int), np.ones(width, dtype=int), mode='valid')
    return frozenset(int(start) for start in np.flatnonzero(counts == width))


def source_energy(path, duration, head, sr, loader):
    """Vorhandenen Head nutzen; fehlende Sekunden begrenzt am Quellort lesen."""
    total = math.floor(duration)
    energy = second_energy(head, sr)[:total]
    pieces = [energy]
    position = len(energy)
    while position < total:
        width = min(60, total - position)
        audio, loaded_sr = loader(path, sr=sr, offset=position, duration=width)
        block = second_energy(audio, loaded_sr)
        if loaded_sr != sr or len(block) != width:
            raise ValueError('Incomplete source energy window')
        pieces.append(block)
        position += width
    return np.concatenate(pieces)
