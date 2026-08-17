"""Isolierte Vertrags- und Fehlerpfadtests fuer den lokalen AI-Launcher."""

from types import SimpleNamespace

import pytest
import requests

from hpg_core import ai_launcher as launcher


def test_provider_status_repr_and_defaults():
  status = launcher.AIProviderStatus("Ollama", "http://local", None, "m", True)

  assert status.models == []
  assert "running=True" in repr(status)
  assert "active='m'" in repr(status)


@pytest.mark.parametrize(
  ("status_code", "payload", "expected"),
  [(200, {"ok": True}, (True, {"ok": True})), (503, {}, (False, None))],
)
def test_http_json_contract(monkeypatch, status_code, payload, expected):
  response = SimpleNamespace(status_code=status_code, json=lambda: payload)
  monkeypatch.setattr(launcher.requests, "get", lambda *args, **kwargs: response)

  assert launcher._http_json("http://local") == expected


def test_http_json_swallows_transport_error(monkeypatch):
  def fail(*args, **kwargs):
    raise requests.ConnectionError("offline")

  monkeypatch.setattr(launcher.requests, "get", fail)
  assert launcher._http_json("http://local") == (False, None)


def test_wait_until_success_and_timeout(monkeypatch):
  assert launcher._wait_until(lambda: True, 1) is True
  clock = iter([0.0, 0.0, 0.4, 1.1])
  monkeypatch.setattr("time.monotonic", lambda: next(clock))
  monkeypatch.setattr("time.sleep", lambda _seconds: None)

  assert launcher._wait_until(lambda: False, 1) is False


def test_hidden_process_helpers(monkeypatch):
  popen_calls = []
  monkeypatch.setattr(
    launcher.subprocess,
    "Popen",
    lambda args, **kwargs: popen_calls.append((args, kwargs)) or "process",
  )

  assert launcher._popen_hidden(["tool", "serve"]) == "process"
  assert popen_calls[0][0] == ["tool", "serve"]
  assert popen_calls[0][1]["stdout"] is launcher.subprocess.DEVNULL

  completed = SimpleNamespace(stdout="out", stderr="err", returncode=0)
  monkeypatch.setattr(launcher.subprocess, "run", lambda *args, **kwargs: completed)
  assert launcher._run_hidden(["tool"], 2) == "outerr"

  monkeypatch.setattr(
    launcher.subprocess,
    "run",
    lambda *args, **kwargs: (_ for _ in ()).throw(OSError("broken")),
  )
  assert launcher._run_hidden(["tool"], 2) is None


@pytest.mark.parametrize("model", ["nomic-embed", "BERT-base"])
def test_embedding_models_are_detected(model):
  assert launcher._is_embedding_model(model) is True


def test_pick_model_priority_and_fallbacks():
  models = ["nomic-embed", "llama3:latest", "google/gemma-4-e4b"]

  assert launcher._pick_model(models, "llama3:latest") == "llama3:latest"
  assert launcher._pick_model(models, "llama3") == "llama3:latest"
  assert launcher._pick_model(models, "gemma") == "google/gemma-4-e4b"
  assert launcher._pick_model(models, None) == "llama3:latest"
  assert launcher._pick_model(["nomic-embed"], None) == "nomic-embed"
  assert launcher._pick_model([], "missing") == ""


def test_ollama_queries(monkeypatch):
  payloads = {
    launcher._OLLAMA_HOST + "/api/tags": (
      True,
      {"models": [{"name": "llama3:latest"}, {"name": "gemma4:12b"}, {"missing": "ignored"}]},
    ),
    launcher._OLLAMA_HOST + "/api/ps": (
      True,
      {"models": [{"name": "gemma4:12b"}]},
    ),
  }
  monkeypatch.setattr(launcher, "_http_json", lambda url: payloads[url])
  assert launcher.ollama_running() is True
  assert launcher.ollama_models() == ["llama3:latest", "gemma4:12b"]
  assert launcher.ollama_active_model() == "gemma4:12b"


def test_ollama_empty_responses(monkeypatch):
  monkeypatch.setattr(launcher, "_http_json", lambda _url: (False, None))

  assert launcher.ollama_models() == []
  assert launcher.ollama_active_model() == ""


def test_ollama_start_headless_and_gui_fallback(monkeypatch):
  states = iter([False, True])
  monkeypatch.setattr(launcher, "ollama_running", lambda: next(states))
  monkeypatch.setattr(launcher, "_ollama_exe", lambda: "ollama.exe")
  monkeypatch.setattr(launcher.os.path, "exists", lambda path: path == "ollama.exe")
  calls = []
  monkeypatch.setattr(launcher, "_popen_hidden", lambda args: calls.append(args))
  monkeypatch.setattr(launcher, "_wait_until", lambda predicate, timeout: predicate())

  assert launcher.ollama_start() is True
  assert calls == [["ollama.exe", "serve"]]

  monkeypatch.setattr(launcher, "ollama_running", lambda: False)
  monkeypatch.setattr(launcher, "_ollama_exe", lambda: None)
  monkeypatch.setattr(launcher.os.path, "exists", lambda _path: True)
  monkeypatch.setattr(launcher, "_wait_until", lambda predicate, timeout: True)
  gui_calls = []
  monkeypatch.setattr(
    launcher.subprocess, "Popen", lambda args: gui_calls.append(args)
  )

  assert launcher.ollama_start() is True
  assert gui_calls


