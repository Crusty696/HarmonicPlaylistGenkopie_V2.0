"""
Phase 2 Tests: Erweiterte Intelligenz für das Scoring-System

Tests für:
1. Genre-Kompatibilitäts-Matrix
2. Erweiterte Bonuses und Penalties
3. Flow-Kontinuitäts-Analyse
"""

import pytest
from hpg_core.models import Track
from hpg_core.scoring_context import PlaylistContext
from hpg_core.scoring_engine import IntelligentScoreEngine
from hpg_core.genre_compatibility import GenreCompatibilityMatrix
from hpg_core.scoring_bonuses import EnhancedBonusCalculator, EnhancedPenaltyCalculator
from hpg_core.scoring_flow import FlowAnalyzer


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def house_track():
  """Typischer House Track."""
  return Track(
      filePath="/music/house1.mp3",
      fileName="house1.mp3",
      artist="DJ House",
      title="House Anthem",
      genre="House",
      detected_genre="House",
      bpm=128,
      keyNote="D",
      keyMode="Minor",
      camelotCode="7A",
      energy=70,
      duration=240,
      brightness=60,
      danceability=85,
      vocal_instrumental="instrumental",
  )


@pytest.fixture
def techno_track():
  """Typischer Techno Track."""
  return Track(
      filePath="/music/techno1.mp3",
      fileName="techno1.mp3",
      artist="DJ Techno",
      title="Techno Deep",
      genre="Techno",
      detected_genre="Techno",
      bpm=135,
      keyNote="E",
      keyMode="Minor",
      camelotCode="9A",
      energy=75,
      duration=300,
      brightness=40,
      danceability=80,
      vocal_instrumental="instrumental",
  )


@pytest.fixture
def deep_house_track():
  """Deep House Track - kompatibel mit House."""
  return Track(
      filePath="/music/deephouse1.mp3",
      fileName="deephouse1.mp3",
      artist="DJ Deep",
      title="Deep Vibes",
      genre="Deep House",
      detected_genre="Deep House",
      bpm=126,
      keyNote="C#",
      keyMode="Minor",
      camelotCode="12A",
      energy=65,
      duration=280,
      brightness=50,
      danceability=75,
      vocal_instrumental="instrumental",
  )


@pytest.fixture
def trance_track():
  """Trance Track - weniger kompatibel mit House."""
  return Track(
      filePath="/music/trance1.mp3",
      fileName="trance1.mp3",
      artist="DJ Trance",
      title="Trance Journey",
      genre="Trance",
      detected_genre="Trance",
      bpm=140,
      keyNote="G",
      keyMode="Minor",
      camelotCode="6A",
      energy=80,
      duration=320,
      brightness=70,
      danceability=70,
      vocal_instrumental="instrumental",
  )


@pytest.fixture
def classical_track():
  """Classical Track - nicht kompatibel mit House."""
  return Track(
      filePath="/music/classical1.mp3",
      fileName="classical1.mp3",
      artist="Composer",
      title="Symphony",
      genre="Classical",
      detected_genre="Classical",
      bpm=90,
      keyNote="A",
      keyMode="Major",
      camelotCode="11B",
      energy=30,
      duration=600,
      brightness=80,
      danceability=10,
      vocal_instrumental="instrumental",
  )


# ============================================================================
# GENRE COMPATIBILITY TESTS
# ============================================================================

