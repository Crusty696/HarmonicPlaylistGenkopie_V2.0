"""
Tests fuer Transition Recommendations.
Prueft ob Uebergangsempfehlungen DJ-taugliche Werte liefern.
"""
from types import SimpleNamespace

from hpg_core.playlist import compute_set_timeline, compute_transition_recommendations
from hpg_core.transition_renderer import TransitionClipSpec
from tests.fixtures.track_factories import make_track


def _sections(intro_end=60.0, outro_start=360.0, duration=420.0):
  return [
    {"label": "intro", "start_time": 0.0, "end_time": intro_end, "avg_energy": 20.0},
    {"label": "build", "start_time": intro_end, "end_time": 90.0, "avg_energy": 55.0},
    {"label": "drop", "start_time": 90.0, "end_time": outro_start, "avg_energy": 85.0},
    {"label": "outro", "start_time": outro_start, "end_time": duration, "avg_energy": 20.0},
  ]


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
    assert rec.plan is not None

  def test_plan_is_the_single_timing_contract(self):
    pair = _make_pair(duration=420.0)
    rec = compute_transition_recommendations(pair, default_overlap=16.0)[0]
    spec = TransitionClipSpec.from_plan(rec.plan, rec.from_track, rec.to_track)
    timeline = compute_set_timeline(pair, transition_plans=[rec.plan])

    assert spec.mix_out_sec == rec.plan.mix_out_a == rec.fade_out_end
    assert spec.mix_in_sec == rec.plan.mix_in_b == rec.mix_entry
    assert spec.crossfade_sec == rec.plan.overlap == rec.overlap
    assert rec.plan.crossfade_frames == round(rec.plan.overlap * rec.plan.target_sr)
    assert timeline.entries[0].overlap_with_next == rec.plan.overlap

  def test_plan_and_renderer_share_overlap_limit(self, monkeypatch):
    pair = _make_pair(duration=420.0)
    oversized = SimpleNamespace(
      adjusted_mix_out_a=360.0,
      adjusted_mix_in_b=16.0,
      overlap_seconds=120.0,
    )
    monkeypatch.setattr(
      "hpg_core.playlist._process_dj_brain_recommendations",
      lambda *_: (oversized, [], 120.0, 240.0),
    )

    rec = compute_transition_recommendations(pair)[0]
    spec = TransitionClipSpec.from_plan(rec.plan, rec.from_track, rec.to_track)

    assert rec.overlap == rec.plan.overlap == spec.crossfade_sec == 64.0

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

  def test_dj_brain_adjusted_mix_points_are_applied(self):
    """TransitionRecommendation nutzt paarspezifische DJ-Brain Mixpunkte."""
    current = make_track(
      camelotCode="8A", bpm=143.0, duration=420.0, energy=75,
      detected_genre="Psytrance", mix_in_point=60.0, mix_out_point=360.0,
      sections=_sections(),
    )
    upcoming = make_track(
      camelotCode="8A", bpm=143.0, duration=420.0, energy=78,
      detected_genre="Psytrance", mix_in_point=0.0, mix_out_point=360.0,
      sections=_sections(),
    )

    rec = compute_transition_recommendations([current, upcoming], bpm_tolerance=3.0)[0]

    assert rec.dj_rec is not None
    assert rec.fade_out_end == round(rec.dj_rec.adjusted_mix_out_a, 2)
    assert rec.mix_entry == round(rec.dj_rec.adjusted_mix_in_b, 2)


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
