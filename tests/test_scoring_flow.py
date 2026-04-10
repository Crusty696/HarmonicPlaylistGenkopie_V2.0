"""
Tests für Flow-Kontinuitäts-Analyse (scoring_flow.py).
"""

import pytest
from unittest.mock import patch, MagicMock
from hpg_core.models import Track
from hpg_core.scoring_context import PlaylistContext
from hpg_core.scoring_flow import FlowAnalyzer

class TestFlowAnalyzer:
  """Tests für Flow-Kontinuitäts-Analyse."""

  def _make_track(self, energy=50, bpm=120, detected_genre="House", genre="House", camelotCode="8A", brightness=50, danceability=80):
    return Track(
      filePath="/dummy",
      fileName="dummy",
      energy=energy,
      bpm=bpm,
      detected_genre=detected_genre,
      genre=genre,
      camelotCode=camelotCode,
      brightness=brightness,
      danceability=danceability
    )

  def test_detect_flow_pattern_less_than_3_tracks(self):
    """Flow Detection: Unter 3 Tracks immer UNDEFINED."""
    context = PlaylistContext([self._make_track(), self._make_track()], 10)
    assert FlowAnalyzer.detect_flow_pattern(context) == "UNDEFINED"

    context = PlaylistContext([], 10)
    assert FlowAnalyzer.detect_flow_pattern(context) == "UNDEFINED"

  def test_detect_smooth_rising_flow(self):
    """Flow Detection: Sanfte steigende Energie."""
    playlist = [
        self._make_track(energy=50),
        self._make_track(energy=60),
        self._make_track(energy=70),
    ]
    context = PlaylistContext(playlist, 10)
    assert FlowAnalyzer.detect_flow_pattern(context) == "SMOOTH_RISING"

  def test_detect_smooth_falling_flow(self):
    """Flow Detection: Sanfte fallende Energie."""
    playlist = [
        self._make_track(energy=70),
        self._make_track(energy=60),
        self._make_track(energy=50),
    ]
    context = PlaylistContext(playlist, 10)
    assert FlowAnalyzer.detect_flow_pattern(context) == "SMOOTH_FALLING"

  def test_detect_smooth_stable_flow(self):
    """Flow Detection: Stabile Energie."""
    playlist = [
        self._make_track(energy=70),
        self._make_track(energy=70),
        self._make_track(energy=70),
    ]
    context = PlaylistContext(playlist, 10)
    assert FlowAnalyzer.detect_flow_pattern(context) == "SMOOTH_STABLE"

  @patch('hpg_core.scoring_context.PlaylistContext.get_energy_trend')
  def test_detect_flow_pattern_fallback(self, mock_trend):
    """Flow Detection: Fallback bei unerwartetem Trend."""
    playlist = [
        self._make_track(energy=70),
        self._make_track(energy=70),
        self._make_track(energy=70),
    ]
    context = PlaylistContext(playlist, 10)
    mock_trend.return_value = "WEIRD_TREND"
    assert FlowAnalyzer.detect_flow_pattern(context) == "UNDEFINED"

  def test_get_flow_consistency_score_few_tracks(self):
    """Consistency Score: Bei < 3 Tracks neutral 0.5."""
    context = PlaylistContext([self._make_track()], 10)
    assert FlowAnalyzer.get_flow_consistency_score(context) == 0.5

  def test_get_flow_consistency_score_chaotic(self):
    """Consistency Score: Bei chaotischen Sprüngen sehr niedrig."""
    playlist = [
        self._make_track(energy=10, bpm=100, detected_genre="House"),
        self._make_track(energy=90, bpm=150, detected_genre="Techno"),
        self._make_track(energy=20, bpm=90, detected_genre="Jazz"),
        self._make_track(energy=100, bpm=170, detected_genre="Rock"),
    ]
    context = PlaylistContext(playlist, 10)
    score = FlowAnalyzer.get_flow_consistency_score(context)
    assert score < 0.5

  def test_consistency_score_high_for_smooth_flow(self):
    """Consistency Score sollte hoch sein für smooth Flow."""
    smooth_playlist = [
        self._make_track(energy=70, bpm=128),
        self._make_track(energy=72, bpm=129),
        self._make_track(energy=71, bpm=128),
    ]
    context = PlaylistContext(smooth_playlist, 10)
    consistency = FlowAnalyzer.get_flow_consistency_score(context)
    assert consistency > 0.7

  def test_predict_good_flow_candidates_few_tracks(self):
    """Predict Candidates: < 2 Tracks neutral 0.5."""
    context = PlaylistContext([self._make_track()], 10)
    candidates = [self._make_track(), self._make_track()]
    results = FlowAnalyzer.predict_good_flow_candidates(context, candidates)
    for track, score in results:
      assert score == 0.5

  def test_predict_good_flow_candidates_rising(self):
    """Predict Candidates: Rising Flow belohnt höhere Energy."""
    playlist = [
        self._make_track(energy=50),
        self._make_track(energy=60),
        self._make_track(energy=70),
    ]
    context = PlaylistContext(playlist, 10)
    candidates = [
        self._make_track(energy=75), # higher, good
        self._make_track(energy=40), # much lower, bad
    ]
    scored = FlowAnalyzer.predict_good_flow_candidates(context, candidates)
    # 75 energy candidate should score higher
    assert scored[0][0].energy == 75
    assert scored[1][0].energy == 40
    assert scored[0][1] > scored[1][1]

  def test_predict_good_flow_candidates_falling(self):
    """Predict Candidates: Falling Flow belohnt niedrigere Energy."""
    playlist = [
        self._make_track(energy=70),
        self._make_track(energy=60),
        self._make_track(energy=50),
    ]
    context = PlaylistContext(playlist, 10)
    candidates = [
        self._make_track(energy=70), # much higher, bad
        self._make_track(energy=45), # lower, good
    ]
    scored = FlowAnalyzer.predict_good_flow_candidates(context, candidates)
    assert scored[0][0].energy == 45
    assert scored[1][0].energy == 70

  def test_predict_good_flow_candidates_stable(self):
    """Predict Candidates: Stable Flow belohnt ähnliche Energy."""
    playlist = [
        self._make_track(energy=70),
        self._make_track(energy=70),
        self._make_track(energy=70),
    ]
    context = PlaylistContext(playlist, 10)
    candidates = [
        self._make_track(energy=72), # similar, good
        self._make_track(energy=90), # diff > 10, no bonus
    ]
    scored = FlowAnalyzer.predict_good_flow_candidates(context, candidates)
    assert scored[0][0].energy == 72
    assert scored[0][1] > scored[1][1]

  @patch('hpg_core.scoring_context.PlaylistContext.get_bpm_trend')
  def test_predict_good_flow_candidates_bpm(self, mock_bpm_trend):
    """Predict Candidates: BPM trend accelerates/decelerates."""
    playlist = [
        self._make_track(bpm=120),
        self._make_track(bpm=125),
        self._make_track(bpm=130),
    ]
    context = PlaylistContext(playlist, 10)

    # ACCELERATING
    mock_bpm_trend.return_value = "ACCELERATING"
    c_fast = self._make_track(bpm=135)
    c_slow = self._make_track(bpm=125)
    scored = FlowAnalyzer.predict_good_flow_candidates(context, [c_fast, c_slow])
    assert scored[0][0].bpm == 135

    # DECELERATING
    mock_bpm_trend.return_value = "DECELERATING"
    scored = FlowAnalyzer.predict_good_flow_candidates(context, [c_fast, c_slow])
    assert scored[0][0].bpm == 125

  @patch('hpg_core.scoring_context.PlaylistContext.get_genre_streak')
  def test_predict_good_flow_candidates_genre_streak(self, mock_streak):
    """Predict Candidates: Genre streak logic."""
    playlist = [
        self._make_track(energy=70, detected_genre="House"),
        self._make_track(energy=70, detected_genre="House"),
        self._make_track(energy=70, detected_genre="House"),
    ]
    context = PlaylistContext(playlist, 10)
    c_same = self._make_track(detected_genre="House")
    c_diff = self._make_track(detected_genre="Techno")

    # Streak < 3 -> varied genre has no direct bonus vs same, but gets +0.1 flat in logic
    mock_streak.return_value = 2
    scored = FlowAnalyzer.predict_good_flow_candidates(context, [c_same, c_diff])
    # Both get +0.1 since streak < 3 applies to any candidate

    # Streak >= 5 -> diff gets +0.2, same gets -0.15
    mock_streak.return_value = 5
    scored = FlowAnalyzer.predict_good_flow_candidates(context, [c_same, c_diff])
    assert scored[0][0].detected_genre == "Techno"

  def test_measure_flow_coherence_few_tracks(self):
    """Coherence Score: < 3 Tracks neutral 0.5."""
    context = PlaylistContext([self._make_track()], 10)
    assert FlowAnalyzer.measure_flow_coherence(context) == 0.5

  def test_coherence_high_for_peak_phase(self):
    """Coherence sollte hoch sein im PEAK mit konsistenten Genres."""
    peak_playlist = [
        self._make_track(energy=80, bpm=128),
        self._make_track(energy=82, bpm=129),
        self._make_track(energy=81, bpm=128),
        self._make_track(energy=83, bpm=129),
        self._make_track(energy=82, bpm=128),
    ]
    context = PlaylistContext(peak_playlist, 10)  # Position 5 von 10 = PEAK Phase
    coherence = FlowAnalyzer.measure_flow_coherence(context)
    assert coherence > 0.65

  @patch('hpg_core.scoring_context.PlaylistContext.get_playlist_phase')
  @patch('hpg_core.scoring_context.PlaylistContext.get_genre_streak')
  def test_coherence_genre_quality(self, mock_streak, mock_phase):
    """Coherence: Genre quality varies by phase."""
    playlist = [
        self._make_track(energy=80),
        self._make_track(energy=80),
        self._make_track(energy=80),
    ]
    context = PlaylistContext(playlist, 10)

    mock_phase.return_value = "PEAK"
    mock_streak.return_value = 3
    coherence_peak_streak = FlowAnalyzer.measure_flow_coherence(context)

    mock_streak.return_value = 1
    coherence_peak_no_streak = FlowAnalyzer.measure_flow_coherence(context)
    assert coherence_peak_streak > coherence_peak_no_streak

    mock_phase.return_value = "BUILD_UP"
    mock_streak.return_value = 1
    coherence_build_no_streak = FlowAnalyzer.measure_flow_coherence(context)

    mock_streak.return_value = 5
    coherence_build_streak = FlowAnalyzer.measure_flow_coherence(context)
    assert coherence_build_no_streak > coherence_build_streak

  def test_log_flow_analysis(self):
    """Log Flow Analysis smoke test."""
    context = PlaylistContext([self._make_track(), self._make_track(), self._make_track()], 10)
    with patch('hpg_core.scoring_flow.logger.debug') as mock_debug:
      FlowAnalyzer.log_flow_analysis(context)
      mock_debug.assert_called_once()

  def test_calculate_variance_empty(self):
    """Variance: Leere Liste sollte 0.0 zurückgeben."""
    assert FlowAnalyzer._calculate_variance([]) == 0.0

  def test_calculate_variance_single_element(self):
    """Variance: Ein Element sollte 0.0 zurückgeben."""
    assert FlowAnalyzer._calculate_variance([10.0]) == 0.0

  def test_calculate_variance_identical_elements(self):
    """Variance: Identische Elemente sollten 0.0 zurückgeben."""
    assert FlowAnalyzer._calculate_variance([1.0, 1.0, 1.0]) == 0.0

  def test_calculate_variance_normal_case(self):
    """Variance: Normalfall mit bekannten Werten."""
    # [1.0, 2.0, 3.0] -> Mean = 2.0
    # Variance = ((1-2)^2 + (2-2)^2 + (3-2)^2) / 3 = (1 + 0 + 1) / 3 = 0.666...
    result = FlowAnalyzer._calculate_variance([1.0, 2.0, 3.0])
    assert abs(result - 0.6666666666666666) < 1e-9

  def test_calculate_variance_large_values(self):
    """Variance: Größere Werte (BPM/Energy)."""
    # [120, 130] -> Mean = 125
    # Variance = ((120-125)^2 + (130-125)^2) / 2 = (25 + 25) / 2 = 25.0
    assert FlowAnalyzer._calculate_variance([120.0, 130.0]) == 25.0
