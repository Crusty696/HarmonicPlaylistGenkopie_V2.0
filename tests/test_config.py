"""
Tests fuer hpg_core.config - Konfigurationskonstanten.
Validiert dass alle Magic Numbers im sinnvollen Bereich liegen.
"""
import pytest
from hpg_core.config import (
  HOP_LENGTH, METER,
  INTRO_PERCENTAGE, OUTRO_PERCENTAGE,
  INTRO_MAX_PERCENTAGE, OUTRO_MIN_PERCENTAGE,
  RMS_THRESHOLD, ONSET_THRESHOLD, CENTROID_THRESHOLD,
  MIX_POINT_BUFFER, MIN_MIX_DURATION,
  MIX_IN_MAX_PERCENTAGE, MIX_OUT_MIN_PERCENTAGE,
  FALLBACK_MIX_IN, FALLBACK_MIX_OUT,
  BARS_PER_PHRASE, DEFAULT_BPM, DEFAULT_SECONDS_PER_BAR,
  FALLBACK_INTRO_END, FALLBACK_OUTRO_START,
  RUPTURES_JUMP, RUPTURES_MIN_SIZE_SECONDS, RUPTURES_PENALTY_MULTIPLIER,
  MIN_SEGMENT_DURATION,
)


class TestMeterAndTiming:
  """4/4-Takt und Timing-Konstanten."""

  def test_meter_is_4(self):
    """Elektronische Musik = 4/4 Takt."""
    assert METER == 4

  def test_bars_per_phrase_is_8(self):
    """Standard DJ-Phrase = 8 Bars."""
    assert BARS_PER_PHRASE == 8

  def test_default_bpm_is_120(self):
    """Fallback-BPM = 120 (universeller Standard)."""
    assert DEFAULT_BPM == 120.0

  def test_default_seconds_per_bar(self):
    """Sekunden pro Bar bei Default-BPM."""
    expected = 60.0 / DEFAULT_BPM * METER
    assert abs(DEFAULT_SECONDS_PER_BAR - expected) < 0.01

  def test_hop_length_power_of_two(self):
    """HOP_LENGTH muss eine Zweierpotenz sein (FFT-Optimierung)."""
    assert HOP_LENGTH > 0
    assert (HOP_LENGTH & (HOP_LENGTH - 1)) == 0, (
      f"HOP_LENGTH {HOP_LENGTH} ist keine Zweierpotenz"
    )


class TestIntroOutroPercentages:
  """Intro/Outro Detection Schwellenwerte."""

  def test_intro_before_outro(self):
    """Intro-Ende muss vor Outro-Start liegen."""
    assert INTRO_PERCENTAGE < OUTRO_PERCENTAGE

  def test_intro_percentage_range(self):
    """Intro zwischen 5% und 30%."""
    assert 0.05 <= INTRO_PERCENTAGE <= 0.30

  def test_outro_percentage_range(self):
    """Outro zwischen 70% und 95%."""
    assert 0.70 <= OUTRO_PERCENTAGE <= 0.95

  def test_intro_max_before_outro_min(self):
    """Max-Intro muss vor Min-Outro liegen."""
    assert INTRO_MAX_PERCENTAGE < OUTRO_MIN_PERCENTAGE

  def test_intro_max_reasonable(self):
    """Intro kann maximal 40% sein (mehr waere kein Intro)."""
    assert INTRO_MAX_PERCENTAGE <= 0.40

  def test_outro_min_reasonable(self):
    """Outro startet fruehestens bei 60%."""
    assert OUTRO_MIN_PERCENTAGE >= 0.60

  def test_fallback_intro_end(self):
    """Fallback Intro-Ende im sinnvollen Bereich."""
    assert 0.1 <= FALLBACK_INTRO_END <= 0.3

  def test_fallback_outro_start(self):
    """Fallback Outro-Start im sinnvollen Bereich."""
    assert 0.7 <= FALLBACK_OUTRO_START <= 0.9

  def test_fallback_intro_before_outro(self):
    """Fallback: Intro-Ende vor Outro-Start."""
    assert FALLBACK_INTRO_END < FALLBACK_OUTRO_START


