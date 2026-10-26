"""Begrenztes Lesen von Originalaudio für zusätzliche Modellmerkmale.

HPG-Vorverarbeitung: libsndfile-Float32, SoXR-HQ und Nullpadding. Keine
behauptete Bitgleichheit mit dem Rekordbox-Decoder, keine Audiodateien schreiben.
"""
import math

import numpy as np


def mono_downmix(samples):
    """Faltet unbekannte Mehrkanal-Layouts reproduzierbar auf Mono zusammen."""
    values = np.asarray(samples, dtype=np.float32)
    if values.ndim != 2 or not 1 <= values.shape[1] <= 32:
        raise ValueError('Unsupported audio channel layout')
    if values.shape[1] <= 2:
        return values
    return np.mean(values, axis=1, keepdims=True, dtype=np.float32)


def source_identity(path):
    value = path.stat()
    return [value.st_size, value.st_mtime_ns, value.st_ctime_ns,
            value.st_dev, value.st_ino]


def windows(source, rate, width, hop, *, left_padding=0):
    """Liefert (Startsample, gültige Samples, planar Float32) mit begrenztem RAM."""
    import soxr

    if not 1 <= source.channels <= 32 or not 0 < len(source)/source.samplerate <= 7200:
        raise ValueError('Unsupported source dimensions')
    source_channels = source.channels
    channels = 1 if source_channels > 2 else source_channels
    total = int(round(len(source)*rate/source.samplerate))
    if total <= 0 or not 0 < hop <= width or not 0 <= left_padding < width:
        raise ValueError('Invalid window geometry')
    resampler = (soxr.ResampleStream(source.samplerate, rate, channels,
                                   dtype='float32', quality='HQ')
                 if source.samplerate != rate else None)
    buffered = np.zeros((left_padding, channels), np.float32)
    start = 0
    exhausted = False
    while start < total:
        while len(buffered) < width and not exhausted:
            pcm = source.read(65536, dtype='float32', always_2d=True)
            if source_channels > 2:
                pcm = mono_downmix(pcm)
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
        required = min(width, left_padding + valid)
        if available < required:
            raise ValueError('Incomplete resampled source coverage')
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
