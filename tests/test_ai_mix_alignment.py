"""
Tests fuer align_ai_mix_points (Phrasen-Quantisierung von LLM-Mixpoints)
und den None-Guard im Bass-Kollisions-Check.

Regression fuer:
- AI-Override schrieb Mixpoints ohne Phrase-Alignment in den Track
- _assess_transition_risks crashte bei Section-Dicts ohne end_time
"""
import pytest

from hpg_core.dj_brain import align_ai_mix_points, _assess_transition_risks
from tests.fixtures.track_factories import make_track


class TestAlignAiMixPoints:
  def test_aligns_to_phrase_grid(self):
    # 128 BPM, phrase_unit 8 -> Grid = (60/128*4)*8 = 15.0s
    mix_in, mix_out = align_ai_mix_points(32.5, 240.0, 128.0, 300.0, 8)
    grid = (60.0 / 128.0) * 4 * 8
    assert mix_in % grid == pytest.approx(0.0, abs=0.02)
    assert mix_out % grid == pytest.approx(0.0, abs=0.02)

  def test_mix_in_ceils_mix_out_floors(self):
    # ceil = nach Intro, floor = vor Outro
    mix_in, mix_out = align_ai_mix_points(32.5, 244.0, 128.0, 300.0, 8)
    assert mix_in >= 32.5
    assert mix_out <= 244.0
    assert mix_in < mix_out

  def test_falls_back_to_bar_grid_when_phrase_window_collapses(self):
    # Fenster 20-28s bei 128 BPM: Phrasen-Grid 15s kollabiert (30 > 15),
    # Bar-Grid 1.875s muss greifen
    mix_in, mix_out = align_ai_mix_points(20.0, 28.0, 128.0, 300.0, 8)
    bar = (60.0 / 128.0) * 4
    assert mix_in < mix_out
    # Abstand zur naechsten Bar-Grenze (Werte sind auf 2 Dezimalen gerundet)
    assert abs(mix_in / bar - round(mix_in / bar)) * bar < 0.02
    assert abs(mix_out / bar - round(mix_out / bar)) * bar < 0.02

  def test_invalid_bpm_returns_originals(self):
    assert align_ai_mix_points(30.0, 200.0, 0.0, 300.0, 8) == (30.0, 200.0)

  def test_invalid_window_returns_originals(self):
    assert align_ai_mix_points(200.0, 30.0, 128.0, 300.0, 8) == (200.0, 30.0)

  def test_result_stays_within_duration(self):
    mix_in, mix_out = align_ai_mix_points(10.0, 295.0, 128.0, 300.0, 16)
    assert 0 <= mix_in < mix_out <= 300.0


class TestBassCollisionNoneGuard:
  def test_missing_end_time_does_not_crash(self):
    track_a = make_track()
    track_b = make_track()
    # Section-Dict ohne end_time (unvollstaendige Analyse / alter Cache)
    track_a.sections = [{"label": "main", "start_time": 0.0, "avg_bass": 70.0}]
    track_b.sections = [{"label": "main", "start_time": 0.0, "end_time": None, "avg_bass": 70.0}]
    risks = _assess_transition_risks(track_a, track_b, genre_compat=0.8)
    assert isinstance(risks, list)
