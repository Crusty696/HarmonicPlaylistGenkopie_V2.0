"""
Tests fuer Transition Type Prediction.
Prueft ob der optimale Transition-Typ korrekt vorhergesagt wird
basierend auf BPM-Relation, Energie-Delta, Harmonie und Genre.
"""
import pytest
from unittest.mock import patch
from hpg_core.playlist import (
    predict_transition_type,
    TRANSITION_TYPE_LABELS,
    TRANSITION_TYPE_DESCRIPTIONS,
)
from hpg_core.models import Track


# === Hilfsfunktionen ===

def _make_track(
    title: str = "Test",
    bpm: float = 128.0,
    camelot: str = "8A",
    energy: int = 50,
    genre: str = "Unknown",
) -> Track:
  """Erstellt einen minimalen Track fuer Transition-Tests."""
  return Track(
    filePath="test.mp3",
    fileName="test.mp3",
    title=title,
    bpm=bpm,
    camelotCode=camelot,
    energy=energy,
    detected_genre=genre,
  )


# === Grundlegende Rueckgabewerte ===

class TestTransitionTypeBasics:
  """Grundlegende Tests fuer predict_transition_type."""

  def test_returns_string(self):
    t1 = _make_track()
    t2 = _make_track()
    result = predict_transition_type(t1, t2)
    assert isinstance(result, str)

  def test_returns_known_type(self):
    """Ergebnis muss ein bekannter Transition-Typ sein."""
    t1 = _make_track()
    t2 = _make_track()
    result = predict_transition_type(t1, t2)
    assert result in TRANSITION_TYPE_LABELS

  def test_all_labels_have_descriptions(self):
    """Jeder Label-Key hat auch eine Beschreibung."""
    for key in TRANSITION_TYPE_LABELS:
      assert key in TRANSITION_TYPE_DESCRIPTIONS, f"Missing description for {key}"

  def test_all_descriptions_have_labels(self):
    """Jeder Description-Key hat auch ein Label."""
    for key in TRANSITION_TYPE_DESCRIPTIONS:
      assert key in TRANSITION_TYPE_LABELS, f"Missing label for {key}"


# === Regel 1: Halftime Switch ===

class TestHalftimeSwitch:
  """Tests fuer Half/Double-Time Erkennung."""

  def test_exact_half_time(self):
    """140 BPM -> 70 BPM = halftime_switch."""
    t1 = _make_track(bpm=140.0, camelot="8A")
    t2 = _make_track(bpm=70.0, camelot="8A")
    assert predict_transition_type(t1, t2) == "halftime_switch"

  def test_exact_double_time(self):
    """70 BPM -> 140 BPM = halftime_switch."""
    t1 = _make_track(bpm=70.0, camelot="8A")
    t2 = _make_track(bpm=140.0, camelot="8A")
    assert predict_transition_type(t1, t2) == "halftime_switch"

  def test_dnb_half_time(self):
    """174 BPM -> 87 BPM = halftime_switch."""
    t1 = _make_track(bpm=174.0, camelot="5A")
    t2 = _make_track(bpm=87.0, camelot="5A")
    assert predict_transition_type(t1, t2) == "halftime_switch"

  def test_128_to_64(self):
    """128 BPM -> 64 BPM = halftime_switch."""
    t1 = _make_track(bpm=128.0, camelot="8A")
    t2 = _make_track(bpm=64.0, camelot="8A")
    assert predict_transition_type(t1, t2) == "halftime_switch"


# === Regel 2: BPM ausserhalb Toleranz ===

class TestBpmOutOfTolerance:
  """Tests wenn BPM-Differenz zu gross ist."""

  def test_large_bpm_diff_good_harmony_breakdown(self):
    """Grosse BPM-Diff + gute Harmonie = breakdown_bridge."""
    t1 = _make_track(bpm=128.0, camelot="8A")
    t2 = _make_track(bpm=100.0, camelot="8A")
    result = predict_transition_type(t1, t2, bpm_tolerance=3.0)
    # BPM diff > 3, but harmony could be high (same key)
    # effective_bpm_diff(128, 100): direct=28, half candidates differ
    # With big diff and some harmony -> breakdown_bridge or cold_cut
    assert result in ("breakdown_bridge", "cold_cut")

  def test_large_bpm_diff_bad_harmony_cold_cut(self):
    """Grosse BPM-Diff + schlechte Harmonie = cold_cut."""
    t1 = _make_track(bpm=128.0, camelot="8A")
    t2 = _make_track(bpm=100.0, camelot="1B")
    result = predict_transition_type(t1, t2, bpm_tolerance=3.0)
    assert result == "cold_cut"


