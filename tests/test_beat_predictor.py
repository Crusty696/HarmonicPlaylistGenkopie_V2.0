"""Adaptervertrag mit Fake-TensorFlow; echte Modellprobe erfolgt getrennt."""
from contextlib import nullcontext
import hashlib
import types

import numpy as np
import pytest

from hpg_core.ai_models import beat_predictor as bp


class Shape:
  def __init__(self, values):
    self.values = values
  def as_list(self):
    return self.values


class Spec:
  def __init__(self, shape, dtype='float32', name=None):
    self.shape, self.dtype, self.name = Shape(shape), dtype, name


class Tensor:
  def __init__(self, values):
    self.values = values
    self.dtype = values.dtype
  def numpy(self):
    return self.values


class Function:
  structured_input_signature = ((), {'fltp': Spec([None, None], name='fltp')})
  structured_outputs = {'output_1': Spec([None, None]), 'output_2': Spec([None, 2])}
  def __init__(self):
    self.inputs = []
    self.mutate = lambda values: values
  def __call__(self, *, fltp):
    self.inputs.append(fltp.copy())
    frames = fltp.shape[1] // 441 + 1
    output = np.tile(np.array([.2, .3], np.float32), (frames, 1))
    return {'output_1': Tensor(np.zeros((frames, 314), np.float32)),
            'output_2': Tensor(self.mutate(output))}


@pytest.fixture
def environment(tmp_path, monkeypatch):
  bp._reset_process_state()
  pins = {}
  for model_id in ('model7', 'model8'):
    path = tmp_path / model_id
    path.mkdir()
    pins[model_id] = {}
    for name in ('keras_metadata.pb', 'saved_model.pb', 'variables/variables.index',
                 'variables/variables.data-00000-of-00001'):
      target = path / name
      target.parent.mkdir(exist_ok=True)
      content = (model_id + name).encode()
      target.write_bytes(content)
      pins[model_id][name] = hashlib.sha256(content).hexdigest()
  monkeypatch.setattr(bp, 'MODEL_HASHES', pins)
  function = Function()
  events = []
  config = types.SimpleNamespace(
    set_visible_devices=lambda devices, kind: events.append(('gpu', devices, kind)),
    get_visible_devices=lambda kind: [],
    threading=types.SimpleNamespace(
      set_intra_op_parallelism_threads=lambda value: events.append(('intra', value)),
      set_inter_op_parallelism_threads=lambda value: events.append(('inter', value)),
      get_intra_op_parallelism_threads=lambda: 2,
      get_inter_op_parallelism_threads=lambda: 1))
  def load(path):
    events.append(('load', str(path)))
    return types.SimpleNamespace(signatures={'serving_default': function})
  runtime = types.SimpleNamespace(config=config, float32='float32',
    saved_model=types.SimpleNamespace(load=load), device=lambda name: nullcontext(),
    convert_to_tensor=lambda value, dtype: value)
  def import_module(name):
    assert name == 'tensorflow'
    events.append(('import', name))
    return runtime
  monkeypatch.setattr(bp.importlib, 'import_module', import_module)
  yield tmp_path, function, runtime, events
  bp._reset_process_state()


def infer(environment, audio=None, sample_rate=44100, model_id='model7', **kwargs):
  root, *_ = environment
  if audio is None:
    audio = np.zeros(44100, np.float32)
  return bp.infer_beat_activations(audio, sample_rate,
    model_directory=kwargs.pop('model_directory', root / model_id), model_id=model_id, **kwargs)


def test_lazy_config_cache_and_remainder_class(environment):
  root, function, _, events = environment
  assert events == []
  first = infer(environment)
  assert first['activations'].shape == (100, 2)
  assert np.allclose(first['activations'].sum(axis=1), .5)
  assert first['metadata']['provider'] == 'CPU'
  assert first['metadata']['contract_basis'] == 'static_source_derived'
  assert first['metadata']['duration_s'] == 1.
  assert first['metadata']['frame_rate'] == 100.
  infer(environment)
  assert sum(event[0] == 'load' for event in events) == 1
  assert events[:3] == [('import', 'tensorflow'), ('gpu', [], 'GPU'), ('intra', 2)]
  assert function.inputs[0].shape == (1, 44100)


def test_both_models_only_two_loads_and_path_independent_identity(environment, tmp_path):
  import shutil
  root, _, _, events = environment
  infer(environment)
  infer(environment, model_id='model8')
  copied = tmp_path / 'same-identity'
  shutil.copytree(root / 'model7', copied)
  infer(environment, model_directory=copied)
  assert sum(event[0] == 'load' for event in events) == 2


def test_changed_model_rejected_without_reload(environment):
  root, _, _, events = environment
  infer(environment)
  (root / 'model7' / 'saved_model.pb').write_bytes(b'changed')
  with pytest.raises(bp.UnsupportedBeatModel):
    infer(environment)
  assert sum(event[0] == 'load' for event in events) == 1


def test_hash_change_during_load_rejected_and_not_retried(environment):
  root, _, runtime, events = environment
  original_bytes = (root / 'model7' / 'saved_model.pb').read_bytes()
  original = runtime.saved_model.load
  def changed(path):
    loaded = original(path)
    (root / 'model7' / 'saved_model.pb').write_bytes(b'changed')
    return loaded
  runtime.saved_model.load = changed
  with pytest.raises(bp.UnsupportedBeatModel):
    infer(environment)
  assert not bp._models
  (root / 'model7' / 'saved_model.pb').write_bytes(original_bytes)
  with pytest.raises(bp.UnsupportedBeatModel):
    infer(environment)
  assert sum(event[0] == 'load' for event in events) == 1


