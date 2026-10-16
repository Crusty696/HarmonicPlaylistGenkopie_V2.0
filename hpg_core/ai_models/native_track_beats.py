"""Quellgebundener vollständiger nativer Beat-/Taktlauf, seriell im Broker."""
import json
import math
import os
from pathlib import Path
import time

import soundfile as sf

from .native_phrase_worker import SHA256, _source_identity
from .native_beat_pipeline_worker import TF_SHA256
from .beat_predictor import MODEL_HASHES
from .process_runtime import OwnedModelProcess

CONTRACT = 'hpg-native-track-beats-v1'


def enabled():
    return os.environ.get('HPG_NATIVE_BEAT', '1') != '0'


def has_verified_grid(track):
    """Gemeinsame native Freigabe für Renderer und Export; keine Neuanalyse."""
    from .native_beat_alignment import active_anchor
    value = getattr(track, 'native_beat_analysis', {})
    if (not isinstance(value, dict) or value.get('status') != 'ok'
            or getattr(track, 'beatgrid_status', None) != 'verified'
            or getattr(track, 'downbeat_confidence', None) != 1.0):
        return False
    try:
        validate_snapshot(value, duration=track.duration)
        return track.bpm == value['bpm'] and track.first_downbeat == active_anchor(value)
    except (TypeError, ValueError, KeyError, AttributeError):
        return False


def validate_snapshot(value, *, duration):
    if type(value) is not dict or value.get('status') not in ('ok', 'unavailable', 'disabled'):
        raise ValueError('Invalid native beat snapshot')
    if value['status'] != 'ok':
        if set(value) != {'status', 'reason'} or type(value['reason']) is not str:
            raise ValueError('Invalid unavailable native beats')
        return
    fields = {'status', 'reason', 'contract', 'executable_sha256', 'tensorflow_sha256',
              'model_id', 'model_hashes', 'source_identity', 'sample_rate', 'frames',
              'bpm', 'grid', 'first_downbeat', 'musically_verified', 'input_convention'}
    if (set(value) - {'audio_alignment', 'model_beats'} != fields or value['reason'] is not None or value['contract'] != CONTRACT
            or value['executable_sha256'] != SHA256 or value['tensorflow_sha256'] != TF_SHA256
            or value['model_id'] != 'model7' or value['model_hashes'] != MODEL_HASHES['model7']
            or value['sample_rate'] != 44100 or type(value['frames']) is not int
            or not 44100 <= value['frames'] <= 1200 * 44100
            or abs(value['frames'] / 44100 - duration) > 1 / 44100
            or value['musically_verified'] is not False
            or value['input_convention'] != 'soundfile-normalized-stereo-float32'
            or type(value['source_identity']) is not list or len(value['source_identity']) != 4
            or any(type(v) is not int or v < 0 for v in value['source_identity'])
            or type(value['bpm']) not in (int, float) or not math.isfinite(value['bpm'])
            or not 55 <= value['bpm'] <= 215 or type(value['grid']) is not list
            or not 4 <= len(value['grid']) <= 6000):
        raise ValueError('Invalid native beat identity/coverage')
    previous = None
    for row in value['grid']:
        if (type(row) is not dict or set(row) != {'pos', 'numBar', 'bpm'}
                or any(type(v) is not int for v in row.values())
                or not 0 <= row['pos'] < value['frames'] or not 1 <= row['numBar'] <= 4
                or not 0 < row['bpm'] <= 100000
                or previous is not None and (row['pos'] <= previous['pos']
                    or row['numBar'] != previous['numBar'] % 4 + 1)):
            raise ValueError('Invalid refined native beat sequence')
        previous = row
    downbeats = [r['pos'] / 44100 for r in value['grid'] if r['numBar'] == 1]
    if not downbeats or type(value['first_downbeat']) not in (int, float) or value['first_downbeat'] != downbeats[0]:
        raise ValueError('Invalid native downbeat')
    if 'model_beats' in value:
        previous = -1.
        if type(value['model_beats']) is not list or not 4 <= len(value['model_beats']) <= 6000:
            raise ValueError('Invalid native model beats')
        for row in value['model_beats']:
            if (type(row) is not list or len(row) != 2
                    or any(type(x) not in (int, float) or not math.isfinite(x) for x in row)
                    or not previous < row[0] < duration or row[0] < 0 or row[1] not in (1, 2, 3, 4)):
                raise ValueError('Invalid native model beat sequence')
            previous = row[0]
    if 'audio_alignment' in value:
        from .native_beat_alignment import validate_alignment
        validate_alignment(value, value['audio_alignment'])


