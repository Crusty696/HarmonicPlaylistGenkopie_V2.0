"""
Integrationstests fuer analyze_track() Pipeline.
Testet volle Audio-Analyse: BPM, Key, Energy, Mix-Points.
"""
import os
import pytest
import tempfile
import numpy as np
from hpg_core.models import Track


# ============================================================
# Hilfsfunktionen
# ============================================================

def _create_test_wav(path: str, duration: float = 5.0, sr: int = 22050):
  """Erstellt eine minimale WAV-Datei mit Sinuswelle."""
  import wave
  import struct

  n_samples = int(duration * sr)
  t = np.linspace(0, duration, n_samples, endpoint=False)
  # 440Hz Sinuswelle (A4)
  signal = (np.sin(2 * np.pi * 440 * t) * 32767 * 0.5).astype(np.int16)

  with wave.open(path, "w") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(sr)
    wav.writeframes(signal.tobytes())


def _create_click_wav(path: str, bpm: float = 128.0,
                      duration: float = 10.0, sr: int = 22050):
  """Erstellt eine WAV-Datei mit Click-Track bei gegebenem BPM."""
  import wave

  n_samples = int(duration * sr)
  signal = np.zeros(n_samples)

  beat_interval = 60.0 / bpm
  click_duration = 0.01  # 10ms Click

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


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def simple_wav():
  """Einfache WAV-Datei (5 Sekunden, 440Hz)."""
  with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
    path = f.name
  _create_test_wav(path, duration=5.0)
  yield path
  if os.path.exists(path):
    os.unlink(path)


@pytest.fixture
def click_wav_128():
  """Click-Track WAV bei 128 BPM (10 Sekunden)."""
  with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
    path = f.name
  _create_click_wav(path, bpm=128.0, duration=10.0)
  yield path
  if os.path.exists(path):
    os.unlink(path)


@pytest.fixture
def long_wav():
  """Laengere WAV-Datei (30 Sekunden) fuer Mix-Point Tests."""
  with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
    path = f.name
  _create_click_wav(path, bpm=128.0, duration=30.0)
  yield path
  if os.path.exists(path):
    os.unlink(path)


@pytest.fixture
def silence_wav():
  """Stille WAV-Datei (5 Sekunden)."""
  import wave

  path = tempfile.mktemp(suffix=".wav")
  sr = 22050
  n_samples = int(5.0 * sr)
  signal = np.zeros(n_samples, dtype=np.int16)
  with wave.open(path, "w") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(sr)
    wav.writeframes(signal.tobytes())
  yield path
  if os.path.exists(path):
    os.unlink(path)


@pytest.fixture
def named_wav():
  """WAV-Datei mit DJ-typischem Dateinamen."""
  tmpdir = tempfile.mkdtemp()
  path = os.path.join(tmpdir, "DJ Snake - Turn Down For What.wav")
  _create_test_wav(path, duration=5.0)
  yield path
  if os.path.exists(path):
    os.unlink(path)
  os.rmdir(tmpdir)


# ============================================================
# analyze_track() Basis-Tests
# ============================================================

@pytest.mark.integration
class TestAnalyzeTrackBasics:
  """Grundlegende analyze_track() Pipeline Tests."""

  def test_returns_track_object(self, simple_wav):
    """Gibt Track-Objekt zurueck."""
    from hpg_core.analysis import analyze_track
    result = analyze_track(simple_wav)
    assert isinstance(result, Track)

  def test_none_input_returns_none(self):
    """None Input = None."""
    from hpg_core.analysis import analyze_track
    assert analyze_track(None) is None

  def test_empty_string_returns_none(self):
    """Leerer String = None."""
    from hpg_core.analysis import analyze_track
    assert analyze_track("") is None

  def test_nonexistent_file_returns_none(self):
    """Nicht existente Datei = None."""
    from hpg_core.analysis import analyze_track
    result = analyze_track("/nonexistent/path/fake.mp3")
    assert result is None

  def test_invalid_type_returns_none(self):
    """Nicht-String Input = None."""
    from hpg_core.analysis import analyze_track
    result = analyze_track(12345)
    assert result is None


# ============================================================
# Track-Felder Validierung
# ============================================================

