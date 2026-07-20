"""Golden Tests fuer die gemeinsame Transition-Zielfunktion."""

import pytest

from hpg_core.models import Track
from hpg_core.playlist import (
  calculate_ai_compatibility_bonus,
  calculate_compatibility,
  calculate_enhanced_compatibility,
  calculate_transition_objective,
)


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
  }
  first = _track("first", "8A", 40, metadata)
  second = _track("second", "9A", 60, metadata)

  assert calculate_ai_compatibility_bonus(first, second) == pytest.approx(0.14)
  assert calculate_compatibility(first, second, 3.0) == 94


def test_optimizer_score_is_exactly_the_displayed_enhanced_score():
  metadata = {"moods": ["dark", "driving"], "sub_genre": "Techno"}
  first = _track("first", "8A", 40, metadata)
  second = _track("second", "9A", 60, metadata)

  metrics = calculate_enhanced_compatibility(first, second, 3.0)

  assert metrics.ai_bonus == pytest.approx(0.14)
  assert calculate_transition_objective(first, second, 3.0) == round(
    metrics.overall_score * 100
  )
