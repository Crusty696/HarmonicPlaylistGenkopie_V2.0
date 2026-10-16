"""Begrenzte, prozesslokale ONNX-Sessions mit explizitem CPU-Fallback.

Der LRU hält höchstens zwei Wrapper. Extern gehaltene Wrapper zählen nicht zu
diesem Limit. Harte Timeouts benötigen eine äußere Prozessgrenze. Registrierte
Provider belegen keine GPU-Ausführung. Aufrufer dürfen Eingaben während run()
nicht verändern; die Laufzeit erhält eine private Kopie ohne Typkonvertierung.
"""
from collections import OrderedDict
from collections.abc import Mapping
import hashlib
import importlib
import os
from pathlib import Path
import re
import threading

import numpy as np


class OnnxModelError(RuntimeError):
    """Basisklasse für diagnostizierbare Modellfehler."""


class ModelUnavailableError(OnnxModelError):
    """Modell oder Runtime konnte nicht geladen werden."""


class ModelInputError(OnnxModelError):
    """Eingabe verletzt den Tensorvertrag."""


class ModelInferenceError(OnnxModelError):
    """Inferenz gescheitert oder Ausgabe ungültig."""


_CACHE = OrderedDict()
_CACHE_LOCK = threading.RLock()
_CACHE_PID = os.getpid()
_DTYPES = {
    'float': np.float32, 'double': np.float64, 'float16': np.float16,
    'int8': np.int8, 'int16': np.int16, 'int32': np.int32, 'int64': np.int64,
    'uint8': np.uint8, 'uint16': np.uint16, 'uint32': np.uint32,
    'uint64': np.uint64, 'bool': np.bool_,
}


def _identity(path):
    try:
        before = path.stat()
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        after = path.stat()
        if (before.st_mtime_ns, before.st_size, before.st_ino) != (after.st_mtime_ns, after.st_size, after.st_ino):
            raise ModelUnavailableError('Model file changed while hashing')
        return (str(path), after.st_mtime_ns, after.st_size, digest)
    except OSError as exc:
        raise ModelUnavailableError(f'Model unavailable: {path}: {exc}') from exc


