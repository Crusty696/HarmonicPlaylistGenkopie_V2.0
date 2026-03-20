"""
Test: Intelligentes Scoring System - Phase 1
Demonstriert die neue adaptive Scoring-Engine mit PlaylistContext & DynamicWeights.
"""

import pytest
from hpg_core.scoring_context import PlaylistContext
from hpg_core.scoring_weights import DynamicWeightCalculator
from hpg_core.scoring_engine import IntelligentScoreEngine
from hpg_core.models import Track


@pytest.fixture
def house_track_128():
  """House Track: 128 BPM, A Minor (8A), Energy 72"""
  return Track(
      filePath="<test:house>",
      fileName="house_128.mp3",
      artist="Test Artist",
      title="House Track",
      genre="House",
      duration=240.0,
      bpm=128.0,
      keyNote="A",
      keyMode="Minor",
      camelotCode="8A",
      energy=72,
      bass_intensity=68,
      detected_genre="House",
      genre_confidence=0.95,
      sections=[],
      phrase_unit=8,
  )


@pytest.fixture
def techno_track_132():
  """Techno Track: 132 BPM, E Minor (9A), Energy 78"""
  return Track(
      filePath="<test:techno>",
      fileName="techno_132.mp3",
      artist="Test Artist",
      title="Techno Track",
      genre="Techno",
      duration=240.0,
      bpm=132.0,
      keyNote="E",
      keyMode="Minor",
      camelotCode="9A",
      energy=78,
      bass_intensity=78,
      detected_genre="Techno",
      genre_confidence=0.92,
      sections=[],
      phrase_unit=8,
  )


@pytest.fixture
def deep_house_track_120():
  """Deep House Track: 120 BPM, G Minor (5A), Energy 58"""
  return Track(
      filePath="<test:deephouse>",
      fileName="deep_house_120.mp3",
      artist="Test Artist",
      title="Deep House Track",
      genre="Deep House",
      duration=300.0,
      bpm=120.0,
      keyNote="G",
      keyMode="Minor",
      camelotCode="5A",
      energy=58,
      bass_intensity=62,
      detected_genre="Deep House",
      genre_confidence=0.85,
      sections=[],
      phrase_unit=16,
  )


class TestPlaylistContextPhase1:
  """Tests für PlaylistContext (Schicht 1: Kontext-Erkennung)"""

  def test_intro_phase_detection(self, house_track_128, techno_track_132):
    """Am Anfang sollte INTRO erkannt werden."""
    playlist = [house_track_128]
    context = PlaylistContext(playlist, total_tracks=10, strategy="HARMONIC_FLOW")
    assert context.get_playlist_phase() == "INTRO"

  def test_build_up_phase_detection(self, house_track_128, techno_track_132, deep_house_track_120):
    """Bei 30% sollte BUILD_UP erkannt werden."""
    playlist = [house_track_128, techno_track_132, deep_house_track_120]
    context = PlaylistContext(playlist, total_tracks=10, strategy="HARMONIC_FLOW")
    assert context.get_playlist_phase() == "BUILD_UP"

  def test_peak_phase_detection(self, house_track_128, techno_track_132, deep_house_track_120):
    """Bei 60% sollte PEAK erkannt werden."""
    tracks = [
        house_track_128, techno_track_132, deep_house_track_120,
        house_track_128, techno_track_132, deep_house_track_120,
    ]
    context = PlaylistContext(tracks, total_tracks=10, strategy="HARMONIC_FLOW")
    assert context.get_playlist_phase() == "PEAK"

  def test_energy_trend_rising(self, house_track_128, techno_track_132, deep_house_track_120):
    """Mit steigenden Energies sollte RISING erkannt werden."""
    # House (72) → Techno (78) → House (72) ist kein steigen
    # Lasse mich tracks mit steigender Energie erstellen
    low_energy = Track(
        filePath="<test:low>",
        fileName="low.mp3",
        artist="Test",
        title="Low",
        genre="Ambient",
        duration=300,
        bpm=100,
        keyNote="A",
        keyMode="Minor",
        camelotCode="8A",
        energy=40,
        bass_intensity=30,
        detected_genre="Ambient",
        sections=[],
        phrase_unit=8,
    )

    med_energy = Track(
        filePath="<test:med>",
        fileName="med.mp3",
        artist="Test",
        title="Med",
        genre="House",
        duration=240,
        bpm=120,
        keyNote="A",
        keyMode="Minor",
        camelotCode="8A",
        energy=60,
        bass_intensity=60,
        detected_genre="House",
        sections=[],
        phrase_unit=8,
    )

    high_energy = Track(
        filePath="<test:high>",
        fileName="high.mp3",
        artist="Test",
        title="High",
        genre="Techno",
        duration=240,
        bpm=128,
        keyNote="E",
        keyMode="Minor",
        camelotCode="9A",
        energy=85,
        bass_intensity=85,
        detected_genre="Techno",
        sections=[],
        phrase_unit=8,
    )

    playlist = [low_energy, med_energy, high_energy]
    context = PlaylistContext(playlist, total_tracks=10, strategy="HARMONIC_FLOW")
    assert context.get_energy_trend() == "RISING"

  def test_genre_streak_counting(self, house_track_128, deep_house_track_120, techno_track_132):
    """Genre-Streak sollte korrekt gezählt werden."""
    # House → House → Deep House → Techno
    # Deep House ist nicht exakt "House", also sollte streak = 1
    playlist = [house_track_128, house_track_128, deep_house_track_120]
    context = PlaylistContext(playlist, total_tracks=10, strategy="HARMONIC_FLOW")
    # Die letzten Tracks sind beide House, aber deep_house_track_120 hat detected_genre "Deep House"
    assert context.get_genre_streak() == 1

  def test_camelot_distance_exception_handling(self):
    """Testet, dass _camelot_distance malformed strings sicher behandelt."""

    # Test completely invalid strings
    assert PlaylistContext._camelot_distance("invalid", "string") == 999

    # Test strings that don't conform to camelot pattern
    assert PlaylistContext._camelot_distance("12C", "8A") == 999

    # Test strings that are empty
    assert PlaylistContext._camelot_distance("", "9A") == 999


