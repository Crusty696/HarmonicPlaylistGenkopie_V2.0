"""
Tests fuer Transition Recommendations.
Prueft ob Uebergangsempfehlungen DJ-taugliche Werte liefern.
"""
from types import SimpleNamespace

import pytest

from hpg_core.playlist import (
  _clamp_transition_overlap,
  _outro_overlap_limit,
  compute_set_timeline,
  compute_transition_recommendations,
)
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

    # Die Blende laeuft vorwaerts ab dem Mix-Out (Renderer:
    # transition_renderer.py:159-160/:322-324) — der Mix-Out ist also ihr
    # START. Bis 2026-08-21 stand hier fade_out_end; das hielt die
    # Rueckwaerts-Konvention aus playlist.py fest, die dem Renderer
    # widersprach und in der GUI eine Blende zeigte, die vor dem Mix-Out
    # endete.
    assert spec.mix_out_sec == rec.plan.mix_out_a == rec.fade_out_start
    assert rec.fade_out_end == pytest.approx(
        min(rec.fade_out_start + rec.overlap, rec.from_track.duration)
    )
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
      lambda *_: (oversized, [], 120.0),
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
    # Der interne Timing-Vertrag bleibt ungerundet; gerundet wird erst in
    # Anzeige-/Exportpfaden.
    assert rec.fade_out_start == rec.dj_rec.adjusted_mix_out_a
    assert rec.mix_entry == rec.dj_rec.adjusted_mix_in_b


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


class TestOverlapWindowClamp:
  """Regression: der Overlap darf am realen Sections-Layout nicht kollabieren.

  Audit 2026-08-14: die B-Seite von _clamp_transition_overlap begrenzte auf
  ``intro_end_B - mix_in_b``. dj_brain garantiert per Design
  ``mix_in_b >= intro_end_B`` (tests/test_dj_brain.py), der Term war also
  immer <= 0. An 52 echten Tracks wurden dadurch 50 von 51 Uebergaengen auf
  overlap=0.0 geklemmt — der Renderer bekam ueberall harte Schnitte.
  Die bisherigen Overlap-Tests liefen ueber _make_pair() OHNE sections und
  haben den Zweig nie erreicht.
  """

  def _pair_with_sections(self, intro_end=60.0, duration=420.0):
    """Track-Paar im realen Layout: Mix-In liegt am Intro-Ende."""
    return [
      make_track(
        camelotCode="8A", bpm=138.0, duration=duration, energy=70,
        mix_in_point=intro_end, mix_out_point=duration - 60.0,
        sections=_sections(intro_end=intro_end, duration=duration),
      ),
      make_track(
        camelotCode="8A", bpm=138.0, duration=duration, energy=72,
        mix_in_point=intro_end, mix_out_point=duration - 60.0,
        sections=_sections(intro_end=intro_end, duration=duration),
      ),
    ]

  def test_overlap_survives_sections(self):
    """Mit sections + Mix-In am Intro-Ende bleibt der Overlap nutzbar."""
    rec = compute_transition_recommendations(
      self._pair_with_sections(), bpm_tolerance=3.0, default_overlap=16.0
    )[0]
    assert rec.overlap > 0.0, "Overlap auf 0 geklemmt (Intro-Fenster-Bug)"
    assert rec.plan.overlap == rec.overlap

  def test_overlap_survives_mix_in_after_intro(self):
    """Auch wenn der Mix-In HINTER dem Intro-Ende liegt, bleibt Overlap > 0."""
    tracks = self._pair_with_sections(intro_end=60.0)
    tracks[1].mix_in_point = 115.0  # deutlich hinter intro_end
    rec = compute_transition_recommendations(
      tracks, bpm_tolerance=3.0, default_overlap=16.0
    )[0]
    assert rec.overlap > 0.0

  def test_overlap_limited_by_remaining_audio(self):
    """Der Overlap bleibt im real vorhandenen Audio beider Tracks."""
    tracks = self._pair_with_sections(duration=420.0)
    rec = compute_transition_recommendations(
      tracks, bpm_tolerance=3.0, default_overlap=64.0
    )[0]
    a_rest = rec.from_track.duration - rec.plan.mix_out_a
    b_rest = rec.to_track.duration - rec.plan.mix_in_b
    assert rec.overlap <= a_rest + 1e-6, "Overlap laeuft hinter das Ende von A"
    assert rec.overlap <= b_rest + 1e-6, "Overlap laeuft hinter das Ende von B"

  def test_short_incoming_track_limits_overlap(self):
    """Ein kurzer B-Track begrenzt den Overlap wirklich."""
    tracks = self._pair_with_sections()
    tracks[1].duration = 70.0
    tracks[1].mix_in_point = 60.0
    tracks[1].sections = _sections(intro_end=60.0, outro_start=65.0, duration=70.0)
    rec = compute_transition_recommendations(
      tracks, bpm_tolerance=3.0, default_overlap=64.0
    )[0]
    assert rec.overlap <= 10.0 + 1e-6, f"Overlap {rec.overlap}s > Restdauer von B"


