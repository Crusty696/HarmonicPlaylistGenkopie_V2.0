"""Rekonstruierte Modellwahl aus Rekordbox 7.2.19, RVA128ecd0.

Konfiguration 2 übernimmt das gespeicherte native Modusbit; sie bedeutet
nicht automatisch eine Tempoheuristik. 3 und 4 wählen ausdrücklich Modell8/7.
Die Zuordnung zu Rekordbox-Oberflächenbezeichnungen ist nicht belegt.
"""
import os
import math


VERSION = 'rb-7.2.19-mode-selection-v2'
MAX_NATIVE_BEAT_WINDOW_SECONDS = 1200
MAX_NATIVE_BEAT_SECONDS = 7200
MAX_NATIVE_TRACK_JOB_SECONDS = 420


def is_chunk_seam_pair(previous, current):
    """Doppelte Modell7-Rohereignisse an einer 60-s-Naht erkennen.

    Nur Float32-Rundungsfehler an exakt derselben Naht sind erlaubt.
    Das native korrigierte Beatgrid wird weiterhin streng validiert.
    """
    if not (math.isfinite(previous) and math.isfinite(current)):
        return False
    seam = round(current / 60.) * 60.
    if seam <= 0 or current > previous:
        return False
    tolerance = math.ldexp(1., math.frexp(seam)[1] - 24) * 2
    return abs(previous - seam) <= tolerance and abs(current - seam) <= tolerance


def native_track_job_timeout_seconds(duration):
    """Bound native beat/phrase work by source duration, up to seven minutes."""
    import math
    if (type(duration) not in (int, float) or not math.isfinite(duration)
            or not 0 < duration <= MAX_NATIVE_BEAT_SECONDS):
        raise ValueError('Invalid native track duration')
    return min(float(MAX_NATIVE_TRACK_JOB_SECONDS), max(180., 120. + duration / 24.))


def maximum_native_beat_rows(frames):
    """Maximale Beatanzahl aus Readerdauer und bestehender BPM-Grenze ableiten."""
    import math
    if type(frames) is not int or frames < 0:
        raise ValueError('Invalid native beat frame count')
    # 215 BPM ist die obere native HPG-Grenze; +1 deckt beide Randbeats ab.
    return math.ceil(frames / 44100 * 215 / 60) + 1


def native_beat_segment_count(frames):
    """Zahl der festen 20-Minuten-Fenster mit zehn Beat Überlappung."""
    import math
    if type(frames) is not int or frames < 0:
        raise ValueError('Invalid native beat frame count')
    window = MAX_NATIVE_BEAT_WINDOW_SECONDS * 44100
    if frames <= window:
        return 1
    overlap = math.ceil(10 * 60 / 55 * 44100)
    step = window - overlap
    return math.ceil((frames - window) / step) + 1


def configured_mode():
    """HPG-Vorgabe 2 übernimmt das native Modusbit; kein behaupteter RB-Default."""
    value = os.environ.get('HPG_NATIVE_BEAT_MODE', '2')
    if value not in ('2', '3', '4'):
        raise ValueError('Unsupported native beat configuration; expected 2, 3 or 4')
    return int(value)


def full_model_disagrees(bpm, rows):
    """Stabile Gesamtfolge widerspricht dem Tempo des kurzen Modell8-Fensters."""
    import statistics
    intervals = [b[0] - a[0] for a, b in zip(rows, rows[1:])]
    if len(intervals) < 64:
        return False
    median = statistics.median(intervals)
    if not 60 / 215 <= median <= 60 / 55:
        return False
    stable = sum(abs(value - median) <= .02 + .02 * median for value in intervals)
    return stable >= .75 * len(intervals) and abs(median - 60 / bpm) > .04 * (60 / bpm)


def stable_full_window_start(rows, frames):
    """Vollständiges 60-s-Fenster mit geringster Modell-Intervallstreuung."""
    import statistics
    if len(rows) < 65:
        return None
    period = statistics.median(b[0] - a[0] for a, b in zip(rows, rows[1:]))
    if not 60 / 215 <= period <= 60 / 55:
        return None
    candidates = []
    for start in range(max(0, math.floor(frames / 44100 - 60))):
        times = [row[0] for row in rows if start <= row[0] <= start + 60]
        if (len(times) >= 64 and times[0] - start <= period
                and start + 60 - times[-1] <= period
                and all(abs(b - a - period) <= .02 + .02 * period
                        or is_chunk_seam_pair(a, b) for a, b in zip(times, times[1:]))):
            intervals = [b - a for a, b in zip(times, times[1:])
                         if not is_chunk_seam_pair(a, b)]
            candidates.append((statistics.pvariance(intervals), start))
    return min(candidates)[1] * 44100 if candidates else None


def select_model(mode, stored_mode=None):
    if type(mode) is not int or mode not in (2, 3, 4):
        raise ValueError('Native configuration uses a different analysis pipeline')
    if mode == 2:
        if type(stored_mode) is not bool:
            raise ValueError('Native stored mode is required for configuration 2')
        selected = stored_mode
    else:
        selected = mode == 4
    return dict(version=VERSION, configuration=mode,
                stored_mode=stored_mode if mode == 2 else None,
                model_id='model7' if selected else 'model8', chunked=selected)


def validate_selection(value):
    if type(value) is not dict or set(value) != {
            'version', 'configuration', 'stored_mode', 'model_id', 'chunked'}:
        raise ValueError('Invalid native model selection')
    expected = select_model(value['configuration'], value['stored_mode'])
    if value != expected or type(value['chunked']) is not bool:
        raise ValueError('Inconsistent native model selection')
