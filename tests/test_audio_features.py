"""
Tests fuer Audio Feature Extensions (Phase 1):
- Brightness (Spektrale Helligkeit)
- Vocal/Instrumental Detection
- Danceability
- MFCC Fingerprint

Testet sowohl die standalone-Funktionen als auch die Integration
in die analyze_track() Pipeline.
"""
import pytest
import numpy as np
from hpg_core.models import Track
from hpg_core.analysis import (
  calculate_brightness,
  detect_vocal_instrumental,
  calculate_danceability,
  calculate_mfcc_fingerprint,
)
from tests.fixtures.audio_generators import (
  generate_click_track,
  generate_tone,
  generate_silence,
  generate_noise,
  generate_track_with_structure,
  generate_bass_tone,
  DEFAULT_SR,
)


# ============================================================
# Brightness Tests
# ============================================================

@pytest.mark.unit
class TestCalculateBrightness:
  """Tests fuer calculate_brightness()."""

  def test_returns_int(self, sr):
    """Gibt einen Integer zurueck."""
    y = generate_tone(440.0, 3.0, sr)
    result = calculate_brightness(y, sr)
    assert isinstance(result, int)

  def test_range_0_to_100(self, sr):
    """Ergebnis liegt zwischen 0 und 100."""
    y = generate_tone(440.0, 3.0, sr)
    result = calculate_brightness(y, sr)
    assert 0 <= result <= 100

  def test_none_input_returns_zero(self):
    """None Input = 0."""
    assert calculate_brightness(None, 22050) == 0

  def test_empty_array_returns_zero(self):
    """Leeres Array = 0."""
    assert calculate_brightness(np.array([]), 22050) == 0

  def test_zero_sr_returns_zero(self):
    """Sample-Rate 0 = 0."""
    y = generate_tone(440.0, 1.0)
    assert calculate_brightness(y, 0) == 0

  def test_negative_sr_returns_zero(self):
    """Negative Sample-Rate = 0."""
    y = generate_tone(440.0, 1.0)
    assert calculate_brightness(y, -22050) == 0

  def test_silence_returns_zero(self, sr):
    """Stille = niedriger Brightness-Wert."""
    y = generate_silence(3.0, sr)
    result = calculate_brightness(y, sr)
    assert result == 0

  def test_bass_tone_lower_than_high_tone(self, sr):
    """Bass-Ton hat niedrigere Brightness als hoher Ton."""
    bass = generate_bass_tone(3.0, sr, frequency=80.0)
    high = generate_tone(6000.0, 3.0, sr)
    bass_brightness = calculate_brightness(bass, sr)
    high_brightness = calculate_brightness(high, sr)
    assert bass_brightness < high_brightness, (
      f"Bass brightness {bass_brightness} sollte < high brightness {high_brightness}"
    )

  def test_noise_has_medium_brightness(self, sr):
    """Weisses Rauschen hat mittlere Brightness."""
    y = generate_noise(5.0, sr, amplitude=0.5)
    result = calculate_brightness(y, sr)
    # Weisses Rauschen hat viel Energie ueber das ganze Spektrum
    assert 20 <= result <= 90, f"Noise brightness {result} ausserhalb des erwarteten Bereichs"

  def test_nan_values_handled(self, sr):
    """NaN-Werte werden sicher behandelt."""
    y = np.full(sr * 3, np.nan, dtype=np.float32)
    result = calculate_brightness(y, sr)
    assert isinstance(result, int)
    assert 0 <= result <= 100

  def test_deterministic(self, sr):
    """Gleiches Signal = gleiches Ergebnis."""
    y = generate_tone(1000.0, 3.0, sr)
    result1 = calculate_brightness(y, sr)
    result2 = calculate_brightness(y, sr)
    assert result1 == result2


# ============================================================
# Vocal/Instrumental Detection Tests
# ============================================================

