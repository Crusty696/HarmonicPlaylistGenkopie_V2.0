"""
Tests fuer Set-Timing / Time-based Planning.
Prueft Timeline-Berechnung, Peak-Erkennung und Energy-Phasen.
"""
import pytest
from hpg_core.playlist import (
  compute_set_timeline,
  get_set_timing_summary,
  SetTimeline,
  SetTimelineEntry,
  TransitionPlan,
)
from hpg_core.models import Track


# === Hilfsfunktionen ===

def _make_track(
    title: str = "Test",
    bpm: float = 128.0,
    camelot: str = "8A",
    energy: int = 50,
    duration: float = 300.0,
    mix_out_point: float = -1.0,
    mix_in_point: float = -1.0,
    genre: str = "Unknown",
) -> Track:
  """Erstellt einen Track fuer Set-Timing Tests."""
  return Track(
    filePath="test.mp3",
    fileName="test.mp3",
    title=title,
    bpm=bpm,
    camelotCode=camelot,
    energy=energy,
    duration=duration,
    mix_out_point=mix_out_point,
    mix_in_point=mix_in_point,
    detected_genre=genre,
  )


def _plan(mix_out: float, mix_in: float, overlap: float) -> TransitionPlan:
  return TransitionPlan(
    mix_out_a=mix_out,
    mix_in_b=mix_in,
    fade_out_start=mix_out,
    fade_out_end=mix_out + overlap,
    overlap=overlap,
    transition_type="blend",
  )


# === compute_set_timeline Tests ===

class TestComputeSetTimeline:
  """Tests fuer die Set-Timeline-Berechnung."""

  def test_empty_tracks_returns_empty_timeline(self):
    tl = compute_set_timeline([])
    assert tl.total_duration_minutes == 0.0
    assert tl.entries == []
    assert tl.overflow_minutes == 0.0

  def test_empty_tracks_keeps_target(self):
    tl = compute_set_timeline([], target_minutes=90.0)
    assert tl.target_duration_minutes == 90.0

  def test_single_track_no_overlap(self):
    """Ein einzelner Track hat keinen Overlap (letzter Track)."""
    t = _make_track(title="Solo", duration=300.0)
    tl = compute_set_timeline([t], target_minutes=5.0)
    assert len(tl.entries) == 1
    entry = tl.entries[0]
    assert entry.overlap_with_next == 0.0
    assert entry.start_time == 0.0
    assert entry.playing_duration == 300.0

  def test_single_track_is_peak(self):
    """Einziger Track muss Peak sein."""
    t = _make_track(title="Solo", energy=80)
    tl = compute_set_timeline([t])
    assert tl.entries[0].is_peak is True

  def test_single_track_phase_is_peak(self):
    """Einziger Track bekommt Phase 'peak' (weil er Peak ist)."""
    t = _make_track(title="Solo")
    tl = compute_set_timeline([t])
    # Einziger Track ist immer Peak → Phase "peak"
    assert tl.entries[0].energy_phase == "peak"

  def test_two_tracks_overlap_calculation(self):
    """Ohne Plan entsteht keine erfundene Blende."""
    t1 = _make_track(title="T1", duration=300.0)
    t2 = _make_track(title="T2", duration=300.0)
    tl = compute_set_timeline([t1, t2])
    assert tl.entries[0].overlap_with_next == 0.0
    assert tl.entries[0].transition_planned is False
    assert tl.entries[1].overlap_with_next == 0.0
    assert tl.entries[1].transition_planned is None

  def test_timeline_continuity(self):
    """Start von Entry[i+1] == Ende von Entry[i] minus Overlap.

    Konvention seit dem Blenden-Fix (1ebaa96): die Blende beginnt am Mix-Out
    von A und laeuft vorwaerts; B startet an seinem Mix-In, waehrend A noch
    overlap Sekunden hoerbar ist. Deshalb ueberlappen sich die Eintraege um
    genau overlap_with_next — vorher stand hier "Ende == Start", weil der
    Overlap am Track-ENDE abgezogen wurde."""
    tracks = [_make_track(title=f"T{i}", duration=240.0) for i in range(5)]
    tl = compute_set_timeline(tracks)
    for i in range(len(tl.entries) - 1):
      assert tl.entries[i + 1].start_time == pytest.approx(
        tl.entries[i].end_time - tl.entries[i].overlap_with_next, abs=0.01
      )

  def test_total_duration_matches_last_end(self):
    """Gesamtdauer == Ende des letzten Tracks (in Minuten)."""
    tracks = [_make_track(title=f"T{i}", duration=180.0) for i in range(4)]
    tl = compute_set_timeline(tracks)
    last_end = tl.entries[-1].end_time
    assert tl.total_duration_minutes == pytest.approx(last_end / 60.0, abs=0.01)

  def test_overflow_positive_when_too_long(self):
    """Overflow > 0 wenn Set laenger als Ziel."""
    # 5 Tracks a 300s = viel mehr als 5 Minuten
    tracks = [_make_track(title=f"T{i}", duration=300.0) for i in range(5)]
    tl = compute_set_timeline(tracks, target_minutes=5.0)
    assert tl.overflow_minutes > 0

  def test_overflow_negative_when_too_short(self):
    """Overflow < 0 wenn Set kuerzer als Ziel."""
    t = _make_track(title="Short", duration=60.0)
    tl = compute_set_timeline([t], target_minutes=60.0)
    assert tl.overflow_minutes < 0

  def test_returns_set_timeline_type(self):
    t = _make_track()
    tl = compute_set_timeline([t])
    assert isinstance(tl, SetTimeline)

  def test_entries_are_set_timeline_entry(self):
    t = _make_track()
    tl = compute_set_timeline([t])
    assert isinstance(tl.entries[0], SetTimelineEntry)

  def test_zero_duration_is_rejected(self):
    """Tracks mit 0s Duration sind kein gueltiger Timeline-Vertrag."""
    t = _make_track(title="ZeroDur", duration=0.0)
    with pytest.raises(ValueError, match="Dauer muss endlich und positiv"):
      compute_set_timeline([t])

  def test_negative_duration_is_rejected(self):
    """Negative Duration wird nicht still geklemmt."""
    t = _make_track(title="Neg", duration=-10.0)
    with pytest.raises(ValueError, match="Dauer muss endlich und positiv"):
      compute_set_timeline([t])

  def test_custom_target_minutes(self):
    tracks = [_make_track(duration=180.0) for _ in range(3)]
    tl = compute_set_timeline(tracks, target_minutes=90.0)
    assert tl.target_duration_minutes == 90.0


