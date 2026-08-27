"""
Tests fuer die 'Context Flow'-Strategie (_sort_context_flow) -- der aus der
geloeschten Intelligent-Scoring-Schicht portierte Mehrwert: Set-Phasen,
Energie-Trend, Genre-Fatigue, Repetition-/Cliff-Penalties auf korrekter
Camelot-Basis (calculate_compatibility).
"""

from hpg_core.playlist import (
  STRATEGIES,
  _sort_context_flow,
  _sort_genre_flow,
  generate_playlist,
)
from tests.fixtures.track_factories import make_track


def _mk(bpm, energy, camelot="8A", genre="Techno", title=None):
  identity = title or f"{bpm}-{energy}-{camelot}-{genre}"
  t = make_track(
    filePath=f"/test/{identity}.mp3",
    fileName=f"{identity}.mp3",
    bpm=bpm,
    energy=energy,
    camelotCode=camelot,
    genre=genre,
  )
  t.detected_genre = genre
  if title:
    t.title = title
  return t


class TestContextFlowStrategy:
  def test_registered_in_strategies(self):
    assert "Context Flow" in STRATEGIES
    assert STRATEGIES["Context Flow"] is _sort_context_flow

  def test_returns_all_tracks_exactly_once(self):
    tracks = [_mk(120 + i, 30 + i * 5) for i in range(10)]
    result = _sort_context_flow(tracks, bpm_tolerance=6.0)
    assert len(result) == 10
    assert set(id(t) for t in result) == set(id(t) for t in tracks)

  def test_starts_with_lowest_energy(self):
    tracks = [_mk(124, 80), _mk(125, 20), _mk(126, 55)]
    result = _sort_context_flow(tracks, bpm_tolerance=6.0)
    assert result[0].energy == 20

  def test_small_input_sorted_by_energy(self):
    tracks = [_mk(128, 90), _mk(124, 10)]
    result = _sort_context_flow(tracks, bpm_tolerance=6.0)
    assert [t.energy for t in result] == [10, 90]

  def test_energy_arc_roughly_rises_then_falls(self):
    # 12 Tracks, Energien 10..90 -- Peak-Phase (Position 50-80%) soll im
    # Schnitt energiereicher sein als Warm-up-Phase
    tracks = [_mk(125.0, 10 + i * 7, camelot="8A") for i in range(12)]
    result = _sort_context_flow(tracks, bpm_tolerance=10.0)
    warmup = [t.energy for t in result[:3]]
    peak = [t.energy for t in result[6:9]]
    assert sum(peak) / len(peak) > sum(warmup) / len(warmup)

  def test_genre_fatigue_prefers_switch_after_streak(self):
    # 5x Techno gleicher Energie + 1 Tech House Alternative:
    # nach 4er-Streak soll der Genre-Wechsel belohnt werden
    techno = [_mk(125.0, 50, genre="Techno", title=f"T{i}") for i in range(5)]
    other = _mk(125.0, 50, genre="Tech House", title="TH")
    result = _sort_context_flow(techno + [other], bpm_tolerance=6.0)
    # Tech-House-Track darf nicht ganz am Ende haengen bleiben
    position = next(i for i, t in enumerate(result) if t.detected_genre == "Tech House")
    assert position < len(result) - 1

  def test_works_via_generate_playlist(self):
    tracks = [_mk(120 + i, 30 + i * 6) for i in range(6)]
    result = generate_playlist(tracks, mode="Context Flow", bpm_tolerance=8.0)
    # Nicht lokal anschliessbare Tracks bleiben sichtbar in der Library,
    # werden aber nicht als stiller schlechter Uebergang angehaengt.
    assert len(result) == 6

  def test_peak_position_changes_auto_energy_arc(self):
    energies = [10, 20, 30, 40, 50, 60, 70, 80, 90]
    early = _sort_context_flow(
      [_mk(128, energy) for energy in energies],
      bpm_tolerance=3.0,
      peak_position=40,
    )
    late = _sort_context_flow(
      [_mk(128, energy) for energy in energies],
      bpm_tolerance=3.0,
      peak_position=80,
    )

    assert [track.energy for track in early] != [track.energy for track in late]
    early_peak = next(i for i, track in enumerate(early) if track.energy == 90)
    late_peak = next(i for i, track in enumerate(late) if track.energy == 90)
    assert early_peak < late_peak

  def test_context_genre_weight_changes_candidate_ranking(self):
    genres = ["Techno", "Trance", "Minimal", "Tech House", "Deep House", "Psytrance"]
    no_genre = _sort_context_flow(
      [_mk(128, 50, genre=genre, title=genre) for genre in genres],
      bpm_tolerance=3.0,
      genre_mixing=True,
      genre_weight=0.0,
    )
    genre_first = _sort_context_flow(
      [_mk(128, 50, genre=genre, title=genre) for genre in genres],
      bpm_tolerance=3.0,
      genre_mixing=True,
      genre_weight=1.0,
    )

    assert [track.detected_genre for track in no_genre] != [
      track.detected_genre for track in genre_first
    ]

  def test_genre_flow_falls_back_from_unknown_detection_to_id3(self):
    tracks = [
      _mk(128, 50, genre="Techno", title="T1"),
      _mk(128, 50, genre="Trance", title="R"),
      _mk(128, 50, genre="Techno", title="T2"),
    ]
    for track in tracks:
      track.detected_genre = "Unknown"

    result = _sort_genre_flow(tracks, bpm_tolerance=3.0)

    assert [track.title for track in result] == ["T1", "T2", "R"]

  def test_genre_flow_weight_blends_transition_and_genre_scores(self):
    genres = ["Techno", "Trance", "Minimal", "Tech House", "Deep House", "Psytrance"]
    transition_first = _sort_genre_flow(
      [_mk(128, 50, genre=genre, title=genre) for genre in genres],
      bpm_tolerance=3.0,
      genre_weight=0.0,
    )
    genre_first = _sort_genre_flow(
      [_mk(128, 50, genre=genre, title=genre) for genre in genres],
      bpm_tolerance=3.0,
      genre_weight=1.0,
    )

    assert [track.detected_genre for track in transition_first] != [
      track.detected_genre for track in genre_first
    ]