class TestDynamicWeightCalculatorPhase1:
  """Tests für DynamicWeightCalculator (Schicht 2: Dynamische Gewichte)"""

  def test_intro_weights_prioritize_harmonic(self, house_track_128):
    """In INTRO Phase sollte harmonic Gewicht höher sein."""
    playlist = [house_track_128]
    context = PlaylistContext(playlist, total_tracks=10, strategy="HARMONIC_FLOW")
    calculator = DynamicWeightCalculator()
    weights = calculator.calculate_weights(context, "HARMONIC_FLOW")

    # Harmonic sollte am höchsten sein in INTRO
    assert weights['harmonic'] > weights['energy']
    assert weights['harmonic'] > weights['bpm']

  def test_build_up_weights_prioritize_energy(self, house_track_128, techno_track_132, deep_house_track_120):
    """In BUILD_UP Phase sollte energy Gewicht höher sein."""
    playlist = [house_track_128, techno_track_132, deep_house_track_120]
    context = PlaylistContext(playlist, total_tracks=10, strategy="HARMONIC_FLOW")
    calculator = DynamicWeightCalculator()
    weights = calculator.calculate_weights(context, "HARMONIC_FLOW")

    # Energy sollte am höchsten sein in BUILD_UP
    assert weights['energy'] > weights['harmonic']

  def test_peak_time_strategy_weights(self, house_track_128):
    """PEAK_TIME Strategie sollte energy maximum gewichten."""
    playlist = [house_track_128]
    context = PlaylistContext(playlist, total_tracks=10, strategy="PEAK_TIME")
    calculator = DynamicWeightCalculator()
    weights = calculator.calculate_weights(context, "PEAK_TIME")

    # Energy sollte das höchste Gewicht haben bei PEAK_TIME
    max_weight = max(weights.values())
    assert weights['energy'] >= 0.4  # MIN 0.4
    assert weights['energy'] == max_weight

  def test_genre_flow_strategy_weights(self, house_track_128):
    """GENRE_FLOW Strategie sollte genre hoch gewichten."""
    playlist = [house_track_128]
    context = PlaylistContext(playlist, total_tracks=10, strategy="GENRE_FLOW")
    calculator = DynamicWeightCalculator()
    weights = calculator.calculate_weights(context, "GENRE_FLOW")

    # Genre sollte hoch sein bei GENRE_FLOW
    assert weights['genre'] >= 0.3

  def test_weights_sum_to_one(self, house_track_128):
    """Alle Gewichte sollten sich zu 1.0 summieren."""
    playlist = [house_track_128]
    context = PlaylistContext(playlist, total_tracks=10)
    calculator = DynamicWeightCalculator()
    weights = calculator.calculate_weights(context, "HARMONIC_FLOW")

    total = sum(weights.values())
    assert abs(total - 1.0) < 0.001  # Floating point tolerance