# === Peak-Erkennung Tests ===

class TestPeakIdentification:
  """Tests fuer die Peak-Track-Erkennung."""

  def test_exactly_one_peak(self):
    """Genau ein Track wird als Peak markiert."""
    tracks = [_make_track(title=f"T{i}", energy=50) for i in range(8)]
    tl = compute_set_timeline(tracks)
    peaks = [e for e in tl.entries if e.is_peak]
    assert len(peaks) == 1

  def test_highest_energy_near_peak_wins(self):
    """Track mit hoher Energie nahe Peak-Position gewinnt."""
    tracks = [
      _make_track(title="Intro", energy=30, duration=240.0),
      _make_track(title="Build1", energy=50, duration=240.0),
      _make_track(title="Build2", energy=60, duration=240.0),
      _make_track(title="Peak", energy=95, duration=240.0),
      _make_track(title="Sustain", energy=70, duration=240.0),
      _make_track(title="Cool", energy=40, duration=240.0),
    ]
    tl = compute_set_timeline(tracks, peak_position_pct=0.65)
    peak_entry = next(e for e in tl.entries if e.is_peak)
    # Peak-Track sollte der mit Energie 95 sein
    assert peak_entry.track.title == "Peak"

  def test_energy_beats_position(self):
    """Bei gleicher Position gewinnt hoehere Energie."""
    tracks = [
      _make_track(title="Low", energy=20, duration=200.0),
      _make_track(title="High", energy=100, duration=200.0),
      _make_track(title="Med", energy=50, duration=200.0),
    ]
    tl = compute_set_timeline(tracks)
    peak = next(e for e in tl.entries if e.is_peak)
    assert peak.track.title == "High"

  def test_peak_position_in_timeline(self):
    """Peak-Position in Minuten wird korrekt berechnet."""
    tracks = [
      _make_track(title=f"T{i}", duration=240.0, energy=40 + i * 10)
      for i in range(5)
    ]
    tl = compute_set_timeline(tracks)
    assert tl.peak_position_minutes >= 0.0

  def test_peak_position_pct_clamped(self):
    """Peak-Position wird auf 0.1-0.9 begrenzt."""
    t = _make_track(duration=300.0)
    tl1 = compute_set_timeline([t], peak_position_pct=0.0)
    tl2 = compute_set_timeline([t], peak_position_pct=1.5)
    # Keine Fehler, Timeline wurde erstellt
    assert len(tl1.entries) == 1
    assert len(tl2.entries) == 1