def test_ollama_pull_and_prepare(monkeypatch):
  monkeypatch.setattr(launcher, "_ollama_exe", lambda: "ollama.exe")
  monkeypatch.setattr(launcher.os.path, "exists", lambda _path: True)
  monkeypatch.setattr(launcher, "_run_hidden", lambda *args, **kwargs: "ok")
  monkeypatch.setattr(launcher, "ollama_models", lambda: ["llama3:latest"])
  assert launcher.ollama_pull("llama3") is True

  monkeypatch.setattr(launcher, "ollama_start", lambda: True)
  monkeypatch.setattr(launcher, "ollama_active_model", lambda: "")
  status = launcher._prepare_ollama("llama3")
  assert status.running is True
  assert status.active_model == "llama3:latest"

  monkeypatch.setattr(launcher, "ollama_start", lambda: False)
  assert launcher._prepare_ollama("llama3").running is False


def test_ollama_already_running_missing_exe_and_auto_pull(monkeypatch):
  monkeypatch.setattr(launcher, "ollama_running", lambda: True)
  assert launcher.ollama_start() is True

  monkeypatch.setattr(launcher, "_ollama_exe", lambda: None)
  assert launcher.ollama_pull("llama3") is False

  monkeypatch.setattr(launcher, "ollama_start", lambda: True)
  model_lists = iter([[], ["llama3:latest"]])
  monkeypatch.setattr(launcher, "ollama_models", lambda: next(model_lists))
  monkeypatch.setattr(launcher, "ollama_active_model", lambda: "")
  monkeypatch.setattr(
    launcher, "ollama_pull", lambda _model, cancel_check=None: True
  )
  status = launcher._prepare_ollama("llama3")
  assert status.models == ["llama3:latest"]
  assert status.active_model == "llama3:latest"


def test_lms_detect_port(monkeypatch):
  monkeypatch.setattr(launcher, "_lms_exe", lambda: "lms.exe")
  monkeypatch.setattr(launcher.os.path, "exists", lambda _path: True)
  monkeypatch.setattr(
    launcher, "_run_hidden", lambda *args, **kwargs: "Server running on port 2345"
  )
  assert launcher.lms_detect_port() == 2345

  monkeypatch.setattr(launcher, "_run_hidden", lambda *args, **kwargs: "stopped")
  assert launcher.lms_detect_port() is None

  monkeypatch.setattr(launcher, "_lms_exe", lambda: None)
  assert launcher.lms_detect_port() is None


def test_lms_start_cli_and_gui(monkeypatch):
  ports = iter([None, 2345])
  monkeypatch.setattr(launcher, "lms_detect_port", lambda: next(ports))
  monkeypatch.setattr(launcher, "_lms_exe", lambda: "lms.exe")
  monkeypatch.setattr(launcher.os.path, "exists", lambda _path: True)
  monkeypatch.setattr(launcher, "_run_hidden", lambda *args, **kwargs: "")
  assert launcher.lms_start() == 2345

  monkeypatch.setattr(launcher, "lms_detect_port", lambda: None)
  monkeypatch.setattr(launcher, "_lms_exe", lambda: None)
  monkeypatch.setattr(launcher, "_wait_until", lambda predicate, timeout: True)
  gui_calls = []
  monkeypatch.setattr(
    launcher.subprocess, "Popen", lambda args: gui_calls.append(args)
  )
  detections = iter([None, 4567])
  monkeypatch.setattr(launcher, "lms_detect_port", lambda: next(detections))
  assert launcher.lms_start() == 4567
  assert gui_calls


def test_lms_models_load_get_and_prepare(monkeypatch):
  monkeypatch.setattr(
    launcher,
    "_http_json",
    lambda _url: (
      True,
      {
        "models": [
          {
            "type": "llm",
            "key": "google/gemma-4-e2b",
            "architecture": "gemma4",
            "capabilities": {"vision": True},
          },
          {"type": "llm", "key": "text-only", "capabilities": {}},
          {"type": "embedding", "key": "nomic-embed"},
        ]
      },
    ),
  )
  assert launcher.lms_models(1234) == ["google/gemma-4-e2b", "text-only"]

  monkeypatch.setattr(launcher, "_lms_exe", lambda: "lms.exe")
  monkeypatch.setattr(launcher.os.path, "exists", lambda _path: True)
  calls = []
  monkeypatch.setattr(
    launcher, "_run_hidden", lambda args, timeout: calls.append((args, timeout)) or ""
  )
  assert launcher.lms_load("google/gemma", 1234) is True
  assert launcher.lms_get("google/gemma") is True

  monkeypatch.setattr(launcher, "_run_hidden", lambda *args, **kwargs: None)
  assert launcher.lms_load("google/gemma", 1234) is False
  assert launcher.lms_get("google/gemma") is False

  monkeypatch.setattr(launcher, "lms_start", lambda: 1234)
  monkeypatch.setattr(launcher, "lms_models", lambda _port: ["google/gemma"])
  loaded = []
  monkeypatch.setattr(
    launcher, "lms_load", lambda model, port: loaded.append((model, port)) or True
  )
  status = launcher._prepare_lmstudio("gemma")
  assert status.running is True
  assert status.active_model == "google/gemma"
  assert loaded == [("google/gemma", 1234)]

  monkeypatch.setattr(launcher, "lms_load", lambda model, port: False)
  status = launcher._prepare_lmstudio("gemma")
  assert status.running is True
  assert status.active_model == ""

  monkeypatch.setattr(launcher, "lms_start", lambda: None)
  assert launcher._prepare_lmstudio("gemma").running is False


