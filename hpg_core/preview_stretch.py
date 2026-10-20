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
        high_quality=True, transient_mode='crisp', transient_detector='percussive',
        retain_phase_continuity=True, use_long_fft_window=False,
        use_time_domain_smoothing=False,
    ).T
    if result.ndim != 2 or result.shape[1] != values.shape[1] or not np.isfinite(result).all():
        raise ValueError('Invalid preview stretch result')
    return np.ascontiguousarray(result)