# === Energy-Phasen Tests ===

class TestEnergyPhases:
  """Tests fuer die Energy-Phasen-Zuweisung."""

  def test_first_track_is_intro_when_not_peak(self):
    """Erster Track ist 'intro' wenn er nicht Peak ist."""
    tracks = [
      _make_track(title="Intro", energy=20, duration=240.0),
      _make_track(title="Mid", energy=50, duration=240.0),
      _make_track(title="Peak", energy=90, duration=240.0),
      _make_track(title="Cool", energy=30, duration=240.0),
    ]
    tl = compute_set_timeline(tracks)
    assert tl.entries[0].energy_phase == "intro"

  def test_last_track_is_cooldown_when_not_peak(self):
    """Letzter Track ist 'cooldown' wenn er nicht Peak ist."""
    tracks = [
      _make_track(title="Intro", energy=20, duration=240.0),
      _make_track(title="Peak", energy=90, duration=240.0),
      _make_track(title="Sustain", energy=60, duration=240.0),
      _make_track(title="Cool", energy=25, duration=240.0),
    ]
    tl = compute_set_timeline(tracks)
    assert tl.entries[-1].energy_phase == "cooldown"

  def test_multiple_phases_in_long_set(self):
    """In einem langen Set mit klarem Verlauf gibt es mehrere Phasen."""
    # Klar definierter Energie-Verlauf: rauf, Peak in der Mitte, runter
    energies = [20, 30, 40, 55, 70, 90, 75, 55, 35, 20]
    tracks = [
      _make_track(title=f"T{i}", energy=energies[i], duration=240.0)
      for i in range(10)
    ]
    tl = compute_set_timeline(tracks, peak_position_pct=0.55)
    phases = {e.energy_phase for e in tl.entries}
    # Mindestens 3 verschiedene Phasen
    assert len(phases) >= 3, f"Nur {phases} gefunden"
    assert "peak" in phases

  def test_two_tracks_phases(self):
    """Zwei Tracks: Peak hat 'peak' Phase, anderer hat andere Phase."""
    t1 = _make_track(title="T1", energy=50)
    t2 = _make_track(title="T2", energy=60)
    tl = compute_set_timeline([t1, t2])
    phases = {e.energy_phase for e in tl.entries}
    # Einer muss Peak sein
    assert "peak" in phases
    # Beide muessen gueltige Phasen haben
    valid = {"intro", "warmup", "build", "peak", "sustain", "cooldown"}
    for entry in tl.entries:
      assert entry.energy_phase in valid

  def test_valid_phase_names(self):
    """Alle Phasen haben gueltige Namen."""
    valid = {"intro", "warmup", "build", "peak", "sustain", "cooldown"}
    tracks = [_make_track(title=f"T{i}", energy=30+i*5) for i in range(12)]
    tl = compute_set_timeline(tracks)
    for entry in tl.entries:
      assert entry.energy_phase in valid, f"Invalid phase: {entry.energy_phase}"

  def test_peak_phase_exists_in_mid_set(self):
    """Peak-Phase existiert im mittleren Bereich eines Sets."""
    # Peak muss klar im mittleren Bereich liegen (nicht am Rand)
    energies = [30, 40, 50, 70, 95, 80, 60, 35, 25, 20]
    tracks = [
      _make_track(title=f"T{i}", energy=energies[i], duration=240.0)
      for i in range(10)
    ]
    tl = compute_set_timeline(tracks, peak_position_pct=0.5)
    peak_entry = next(e for e in tl.entries if e.is_peak)
    # Peak-Track sollte "peak" Phase haben
    assert peak_entry.energy_phase == "peak"


# === Overlap-Berechnung Tests ===

