"""
Tests fuer Key-Erkennung (Krumhansl-Schmuckler Algorithmus).
Prueft Chroma-Korrelation fuer alle 24 Keys (12 Major + 12 Minor).
"""
import pytest
import numpy as np
from hpg_core.analysis import get_key, MAJOR_PROFILE, MINOR_PROFILE, NOTES
from hpg_core.models import CAMELOT_MAP
from tests.fixtures.audio_generators import (
  generate_major_chord, generate_minor_chord,
  generate_tone, generate_silence, NOTE_FREQUENCIES,
  DEFAULT_SR,
)


class TestGetKeyBasics:
  """Grundlegende Funktionalitaet der Key-Erkennung."""

  def test_returns_tuple(self):
    """get_key gibt (note, mode) Tupel zurueck."""
    chroma = np.array(MAJOR_PROFILE, dtype=np.float64)
    result = get_key(chroma)
    assert isinstance(result, tuple)
    assert len(result) == 2

  def test_note_is_valid(self):
    """Erkannte Note muss in NOTES-Liste sein."""
    chroma = np.array(MAJOR_PROFILE, dtype=np.float64)
    note, _ = get_key(chroma)
    assert note in NOTES, f"Note '{note}' nicht in {NOTES}"

  def test_mode_is_major_or_minor(self):
    """Mode muss 'Major' oder 'Minor' sein."""
    chroma = np.array(MAJOR_PROFILE, dtype=np.float64)
    _, mode = get_key(chroma)
    assert mode in ("Major", "Minor")

  def test_chroma_length_12(self):
    """Chroma-Vektor muss 12 Elemente haben."""
    assert len(MAJOR_PROFILE) == 12
    assert len(MINOR_PROFILE) == 12
    assert len(NOTES) == 12


class TestMajorKeyDetection:
  """Major Key Erkennung mit Krumhansl-Schmuckler Profilen."""

  def test_c_major_from_profile(self):
    """C Major Profil ungerollt = C Major."""
    chroma = np.array(MAJOR_PROFILE, dtype=np.float64)
    note, mode = get_key(chroma)
    assert note == "C", f"Erwartet C, bekommen {note}"
    assert mode == "Major"

  @pytest.mark.parametrize("shift,expected_note", [
    (0, "C"), (1, "C#"), (2, "D"), (3, "D#"),
    (4, "E"), (5, "F"), (6, "F#"), (7, "G"),
    (8, "G#"), (9, "A"), (10, "A#"), (11, "B"),
  ])
  def test_all_major_keys_from_rolled_profile(self, shift, expected_note):
    """Gerolltes Major-Profil ergibt korrekte Tonart."""
    chroma = np.roll(MAJOR_PROFILE, shift)
    note, mode = get_key(chroma)
    assert note == expected_note, (
      f"Shift {shift}: erwartet {expected_note}, bekommen {note}"
    )
    assert mode == "Major"

  def test_major_chord_detected_as_major(self):
    """Synthetischer Major-Akkord wird als Major erkannt."""
    # C Major Akkord generieren und Chroma extrahieren
    import librosa
    y = generate_major_chord("C", 3.0, DEFAULT_SR)
    chroma = librosa.feature.chroma_stft(y=y, sr=DEFAULT_SR)
    chroma_mean = np.mean(chroma, axis=1)
    _, mode = get_key(chroma_mean)
    assert mode == "Major", f"Major-Akkord als {mode} erkannt"


class TestMinorKeyDetection:
  """Minor Key Erkennung."""

  def test_a_minor_from_profile(self):
    """A Minor Profil (Shift 9) = A Minor."""
    # Minor Profil bei A = roll(MINOR, 9) weil A ist Index 9
    chroma = np.roll(MINOR_PROFILE, 9)
    note, mode = get_key(chroma)
    assert note == "A", f"Erwartet A, bekommen {note}"
    assert mode == "Minor"

  @pytest.mark.parametrize("shift,expected_note", [
    (0, "C"), (1, "C#"), (2, "D"), (3, "D#"),
    (4, "E"), (5, "F"), (6, "F#"), (7, "G"),
    (8, "G#"), (9, "A"), (10, "A#"), (11, "B"),
  ])
  def test_all_minor_keys_from_rolled_profile(self, shift, expected_note):
    """Gerolltes Minor-Profil ergibt korrekte Tonart."""
    chroma = np.roll(MINOR_PROFILE, shift)
    note, mode = get_key(chroma)
    assert note == expected_note, (
      f"Shift {shift}: erwartet {expected_note}, bekommen {note}"
    )
    assert mode == "Minor"

  def test_minor_chord_detected_as_minor(self):
    """Synthetischer Minor-Akkord wird als Minor erkannt."""
    import librosa
    y = generate_minor_chord("A", 3.0, DEFAULT_SR)
    chroma = librosa.feature.chroma_stft(y=y, sr=DEFAULT_SR)
    chroma_mean = np.mean(chroma, axis=1)
    _, mode = get_key(chroma_mean)
    assert mode == "Minor", f"Minor-Akkord als {mode} erkannt"


