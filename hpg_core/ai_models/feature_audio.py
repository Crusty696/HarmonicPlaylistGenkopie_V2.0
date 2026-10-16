"""Begrenztes Lesen von Originalaudio für zusätzliche Modellmerkmale.

HPG-Vorverarbeitung: libsndfile-Float32, SoXR-HQ und Nullpadding. Keine
behauptete Bitgleichheit mit dem Rekordbox-Decoder, keine Audiodateien schreiben.
"""
import math

import numpy as np


def source_identity(path):
    value = path.stat()
    return [value.st_size, value.st_mtime_ns, value.st_dev, value.st_ino]


def windows(source, rate, width, hop, *, left_padding=0):
    """Liefert (Startsample, gültige Samples, planar Float32) mit begrenztem RAM."""
    import soxr

    if source.channels not in (1, 2) or not 0 < len(source)/source.samplerate <= 7200:
        raise ValueError('Unsupported source dimensions')
    total = int(round(len(source)*rate/source.samplerate))
    if total <= 0 or not 0 < hop <= width or not 0 <= left_padding < width:
        raise ValueError('Invalid window geometry')
    resampler = (soxr.ResampleStream(source.samplerate, rate, source.channels,
                                   dtype='float32', quality='HQ')
                 if source.samplerate != rate else None)
    buffered = np.zeros((left_padding, source.channels), np.float32)
    start = 0
    exhausted = False
    while start < total:
        while len(buffered) < width and not exhausted:
            pcm = source.read(65536, dtype='float32', always_2d=True)
            exhausted = source.tell() >= len(source)
            if not len(pcm) and not exhausted:
                raise ValueError('Unexpected audio EOF')
            if not np.isfinite(pcm).all():
                raise ValueError('Nonfinite audio')
            if resampler is not None:
                pcm = resampler.resample_chunk(pcm, last=exhausted)
            buffered = np.concatenate((buffered, pcm), axis=0)
        valid = min(hop, total-start)
        block = np.zeros((width, 2), np.float32)
        available = min(width, len(buffered))
        block[:available, 0] = buffered[:available, 0]
        block[:available, 1] = buffered[:available, -1]
        yield start, valid, np.ascontiguousarray(block.T)
        buffered = buffered[hop:]
        start += hop


class EnergyBins:
    """RMS je absoluter Sekunde; Blockgrenzen ändern das Zeitraster nicht."""
    def __init__(self, total_samples, rate, names):
        self.rate = rate
        self.names = names
        self.sums = np.zeros((len(names), math.ceil(total_samples/rate)), np.float64)
        self.counts = np.zeros(self.sums.shape[1], np.int64)

    def add(self, start, signals):
        values = np.asarray(signals, dtype=np.float64)
        if values.ndim != 3 or values.shape[:2] != (len(self.names), 2) or not np.isfinite(values).all():
            raise ValueError('Invalid stem output')
        offset = 0
        while offset < values.shape[2]:
            absolute = start + offset
            index = absolute // self.rate
            count = min(values.shape[2]-offset, self.rate-absolute % self.rate)
            self.sums[:, index] += np.sum(values[:, :, offset:offset+count]**2, axis=(1, 2))
            self.counts[index] += count*2
            offset += count

    def result(self):
        if np.any(self.counts <= 0):
            raise ValueError('Incomplete stem coverage')
        return {name: np.sqrt(self.sums[index]/self.counts).tolist()
                for index, name in enumerate(self.names)}
