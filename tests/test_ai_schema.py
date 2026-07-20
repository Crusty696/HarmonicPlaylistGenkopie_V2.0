"""Tests fuer strukturierten, versionierten KI-Output."""

import json
from unittest.mock import Mock

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


def test_fetch_ai_analysis_rejects_mixout_without_tail_coverage(monkeypatch):
  monkeypatch.setattr(
    "hpg_core.ai_engine.requests.post",
    Mock(return_value=_response(_valid_data())),
  )

  assert fetch_ai_analysis(_track(outro_covered=False), url="http://local/test") == {}


def test_ai_metadata_cache_requires_exact_provenance():
  track = _track()
  track.ai_metadata = {
    "_provenance": {
      "provider": "Ollama",
      "model": "test-model",
      "prompt_version": AI_PROMPT_VERSION,
      "schema_version": AI_SCHEMA_VERSION,
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
