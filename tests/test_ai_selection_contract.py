"""Keine stillen Modellwechsel oder Wiederholung bereits gescheiterter KI-Anfragen."""
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("installed", [["wanted-extra"], ["other"], ["prefix-wanted"]])
def test_explicit_lm_key_must_match_exactly(monkeypatch, installed):
    from hpg_core import ai_launcher as launcher
    monkeypatch.setattr(launcher, "lms_start", lambda: 1234)
    monkeypatch.setattr(launcher, "lms_models", lambda port: installed)
    status = launcher._prepare_lmstudio("wanted")
    assert status.active_model == ""


def test_analysis_cannot_change_explicit_provider_or_model(monkeypatch):
    import main
    from hpg_core import ai_launcher as launcher
    monkeypatch.setattr(launcher, "detect_and_start", lambda **kwargs: SimpleNamespace(
        running=True, name="Ollama", active_model="other", base_url="http://localhost:11434/v1/chat/completions"))
    monkeypatch.setattr(launcher, "prepare_provider", lambda *args, **kwargs: SimpleNamespace(
        running=True, name="LM Studio", active_model="other", base_url="http://localhost:1234/v1/chat/completions"))
    worker = main.AIAnalysisWorker([], provider="LM Studio", model="wanted")
    assert worker._ensure_ready() is False
    assert worker.provider == "LM Studio" and worker.model == "wanted"


def test_failed_qualification_blocks_analysis_but_explicit_retest_can_replace(monkeypatch):
    import main
    from hpg_core import lmstudio_runtime as runtime
    url = "http://localhost:1234/v1/chat/completions"
    runtime.record_qualification("unique-failed-model", url, False, "Schema ungueltig")
    called = []
    def prepare(model, url, **kwargs):
        runtime.require_not_failed(model, url)
        called.append(model)
        return "owned"
    monkeypatch.setattr(runtime, "prepare_gpu_model", prepare)
    worker = main.AIAnalysisWorker([], provider="LM Studio", model="unique-failed-model", base_url=url)
    assert worker._ensure_ready() is False
    assert not called
    runtime.record_qualification("unique-failed-model", url, True, "Schema gueltig")
    assert worker._ensure_ready() is True
    assert len(called) == 1


def test_qualification_is_endpoint_and_config_scoped(monkeypatch):
    from hpg_core import lmstudio_runtime as runtime
    url = "http://localhost:1234/v1/chat/completions"
    runtime.record_qualification("scope-model", url, False, "Schema ungueltig")
    with pytest.raises(ValueError, match="Schema ungueltig"):
        runtime.require_not_failed("scope-model", url)
    runtime.require_not_failed("scope-model", "http://localhost:9999/v1/chat/completions")
    monkeypatch.setattr(runtime, "CONTEXT_TOKENS", 1024)
    runtime.require_not_failed("scope-model", url)


def test_real_prepare_blocks_failed_exact_load_profile_before_sdk(monkeypatch):
    import lmstudio
    from hpg_core import ai_launcher, lmstudio_runtime as runtime
    from tests.test_lmstudio_runtime import survey
    target = runtime.select_target_gpu(survey())
    url = "http://localhost:1234/v1/chat/completions"
    profile = runtime.requested_load_config(target)
    key = runtime._qualification_key("selected", url, load_profile=profile)
    runtime.record_qualification("selected", url, False, "bad schema", qualification_key=key)
    monkeypatch.setattr(runtime, "runtime_target", lambda *a: target)
    record = {"key": "selected", "type": "llm", "format": "gguf", "architecture": "qwen3",
              "size_bytes": 2*1024**3, "capabilities": {"trained_for_tool_use": True}}
    monkeypatch.setattr(ai_launcher, "_http_json", lambda *a, **k: (True, {"models": [record]}))
    def no_sdk(**kwargs):
        raise AssertionError("SDK darf bei gescheitertem Antwortvertrag nicht geladen werden")
    monkeypatch.setattr(lmstudio, "Client", no_sdk)
    with pytest.raises(ValueError, match="bad schema"):
        runtime.prepare_gpu_model("selected", url)
    changed = {**profile, "gpu": {**profile["gpu"], "mainGpu": 7}}
    assert key != runtime._qualification_key("selected", url, load_profile=changed)


def test_explicit_qt_probe_replaces_failed_schema_and_uses_fixed_request_key(monkeypatch):
    import main
    import requests
    from hpg_core import lmstudio_runtime as runtime
    from tests.test_ai_schema import _valid_data
    import json
    url = "http://localhost:1234/v1/chat/completions"
    key = runtime._qualification_key("selected", url, load_profile={"exact": "profile"})
    runtime.record_qualification("selected", url, False, "bad schema", qualification_key=key)
    calls = []
    def prepare(model, endpoint, **kwargs):
        calls.append(kwargs)
        runtime._INSTANCE_QUALIFICATION_KEYS["owned"] = key
        return "owned"
    monkeypatch.setattr(runtime, "prepare_gpu_model", prepare)
    def post(*args, **kwargs):
        # Waehren der Anfrage geaenderte Zuordnung darf den Nachweis nicht umhaengen.
        runtime._INSTANCE_QUALIFICATION_KEYS["owned"] = ("different",)
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {
            "model": "owned", "choices": [{"message": {"content": json.dumps(_valid_data())}}]})
    monkeypatch.setattr(requests, "post", post)
    worker = main.AITestWorker("LM Studio", "selected", url)
    results = []
    worker.test_finished.connect(lambda *args: results.append(args))
    worker.run()
    assert results[0][0] is True and calls[0]["explicit_retest"] is True
    runtime.require_not_failed("selected", url, qualification_key=key)
    assert ("different",) not in runtime._QUALIFICATIONS


@pytest.mark.parametrize("failure", ["timeout", "cancel", "gpu"])
def test_incomplete_probe_does_not_replace_previous_failed_schema(monkeypatch, failure):
    import main
    import requests
    from hpg_core import lmstudio_runtime as runtime
    url = "http://localhost:1234/v1/chat/completions"
    runtime.record_qualification("selected", url, False, "original schema failure")
    worker = main.AITestWorker("LM Studio", "selected", url)
    def prepare(*args, **kwargs):
        if failure == "gpu":
            raise ValueError("GPU setup error")
        return "owned"
    monkeypatch.setattr(runtime, "prepare_gpu_model", prepare)
    def post(*args, **kwargs):
        if failure == "timeout":
            raise requests.Timeout("timeout")
        # Direkter run()-Unit-Test: Qt ignoriert requestInterruption bei nicht
        # gestarteten Threads. Den beobachtbaren Cancel-Zustand gezielt setzen.
        monkeypatch.setattr(worker, "isInterruptionRequested", lambda: True)
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {})
    monkeypatch.setattr(requests, "post", post)
    worker.run()
    with pytest.raises(ValueError, match="original schema failure"):
        runtime.require_not_failed("selected", url)


def test_fetch_cancel_after_http_does_not_record_qualification(monkeypatch):
    from hpg_core import ai_engine, lmstudio_runtime as runtime
    from tests.test_ai_schema import _track
    monkeypatch.setattr(ai_engine, "_cancelable_post", lambda *args: SimpleNamespace(status_code=200, json=lambda: {}))
    with pytest.raises(InterruptedError):
        ai_engine.fetch_ai_analysis(_track(), "LM Studio", "selected", "http://localhost:1234/v1/chat/completions",
                                   request_model="owned", cancel_check=lambda: True)
    assert not runtime._QUALIFICATIONS