class TestOverlapCalculation:
  """Tests fuer den planbasierten Timeline-Vertrag."""

  def test_last_track_no_overlap(self):
    tracks = [_make_track(duration=200.0) for _ in range(3)]
    tl = compute_set_timeline(tracks)
    assert tl.entries[-1].overlap_with_next == 0.0
    assert tl.entries[-1].transition_planned is None

  def test_planlose_kanten_haben_keine_erfundene_blende(self):
    tracks = [_make_track(duration=200.0) for _ in range(4)]
    tl = compute_set_timeline(tracks, default_overlap=64.0)
    for entry in tl.entries[:-1]:
      assert entry.overlap_with_next == 0.0
      assert entry.transition_planned is False
    assert [entry.start_time for entry in tl.entries] == [0.0, 200.0, 400.0, 600.0]
    assert tl.entries[-1].end_time == 800.0

  def test_track_mixpoints_sind_ohne_plan_keine_timeline_blende(self):
    t1 = _make_track(title="MixOut", duration=300.0, mix_out_point=250.0)
    t2 = _make_track(title="Next", duration=300.0, mix_in_point=50.0)
    tl = compute_set_timeline([t1, t2])
    assert tl.entries[0].end_time == 300.0
    assert tl.entries[1].start_time == 300.0
    assert tl.entries[0].transition_planned is False

  def test_sparse_plan_none_plan_behaelt_exakte_indices(self):
    tracks = [
      _make_track(title="T0", duration=100.0),
      _make_track(title="T1", duration=200.0),
      _make_track(title="T2", duration=300.0),
      _make_track(title="T3", duration=400.0),
    ]
    plans = [_plan(70.0, 20.0, 20.0), None, _plan(250.0, 30.0, 40.0)]
    tl = compute_set_timeline(tracks, transition_plans=plans)

    assert [entry.start_time for entry in tl.entries] == [0.0, 70.0, 250.0, 500.0]
    assert [entry.end_time for entry in tl.entries] == [90.0, 250.0, 540.0, 870.0]
    assert [entry.playing_duration for entry in tl.entries] == [90.0, 180.0, 290.0, 370.0]
    assert [entry.overlap_with_next for entry in tl.entries] == [20.0, 0.0, 40.0, 0.0]
    assert [entry.transition_planned for entry in tl.entries] == [True, False, True, None]

  def test_gueltiger_overlap_ueber_halber_trackdauer_bleibt_exakt(self):
    tracks = [_make_track(duration=100.0), _make_track(duration=100.0)]
    tl = compute_set_timeline(
      tracks, transition_plans=[_plan(30.1234, 10.5678, 60.0)]
    )
    assert tl.entries[0].overlap_with_next == 60.0
    assert tl.entries[0].end_time == 90.1234
    assert tl.entries[1].start_time == 30.1234
    assert tl.entries[1].playing_duration == 89.4322

  @pytest.mark.parametrize(
    "plan, message",
    [
      (_plan(float("nan"), 10.0, 5.0), "nicht-endliche"),
      (_plan(20.0, 10.0, 0.0), "Overlap muss positiv"),
      (_plan(-1.0, 10.0, 5.0), "Track A"),
      (_plan(96.0, 10.0, 5.0), "Track A"),
      (_plan(20.0, -1.0, 5.0), "Track B"),
      (_plan(20.0, 96.0, 5.0), "Track B"),
    ],
  )
  def test_ungueltige_plaene_werden_nicht_geklemmt(self, plan, message):
    tracks = [_make_track(duration=100.0), _make_track(duration=100.0)]
    with pytest.raises(ValueError, match=message):
      compute_set_timeline(tracks, transition_plans=[plan])

  @pytest.mark.parametrize("duration", [0.0, -1.0, float("nan"), float("inf")])
  def test_nichtpositive_oder_nichtendliche_dauer_bricht_ab(self, duration):
    with pytest.raises(ValueError, match="Dauer muss endlich und positiv"):
      compute_set_timeline([_make_track(duration=duration)])

  def test_mittlerer_track_verlangt_mix_in_vor_mix_out(self):
    tracks = [_make_track(duration=100.0) for _ in range(3)]
    plans = [_plan(70.0, 60.0, 10.0), _plan(60.0, 10.0, 10.0)]
    with pytest.raises(ValueError, match="eingehender Mix-In muss vor"):
      compute_set_timeline(tracks, transition_plans=plans)

  def test_kurze_positive_dauer_bleibt_exakt(self):
    tl = compute_set_timeline([_make_track(duration=0.123456)])
    assert tl.entries[0].playing_duration == 0.123456
    assert tl.entries[0].end_time == 0.123456
    assert tl.total_duration_minutes == 0.123456 / 60.0

  def test_summary_behaelt_rohe_praezision(self):
    tracks = [_make_track(duration=1.111), _make_track(duration=2.222)]
    tl = compute_set_timeline(tracks, target_minutes=0.012345)
    summary = get_set_timing_summary(tl)
    assert tl.total_duration_minutes == 3.333 / 60.0
    assert tl.overflow_minutes == tl.total_duration_minutes - 0.012345
    assert summary["overflow_seconds"] == tl.overflow_minutes * 60.0
    assert summary["avg_track_duration"] == (1.111 + 2.222) / 2.0


