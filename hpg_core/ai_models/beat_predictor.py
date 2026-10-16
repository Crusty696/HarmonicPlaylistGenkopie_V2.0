"""Gepinnte Beat-SavedModels auf CPU; keine Modellwahl oder Trackintegration.

44100 Hz und normalisierte Float-PCM-Konvention sind quellengestützt abgeleitet,
nicht gegen den nativen Rekordbox-Reader bewiesen. STFT bleibt im Modellgraph.
"""
from __future__ import annotations

import hashlib
import importlib
import math
import os
from pathlib import Path
import threading

import numpy as np


MAX_AUDIO_BYTES = 64 * 1024 * 1024
TARGET_RATE = 44100
PREPROCESS_VERSION = 'hpg-beat-mono-44100-soxr-hq-float-v1'
# Vollständige Identität aus research-beat-runtime/manifest.json, RB7.2.19.
MODEL_HASHES = {
  'model7': {
    'keras_metadata.pb': '41b7d1c17876465b4bbe240e999d9d1e3e0687ff467a42488654f1e87bcc6b55',
    'saved_model.pb': 'ea7b5e7c3567525bb9b0eff1238c13b9d4ab8336399e0f2dd3301528a9dc936a',
    'variables/variables.data-00000-of-00001': '7ddbbfaf22feab99687d8fdc6e1f72b46e3937b7a4e006e320be8888d85b2e4c',
    'variables/variables.index': '8c5864c2e5ae076117ac7fbbe2fe090d0983801238b837525425a5233a9804af',
  },
  'model8': {
    'keras_metadata.pb': '89d63710656f1858bd78266e6449e14ef740f03046186f8926a0bb8acc4528cf',
    'saved_model.pb': '09baf025fb561d27264a6f26522e12037fd2f37bf1db378c7edf9366116c49dd',
    'variables/variables.data-00000-of-00001': 'ec2cef99d55076b46ec54dd4f51c0bd2d8e8344aeaf96a85166e9062b014604e',
    'variables/variables.index': 'f3041d936e049d5cb4c206c58f9298ba131e247dcac4f2e696255a706df34fa1',
  },
}


class BeatModelUnavailable(RuntimeError):
  """Modell/Runtime ist nicht verfügbar oder Inferenz ist fehlgeschlagen."""


class UnsupportedBeatModel(BeatModelUnavailable):
  """Modell-ID oder vollständige Dateiidentität ist nicht unterstützt."""


class BeatModelProtocolError(BeatModelUnavailable):
  """Signatur oder Rückgabe verletzt den belegten Tensorvertrag."""


_lock = threading.RLock()
_pid = os.getpid()
_runtime = None
_runtime_failure = None
_models = {}
_load_failures = {}


def _reset_process_state():
  """Prozesslokale Referenzen; nur beim PID-Wechsel vor einem Zugriff nötig."""
  global _pid, _runtime, _runtime_failure
  _pid, _runtime, _runtime_failure = os.getpid(), None, None
  _models.clear()
  _load_failures.clear()


def _hashes(directory, model_id):
  hashes = {}
  try:
    for name in MODEL_HASHES[model_id]:
      digest = hashlib.sha256()
      with (Path(directory) / name).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
          digest.update(chunk)
      hashes[name] = digest.hexdigest()
  except (OSError, TypeError, ValueError) as exc:
    raise BeatModelUnavailable(f'model_files: {type(exc).__name__}') from exc
  if hashes != MODEL_HASHES[model_id]:
    raise UnsupportedBeatModel('unsupported_model_hashes')
  return hashes


def _tensorflow():
  global _runtime, _runtime_failure
  if _runtime_failure is not None:
    raise BeatModelUnavailable(_runtime_failure)
  if _runtime is None:
    try:
      runtime = importlib.import_module('tensorflow')
      runtime.config.set_visible_devices([], 'GPU')
      runtime.config.threading.set_intra_op_parallelism_threads(2)
      runtime.config.threading.set_inter_op_parallelism_threads(1)
      if (runtime.config.get_visible_devices('GPU')
          or runtime.config.threading.get_intra_op_parallelism_threads() != 2
          or runtime.config.threading.get_inter_op_parallelism_threads() != 1):
        raise RuntimeError('CPU/thread configuration not applied')
    except Exception as exc:
      _runtime_failure = f'runtime_configuration: {type(exc).__name__}'
      raise BeatModelUnavailable(_runtime_failure) from exc
    _runtime = runtime
  return _runtime


def _validate_signature(function, runtime):
  try:
    positional, named = function.structured_input_signature
    if positional != () or set(named) != {'fltp'}:
      raise ValueError('input names')
    spec = named['fltp']
    if (spec.dtype != runtime.float32 or spec.shape.as_list() != [None, None]
        or spec.name != 'fltp'):
      raise ValueError('input tensor')
    outputs = function.structured_outputs
    if set(outputs) != {'output_1', 'output_2'}:
      raise ValueError('output names')
    # Gepinnte Runtime-Signatur: output_1 hat eine dynamische zweite Achse.
    # 314 ist eine beobachtete Tensorbreite, keine statische TensorSpec-Angabe.
    for name, width in (('output_1', None), ('output_2', 2)):
      if outputs[name].dtype != runtime.float32 or outputs[name].shape.as_list() != [None, width]:
        raise ValueError('output tensor')
  except Exception as exc:
    raise BeatModelProtocolError(f'signature: {type(exc).__name__}') from exc


