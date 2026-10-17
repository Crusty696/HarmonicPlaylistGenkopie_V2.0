"""Quellgebundener vollständiger nativer Beat-/Taktlauf, seriell im Broker."""
import json
import math
import os
from pathlib import Path
import time


from .native_phrase_worker import SHA256, _source_identity
from .native_beat_pipeline_worker import TF_SHA256
from .beat_predictor import MODEL_HASHES
from .process_runtime import OwnedModelProcess
from .native_beat_selection import (
    MAX_NATIVE_BEAT_SECONDS, MAX_NATIVE_BEAT_WINDOW_SECONDS,
    configured_mode, maximum_native_beat_rows, native_beat_segment_count,
    validate_selection,
)
from .native_audio_reader import CONTRACT as READER_CONTRACT
from .reader_contract import NATIVE_BEAT_INPUT_CONVENTIONS
from .native_beat_boundaries import VERSION as BOUNDARY_CONTRACT

CONTRACT = 'hpg-native-track-beats-v13'


def enabled():
    return os.environ.get('HPG_NATIVE_BEAT', '1') != '0'


def has_verified_grid(track):
    """Prüft native Beatgrid-Gültigkeit unabhängig vom Bar-1-Status."""
    from .native_beat_alignment import active_anchor
    value = getattr(track, 'native_beat_analysis', {})
    if (not isinstance(value, dict) or value.get('status') != 'ok'
            or getattr(track, 'beatgrid_status', None) != 'verified'):
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
              'bpm', 'grid', 'first_downbeat', 'musically_verified', 'input_convention', 'selection', 'reader', 'boundary_contract', 'model_coverage'}
    if (set(value) - {'audio_alignment', 'model_beats', 'verification', 'phase_method',
                      'model_coverage_segments'} != fields or value['reason'] is not None or value['contract'] != CONTRACT
            or value['executable_sha256'] != SHA256 or value['tensorflow_sha256'] != TF_SHA256
            or value['boundary_contract'] != BOUNDARY_CONTRACT
            or value['model_id'] not in MODEL_HASHES or value['model_hashes'] != MODEL_HASHES[value['model_id']]
            or value['sample_rate'] != 44100 or type(value['frames']) is not int
            or not 44100 <= value['frames'] <= MAX_NATIVE_BEAT_SECONDS * 44100
            or abs(value['frames'] / 44100 - duration) >
                (2 / 44100 if value['input_convention'] == 'rekordbox-builtin-planar-float32' else 0.1)
            or value['musically_verified'] is not False
            or type(value['input_convention']) is not str
            or value['input_convention'] not in NATIVE_BEAT_INPUT_CONVENTIONS.values()
            or type(value['source_identity']) is not list or len(value['source_identity']) != 5
            or any(type(v) is not int or v < 0 for v in value['source_identity'])
            or type(value['bpm']) not in (int, float) or not math.isfinite(value['bpm'])
            or not 55 <= value['bpm'] <= 215 or type(value['grid']) is not list
            or not 4 <= len(value['grid']) <= maximum_native_beat_rows(value['frames'])):
        raise ValueError('Invalid native beat identity/coverage')
    if 'phase_method' in value and value['phase_method'] != 'native_attack_v1':
        raise ValueError('Invalid native phase method')
    validate_selection(value['selection'])
    if value['selection']['model_id'] != value['model_id']:
        raise ValueError('Native selected model mismatch')
    validate_reader(value['reader'], value['frames'], duration, value['input_convention'])
    coverage = value['model_coverage']
    if (type(coverage) is not dict or set(coverage) != {'start_s', 'end_s'}
            or any(type(x) not in (int, float) or not math.isfinite(x) for x in coverage.values())
            or any(x != round(x * 44100) / 44100 for x in coverage.values())
            or not 0 <= coverage['start_s'] < coverage['end_s'] <= duration
            or (not value['selection']['chunked'] and coverage['end_s']-coverage['start_s'] > 60+1e-6)):
        raise ValueError('Invalid native model coverage')
    segments_required = (
        not value['selection']['chunked']
        and value['frames'] > MAX_NATIVE_BEAT_WINDOW_SECONDS * 44100
    )
    if segments_required and 'model_coverage_segments' not in value:
        raise ValueError('Segmented native model coverage is required')
    if not segments_required and 'model_coverage_segments' in value:
        raise ValueError('Unexpected segmented native model coverage')
    if 'model_coverage_segments' in value:
        segments = value['model_coverage_segments']
        if (value['selection']['chunked'] or type(segments) is not list or len(segments) < 2
                or len(segments) != native_beat_segment_count(value['frames'])
                or segments[0] != coverage):
            raise ValueError('Invalid segmented model coverage')
        previous_start = -1.
        previous_end = None
        for segment in segments:
            if (type(segment) is not dict or set(segment) != {'start_s', 'end_s'}
                    or any(type(x) not in (int, float) or not math.isfinite(x)
                           for x in segment.values())
                    or any(x != round(x * 44100) / 44100 for x in segment.values())
                    or not 0 <= segment['start_s'] < segment['end_s'] <= duration
                    or segment['end_s'] - segment['start_s'] > 60 + 1e-6
                    or segment['start_s'] <= previous_start
                    or previous_end is not None and segment['start_s'] >= previous_end):
                raise ValueError('Invalid segmented model coverage range')
            previous_start = segment['start_s']
            previous_end = segment['end_s']
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
        if (type(value['model_beats']) is not list or not 4 <= len(value['model_beats'])
                <= maximum_native_beat_rows(value['frames'])):
            raise ValueError('Invalid native model beats')
        for row in value['model_beats']:
            if (type(row) is not list or len(row) != 2
                    or any(type(x) not in (int, float) or not math.isfinite(x) for x in row)
                    or not previous < row[0] < duration or row[0] < 0 or row[1] not in (1, 2, 3, 4)):
                raise ValueError('Invalid native model beat sequence')
            previous = row[0]
    if value.get('verification') is not None:
        verification = value['verification']
        if (type(verification) is not dict or set(verification) != {'model_id', 'model_hashes', 'beats', 'coverage'}
                or verification['model_id'] != 'model7'
                or verification['model_hashes'] != MODEL_HASHES['model7']
                or verification['coverage'] != dict(start_s=0., end_s=(value['frames']-1)/44100)
                or type(verification['beats']) is not list or not 4 <= len(verification['beats'])
                <= maximum_native_beat_rows(value['frames'])):
            raise ValueError('Invalid native verification provenance')
        previous = -1.
        for row in verification['beats']:
            if (type(row) is not list or len(row) != 2
                    or any(type(x) not in (int, float) or not math.isfinite(x) for x in row)
                    or not previous < row[0] < duration or row[0] < 0 or row[1] not in (1, 2, 3, 4)):
                raise ValueError('Invalid native verification sequence')
            previous = row[0]
    if 'audio_alignment' in value:
        from .native_beat_alignment import validate_alignment
        validate_alignment(value, value['audio_alignment'])


