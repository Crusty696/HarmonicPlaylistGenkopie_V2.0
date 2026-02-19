"""
Tests fuer Camelot-Wheel Kompatibilitaet (hpg_core.playlist.calculate_compatibility).
Prueft alle 9 harmonischen Regeln und BPM-Toleranz.
"""
import pytest
from hpg_core.playlist import calculate_compatibility, _get_camelot_components
from tests.fixtures.track_factories import make_track
from tests.fixtures.camelot_test_data import (
  COMPATIBILITY_RULES, INCOMPATIBLE_PAIRS, BPM_TOLERANCE_CASES,
)


class TestCamelotComponents:
  """Prueft das Parsen von Camelot-Codes."""

  @pytest.mark.parametrize("code,expected_num,expected_letter", [
    ("8A", 8, "A"),
    ("1B", 1, "B"),
    ("12A", 12, "A"),
    ("3B", 3, "B"),
  ])
  def test_valid_codes(self, code, expected_num, expected_letter):
    """Gueltige Codes werden korrekt zerlegt."""
    num, letter = _get_camelot_components(code)
    assert num == expected_num
    assert letter == expected_letter

  def test_invalid_code(self):
    """Ungueltiger Code ergibt (0, '')."""
    num, letter = _get_camelot_components("invalid")
    assert num == 0
    assert letter == ""

  def test_empty_code(self):
    """Leerer Code ergibt (0, '')."""
    num, letter = _get_camelot_components("")
    assert num == 0
    assert letter == ""


class TestSameKeyCompatibility:
  """Same Key = 100 Punkte."""

  @pytest.mark.parametrize("code", [
    "1A", "5A", "8A", "12A", "1B", "6B", "8B", "12B",
  ])
  def test_same_key_is_100(self, code):
    """Gleicher Key = perfekte Kompatibilitaet."""
    t1 = make_track(camelotCode=code, bpm=128.0)
    t2 = make_track(camelotCode=code, bpm=128.0)
    assert calculate_compatibility(t1, t2, 3.0) == 100


class TestRelativeCompatibility:
  """Relative Major/Minor = 90 Punkte."""

  @pytest.mark.parametrize("code_a,code_b", [
    ("8A", "8B"),
    ("1A", "1B"),
    ("12A", "12B"),
    ("5B", "5A"),
  ])
  def test_relative_is_90(self, code_a, code_b):
    """Relative Major/Minor (gleiche Nummer, anderer Buchstabe)."""
    t1 = make_track(camelotCode=code_a, bpm=128.0)
    t2 = make_track(camelotCode=code_b, bpm=128.0)
    assert calculate_compatibility(t1, t2, 3.0) == 90


class TestAdjacentCompatibility:
  """Adjacent Keys = 80 Punkte."""

  @pytest.mark.parametrize("code1,code2", [
    ("8A", "9A"),   # +1
    ("8A", "7A"),   # -1
    ("8B", "9B"),   # +1 Major
    ("8B", "7B"),   # -1 Major
  ])
  def test_adjacent_is_80(self, code1, code2):
    """Nachbar-Keys im Camelot Wheel."""
    t1 = make_track(camelotCode=code1, bpm=128.0)
    t2 = make_track(camelotCode=code2, bpm=128.0)
    assert calculate_compatibility(t1, t2, 3.0) == 80

  def test_wraparound_12_to_1(self):
    """Camelot Wheel ist zirkulaer: 12 -> 1 = 80."""
    t1 = make_track(camelotCode="12A", bpm=128.0)
    t2 = make_track(camelotCode="1A", bpm=128.0)
    assert calculate_compatibility(t1, t2, 3.0) == 80

  def test_wraparound_1_to_12(self):
    """Camelot Wheel ist zirkulaer: 1 -> 12 = 80."""
    t1 = make_track(camelotCode="1A", bpm=128.0)
    t2 = make_track(camelotCode="12A", bpm=128.0)
    assert calculate_compatibility(t1, t2, 3.0) == 80


class TestExperimentalTechniques:
  """Plus Four (70) und Plus Seven (65) Techniken."""

  def test_plus_four_is_70(self):
    """Plus-Four Technik: 8A -> 12A = 70."""
    t1 = make_track(camelotCode="8A", bpm=128.0)
    t2 = make_track(camelotCode="12A", bpm=128.0)
    assert calculate_compatibility(t1, t2, 3.0) == 70

  def test_plus_four_major(self):
    """Plus-Four Major: 3B -> 7B = 70."""
    t1 = make_track(camelotCode="3B", bpm=128.0)
    t2 = make_track(camelotCode="7B", bpm=128.0)
    assert calculate_compatibility(t1, t2, 3.0) == 70

  def test_plus_seven_is_65(self):
    """Plus-Seven (Quintenzirkel): 8A -> 3A = 65."""
    t1 = make_track(camelotCode="8A", bpm=128.0)
    t2 = make_track(camelotCode="3A", bpm=128.0)
    assert calculate_compatibility(t1, t2, 3.0) == 65

  def test_experimental_disabled(self):
    """Wenn experimental deaktiviert, kein Plus-Four/Seven."""
    t1 = make_track(camelotCode="8A", bpm=128.0)
    t2 = make_track(camelotCode="12A", bpm=128.0)
    score = calculate_compatibility(t1, t2, 3.0, allow_experimental=False)
    assert score < 70  # Kein Plus-Four Score