def _model(directory, model_id):
  hashes = _hashes(directory, model_id)
  identity = (_pid, model_id, tuple(sorted(hashes.items())))
  runtime = _tensorflow()
  if identity in _load_failures:
    error_type, reason = _load_failures[identity]
    raise error_type(reason)
  if identity not in _models:
    if len(_models) + len(_load_failures) >= 2:
      raise BeatModelUnavailable('model_capacity')
    try:
      with runtime.device('/CPU:0'):
        loaded = runtime.saved_model.load(str(directory))
      if set(loaded.signatures) != {'serving_default'}:
        raise BeatModelProtocolError('serving_default signature required')
      function = loaded.signatures['serving_default']
      _validate_signature(function, runtime)
      if _hashes(directory, model_id) != hashes:
        raise UnsupportedBeatModel('model_changed_during_load')
    except BeatModelUnavailable as exc:
      _load_failures[identity] = (type(exc), str(exc))
      raise
    except Exception as exc:
      reason = f'model_load: {type(exc).__name__}'
      _load_failures[identity] = (BeatModelUnavailable, reason)
      raise BeatModelUnavailable(reason) from exc
    _models[identity] = (loaded, function)
  return runtime, _models[identity][1], hashes


def _prepare_audio(audio, sample_rate):
  if (not isinstance(audio, np.ndarray) or audio.ndim != 1
      or audio.dtype.kind != 'f' or audio.dtype.itemsize not in (4, 8)):
    raise ValueError('expected mono float32/float64')
  if audio.nbytes > MAX_AUDIO_BYTES:
    raise ValueError('audio_payload_limit')
  if (isinstance(sample_rate, (bool, np.bool_))
      or not isinstance(sample_rate, (int, float, np.integer, np.floating))
      or not math.isfinite(float(sample_rate)) or sample_rate < 1
      or int(sample_rate) != sample_rate):
    raise ValueError('invalid sample_rate')
  sample_rate = int(sample_rate)
  duration = len(audio) / sample_rate
  if not 1 <= duration <= 60:
    raise ValueError('audio duration must be between 1 and 60 seconds')
  if not np.isfinite(audio).all():
    raise ValueError('nonfinite audio')
  # Größenlimits stehen vor Floatkopie und Resampling; keine Peaknorm/PCM-Skalierung.
  with np.errstate(over='ignore', invalid='ignore'):
    prepared = np.ascontiguousarray(audio, dtype=np.float32)
  if not np.isfinite(prepared).all():
    raise ValueError('audio outside float32 range')
  if sample_rate != TARGET_RATE:
    try:
      import librosa
      prepared = librosa.resample(prepared, orig_sr=sample_rate,
                                 target_sr=TARGET_RATE, res_type='soxr_hq')
    except Exception as exc:
      raise BeatModelUnavailable(f'resampling: {type(exc).__name__}') from exc
  expected = math.ceil(len(audio) * TARGET_RATE / sample_rate)
  if (prepared.dtype != np.float32 or prepared.ndim != 1 or len(prepared) != expected
      or not np.isfinite(prepared).all()):
    raise BeatModelProtocolError('resampling_output')
  return np.ascontiguousarray(prepared), duration, sample_rate


def infer_beat_activations(audio, sample_rate, *, model_directory, model_id):
  """Liefert {'activations': Float32[T,2], 'metadata': {...}} oder klare Exception.

  model_directory bezeichnet das konkrete SavedModel-Verzeichnis. model_id ist
  exakt 'model7' oder 'model8'; keine automatische Auswahl, Downloads oder Ensembles.
  Aktivierungen enthalten Beat ohne Downbeat und Downbeat, mit impliziter Restklasse.
  Framezeiten >= Originaldauer werden entfernt. Kein Decoder/Track wird aufgerufen.
  """
  if not isinstance(model_id, str) or model_id not in MODEL_HASHES:
    raise UnsupportedBeatModel('unsupported_model_id')
  prepared, duration, source_rate = _prepare_audio(audio, sample_rate)
  with _lock:
    if os.getpid() != _pid:
      _reset_process_state()
    runtime, function, hashes = _model(model_directory, model_id)
    try:
      with runtime.device('/CPU:0'):
        outputs = function(fltp=runtime.convert_to_tensor(prepared[None, :], dtype=runtime.float32))
      if not isinstance(outputs, dict) or set(outputs) != {'output_1', 'output_2'}:
        raise BeatModelProtocolError('output names')
      activations = outputs['output_2'].numpy()
    except BeatModelProtocolError:
      raise
    except Exception as exc:
      raise BeatModelUnavailable(f'inference: {type(exc).__name__}') from exc
    expected_frames = len(prepared) // 441 + 1
    if (not isinstance(activations, np.ndarray) or activations.dtype != np.float32
        or activations.shape != (expected_frames, 2)
        or not np.isfinite(activations).all()
        or np.any(activations < 0) or np.any(activations > 1)
        or np.any(activations.astype(np.float64).sum(axis=1) > 1 + 1e-6)):
      raise BeatModelProtocolError('invalid output_2 activations')
    keep = int(np.searchsorted(np.arange(expected_frames) / 100., duration, side='left'))
    return {'activations': activations[:keep].copy(), 'metadata': {
      'model_id': model_id, 'model_hashes': hashes, 'provider': 'CPU',
      'frame_rate': 100., 'duration_s': duration, 'input_sample_rate': source_rate,
      'model_sample_rate': TARGET_RATE, 'model_sample_count': len(prepared),
      'preprocess_version': PREPROCESS_VERSION, 'contract_basis': 'static_source_derived',
      'verified': False,
    }}
