"""Transiente Stereo-Tempoanpassung mit dem bereits gebündelten Pedalboard."""
import math

import numpy as np


def stretch(audio, sr, rate):
    """Rate > 1 verkürzt; Tonhöhe und gemeinsames Stereo-Timing bleiben."""
    if not math.isfinite(rate) or rate <= 0 or not math.isfinite(sr) or sr <= 0:
        raise ValueError('Invalid preview stretch rate/sample rate')
    if abs(rate - 1.) < 1e-9:
        return audio
    from pedalboard import time_stretch
    values = np.asarray(audio, dtype=np.float32)
    if values.ndim != 2 or values.shape[1] not in (1, 2) or not np.isfinite(values).all():
        raise ValueError('Invalid preview stretch audio')
    result = time_stretch(
        np.ascontiguousarray(values.T), sr, stretch_factor=rate,
        # Der alternative HQ-Modus verschiebt lokale Anschläge trotz korrekter
        # Gesamtlänge. Der Standardmodus hält die gemessenen Kickfenster ein.
        # Gemischter Modus erhält auch stationäre tonale Anteile; vollständige
        # Phasenresets im Crisp-Modus können deren Tonhöhe verschieben.
        high_quality=False, transient_mode='mixed', transient_detector='percussive',
        # Das lange Fenster verhindert Tonhöhendrift bei stationären Tönen,
        # auch bei anderen Sampleraten als dem 44,1-kHz-Previewstandard.
        retain_phase_continuity=True, use_long_fft_window=True,
        use_time_domain_smoothing=False,
    ).T
    if result.ndim != 2 or result.shape[1] != values.shape[1] or not np.isfinite(result).all():
        raise ValueError('Invalid preview stretch result')
    return np.ascontiguousarray(result)
