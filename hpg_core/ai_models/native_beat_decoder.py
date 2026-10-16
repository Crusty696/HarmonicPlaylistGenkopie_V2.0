"""Native Beatzeiten und Taktpositionen ohne nachträgliche HPG-Rotation."""
import math

import numpy as np

from .native_beat_worker import CONTRACT_VERSION, MAX_FRAMES, decode


ALGORITHM_VERSION = f'{CONTRACT_VERSION}-activation-neighborhood-v1'
_OBSERVATION_RADIUS_FRAMES = 1


def decode_beat_activations(activations, *, duration_s):
    if (type(duration_s) not in (float, int) or not math.isfinite(duration_s)
            or not 0 < duration_s <= 60):
        raise ValueError('Invalid native decoder duration')
    if (not isinstance(activations, np.ndarray) or activations.ndim != 2
            or activations.shape[1] != 2 or len(activations) > MAX_FRAMES + 1):
        raise ValueError('Invalid native decoder shape')
    retained = min(len(activations), int(math.ceil(duration_s * 100)))
    values = activations[:retained]
    result = dict(status='unavailable', reason='insufficient_evidence', verified=False,
        algorithm_version=ALGORITHM_VERSION, frame_rate=100., quantization_s=.01,
        tempo_quantization='native_peak_times', beats=[], bpm=None,
        covered_duration_s=None, ambiguous=True,
        first_downbeat=None)
    if not retained:
        result['reason'] = 'empty'
        return result
    native = decode(values)
    native_rows = [(row['pos'] / 44100., row['numBar']) for row in native['grid']]
    beats = []
    for stamp, position in native_rows:
        if stamp >= duration_s:
            continue
        # Der native Decoder kann den Peak innerhalb des 100-Hz-Rasters um
        # ein Feld quantisieren. Den Zeitstempel deshalb auf das naechste
        # Feld abbilden und die direkte Nachbarschaft als denselben Peak werten.
        center = int(math.floor(stamp * 100. + .5))
        first = max(0, center - _OBSERVATION_RADIUS_FRAMES)
        last = min(retained, center + _OBSERVATION_RADIUS_FRAMES + 1)
        observed = bool(float(np.max(values[first:last].sum(axis=1))) >= .05)
        beats.append({'time_s': float(stamp), 'position': int(position),
                      'observed': observed})
    # Native Ausgabe unverändert lassen. Weder Barrotation noch neue Beatzeiten
    # aus HPG-Heuristiken hinzufügen. Unvollständige Zyklen sind keine Freigabe.
    if (len(beats) < 4 or sum(b['observed'] for b in beats) < 4
            or not any(b['position'] == 1 for b in beats)
            or any(b['position'] != a['position'] % 4 + 1
                   for a, b in zip(beats, beats[1:]))):
        return result
    bpm = native['bpm']
    if (type(bpm) not in (float, int) or not math.isfinite(bpm)
            or not 55 <= bpm <= 215
            or min(duration_s, retained / 100.) < 4 * 60. / bpm):
        return result
    result.update(status='ok', reason='', beats=beats, bpm=bpm,
        covered_duration_s=min(duration_s, retained / 100.), ambiguous=False,
        first_downbeat=next(b['time_s'] for b in beats if b['position'] == 1))
    return result


def validate_decoder(value, window):
    """Native Herkunft ohne erfundene Likelihood-/Rotations-Konfidenzen."""
    fields = {'status', 'reason', 'verified', 'algorithm_version', 'frame_rate',
        'quantization_s', 'tempo_quantization', 'beats', 'bpm',
        'covered_duration_s', 'ambiguous', 'first_downbeat'}
    def finite(v):
        return type(v) in (int, float) and math.isfinite(v)
    if (type(value) is not dict or set(value) != fields
            or value['algorithm_version'] != ALGORITHM_VERSION
            or value['verified'] is not False or value['frame_rate'] != 100.
            or value['quantization_s'] != .01
            or value['tempo_quantization'] != 'native_peak_times'
            or type(value['beats']) is not list):
        raise ValueError('Invalid native decoder schema')
    if value['status'] == 'unavailable':
        if (value['reason'] not in ('empty', 'insufficient_evidence') or value['beats']
                or value['ambiguous'] is not True
                or any(value[k] is not None for k in ('bpm', 'covered_duration_s', 'first_downbeat'))):
            raise ValueError('Invalid unavailable native decoder')
        return
    if (value['status'] != 'ok' or value['reason'] != '' or value['ambiguous'] is not False
            or not finite(value['bpm']) or not 55 <= value['bpm'] <= 215
            or not finite(value['covered_duration_s'])
            or not 0 < value['covered_duration_s'] <= window['duration_s']
            or not 4 <= len(value['beats']) <= MAX_FRAMES):
        raise ValueError('Invalid native decoder values')
    previous = None
    for beat in value['beats']:
        if (type(beat) is not dict or set(beat) != {'time_s', 'position', 'observed'}
                or not finite(beat['time_s']) or type(beat['position']) is not int
                or not 1 <= beat['position'] <= 4 or type(beat['observed']) is not bool
                or not window['start_s'] <= beat['time_s'] < window['start_s'] + value['covered_duration_s']
                or previous is not None and (beat['time_s'] <= previous['time_s']
                    or beat['position'] != previous['position'] % 4 + 1)):
            raise ValueError('Invalid native beat')
        previous = beat
    downbeats = [b['time_s'] for b in value['beats'] if b['position'] == 1]
    if (not downbeats or not finite(value['first_downbeat'])
            or value['first_downbeat'] != downbeats[0]
            or value['covered_duration_s'] < 4 * 60. / value['bpm']
            or sum(b['observed'] for b in value['beats']) < 4):
        raise ValueError('Invalid native first downbeat')