class TestDiagonalMixing:
  """Diagonal = 60, Energy Boost = 85, Energy Drop = 75."""

  def test_diagonal_plus_one(self):
    """Diagonal +1: 8A -> 9B = 60."""
    t1 = make_track(camelotCode="8A", bpm=128.0)
    t2 = make_track(camelotCode="9B", bpm=128.0)
    assert calculate_compatibility(t1, t2, 3.0) == 60

  def test_diagonal_minus_one(self):
    """Diagonal -1: 8A -> 7B = 60."""
    t1 = make_track(camelotCode="8A", bpm=128.0)
    t2 = make_track(camelotCode="7B", bpm=128.0)
    assert calculate_compatibility(t1, t2, 3.0) == 60


class TestBPMTolerance:
  """BPM-Differenz ueber Toleranz = Score 0."""

  def test_within_tolerance(self):
    """Innerhalb BPM-Toleranz = Score > 0."""
    t1 = make_track(camelotCode="8A", bpm=126.0)
    t2 = make_track(camelotCode="8A", bpm=128.0)
    assert calculate_compatibility(t1, t2, 3.0) > 0

  def test_over_tolerance(self):
    """Ueber BPM-Toleranz = Score 0."""
    t1 = make_track(camelotCode="8A", bpm=128.0)
    t2 = make_track(camelotCode="8A", bpm=132.0)
    assert calculate_compatibility(t1, t2, 3.0) == 0

  def test_exact_tolerance_boundary(self):
    """Genau an der Grenze = noch kompatibel."""
    t1 = make_track(camelotCode="8A", bpm=128.0)
    t2 = make_track(camelotCode="8A", bpm=131.0)
    assert calculate_compatibility(t1, t2, 3.0) == 100

  @pytest.mark.parametrize("bpm1,bpm2,tolerance,should_compat",
    BPM_TOLERANCE_CASES)
  def test_bpm_tolerance_cases(self, bpm1, bpm2, tolerance, should_compat):
    """Parametrisierte BPM-Toleranz Tests."""
    t1 = make_track(camelotCode="8A", bpm=bpm1)
    t2 = make_track(camelotCode="8A", bpm=bpm2)
    score = calculate_compatibility(t1, t2, tolerance)
    if should_compat:
      assert score > 0, f"BPM {bpm1}/{bpm2} mit Toleranz {tolerance} sollte kompatibel sein"
    else:
      assert score == 0, f"BPM {bpm1}/{bpm2} mit Toleranz {tolerance} sollte inkompatibel sein"


class TestMissingCodes:
  """Edge Cases: fehlende oder ungueltige Codes."""

  def test_missing_camelot_code(self):
    """Fehlender Camelot-Code = minimale Kompatibilitaet."""
    t1 = make_track(camelotCode="", bpm=128.0)
    t2 = make_track(camelotCode="8A", bpm=128.0)
    score = calculate_compatibility(t1, t2, 3.0)
    assert score == 10  # Minimal score fuer fehlende Codes

  def test_both_missing(self):
    """Beide ohne Camelot-Code."""
    t1 = make_track(camelotCode="", bpm=128.0)
    t2 = make_track(camelotCode="", bpm=128.0)
    score = calculate_compatibility(t1, t2, 3.0)
    assert score == 10


class TestIncompatiblePairs:
  """Weit entfernte Keys sollen niedrigen Score haben."""

  @pytest.mark.parametrize("code1,code2", INCOMPATIBLE_PAIRS)
  def test_incompatible_low_score(self, code1, code2):
    """Inkompatible Paare haben niedrigen Score."""
    t1 = make_track(camelotCode=code1, bpm=128.0)
    t2 = make_track(camelotCode=code2, bpm=128.0)
    score = calculate_compatibility(t1, t2, 3.0)
    assert score < 60, f"{code1}->{code2} Score {score} ist zu hoch"


class TestCompatibilityRules:
  """Alle Regeln aus der Testdaten-Tabelle."""

  @pytest.mark.parametrize("code1,code2,expected_score,rule_name",
    COMPATIBILITY_RULES)
  def test_compatibility_rule(self, code1, code2, expected_score, rule_name):
    """Prueft erwarteten Score fuer jede Regel."""
    t1 = make_track(camelotCode=code1, bpm=128.0)
    t2 = make_track(camelotCode=code2, bpm=128.0)
    score = calculate_compatibility(t1, t2, 3.0)
    assert score == expected_score, (
      f"Regel '{rule_name}': {code1}->{code2} "
      f"erwartet {expected_score}, bekommen {score}"
    )


class TestStrictnessParameter:
  """Harmonic Strictness beeinflusst Fallback-Score."""

  def test_low_strictness_higher_fallback(self):
    """Niedrige Strictness = hoeherer Fallback-Score."""
    t1 = make_track(camelotCode="8A", bpm=128.0)
    t2 = make_track(camelotCode="2B", bpm=128.0)  # Weit entfernt
    low = calculate_compatibility(t1, t2, 3.0, harmonic_strictness=1)
    high = calculate_compatibility(t1, t2, 3.0, harmonic_strictness=10)
    assert low >= high