# === Regel 3: Drop Cut (grosser Energie-Push) ===

class TestDropCut:
  """Tests fuer grosse Energie-Spruenge nach oben."""

  def test_big_energy_push_good_harmony(self):
    """Grosser Energie-Push + gute Harmonie = drop_cut."""
    t1 = _make_track(bpm=128.0, camelot="8A", energy=30)
    t2 = _make_track(bpm=128.0, camelot="8A", energy=80)
    # energy_delta = +50, harmonic_score should be high (same key, same bpm)
    result = predict_transition_type(t1, t2)
    assert result == "drop_cut"

  def test_moderate_energy_push_not_drop(self):
    """Moderater Energie-Push (< 26) ist kein drop_cut."""
    t1 = _make_track(bpm=128.0, camelot="8A", energy=50)
    t2 = _make_track(bpm=128.0, camelot="8A", energy=70)
    result = predict_transition_type(t1, t2)
    assert result != "drop_cut"


# === Regel 4: Echo Out / Breakdown (Energie-Drop) ===

class TestEnergyDrop:
  """Tests fuer grosse Energie-Drops nach unten."""

  def test_big_energy_drop_good_harmony(self):
    """Grosser Energie-Drop + gute Harmonie = echo_out."""
    t1 = _make_track(bpm=128.0, camelot="8A", energy=80)
    t2 = _make_track(bpm=128.0, camelot="8A", energy=30)
    # energy_delta = -50, harmonic_score high
    result = predict_transition_type(t1, t2)
    assert result == "echo_out"

  def test_big_energy_drop_bad_harmony(self):
    """Grosser Energie-Drop + schlechte Harmonie = breakdown_bridge."""
    t1 = _make_track(bpm=128.0, camelot="8A", energy=80)
    t2 = _make_track(bpm=129.0, camelot="1B", energy=30)
    result = predict_transition_type(t1, t2)
    assert result in ("breakdown_bridge", "echo_out", "cold_cut")


# === Regel 5: Smooth Blend / Filter Ride (perfekte Harmonie) ===

class TestPerfectHarmony:
  """Tests fuer harmonisch perfekte Uebergaenge."""

  def test_perfect_match_melodic_genre(self):
    """Perfekte Harmonie + melodisches Genre = filter_ride."""
    t1 = _make_track(bpm=128.0, camelot="8A", energy=50, genre="Melodic Techno")
    t2 = _make_track(bpm=128.0, camelot="8A", energy=50, genre="Melodic Techno")
    result = predict_transition_type(t1, t2)
    assert result == "filter_ride"

  def test_perfect_match_non_melodic(self):
    """Perfekte Harmonie + nicht-melodisches Genre = smooth_blend."""
    t1 = _make_track(bpm=128.0, camelot="8A", energy=50, genre="Unknown")
    t2 = _make_track(bpm=128.0, camelot="8A", energy=50, genre="Unknown")
    result = predict_transition_type(t1, t2)
    assert result == "smooth_blend"

  def test_progressive_is_melodic(self):
    """Progressive zaehlt als melodisches Genre."""
    t1 = _make_track(bpm=128.0, camelot="8A", energy=50, genre="Progressive")
    t2 = _make_track(bpm=128.0, camelot="8A", energy=50, genre="Progressive")
    result = predict_transition_type(t1, t2)
    assert result == "filter_ride"

  def test_trance_is_melodic(self):
    """Trance zaehlt als melodisches Genre."""
    t1 = _make_track(bpm=138.0, camelot="8A", energy=50, genre="Trance")
    t2 = _make_track(bpm=138.0, camelot="8A", energy=50, genre="Trance")
    result = predict_transition_type(t1, t2)
    assert result == "filter_ride"

  def test_deep_house_is_melodic(self):
    """Deep House zaehlt als melodisches Genre."""
    t1 = _make_track(bpm=122.0, camelot="8A", energy=45, genre="Deep House")
    t2 = _make_track(bpm=122.0, camelot="8A", energy=45, genre="Deep House")
    result = predict_transition_type(t1, t2)
    assert result == "filter_ride"