# ---------------------------------------------------------------------------
# Outro-Grenze der Blende (2026-08-21)
#
# Anlass, gemessen an 160 gerenderten Uebergaengen: die Blende lief bei 109
# davon in das Outro von Track A, im Median 17.3 s. Der Mix-Out selbst liegt
# per dj_brain-Guard immer VOR dem Outro — die Blende laeuft aber vorwaerts
# ab diesem Punkt darueber hinaus.
# ---------------------------------------------------------------------------

class TestOutroOverlapLimit:

  def _track(self, bpm=120.0, duration=420.0, outro_start=360.0, sections=True):
    return make_track(
      camelotCode="8A", bpm=bpm, duration=duration, energy=70,
      mix_in_point=60.0, mix_out_point=outro_start - 60.0,
      sections=_sections(outro_start=outro_start, duration=duration) if sections else [],
    )

  def test_blende_endet_spaetestens_am_outro(self):
    """Kernaussage: Mix-Out + Blende laeuft nicht ueber den Outro-Beginn."""
    track = self._track(bpm=120.0, outro_start=360.0)
    mix_out = 300.0                      # 60 s Kopfraum = 30 Takte bei 120 BPM
    grenze = _outro_overlap_limit(track, mix_out)
    assert grenze is not None
    assert mix_out + grenze <= 360.0 + 1e-9

  def test_grenze_liegt_auf_ganzen_takten(self):
    """Ganze Takte, nicht ganze Phrasen — sonst kollabiert die Streuung."""
    track = self._track(bpm=120.0, outro_start=360.0)
    sekunden_pro_takt = (60.0 / 120.0) * 4          # 2.0 s
    grenze = _outro_overlap_limit(track, 301.0)     # 59 s Kopfraum
    # 29 volle Takte. Auf Phrasen gerundet (8 Takte = 16 s bei 120 BPM) waeren
    # es 48.0 — genau die Vergroeberung, die die Streuung wieder wegwirft.
    assert grenze == pytest.approx(58.0)
    assert (grenze / sekunden_pro_takt) % 1 == pytest.approx(0.0)

  def test_kurzer_kopfraum_wird_nicht_gekuerzt(self):
    """Unter 8 Takten lieber ins Outro laufen als harter Schnitt."""
    track = self._track(bpm=120.0, outro_start=360.0)
    # 10 s Kopfraum = 5 Takte, unter MIN_TRANSITION_BARS
    assert _outro_overlap_limit(track, 350.0) is None

  def test_ohne_erkanntes_outro_keine_grenze(self):
    track = self._track(sections=False)
    assert _outro_overlap_limit(track, 100.0) is None

  def test_unbrauchbare_werte_ergeben_keine_grenze(self):
    assert _outro_overlap_limit(self._track(bpm=0.0), 100.0) is None
    assert _outro_overlap_limit(self._track(duration=0.0), 100.0) is None

  def test_klemme_wendet_die_outro_grenze_an(self):
    a = self._track(bpm=120.0, duration=420.0, outro_start=360.0)
    b = self._track(bpm=120.0, duration=420.0, outro_start=360.0)
    gekuerzt = _clamp_transition_overlap(64.0, a, b, 320.0, 60.0)
    assert gekuerzt == pytest.approx(40.0)   # 40 s Kopfraum, 20 volle Takte

  def test_klemme_ohne_fenster_ignoriert_die_outro_grenze(self):
    """limit_to_windows=False ist der Pfad ohne Fensterlogik — dort gilt nur der Deckel."""
    a = self._track(bpm=120.0, outro_start=360.0)
    b = self._track(bpm=120.0, outro_start=360.0)
    assert _clamp_transition_overlap(
      64.0, a, b, 320.0, 60.0, limit_to_windows=False
    ) == pytest.approx(64.0)