def _finite(value):
    if isinstance(value, Mapping):
        return all(_finite(k) and _finite(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return all(_finite(item) for item in value)
    if isinstance(value, np.ndarray):
        if value.dtype.kind in 'biufc':
            return bool(np.isfinite(value).all())
        if value.dtype.kind == 'O':
            return all(_finite(item) for item in value.flat)
        return value.dtype.kind in 'US'
    if isinstance(value, (float, complex, np.number)):
        return bool(np.isfinite(value))
    return isinstance(value, (str, bytes, int, bool))


def _output_type(text):
    """Nur explizit unterstützte ORT-Metatypen zulassen, auch bei leeren Werten."""
    text = text.replace(' ', '')
    tensor = re.fullmatch(r'tensor\((\w+)\)', text)
    if tensor and tensor[1] in _DTYPES:
        return ('tensor', tensor[1])
    sequence = re.fullmatch(r'seq\((.+)\)', text)
    if sequence:
        return ('seq', _output_type(sequence[1]))
    mapping = re.fullmatch(r'map\((int64|string),(.+)\)', text)
    if mapping:
        return ('map', mapping[1], _output_type(mapping[2]))
    raise ModelInferenceError(f'Unsupported output type: {text}')


def _check_output_value(value, contract, name, shape, symbols, *, map_scalar=False):
    kind = contract[0]
    if kind == 'seq':
        if not isinstance(value, (list, tuple)):
            raise ModelInferenceError(f'{name}: expected sequence')
        for item in value:
            _check_output_value(item, contract[1], name, None, symbols)
        return
    if kind == 'map':
        if not isinstance(value, Mapping):
            raise ModelInferenceError(f'{name}: expected map')
        for key, item in value.items():
            if contract[1] == 'string':
                valid = isinstance(key, str)
            else:
                valid = (type(key) is int or isinstance(key, np.int64)) and -(2**63) <= key < 2**63
            if not valid:
                raise ModelInferenceError(f'{name}: map key type mismatch')
            _check_output_value(item, contract[2], name, None, symbols, map_scalar=True)
        return
    dtype = np.dtype(_DTYPES[contract[1]])
    if map_scalar and not isinstance(value, np.ndarray):
        # ORT liefert ML-Map-Werte als Python-Skalare ohne erhaltene Bitbreite.
        if isinstance(value, np.generic):
            valid = value.dtype == dtype
        elif dtype.kind == 'f':
            valid = type(value) is float
        elif dtype.kind in 'iu':
            valid = type(value) is int and np.iinfo(dtype).min <= value <= np.iinfo(dtype).max
        else:
            valid = type(value) is bool
        if not valid or not _finite(value):
            raise ModelInferenceError(f'{name}: map value dtype or finite mismatch')
        return
    if not isinstance(value, np.ndarray) or value.dtype != dtype:
        raise ModelInferenceError(f'{name}: output dtype mismatch')
    if shape is not None:
        if value.ndim != len(shape):
            raise ModelInferenceError(f'{name}: output rank mismatch')
        for expected, actual in zip(shape, value.shape):
            if isinstance(expected, int) and expected >= 0 and expected != actual:
                raise ModelInferenceError(f'{name}: output dimension mismatch')
            if isinstance(expected, str) and expected and symbols.setdefault(expected, actual) != actual:
                raise ModelInferenceError(f'{name}: output symbolic dimension mismatch: {expected}')
    if not _finite(value):
        raise ModelInferenceError(f'{name}: non-finite output')


class OnnxModel:
    """Session und gemeinsame Sperre; über get_model() beziehen."""

    def __init__(self, path, identity, ort, prefer_directml, device_id):
        self._lock = threading.RLock()
        self._pid = os.getpid()
        self._path = path
        self._identity = identity
        self._ort = ort
        self._device_id = device_id
        self._available = list(ort.get_available_providers())
        self._requested = ['DmlExecutionProvider', 'CPUExecutionProvider'] if prefer_directml else ['CPUExecutionProvider']
        self._fallback_reason = None
        self._terminal_error = None
        dml = prefer_directml and 'DmlExecutionProvider' in self._available
        if prefer_directml and not dml:
            self._fallback_reason = 'DirectML unavailable'
        try:
            self._session = self._create(dml)
        except Exception as exc:
            if not dml:
                raise ModelUnavailableError(f'CPU init failed: {exc}') from exc
            self._fallback_reason = f'DirectML init failed: {exc}'
            try:
                self._session = self._create(False)
            except Exception as cpu_exc:
                raise ModelUnavailableError(f'CPU init fallback failed: {cpu_exc}') from cpu_exc
        if _identity(path) != identity:
            raise ModelUnavailableError('Model file changed during session creation')

    def _create(self, dml):
        options = self._ort.SessionOptions()
        options.execution_mode = self._ort.ExecutionMode.ORT_SEQUENTIAL
        options.enable_mem_pattern = False
        options.intra_op_num_threads = min(2, os.cpu_count() or 1)
        options.inter_op_num_threads = 1
        providers = [('DmlExecutionProvider', {'device_id': self._device_id}), 'CPUExecutionProvider'] if dml else ['CPUExecutionProvider']
        session = self._ort.InferenceSession(str(self._path), sess_options=options, providers=providers)
        session.disable_fallback()
        registered = session.get_providers()
        if dml and 'DmlExecutionProvider' not in registered:
            raise ModelUnavailableError(f'DirectML init silently fell back: {registered}')
        if not dml and registered != ['CPUExecutionProvider']:
            raise ModelUnavailableError(f'Unexpected CPU session providers: {registered}')
        return session

    def describe(self):
        with self._lock:
            def metadata(node):
                return {'name': node.name, 'type': node.type, 'shape': list(node.shape) if node.shape is not None else None}
            return {
                'path': str(self._path), 'sha256': self._identity[3], 'pid': self._pid,
                'requested_providers': list(self._requested), 'available_providers': list(self._available),
                'session_providers': list(self._session.get_providers()), 'fallback_reason': self._fallback_reason,
                'inputs': [metadata(n) for n in self._session.get_inputs()],
                'outputs': [metadata(n) for n in self._session.get_outputs()],
            }

    def _inputs(self, inputs, symbols=None):
        nodes = self._session.get_inputs()
        if not isinstance(inputs, Mapping) or set(inputs) != {n.name for n in nodes}:
            raise ModelInputError('Input names do not match model')
        if symbols is None:
            symbols = {}
        result = {}
        for node in nodes:
            value = inputs[node.name]
            dtype = _DTYPES.get(node.type.removeprefix('tensor(').removesuffix(')'))
            if not isinstance(value, np.ndarray) or dtype is None or value.dtype != np.dtype(dtype):
                raise ModelInputError(f'{node.name}: unsupported or mismatched dtype {node.type}')
            value = value.copy(order='C')
            if node.shape is not None:
                if value.ndim != len(node.shape):
                    raise ModelInputError(f'{node.name}: rank mismatch')
                for expected, actual in zip(node.shape, value.shape):
                    if isinstance(expected, int) and expected >= 0 and expected != actual:
                        raise ModelInputError(f'{node.name}: dimension mismatch')
                    if isinstance(expected, str) and expected:
                        if symbols.setdefault(expected, actual) != actual:
                            raise ModelInputError(f'{node.name}: symbolic dimension mismatch: {expected}')
            if not _finite(value):
                raise ModelInputError(f'{node.name}: non-finite input')
            result[node.name] = value
        return result

    def run(self, inputs, output_names=None):
        if os.getpid() != self._pid:
            raise ModelInferenceError('Session belongs to another process')
        with self._lock:
            if os.getpid() != self._pid:
                raise ModelInferenceError('Session belongs to another process')
            if self._terminal_error is not None:
                raise ModelInferenceError(self._terminal_error)
            symbols = {}
            prepared = self._inputs(inputs, symbols)
            output_nodes = self._session.get_outputs()
            known = {n.name: n for n in output_nodes}
            if output_names is not None and (not isinstance(output_names, (list, tuple)) or not output_names or any(not isinstance(n, str) or n not in known for n in output_names)):
                raise ModelInputError('Invalid output names')
            names = list(output_names) if output_names is not None else None
            selected_nodes = [known[name] for name in names] if names is not None else output_nodes
            contracts = [_output_type(node.type) for node in selected_nodes]
            try:
                outputs = self._session.run(names, prepared)
            except Exception as exc:
                if 'DmlExecutionProvider' not in self._session.get_providers():
                    raise ModelInferenceError(f'CPU run failed: {exc}') from exc
                self._fallback_reason = f'DirectML run failed: {exc}'
                try:
                    if _identity(self._path) != self._identity:
                        raise ModelUnavailableError('Model file changed before CPU fallback')
                    self._session = self._create(False)
                    if _identity(self._path) != self._identity:
                        raise ModelUnavailableError('Model file changed during CPU fallback')
                    outputs = self._session.run(names, prepared)
                except Exception as cpu_exc:
                    self._terminal_error = f'CPU run fallback failed: {cpu_exc}'
                    raise ModelInferenceError(self._terminal_error) from cpu_exc
            if not isinstance(outputs, (list, tuple)) or len(outputs) != len(selected_nodes):
                raise ModelInferenceError('Output count does not match requested model outputs')
            for value, node, contract in zip(outputs, selected_nodes, contracts):
                _check_output_value(value, contract, node.name, node.shape, symbols)
            return outputs


def clear_model_cache():
    """Entfernt Cache-Referenzen; extern gehaltene Wrapper bleiben verwendbar."""
    global _CACHE_PID
    with _CACHE_LOCK:
        _CACHE.clear()
        _CACHE_PID = os.getpid()


def get_model(path, *, prefer_directml=True, device_id=0):
    """Lädt lazy; identische Anfragen teilen Session und Inferenzsperre."""
    if not isinstance(device_id, int) or isinstance(device_id, bool) or device_id < 0:
        raise ModelInputError('device_id must be a nonnegative integer')
    with _CACHE_LOCK:
        if _CACHE_PID != os.getpid():
            clear_model_cache()
        try:
            resolved = Path(path).resolve(strict=True)
        except (OSError, ValueError, TypeError) as exc:
            raise ModelUnavailableError(f'Invalid model path: {exc}') from exc
        identity = _identity(resolved)
        key = (os.getpid(), *identity, bool(prefer_directml), device_id)
        for stale in list(_CACHE):
            if stale[1] == str(resolved) and stale[1:5] != identity:
                del _CACHE[stale]
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key]
        try:
            ort = importlib.import_module('onnxruntime')
        except (ImportError, OSError) as exc:
            raise ModelUnavailableError(f'ONNX Runtime unavailable: {exc}') from exc
        model = OnnxModel(resolved, identity, ort, prefer_directml, device_id)
        _CACHE[key] = model
        while len(_CACHE) > 2:
            _CACHE.popitem(last=False)
        return model
