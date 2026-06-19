"""
Tests fuer BPM Half/Double Tolerance.
Prueft ob Tracks mit halbem/doppeltem BPM als kompatibel erkannt werden.
z.B. 140 BPM <-> 70 BPM (Half-Time) oder 128 BPM <-> 64 BPM.
"""
import pytest
from unittest.mock import patch
from hpg_core.playlist import effective_bpm_diff, calculate_compatibility
from hpg_core.models import Track


# === Hilfsfunktionen ===

def _make_track(bpm: float, camelot: str = "8A", energy: int = 50) -> Track:
  """Erstellt einen minimalen Track fuer BPM-Tests."""
  return Track(
    filePath="test.mp3",
    fileName="test.mp3",
    title=f"Track_{bpm}bpm",
    bpm=bpm,
    camelotCode=camelot,
    energy=energy,
  )


# === effective_bpm_diff Tests ===

class TestEffectiveBpmDiff:
  """Tests fuer die zentrale BPM-Differenz-Berechnung."""

  def test_same_bpm_is_zero(self):
    diff, relation = effective_bpm_diff(128.0, 128.0)
    assert diff == 0.0
    assert relation == "direct"

  def test_direct_close_bpm(self):
    diff, relation = effective_bpm_diff(128.0, 130.0)
    assert diff == pytest.approx(2.0)
    assert relation == "direct"

  def test_half_time_recognition(self):
    """70 BPM ist Half-Time von 140 BPM."""
    diff, relation = effective_bpm_diff(140.0, 70.0)
    assert diff == pytest.approx(0.0)
    assert relation == "half"

  def test_half_time_reversed(self):
    """70 BPM ↔ 140 BPM auch andersrum."""
    diff, relation = effective_bpm_diff(70.0, 140.0)
    assert diff == pytest.approx(0.0)
    assert relation == "half"

  def test_double_time_recognition(self):
    """256 BPM ist Double-Time von 128 BPM."""
    diff, relation = effective_bpm_diff(128.0, 256.0)
    assert diff == pytest.approx(0.0)
    assert relation in ("half", "double")  # Beide Richtungen moeglich

  def test_approximate_half_time(self):
    """174 BPM DnB ↔ 87 BPM — fast exakt halb."""
    diff, relation = effective_bpm_diff(174.0, 87.0)
    assert diff == pytest.approx(0.0)
    assert relation == "half"

  def test_near_half_time_small_diff(self):
    """140 BPM ↔ 72 BPM — fast halb, kleine Differenz."""
    diff, relation = effective_bpm_diff(140.0, 72.0)
    # Candidates: direct=68, |140-144|=4 (half), |140/2-72|=|70-72|=2 (double)
    # Minimum: 2.0 (double: 140/2=70, diff to 72 = 2)
    assert diff == pytest.approx(2.0)
    assert relation == "double"

  def test_direct_is_closer_than_half(self):
    """128 BPM ↔ 126 BPM — direkt ist naeher als halb."""
    diff, relation = effective_bpm_diff(128.0, 126.0)
    assert diff == pytest.approx(2.0)
    assert relation == "direct"

  def test_zero_bpm_returns_direct(self):
    diff, relation = effective_bpm_diff(0.0, 128.0)
    assert relation == "direct"

  def test_negative_bpm_returns_direct(self):
    diff, relation = effective_bpm_diff(-1.0, 128.0)
    assert relation == "direct"

  def test_both_zero_returns_zero(self):
    diff, relation = effective_bpm_diff(0.0, 0.0)
    assert diff == 0.0

  def test_returns_tuple(self):
    result = effective_bpm_diff(128.0, 130.0)
    assert isinstance(result, tuple)
    assert len(result) == 2

  def test_diff_always_non_negative(self):
    """Differenz ist immer >= 0."""
    for bpm1 in [60, 90, 128, 140, 174]:
      for bpm2 in [60, 90, 128, 140, 174]:
        diff, _ = effective_bpm_diff(float(bpm1), float(bpm2))
        assert diff >= 0, f"Negativ: {bpm1} vs {bpm2} = {diff}"

  def test_symmetric(self):
    """effective_bpm_diff(a, b) == effective_bpm_diff(b, a)."""
    for bpm1, bpm2 in [(128, 64), (140, 70), (174, 87), (130, 126)]:
      d1, _ = effective_bpm_diff(float(bpm1), float(bpm2))
      d2, _ = effective_bpm_diff(float(bpm2), float(bpm1))
      assert d1 == pytest.approx(d2), f"Asymmetrie: {bpm1}/{bpm2}"

  def test_disabled_flag(self):
    """Bei BPM_HALF_DOUBLE_ENABLED=False nur direkte Differenz."""
    with patch("hpg_core.playlist.BPM_HALF_DOUBLE_ENABLED", False):
      diff, relation = effective_bpm_diff(140.0, 70.0)
      assert diff == pytest.approx(70.0)
      assert relation == "direct"


# === Integration: calculate_compatibility mit Half/Double ===

