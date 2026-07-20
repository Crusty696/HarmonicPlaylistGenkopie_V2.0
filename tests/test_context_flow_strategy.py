"""
Tests fuer die 'Context Flow'-Strategie (_sort_context_flow) -- der aus der
geloeschten Intelligent-Scoring-Schicht portierte Mehrwert: Set-Phasen,
Energie-Trend, Genre-Fatigue, Repetition-/Cliff-Penalties auf korrekter
Camelot-Basis (calculate_compatibility).
"""

from hpg_core.playlist import STRATEGIES, _sort_context_flow, generate_playlist
from tests.fixtures.track_factories import make_track


def _mk(bpm, energy, camelot="8A", genre="Techno", title=None):
  t = make_track()
  t.bpm = bpm
  t.energy = energy
  t.camelotCode = camelot
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
    assert len(result) == 6
