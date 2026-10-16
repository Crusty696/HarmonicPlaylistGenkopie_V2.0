"""Getrennte Audio-Zeitkorrektur; native Taktzahlen und Rohpositionen bleiben erhalten."""
import math

from ..downbeat import EXACT_BEAT_SYNC_TOLERANCE_SECONDS, BEATGRID_MIN_FOLD_LOCK


def stable_model_window(native, start, width):
    """Fenster vor der Audioprüfung auswählen, ohne deren Phasenfehler zu kennen.

    Unregelmäßige Modellbeats in Breaks eignen sich nicht zur Kickbestätigung.
    100-Hz-Modellraster: zwei Quantisierungsschritte plus 2% Tempotoleranz.
    """
    period = 60. / native['bpm']
    times = [r[0] for r in native.get('model_beats', []) if start <= r[0] < start + width]
    return (len(times) >= 8 and times[0] - start <= period
            and start + width - times[-1] <= period
            and all(abs(b-a-period) <= .02 + .02*period for a, b in zip(times, times[1:])))


def validate_alignment(native, alignment):
    if type(alignment) is not dict or set(alignment) != {'offset_seconds', 'calibration', 'confirmation'}:
        raise ValueError('Invalid native audio alignment')
    shift = alignment['offset_seconds']
    period = 60. / native['bpm']
    tolerance = EXACT_BEAT_SYNC_TOLERANCE_SECONDS
    if (type(shift) not in (int, float) or not math.isfinite(shift)
            or not tolerance < abs(shift) < period / 4
            or native['first_downbeat'] + shift < 0):
        raise ValueError('Invalid native phase correction')
    intervals = []
    calibrated_errors = []
    for group in ('calibration', 'confirmation'):
        rows = alignment[group]
        if type(rows) is not list or len(rows) != 3:
            raise ValueError('Three disjoint audio windows required')
        for row in rows:
            keys = {'offset_seconds', 'duration_seconds', 'phase_seconds', 'fold_lock',
                    'phase_error_ms', 'reason', 'signed_phase_error_ms'}
            if type(row) is not dict or set(row) != keys or row['reason'] != 'measured':
                raise ValueError('Invalid native audio evidence')
            if any(type(row[k]) not in (int, float) or not math.isfinite(row[k])
                   for k in keys - {'reason'}):
                raise ValueError('Nonfinite native audio evidence')
            start, width = row['offset_seconds'], row['duration_seconds']
            if group == 'confirmation' and not stable_model_window(native, start, width):
                raise ValueError('Native confirmation lacks stable model beats')
            if (start < 0 or width < 8 * period or start + width > native['frames']/44100 + 1e-6
                    or not BEATGRID_MIN_FOLD_LOCK <= row['fold_lock'] <= 1
                    or not 0 <= row['phase_seconds'] < period):
                raise ValueError('Invalid native audio window')
            if any(start < end and start + width > begin for begin, end in intervals):
                raise ValueError('Native confirmation windows overlap')
            intervals.append((start, start + width))
            correction = shift if group == 'confirmation' else 0.
            tick = min((r['pos']/44100 + correction for r in native['grid']),
                       key=lambda t: abs(t - start))
            signed = (row['phase_seconds'] - (tick-start) + period/2) % period - period/2
            if (abs(signed*1000-row['signed_phase_error_ms']) > .002
                    or abs(abs(signed)*1000-row['phase_error_ms']) > .002):
                raise ValueError('Native phase evidence inconsistent')
            residual = signed - shift if group == 'calibration' else signed
            if abs(residual) > tolerance + 1e-6:
                raise ValueError('Native corrected phase exceeds sync tolerance')
            if group == 'calibration':
                calibrated_errors.append(signed)
    # Der gespeicherte Versatz muss aus den Messungen stammen, nicht aus einem
    # nachträglich gewählten Taktanker. Median bei drei konsistenten Fenstern.
    if abs(sorted(calibrated_errors)[1] - shift) > 1e-6:
        raise ValueError('Native correction differs from measured median')


def active_anchor(native):
    alignment = native.get('audio_alignment')
    if alignment is None:
        return native['first_downbeat']
    validate_alignment(native, alignment)
    return native['first_downbeat'] + alignment['offset_seconds']
