"""GPU-Identitaet und Modellbudget duerfen nicht aus Listenpositionen stammen."""
import pytest


def test_pre_cancelled_gpu_preparation_does_no_survey(monkeypatch):
    from hpg_core import lmstudio_runtime as runtime
    monkeypatch.setattr(runtime, 'runtime_target', lambda *a: pytest.fail('Survey nach Abbruch'))
    with pytest.raises(InterruptedError):
        runtime.prepare_gpu_model('selected', 'http://localhost:1234/v1/chat/completions',
                                  cancel_check=lambda: True)


def test_cancel_during_survey_prevents_inventory(monkeypatch):
    from hpg_core import lmstudio_runtime as runtime, ai_launcher
    state = {'cancel': False}
    def survey(*a):
        state['cancel'] = True
        return {}
    monkeypatch.setattr(runtime, 'runtime_target', survey)
    monkeypatch.setattr(ai_launcher, '_http_json', lambda *a, **kw: pytest.fail('Inventar nach Abbruch'))
    with pytest.raises(InterruptedError):
        runtime.prepare_gpu_model('selected', 'http://localhost:1234/v1/chat/completions',
                                  cancel_check=lambda: state['cancel'])


def survey():
    return {"status": "ok", "engines": [{
        "name": "llama.cpp-win-x86_64-vulkan-avx2", "version": "2.51.0",
        "hardwareSurvey": {"gpuSurveyResult": {"result": {"code": "success"}, "gpuInfo": [
            {"name": "AMD Radeon(TM) Graphics", "deviceId": 7,
             "integrationType": "integrated", "dedicatedMemoryCapacityBytes": 32*1024**3},
            {"name": "AMD Radeon RX 7800 XT", "deviceId": 3,
             "integrationType": "discrete", "dedicatedMemoryCapacityBytes": 16*1024**3},
        ]}}, "visibleDevicesConfig": {"visibleDevices": [3, 7], "changesOrder": True},
    }]}


def test_selects_named_discrete_gpu_not_first_or_largest():
    from hpg_core.lmstudio_runtime import select_target_gpu
    target = select_target_gpu(survey())
    assert target["device_id"] == 3
    assert target["disabled_ids"] == [7]
    assert target["vram_bytes"] == 16*1024**3


def test_missing_rx_is_not_silently_replaced_by_igpu():
    from hpg_core.lmstudio_runtime import select_target_gpu
    data = survey()
    data["engines"][0]["hardwareSurvey"]["gpuSurveyResult"]["gpuInfo"].pop()
    with pytest.raises(ValueError, match="RX 7800 XT"):
        select_target_gpu(data)


@pytest.mark.parametrize("overrides", [
    {"architecture": "ltxv"}, {"architecture": "clip"},
    {"architecture": None}, {"size_bytes": 16*1024**3},
    {"capabilities": {}}, {"type": "embedding"},
])
def test_non_chat_or_unbudgeted_records_not_offered(overrides):
    from hpg_core.lmstudio_runtime import model_rejection_reason
    record = {"key": "arbitrary-name", "type": "llm", "format": "gguf",
              "architecture": "qwen3", "size_bytes": 4*1024**3,
              "capabilities": {"trained_for_tool_use": True}}
    record.update(overrides)
    assert model_rejection_reason(record, 16*1024**3)


def test_provider_discovery_never_loads_or_downloads_models(monkeypatch):
    from hpg_core import ai_launcher as launcher
    monkeypatch.setattr(launcher, "lms_start", lambda: 1234)
    monkeypatch.setattr(launcher, "lms_models", lambda port: ["installed"])
    def forbidden(*args, **kwargs):
        pytest.fail("Inventarabfrage darf kein Modell laden oder herunterladen")
    monkeypatch.setattr(launcher, "lms_get", forbidden)
    monkeypatch.setattr(launcher, "lms_load", forbidden)
    assert launcher._prepare_lmstudio("missing").active_model == ""
    assert launcher._prepare_lmstudio(None).active_model == "installed"


def test_worker_checks_gpu_even_with_existing_endpoint(monkeypatch):
    import main
    from hpg_core import lmstudio_runtime
    seen = []
    def prepare(model, url, **kwargs):
        seen.append((model, url))
        return "owned-instance"
    monkeypatch.setattr(lmstudio_runtime, "prepare_gpu_model", prepare)
    worker = main.AIAnalysisWorker([], "LM Studio", "selected", "http://localhost:1234/v1/chat/completions")
    assert worker._ensure_ready()
    assert seen == [("selected", "http://localhost:1234/v1/chat/completions")]
    assert worker._request_model == "owned-instance"


def test_ambiguous_gpu_index_mapping_fails_before_load():
    from hpg_core.lmstudio_runtime import requested_load_config, select_target_gpu
    target = select_target_gpu(survey())
    target["visible_devices"] = [3, 3]
    with pytest.raises(ValueError, match="Indexzuordnung"):
        requested_load_config(target)