@pytest.mark.unit
class TestDetectVocalInstrumental:
  """Tests fuer detect_vocal_instrumental()."""

  def test_returns_string(self, sr):
    """Gibt einen String zurueck."""
    y = generate_tone(440.0, 3.0, sr)
    result = detect_vocal_instrumental(y, sr)
    assert isinstance(result, str)

  def test_valid_return_values(self, sr):
    """Nur gueltige Werte: vocal, instrumental, unknown."""
    y = generate_tone(440.0, 3.0, sr)
    result = detect_vocal_instrumental(y, sr)
    assert result in ("vocal", "instrumental", "unknown"), (
      f"Ungueltiger Wert: '{result}'"
    )

  def test_none_input_returns_unknown(self):
    """None Input = unknown."""
    assert detect_vocal_instrumental(None, 22050) == "unknown"

  def test_empty_array_returns_unknown(self):
    """Leeres Array = unknown."""
    assert detect_vocal_instrumental(np.array([]), 22050) == "unknown"

  def test_zero_sr_returns_unknown(self):
    """Sample-Rate 0 = unknown."""
    y = generate_tone(440.0, 1.0)
    assert detect_vocal_instrumental(y, 0) == "unknown"

  def test_silence_returns_value(self, sr):
    """Stille gibt gueltigen Wert zurueck."""
    y = generate_silence(3.0, sr)
    result = detect_vocal_instrumental(y, sr)
    assert result in ("vocal", "instrumental", "unknown")

  def test_pure_sine_is_not_vocal(self, sr):
    """Reiner Sinuston sollte nicht als 'vocal' erkannt werden."""
    y = generate_tone(440.0, 5.0, sr)
    result = detect_vocal_instrumental(y, sr)
    # Reiner Sinuston hat sehr flaches Spektrum → kein Vocal
    assert result != "vocal", "Reiner Sinuston faelschlicherweise als vocal erkannt"

  def test_noise_returns_valid_value(self, sr):
    """Rauschen gibt gueltigen Wert zurueck."""
    y = generate_noise(5.0, sr)
    result = detect_vocal_instrumental(y, sr)
    assert result in ("vocal", "instrumental", "unknown")

  def test_deterministic(self, sr):
    """Gleiches Signal = gleiches Ergebnis."""
    y = generate_noise(5.0, sr)
    result1 = detect_vocal_instrumental(y, sr)
    result2 = detect_vocal_instrumental(y, sr)
    assert result1 == result2

  def test_nan_values_handled(self, sr):
    """NaN-Werte werden sicher behandelt."""
    y = np.full(sr * 3, np.nan, dtype=np.float32)
    result = detect_vocal_instrumental(y, sr)
    assert result in ("vocal", "instrumental", "unknown")


# ============================================================
# Danceability Tests
# ============================================================

