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
  compute_adjacent_transition_metrics,
  compute_transition_recommendations,
  generate_playlist,
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


def test_peak_time_orders_by_energy_not_input_order():
  """Audit-Fix 2026-07-21: Peak-Time muss energiereiche Tracks in die Peak-Zone
  legen und darf NICHT von der Eingabereihenfolge abhaengen."""
  # Gleicher Key/BPM -> nur Energie unterscheidet; Camelot 8A haelt BPM-Gate offen
  energies = [10, 30, 50, 70, 90, 75, 55, 35, 15]
  tracks = [_track(f"t{i}", "8A", e) for i, e in enumerate(energies)]

  ordered = generate_playlist(list(tracks), "Peak-Time", bpm_tolerance=3.0,
                              advanced_params={"peak_position": 70})
  assert len(ordered) == len(tracks)

  # Der energiereichste Track (90) darf nicht am Rand (Start/Ende) stehen,
  # sondern muss in die Peak-Region wandern.
  pos_max = next(i for i, t in enumerate(ordered) if t.energy == 90)
  assert 0 < pos_max < len(ordered) - 1

  # Unabhaengigkeit von der Eingabereihenfolge: umgekehrte Eingabe -> gleiche
  # Energie-Sequenz (bei eindeutigen Energien deterministisch).
  reversed_in = list(reversed(tracks))
  ordered_rev = generate_playlist(reversed_in, "Peak-Time", bpm_tolerance=3.0,
                                  advanced_params={"peak_position": 70})
  assert [t.energy for t in ordered] == [t.energy for t in ordered_rev]


def test_ai_bonus_has_one_bounded_definition():
  metadata = {
    "moods": ["dark", "driving"],
    "sub_genre": "Peak-Time Techno",
    "_provenance": _provenance(),
  }
  first = _track("first", "8A", 40, metadata)
  second = _track("second", "9A", 60, metadata)

  # AUDIT-FIX F05: Der KI-Bonus hat GENAU EINE Definition
  # (calculate_ai_compatibility_bonus) und wird nur EINMAL angewandt — im
  # Overall-Pfad (calculate_enhanced_compatibility), NICHT zusaetzlich in die
  # 0-100-Harmonik-Skala von calculate_compatibility gebacken. Vorher war er
  # doppelt gezaehlt (80 harmonic -> 94), was predict_transition_type
  # verfaelschte. calculate_compatibility liefert jetzt die reine Harmonik.
  assert calculate_ai_compatibility_bonus(first, second) == pytest.approx(0.14)
  assert calculate_compatibility(first, second, 3.0) == 80


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


def test_playlist_quality_uses_the_same_enhanced_transition_contract():
  first = _track("first-quality", "8A", 40)
  second = _track("second-quality", "9A", 60)

  quality = calculate_playlist_quality([first, second], 3.0)
  recommendation = compute_transition_recommendations([first, second], 3.0)[0]

  assert quality["avg_transition_score"] == pytest.approx(
    recommendation.compatibility_score
  )
  assert quality["overall_score"] == pytest.approx(
    recommendation.compatibility_score / 100.0, abs=0.01
  )


def test_recommendation_and_quality_use_identical_display_rounding():
  first = _track("round-a", "8A", 0)
  second = _track("round-b", "12A", 20)

  recommendation = compute_transition_recommendations([first, second], 3.0)[0]
  quality = calculate_playlist_quality([first, second], 3.0)

  assert recommendation.compatibility_score == 78
  assert quality["avg_transition_score"] == 78


def test_precomputed_adjacent_metrics_are_shared_by_consumers():
  tracks = [
    _track("shared-a", "8A", 20),
    _track("shared-b", "9A", 40),
    _track("shared-c", "10A", 60),
  ]
  metrics = compute_adjacent_transition_metrics(tracks, 3.0)

  recommendations = compute_transition_recommendations(
    tracks, 3.0, transition_metrics=metrics
  )
  quality = calculate_playlist_quality(
    tracks, 3.0, transition_metrics=metrics
  )

  assert [item.compatibility_score for item in recommendations] == [
    round(item.overall_score * 100) for item in metrics
  ]
  assert quality["avg_transition_score"] == pytest.approx(
    sum(item.compatibility_score for item in recommendations) / len(recommendations)
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
