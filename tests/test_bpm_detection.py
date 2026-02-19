"""
Tests fuer BPM-Erkennung (librosa.beat.beat_track Pipeline).
Verwendet synthetische Click-Tracks mit bekanntem Tempo.
"""
import pytest
import numpy as np
import librosa
from hpg_core.config import DEFAULT_BPM
from tests.fixtures.audio_generators import (
  generate_click_track, generate_silence, generate_noise,
  generate_tone, DEFAULT_SR,
)


def _detect_bpm(y, sr):
  """BPM-Erkennung wie in analyze_track()."""
  if y is None or len(y) == 0:
    return 0.0
  tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
  tempo_array = np.atleast_1d(tempo)
  bpm_value = float(tempo_array[0]) if tempo_array.size else 0.0
  if bpm_value <= 0:
    alt_tempo = librosa.beat.tempo(y=y, sr=sr)
    alt_array = np.atleast_1d(alt_tempo)
    bpm_value = float(alt_array[0]) if alt_array.size else 0.0
  if bpm_value <= 0 and beat_frames.size > 1:
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    intervals = np.diff(beat_times)
    if intervals.size > 0:
      median_interval = np.median(intervals)
      if median_interval > 0:
        bpm_value = 60.0 / median_interval
  return bpm_value


class TestBPMDetectionBasics:
  """Grundlegende BPM-Erkennung mit Click-Tracks."""

  @pytest.mark.slow
  def test_128bpm_click_track(self):
    """128 BPM Click-Track wird korrekt erkannt (+-2 BPM)."""
    y = generate_click_track(128.0, 10.0, DEFAULT_SR)
    bpm = _detect_bpm(y, DEFAULT_SR)
    assert abs(bpm - 128.0) <= 2.0, (
      f"128 BPM erwartet, {bpm:.1f} erkannt"
    )

  @pytest.mark.slow
  def test_120bpm_click_track(self):
    """120 BPM Click-Track wird korrekt erkannt (+-5 BPM oder halbes/doppeltes)."""
    y = generate_click_track(120.0, 10.0, DEFAULT_SR)
    bpm = _detect_bpm(y, DEFAULT_SR)
    # librosa kann bei kurzen synthetischen Signalen ungenau sein
    close = (abs(bpm - 120.0) <= 5.0 or
             abs(bpm - 60.0) <= 5.0 or
             abs(bpm - 240.0) <= 5.0)
    assert close, f"120 BPM erwartet, {bpm:.1f} erkannt"

  @pytest.mark.slow
  def test_140bpm_click_track(self):
    """140 BPM Click-Track wird korrekt erkannt (+-5 BPM oder halbes/doppeltes)."""
    y = generate_click_track(140.0, 10.0, DEFAULT_SR)
    bpm = _detect_bpm(y, DEFAULT_SR)
    # librosa kann bei kurzen synthetischen Signalen ungenau sein
    close = (abs(bpm - 140.0) <= 5.0 or
             abs(bpm - 70.0) <= 5.0 or
             abs(bpm - 280.0) <= 5.0)
    assert close, f"140 BPM erwartet, {bpm:.1f} erkannt"

  @pytest.mark.slow
  def test_bpm_positive(self):
    """Erkannter BPM-Wert ist positiv."""
    y = generate_click_track(128.0, 10.0, DEFAULT_SR)
    bpm = _detect_bpm(y, DEFAULT_SR)
    assert bpm > 0, "BPM muss positiv sein"


class TestBPMDifferentTempi:
  """BPM-Erkennung bei verschiedenen Tempi."""

  @pytest.mark.slow
  @pytest.mark.parametrize("target_bpm", [
    80.0, 100.0, 110.0, 120.0, 128.0, 135.0, 140.0, 150.0, 174.0,
  ])
  def test_various_tempi(self, target_bpm):
    """BPM-Erkennung bei verschiedenen Tempi (+-5 BPM oder halbes/doppeltes Tempo)."""
    y = generate_click_track(target_bpm, 10.0, DEFAULT_SR)
    bpm = _detect_bpm(y, DEFAULT_SR)
    # librosa kann bei kurzen synthetischen Signalen ungenau sein
    close_to_target = abs(bpm - target_bpm) <= 5.0
    close_to_half = abs(bpm - target_bpm / 2) <= 5.0
    close_to_double = abs(bpm - target_bpm * 2) <= 5.0
    assert close_to_target or close_to_half or close_to_double, (
      f"BPM {target_bpm}: erkannt {bpm:.1f} "
      f"(weder +-5 noch halbes/doppeltes Tempo)"
    )


