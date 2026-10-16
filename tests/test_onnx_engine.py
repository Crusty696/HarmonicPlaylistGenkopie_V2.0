import sys
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from hpg_core.ai_models import onnx_engine as engine


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    state = SimpleNamespace(created=[], available=['CPUExecutionProvider'], init_fail=False,
                            run_fail=False, cpu_init_fail=False, cpu_run_fail=False,
                            silent_fallback=False, change_on_init=False,
                            output=None, output_nodes=None, active=0, peak=0, shape=['N', 2])

    class Session:
        def __init__(self, path, sess_options, providers):
            self.providers = [p[0] if isinstance(p, tuple) else p for p in providers]
            if state.init_fail and self.providers[0] == 'DmlExecutionProvider':
                raise RuntimeError('DML init failed')
            if state.cpu_init_fail and self.providers[0] == 'CPUExecutionProvider':
                raise RuntimeError('CPU init failed')
            if state.silent_fallback:
                self.providers = ['CPUExecutionProvider']
            if state.change_on_init:
                state.path.write_bytes(b'changed')
            state.created.append(self)
            self.options = sess_options
        def disable_fallback(self):
            self.disabled = True
        def get_providers(self):
            return self.providers
        def get_inputs(self):
            return [SimpleNamespace(name='x', type='tensor(float)', shape=state.shape)]
        def get_outputs(self):
            return state.output_nodes if state.output_nodes is not None else [SimpleNamespace(name='y', type='tensor(float)', shape=state.shape)]
        def run(self, names, inputs):
            if state.run_fail and self.providers[0] == 'DmlExecutionProvider':
                raise RuntimeError('DML run failed')
            if state.cpu_run_fail and self.providers[0] == 'CPUExecutionProvider':
                raise RuntimeError('CPU run failed')
            state.active += 1
            state.peak = max(state.peak, state.active)
            try:
                time.sleep(.005)
                return state.output if state.output is not None else [inputs['x'].copy()]
            finally:
                state.active -= 1

    ort = SimpleNamespace(InferenceSession=Session, SessionOptions=SimpleNamespace,
                          ExecutionMode=SimpleNamespace(ORT_SEQUENTIAL=0),
                          get_available_providers=lambda: state.available)
    monkeypatch.setitem(sys.modules, 'onnxruntime', ort)
    engine.clear_model_cache()
    state.path = tmp_path / 'model.onnx'
    state.path.write_bytes(b'model')
    yield state
    engine.clear_model_cache()


def test_missing_runtime(runtime, monkeypatch):
    monkeypatch.setitem(sys.modules, 'onnxruntime', None)
    with pytest.raises(engine.ModelUnavailableError):
        engine.get_model(runtime.path)


def test_cpu_options_and_metadata(runtime):
    model = engine.get_model(runtime.path)
    assert model.run({'x': np.ones((3, 2), np.float32)})[0].shape == (3, 2)
    assert runtime.created[0].options.enable_mem_pattern is False
    assert runtime.created[0].options.execution_mode == 0
    assert runtime.created[0].disabled
    assert model.describe()['session_providers'] == ['CPUExecutionProvider']
    assert model.describe()['fallback_reason']


@pytest.mark.parametrize('failure', ['init_fail', 'run_fail'])
def test_dml_cpu_fallback(runtime, failure):
    runtime.available.insert(0, 'DmlExecutionProvider')
    setattr(runtime, failure, True)
    model = engine.get_model(runtime.path)
    model.run({'x': np.ones((1, 2), np.float32)})
    assert model.describe()['session_providers'] == ['CPUExecutionProvider']
    assert failure.split('_')[0] in model.describe()['fallback_reason']


@pytest.mark.parametrize('value', [np.ones((1, 2), np.float64), np.ones((2,), np.float32),
                                  np.ones((1, 3), np.float32), np.full((1, 2), np.nan, np.float32)])
def test_bad_input(runtime, value):
    with pytest.raises(engine.ModelInputError):
        engine.get_model(runtime.path).run({'x': value})


def test_names_symbols_and_nested_nonfinite(runtime):
    model = engine.get_model(runtime.path)
    with pytest.raises(engine.ModelInputError):
        model.run({'wrong': np.ones((1, 2), np.float32)})
    with pytest.raises(engine.ModelInputError):
        model.run({'x': np.ones((1, 2), np.float32)}, ['unknown'])
    runtime.shape[:] = ['N', 'N']
    with pytest.raises(engine.ModelInputError):
        model.run({'x': np.ones((1, 2), np.float32)})
    runtime.shape[:] = ['N', 2]
    runtime.output = [[{1: float('nan')}]]
    with pytest.raises(engine.ModelInferenceError):
        model.run({'x': np.ones((1, 2), np.float32)})