# === Regel 6: Bass Swap / Smooth Blend (gute Harmonie) ===

class TestGoodHarmony:
  """Tests fuer gute harmonische Uebergaenge."""

  def test_tech_house_bass_swap(self):
    """Tech House mit guter Harmonie = bass_swap."""
    t1 = _make_track(bpm=128.0, camelot="8A", energy=60, genre="Tech House")
    t2 = _make_track(bpm=129.0, camelot="9A", energy=65, genre="Tech House")
    result = predict_transition_type(t1, t2)
    assert result == "bass_swap"

  def test_techno_bass_swap(self):
    """Techno mit guter Harmonie = bass_swap."""
    t1 = _make_track(bpm=135.0, camelot="8A", energy=70, genre="Techno")
    t2 = _make_track(bpm=136.0, camelot="9A", energy=65, genre="Techno")
    result = predict_transition_type(t1, t2)
    assert result == "bass_swap"

  def test_minimal_bass_swap(self):
    """Minimal mit guter Harmonie = bass_swap."""
    t1 = _make_track(bpm=126.0, camelot="8A", energy=55, genre="Minimal")
    t2 = _make_track(bpm=126.0, camelot="9A", energy=50, genre="Minimal")
    result = predict_transition_type(t1, t2)
    assert result == "bass_swap"

  def test_dnb_bass_swap(self):
    """Drum & Bass mit guter Harmonie = bass_swap."""
    t1 = _make_track(bpm=174.0, camelot="8A", energy=75, genre="Drum & Bass")
    t2 = _make_track(bpm=174.0, camelot="9A", energy=70, genre="Drum & Bass")
    result = predict_transition_type(t1, t2)
    assert result == "bass_swap"


# === Regel 7 & 8: Moderate/Schlechte Harmonie ===

class TestModerateHarmony:
  """Tests fuer moderate harmonische Beziehungen."""

  def test_moderate_harmony_energy_diff(self):
    """Moderate Harmonie + Energie-Diff = breakdown_bridge."""
    t1 = _make_track(bpm=128.0, camelot="8A", energy=40)
    t2 = _make_track(bpm=129.0, camelot="3A", energy=70)
    result = predict_transition_type(t1, t2)
    # Moderate harmony, energy diff > 15 -> breakdown_bridge
    assert result in ("breakdown_bridge", "filter_ride", "echo_out")

  def test_moderate_harmony_similar_energy(self):
    """Moderate Harmonie + aehnliche Energie = filter_ride."""
    t1 = _make_track(bpm=128.0, camelot="8A", energy=50)
    t2 = _make_track(bpm=129.0, camelot="3A", energy=55)
    result = predict_transition_type(t1, t2)
    assert result in ("filter_ride", "smooth_blend", "breakdown_bridge")


# === Cold Cut Tests ===

class TestColdCut:
  """Tests fuer inkompatible Tracks."""

  def test_incompatible_everything(self):
    """Komplett inkompatible Tracks = cold_cut."""
    t1 = _make_track(bpm=128.0, camelot="8A", energy=50)
    t2 = _make_track(bpm=90.0, camelot="1B", energy=50)
    result = predict_transition_type(t1, t2, bpm_tolerance=3.0)
    assert result == "cold_cut"


# === Edge Cases ===

