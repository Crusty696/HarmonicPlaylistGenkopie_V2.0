"""Tests fuer strukturierten, versionierten KI-Output."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socketserver
import threading
import time
from unittest.mock import Mock

import pytest

from hpg_core.ai_engine import (
  AI_PROMPT_VERSION,
  AI_SCHEMA_VERSION,
  ai_metadata_matches,
  fetch_ai_analysis,
)
from hpg_core.models import Track


def _track(outro_covered=True):
  return Track(
    filePath="C:/Music/example.wav",
    fileName="example.wav",
    artist="Artist",
    title="Title",
    duration=300.0,
    bpm=128.0,
    energy=70,
    detected_genre="Techno",
    outro_covered=outro_covered,
  )


def _response(data):
  response = Mock()
  response.status_code = 200
  response.json.return_value = {
    "model": "test-model",
    "choices": [{"message": {"content": json.dumps(data)}}],
  }
  return response


def _valid_data():
  return {
    "sub_genre": "Peak-Time Techno",
    "moods": ["driving", "dark"],
    "description": "Blend on the outro phrase.",
    "mix_in_time": 32.0,
    "mix_out_time": 260.0,
  }


def test_fetch_ai_analysis_enforces_schema_and_provenance(monkeypatch):
  post = Mock(return_value=_response(_valid_data()))
  monkeypatch.setattr("hpg_core.ai_engine.requests.post", post)

  result = fetch_ai_analysis(
    _track(), provider="Ollama", model="test-model", url="http://local/test"
  )

  assert result["mix_out_time"] == 260.0
  assert result["_provenance"]["model"] == "test-model"
  assert result["_provenance"]["mixpoints_advisory"] is True
  payload = post.call_args.kwargs["json"]
  assert payload["temperature"] == 0
  assert payload["seed"] == 0
  assert payload["response_format"]["type"] == "json_schema"


def test_fetch_ai_analysis_rejects_observed_typo_key(monkeypatch):
  invalid = _valid_data()
  invalid["mix_in_tme"] = invalid.pop("mix_in_time")
  monkeypatch.setattr("hpg_core.ai_engine.requests.post", Mock(return_value=_response(invalid)))

  assert fetch_ai_analysis(_track(), url="http://local/test") == {}


def test_fetch_ai_analysis_verwirft_nur_die_mixpunkte_ohne_tail_coverage(monkeypatch):
  """Ohne analysiertes Track-Ende sind nur die KI-Mixpunkte unzulaessig.

  Bis 2026-08-21 hiess dieser Test `..._rejects_mixout_without_tail_coverage`
  und erwartete `{}`: das GESAMTE Ergebnis wurde verworfen — auch sub_genre
  und moods, die als erklaerende KI-Metadaten erhalten bleiben. Die Mixpunkte
  selbst liest kein Produktivpfad (advisory, siehe
  docs/DATA_AND_VALIDATION_CONTRACT.md). Regel nach Ruecksprache gelockert:
  Mixpunkte None, Rest bleibt.
  """
  monkeypatch.setattr(
    "hpg_core.ai_engine.requests.post",
    Mock(return_value=_response(_valid_data())),
  )

  ergebnis = fetch_ai_analysis(_track(outro_covered=False), url="http://local/test")
  assert ergebnis["sub_genre"]
  assert ergebnis["moods"]
  assert ergebnis["mix_in_time"] is None
  assert ergebnis["mix_out_time"] is None


def test_ai_metadata_cache_requires_exact_provenance():
  track = _track()
  track.ai_metadata = {
    **_valid_data(),
    "_provenance": {
      "provider": "Ollama",
      "model": "test-model",
      "prompt_version": AI_PROMPT_VERSION,
      "schema_version": AI_SCHEMA_VERSION,
      "mixpoints_advisory": True,
    }
  }

  assert ai_metadata_matches(track, "Ollama", "test-model") is True
  assert ai_metadata_matches(track, "Ollama", "other-model") is False


def test_fetch_ai_analysis_rejects_overlong_schema_values(monkeypatch):
  invalid = _valid_data()
  invalid["sub_genre"] = "x" * 101
  monkeypatch.setattr(
    "hpg_core.ai_engine.requests.post", Mock(return_value=_response(invalid))
  )

  assert fetch_ai_analysis(_track(), url="http://local/test") == {}


@pytest.mark.parametrize("invalid_number", [True, "32.0"])
def test_fetch_ai_analysis_rejects_non_json_number_mixpoints(
  monkeypatch, invalid_number
):
  invalid = _valid_data()
  invalid["mix_in_time"] = invalid_number
  monkeypatch.setattr(
    "hpg_core.ai_engine.requests.post", Mock(return_value=_response(invalid))
  )

  assert fetch_ai_analysis(_track(), url="http://local/test") == {}


def test_fetch_ai_analysis_cancel_beendet_blockierenden_http_prozess():
  verbunden = threading.Event()
  getrennt = threading.Event()

  class BlockingHandler(socketserver.BaseRequestHandler):
    def handle(self):
      verbunden.set()
      try:
        while self.request.recv(4096):
          pass
      finally:
        getrennt.set()

  server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), BlockingHandler)
  server.daemon_threads = True
  server_thread = threading.Thread(target=server.serve_forever)
  server_thread.start()
  start = time.monotonic()
  try:
    with pytest.raises(InterruptedError, match="abgebrochen"):
      fetch_ai_analysis(
        _track(),
        url=f"http://127.0.0.1:{server.server_address[1]}/v1/chat/completions",
        cancel_check=lambda: verbunden.is_set(),
      )
    elapsed = time.monotonic() - start
    assert elapsed < 10.0
    assert getrennt.wait(2.0), "Terminierter HTTP-Prozess hielt Socket offen"
  finally:
    server.shutdown()
    server.server_close()
    server_thread.join(2.0)
  assert not server_thread.is_alive()


def test_fetch_ai_analysis_spawn_pfad_behaelt_ergebnisvertrag():
  payloads = []

  class SuccessHandler(BaseHTTPRequestHandler):
    def do_POST(self):
      length = int(self.headers.get("Content-Length", "0"))
      payloads.append(json.loads(self.rfile.read(length)))
      body = json.dumps({
        "model": "test-model",
        "choices": [{"message": {"content": json.dumps(_valid_data())}}],
      }).encode("utf-8")
      self.send_response(200)
      self.send_header("Content-Type", "application/json")
      self.send_header("Content-Length", str(len(body)))
      self.end_headers()
      self.wfile.write(body)

    def log_message(self, _format, *_args):
      pass

  server = ThreadingHTTPServer(("127.0.0.1", 0), SuccessHandler)
  server_thread = threading.Thread(target=server.serve_forever)
  server_thread.start()
  try:
    result = fetch_ai_analysis(
      _track(),
      provider="Ollama",
      model="test-model",
      url=f"http://127.0.0.1:{server.server_address[1]}/v1/chat/completions",
      cancel_check=lambda: False,
    )
  finally:
    server.shutdown()
    server.server_close()
    server_thread.join(2.0)

  assert not server_thread.is_alive()
  assert result["mix_out_time"] == 260.0
  assert result["_provenance"]["model"] == "test-model"
  assert payloads[0]["response_format"]["type"] == "json_schema"