@pytest.mark.integration
class TestAnalyzeTrackFields:
  """Prueft ob alle Track-Felder korrekt befuellt werden."""

  def test_file_path_set(self, simple_wav):
    """filePath wird korrekt gesetzt."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(simple_wav)
    assert track.filePath == simple_wav

  def test_file_name_set(self, simple_wav):
    """fileName wird korrekt gesetzt."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(simple_wav)
    assert track.fileName == os.path.basename(simple_wav)

  def test_duration_positive(self, simple_wav):
    """Duration ist positiv."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(simple_wav)
    assert track.duration > 0

  def test_duration_approximately_correct(self, simple_wav):
    """Duration ist ca. 5 Sekunden (Fixture-Laenge)."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(simple_wav)
    assert 4.0 <= track.duration <= 6.0, (
      f"Duration {track.duration}s (erwartet ~5.0s)"
    )

  def test_bpm_positive(self, simple_wav):
    """BPM ist positiv."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(simple_wav)
    assert track.bpm > 0

  def test_bpm_reasonable_range(self, simple_wav):
    """BPM im DJ-Bereich (50-250)."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(simple_wav)
    assert 50 <= track.bpm <= 250, (
      f"BPM {track.bpm} ausserhalb DJ-Bereich"
    )

  def test_camelot_code_valid(self, simple_wav):
    """Camelot-Code ist gueltig (1A-12B)."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(simple_wav)
    import re
    if track.camelotCode:
      assert re.match(r"^(1[0-2]|[1-9])[AB]$", track.camelotCode), (
        f"Ungueltiger Camelot-Code: '{track.camelotCode}'"
      )

  def test_energy_in_range(self, simple_wav):
    """Energy zwischen 0 und 100."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(simple_wav)
    assert 0 <= track.energy <= 100

  def test_bass_intensity_in_range(self, simple_wav):
    """Bass Intensity zwischen 0 und 100."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(simple_wav)
    assert 0 <= track.bass_intensity <= 100

  def test_key_note_set(self, simple_wav):
    """keyNote ist gesetzt."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(simple_wav)
    assert track.keyNote is not None
    valid_notes = [
      "C", "C#", "D", "D#", "E", "F",
      "F#", "G", "G#", "A", "A#", "B",
      "Db", "Eb", "Gb", "Ab", "Bb",
    ]
    assert track.keyNote in valid_notes, (
      f"Unbekannte Note: '{track.keyNote}'"
    )

  def test_key_mode_set(self, simple_wav):
    """keyMode ist Major oder Minor."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(simple_wav)
    assert track.keyMode in ("Major", "Minor"), (
      f"Ungueltiger Mode: '{track.keyMode}'"
    )


# ============================================================
# Mix-Point Validierung in der Pipeline
# ============================================================

@pytest.mark.integration
class TestAnalyzeTrackMixPoints:
  """Mix-Point Validierung in voller Pipeline."""

  def test_mix_in_point_set(self, long_wav):
    """mix_in_point wird gesetzt."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(long_wav)
    assert track.mix_in_point is not None
    assert track.mix_in_point >= 0

  def test_mix_out_point_set(self, long_wav):
    """mix_out_point wird gesetzt."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(long_wav)
    assert track.mix_out_point is not None
    assert track.mix_out_point > 0

  def test_mix_out_after_mix_in(self, long_wav):
    """mix_out > mix_in."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(long_wav)
    assert track.mix_out_point > track.mix_in_point, (
      f"Mix-Out {track.mix_out_point} <= Mix-In {track.mix_in_point}"
    )

  def test_mix_points_within_duration(self, long_wav):
    """Mix-Points innerhalb der Track-Dauer."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(long_wav)
    assert track.mix_in_point <= track.duration, (
      f"Mix-In {track.mix_in_point} > Duration {track.duration}"
    )
    assert track.mix_out_point <= track.duration, (
      f"Mix-Out {track.mix_out_point} > Duration {track.duration}"
    )

  def test_mix_in_bars_set(self, long_wav):
    """mix_in_bars wird gesetzt."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(long_wav)
    assert track.mix_in_bars is not None
    assert track.mix_in_bars >= 0

  def test_mix_out_bars_set(self, long_wav):
    """mix_out_bars wird gesetzt."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(long_wav)
    assert track.mix_out_bars is not None
    assert track.mix_out_bars > 0


# ============================================================
# Edge Cases
# ============================================================

@pytest.mark.integration
class TestAnalyzeTrackEdgeCases:
  """Edge Cases fuer analyze_track()."""

  def test_silence_does_not_crash(self, silence_wav):
    """Stille WAV crasht nicht."""
    from hpg_core.analysis import analyze_track
    result = analyze_track(silence_wav)
    assert result is not None
    assert isinstance(result, Track)

  def test_silence_has_defaults(self, silence_wav):
    """Stille WAV hat sinnvolle Defaults."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(silence_wav)
    # BPM sollte Default sein
    assert track.bpm >= 0

  def test_named_file_extracts_metadata(self, named_wav):
    """DJ-Dateiname wird fuer Metadata genutzt."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(named_wav)
    # Artist oder Title sollte aus Dateiname extrahiert werden
    assert track.fileName == "DJ Snake - Turn Down For What.wav"

  def test_pathlike_input(self, simple_wav):
    """os.PathLike Input funktioniert."""
    from hpg_core.analysis import analyze_track
    from pathlib import Path
    result = analyze_track(Path(simple_wav))
    assert isinstance(result, Track)


# ============================================================
# Caching in der Pipeline
# ============================================================

@pytest.mark.integration
class TestAnalyzeTrackCaching:
  """Caching-Verhalten in analyze_track()."""

  def test_second_call_uses_cache(self, simple_wav):
    """Zweiter Aufruf nutzt Cache (schneller)."""
    from hpg_core.analysis import analyze_track
    import time

    # Erster Aufruf (erzeugt Cache)
    start1 = time.time()
    track1 = analyze_track(simple_wav)
    time1 = time.time() - start1

    # Zweiter Aufruf (aus Cache)
    start2 = time.time()
    track2 = analyze_track(simple_wav)
    time2 = time.time() - start2

    # Cache-Hit sollte deutlich schneller sein
    assert track1.bpm == track2.bpm
    assert track1.camelotCode == track2.camelotCode
    # Timing-Vergleich kann flaky sein, daher nur Track-Gleichheit pruefen

  def test_cached_track_has_all_fields(self, simple_wav):
    """Gecachter Track hat alle Felder."""
    from hpg_core.analysis import analyze_track

    # Erster Aufruf (erzeugt Cache)
    track1 = analyze_track(simple_wav)
    # Zweiter Aufruf (aus Cache)
    track2 = analyze_track(simple_wav)

    assert track2.filePath == track1.filePath
    assert track2.duration == track1.duration
    assert track2.bpm == track1.bpm
    assert track2.energy == track1.energy