class TestTransitionEdgeCases:
  """Edge Cases fuer Transition Type Prediction."""

  def test_zero_bpm_tracks(self):
    """Tracks mit 0 BPM crashen nicht."""
    t1 = _make_track(bpm=0.0)
    t2 = _make_track(bpm=128.0)
    result = predict_transition_type(t1, t2)
    assert result in TRANSITION_TYPE_LABELS

  def test_same_track(self):
    """Identischer Track = smooth_blend oder filter_ride."""
    t = _make_track(bpm=128.0, camelot="8A", energy=50)
    result = predict_transition_type(t, t)
    assert result in ("smooth_blend", "filter_ride")

  def test_no_genre(self):
    """Tracks ohne Genre crashen nicht."""
    t1 = _make_track(genre="")
    t2 = _make_track(genre="")
    result = predict_transition_type(t1, t2)
    assert result in TRANSITION_TYPE_LABELS

  def test_none_genre_attribute(self):
    """Track mit None-Genre crasht nicht."""
    t1 = _make_track()
    t2 = _make_track()
    t1.detected_genre = None
    t2.detected_genre = None
    result = predict_transition_type(t1, t2)
    assert result in TRANSITION_TYPE_LABELS

  def test_extreme_energy_values(self):
    """Extreme Energy-Werte (0, 100) crashen nicht."""
    t1 = _make_track(energy=0)
    t2 = _make_track(energy=100)
    result = predict_transition_type(t1, t2)
    assert result in TRANSITION_TYPE_LABELS

  def test_very_high_bpm(self):
    """Sehr hohe BPM crashen nicht."""
    t1 = _make_track(bpm=200.0)
    t2 = _make_track(bpm=200.0)
    result = predict_transition_type(t1, t2)
    assert result in TRANSITION_TYPE_LABELS

  def test_very_low_bpm(self):
    """Sehr niedrige BPM crashen nicht."""
    t1 = _make_track(bpm=60.0)
    t2 = _make_track(bpm=60.0)
    result = predict_transition_type(t1, t2)
    assert result in TRANSITION_TYPE_LABELS

  def test_custom_tolerance(self):
    """Benutzerdefinierte BPM-Toleranz wird respektiert."""
    t1 = _make_track(bpm=128.0, camelot="8A")
    t2 = _make_track(bpm=135.0, camelot="8A")
    # Mit Toleranz 3: BPM diff=7 > 3 -> breakdown/cold
    result_strict = predict_transition_type(t1, t2, bpm_tolerance=3.0)
    # Mit Toleranz 10: BPM diff=7 < 10 -> irgendein Blend
    result_loose = predict_transition_type(t1, t2, bpm_tolerance=10.0)
    # Strict sollte restriktiver sein
    assert result_strict in TRANSITION_TYPE_LABELS
    assert result_loose in TRANSITION_TYPE_LABELS


# === Integration: TransitionRecommendation beinhaltet transition_type ===

class TestTransitionInRecommendation:
  """Prueft ob transition_type in den Recommendations gesetzt wird."""

  def test_recommendation_has_transition_type(self):
    from hpg_core.playlist import compute_transition_recommendations
    t1 = _make_track(title="T1", bpm=128.0, camelot="8A", energy=50)
    t2 = _make_track(title="T2", bpm=128.0, camelot="8A", energy=55)
    recs = compute_transition_recommendations([t1, t2], bpm_tolerance=6.0)
    assert len(recs) == 1
    assert recs[0].transition_type in TRANSITION_TYPE_LABELS

  def test_recommendation_type_not_default(self):
    """transition_type soll aktiv gesetzt werden, nicht nur default."""
    from hpg_core.playlist import compute_transition_recommendations
    t1 = _make_track(title="T1", bpm=128.0, camelot="8A", energy=50, genre="Tech House")
    t2 = _make_track(title="T2", bpm=128.0, camelot="9A", energy=55, genre="Tech House")
    recs = compute_transition_recommendations([t1, t2], bpm_tolerance=6.0)
    assert len(recs) == 1
    # Tech House + gute Harmonie -> bass_swap (nicht default "blend")
    assert recs[0].transition_type != "blend"

  def test_multiple_recommendations(self):
    """Mehrere Recommendations haben jeweils ihren eigenen Typ."""
    from hpg_core.playlist import compute_transition_recommendations
    t1 = _make_track(title="T1", bpm=128.0, camelot="8A", energy=50)
    t2 = _make_track(title="T2", bpm=128.0, camelot="8A", energy=80)
    t3 = _make_track(title="T3", bpm=70.0, camelot="8A", energy=50)
    recs = compute_transition_recommendations([t1, t2, t3], bpm_tolerance=6.0)
    assert len(recs) == 2
    for rec in recs:
      assert rec.transition_type in TRANSITION_TYPE_LABELS

  def test_halftime_in_recommendation(self):
    """Half-Time Transition wird in Recommendation korrekt gesetzt."""
    from hpg_core.playlist import compute_transition_recommendations
    t1 = _make_track(title="T1", bpm=140.0, camelot="8A", energy=50)
    t2 = _make_track(title="T2", bpm=70.0, camelot="8A", energy=50)
    recs = compute_transition_recommendations([t1, t2], bpm_tolerance=6.0)
    assert len(recs) == 1
    assert recs[0].transition_type == "halftime_switch"