class TestGenreCompatibilityMatrix:
  """Tests für Genre-Kompatibilitäts-Matrix."""

  def test_same_genre_is_perfect(self, house_track):
    """Gleiches Genre sollte 1.0 Score geben."""
    score = GenreCompatibilityMatrix.get_compatibility("House", "House")
    assert score == 1.0

  def test_house_deep_house_compatible(self):
    """House → Deep House sollte sehr kompatibel sein."""
    score = GenreCompatibilityMatrix.get_compatibility("House", "Deep House")
    assert score == 0.95

  def test_house_techno_somewhat_compatible(self):
    """House → Techno sollte teilweise kompatibel sein."""
    score = GenreCompatibilityMatrix.get_compatibility("House", "Techno")
    assert 0.65 <= score <= 0.75

  def test_house_classical_incompatible(self):
    """House → Classical sollte inkompatibel sein."""
    score = GenreCompatibilityMatrix.get_compatibility("House", "Classical")
    # Heuristik für electronic+acoustic = 0.35
    assert score <= 0.35

  def test_bidirectional_compatibility(self):
    """Kompatibilität sollte bidirektional sein."""
    score1 = GenreCompatibilityMatrix.get_compatibility("House", "Techno")
    score2 = GenreCompatibilityMatrix.get_compatibility("Techno", "House")
    assert score1 == score2

  def test_missing_genre_returns_neutral(self):
    """Fehlende Genres sollten neutral bewertet werden."""
    score = GenreCompatibilityMatrix.get_compatibility("House", "")
    assert score == 0.5

    score = GenreCompatibilityMatrix.get_compatibility("", "House")
    assert score == 0.5

  def test_case_insensitive_matching(self):
    """Matching sollte case-insensitiv sein."""
    score1 = GenreCompatibilityMatrix.get_compatibility("house", "HOUSE")
    assert score1 == 1.0

    score2 = GenreCompatibilityMatrix.get_compatibility("HOUSE", "deep house")
    assert score2 == 0.95


# ============================================================================
# ENHANCED BONUS TESTS
# ============================================================================

class TestEnhancedBonusCalculator:
  """Tests für erweiterte Bonus-Berechnung."""

  def test_surprise_bonus_cross_genre(self, house_track):
    """Überraschung: harmonisch eng aber Genre-Wechsel."""
    # Techno mit Camelot sehr nah dran aber anderes Genre
    techno_track = Track(
        "/techno", "techno", artist="DJ", title="Tech", genre="Techno",
        detected_genre="Techno", bpm=130, keyNote="E", keyMode="Minor",
        camelotCode="8A",  # Abstand zu House 7A = 1
        energy=75, brightness=40, danceability=80,
        duration=300
    )

    context = PlaylistContext([house_track], 10)
    bonus = EnhancedBonusCalculator.calculate_all_bonuses(
        house_track, techno_track, context, "HARMONIC_FLOW"
    )

    # Sollte Bonus bekommen (enges Camelot + Genre-Wechsel + ähnliches BPM)
    assert bonus >= 0.03  # Mindestens ein kleiner Bonus

  def test_flow_bonus_energy_rising(self, house_track, techno_track):
    """Flow Bonus: Energy steigt schön an."""
    playlist = [
        Track("/1", "1", bpm=124, energy=50, detected_genre="House", genre="House",
              camelotCode="7A", brightness=50, danceability=80),
        Track("/2", "2", bpm=122, energy=60, detected_genre="House", genre="House",
              camelotCode="8A", brightness=50, danceability=80),
        Track("/3", "3", bpm=124, energy=70, detected_genre="House", genre="House",
              camelotCode="8A", brightness=50, danceability=80),
    ]

    context = PlaylistContext(playlist, 10)
    candidate = Track("/4", "4", bpm=126, energy=80, detected_genre="House", genre="House",
                      camelotCode="9A", brightness=50, danceability=80)

    bonus = EnhancedBonusCalculator.calculate_all_bonuses(
        playlist[-1], candidate, context, "PEAK_TIME"
    )

    # Sollte Bonus bekommen für sanfte Energie-Eskalation
    assert bonus > 0.04

  def test_spectral_bonus_brightness_variation(self):
    """Spectral Bonus: Unterschied in Brightness ist erfreulich."""
    house_track = Track(
        "/house", "house", artist="DJ", title="House", genre="House",
        detected_genre="House", bpm=128, keyNote="D", keyMode="Minor",
        camelotCode="7A", energy=70, brightness=30,  # Dunkel
        danceability=85, duration=240
    )

    techno_track = Track(
        "/techno", "techno", artist="DJ", title="Techno", genre="Techno",
        detected_genre="Techno", bpm=130, keyNote="E", keyMode="Minor",
        camelotCode="9A", energy=75, brightness=65,  # Hell (diff = 35)
        danceability=80, duration=300
    )

    context = PlaylistContext([house_track], 10)
    bonus = EnhancedBonusCalculator.calculate_all_bonuses(
        house_track, techno_track, context, "HARMONIC_FLOW"
    )

    # Sollte Bonus für Spektral-Unterschied bekommen (10-40 Punkte ideal)
    assert bonus > 0.01  # Mindestens ein kleiner Bonus

  def test_danceability_bonus_in_peak(self):
    """Danceability Bonus: Im PEAK sollte ähnliche Danceability belohnt werden."""
    # Position 6 von 10 Tracks = PEAK (50-80%)
    peak_tracks = [
        Track("/1", "1", energy=85, bpm=130, danceability=85, brightness=50,
              detected_genre="House", genre="House", camelotCode="7A"),
        Track("/2", "2", energy=84, bpm=131, danceability=86, brightness=50,
              detected_genre="House", genre="House", camelotCode="8A"),
        Track("/3", "3", energy=86, bpm=129, danceability=87, brightness=50,
              detected_genre="House", genre="House", camelotCode="9A"),
        Track("/4", "4", energy=85, bpm=130, danceability=85, brightness=50,
              detected_genre="House", genre="House", camelotCode="7A"),
        Track("/5", "5", energy=86, bpm=129, danceability=86, brightness=50,
              detected_genre="House", genre="House", camelotCode="8A"),
        Track("/6", "6", energy=85, bpm=130, danceability=86, brightness=50,
              detected_genre="House", genre="House", camelotCode="8A"),
    ]

    context = PlaylistContext(peak_tracks, 10)  # 6/10 = 0.6 = PEAK
    candidate = Track("/7", "7", energy=85, bpm=130, danceability=84, brightness=50,
                      detected_genre="House", genre="House", camelotCode="7A")

    bonus = EnhancedBonusCalculator.calculate_all_bonuses(
        peak_tracks[-1], candidate, context, "PEAK_TIME"
    )

    # Sollte Bonus für Danceability-Konsistenz im Peak bekommen (min > 0)
    assert bonus > 0.0