class TestThresholds:
  """Energy-Detection Schwellenwerte."""

  def test_rms_threshold_between_0_and_1(self):
    """RMS-Schwelle muss zwischen 0 und 1 liegen."""
    assert 0.0 < RMS_THRESHOLD < 1.0

  def test_onset_threshold_between_0_and_1(self):
    """Onset-Schwelle muss zwischen 0 und 1 liegen."""
    assert 0.0 < ONSET_THRESHOLD < 1.0

  def test_centroid_threshold_between_0_and_1(self):
    """Centroid-Schwelle muss zwischen 0 und 1 liegen."""
    assert 0.0 < CENTROID_THRESHOLD < 1.0

  def test_rms_strictest(self):
    """RMS ist der strengste Indikator (niedrigster Schwellenwert)."""
    assert RMS_THRESHOLD <= ONSET_THRESHOLD
    assert RMS_THRESHOLD <= CENTROID_THRESHOLD


class TestMixPointConfig:
  """Mix-Point Konfiguration."""

  def test_mix_point_buffer_positive(self):
    """Buffer muss positiv sein."""
    assert MIX_POINT_BUFFER > 0

  def test_min_mix_duration_positive(self):
    """Mindest-Mix-Dauer muss positiv sein."""
    assert MIN_MIX_DURATION > 0

  def test_min_mix_duration_reasonable(self):
    """Mindest-Mix-Dauer zwischen 5 und 30 Sekunden."""
    assert 5.0 <= MIN_MIX_DURATION <= 30.0

  def test_mix_in_max_at_most_half(self):
    """Mix-In darf maximal in der ersten Haelfte sein."""
    assert MIX_IN_MAX_PERCENTAGE <= 0.5

  def test_mix_out_min_at_least_half(self):
    """Mix-Out muss mindestens in der zweiten Haelfte sein."""
    assert MIX_OUT_MIN_PERCENTAGE >= 0.5

  def test_fallback_mix_in_before_out(self):
    """Fallback Mix-In vor Mix-Out."""
    assert FALLBACK_MIX_IN < FALLBACK_MIX_OUT

  def test_min_segment_duration_positive(self):
    """Minimum Segment-Dauer positiv."""
    assert MIN_SEGMENT_DURATION > 0


class TestRupturesConfig:
  """Ruptures-Algorithmus Konfiguration."""

  def test_jump_positive(self):
    """Jump-Parameter muss positiv sein."""
    assert RUPTURES_JUMP > 0

  def test_min_size_positive(self):
    """Minimum-Segmentgroesse muss positiv sein."""
    assert RUPTURES_MIN_SIZE_SECONDS > 0

  def test_penalty_multiplier_positive(self):
    """Penalty-Multiplikator muss positiv sein."""
    assert RUPTURES_PENALTY_MULTIPLIER > 0


class TestConfigConsistency:
  """Konsistenzpruefungen ueber mehrere Konstanten."""

  def test_phrase_math_consistency(self):
    """8 Bars * 4 Beats = 32 Beats pro Phrase."""
    beats_per_phrase = BARS_PER_PHRASE * METER
    assert beats_per_phrase == 32

  def test_default_timing_consistency(self):
    """Default-Timing: 120 BPM, 4/4, 8-bar Phrases = 16s/Phrase."""
    spb = 60.0 / DEFAULT_BPM  # seconds per beat
    bar_duration = spb * METER  # seconds per bar
    phrase_duration = bar_duration * BARS_PER_PHRASE  # seconds per phrase
    assert abs(phrase_duration - 16.0) < 0.01

  def test_intro_outro_sum_less_than_100(self):
    """Intro + Outro duerfen zusammen nicht 100% ueberschreiten."""
    assert INTRO_PERCENTAGE + (1.0 - OUTRO_PERCENTAGE) < 1.0
