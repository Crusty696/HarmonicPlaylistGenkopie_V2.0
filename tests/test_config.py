"""
Tests fuer hpg_core.config - Konfigurationskonstanten.
Validiert dass alle produktiv genutzten Magic Numbers im sinnvollen Bereich liegen.

Hinweis: Tote Konstanten (MIX_POINT_BUFFER, FALLBACK_*, RUPTURES_*, ONSET/CENTROID_THRESHOLD
u.a.) wurden 2026-07-16 entfernt -- gruene Existenz-Tests hatten Aktivitaet vorgetaeuscht.
"""
import pytest
from hpg_core.config import (
  HOP_LENGTH, METER,
  INTRO_MAX_PERCENTAGE, OUTRO_MIN_PERCENTAGE,
  RMS_THRESHOLD,
  BARS_PER_PHRASE, DEFAULT_BPM,
  DJ_BRAIN_ENABLED,
  SECURITY_MAX_FILE_SIZE, SECURITY_MAX_TRACK_DURATION, SECURITY_MAX_PLAYLIST_SIZE,
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

  def test_hop_length_power_of_two(self):
    """HOP_LENGTH muss eine Zweierpotenz sein (FFT-Optimierung)."""
    assert HOP_LENGTH > 0
    assert (HOP_LENGTH & (HOP_LENGTH - 1)) == 0, (
      f"HOP_LENGTH {HOP_LENGTH} ist keine Zweierpotenz"
    )


class TestIntroOutroThresholds:
  """Intro/Outro Detection Schwellenwerte (produktiv in analysis.py genutzt)."""

  def test_intro_max_before_outro_min(self):
    """Max-Intro muss vor Min-Outro liegen."""
    assert INTRO_MAX_PERCENTAGE < OUTRO_MIN_PERCENTAGE

  def test_intro_max_reasonable(self):
    """Intro kann maximal 40% sein (mehr waere kein Intro)."""
    assert INTRO_MAX_PERCENTAGE <= 0.40

  def test_outro_min_reasonable(self):
    """Outro startet fruehestens bei 60%."""
    assert OUTRO_MIN_PERCENTAGE >= 0.60

  def test_rms_threshold_between_0_and_1(self):
    """RMS-Schwelle muss zwischen 0 und 1 liegen."""
    assert 0.0 < RMS_THRESHOLD < 1.0


class TestDJBrainConfig:
  """DJ-Brain Master-Schalter (verdrahtet in analysis.py)."""

  def test_dj_brain_enabled_is_bool(self):
    assert isinstance(DJ_BRAIN_ENABLED, bool)


class TestSecurityLimits:
  """Security-Limits (verdrahtet via playlist_security in main.py)."""

  def test_max_file_size_reasonable(self):
    """Zwischen 10 MB und 1 GB."""
    assert 10 * 1024 * 1024 <= SECURITY_MAX_FILE_SIZE <= 1024 * 1024 * 1024

  def test_max_track_duration_reasonable(self):
    """Zwischen 10 Minuten und 24 Stunden."""
    assert 600 <= SECURITY_MAX_TRACK_DURATION <= 86400

  def test_max_playlist_size_positive(self):
    assert SECURITY_MAX_PLAYLIST_SIZE > 0


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