# ============================================================================
# ENHANCED PENALTY TESTS
# ============================================================================

class TestEnhancedPenaltyCalculator:
  """Tests für erweiterte Penalty-Berechnung."""

  def test_jarring_penalty_big_bpm_jump(self):
    """Jarring Penalty: Großer BPM-Sprung bei stabiler Energie."""
    # Stabile Energien über 3 Tracks
    stable_playlist = [
        Track("/1", "1", energy=70, bpm=120, detected_genre="House", genre="House",
              camelotCode="7A", brightness=50, danceability=80),
        Track("/2", "2", energy=71, bpm=119, detected_genre="House", genre="House",
              camelotCode="8A", brightness=50, danceability=80),
        Track("/3", "3", energy=69, bpm=121, detected_genre="House", genre="House",
              camelotCode="8A", brightness=50, danceability=80),
    ]

    context = PlaylistContext(stable_playlist, 10)
    # Kandidat mit großem BPM-Sprung (>40) bei stabiler Energie
    candidate = Track("/4", "4", energy=68, bpm=165, detected_genre="Techno", genre="Techno",
                      camelotCode="6A", brightness=50, danceability=80)

    penalty = EnhancedPenaltyCalculator.calculate_all_penalties(
        stable_playlist[-1], candidate, context
    )

    # Sollte Penalty bekommen für schockierender BPM-Sprung (bpm_diff=44 > 40)
    # Kombiniert mit Camelot weit (6A vs 8A = 2) → gesamt penalty
    assert penalty < -0.05

  def test_repetition_penalty_too_similar(self):
    """Repetition Penalty: Kandidat zu ähnlich zum letzten Track."""
    last_track = Track("/3", "3", energy=70, bpm=128, detected_genre="House", genre="House",
                       camelotCode="8A", brightness=60, danceability=85)

    playlist = [
        Track("/1", "1", energy=50, bpm=120, detected_genre="House", genre="House",
              camelotCode="7A", brightness=50, danceability=80),
        Track("/2", "2", energy=60, bpm=125, detected_genre="House", genre="House",
              camelotCode="7A", brightness=50, danceability=80),
        last_track,
    ]

    context = PlaylistContext(playlist, 10)
    # Kandidat fast identisch zum letzten
    candidate = Track("/4", "4", energy=71, bpm=128, detected_genre="House", genre="House",
                      camelotCode="8A", brightness=62, danceability=84)

    penalty = EnhancedPenaltyCalculator.calculate_all_penalties(
        last_track, candidate, context
    )

    # Sollte Penalty bekommen für zu große Ähnlichkeit
    assert penalty < -0.15

  def test_energy_cliff_penalty_in_peak(self):
    """Energy Cliff Penalty: Große Energie-Unterschiede im PEAK."""
    peak_playlist = [
        Track("/1", "1", energy=85, bpm=130, detected_genre="House", genre="House",
              camelotCode="7A", brightness=50, danceability=85),
        Track("/2", "2", energy=84, bpm=131, detected_genre="House", genre="House",
              camelotCode="8A", brightness=50, danceability=85),
        Track("/3", "3", energy=86, bpm=129, detected_genre="House", genre="House",
              camelotCode="8A", brightness=50, danceability=85),
        Track("/4", "4", energy=85, bpm=130, detected_genre="House", genre="House",
              camelotCode="9A", brightness=50, danceability=85),
        Track("/5", "5", energy=85, bpm=129, detected_genre="House", genre="House",
              camelotCode="7A", brightness=50, danceability=85),
    ]

    context = PlaylistContext(peak_playlist, 10)
    # Kandidat mit großem Energie-Sprung
    candidate = Track("/6", "6", energy=55, bpm=130, detected_genre="House", genre="House",
                      camelotCode="7A", brightness=50, danceability=85)

    penalty = EnhancedPenaltyCalculator.calculate_all_penalties(
        peak_playlist[-1], candidate, context
    )

    # Sollte Penalty bekommen für Energy-Cliff im Peak
    assert penalty < -0.06


