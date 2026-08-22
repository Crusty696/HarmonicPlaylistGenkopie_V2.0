"""
Tests fuer hpg_core.config - Konfigurationskonstanten.
Validiert dass alle produktiv genutzten Magic Numbers im sinnvollen Bereich liegen.

Hinweis: Tote Konstanten (MIX_POINT_BUFFER, FALLBACK_*, RUPTURES_*, ONSET/CENTROID_THRESHOLD
u.a.) wurden 2026-07-16 entfernt -- gruene Existenz-Tests hatten Aktivitaet vorgetaeuscht.
"""
from hpg_core.config import (
  HOP_LENGTH, METER,
  MIX_IN_SEARCH_WINDOW_PCT, MIX_OUT_SEARCH_WINDOW_PCT,
  RMS_THRESHOLD,
  BARS_PER_PHRASE, DEFAULT_BPM,
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

  def test_search_windows_disjunkt(self):
    """Mix-In-Suchfenster muss vor dem Mix-Out-Suchfenster enden.

    Research-Basis: Bittner et al. (ISMIR 2017) — Mix-In in den ersten 20%,
    Mix-Out in den letzten 25% des Tracks.
    """
    assert MIX_IN_SEARCH_WINDOW_PCT < MIX_OUT_SEARCH_WINDOW_PCT
    assert MIX_IN_SEARCH_WINDOW_PCT <= 0.40
    assert MIX_OUT_SEARCH_WINDOW_PCT >= 0.60

  def test_rms_threshold_between_0_and_1(self):
    """RMS-Schwelle (Zehren-Salience, 0.4 x Max) muss zwischen 0 und 1 liegen."""
    assert 0.0 < RMS_THRESHOLD < 1.0


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


class TestKandidatenKonstanten:
  """Konstanten fuer Mixpunkt-Kandidaten (Spec 2026-08-21, Abschnitt 1)."""

  def test_kandidaten_konstanten_vorhanden_und_plausibel(self):
    from hpg_core import config
    assert config.KANDIDATEN_MAX_JE_SEITE == 8
    assert config.KANDIDATEN_MIN_JE_SEITE == 3
    assert config.KANDIDATEN_FENSTER_PHRASEN == 1
    assert config.CUE_DEDUPE_SEC == 2.0
    assert config.KICK_AKTIV_MIN_DBFS == -35.0
    assert config.KICK_AKTIV_ONBEAT_MIN == 0.40
    assert config.ENERGIE_TREND_SCHWELLE == 10
    assert config.ENERGIE_NEUHEIT_MIN == 20
    assert config.KANDIDATEN_AUDIO_SR == 22050

  def test_paar_konstanten_vorhanden_und_plausibel(self):
    from hpg_core import config
    assert config.PAAR_BPM_MAX == 2.0
    assert config.PAAR_PITCH_MAX == 0.04
    assert config.PAAR_HALF_DOUBLE_MAX_BARS == 16
    assert config.PAAR_BPM_SKALA == 1.0
    assert config.PAAR_MAX_KOMBINATIONEN == 6
    assert config.LUFS_DELTA_MAX_DB == 3.0
    assert config.BASS_RMS_DELTA_MAX_DB == 6.0
    assert config.SYNCOPATION_DELTA_MAX == 0.5
    assert config.PERCUSSIVE_HOCH == 0.7
    assert config.PERCUSSIVE_NIEDRIG == 0.3
    assert config.PERCUSSIVE_ABZUG == 0.10
    assert config.KICK_KONFLIKT_ABZUG == 0.15
    assert config.MIDS_HIGHS_DELTA_MAX == 15.0
    assert config.PSSI_MOOD_ABZUG == 0.10
    assert config.ENERGIE_TREND_WIDERSPRUCH == 0.8
    assert config.STRUKTUR_LABEL_BONUS == 0.10
    assert 0.0 < config.PERCUSSIVE_NIEDRIG < config.PERCUSSIVE_HOCH < 1.0