def validate_reader(reader, frames, duration, input_convention):
    fields = {'contract', 'source_sample_rate', 'source_channels', 'output_channels', 'source_bit_depth',
              'source_frames', 'output_sample_rate', 'output_frames', 'backend'}
    if (type(reader) is not dict or set(reader) != fields
            or reader['contract'] != READER_CONTRACT
            or type(reader['backend']) is not str
            or reader['backend'] not in NATIVE_BEAT_INPUT_CONVENTIONS
            or input_convention != NATIVE_BEAT_INPUT_CONVENTIONS[reader['backend']]
            or any(type(reader[k]) is not int for k in fields - {'contract', 'backend'})
            or not 1 <= reader['source_channels'] <= 32
            or reader['output_channels'] not in (1, 2)
            or reader['output_channels'] != (1 if reader['source_channels'] > 2
                                               else reader['source_channels'])
            or not 8000 <= reader['source_sample_rate'] <= 384000
            or reader['source_bit_depth'] not in (0, 8, 16, 24, 32, 64)
            or (reader['backend'].startswith('rekordbox-builtin')
                and reader['source_bit_depth'] == 0)
            or reader['source_frames'] < 1
            or reader['output_sample_rate'] != 44100 or reader['output_frames'] != frames
            or abs(reader['source_frames']/reader['source_sample_rate']-duration) >
                (2/44100 if reader['backend'].startswith('rekordbox-builtin') else 0.1)):
        raise ValueError('Invalid native reader provenance')


def analyze(path, *, transport=None, timeout_s=180., cancel_event=None):
    if not enabled():
        return dict(status='disabled', reason='disabled')
    try:
        source = Path(path).resolve(strict=True)
        identity = _source_identity(source)
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
        mode = configured_mode()
        request = dict(path=str(source), source_identity=identity, configuration=mode)
        raw = call('native_beat', 'hpg_core.ai_models.native_beat_pipeline_worker', request)
        if (raw.get('contract') != 'rb-7.2.19-native-beat-pipeline-research-v13'
                or raw.get('executable_sha256') != SHA256 or raw.get('tensorflow_sha256') != TF_SHA256
                or raw.get('model_id') not in MODEL_HASHES
                or raw.get('model_hashes') != MODEL_HASHES[raw['model_id']]
                or raw.get('boundary_contract') != BOUNDARY_CONTRACT
                or raw.get('verified') is not False
                or _source_identity(source) != identity):
            raise ValueError('Native pipeline provenance mismatch')
        validate_selection(raw['selection'])
        if raw['selection']['configuration'] != mode or raw['selection']['model_id'] != raw['model_id']:
            raise ValueError('Native mode response mismatch')
        frames = raw['frames']
        result = dict(status='ok', reason=None, contract=CONTRACT, executable_sha256=SHA256,
            tensorflow_sha256=TF_SHA256, model_id=raw['model_id'], model_hashes=raw['model_hashes'],
            source_identity=identity, sample_rate=44100, frames=frames,
            bpm=raw['bpm'], grid=raw['grid'],
            first_downbeat=next(r['pos']/44100 for r in raw['grid'] if r['numBar'] == 1),
            musically_verified=False, input_convention=raw['input_convention'], model_beats=raw['beats'],
            selection=raw['selection'], reader=raw['reader'], boundary_contract=raw['boundary_contract'],
            model_coverage=raw['model_coverage'])
        if 'model_coverage_segments' in raw:
            result['model_coverage_segments'] = raw['model_coverage_segments']
        validate_snapshot(result, duration=frames/44100)
        if raw.get('verification') is not None:
            result['verification'] = raw['verification']
            validate_snapshot(result, duration=frames/44100)
        return result
    except Exception as error:
        return dict(status='unavailable', reason=f'{type(error).__name__}: {error}')
