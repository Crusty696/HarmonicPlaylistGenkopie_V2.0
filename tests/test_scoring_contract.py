"""Golden Tests fuer die gemeinsame Transition-Zielfunktion."""

import pytest

from hpg_core.ai_engine import AI_PROMPT_VERSION, AI_SCHEMA_VERSION
from hpg_core.models import Track
from hpg_core.playlist import (
  calculate_ai_compatibility_bonus,
  calculate_compatibility,
  calculate_enhanced_compatibility,
  calculate_playlist_quality,
  calculate_transition_objective,
  compute_transition_recommendations,
  resolve_scoring_context,
)


def _provenance():
  """Gueltige Provenienz nach aktuellem KI-Vertrag (HPG-002)."""
  return {
    "provider": "LM Studio",
    "model": "test-model",
    "prompt_version": AI_PROMPT_VERSION,
    "schema_version": AI_SCHEMA_VERSION,
  }


def _track(name, camelot, energy, ai_metadata=None):
  return Track(
    filePath=f"C:/{name}.wav",
    fileName=f"{name}.wav",
    bpm=128.0,
    camelotCode=camelot,
    energy=energy,
    ai_metadata=ai_metadata or {},
  )


def test_ai_bonus_has_one_bounded_definition():
  metadata = {
    "moods": ["dark", "driving"],
    "sub_genre": "Peak-Time Techno",
    "_provenance": _provenance(),
  }
  first = _track("first", "8A", 40, metadata)
  second = _track("second", "9A", 60, metadata)

  assert calculate_ai_compatibility_bonus(first, second) == pytest.approx(0.14)
  assert calculate_compatibility(first, second, 3.0) == 94


def test_ai_bonus_requires_valid_provenance():
  """HPG-002-Regression: beliebige/stale ai_metadata darf Score NICHT heben."""
  no_provenance = {"moods": ["dark", "driving"], "sub_genre": "Techno"}
  stale = {
    "moods": ["dark", "driving"],
    "sub_genre": "Techno",
    "_provenance": {**_provenance(), "prompt_version": "2000-01-01"},
  }
  clean_a = _track("a", "8A", 40)
  clean_b = _track("b", "9A", 60)

  for bad_meta in (no_provenance, stale):
    first = _track("first", "8A", 40, dict(bad_meta))
    second = _track("second", "9A", 60, dict(bad_meta))
    assert calculate_ai_compatibility_bonus(first, second) == 0.0
    # Score identisch zu Tracks ganz ohne ai_metadata
    assert calculate_compatibility(first, second, 3.0) == calculate_compatibility(
      clean_a, clean_b, 3.0
    )


def test_optimizer_score_is_exactly_the_displayed_enhanced_score():
  metadata = {
    "moods": ["dark", "driving"],
    "sub_genre": "Techno",
    "_provenance": _provenance(),
  }
  first = _track("first", "8A", 40, metadata)
  second = _track("second", "9A", 60, metadata)

  metrics = calculate_enhanced_compatibility(first, second, 3.0)

  assert metrics.ai_bonus == pytest.approx(0.14)
  assert calculate_transition_objective(first, second, 3.0) == round(
    metrics.overall_score * 100
  )


# --- HPG-001: Scoring-Kontext ist durchgaengig ---------------------------


def test_resolve_scoring_context_only_for_strictness_strategies():
  """Nur Strategien, die harmonic_strictness beim Sortieren nutzen, liefern
  einen nicht-leeren Kontext — sonst bewerten Sort und Anzeige mit Defaults."""
  ctx_strict = resolve_scoring_context(
    "Harmonic Flow", {"harmonic_strictness": 10, "allow_experimental": False}
  )
  assert ctx_strict == {"harmonic_strictness": 10, "allow_experimental": False}

  # Warm-Up nutzt keine Scoring-Parameter -> leerer Kontext
  assert resolve_scoring_context("Warm-Up", {"harmonic_strictness": 10}) == {}

  # Alte Strategie-Namen werden aufgeloest
  assert "harmonic_strictness" in resolve_scoring_context(
    "Harmonic Flow Enhanced", {"harmonic_strictness": 3}
  )


def test_quality_and_recommendations_honor_scoring_context():
  """HPG-001-Regression: derselbe diagonale Uebergang wird unter strengem
  Kontext niedriger bewertet — in Quality UND Empfehlungen, nicht nur im Sort."""
  # 8A -> 12A (Plus-Four, experimentell) reagiert auf strictness
  a = _track("a", "8A", 50)
  b = _track("b", "12A", 55)
  playlist = [a, b]

  loose = {"harmonic_strictness": 1, "allow_experimental": True}
  strict = {"harmonic_strictness": 10, "allow_experimental": True}

  q_loose = calculate_playlist_quality(playlist, 3.0, loose)["harmonic_flow"]
  q_strict = calculate_playlist_quality(playlist, 3.0, strict)["harmonic_flow"]
  assert q_loose > q_strict

  rec_loose = compute_transition_recommendations(
    playlist, 3.0, scoring_context=loose
  )[0].compatibility_score
  rec_strict = compute_transition_recommendations(
    playlist, 3.0, scoring_context=strict
  )[0].compatibility_score
  assert rec_loose > rec_strict

  # Ohne Kontext == Default (strictness 7): liegt zwischen den Extremen
  rec_default = compute_transition_recommendations(playlist, 3.0)[0].compatibility_score
  assert rec_strict <= rec_default <= rec_loose