@pytest.mark.parametrize('version', ['2.51.0', '2.67.0', '2.71.0'])
def test_verified_runtime_uses_device_ids_without_double_remapping(version):
    from hpg_core.lmstudio_runtime import requested_load_config, select_target_gpu
    data = survey()
    data['engines'][0]['version'] = version
    config = requested_load_config(select_target_gpu(data))
    assert config["gpu"]["mainGpu"] == 3
    assert config["gpu"]["disabledGpus"] == [7]


@pytest.mark.parametrize('mutation', [
    {'runtime_version': '2.68.0'}, {'runtime_version': None},
    {'runtime': 'other'}, {'visible_devices': [7]},
    {'survey_ids': [3, 3]}, {'visible_devices': [3, 99]},
    {'disabled_ids': []}, {'disabled_ids': [3, 7]},
    {'disabled_ids': [7, 7]}, {'device_id': True},
])
def test_runtime_and_device_sets_must_remain_unambiguous(mutation):
    from hpg_core.lmstudio_runtime import requested_load_config, select_target_gpu
    target = select_target_gpu(survey())
    target.update(mutation)
    with pytest.raises(ValueError):
        requested_load_config(target)


def test_qualification_is_bound_to_observed_runtime_version():
    from hpg_core.lmstudio_runtime import _qualification_key
    url = 'http://localhost:1234/v1/chat/completions'
    old = _qualification_key('selected', url, load_profile={'same': True},
        runtime_identity=('llama.cpp-win-x86_64-vulkan-avx2', '2.51.0'))
    current = _qualification_key('selected', url, load_profile={'same': True},
        runtime_identity=('llama.cpp-win-x86_64-vulkan-avx2', '2.67.0'))
    assert old != current
    assert current != _qualification_key('selected', url, load_profile={'same': True})


def test_failed_gpu_setup_never_becomes_ready(monkeypatch):
    import main
    from hpg_core import lmstudio_runtime
    def fail(*args, **kwargs):
        raise ValueError("GPU mapping missing")
    monkeypatch.setattr(lmstudio_runtime, "prepare_gpu_model", fail)
    worker = main.AIAnalysisWorker([], "LM Studio", "selected", "http://localhost:1234/v1/chat/completions")
    assert not worker._ensure_ready()
    assert "GPU mapping missing" in worker.failure_reason


def test_probe_rejects_ok_as_schema_evidence(monkeypatch):
    import main
    import requests
    from types import SimpleNamespace
    monkeypatch.setattr(requests, "post", lambda *a, **k: SimpleNamespace(
        status_code=200, raise_for_status=lambda: None,
        json=lambda: {"model": "model", "choices": [{"message": {"content": "OK"}}]}))
    worker = main.AITestWorker("Ollama", "model", "http://localhost:11434/v1/chat/completions")
    results = []
    worker.test_finished.connect(lambda *args: results.append(args))
    worker.run()
    assert results and results[0][0] is False


@pytest.mark.parametrize("failure", [None, "identity", "readback", "cancel"])
def test_owned_sdk_instance_validation_and_cleanup(monkeypatch, failure):
    from types import SimpleNamespace
    import lmstudio
    from hpg_core import ai_launcher, lmstudio_runtime as runtime
    target = runtime.select_target_gpu(survey())
    monkeypatch.setattr(runtime, "runtime_target", lambda *a: target)
    record = {"key": "selected", "type": "llm", "format": "gguf", "architecture": "qwen3",
              "size_bytes": 2*1024**3, "capabilities": {"trained_for_tool_use": True}}
    monkeypatch.setattr(ai_launcher, "_http_json", lambda *a, **k: (True, {"models": [record]}))
    monkeypatch.setattr(ai_launcher, "_lms_exe", lambda: "lms")
    cancelled, loaded, unloaded = [], [], []
    def estimate(*args, **kwargs):
        if failure == "cancel":
            cancelled.append(True)
        return "Estimated GPU Memory: 3 GiB"
    monkeypatch.setattr(ai_launcher, "_run_hidden", estimate)
    def load(model, identifier, **kwargs):
        loaded.append(identifier)
        config = {} if failure == "readback" else kwargs["config"]
        return SimpleNamespace(identifier=identifier,
            get_info=lambda: SimpleNamespace(model_key="wrong" if failure == "identity" else model),
            get_load_config=lambda: SimpleNamespace(to_dict=lambda: config),
            unload=lambda: unloaded.append(identifier))
    class Client:
        def __init__(self, **kwargs):
            self.llm = SimpleNamespace(list_loaded=lambda: [], load_new_instance=load)
        def __enter__(self): return self
        def __exit__(self, *args): return False
    monkeypatch.setattr(lmstudio, "Client", Client)
    monkeypatch.setattr(runtime, "_OWNED_INSTANCES", {})
    if failure:
        with pytest.raises((ValueError, InterruptedError)):
            runtime.prepare_gpu_model("selected", "http://localhost:1234/v1/chat/completions", cancel_check=lambda: bool(cancelled))
        assert runtime._OWNED_INSTANCES == {}
        assert unloaded == loaded
        if failure == "cancel": assert loaded == []
    else:
        identifier = runtime.prepare_gpu_model("selected", "http://localhost:1234/v1/chat/completions")
        assert loaded == [identifier] and not unloaded
        assert runtime._OWNED_INSTANCES[("localhost:1234", "selected")] == identifier