def test_configuration_failure_is_explicit_and_not_retried(environment):
  _, _, runtime, events = environment
  def fail(value):
    raise RuntimeError('already initialized')
  runtime.config.threading.set_intra_op_parallelism_threads = fail
  for _ in range(2):
    with pytest.raises(bp.BeatModelUnavailable, match='configuration'):
      infer(environment)
  assert not any(event[0] == 'load' for event in events)
  assert sum(event[0] == 'import' for event in events) == 1


@pytest.mark.parametrize('audio,sr', [(np.zeros((44100, 2), np.float32), 44100),
  (np.zeros(44100, int), 44100), (np.zeros(44099, np.float32), 44100),
  (np.zeros(61, np.float32), 1), (np.array([np.nan], np.float32), 1),
  (np.array([np.inf], np.float64), 1), (np.zeros(44100, np.float32), 0),
  (np.zeros(44100, np.float32), True)],
  ids=['stereo', 'integer', 'short', 'long', 'nan', 'inf', 'zero-rate', 'bool-rate'])
def test_invalid_pcm_before_runtime(environment, audio, sr):
  with pytest.raises(ValueError):
    infer(environment, audio, sr)
  assert environment[3] == []


def test_resampling_has_no_peak_or_integer_scale(environment, monkeypatch):
  seen = {}
  fake = types.SimpleNamespace()
  def resample(audio, **kwargs):
    seen.update(kwargs)
    seen['peak'] = float(audio.max())
    return np.repeat(audio, 2)
  fake.resample = resample
  monkeypatch.setitem(__import__('sys').modules, 'librosa', fake)
  infer(environment, np.full(22050, .25, np.float64), 22050)
  assert seen == {'orig_sr': 22050, 'target_sr': 44100, 'res_type': 'soxr_hq', 'peak': .25}
  assert np.all(environment[1].inputs[0] == .25)


@pytest.mark.parametrize('mutation', [lambda a: a.astype(np.float64), lambda a: a[:-1],
  lambda a: np.full_like(a, np.nan), lambda a: np.full_like(a, .7),
  lambda a: np.full_like(a, -.1)], ids=['dtype', 'shape', 'nan', 'sum', 'negative'])
def test_invalid_output(environment, mutation):
  environment[1].mutate = mutation
  with pytest.raises(bp.BeatModelProtocolError):
    infer(environment)


def test_signature_mismatch(environment):
  environment[1].structured_input_signature = ((), {'wrong': Spec([None, None])})
  with pytest.raises(bp.BeatModelProtocolError):
    infer(environment)


def test_pinned_runtime_dynamic_output1_signature(environment):
  # Echte Metadaten aus beat-owned-signature-red.txt: output_1 dynamisch,
  # obwohl der ausgeführte Tensor in den Forschungsproben 314 Spalten besitzt.
  environment[1].structured_outputs = {
    'output_1': Spec([None, None], name='output_1'),
    'output_2': Spec([None, 2], name='output_2'),
  }
  assert infer(environment)['activations'].shape == (100, 2)


def test_missing_model_does_not_import_tf(environment):
  with pytest.raises(bp.BeatModelUnavailable):
    infer(environment, model_directory=environment[0] / 'missing')
  assert environment[3] == []


def test_payload_limit_before_copy(environment, monkeypatch):
  monkeypatch.setattr(bp, 'MAX_AUDIO_BYTES', 4)
  with pytest.raises(ValueError, match='limit'):
    infer(environment)
  assert environment[3] == []


def test_pid_change_does_not_reuse_model(environment, monkeypatch):
  infer(environment)
  original_pid = bp.os.getpid()
  monkeypatch.setattr(bp.os, 'getpid', lambda: original_pid + 1)
  infer(environment)
  assert sum(event[0] == 'load' for event in environment[3]) == 2
  assert len(bp._models) == 1
  assert next(iter(bp._models))[0] == original_pid + 1


def test_load_failure_not_retried(environment):
  attempts = []
  def fail(path):
    attempts.append(path)
    raise RuntimeError('load error')
  environment[2].saved_model.load = fail
  for _ in range(2):
    with pytest.raises(bp.BeatModelUnavailable, match='model_load'):
      infer(environment)
  assert len(attempts) == 1


def test_runtime_import_failure_explicit(environment, monkeypatch):
  def missing(name):
    raise ImportError('missing runtime')
  monkeypatch.setattr(bp.importlib, 'import_module', missing)
  with pytest.raises(bp.BeatModelUnavailable, match='runtime_configuration: ImportError'):
    infer(environment)


def test_inference_failure_keeps_loaded_model(environment):
  def fail(values):
    raise RuntimeError('inference error')
  environment[1].mutate = fail
  with pytest.raises(bp.BeatModelUnavailable, match='inference'):
    infer(environment)
  environment[1].mutate = lambda values: values
  assert infer(environment)['activations'].shape == (100, 2)
  assert sum(event[0] == 'load' for event in environment[3]) == 1


def test_sixty_second_limit_and_fractional_duration(environment):
  result = infer(environment, np.zeros(44100 * 60, np.float32))
  assert result['activations'].shape == (6000, 2)
  result = infer(environment, np.zeros(44101, np.float32))
  assert result['activations'].shape == (101, 2)
  assert result['metadata']['duration_s'] == 44101 / 44100


def test_unsupported_id_does_not_import(environment):
  with pytest.raises(bp.UnsupportedBeatModel):
    infer(environment, model_id='model9')
  assert not environment[3]


def test_float64_overflow_rejected_before_runtime(environment):
  with pytest.raises(ValueError, match='float32 range'):
    infer(environment, np.full(44100, 1e200, np.float64))
  assert not environment[3]