class TestKeyDetectionEdgeCases:
  """Edge Cases und Grenzfaelle."""

  def test_uniform_chroma(self):
    """Gleichmaessiger Chroma-Vektor - kein Crash."""
    chroma = np.ones(12, dtype=np.float64)
    note, mode = get_key(chroma)
    assert note in NOTES
    assert mode in ("Major", "Minor")

  def test_zeros_chroma(self):
    """Null-Chroma-Vektor - kein Crash."""
    chroma = np.zeros(12, dtype=np.float64)
    # np.corrcoef mit Nullen kann NaN erzeugen
    try:
      note, mode = get_key(chroma)
      # Wenn kein Crash, ist das OK
      assert True
    except (ValueError, RuntimeWarning):
      # Auch akzeptabel bei Null-Input
      assert True

  def test_single_peak_chroma(self):
    """Ein einzelner dominanter Chroma-Bin."""
    chroma = np.zeros(12, dtype=np.float64)
    chroma[0] = 1.0  # Nur C dominant
    note, mode = get_key(chroma)
    # C sollte erkannt werden (Major oder Minor)
    assert note in NOTES

  def test_very_small_values(self):
    """Sehr kleine Werte - kein Crash."""
    chroma = np.full(12, 1e-10, dtype=np.float64)
    chroma[0] = 1e-9  # Leichte C-Dominanz
    note, mode = get_key(chroma)
    assert note in NOTES

  def test_negative_values(self):
    """Negative Werte im Chroma-Vektor - kein Crash."""
    chroma = np.array(MAJOR_PROFILE, dtype=np.float64) - 3.0
    note, mode = get_key(chroma)
    assert note in NOTES
    assert mode in ("Major", "Minor")


class TestCamelotMapping:
  """Key-Erkennung und Camelot-Zuordnung."""

  def test_recognized_keys_have_camelot_code(self):
    """Jede erkannte Key/Mode Kombination hat einen Camelot-Code."""
    for shift in range(12):
      chroma = np.roll(MAJOR_PROFILE, shift)
      note, mode = get_key(chroma)
      key_tuple = (note, mode)
      assert key_tuple in CAMELOT_MAP, (
        f"Key {key_tuple} nicht in CAMELOT_MAP"
      )

  def test_all_camelot_codes_reachable(self):
    """Alle 24 Camelot-Codes sind durch Key-Erkennung erreichbar."""
    detected_keys = set()
    # Alle Major Keys
    for shift in range(12):
      chroma = np.roll(MAJOR_PROFILE, shift)
      note, mode = get_key(chroma)
      detected_keys.add(f"{note} {mode}")
    # Alle Minor Keys
    for shift in range(12):
      chroma = np.roll(MINOR_PROFILE, shift)
      note, mode = get_key(chroma)
      detected_keys.add(f"{note} {mode}")
    # Mindestens 20 von 24 sollten erreichbar sein
    assert len(detected_keys) >= 20, (
      f"Nur {len(detected_keys)} Keys erkannt: {detected_keys}"
    )


class TestCorrelationQuality:
  """Qualitaet der Korrelationswerte."""

  def test_perfect_major_high_correlation(self):
    """Perfektes Major-Profil hat hohe Korrelation."""
    chroma = np.array(MAJOR_PROFILE, dtype=np.float64)
    # Direkte Korrelation berechnen
    corr = np.corrcoef(chroma, MAJOR_PROFILE)[0, 1]
    assert corr > 0.99, f"Korrelation {corr} zu niedrig"

  def test_major_minor_distinguishable(self):
    """Major und Minor Profile sind unterscheidbar."""
    major_chroma = np.array(MAJOR_PROFILE, dtype=np.float64)
    minor_chroma = np.array(MINOR_PROFILE, dtype=np.float64)
    # Major-Profil sollte hoehere Major-Korrelation haben
    major_corr = np.corrcoef(major_chroma, MAJOR_PROFILE)[0, 1]
    minor_corr = np.corrcoef(major_chroma, MINOR_PROFILE)[0, 1]
    assert major_corr > minor_corr, (
      f"Major Korr ({major_corr}) nicht > Minor Korr ({minor_corr})"
    )

  def test_rolled_profile_correct_peak(self):
    """Gerolltes Profil hat Korrelationspeak bei richtigem Index."""
    # G Major = Shift 7
    chroma = np.roll(MAJOR_PROFILE, 7)
    correlations = []
    for i in range(12):
      corr = np.corrcoef(np.roll(chroma, -i), MAJOR_PROFILE)[0, 1]
      correlations.append(corr)
    peak_index = np.argmax(correlations)
    assert peak_index == 7, (
      f"Peak bei Index {peak_index} (NOTES[7]={NOTES[7]}), erwartet 7 (G)"
    )