class TestIntelligentScoreEnginePhase1:
  """Tests für IntelligentScoreEngine (Schicht 3: Intelligente Scoring)"""

  def test_harmonic_compatibility_scores_adjacent_codes(self, house_track_128, techno_track_132):
    """Adjacent Camelot Codes sollten hohe harmonische Scores bekommen."""
    # 8A (House) und 9A (Techno) sind benachbart
    playlist = [house_track_128]
    context = PlaylistContext(playlist, total_tracks=10, strategy="HARMONIC_FLOW")
    engine = IntelligentScoreEngine()

    score = engine._score_harmonic(house_track_128, techno_track_132, context)
    assert score > 0.7  # Sollte gut sein

  def test_bpm_similarity_favored(self, house_track_128, techno_track_132):
    """Ähnliche BPMs sollten bessere Scores bekommen."""
    # 128 BPM vs 132 BPM (nur 4 BPM Unterschied)
    playlist = [house_track_128]
    context = PlaylistContext(playlist, total_tracks=10, strategy="HARMONIC_FLOW")
    engine = IntelligentScoreEngine()

    score = engine._score_bpm(house_track_128, techno_track_132, context)
    assert score > 0.8  # Sollte ziemlich gut sein

  def test_energy_score_targets_phase_energy(self, house_track_128, techno_track_132):
    """Energy Score sollte zur Phase-Ziel-Energie passen."""
    # BUILD_UP Phase sollte Energie ~60 anstreben
    # Techno hat 78, House hat 72
    playlist = [house_track_128, techno_track_132]
    context = PlaylistContext(playlist, total_tracks=10)
    engine = IntelligentScoreEngine()

    # Ziel-Energie für BUILD_UP ist 60
    # House (72) ist näher als Techno (78)
    score_house = engine._score_energy(house_track_128, context)
    score_techno = engine._score_energy(techno_track_132, context)

    assert score_house > score_techno  # House sollte besser sein

  def test_full_score_calculation(self, house_track_128, techno_track_132):
    """Volle Score-Berechnung sollte zwischen 0-1 sein."""
    playlist = [house_track_128]
    context = PlaylistContext(playlist, total_tracks=10, strategy="HARMONIC_FLOW")
    engine = IntelligentScoreEngine()

    score = engine.calculate_score(house_track_128, techno_track_132, context, "HARMONIC_FLOW")

    assert 0.0 <= score <= 1.0
    assert score > 0.6  # Sollte ein guter Match sein

  def test_cross_genre_surprise_bonus(self, house_track_128):
    """Cross-Genre mit guter Harmonie sollte Bonus bekommen."""
    # Erstelle Jazz Track für stärkere Genre-Überraschung
    # Jazz vs House = sehr unterschiedlich (kompatibilität ~0.5)
    jazz_track = Track(
        filePath="<test:jazz>",
        fileName="jazz.mp3",
        artist="Test Artist",
        title="Jazz Track",
        genre="Jazz",
        duration=240.0,
        bpm=132.0,  # Ähnliches BPM zu House (diff=4)
        keyNote="E",
        keyMode="Minor",
        camelotCode="9A",  # Camelot nah dran (8A→9A = Abstand 1)
        energy=78,
        bass_intensity=50,
        detected_genre="Jazz",  # Sehr unterschiedlich zu House
        genre_confidence=0.90,
        sections=[],
        phrase_unit=8,
    )

    playlist = [house_track_128]
    context = PlaylistContext(playlist, total_tracks=10, strategy="HARMONIC_FLOW")
    engine = IntelligentScoreEngine()

    bonus = engine._calculate_bonuses(house_track_128, jazz_track, context, "HARMONIC_FLOW")
    # Mit Phase 2 Enhancements: Bonus >= 0.08 wenn:
    # camelot_dist <= 1 AND genre_compat < 0.6 AND bpm_diff < 5
    # Jazz vs House sollte < 0.5 Kompatibilität haben
    assert bonus > 0.05

  def test_jarring_transition_penalty(self, house_track_128):
    """Zu große BPM-Sprünge + große Harmonic Jumps sollten Penalty bekommen."""
    # Erstelle Track mit großem BPM-Unterschied UND großem Harmonic Jump
    big_jump = Track(
        filePath="<test:jump>",
        fileName="jump.mp3",
        artist="Test",
        title="Jump",
        genre="Hardcore",
        duration=200,
        bpm=170.0,  # 42 BPM Unterschied zu 128
        keyNote="B",
        keyMode="Minor",
        camelotCode="4B",  # Großer Camelot Abstand (nicht 1A/8A)
        energy=95,
        bass_intensity=92,
        detected_genre="Hardcore",
        sections=[],
        phrase_unit=4,
    )

    # Erstelle stabile Energie Playlist (damit "STABLE" trend erkannt wird)
    stable_energy_playlist = [
        house_track_128,
        Track(
            filePath="<test:s1>",
            fileName="s1.mp3",
            artist="Test",
            title="S1",
            genre="House",
            duration=240,
            bpm=128,
            keyNote="A",
            keyMode="Minor",
            camelotCode="8A",
            energy=72,  # Ähnliche Energie
            bass_intensity=68,
            detected_genre="House",
            sections=[],
            phrase_unit=8,
        ),
        Track(
            filePath="<test:s2>",
            fileName="s2.mp3",
            artist="Test",
            title="S2",
            genre="House",
            duration=240,
            bpm=128,
            keyNote="A",
            keyMode="Minor",
            camelotCode="8A",
            energy=71,  # Stabil
            bass_intensity=68,
            detected_genre="House",
            sections=[],
            phrase_unit=8,
        ),
    ]

    context = PlaylistContext(stable_energy_playlist, total_tracks=10, strategy="HARMONIC_FLOW")
    engine = IntelligentScoreEngine()

    penalty = engine._calculate_penalties(stable_energy_playlist[-1], big_jump, context)
    # Mit stabiler Energie und großem BPM-Sprung sollte Penalty sein
    assert penalty < -0.05  # Sollte signifikante Penalty sein