# === get_set_timing_summary Tests ===

class TestSetTimingSummary:
  """Tests fuer die Set-Zusammenfassung."""

  def test_empty_timeline_summary(self):
    tl = compute_set_timeline([])
    summary = get_set_timing_summary(tl)
    assert summary["total_time"] == "0:00"
    assert summary["track_count"] == 0
    assert summary["peak_track"] is None
    assert summary["avg_track_duration"] == 0.0

  def test_summary_returns_dict(self):
    t = _make_track(duration=300.0)
    tl = compute_set_timeline([t])
    summary = get_set_timing_summary(tl)
    assert isinstance(summary, dict)

  def test_required_keys_present(self):
    t = _make_track(duration=300.0)
    tl = compute_set_timeline([t])
    summary = get_set_timing_summary(tl)
    required = [
      "total_time", "target_time", "overflow", "overflow_seconds",
      "peak_track", "peak_time", "phase_breakdown", "track_count",
      "avg_track_duration",
    ]
    for key in required:
      assert key in summary, f"Missing key: {key}"

  def test_track_count_correct(self):
    tracks = [_make_track(title=f"T{i}", duration=180.0) for i in range(7)]
    tl = compute_set_timeline(tracks)
    summary = get_set_timing_summary(tl)
    assert summary["track_count"] == 7

  def test_peak_track_name(self):
    tracks = [
      _make_track(title="Low", energy=20, duration=200.0),
      _make_track(title="Peak", energy=99, duration=200.0),
      _make_track(title="Mid", energy=50, duration=200.0),
    ]
    tl = compute_set_timeline(tracks)
    summary = get_set_timing_summary(tl)
    assert summary["peak_track"] == "Peak"

  def test_phase_breakdown_is_dict(self):
    tracks = [_make_track(title=f"T{i}") for i in range(5)]
    tl = compute_set_timeline(tracks)
    summary = get_set_timing_summary(tl)
    assert isinstance(summary["phase_breakdown"], dict)

  def test_phase_breakdown_sums_to_track_count(self):
    tracks = [_make_track(title=f"T{i}") for i in range(8)]
    tl = compute_set_timeline(tracks)
    summary = get_set_timing_summary(tl)
    total_phases = sum(summary["phase_breakdown"].values())
    assert total_phases == 8

  def test_avg_track_duration_positive(self):
    tracks = [_make_track(duration=240.0) for _ in range(4)]
    tl = compute_set_timeline(tracks)
    summary = get_set_timing_summary(tl)
    assert summary["avg_track_duration"] > 0

  def test_time_format(self):
    """Zeiten muessen im Format M:SS sein."""
    tracks = [_make_track(duration=180.0) for _ in range(3)]
    tl = compute_set_timeline(tracks)
    summary = get_set_timing_summary(tl)
    # Pruefe Format: enthaelt Doppelpunkt
    assert ":" in summary["total_time"]
    assert ":" in summary["target_time"]
    assert ":" in summary["peak_time"]

  def test_overflow_seconds_matches_overflow(self):
    """overflow_seconds sollte mit overflow-String konsistent sein."""
    tracks = [_make_track(duration=300.0) for _ in range(5)]
    tl = compute_set_timeline(tracks, target_minutes=10.0)
    summary = get_set_timing_summary(tl)
    # overflow_seconds ist einfach overflow_minutes * 60
    assert summary["overflow_seconds"] == pytest.approx(
      tl.overflow_minutes * 60, abs=0.1
    )