@pytest.mark.unit
class TestCalculateDanceability:
  """Tests fuer calculate_danceability()."""

  def test_returns_int(self, sr):
    """Gibt einen Integer zurueck."""
    y = generate_click_track(128.0, 10.0, sr)
    result = calculate_danceability(y, sr)
    assert isinstance(result, int)

  def test_range_0_to_100(self, sr):
    """Ergebnis liegt zwischen 0 und 100."""
    y = generate_click_track(128.0, 10.0, sr)
    result = calculate_danceability(y, sr)
    assert 0 <= result <= 100

  def test_none_input_returns_zero(self):
    """None Input = 0."""
    assert calculate_danceability(None, 22050) == 0

  def test_empty_array_returns_zero(self):
    """Leeres Array = 0."""
    assert calculate_danceability(np.array([]), 22050) == 0

  def test_zero_sr_returns_zero(self):
    """Sample-Rate 0 = 0."""
    y = generate_click_track(128.0, 5.0)
    assert calculate_danceability(y, 0) == 0

  def test_negative_sr_returns_zero(self):
    """Negative Sample-Rate = 0."""
    y = generate_click_track(128.0, 5.0)
    assert calculate_danceability(y, -22050) == 0

  def test_silence_low_danceability(self, sr):
    """Stille hat niedrige Danceability."""
    y = generate_silence(10.0, sr)
    result = calculate_danceability(y, sr)
    assert result <= 20, f"Stille hat Danceability {result}, erwartet <= 20"

  def test_click_track_has_danceability(self, sr):
    """Click-Track (regelmaessiger Beat) hat Danceability > 0."""
    y = generate_click_track(128.0, 10.0, sr)
    result = calculate_danceability(y, sr)
    assert result > 0, "Click-Track sollte Danceability > 0 haben"

  def test_bpm_parameter_accepted(self, sr):
    """BPM-Parameter wird akzeptiert und verarbeitet."""
    y = generate_click_track(128.0, 10.0, sr)
    result_with_bpm = calculate_danceability(y, sr, bpm=128.0)
    result_without_bpm = calculate_danceability(y, sr)
    # Beide sollten gueltige Werte liefern
    assert 0 <= result_with_bpm <= 100
    assert 0 <= result_without_bpm <= 100

  def test_bpm_in_dance_range_bonus(self, sr):
    """BPM im optimalen Tanzbereich (118-152) gibt Bonus."""
    y = generate_click_track(128.0, 10.0, sr)
    result_dance_bpm = calculate_danceability(y, sr, bpm=128.0)
    result_no_bpm = calculate_danceability(y, sr, bpm=0)
    # Mit DJ-typischem BPM sollte Danceability mindestens gleich hoch sein
    assert result_dance_bpm >= result_no_bpm, (
      f"Dance BPM ({result_dance_bpm}) sollte >= no BPM ({result_no_bpm})"
    )

  def test_deterministic(self, sr):
    """Gleiches Signal = gleiches Ergebnis."""
    y = generate_click_track(128.0, 10.0, sr)
    result1 = calculate_danceability(y, sr, bpm=128.0)
    result2 = calculate_danceability(y, sr, bpm=128.0)
    assert result1 == result2

  def test_structured_audio_has_danceability(self, sr):
    """Strukturiertes Audio (mit Beats) hat messbare Danceability."""
    y = generate_track_with_structure(bpm=128.0, duration=30.0, sr=sr)
    result = calculate_danceability(y, sr, bpm=128.0)
    assert result > 0, "Strukturiertes Audio sollte Danceability > 0 haben"

  def test_nan_values_handled(self, sr):
    """NaN-Werte werden sicher behandelt."""
    y = np.full(sr * 3, np.nan, dtype=np.float32)
    result = calculate_danceability(y, sr)
    assert isinstance(result, int)
    assert 0 <= result <= 100


# ============================================================
# MFCC Fingerprint Tests
# ============================================================

@pytest.mark.unit
class TestCalculateMfccFingerprint:
  """Tests fuer calculate_mfcc_fingerprint()."""

  def test_returns_list(self, sr):
    """Gibt eine Liste zurueck."""
    y = generate_tone(440.0, 3.0, sr)
    result = calculate_mfcc_fingerprint(y, sr)
    assert isinstance(result, list)

  def test_correct_length(self, sr):
    """Standard: 13 MFCCs."""
    y = generate_tone(440.0, 3.0, sr)
    result = calculate_mfcc_fingerprint(y, sr)
    assert len(result) == 13, f"MFCC-Laenge {len(result)}, erwartet 13"

  def test_custom_n_mfcc(self, sr):
    """Custom Anzahl MFCCs."""
    y = generate_tone(440.0, 3.0, sr)
    result = calculate_mfcc_fingerprint(y, sr, n_mfcc=20)
    assert len(result) == 20

  def test_none_input_returns_empty(self):
    """None Input = leere Liste."""
    assert calculate_mfcc_fingerprint(None, 22050) == []

  def test_empty_array_returns_empty(self):
    """Leeres Array = leere Liste."""
    assert calculate_mfcc_fingerprint(np.array([]), 22050) == []

  def test_zero_sr_returns_empty(self):
    """Sample-Rate 0 = leere Liste."""
    y = generate_tone(440.0, 1.0)
    assert calculate_mfcc_fingerprint(y, 0) == []

  def test_values_are_float(self, sr):
    """Alle Werte sind Floats."""
    y = generate_tone(440.0, 3.0, sr)
    result = calculate_mfcc_fingerprint(y, sr)
    for val in result:
      assert isinstance(val, float), f"Wert {val} ist {type(val)}, erwartet float"

  def test_values_are_finite(self, sr):
    """Alle Werte sind endlich (kein NaN/Inf)."""
    y = generate_tone(440.0, 3.0, sr)
    result = calculate_mfcc_fingerprint(y, sr)
    for val in result:
      assert np.isfinite(val), f"MFCC-Wert {val} ist nicht endlich"

  def test_different_signals_different_fingerprints(self, sr):
    """Verschiedene Signale haben verschiedene Fingerprints."""
    tone = generate_tone(440.0, 3.0, sr)
    noise = generate_noise(3.0, sr)
    fp_tone = calculate_mfcc_fingerprint(tone, sr)
    fp_noise = calculate_mfcc_fingerprint(noise, sr)
    # Mindestens ein MFCC sollte sich unterscheiden
    assert fp_tone != fp_noise, "Ton und Rauschen sollten verschiedene Fingerprints haben"

  def test_same_signal_same_fingerprint(self, sr):
    """Gleiches Signal = gleicher Fingerprint."""
    y = generate_tone(440.0, 3.0, sr)
    fp1 = calculate_mfcc_fingerprint(y, sr)
    fp2 = calculate_mfcc_fingerprint(y, sr)
    assert fp1 == fp2

  def test_silence_returns_valid_fingerprint(self, sr):
    """Stille gibt gueltigen Fingerprint zurueck."""
    y = generate_silence(3.0, sr)
    result = calculate_mfcc_fingerprint(y, sr)
    assert isinstance(result, list)
    # Stille kann leere oder gefuellte Liste zurueckgeben
    if len(result) > 0:
      assert len(result) == 13

  def test_nan_values_handled(self, sr):
    """NaN-Werte werden sicher behandelt."""
    y = np.full(DEFAULT_SR * 3, np.nan, dtype=np.float32)
    result = calculate_mfcc_fingerprint(y, DEFAULT_SR)
    assert isinstance(result, list)

  def test_rounded_to_4_decimals(self, sr):
    """Werte sind auf 4 Dezimalstellen gerundet."""
    y = generate_noise(3.0, sr)
    result = calculate_mfcc_fingerprint(y, sr)
    for val in result:
      # Check: round(val, 4) == val
      assert round(val, 4) == val, f"Wert {val} hat mehr als 4 Dezimalstellen"