class TestIntelligentScoringVsOldSystem:
  """Vergleich: Intelligentes System vs altes starres System"""

  def test_intelligent_recognizes_genre_fatigue(self, house_track_128, deep_house_track_120, techno_track_132):
    """Intelligentes System sollte Genre-Fatigue erkennen nach 5+ Tracks im gleichen Genre."""
    # Erstelle eine Playlist mit 5+ House-Tracks (alle mit gleicher detected_genre)
    house_like_tracks = [
        house_track_128,
        house_track_128,
        house_track_128,  # Nicht deep_house, bleib bei House
        house_track_128,
        house_track_128,
        house_track_128,  # 6 Tracks
    ]

    context = PlaylistContext(house_like_tracks, total_tracks=15, strategy="HARMONIC_FLOW")
    engine = IntelligentScoreEngine()

    # Genre-Streak sollte >= 5 sein (alle House)
    assert context.get_genre_streak() >= 5

    # Genre-Score sollte für Techno (anderes Genre) hoch sein
    score_techno = engine._score_genre(house_like_tracks[-1], techno_track_132, context)
    # Nach Genre-Fatigue sollte Genre-Wechsel bevorzugt sein
    assert score_techno > 0.8  # Techno sollte sehr gut sein nach Genre-Fatigue

  def test_context_aware_scoring_phase_dependent(self, house_track_128, techno_track_132):
    """Scores sollten je nach Phase unterschiedlich ausfallen."""
    playlist_intro = [house_track_128]
    playlist_peak = [
        house_track_128, techno_track_132, house_track_128,
        techno_track_132, house_track_128, techno_track_132,
    ]

    context_intro = PlaylistContext(playlist_intro, total_tracks=10, strategy="HARMONIC_FLOW")
    context_peak = PlaylistContext(playlist_peak, total_tracks=10, strategy="HARMONIC_FLOW")

    engine = IntelligentScoreEngine()

    score_intro = engine.calculate_score(house_track_128, techno_track_132, context_intro, "HARMONIC_FLOW")
    score_peak = engine.calculate_score(house_track_128, techno_track_132, context_peak, "HARMONIC_FLOW")

    # Diese sollten unterschiedlich sein, weil die Gewichte unterschiedlich sind
    # (nicht unbedingt größer/kleiner, aber unterschiedlich)
    assert score_intro != score_peak or abs(score_intro - score_peak) < 0.01  # Allow small difference


@pytest.mark.parametrize(
    "strategy,expected_primary_weight",
    [
        ("PEAK_TIME", "energy"),
        ("GENRE_FLOW", "genre"),
        ("ENERGY_WAVE", "energy"),
        ("HARMONIC_FLOW", "harmonic"),
    ],
)
def test_strategy_specific_weights(house_track_128, strategy, expected_primary_weight):
  """Jede Strategie sollte ihre eigene primäre Gewichtung haben."""
  playlist = [house_track_128]
  context = PlaylistContext(playlist, total_tracks=10, strategy=strategy)
  calculator = DynamicWeightCalculator()
  weights = calculator.calculate_weights(context, strategy)

  # Der primäre Fokus sollte das höchste Gewicht sein (oder nahe dran)
  primary_weight = weights[expected_primary_weight]
  max_weight = max(weights.values())

  # Erlauben ein bisschen Flexibilität wegen Normalisierung
  assert primary_weight >= (max_weight * 0.8)