def analyze(path, *, transport=None, timeout_s=180., cancel_event=None):
    if not enabled():
        return dict(status='disabled', reason='disabled')
    try:
        source = Path(path).resolve(strict=True)
        identity = _source_identity(source)
        info = sf.info(str(source))
        if info.samplerate != 44100 or info.channels != 2 or info.subtype != 'PCM_16' or not 1 <= info.duration <= 1200:
            return dict(status='unavailable', reason='unsupported_source_format')
        if type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not 0 < timeout_s <= 180:
            raise ValueError('Invalid native beat timeout')
        deadline = time.monotonic() + timeout_s
        def call(job, module, request):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Native beat deadline expired')
            if transport is not None:
                result = transport(job, request, timeout_s=remaining)
            else:
                from ..config import MODEL_PROCESS_MEMORY_LIMIT_BYTES
                with OwnedModelProcess(module, 'handle', max_payload_bytes=8*1024*1024,
                        memory_limit_bytes=MODEL_PROCESS_MEMORY_LIMIT_BYTES) as owner:
                    result = json.loads(owner.call(json.dumps(request, allow_nan=False).encode(),
                                        deadline=deadline, cancel_event=cancel_event))
            if type(result) is not dict:
                raise ValueError('Invalid native beat response')
            if result.get('status') == 'unavailable':
                raise ValueError(result.get('reason', 'Native worker unavailable'))
            return result
        request = dict(path=str(source), source_identity=identity, frames=info.frames, model_id='model7')
        raw = call('native_beat', 'hpg_core.ai_models.native_beat_pipeline_worker', request)
        if (raw.get('contract') != 'rb-7.2.19-native-beat-pipeline-research-v1'
                or raw.get('executable_sha256') != SHA256 or raw.get('tensorflow_sha256') != TF_SHA256
                or raw.get('model_id') != 'model7' or raw.get('model_hashes') != MODEL_HASHES['model7']
                or raw.get('frames') != info.frames or raw.get('verified') is not False):
            raise ValueError('Native pipeline provenance mismatch')
        request = dict(path=str(source), source_identity=identity, frames=info.frames,
                       grid=raw['grid'], bpm_hundredths=round(raw['bpm'] * 100))
        refined = call('native_beat_refine', 'hpg_core.ai_models.native_grid_refinement_worker', request)
        if (refined.get('contract') != 'rb-7.2.19-final-grid-research-v1'
                or refined.get('executable_sha256') != SHA256 or refined.get('frames') != info.frames
                or refined.get('sample_rate') != 44100 or refined.get('verified') is not False
                or _source_identity(source) != identity):
            raise ValueError('Native refinement provenance mismatch')
        result = dict(status='ok', reason=None, contract=CONTRACT, executable_sha256=SHA256,
            tensorflow_sha256=TF_SHA256, model_id='model7', model_hashes=MODEL_HASHES['model7'],
            source_identity=identity, sample_rate=44100, frames=info.frames,
            bpm=refined['bpm_hundredths']/100., grid=refined['grid'],
            first_downbeat=next(r['pos']/44100 for r in refined['grid'] if r['numBar'] == 1),
            musically_verified=False, input_convention=raw['input_convention'], model_beats=raw['beats'])
        validate_snapshot(result, duration=info.duration)
        return result
    except Exception as error:
        return dict(status='unavailable', reason=f'{type(error).__name__}: {error}')