def test_cache_reuse_lock_eviction_identity(runtime):
    first = engine.get_model(runtime.path)
    assert engine.get_model(runtime.path) is first
    threads = [threading.Thread(target=first.run, args=({'x': np.ones((1, 2), np.float32)},)) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert runtime.peak == 1
    for name in ['two', 'three']:
        path = runtime.path.with_name(name)
        path.write_bytes(name.encode())
        engine.get_model(path)
    assert engine.get_model(runtime.path) is not first
    current = engine.get_model(runtime.path)
    runtime.path.write_bytes(b'other')
    assert engine.get_model(runtime.path) is not current


def test_pid_change(runtime, monkeypatch):
    model = engine.get_model(runtime.path)
    pid = engine.os.getpid()
    monkeypatch.setattr(engine.os, 'getpid', lambda: pid + 1)
    with pytest.raises(engine.ModelInferenceError):
        model.run({'x': np.ones((1, 2), np.float32)})
    assert engine.get_model(runtime.path) is not model


def test_cpu_failures(runtime):
    runtime.cpu_init_fail = True
    with pytest.raises(engine.ModelUnavailableError, match='CPU init'):
        engine.get_model(runtime.path)
    runtime.cpu_init_fail = False
    runtime.cpu_run_fail = True
    with pytest.raises(engine.ModelInferenceError, match='CPU run'):
        engine.get_model(runtime.path).run({'x': np.ones((1, 2), np.float32)})


def test_failed_fallback_is_not_retried(runtime):
    runtime.available.insert(0, 'DmlExecutionProvider')
    model = engine.get_model(runtime.path)
    runtime.run_fail = True
    runtime.cpu_run_fail = True
    for _ in range(2):
        with pytest.raises(engine.ModelInferenceError, match='fallback failed'):
            model.run({'x': np.ones((1, 2), np.float32)})
    assert len(runtime.created) == 2


def test_silent_fallback_is_reported(runtime):
    runtime.available.insert(0, 'DmlExecutionProvider')
    runtime.silent_fallback = True
    model = engine.get_model(runtime.path)
    assert 'silently fell back' in model.describe()['fallback_reason']
    assert model.describe()['requested_providers'][0] == 'DmlExecutionProvider'
    assert model.describe()['session_providers'] == ['CPUExecutionProvider']


def test_model_change_during_creation(runtime):
    runtime.change_on_init = True
    with pytest.raises(engine.ModelUnavailableError, match='changed during'):
        engine.get_model(runtime.path)


def test_same_stat_content_change_and_input_ownership(runtime):
    import os
    before = runtime.path.stat()
    model = engine.get_model(runtime.path)
    data = np.ones((1, 2), np.float32)
    prepared = model._inputs({'x': data})
    assert not np.shares_memory(prepared['x'], data)
    runtime.path.write_bytes(b'other')
    os.utime(runtime.path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert engine.get_model(runtime.path) is not model
    assert len(engine._CACHE) == 1


@pytest.mark.parametrize('output', [[], [np.ones((1, 2), np.float32)] * 2,
    [np.ones((1, 2), np.int64)], [np.ones((2,), np.float32)],
    [np.ones((1, 3), np.float32)], [np.ones((2, 2), np.float32)]])
def test_output_contract_rejects_count_dtype_rank_fixed_and_symbol(runtime, output):
    runtime.output = output
    with pytest.raises(engine.ModelInferenceError):
        engine.get_model(runtime.path).run({'x': np.ones((1, 2), np.float32)})


def test_output_requested_order(runtime):
    runtime.output_nodes = [SimpleNamespace(name='y', type='tensor(float)', shape=['N', 2]),
                            SimpleNamespace(name='z', type='tensor(int64)', shape=['N'])]
    runtime.output = [np.ones((1,), np.int64), np.ones((1, 2), np.float32)]
    model = engine.get_model(runtime.path)
    assert len(model.run({'x': np.ones((1, 2), np.float32)}, ['z', 'y'])) == 2
    with pytest.raises(engine.ModelInferenceError):
        model.run({'x': np.ones((1, 2), np.float32)}, ['y', 'z'])


@pytest.mark.parametrize('value', [[{0: .2, 1: .8}], [{0: np.float32(.5)}]])
def test_genre_sequence_map_output(runtime, value):
    runtime.output_nodes = [SimpleNamespace(name='y', type='seq(map(int64,tensor(float)))', shape=[])]
    runtime.output = [value]
    assert engine.get_model(runtime.path).run({'x': np.ones((1, 2), np.float32)}) == [value]


@pytest.mark.parametrize('value', [[{'bad': .2}], [{0: 'bad'}], [{0: float('nan')}],
                                  [{0: np.float64(.2)}], {0: .2}, [{0: True}]])
def test_genre_sequence_map_rejects_invalid_types(runtime, value):
    runtime.output_nodes = [SimpleNamespace(name='y', type='seq(map(int64,tensor(float)))', shape=[])]
    runtime.output = [value]
    with pytest.raises(engine.ModelInferenceError):
        engine.get_model(runtime.path).run({'x': np.ones((1, 2), np.float32)})


@pytest.mark.parametrize('meta', ['optional(tensor(float))', 'tensor(bfloat16)', 'seq(unknown)'])
def test_unknown_output_metadata_rejected(runtime, meta):
    runtime.output_nodes = [SimpleNamespace(name='y', type=meta, shape=[])]
    runtime.output = [[]]
    with pytest.raises(engine.ModelInferenceError, match='Unsupported output type'):
        engine.get_model(runtime.path).run({'x': np.ones((1, 2), np.float32)})
