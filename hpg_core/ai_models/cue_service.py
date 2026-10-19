"""Begrenzter lokaler Cue-Dienst; ausschließlich JSON und Mono-PCM auf dem Wire.

Ein serieller Broker nimmt Audio erst nach READY an. Das begrenzt aktive
Übertragungen, nicht den gesamten RAM-Verbrauch der Analyseworker.
"""
from contextlib import contextmanager
from functools import wraps
import hashlib
from importlib import metadata
import hmac
import json
import logging
import math
import os
from pathlib import Path
import secrets
import socket
import struct
import threading
import time
import uuid

import numpy as np

from .cue_predictor import PREPROCESS_VERSION, MODEL_HASHES, CUE_SCORE_SOURCE
from .process_runtime import OwnedModelProcess, ModelProcessCleanupError
from .beat_predictor import MODEL_HASHES as BEAT_HASHES, PREPROCESS_VERSION as BEAT_PREPROCESS
from .native_beat_decoder import ALGORITHM_VERSION as BEAT_DECODER_VERSION
from .rekordbox_runtime import REKORDBOX_ROOT

logger = logging.getLogger(__name__)
MAX_WIRE = 64 * 1024 * 1024
MAX_HEADER = 1024 * 1024
MAX_CANDIDATES = 4096
MAX_PATH_JOB_SECONDS = 420.
MAX_DEEP_FEATURE_SECONDS = 240.
_local = threading.local()
_pool_client = None
_terminal_failure = threading.Event()


def model_config():
    root = Path(os.environ.get('HPG_CUE_MODEL_DIR', str(REKORDBOX_ROOT/'models'/'detect_cue_model')))
    beat_root = Path(os.environ.get('HPG_BEAT_MODEL_DIR', str(REKORDBOX_ROOT/'models'/'detect_beat')))
    return dict(samplecnn_path=str(root / 'samplecnn.onnx'),
                cue_model_path=str(root / 'cue_prediction_model_no_abs_position.onnx'),
                beat_model7_path=str(beat_root / 'model7'), beat_model8_path=str(beat_root / 'model8'),
                prefer_directml=True)


def _runtime_versions():
    versions = {}
    for name in ('numpy', 'librosa', 'soxr', 'soundfile', 'audioread',
                 'imageio-ffmpeg', 'pefile', 'onnxruntime-directml',
                 'tensorflow-cpu', 'tensorflow-intel'):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def fingerprint(config=None):
    from ..config import MODEL_PROCESS_MEMORY_LIMIT_BYTES
    from .native_phrase_adapter import identity as native_phrase_identity
    from .deep_features import config_fingerprint as deep_feature_fingerprint
    from .native_track_beats import CONTRACT as native_beat_contract, TF_SHA256, enabled as native_beat_enabled
    from .native_beat_selection import configured_mode, VERSION as selection_version
    from .native_audio_reader import CONTRACT as reader_contract
    config = dict(model_config(), **(config or (_pool_client.config if _pool_client else {})))
    identities = {}
    paths = {key: config[key] for key in ('samplecnn_path', 'cue_model_path')}
    for model_id, hashes in BEAT_HASHES.items():
        for name in hashes:
            paths[f'{model_id}/{name}'] = str(Path(config[f'beat_{model_id}_path']) / name)
    for key, path in paths.items():
        try:
            with open(path, 'rb') as stream:
                identities[key] = hashlib.file_digest(stream, 'sha256').hexdigest()
        except (OSError, ValueError):
            identities[key] = None
    return hashlib.sha256(_json(dict(config=config, hashes=identities,
                                     preprocess=PREPROCESS_VERSION, beat_preprocess=BEAT_PREPROCESS,
                                     beat_decoder=BEAT_DECODER_VERSION,
                                     native_phrase=native_phrase_identity(),
                                     native_beat=dict(contract=native_beat_contract, tensorflow_sha256=TF_SHA256,
                                                      enabled=native_beat_enabled(), configuration=configured_mode(),
                                                      selection=selection_version, reader=reader_contract),
                                     deep_features=deep_feature_fingerprint(),
                                     runtimes=_runtime_versions(), wire=3,
                                     memory_limit_bytes=MODEL_PROCESS_MEMORY_LIMIT_BYTES))).hexdigest()