# ============================================================
# Track Dataclass Integration Tests
# ============================================================

@pytest.mark.unit
class TestTrackAudioFeatureFields:
  """Tests fuer die neuen Audio-Feature Felder im Track Dataclass."""

  def test_brightness_default(self):
    """brightness Default = 0."""
    track = Track(filePath="/t.mp3", fileName="t.mp3")
    assert track.brightness == 0

  def test_vocal_instrumental_default(self):
    """vocal_instrumental Default = 'unknown'."""
    track = Track(filePath="/t.mp3", fileName="t.mp3")
    assert track.vocal_instrumental == "unknown"

  def test_danceability_default(self):
    """danceability Default = 0."""
    track = Track(filePath="/t.mp3", fileName="t.mp3")
    assert track.danceability == 0

  def test_mfcc_fingerprint_default(self):
    """mfcc_fingerprint Default = leere Liste."""
    track = Track(filePath="/t.mp3", fileName="t.mp3")
    assert track.mfcc_fingerprint == []

  def test_mfcc_fingerprint_independent(self):
    """mfcc_fingerprint ist pro Instanz unabhaengig (kein Shared State)."""
    t1 = Track(filePath="/a.mp3", fileName="a.mp3")
    t2 = Track(filePath="/b.mp3", fileName="b.mp3")
    t1.mfcc_fingerprint.append(1.0)
    assert t2.mfcc_fingerprint == [], "Shared mutable default state entdeckt!"

  def test_custom_audio_feature_values(self):
    """Custom Audio-Feature Werte werden korrekt gesetzt."""
    track = Track(
      filePath="/t.mp3",
      fileName="t.mp3",
      brightness=75,
      vocal_instrumental="vocal",
      danceability=80,
      mfcc_fingerprint=[1.0, 2.0, 3.0],
    )
    assert track.brightness == 75
    assert track.vocal_instrumental == "vocal"
    assert track.danceability == 80
    assert track.mfcc_fingerprint == [1.0, 2.0, 3.0]

  def test_track_has_audio_feature_fields(self):
    """Track Dataclass hat alle Audio-Feature Felder."""
    from dataclasses import fields
    field_names = {f.name for f in fields(Track)}
    expected = {"brightness", "vocal_instrumental", "danceability", "mfcc_fingerprint"}
    assert expected.issubset(field_names), (
      f"Fehlende Felder: {expected - field_names}"
    )


