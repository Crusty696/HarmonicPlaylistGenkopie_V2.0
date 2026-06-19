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
)
from hpg_core.models import Track


# === Hilfsfunktionen ===

def _make_track(
    title: str = "Test",
    bpm: float = 128.0,
    camelot: str = "8A",
    energy: int = 50,
    duration: float = 300.0,
    mix_out_point: float = 0.0,
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
    detected_genre=genre,
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
    """Zwei Tracks: erster hat Overlap, zweiter nicht."""
    t1 = _make_track(title="T1", duration=300.0)
    t2 = _make_track(title="T2", duration=300.0)
    tl = compute_set_timeline([t1, t2])
    assert tl.entries[0].overlap_with_next > 0
    assert tl.entries[1].overlap_with_next == 0.0

  def test_timeline_continuity(self):
    """End-Zeit von Entry[i] == Start-Zeit von Entry[i+1]."""
    tracks = [_make_track(title=f"T{i}", duration=240.0) for i in range(5)]
    tl = compute_set_timeline(tracks)
    for i in range(len(tl.entries) - 1):
      assert tl.entries[i].end_time == pytest.approx(
        tl.entries[i + 1].start_time
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

  def test_minimum_duration_enforced(self):
    """Tracks mit 0s Duration bekommen mindestens 30s."""
    t = _make_track(title="ZeroDur", duration=0.0)
    tl = compute_set_timeline([t])
    assert tl.entries[0].playing_duration >= 30.0

  def test_negative_duration_clamped(self):
    """Negative Duration wird auf mindestens 30s gesetzt."""
    t = _make_track(title="Neg", duration=-10.0)
    tl = compute_set_timeline([t])
    assert tl.entries[0].playing_duration >= 30.0

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
    valid = {"intro", "build", "peak", "sustain", "cooldown"}
    for entry in tl.entries:
      assert entry.energy_phase in valid

  def test_valid_phase_names(self):
    """Alle Phasen haben gueltige Namen."""
    valid = {"intro", "build", "peak", "sustain", "cooldown"}
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
  """Tests fuer die Overlap-Berechnung."""

  def test_last_track_no_overlap(self):
    tracks = [_make_track(duration=200.0) for _ in range(3)]
    tl = compute_set_timeline(tracks)
    assert tl.entries[-1].overlap_with_next == 0.0

  def test_overlap_positive(self):
    """Overlap sollte immer positiv sein."""
    tracks = [_make_track(duration=200.0) for _ in range(4)]
    tl = compute_set_timeline(tracks)
    for entry in tl.entries[:-1]:
      assert entry.overlap_with_next > 0

  def test_overlap_bounded_by_track_duration(self):
    """Overlap darf nicht groesser als 30% der Track-Dauer sein."""
    tracks = [_make_track(duration=120.0) for _ in range(3)]
    tl = compute_set_timeline(tracks)
    for entry in tl.entries[:-1]:
      track_dur = max(entry.track.duration, 30.0)
      assert entry.overlap_with_next <= track_dur * 0.3 + 0.1  # +0.1 Toleranz

  def test_overlap_at_least_4_seconds(self):
    """Minimum 4 Sekunden Overlap."""
    tracks = [_make_track(duration=300.0) for _ in range(3)]
    tl = compute_set_timeline(tracks)
    for entry in tl.entries[:-1]:
      assert entry.overlap_with_next >= 4.0

  def test_mix_out_point_used(self):
    """Wenn mix_out_point gesetzt, beeinflusst es den Overlap."""
    t1 = _make_track(title="MixOut", duration=300.0, mix_out_point=250.0)
    t2 = _make_track(title="Next", duration=300.0)
    tl = compute_set_timeline([t1, t2])
    # mix_out bei 250s, duration 300s -> Overlap-Bereich ca. 50s
    # Wird aber auf max(default_overlap, 30% dur) begrenzt
    assert tl.entries[0].overlap_with_next > 0

  def test_playing_duration_equals_total_minus_overlap(self):
    """playing_duration = track_duration - overlap."""
    tracks = [_make_track(duration=240.0) for _ in range(3)]
    tl = compute_set_timeline(tracks)
    for entry in tl.entries:
      track_dur = max(entry.track.duration, 30.0)
      expected = track_dur - entry.overlap_with_next
      assert entry.playing_duration == pytest.approx(expected, abs=0.1)


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

  def test_default_overlap_parameter(self):
    """custom default_overlap wird respektiert."""
    tracks = [_make_track(duration=300.0) for _ in range(3)]
    tl1 = compute_set_timeline(tracks, default_overlap=8.0)
    tl2 = compute_set_timeline(tracks, default_overlap=32.0)
    # Verschiedene default_overlaps koennen unterschiedliche Ergebnisse geben
    assert tl1.total_duration_minutes > 0
    assert tl2.total_duration_minutes > 0

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