# === Edge Cases ===

class TestSetTimingEdgeCases:
  """Edge Cases fuer Set-Timing."""

  def test_all_same_energy(self):
    """Alle Tracks mit gleicher Energie — Peak wird trotzdem gesetzt."""
    tracks = [_make_track(title=f"T{i}", energy=50) for i in range(5)]
    tl = compute_set_timeline(tracks)
    peaks = [e for e in tl.entries if e.is_peak]
    assert len(peaks) == 1

  def test_zero_energy_tracks(self):
    """Tracks mit Energie 0 — kein Fehler."""
    tracks = [_make_track(energy=0, duration=120.0) for _ in range(3)]
    tl = compute_set_timeline(tracks)
    assert len(tl.entries) == 3

  def test_max_energy_tracks(self):
    """Tracks mit Energie 100 — kein Fehler."""
    tracks = [_make_track(energy=100, duration=120.0) for _ in range(3)]
    tl = compute_set_timeline(tracks)
    assert len(tl.entries) == 3

  def test_very_short_tracks(self):
    """Sehr kurze Tracks (10s) — Duration wird auf 30s hochgesetzt."""
    tracks = [_make_track(duration=10.0) for _ in range(3)]
    tl = compute_set_timeline(tracks)
    for entry in tl.entries:
      assert entry.playing_duration >= 4.0  # Mindestens etwas spielbar

  def test_very_long_tracks(self):
    """Sehr lange Tracks (20 Minuten)."""
    tracks = [_make_track(duration=1200.0) for _ in range(3)]
    tl = compute_set_timeline(tracks)
    assert tl.total_duration_minutes > 0

  def test_mixed_durations(self):
    """Mix aus kurzen und langen Tracks."""
    tracks = [
      _make_track(title="Short", duration=90.0),
      _make_track(title="Medium", duration=300.0),
      _make_track(title="Long", duration=600.0),
    ]
    tl = compute_set_timeline(tracks)
    assert len(tl.entries) == 3
    # Kurzester Track hat kleinste playing_duration
    durations = [e.playing_duration for e in tl.entries]
    assert durations[0] < durations[2]

  def test_default_overlap_bleibt_legacy_parameter_ohne_timing_wirkung(self):
    """Ohne Plan bleibt der oeffentliche Legacy-Parameter bewusst inert."""
    tracks = [_make_track(duration=300.0) for _ in range(3)]
    tl1 = compute_set_timeline(tracks, default_overlap=8.0)
    tl2 = compute_set_timeline(tracks, default_overlap=32.0)
    timing1 = [
      (e.start_time, e.end_time, e.playing_duration, e.overlap_with_next)
      for e in tl1.entries
    ]
    timing2 = [
      (e.start_time, e.end_time, e.playing_duration, e.overlap_with_next)
      for e in tl2.entries
    ]
    assert timing1 == timing2 == [
      (0.0, 300.0, 300.0, 0.0),
      (300.0, 600.0, 300.0, 0.0),
      (600.0, 900.0, 300.0, 0.0),
    ]

  def test_large_set_50_tracks(self):
    """50 Tracks — Performance und Korrektheit."""
    tracks = [
      _make_track(title=f"T{i:02d}", energy=20+i, duration=180.0)
      for i in range(50)
    ]
    tl = compute_set_timeline(tracks, target_minutes=120.0)
    assert len(tl.entries) == 50
    peaks = [e for e in tl.entries if e.is_peak]
    assert len(peaks) == 1
    # Alle Zeiten muessen aufsteigend sein
    for i in range(len(tl.entries) - 1):
      assert tl.entries[i].start_time < tl.entries[i + 1].start_time

  def test_target_zero_minutes(self):
    """target_minutes=0 — overflow ist positiv."""
    t = _make_track(duration=120.0)
    tl = compute_set_timeline([t], target_minutes=0.0)
    assert tl.overflow_minutes > 0

  def test_entries_start_at_zero(self):
    """Erster Track startet bei 0 Sekunden."""
    tracks = [_make_track(duration=200.0) for _ in range(4)]
    tl = compute_set_timeline(tracks)
    assert tl.entries[0].start_time == 0.0
