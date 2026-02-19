"""
Tests fuer Energy und Bass Intensity Berechnung.
Prueft Skalierung 0-100 und korrekte Frequenzerkennung.
"""
import pytest
import numpy as np
from hpg_core.analysis import calculate_energy, calculate_bass_intensity
from tests.fixtures.audio_generators import (
  generate_silence, generate_noise, generate_tone,
  generate_bass_tone, DEFAULT_SR,
)


class TestEnergyCalculation:
  """Energy-Berechnung (RMS-basiert, Skala 0-100)."""

  def test_silence_is_zero(self):
    """Stille = Energy 0."""
    y = generate_silence(5.0, DEFAULT_SR)
    assert calculate_energy(y) == 0

  def test_noise_has_energy(self):
    """Rauschen hat messbare Energy."""
    y = generate_noise(5.0, DEFAULT_SR, amplitude=0.3)
    energy = calculate_energy(y)
    assert energy > 0, "Rauschen sollte Energy > 0 haben"

  def test_loud_noise_high_energy(self):
    """Lautes Rauschen = hohe Energy."""
    y = generate_noise(5.0, DEFAULT_SR, amplitude=0.8)
    energy = calculate_energy(y)
    assert energy > 50, f"Lautes Rauschen: Energy {energy} (erwartet >50)"

  def test_energy_range_0_to_100(self):
    """Energy ist immer zwischen 0 und 100."""
    # Verschiedene Amplituden testen
    for amp in [0.0, 0.1, 0.3, 0.5, 0.8, 1.0]:
      if amp == 0:
        y = generate_silence(2.0, DEFAULT_SR)
      else:
        y = generate_noise(2.0, DEFAULT_SR, amplitude=amp)
      energy = calculate_energy(y)
      assert 0 <= energy <= 100, f"Energy {energy} bei Amplitude {amp}"

  def test_louder_means_more_energy(self):
    """Hohere Amplitude = mehr Energy."""
    y_quiet = generate_noise(5.0, DEFAULT_SR, amplitude=0.1)
    y_loud = generate_noise(5.0, DEFAULT_SR, amplitude=0.5)
    assert calculate_energy(y_loud) > calculate_energy(y_quiet)

  def test_empty_array_is_zero(self):
    """Leeres Array = Energy 0."""
    y = np.array([], dtype=np.float32)
    assert calculate_energy(y) == 0

  def test_none_is_zero(self):
    """None = Energy 0."""
    assert calculate_energy(None) == 0

  def test_full_amplitude_near_100(self):
    """Vollausschlag (Amplitude 1.0) -> Energy nahe 100."""
    # Dauerton bei voller Amplitude
    y = generate_tone(440.0, 5.0, DEFAULT_SR, amplitude=1.0)
    energy = calculate_energy(y)
    # RMS einer Sinuswelle bei Amplitude 1.0 = 1/sqrt(2) ≈ 0.707
    # np.interp(0.707, [0, 0.4], [0, 100]) = 100 (da 0.707 > 0.4)
    assert energy > 90, f"Vollausschlag: Energy {energy} (erwartet >90)"

  def test_nan_values_handled(self):
    """NaN-Werte werden korrekt behandelt."""
    y = np.array([np.nan, np.nan, 0.5, 0.3], dtype=np.float32)
    energy = calculate_energy(y)
    assert 0 <= energy <= 100

  def test_inf_values_handled(self):
    """Inf-Werte werden korrekt behandelt."""
    y = np.array([np.inf, -np.inf, 0.5, 0.3], dtype=np.float32)
    energy = calculate_energy(y)
    assert 0 <= energy <= 100


class TestBassIntensity:
  """Bass Intensity (20-150Hz STFT-Analyse, Skala 0-100)."""

  def test_silence_is_zero(self):
    """Stille = Bass 0."""
    y = generate_silence(5.0, DEFAULT_SR)
    assert calculate_bass_intensity(y, DEFAULT_SR) == 0

  def test_bass_tone_has_bass(self):
    """80Hz Ton hat hohe Bass-Intensitaet."""
    y = generate_bass_tone(5.0, DEFAULT_SR, frequency=80.0, amplitude=0.7)
    bass = calculate_bass_intensity(y, DEFAULT_SR)
    assert bass > 0, f"80Hz Ton sollte Bass > 0 haben, bekommen {bass}"

  def test_high_tone_low_bass(self):
    """5000Hz Ton hat niedrige Bass-Intensitaet."""
    y = generate_tone(5000.0, 5.0, DEFAULT_SR, amplitude=0.7)
    bass = calculate_bass_intensity(y, DEFAULT_SR)
    # Hoher Ton sollte weniger Bass haben als tiefer Ton
    y_bass = generate_bass_tone(5.0, DEFAULT_SR, frequency=80.0, amplitude=0.7)
    bass_low = calculate_bass_intensity(y_bass, DEFAULT_SR)
    assert bass < bass_low, (
      f"5kHz Bass ({bass}) sollte < 80Hz Bass ({bass_low}) sein"
    )

  def test_bass_range_0_to_100(self):
    """Bass Intensity immer zwischen 0 und 100."""
    for freq in [50.0, 100.0, 500.0, 2000.0]:
      y = generate_tone(freq, 3.0, DEFAULT_SR, amplitude=0.5)
      bass = calculate_bass_intensity(y, DEFAULT_SR)
      assert 0 <= bass <= 100, f"Bass {bass} bei {freq}Hz"

  def test_empty_array_is_zero(self):
    """Leeres Array = Bass 0."""
    y = np.array([], dtype=np.float32)
    assert calculate_bass_intensity(y, DEFAULT_SR) == 0

  def test_none_is_zero(self):
    """None = Bass 0."""
    assert calculate_bass_intensity(None, DEFAULT_SR) == 0

  def test_invalid_sr_is_zero(self):
    """Ungueltige Sample Rate = Bass 0."""
    y = generate_tone(440.0, 2.0, DEFAULT_SR)
    assert calculate_bass_intensity(y, 0) == 0
    assert calculate_bass_intensity(y, -1) == 0

  def test_very_short_audio(self):
    """Sehr kurzes Audio - kein Crash."""
    y = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    bass = calculate_bass_intensity(y, DEFAULT_SR)
    assert 0 <= bass <= 100