def _json(value):
    return json.dumps(value, allow_nan=False, separators=(',', ':'), sort_keys=True).encode('utf8')


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def _load(value):
    return json.loads(value, object_pairs_hook=_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def _finite(value):
    if type(value) not in (float, int):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def _pack(header, data):
    encoded = _json(header)
    if len(encoded) > MAX_HEADER or len(encoded) + len(data) + 4 > MAX_WIRE:
        raise ValueError('Cue payload too large')
    return struct.pack('!I', len(encoded)) + encoded + data


def encode_audio(audio, sample_rate, candidates, *, window_start_s, track_duration_s, verified_grid):
    if (not isinstance(audio, np.ndarray) or audio.ndim != 1
            or audio.dtype not in (np.dtype('float32'), np.dtype('float64'))
            or not np.isfinite(audio).all()):
        raise ValueError('Finite mono float32/64 required')
    if type(candidates) is not list or len(candidates) > MAX_CANDIDATES:
        raise ValueError('Invalid candidate count')
    header = dict(version=1, dtype=audio.dtype.str, samples=len(audio), sample_rate=sample_rate,
                  candidates=candidates, window_start_s=window_start_s,
                  track_duration_s=track_duration_s, verified_grid=verified_grid)
    header_size = len(_json(header))
    if header_size > MAX_HEADER or 4 + header_size + audio.nbytes > MAX_WIRE:
        raise ValueError('Cue payload too large before audio copy')
    data = _pack(header, audio.tobytes(order='C'))
    decode_audio(data)
    return data


def decode_audio(payload):
    if not isinstance(payload, bytes) or not 4 <= len(payload) <= MAX_WIRE:
        raise ValueError('Invalid cue frame')
    size = struct.unpack('!I', payload[:4])[0]
    if not 0 < size <= MAX_HEADER or size + 4 > len(payload):
        raise ValueError('Invalid cue header size')
    header = _load(payload[4:4+size])
    keys = {'version', 'dtype', 'samples', 'sample_rate', 'candidates', 'window_start_s', 'track_duration_s', 'verified_grid'}
    if type(header) is not dict or set(header) not in (keys, keys | {'config'}):
        raise ValueError('Invalid cue header fields')
    if (type(header['version']) is not int or header['version'] != 1
            or header['dtype'] not in ('<f4', '<f8')
            or type(header['samples']) is not int or header['samples'] <= 0
            or not _finite(header['sample_rate']) or header['sample_rate'] < 1
            or header['sample_rate'] % 1 != 0
            or not _finite(header['window_start_s']) or header['window_start_s'] < 0
            or not _finite(header['track_duration_s']) or header['track_duration_s'] <= header['window_start_s']
            or type(header['verified_grid']) is not bool):
        raise ValueError('Invalid cue header values')
    candidates = header['candidates']
    if type(candidates) is not list or len(candidates) > MAX_CANDIDATES:
        raise ValueError('Invalid candidate list')
    for item in candidates:
        if (type(item) is not dict or set(item) != {'start_s', 'kind', 'mood'}
                or not _finite(item['start_s']) or not 0 <= item['start_s'] < header['track_duration_s']
                or type(item['kind']) is not int or not 1 <= item['kind'] <= 10
                or type(item['mood']) is not int or not 1 <= item['mood'] <= 3):
            raise ValueError('Invalid phrase candidate')
    raw = memoryview(payload)[4+size:]
    dtype = np.dtype(header['dtype'])
    if header['samples'] * dtype.itemsize != len(raw):
        raise ValueError('Cue audio length mismatch')
    audio = np.frombuffer(raw, dtype=dtype)
    if not np.isfinite(audio).all():
        raise ValueError('Nonfinite cue audio')
    return header, audio


def handle_cue(payload):
    """Fester Lane-Handler; Modellpfade werden ausschließlich vom Owner ergänzt."""
    from .cue_predictor import score_phrase_candidates
    header, audio = decode_audio(payload)
    config = header.pop('config')
    if (type(config) is not dict or set(config) != {'samplecnn_path', 'cue_model_path', 'prefer_directml'}
            or any(type(config[k]) is not str for k in ('samplecnn_path', 'cue_model_path'))
            or type(config['prefer_directml']) is not bool):
        raise ValueError('Invalid owner configuration')
    return _json(score_phrase_candidates(audio, header['sample_rate'], header['candidates'],
                 window_start_s=header['window_start_s'], track_duration_s=header['track_duration_s'],
                 verified_grid=header['verified_grid'], **config))


def encode_beat_audio(audio, sample_rate, *, window_start_s, track_duration_s):
    if (not isinstance(audio, np.ndarray) or audio.ndim != 1
            or audio.dtype not in (np.dtype('float32'), np.dtype('float64'))):
        raise ValueError('Beat mono float required')
    header = dict(version=2, job='beat', dtype=audio.dtype.str, samples=len(audio),
                  sample_rate=sample_rate, window_start_s=window_start_s, track_duration_s=track_duration_s)
    if 4 + len(_json(header)) + audio.nbytes > MAX_WIRE:
        raise ValueError('Beat payload too large before copy')
    payload = _pack(header, audio.tobytes())
    decode_beat_audio(payload)
    return payload


def _header(payload):
    if type(payload) is not bytes or not 4 <= len(payload) <= MAX_WIRE:
        raise ValueError('Invalid model frame')
    size = struct.unpack('!I', payload[:4])[0]
    if not 0 < size <= MAX_HEADER or size + 4 > len(payload):
        raise ValueError('Invalid model header')
    header = _load(payload[4:4+size])
    if type(header) is not dict:
        raise ValueError('Invalid model header type')
    return header, size


def decode_beat_audio(payload):
    header, size = _header(payload)
    keys = {'version', 'job', 'dtype', 'samples', 'sample_rate', 'window_start_s', 'track_duration_s'}
    if set(header) not in (keys, keys | {'config'}):
        raise ValueError('Invalid beat header fields')
    if (type(header['version']) is not int or header['version'] != 2 or header['job'] != 'beat'
            or header['dtype'] not in ('<f4', '<f8')
            or type(header['samples']) is not int or not 44100 <= header['samples'] <= 44100 * 60
            or type(header['sample_rate']) is not int or header['sample_rate'] != 44100
            or not _finite(header['window_start_s']) or header['window_start_s'] < 0
            or not _finite(header['track_duration_s'])
            or header['window_start_s'] + header['samples'] / 44100 > header['track_duration_s'] + 1/44100):
        raise ValueError('Invalid beat header values')
    raw = memoryview(payload)[4+size:]
    dtype = np.dtype(header['dtype'])
    if len(raw) != header['samples'] * dtype.itemsize:
        raise ValueError('Beat audio length mismatch')
    audio = np.frombuffer(raw, dtype=dtype)
    if not np.isfinite(audio).all():
        raise ValueError('Nonfinite beat audio')
    return header, audio


def _decode_job(payload):
    header, _ = _header(payload)
    if header.get('job') == 'beat':
        return decode_beat_audio(payload)
    if 'job' not in header and header.get('version') == 1:
        return decode_audio(payload)
    raise ValueError('Unsupported model job')


def _beat_result(model_id, status, reason):
    return dict(model_id=model_id, status=status, reason=reason, model_hashes={},
                preprocess_version=BEAT_PREPROCESS, decoder_version=BEAT_DECODER_VERSION,
                provider='CPU', frame_rate=100., contract_basis='static_source_derived', decoder=None)


def _beat_failure_window(start, duration, status, reason):
    return dict(start_s=start, duration_s=duration, status='evaluated', reason=None,
                results=[_beat_result(model_id, status, reason) for model_id in ('model7', 'model8')])


def handle_models(payload):
    """Geschlossener Cue/Beat-Dispatcher im selben begrenzten Modellprozess."""
    header, audio = _decode_job(payload)
    if header.get('job') != 'beat':
        return handle_cue(payload)
    from .beat_predictor import infer_beat_activations, UnsupportedBeatModel, BeatModelUnavailable
    from .native_beat_decoder import decode_beat_activations
    config = header.get('config')
    if (type(config) is not dict
            or set(config) != {'samplecnn_path', 'cue_model_path', 'prefer_directml', 'beat_model7_path', 'beat_model8_path'}
            or any(type(config[key]) is not str for key in config if key != 'prefer_directml')
            or type(config['prefer_directml']) is not bool):
        raise ValueError('Invalid beat owner configuration')
    duration = len(audio) / header['sample_rate']
    window = _beat_failure_window(header['window_start_s'], duration, 'model_error', 'not_evaluated')
    for index, model_id in enumerate(('model7', 'model8')):
        try:
            inference = infer_beat_activations(audio, header['sample_rate'],
                model_directory=config[f'beat_{model_id}_path'], model_id=model_id)
            decoded = decode_beat_activations(inference['activations'], duration_s=duration)
            for beat in decoded['beats']:
                beat['time_s'] += header['window_start_s']
            if decoded['first_downbeat'] is not None:
                decoded['first_downbeat'] += header['window_start_s']
            result = _beat_result(model_id, decoded['status'], decoded['reason'] or None)
            result.update(model_hashes=inference['metadata']['model_hashes'], decoder=decoded)
        except UnsupportedBeatModel as error:
            result = _beat_result(model_id, 'unsupported_model', type(error).__name__)
        except BeatModelUnavailable as error:
            cause = error
            while cause.__cause__ is not None:
                cause = cause.__cause__
            status = 'missing_model' if isinstance(cause, FileNotFoundError) else 'model_error'
            result = _beat_result(model_id, status, type(error).__name__)
        except Exception as error:
            result = _beat_result(model_id, 'model_error', type(error).__name__)
        window['results'][index] = result
    _validate_beat_window(window)
    return _json(window)


class _CombinedEvent(threading.Event):
    def __init__(self, *events):
        super().__init__()
        self._events = events

    def is_set(self):
        return super().is_set() or any(event.is_set() for event in self._events)


def _check(deadline, cancel):
    if cancel is not None and cancel.is_set():
        raise InterruptedError('Cue request cancelled')
    if time.monotonic() >= deadline:
        raise TimeoutError('Cue deadline exceeded')


def _read(sock, size, deadline, cancel):
    result = bytearray()
    while len(result) < size:
        _check(deadline, cancel)
        try:
            chunk = sock.recv(min(65536, size-len(result)))
        except socket.timeout:
            continue
        if not chunk:
            raise EOFError('Cue peer disconnected')
        result.extend(chunk)
    return bytes(result)


def _write(sock, data, deadline, cancel):
    view = memoryview(data)
    while view:
        _check(deadline, cancel)
        try:
            sent = sock.send(view[:65536])
        except socket.timeout:
            continue
        if not sent:
            raise EOFError('Cue peer disconnected')
        view = view[sent:]


def _receive(sock, maximum, deadline, cancel):
    size = struct.unpack('!I', _read(sock, 4, deadline, cancel))[0]
    if not 0 < size <= maximum:
        raise ValueError('Cue frame length invalid')
    return _read(sock, size, deadline, cancel)


def _send(sock, data, deadline, cancel):
    _write(sock, struct.pack('!I', len(data)) + data, deadline, cancel)


def _diagnostics(candidates, reason):
    return [dict(index=i, status='unavailable', reason=reason, raw_score=None,
                 source=CUE_SCORE_SOURCE, model_hashes={},
                 preprocess_version=PREPROCESS_VERSION, coverage={}) for i in range(len(candidates))]


class CueClient:
    def __init__(self, address, token, generation, config, error=None):
        self.address, self.token, self.generation = address, token, generation
        self.config, self.error = config, error

    def native_phrases(self, parameters, *, timeout_s=MAX_PATH_JOB_SECONDS):
        return self._path_job('native_phrase', parameters, timeout_s=timeout_s)

    def native_beats(self, job, parameters, *, timeout_s=MAX_PATH_JOB_SECONDS):
        if job != 'native_beat':
            raise ValueError('Invalid native beat job')
        return self._path_job(job, parameters, timeout_s=timeout_s)

    def deep_features(self, parameters, *, timeout_s=240.):
        started = time.monotonic()
        result = self._path_job('deep_features', parameters, timeout_s=timeout_s)
        remaining = min(float(timeout_s), MAX_DEEP_FEATURE_SECONDS) - (time.monotonic()-started)
        # Ein neuer Prozess ist nötig: ein fehlgeschlagener nativer Aufruf
        # darf nicht mit beschädigtem DLL-Zustand auf CPU wiederholt werden.
        if (parameters.get('kind') in ('stems', 'embedding') and result.get('status') == 'unavailable'
                and parameters.get('config', {}).get('prefer_directml') is True
                and remaining > 1. and str(result.get('reason', '')).startswith(('RuntimeError', 'service_error:'))):
            result = self._path_job('deep_features', dict(parameters, cpu_fallback=True), timeout_s=remaining)
        return result

    def _path_job(self, job, parameters, *, timeout_s):
        """Pfadauftrag am seriellen Broker, eigener Einmalprozess ohne PCM-Wire."""
        if self.error:
            return dict(status='unavailable', reason=self.error)
        track_deadline = getattr(_local, 'deadline', None) or float('inf')
        # Zusatzmerkmale müssen vor dem Pool-Timeout zurückkehren, damit
        # der fertige DSP-Track samt Fehlerstatus noch ausgeliefert wird.
        if job == 'deep_features':
            track_deadline -= 5.
        timeout_limit = (MAX_DEEP_FEATURE_SECONDS if job == 'deep_features'
                         else MAX_PATH_JOB_SECONDS)
        execution_timeout = min(float(timeout_s), timeout_limit)
        # Das Trackbudget begrenzt die Queue. Die Laufzeit des einzelnen
        # Modells beginnt erst, wenn der serielle Broker READY meldet.
        deadline = (track_deadline if math.isfinite(track_deadline)
                    else time.monotonic() + execution_timeout)
        request = uuid.uuid4().hex
        try:
            _check(deadline, None)
            with socket.socket() as sock:
                sock.settimeout(.05)
                sock.connect(self.address)
                _send(sock, _json(dict(token=self.token, generation=self.generation,
                    request=request, deadline=deadline)), min(deadline, time.monotonic()+2), None)
                if _receive(sock, MAX_HEADER, deadline, None) != b'READY':
                    raise ValueError('Native READY missing')
                deadline = min(deadline, time.monotonic() + execution_timeout)
                _send(sock, _pack(dict(version=3, job=job, parameters=parameters,
                                      execution_timeout_s=execution_timeout), b''), deadline, None)
                response = _load(_receive(sock, 8*1024*1024, deadline, None))
                _check(deadline, None)
                if (type(response) is not dict or set(response) != {'request', 'results'}
                        or response['request'] != request or type(response['results']) is not dict):
                    raise ValueError('Native response identity mismatch')
                return response['results']
        except Exception as error:
            return dict(status='unavailable', reason=f'service_error:{type(error).__name__}')

    def score(self, audio, sample_rate, candidates, *, window_start_s, track_duration_s, verified_grid, **unused):
        if not candidates:
            return []
        if verified_grid is not True:
            return _diagnostics(candidates, 'unverified_grid')
        if self.error:
            return _diagnostics(candidates, self.error)
        if len(candidates) > MAX_CANDIDATES:
            return _diagnostics(candidates, 'service_error:CandidateLimit')
        from ..config import PARALLEL_ANALYSIS_TIMEOUT
        deadline = getattr(_local, 'deadline', None) or time.monotonic() + PARALLEL_ANALYSIS_TIMEOUT
        request = uuid.uuid4().hex
        try:
            _check(deadline, None)
            with socket.socket() as sock:
                sock.settimeout(.05)
                sock.connect(self.address)
                _send(sock, _json(dict(token=self.token, generation=self.generation, request=request,
                                       deadline=deadline)), min(deadline, time.monotonic()+2), None)
                if _receive(sock, MAX_HEADER, deadline, None) != b'READY':
                    raise ValueError('Cue READY missing')
                # Erst jetzt PCM kopieren: wartende Worker serialisieren kein Audio.
                reduced = [{k: item[k] for k in ('start_s', 'kind', 'mood')} for item in candidates]
                payload = encode_audio(audio, sample_rate, reduced, window_start_s=window_start_s,
                                       track_duration_s=track_duration_s, verified_grid=verified_grid)
                _send(sock, payload, deadline, None)
                response = _load(_receive(sock, MAX_WIRE, deadline, None))
                _check(deadline, None)
                if type(response) is not dict or set(response) != {'request', 'results'} or response['request'] != request:
                    raise ValueError('Cue response identity mismatch')
                _validate_results(response['results'], len(candidates))
                return response['results']
        except Exception as error:
            logger.warning('Cue-Service nicht verfügbar: %s', type(error).__name__)
            return _diagnostics(candidates, f'service_error:{type(error).__name__}')

    def score_beats(self, audio, sample_rate, *, window_start_s, track_duration_s):
        duration = len(audio) / sample_rate
        if self.error:
            return _beat_failure_window(window_start_s, duration, 'service_error', self.error)
        from ..config import PARALLEL_ANALYSIS_TIMEOUT
        deadline = getattr(_local, 'deadline', None) or time.monotonic() + PARALLEL_ANALYSIS_TIMEOUT
        request = uuid.uuid4().hex
        try:
            _check(deadline, None)
            with socket.socket() as sock:
                sock.settimeout(.05)
                sock.connect(self.address)
                _send(sock, _json(dict(token=self.token, generation=self.generation, request=request,
                                       deadline=deadline)), min(deadline, time.monotonic()+2), None)
                if _receive(sock, MAX_HEADER, deadline, None) != b'READY':
                    raise ValueError('Beat READY missing')
                payload = encode_beat_audio(audio, sample_rate, window_start_s=window_start_s,
                                           track_duration_s=track_duration_s)
                _send(sock, payload, deadline, None)
                response = _load(_receive(sock, MAX_WIRE, deadline, None))
                _check(deadline, None)
                if type(response) is not dict or set(response) != {'request', 'results'} or response['request'] != request:
                    raise ValueError('Beat response identity mismatch')
                result = response['results']
                _validate_beat_window(result)
                if result['start_s'] != window_start_s or result['duration_s'] != duration:
                    raise ValueError('Beat response coverage mismatch')
                return result
        except Exception as error:
            logger.warning('Beat-Service nicht verfügbar: %s', type(error).__name__)
            return _beat_failure_window(window_start_s, duration, 'service_error', type(error).__name__)


class CueServiceOwner:
    def __init__(self, config=None):
        self.config = dict(model_config(), **(config or {}))
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._generations = {}
        self._lane = self._thread = self._listener = self._active = None
        self._error = None
        self._token = secrets.token_hex(32)
        self._seen = {}
        self._closed = False

    @property
    def model_pid(self):
        return self._lane.pid if self._lane else None

    def register_generation(self):
        generation = uuid.uuid4().hex
        with self._lock:
            if self._closed:
                raise RuntimeError('Cue owner closed')
            if _terminal_failure.is_set():
                return CueClient(None, self._token, generation, self.config, 'service_cleanup_unconfirmed')
            self._generations[generation] = threading.Event()
            self._seen[generation] = set()
            if self._listener is None and self._error is None:
                listener = None
                try:
                    listener = socket.socket()
                    listener.bind(('127.0.0.1', 0))
                    listener.listen(4)
                    listener.settimeout(.05)
                    self._listener = listener
                    self._thread = threading.Thread(target=self._serve, daemon=True, name='hpg-cue-broker')
                    self._thread.start()
                except OSError as error:
                    if listener is not None:
                        listener.close()
                    self._error = f'service_bind_error:{type(error).__name__}'
            return CueClient(self._listener.getsockname() if self._listener else None,
                             self._token, generation, self.config, self._error)

    def cancel_generation(self, generation):
        with self._lock:
            event = self._generations.pop(generation, None)
            self._seen.pop(generation, None)
            if event:
                event.set()

    def _serve(self):
        while not self._stop.is_set():
            try:
                sock, _ = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with sock:
                with self._lock:
                    self._active = sock
                sock.settimeout(.05)
                try:
                    auth = _load(_receive(sock, MAX_HEADER, time.monotonic()+2, self._stop))
                    if (type(auth) is not dict or set(auth) != {'token', 'generation', 'request', 'deadline'}
                            or type(auth['token']) is not str or not hmac.compare_digest(auth['token'], self._token)
                            or type(auth['generation']) is not str or type(auth['request']) is not str
                            or len(auth['request']) != 32 or any(c not in '0123456789abcdef' for c in auth['request'])
                            or not _finite(auth['deadline'])):
                        raise ValueError('Cue auth invalid')
                    with self._lock:
                        event = self._generations.get(auth['generation'])
                        seen = self._seen.get(auth['generation'])
                        if event is None or auth['request'] in seen or len(seen) >= MAX_CANDIDATES:
                            raise ValueError('Cue generation/request invalid')
                        seen.add(auth['request'])
                    cancel = _CombinedEvent(self._stop, event)
                    deadline = auth['deadline']
                    _check(deadline, cancel)
                    _send(sock, b'READY', deadline, cancel)
                    payload = _receive(sock, MAX_WIRE, deadline, cancel)
                    envelope, envelope_size = _header(payload)
                    if envelope.get('job') in ('native_phrase', 'deep_features', 'native_beat'):
                        from .native_phrase_adapter import enabled
                        is_phrase = envelope['job'] == 'native_phrase'
                        if ((is_phrase and not enabled()) or set(envelope) not in (
                                {'version', 'job', 'parameters'},
                                {'version', 'job', 'parameters', 'execution_timeout_s'})
                                or type(envelope['version']) is not int or envelope['version'] != 3
                                or len(payload) != 4 + envelope_size
                                or type(envelope['parameters']) is not dict):
                            raise ValueError('Invalid or disabled native phrase job')
                        execution_timeout = envelope.get('execution_timeout_s', MAX_PATH_JOB_SECONDS)
                        timeout_limit = (MAX_DEEP_FEATURE_SECONDS if envelope['job'] == 'deep_features'
                                         else MAX_PATH_JOB_SECONDS)
                        if not _finite(execution_timeout) or not 0. < execution_timeout <= timeout_limit:
                            raise ValueError('Invalid native execution timeout')
                        native_payload = _json(envelope['parameters'])
                        native_limit = 16384 if is_phrase else 32768
                        if len(native_payload) > native_limit:
                            raise ValueError('Native request too large')
                        # Vor dem nativen Aufruf ONNX/TF freigeben: kein zweites
                        # gleichzeitig residentes Modellbudget von 4 GiB.
                        if self._lane is not None:
                            self._lane.close()
                            self._lane = None
                        from ..config import MODEL_PROCESS_MEMORY_LIMIT_BYTES
                        module = {
                            'native_phrase': 'hpg_core.ai_models.native_phrase_worker',
                            'deep_features': 'hpg_core.ai_models.deep_feature_worker',
                            'native_beat': 'hpg_core.ai_models.native_beat_pipeline_worker',
                        }[envelope['job']]
                        with OwnedModelProcess(module, 'handle',
                                max_payload_bytes=8*1024*1024,
                                memory_limit_bytes=MODEL_PROCESS_MEMORY_LIMIT_BYTES) as native:
                            response = native.call(native_payload,
                                deadline=min(deadline, time.monotonic()+execution_timeout), cancel_event=cancel)
                        results = _load(response)
                        if type(results) is not dict:
                            raise ValueError('Invalid native response')
                        _send(sock, _json(dict(request=auth['request'], results=results)), deadline, cancel)
                        continue
                    header, audio = _decode_job(payload)
                    is_beat = header.get('job') == 'beat'
                    header['config'] = self.config if is_beat else {
                        key: self.config[key] for key in ('samplecnn_path', 'cue_model_path', 'prefer_directml')}
                    if 4 + len(_json(header)) + audio.nbytes > MAX_WIRE:
                        raise ValueError('Owner header exceeds payload bound')
                    payload = _pack(header, audio.tobytes())
                    _check(deadline, cancel)
                    if self._lane is None:
                        from ..config import MODEL_PROCESS_MEMORY_LIMIT_BYTES
                        self._lane = OwnedModelProcess(
                            __name__, 'handle_models',
                            memory_limit_bytes=MODEL_PROCESS_MEMORY_LIMIT_BYTES)
                    response = self._lane.call(payload, deadline=deadline, cancel_event=cancel)
                    results = _load(response)
                    if is_beat:
                        _validate_beat_window(results)
                    else:
                        _validate_results(results, len(header['candidates']))
                    _send(sock, _json(dict(request=auth['request'], results=results)), deadline, cancel)
                except Exception as error:
                    if isinstance(error, ModelProcessCleanupError):
                        _terminal_failure.set()
                        self._stop.set()
                    logger.warning('Cue-Auftrag beendet: %s', type(error).__name__)
                finally:
                    with self._lock:
                        self._active = None

    def close(self):
        with self._lock:
            self._closed = True
            self._stop.set()
            sockets = (self._active, self._listener)
        for sock in sockets:
            if sock:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()
        if self._thread:
            self._thread.join(3.5)
        if self._thread and self._thread.is_alive():
            self._error = 'service_cleanup_unconfirmed'
            _terminal_failure.set()
            logger.error('Cue-Broker-Ende unbestätigt; Owner bleibt geschlossen')
            return
        if self._lane:
            try:
                self._lane.close()
            except Exception:
                self._error = 'service_cleanup_unconfirmed'
                _terminal_failure.set()
                logger.exception('Cue-Lane-Ende unbestätigt')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def install_client(client):
    global _pool_client
    _pool_client = client


@contextmanager
def request_deadline(deadline):
    previous = getattr(_local, 'deadline', None)
    _local.deadline = deadline
    try:
        yield
    finally:
        _local.deadline = previous


@contextmanager
def _track_context():
    if getattr(_local, 'track', None) is not None:
        yield
        return
    from ..config import analysis_timeout_seconds
    previous_deadline = getattr(_local, 'deadline', None)
    _local.deadline = previous_deadline if previous_deadline is not None else time.monotonic() + analysis_timeout_seconds()
    state = dict(owner=None, client=None)
    _local.track = state
    try:
        yield
    finally:
        try:
            if state['owner'] is not None:
                state['owner'].close()
        finally:
            _local.track = None
            _local.deadline = previous_deadline


def track_session(function):
    """Ein lazy Owner pro direktem Trackaufruf, keine Änderung der Pooldeadline."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        with _track_context():
            return function(*args, **kwargs)
    return wrapped


@contextmanager
def session():
    if _pool_client is not None:
        yield _pool_client
    else:
        with _track_context():
            state = _local.track
            if state['client'] is None:
                state['owner'] = CueServiceOwner()
                state['client'] = state['owner'].register_generation()
            yield state['client']


def _validate_results(results, count=None):
    if type(results) is not list or len(results) > MAX_CANDIDATES or (count is not None and len(results) != count):
        raise ValueError('Invalid cue result count')
    fields = {'index', 'status', 'reason', 'raw_score', 'source', 'model_hashes', 'preprocess_version', 'coverage'}
    for index, item in enumerate(results):
        if (type(item) is not dict or set(item) != fields or type(item['index']) is not int or item['index'] != index
                or type(item['status']) is not str
                or item['status'] not in {'ok', 'unavailable', 'invalid_input', 'unsupported_model', 'model_error'}
                or (item['reason'] is not None and type(item['reason']) is not str)
                or item['source'] != CUE_SCORE_SOURCE
                or item['preprocess_version'] != PREPROCESS_VERSION
                or type(item['model_hashes']) is not dict or type(item['coverage']) is not dict):
            raise ValueError('Invalid cue result schema')
        if item['status'] == 'ok':
            if not _finite(item['raw_score']) or item['model_hashes'] != MODEL_HASHES or item['reason'] is not None:
                raise ValueError('Invalid successful cue result')
        elif item['raw_score'] is not None:
            raise ValueError('Failed cue result contains score')
        if any(k not in MODEL_HASHES or type(v) is not str or len(v) != 64 or any(c not in '0123456789abcdef' for c in v)
               for k, v in item['model_hashes'].items()):
            raise ValueError('Invalid model identity')
        allowed = {'window_start_s', 'window_end_s', 'track_duration_s', 'required_start_sample',
                   'required_end_sample', 'sample_rate', 'padded_left_samples', 'padded_right_samples',
                   'source_sample_rate', 'source_sample_count'}
        if any(k not in allowed or not _finite(v) for k, v in item['coverage'].items()):
            raise ValueError('Invalid cue coverage')
        coverage = item['coverage']
        if coverage:
            required = allowed - {'padded_left_samples', 'padded_right_samples'}
            if (not required <= set(coverage) or coverage['sample_rate'] != 22050
                    or type(coverage['source_sample_rate']) is not int or coverage['source_sample_rate'] < 1
                    or type(coverage['source_sample_count']) is not int or coverage['source_sample_count'] < 1
                    or not 0 <= coverage['window_start_s'] < coverage['window_end_s']
                    or coverage['track_duration_s'] <= coverage['window_start_s']
                    or coverage['window_end_s'] > coverage['track_duration_s'] + 1 / coverage['source_sample_rate']
                    or coverage['window_end_s'] != coverage['window_start_s'] + coverage['source_sample_count'] / coverage['source_sample_rate']
                    or any(type(coverage[k]) is not int for k in ('required_start_sample', 'required_end_sample'))
                    or coverage['required_end_sample'] - coverage['required_start_sample'] != 6 * 59049):
                raise ValueError('Inconsistent cue coverage')
        if item['status'] == 'ok':
            if set(coverage) != allowed:
                raise ValueError('Successful cue needs full coverage')
            left, right = coverage['padded_left_samples'], coverage['padded_right_samples']
            available = math.ceil(coverage['source_sample_count'] * 22050 / coverage['source_sample_rate'])
            if (type(left) is not int or type(right) is not int or min(left, right) < 0
                    or left + right > 6 * 59049
                    or left != max(0, -coverage['required_start_sample'])
                    or right != max(0, coverage['required_end_sample'] - available)
                    or (left > 0 and coverage['window_start_s'] != 0)
                    or (right > 0 and abs(coverage['window_end_s'] - coverage['track_duration_s']) > 1 / coverage['source_sample_rate'])):
                raise ValueError('Invalid cue edge padding')


def _validate_beat_window(window):
    fields = {'start_s', 'duration_s', 'status', 'reason', 'results'}
    if (type(window) is not dict or set(window) != fields
            or not _finite(window['start_s']) or window['start_s'] < 0
            or not _finite(window['duration_s']) or not 0 < window['duration_s'] <= 60
            or window['status'] not in ('evaluated', 'decode_error', 'unavailable')
            or (window['reason'] is not None and type(window['reason']) is not str)
            or type(window['results']) is not list):
        raise ValueError('Invalid beat window')
    if window['status'] != 'evaluated':
        if window['results'] or not window['reason']:
            raise ValueError('Invalid unavailable beat window')
        return
    if window['reason'] is not None or len(window['results']) != 2:
        raise ValueError('Invalid evaluated beat window')
    fields = {'model_id', 'status', 'reason', 'model_hashes', 'preprocess_version',
              'decoder_version', 'provider', 'frame_rate', 'contract_basis', 'decoder'}
    for model_id, result in zip(('model7', 'model8'), window['results']):
        if (type(result) is not dict or set(result) != fields or result['model_id'] != model_id
                or result['status'] not in ('ok', 'unavailable', 'missing_model', 'unsupported_model', 'model_error', 'service_error')
                or (result['reason'] is not None and type(result['reason']) is not str)
                or type(result['model_hashes']) is not dict
                or result['model_hashes'] not in ({}, BEAT_HASHES[model_id])
                or result['preprocess_version'] != BEAT_PREPROCESS
                or result['decoder_version'] != BEAT_DECODER_VERSION
                or result['provider'] != 'CPU' or type(result['frame_rate']) not in (int, float)
                or result['frame_rate'] != 100 or result['contract_basis'] != 'static_source_derived'):
            raise ValueError('Invalid beat model result')
        if result['status'] in ('ok', 'unavailable'):
            if result['model_hashes'] != BEAT_HASHES[model_id]:
                raise ValueError('Missing beat model identity')
            _validate_beat_decoder(result['decoder'], window)
            if result['status'] != result['decoder']['status']:
                raise ValueError('Beat decoder status mismatch')
            if result['reason'] != (result['decoder']['reason'] or None):
                raise ValueError('Beat decoder reason mismatch')
        elif result['decoder'] is not None or not result['reason']:
            raise ValueError('Invalid failed beat model')


def _validate_beat_decoder(value, window):
    from .native_beat_decoder import validate_decoder
    return validate_decoder(value, window)


def neural_snapshot(structure, identity, beat_windows=None):
    return dict(version=2, fingerprint=identity, windows=structure.cue_diagnostics,
                beat_windows=[] if beat_windows is None else beat_windows)


def validate_neural_analysis(value, *, track_duration_s=None):
    if value == {}:
        return
    if (type(value) is not dict or set(value) != {'version', 'fingerprint', 'windows', 'beat_windows'}
            or type(value['version']) is not int or value['version'] != 2
            or type(value['fingerprint']) is not str or len(value['fingerprint']) != 64
            or any(c not in '0123456789abcdef' for c in value['fingerprint'])
            or type(value['windows']) is not list or len(value['windows']) > 2
            or type(value['beat_windows']) is not list or len(value['beat_windows']) > 3):
        raise ValueError('Invalid neural analysis schema')
    for window in value['windows']:
        if (type(window) is not dict or set(window) != {'start_s', 'status', 'results'}
                or not _finite(window['start_s']) or window['start_s'] < 0
                or type(window['status']) is not str
                or window['status'] not in {'evaluated', 'unverified_grid', 'no_candidates', 'decode_error'}):
            raise ValueError('Invalid neural window')
        _validate_results(window['results'])
    previous = -1.
    for window in value['beat_windows']:
        _validate_beat_window(window)
        if window['start_s'] <= previous:
            raise ValueError('Duplicate or unordered beat windows')
        if track_duration_s is not None and (not _finite(track_duration_s)
                or window['start_s'] + window['duration_s'] > track_duration_s + 1/44100):
            raise ValueError('Beat window outside track')
        previous = window['start_s']


def transient_failure(value):
    for window in value.get('windows', []):
        if window.get('status') == 'decode_error':
            return True
        for result in window['results']:
            if result['status'] == 'model_error' and result['reason'] == 'model_load_error: FileNotFoundError':
                continue
            if result['status'] in {'model_error', 'invalid_input'}:
                return True
            if result['status'] == 'unavailable' and result['reason'] not in {'unverified_grid', 'missing_window_context'}:
                return True
    for window in value.get('beat_windows', []):
        if window['status'] == 'decode_error':
            return True
        if any(result['status'] in ('model_error', 'service_error') for result in window['results']):
            return True
    return False