class TestBPMEdgeCases:
  """Edge Cases und Fehlerbehandlung."""

  def test_silence_returns_value(self):
    """Stille ergibt einen BPM-Wert (irgendein Fallback)."""
    y = generate_silence(5.0, DEFAULT_SR)
    bpm = _detect_bpm(y, DEFAULT_SR)
    # Bei Stille kann librosa beliebige Werte zurueckgeben
    assert isinstance(bpm, float)

  def test_empty_array(self):
    """Leeres Array ergibt BPM 0."""
    y = np.array([], dtype=np.float32)
    bpm = _detect_bpm(y, DEFAULT_SR)
    assert bpm == 0.0

  def test_none_input(self):
    """None ergibt BPM 0."""
    bpm = _detect_bpm(None, DEFAULT_SR)
    assert bpm == 0.0

  @pytest.mark.slow
  def test_very_short_audio(self):
    """Sehr kurzes Audio (2s) - kein Crash."""
    y = generate_click_track(128.0, 2.0, DEFAULT_SR)
    bpm = _detect_bpm(y, DEFAULT_SR)
    assert isinstance(bpm, float)
    assert bpm >= 0

  @pytest.mark.slow
  def test_noise_returns_value(self):
    """Rauschen ergibt irgendeinen BPM-Wert (kein Crash)."""
    y = generate_noise(5.0, DEFAULT_SR, amplitude=0.3)
    bpm = _detect_bpm(y, DEFAULT_SR)
    assert isinstance(bpm, float)
    assert bpm >= 0

  @pytest.mark.slow
  def test_pure_tone_no_crash(self):
    """Reiner Sinuston (kein Rhythmus) - kein Crash."""
    y = generate_tone(440.0, 5.0, DEFAULT_SR, amplitude=0.5)
    bpm = _detect_bpm(y, DEFAULT_SR)
    assert isinstance(bpm, float)


class TestBPMConsistency:
  """Konsistenz der BPM-Erkennung."""

  @pytest.mark.slow
  def test_same_input_same_result(self):
    """Gleicher Input = gleiches Ergebnis (deterministisch)."""
    y = generate_click_track(128.0, 10.0, DEFAULT_SR)
    bpm1 = _detect_bpm(y, DEFAULT_SR)
    bpm2 = _detect_bpm(y, DEFAULT_SR)
    assert bpm1 == bpm2, (
      f"Nicht deterministisch: {bpm1} vs {bpm2}"
    )

  @pytest.mark.slow
  def test_louder_click_same_bpm(self):
    """Lauterer Click-Track hat gleichen BPM."""
    y_quiet = generate_click_track(128.0, 10.0, DEFAULT_SR)
    y_loud = y_quiet * 2.0  # Doppelte Amplitude
    y_loud = np.clip(y_loud, -1.0, 1.0)
    bpm_quiet = _detect_bpm(y_quiet, DEFAULT_SR)
    bpm_loud = _detect_bpm(y_loud, DEFAULT_SR)
    assert abs(bpm_quiet - bpm_loud) <= 2.0, (
      f"Leise: {bpm_quiet:.1f}, Laut: {bpm_loud:.1f}"
    )

  @pytest.mark.slow
  def test_longer_audio_more_accurate(self):
    """Laengeres Audio tendenziell genauere BPM-Erkennung."""
    target = 128.0
    y_short = generate_click_track(target, 5.0, DEFAULT_SR)
    y_long = generate_click_track(target, 20.0, DEFAULT_SR)
    bpm_short = _detect_bpm(y_short, DEFAULT_SR)
    bpm_long = _detect_bpm(y_long, DEFAULT_SR)
    err_short = abs(bpm_short - target)
    err_long = abs(bpm_long - target)
    # Laengeres Audio sollte mindestens nicht schlechter sein
    # (mit grosszuegiger Toleranz)
    assert err_long <= err_short + 2.0, (
      f"Langes Audio ({err_long:.1f}) ungenauer als kurzes ({err_short:.1f})"
    )


class TestBPMRealisticRange:
  """BPM-Werte im realistischen DJ-Bereich."""

  @pytest.mark.slow
  def test_house_tempo_range(self):
    """House-Tempo (120-130 BPM) wird korrekt erkannt."""
    for target in [120.0, 124.0, 126.0, 128.0, 130.0]:
      y = generate_click_track(target, 10.0, DEFAULT_SR)
      bpm = _detect_bpm(y, DEFAULT_SR)
      # Entweder korrekt oder halbes/doppeltes Tempo
      ok = (abs(bpm - target) <= 3.0 or
            abs(bpm - target / 2) <= 3.0 or
            abs(bpm - target * 2) <= 3.0)
      assert ok, f"House {target} BPM: erkannt {bpm:.1f}"

  @pytest.mark.slow
  def test_dnb_tempo_range(self):
    """D&B Tempo (170-175 BPM) - Erkennung oder halbes Tempo."""
    y = generate_click_track(174.0, 10.0, DEFAULT_SR)
    bpm = _detect_bpm(y, DEFAULT_SR)
    # D&B wird oft als halbes Tempo (87 BPM) erkannt
    ok = (abs(bpm - 174.0) <= 3.0 or
          abs(bpm - 87.0) <= 3.0)
    assert ok, f"D&B 174 BPM: erkannt {bpm:.1f}"

  @pytest.mark.slow
  def test_techno_tempo(self):
    """Techno Tempo (135-140 BPM)."""
    y = generate_click_track(138.0, 10.0, DEFAULT_SR)
    bpm = _detect_bpm(y, DEFAULT_SR)
    ok = (abs(bpm - 138.0) <= 3.0 or
          abs(bpm - 69.0) <= 3.0 or
          abs(bpm - 276.0) <= 3.0)
    assert ok, f"Techno 138 BPM: erkannt {bpm:.1f}"