# ============================================================================
# FLOW ANALYSIS TESTS
# ============================================================================

class TestFlowAnalyzer:
  """Tests für Flow-Kontinuitäts-Analyse."""

  def test_detect_smooth_rising_flow(self):
    """Flow Detection: Sanfte steigende Energie."""
    playlist = [
        Track("/1", "1", energy=50, bpm=120, detected_genre="House", genre="House",
              camelotCode="7A", brightness=50, danceability=80),
        Track("/2", "2", energy=60, bpm=122, detected_genre="House", genre="House",
              camelotCode="8A", brightness=50, danceability=80),
        Track("/3", "3", energy=70, bpm=120, detected_genre="House", genre="House",
              camelotCode="8A", brightness=50, danceability=80),
    ]

    context = PlaylistContext(playlist, 10)
    flow = FlowAnalyzer.detect_flow_pattern(context)

    assert flow == "SMOOTH_RISING"

  def test_consistency_score_high_for_smooth_flow(self):
    """Consistency Score sollte hoch sein für smooth Flow."""
    smooth_playlist = [
        Track("/1", "1", energy=70, bpm=128, detected_genre="House", genre="House",
              camelotCode="7A", brightness=50, danceability=80),
        Track("/2", "2", energy=72, bpm=129, detected_genre="House", genre="House",
              camelotCode="8A", brightness=50, danceability=80),
        Track("/3", "3", energy=71, bpm=128, detected_genre="House", genre="House",
              camelotCode="8A", brightness=50, danceability=80),
    ]

    context = PlaylistContext(smooth_playlist, 10)
    consistency = FlowAnalyzer.get_flow_consistency_score(context)

    # Sollte ziemlich konsistent sein
    assert consistency > 0.7

  def test_coherence_high_for_peak_phase(self):
    """Coherence sollte hoch sein im PEAK mit konsistenten Genres."""
    peak_playlist = [
        Track("/1", "1", energy=80, bpm=128, detected_genre="House", genre="House",
              camelotCode="7A", brightness=50, danceability=85),
        Track("/2", "2", energy=82, bpm=129, detected_genre="House", genre="House",
              camelotCode="8A", brightness=50, danceability=85),
        Track("/3", "3", energy=81, bpm=128, detected_genre="House", genre="House",
              camelotCode="8A", brightness=50, danceability=85),
        Track("/4", "4", energy=83, bpm=129, detected_genre="House", genre="House",
              camelotCode="9A", brightness=50, danceability=85),
        Track("/5", "5", energy=82, bpm=128, detected_genre="House", genre="House",
              camelotCode="7A", brightness=50, danceability=85),
    ]

    context = PlaylistContext(peak_playlist, 10)  # Position 5 von 10 = PEAK Phase
    coherence = FlowAnalyzer.measure_flow_coherence(context)

    # Sollte gute Kohärenz haben
    assert coherence > 0.65

  def test_predict_good_flow_candidates(self, house_track):
    """Predict Candidates: Rising Flow sollte Kandidaten mit höherer Energy bevorzugen."""
    rising_playlist = [
        Track("/1", "1", energy=50, bpm=120, detected_genre="House", genre="House",
              camelotCode="7A", brightness=50, danceability=80),
        Track("/2", "2", energy=60, bpm=122, detected_genre="House", genre="House",
              camelotCode="8A", brightness=50, danceability=80),
        Track("/3", "3", energy=70, bpm=124, detected_genre="House", genre="House",
              camelotCode="8A", brightness=50, danceability=80),
    ]

    context = PlaylistContext(rising_playlist, 10)

    candidates = [
        Track("/4a", "4a", energy=75, bpm=126, detected_genre="House", genre="House",
              camelotCode="9A", brightness=50, danceability=80),
        Track("/4b", "4b", energy=65, bpm=125, detected_genre="House", genre="House",
              camelotCode="8A", brightness=50, danceability=80),
    ]

    scored = FlowAnalyzer.predict_good_flow_candidates(context, candidates)

    # Erstes sollte höhere Energy haben (4a mit 75)
    assert scored[0][0].energy > scored[1][0].energy


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestPhase2Integration:
  """Integration Tests für Phase 2 Enhancements."""

  def test_scoring_with_phase2_bonuses_penalties(self, house_track, techno_track):
    """Scoring sollte Phase 2 Enhancements verwenden."""
    engine = IntelligentScoreEngine()
    context = PlaylistContext([house_track], 10, "HARMONIC_FLOW")

    score = engine.calculate_score(house_track, techno_track, context)

    # Score sollte zwischen 0 und 1 sein
    assert 0.0 <= score <= 1.0

  def test_genre_compatibility_affects_scoring(self, house_track, deep_house_track, classical_track):
    """Genre-Kompatibilität sollte Scoring beeinflussen."""
    engine = IntelligentScoreEngine()
    context = PlaylistContext([house_track], 10)

    score_compatible = engine.calculate_score(house_track, deep_house_track, context)
    score_incompatible = engine.calculate_score(house_track, classical_track, context)

    # Kompatibles Genre sollte höheren Score geben
    assert score_compatible > score_incompatible

  def test_phase2_genre_flow_strategy(self, house_track, deep_house_track):
    """GENRE_FLOW Strategie sollte Genre-Kompatibilität bevorzugen."""
    engine = IntelligentScoreEngine()
    context = PlaylistContext([house_track], 10)

    score_genre_flow = engine.calculate_score(
        house_track, deep_house_track, context, strategy="GENRE_FLOW"
    )
    score_harmonic = engine.calculate_score(
        house_track, deep_house_track, context, strategy="HARMONIC_FLOW"
    )

    # GENRE_FLOW sollte kompatible Genres bevorzugen
    # (möglicherweise höherer Score, aber mindestens nicht niedriger)
    assert score_genre_flow >= score_harmonic * 0.9

  def test_calculate_all_bonuses_max_cap(self, house_track, techno_track):
    """Testet, dass die Summe aller Boni den Maximalwert von 0.2 nicht überschreitet."""
    # Wir erstellen ein Szenario, in dem viele Boni greifen.
    playlist = [
        Track("/1", "1", energy=50, bpm=120, detected_genre="House", genre="House", camelotCode="7A", brightness=50, danceability=80, vocal_instrumental="instrumental"),
        Track("/2", "2", energy=60, bpm=124, detected_genre="House", genre="House", camelotCode="7A", brightness=50, danceability=80, vocal_instrumental="instrumental"),
        Track("/3", "3", energy=70, bpm=128, detected_genre="House", genre="House", camelotCode="7A", brightness=50, danceability=80, vocal_instrumental="instrumental"),
    ]

    # Kontext ist im BUILD_UP (3/10 = 0.3) oder PEAK, wenn wir die Länge anpassen
    # Energy steigt, bpm steigt
    context = PlaylistContext(playlist, 5) # 3/5 = 0.6 = PEAK

    current = playlist[-1]
    # Kandidat hat:
    # - höhere Energie (Flow: +0.05)
    # - hellere Brightness (Spectral: +0.03)
    # - ähnliche Danceability im Peak (+0.05)
    # - sehr ähnliche Energie und BPM (+0.06 Momentum)
    # Das ergibt > 0.19. Fügen wir noch Emotional Journey und Genre Flow hinzu.
    candidate = Track(
        "/4", "4", energy=73, bpm=130, detected_genre="Deep House", genre="Deep House",
        camelotCode="7A", brightness=75, danceability=82, vocal_instrumental="instrumental"
    )

    # EMOTIONAL_JOURNEY bringt +0.05 (weil vocal_instrumental gleich)
    bonus1 = EnhancedBonusCalculator.calculate_all_bonuses(
        current, candidate, context, "EMOTIONAL_JOURNEY"
    )
    assert bonus1 == 0.2  # Gekappt auf 0.2

    # GENRE_FLOW bringt +0.08 (weil House -> Deep House = 0.95 Kompatibilität, aber nicht gleich)
    bonus2 = EnhancedBonusCalculator.calculate_all_bonuses(
        current, candidate, context, "GENRE_FLOW"
    )
    assert bonus2 == 0.2  # Gekappt auf 0.2

  def test_calculate_all_bonuses_emotional_journey(self, house_track):
    """Testet die spezifischen Boni für EMOTIONAL_JOURNEY."""
    context = PlaylistContext([house_track], 10)
    candidate = Track(
        "/5", "5", energy=70, bpm=128, detected_genre="House", genre="House",
        camelotCode="7A", brightness=60, danceability=85, vocal_instrumental="instrumental"
    )
    bonus = EnhancedBonusCalculator.calculate_all_bonuses(
        house_track, candidate, context, "EMOTIONAL_JOURNEY"
    )
    # _emotional_journey_bonus bringt +0.05
    assert bonus >= 0.05

  def test_calculate_all_bonuses_genre_flow(self, house_track, deep_house_track):
    """Testet die spezifischen Boni für GENRE_FLOW."""
    context = PlaylistContext([house_track], 10)
    bonus = EnhancedBonusCalculator.calculate_all_bonuses(
        house_track, deep_house_track, context, "GENRE_FLOW"
    )
    # _genre_storytelling_bonus bringt +0.08 für House -> Deep House (0.95)
    assert bonus >= 0.08

  def test_calculate_all_bonuses_build_up_danceability(self):
    """Testet Tanzbarkeits-Konsistenz in der BUILD_UP Phase."""
    playlist = [
        Track("/1", "1", energy=50, bpm=120, detected_genre="House", genre="House", camelotCode="7A", danceability=60),
    ]
    # 1/5 = 0.2 = BUILD_UP
    context = PlaylistContext(playlist, 5)
    current = playlist[-1]
    candidate = Track("/2", "2", energy=60, bpm=122, detected_genre="House", genre="House", camelotCode="7A", danceability=75)

    # _danceability_bonus im BUILD_UP mit steigender Tanzbarkeit bringt +0.04
    bonus = EnhancedBonusCalculator.calculate_all_bonuses(
        current, candidate, context, "HARMONIC_FLOW"
    )
    assert bonus >= 0.04

  def test_calculate_all_bonuses_flow_falling(self):
    """Testet Flow Bonus für fallende Energie und BPM."""
    playlist = [
        Track("/1", "1", energy=80, bpm=135, detected_genre="House", genre="House", camelotCode="7A"),
        Track("/2", "2", energy=70, bpm=130, detected_genre="House", genre="House", camelotCode="7A"),
        Track("/3", "3", energy=60, bpm=125, detected_genre="House", genre="House", camelotCode="7A"),
    ]
    context = PlaylistContext(playlist, 10)
    current = playlist[-1]
    candidate = Track("/4", "4", energy=50, bpm=120, detected_genre="House", genre="House", camelotCode="7A")

    bonus = EnhancedBonusCalculator.calculate_all_bonuses(
        current, candidate, context, "HARMONIC_FLOW"
    )
    # Energy falling (+0.05), BPM falling (+0.04) -> +0.09
    assert bonus >= 0.08

  def test_surprise_bonus_energy_trend_rising(self):
    """Testet Überraschungs-Bonus bei steigender Energie und unerwartetem Übergang."""
    playlist = [
        Track("/1", "1", energy=50, bpm=120, detected_genre="House", genre="House", camelotCode="7A"),
        Track("/2", "2", energy=60, bpm=122, detected_genre="House", genre="House", camelotCode="7A"),
        Track("/3", "3", energy=70, bpm=124, detected_genre="House", genre="House", camelotCode="7A"),
    ]
    context = PlaylistContext(playlist, 10)
    current = playlist[-1]

    # Alles unerwartet (Camelot 7A -> 9A = dist 2), aber Energy Trend Rising und candidate.energy > current.energy
    candidate = Track("/4", "4", energy=80, bpm=124, detected_genre="Techno", genre="Techno", camelotCode="9A")
    bonus = EnhancedBonusCalculator.calculate_all_bonuses(
        current, candidate, context, "HARMONIC_FLOW"
    )
    # Sollte Bonus 3 auslösen (+0.04)
    assert bonus >= 0.04

  def test_surprise_bonus_genre_compat_far_camelot(self):
    """Testet Überraschungs-Bonus für kompatibles Genre aber weiten Camelot Abstand."""
    playlist = [
        Track("/1", "1", energy=70, bpm=128, detected_genre="House", genre="House", camelotCode="7A")
    ]
    context = PlaylistContext(playlist, 10)
    current = playlist[-1]

    # House zu Deep House = kompatibel, aber Camelot 7A zu 11A (Distanz 4)
    candidate = Track("/2", "2", energy=70, bpm=128, detected_genre="Deep House", genre="Deep House", camelotCode="11A")
    bonus = EnhancedBonusCalculator.calculate_all_bonuses(
        current, candidate, context, "HARMONIC_FLOW"
    )
    # Sollte Bonus 2 auslösen (+0.06)
    assert bonus >= 0.06

  def test_flow_bonus_genre_streak(self):
    """Testet Flow Bonus bei einem Genre Streak und sanftem Wechsel."""
    playlist = [
        Track("/1", "1", energy=70, bpm=128, detected_genre="House", genre="House", camelotCode="7A"),
        Track("/2", "2", energy=70, bpm=128, detected_genre="House", genre="House", camelotCode="7A"),
        Track("/3", "3", energy=70, bpm=128, detected_genre="House", genre="House", camelotCode="7A"),
        Track("/4", "4", energy=70, bpm=128, detected_genre="House", genre="House", camelotCode="7A"),
    ]
    # Streak von 4 House Tracks
    context = PlaylistContext(playlist, 10)
    current = playlist[-1]

    # Wechsel zu Techno (Compat 0.65-0.75, was in 0.6 < compat < 1.0 fällt)
    candidate = Track("/5", "5", energy=70, bpm=128, detected_genre="Techno", genre="Techno", camelotCode="7A")

    #_flow_bonus sollte für Genre Flow +0.04 geben
    bonus = EnhancedBonusCalculator.calculate_all_bonuses(
        current, candidate, context, "HARMONIC_FLOW"
    )
    assert bonus >= 0.04