# ============================================================
# Integration: analyze_track() mit Audio Features
# ============================================================

@pytest.mark.integration
class TestAnalyzeTrackAudioFeatures:
  """Integration: Audio Features in der analyze_track() Pipeline."""

  @pytest.fixture
  def simple_wav(self, tmp_path):
    """Einfache WAV-Datei fuer Integration Tests."""
    import wave
    path = str(tmp_path / "test_features.wav")
    sr = 22050
    duration = 5.0
    n_samples = int(duration * sr)
    t = np.linspace(0, duration, n_samples, endpoint=False)
    signal = (np.sin(2 * np.pi * 440 * t) * 32767 * 0.5).astype(np.int16)
    with wave.open(path, "w") as wav:
      wav.setnchannels(1)
      wav.setsampwidth(2)
      wav.setframerate(sr)
      wav.writeframes(signal.tobytes())
    return path

  @pytest.fixture
  def click_wav(self, tmp_path):
    """Click-Track WAV bei 128 BPM fuer Integration Tests."""
    import wave
    path = str(tmp_path / "test_click.wav")
    sr = 22050
    duration = 10.0
    n_samples = int(duration * sr)
    signal = np.zeros(n_samples)
    beat_interval = 60.0 / 128.0
    click_duration = 0.01
    t = 0.0
    while t < duration:
      start = int(t * sr)
      end = min(start + int(click_duration * sr), n_samples)
      if end > start:
        click_t = np.linspace(0, click_duration, end - start, endpoint=False)
        signal[start:end] = np.sin(2 * np.pi * 1000 * click_t) * 0.8
      t += beat_interval
    int_signal = (signal * 32767).astype(np.int16)
    with wave.open(path, "w") as wav:
      wav.setnchannels(1)
      wav.setsampwidth(2)
      wav.setframerate(sr)
      wav.writeframes(int_signal.tobytes())
    return path

  def test_brightness_set_in_pipeline(self, simple_wav):
    """analyze_track setzt brightness Feld."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(simple_wav)
    assert track is not None
    assert isinstance(track.brightness, int)
    assert 0 <= track.brightness <= 100

  def test_vocal_instrumental_set_in_pipeline(self, simple_wav):
    """analyze_track setzt vocal_instrumental Feld."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(simple_wav)
    assert track is not None
    assert track.vocal_instrumental in ("vocal", "instrumental", "unknown")

  def test_danceability_set_in_pipeline(self, simple_wav):
    """analyze_track setzt danceability Feld."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(simple_wav)
    assert track is not None
    assert isinstance(track.danceability, int)
    assert 0 <= track.danceability <= 100

  def test_mfcc_fingerprint_set_in_pipeline(self, simple_wav):
    """analyze_track setzt mfcc_fingerprint Feld."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(simple_wav)
    assert track is not None
    assert isinstance(track.mfcc_fingerprint, list)
    if len(track.mfcc_fingerprint) > 0:
      assert len(track.mfcc_fingerprint) == 13

  def test_all_audio_features_consistent(self, click_wav):
    """Alle Audio-Features werden konsistent gesetzt."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(click_wav)
    assert track is not None
    # Alle Felder muessen gueltig sein
    assert isinstance(track.brightness, int)
    assert isinstance(track.vocal_instrumental, str)
    assert isinstance(track.danceability, int)
    assert isinstance(track.mfcc_fingerprint, list)

  def test_cached_track_has_audio_features(self, simple_wav):
    """Gecachter Track behaelt Audio-Feature Felder."""
    from hpg_core.analysis import analyze_track
    # Erster Aufruf (Cache schreiben)
    track1 = analyze_track(simple_wav)
    # Zweiter Aufruf (Cache lesen)
    track2 = analyze_track(simple_wav)
    assert track2.brightness == track1.brightness
    assert track2.vocal_instrumental == track1.vocal_instrumental
    assert track2.danceability == track1.danceability
    assert track2.mfcc_fingerprint == track1.mfcc_fingerprint
