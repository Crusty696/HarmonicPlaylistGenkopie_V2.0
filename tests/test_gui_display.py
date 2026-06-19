"""
Tests fuer GUI-Anzeigeformate (kein Qt noetig).
Prueft Format-Strings fuer Mix-Points, BPM, Duration.
"""
import pytest


def format_time(seconds: float) -> str:
  """Formatiert Sekunden als mm:ss (wie in main.py Zeile 658-659)."""
  if seconds is None or seconds < 0:
    return "0:00"
  mins = int(seconds) // 60
  secs = int(seconds) % 60
  return f"{mins}:{secs:02d}"


def format_mix_point(seconds: float, bars: int) -> str:
  """Formatiert Mix-Point als 'mm:ss (N bars)'."""
  time_str = format_time(seconds)
  return f"{time_str} ({bars} bars)"


def format_bpm(bpm: float) -> str:
  """Formatiert BPM mit 1 Dezimalstelle."""
  return f"{bpm:.1f}"


def format_duration(seconds: float) -> str:
  """Formatiert Dauer als m:ss."""
  return format_time(seconds)


class TestTimeFormatting:
  """Zeitformat mm:ss."""

  def test_zero_seconds(self):
    assert format_time(0) == "0:00"

  def test_30_seconds(self):
    assert format_time(30) == "0:30"

  def test_60_seconds(self):
    assert format_time(60) == "1:00"

  def test_93_seconds(self):
    """1:33 = 93 Sekunden."""
    assert format_time(93) == "1:33"

  def test_270_seconds(self):
    """4:30 = 270 Sekunden."""
    assert format_time(270) == "4:30"

  def test_367_seconds(self):
    """6:07 = 367 Sekunden."""
    assert format_time(367) == "6:07"

  def test_negative_seconds(self):
    """Negative Sekunden = 0:00."""
    assert format_time(-5) == "0:00"

  def test_none_seconds(self):
    """None = 0:00."""
    assert format_time(None) == "0:00"

  def test_large_value(self):
    """3600 Sekunden = 60:00."""
    assert format_time(3600) == "60:00"


class TestMixPointFormatting:
  """Mix-Point Anzeigeformat."""

  def test_mix_in_format(self):
    """Mix-In Format: '1:33 (50 bars)'."""
    result = format_mix_point(93.0, 50)
    assert result == "1:33 (50 bars)"

  def test_mix_out_format(self):
    """Mix-Out Format: '4:30 (144 bars)'."""
    result = format_mix_point(270.0, 144)
    assert result == "4:30 (144 bars)"

  def test_zero_bars(self):
    """0 Bars."""
    result = format_mix_point(0.0, 0)
    assert result == "0:00 (0 bars)"


class TestBPMFormatting:
  """BPM-Anzeige."""

  def test_128_bpm(self):
    assert format_bpm(128.0) == "128.0"

  def test_128_5_bpm(self):
    assert format_bpm(128.5) == "128.5"

  def test_174_bpm(self):
    assert format_bpm(174.0) == "174.0"

  def test_rounding(self):
    """128.45 -> 128.4 (1 Dezimalstelle)."""
    assert format_bpm(128.45) in ("128.4", "128.5")  # Python rounding

  def test_zero_bpm(self):
    assert format_bpm(0.0) == "0.0"


class TestDurationFormatting:
  """Track-Dauer Anzeige."""

  def test_5_minutes(self):
    """300s = 5:00."""
    assert format_duration(300) == "5:00"

  def test_6_min_7_sec(self):
    """367s = 6:07."""
    assert format_duration(367) == "6:07"

  def test_3_min_30_sec(self):
    """210s = 3:30."""
    assert format_duration(210) == "3:30"