class TestCompatibilityHalfDouble:
  """Prueft ob calculate_compatibility Half/Double korrekt nutzt."""

  def test_same_key_half_time_is_compatible(self):
    """140 BPM Track und 70 BPM Track mit gleichem Key."""
    t1 = _make_track(bpm=140.0, camelot="8A")
    t2 = _make_track(bpm=70.0, camelot="8A")
    score = calculate_compatibility(t1, t2, bpm_tolerance=8.0)
    # Bei Half-Time eff_diff=0, gleicher Key = hoher Score (mit Penalty)
    assert score > 0, "Half-Time sollte kompatibel sein"
    assert score >= 80, "Gleicher Key + Half-Time sollte >= 80 sein"

  def test_half_time_lower_than_direct(self):
    """Half-Time Score soll etwas unter direktem Score liegen."""
    t_direct_1 = _make_track(bpm=140.0, camelot="8A")
    t_direct_2 = _make_track(bpm=140.0, camelot="8A")
    t_half = _make_track(bpm=70.0, camelot="8A")

    direct_score = calculate_compatibility(t_direct_1, t_direct_2, bpm_tolerance=8.0)
    half_score = calculate_compatibility(t_direct_1, t_half, bpm_tolerance=8.0)

    assert direct_score >= half_score, "Direct soll >= Half-Time sein"
    assert half_score > 0, "Half-Time darf nicht 0 sein"

  def test_without_half_double_incompatible(self):
    """Ohne Half/Double: 140 vs 70 BPM bei tolerance=8 → 0."""
    with patch("hpg_core.playlist.BPM_HALF_DOUBLE_ENABLED", False):
      t1 = _make_track(bpm=140.0, camelot="8A")
      t2 = _make_track(bpm=70.0, camelot="8A")
      score = calculate_compatibility(t1, t2, bpm_tolerance=8.0)
      assert score == 0, "Ohne Half/Double: 70 BPM diff > 8 tolerance"

  def test_dnb_half_time_compatible(self):
    """174 BPM DnB ↔ 87 BPM Half-Time."""
    t1 = _make_track(bpm=174.0, camelot="5A")
    t2 = _make_track(bpm=87.0, camelot="5A")
    score = calculate_compatibility(t1, t2, bpm_tolerance=8.0)
    assert score > 0, "DnB Half-Time sollte kompatibel sein"

  def test_penalty_applied_for_half_time(self):
    """Half-Time Score hat BPM_HALF_DOUBLE_PENALTY."""
    t1 = _make_track(bpm=140.0, camelot="8A")
    t2 = _make_track(bpm=70.0, camelot="8A")
    score = calculate_compatibility(t1, t2, bpm_tolerance=8.0)
    # Same key = 100 * 0.85 penalty = 85
    assert score == 85, f"Expected 85, got {score}"

  def test_adjacent_key_half_time(self):
    """Half-Time + adjacent key = 80 * penalty."""
    t1 = _make_track(bpm=140.0, camelot="8A")
    t2 = _make_track(bpm=70.0, camelot="9A")
    score = calculate_compatibility(t1, t2, bpm_tolerance=8.0)
    expected = int(80 * 0.85)  # 68
    assert score == expected, f"Expected {expected}, got {score}"

  def test_relative_major_minor_half_time(self):
    """Half-Time + relative major/minor = 90 * penalty."""
    t1 = _make_track(bpm=128.0, camelot="8A")
    t2 = _make_track(bpm=64.0, camelot="8B")
    score = calculate_compatibility(t1, t2, bpm_tolerance=8.0)
    expected = int(90 * 0.85)  # 76
    assert score == expected, f"Expected {expected}, got {score}"


# === Edge Cases ===

class TestHalfDoubleEdgeCases:
  """Edge Cases fuer BPM Half/Double."""

  def test_very_low_bpm_half(self):
    """60 BPM ↔ 30 BPM — extrem langsam."""
    diff, relation = effective_bpm_diff(60.0, 30.0)
    assert diff == pytest.approx(0.0)
    assert relation == "half"

  def test_very_high_bpm(self):
    """180 BPM ↔ 90 BPM — DnB/Halftime."""
    diff, relation = effective_bpm_diff(180.0, 90.0)
    assert diff == pytest.approx(0.0)
    assert relation == "half"

  def test_third_time_not_detected(self):
    """150 BPM ↔ 50 BPM — Drittel ist KEIN Half/Double."""
    diff, relation = effective_bpm_diff(150.0, 50.0)
    # Direct: |150-50| = 100
    # Half: |150-100| = 50 oder |75-50| = 25
    # Kein exaktes Half/Double, aber die kleinste Diff wird genommen
    assert diff > 0, "Drittel sollte nicht als 0 erkannt werden"

  def test_real_world_psytrance_techno(self):
    """145 BPM Psytrance ↔ 72 BPM Downtempo (near half)."""
    diff, relation = effective_bpm_diff(145.0, 72.0)
    # Candidates: direct=73, |145-144|=1 (half), |145/2-72|=|72.5-72|=0.5 (double)
    # Minimum: 0.5 (double: 145/2=72.5, diff to 72 = 0.5)
    assert diff == pytest.approx(0.5)
    assert relation == "double"

  def test_real_world_house_dnb(self):
    """128 BPM House ↔ 172 BPM DnB — kein Half/Double."""
    diff, relation = effective_bpm_diff(128.0, 172.0)
    # Direct: 44, Half: |128-344|=216 or |256-172|=84, better is direct
    # Actually: |128-172| = 44 direct
    # |128 - 172*2| = |128-344| = 216
    # |128*2 - 172| = |256-172| = 84
    # |128 - 172/2| = |128-86| = 42
    # |128/2 - 172| = |64-172| = 108
    # Minimum: 42 (double)
    assert diff == pytest.approx(42.0)
