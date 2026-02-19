"""
Tests fuer Transition Recommendations.
Prueft ob Uebergangsempfehlungen DJ-taugliche Werte liefern.
"""
import pytest
from hpg_core.playlist import compute_transition_recommendations
from tests.fixtures.track_factories import make_track


def _make_pair(code1="8A", code2="9A", bpm=128.0, duration=300.0):
  """Erstellt ein kompatibles Track-Paar."""
  return [
    make_track(
      camelotCode=code1, bpm=bpm, duration=duration,
      mix_in_point=30.0, mix_out_point=duration - 30.0, energy=70,
    ),
    make_track(
      camelotCode=code2, bpm=bpm, duration=duration,
      mix_in_point=30.0, mix_out_point=duration - 30.0, energy=72,
    ),
  ]


class TestRecommendationBasics:
  """Grundlegende Eigenschaften."""

  def test_empty_playlist(self):
    """Leere Playlist = keine Empfehlungen."""
    assert compute_transition_recommendations([]) == []

  def test_single_track(self):
    """1 Track = keine Empfehlungen."""
    tracks = [make_track(camelotCode="8A", bpm=128.0)]
    assert compute_transition_recommendations(tracks) == []

  def test_two_tracks_one_rec(self):
    """2 Tracks = 1 Empfehlung."""
    recs = compute_transition_recommendations(_make_pair())
    assert len(recs) == 1

  def test_n_tracks_n_minus_1_recs(self):
    """N Tracks = N-1 Empfehlungen."""
    tracks = [
      make_track(camelotCode=f"{i}A", bpm=128.0, duration=300.0,
                 mix_in_point=30.0, mix_out_point=270.0, energy=70)
      for i in range(1, 7)
    ]
    recs = compute_transition_recommendations(tracks)
    assert len(recs) == 5


class TestRecommendationFields:
  """Felder der TransitionRecommendation."""

  def test_has_all_fields(self):
    """Empfehlung hat alle erforderlichen Felder."""
    recs = compute_transition_recommendations(_make_pair())
    rec = recs[0]
    assert hasattr(rec, "index")
    assert hasattr(rec, "from_track")
    assert hasattr(rec, "to_track")
    assert hasattr(rec, "fade_out_start")
    assert hasattr(rec, "fade_out_end")
    assert hasattr(rec, "fade_in_start")
    assert hasattr(rec, "overlap")
    assert hasattr(rec, "bpm_delta")
    assert hasattr(rec, "energy_delta")
    assert hasattr(rec, "compatibility_score")
    assert hasattr(rec, "risk_level")
    assert hasattr(rec, "notes")

  def test_index_is_zero_based(self):
    """Index ist 0-basiert."""
    recs = compute_transition_recommendations(_make_pair())
    assert recs[0].index == 0

  def test_from_to_tracks_correct(self):
    """from_track und to_track sind korrekt zugewiesen."""
    pair = _make_pair()
    recs = compute_transition_recommendations(pair)
    assert recs[0].from_track == pair[0]
    assert recs[0].to_track == pair[1]


class TestTimingValues:
  """Timing-Werte der Empfehlungen."""

  def test_overlap_positive(self):
    """Overlap muss positiv sein."""
    recs = compute_transition_recommendations(_make_pair())
    assert recs[0].overlap > 0

  def test_fade_out_start_not_negative(self):
    """Fade-Out Start >= 0."""
    recs = compute_transition_recommendations(_make_pair())
    assert recs[0].fade_out_start >= 0

  def test_fade_out_end_after_start(self):
    """Fade-Out Ende nach Start."""
    recs = compute_transition_recommendations(_make_pair())
    assert recs[0].fade_out_end >= recs[0].fade_out_start

  def test_overlap_realistic_range(self):
    """Overlap im realistischen Bereich (2-120s)."""
    recs = compute_transition_recommendations(_make_pair())
    assert 2.0 <= recs[0].overlap <= 120.0, (
      f"Overlap {recs[0].overlap}s nicht realistisch"
    )


class TestCompatibilityScore:
  """Kompatibilitaets-Score in Empfehlungen."""

  def test_compatible_tracks_high_score(self):
    """Kompatible Tracks (8A->8A) = hoher Score."""
    pair = _make_pair("8A", "8A")
    recs = compute_transition_recommendations(pair)
    assert recs[0].compatibility_score >= 80, (
      f"Same Key Score {recs[0].compatibility_score} (erwartet >=80)"
    )

  def test_score_is_integer(self):
    """Score ist Integer (0-100)."""
    recs = compute_transition_recommendations(_make_pair())
    assert isinstance(recs[0].compatibility_score, int)


class TestRiskLevel:
  """Risk Level der Empfehlungen."""

  def test_risk_level_is_string(self):
    """Risk Level ist ein String."""
    recs = compute_transition_recommendations(_make_pair())
    assert isinstance(recs[0].risk_level, str)

  def test_same_key_same_bpm_low_risk(self):
    """Gleicher Key, gleicher BPM = low Risk."""
    pair = _make_pair("8A", "8A", bpm=128.0)
    recs = compute_transition_recommendations(pair)
    assert recs[0].risk_level in ("low", "medium"), (
      f"Same Key/BPM Risk '{recs[0].risk_level}'"
    )


class TestNotes:
  """Notes-Feld der Empfehlungen."""

  def test_notes_is_string(self):
    """Notes ist ein String."""
    recs = compute_transition_recommendations(_make_pair())
    assert isinstance(recs[0].notes, str)

  def test_notes_not_empty(self):
    """Notes ist nicht leer."""
    recs = compute_transition_recommendations(_make_pair())
    assert len(recs[0].notes) > 0

  def test_compatible_tracks_mention_harmonic(self):
    """Kompatible Tracks erwaehnen Tonart-Info."""
    pair = _make_pair("8A", "8A")
    recs = compute_transition_recommendations(pair)
    notes_lower = recs[0].notes.lower()
    assert any(kw in notes_lower for kw in ("tonart", "harmoni", "safe", "kompatibel", "perfekte")), (
      f"Notes enthalten keine Tonart-Info: '{recs[0].notes}'"
    )