def test_lms_empty_helpers_and_auto_get(monkeypatch):
  monkeypatch.setattr(launcher, "_http_json", lambda _url: (False, None))
  assert launcher.lms_models(1234) == []
  monkeypatch.setattr(launcher, "_lms_exe", lambda: None)
  assert launcher.lms_load("model", 1234) is False
  assert launcher.lms_get("model") is False

  monkeypatch.setattr(launcher, "lms_start", lambda: 1234)
  model_lists = iter([[], ["provider/model"]])
  monkeypatch.setattr(launcher, "lms_models", lambda _port: next(model_lists))
  monkeypatch.setattr(
    launcher, "lms_get", lambda _model, cancel_check=None: True
  )
  monkeypatch.setattr(launcher, "lms_load", lambda _model, _port: True)
  status = launcher._prepare_lmstudio("model")
  assert status.active_model == "provider/model"


def test_provider_dispatch_and_detection_order(monkeypatch):
  calls = []

  def prepare(name, preferred_model, cancel_check=None):
    calls.append((name, preferred_model, cancel_check))
    return launcher.AIProviderStatus(
      name,
      "http://local",
      ["model"] if name == "Ollama" else [],
      "model",
      name == "Ollama",
    )

  monkeypatch.setattr(launcher, "prepare_provider", prepare)
  status = launcher.detect_and_start(preferred="LM Studio", preferred_model="model")

  assert status.name == "Ollama"
  assert calls == [("LM Studio", "model", None), ("Ollama", "model", None)]


def test_prepare_provider_dispatch(monkeypatch):
  monkeypatch.setattr(
    launcher,
    "_prepare_lmstudio",
    lambda model, cancel_check=None: ("lm", model, cancel_check),
  )
  monkeypatch.setattr(
    launcher,
    "_prepare_ollama",
    lambda model, cancel_check=None: ("ollama", model, cancel_check),
  )

  assert launcher.prepare_provider("LM Studio", "m") == ("lm", "m", None)
  assert launcher.prepare_provider("unknown", "m") == ("ollama", "m", None)


def test_detection_returns_last_failure(monkeypatch):
  monkeypatch.setattr(
    launcher,
    "prepare_provider",
    lambda name, model, cancel_check=None: launcher.AIProviderStatus(
      name, "url", [], "", False
    ),
  )

  status = launcher.detect_and_start()
  assert status.name == "LM Studio"
  assert status.running is False


def test_detection_rejects_provider_without_active_model(monkeypatch):
  not_loaded = launcher.AIProviderStatus(
    "LM Studio", "http://local", ["model"], "", running=True
  )
  monkeypatch.setattr(launcher, "prepare_provider", lambda *args, **kwargs: not_loaded)
  status = launcher.detect_and_start("LM Studio")
  assert status.running is False
  assert status.active_model == ""


def test_preferred_model_is_downloaded_even_with_installed_fallback(monkeypatch):
  monkeypatch.setattr(launcher, "ollama_start", lambda: True)
  model_lists = iter([["fallback-audio"], ["preferred:latest", "fallback-audio"]])
  monkeypatch.setattr(launcher, "ollama_models", lambda: next(model_lists))
  monkeypatch.setattr(launcher, "ollama_active_model", lambda: "fallback-audio")
  pulled = []
  monkeypatch.setattr(
    launcher,
    "ollama_pull",
    lambda model, cancel_check=None: pulled.append((model, cancel_check)) or True,
  )

  status = launcher._prepare_ollama("preferred")

  assert pulled == [("preferred", None)]
  assert status.active_model == "preferred:latest"


def test_cancel_callback_is_propagated_to_lm_download(monkeypatch):
  monkeypatch.setattr(launcher, "lms_start", lambda: 1234)
  monkeypatch.setattr(launcher, "lms_models", lambda _port: ["fallback-audio"])
  cancelled = lambda: True
  received = []
  monkeypatch.setattr(
    launcher,
    "lms_get",
    lambda model, cancel_check=None: received.append(cancel_check) or False,
  )

  with pytest.raises(InterruptedError):
    launcher._prepare_lmstudio("preferred", cancel_check=cancelled)

  assert received == [cancelled]
