"""
Tests fuer Thread-safe Caching Module.
Prueft generate_cache_key, get_cached_track, cache_track.
"""
import os
import pytest
import tempfile
from hpg_core.caching import generate_cache_key, file_lock
from hpg_core.models import Track


@pytest.fixture
def temp_audio_file():
  """Erstellt eine temporaere Datei fuer Cache-Key Tests."""
  with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
    f.write(b"fake audio data for testing" * 100)
    path = f.name
  yield path
  if os.path.exists(path):
    os.unlink(path)


@pytest.fixture
def temp_lock_file():
  """Temporaere Lock-Datei."""
  path = os.path.join(tempfile.gettempdir(), "test_hpg_cache.lock")
  yield path
  if os.path.exists(path):
    os.unlink(path)


@pytest.fixture
def sample_track():
  """Track-Objekt fuer Cache-Tests."""
  return Track(
    filePath="C:/Music/Test - Track.mp3",
    fileName="Test - Track.mp3",
    artist="Test Artist",
    title="Test Track",
    bpm=128.0,
    duration=300.0,
    camelotCode="8A",
    energy=75,
  )


class TestGenerateCacheKey:
  """Cache-Key Generierung."""

  def test_returns_string_for_valid_file(self, temp_audio_file):
    """Valide Datei = String Cache-Key."""
    key = generate_cache_key(temp_audio_file)
    assert isinstance(key, str)
    assert len(key) > 0

  def test_includes_path_in_key(self, temp_audio_file):
    """Cache-Key enthaelt Dateipfad."""
    key = generate_cache_key(temp_audio_file)
    assert temp_audio_file in key

  def test_includes_size_in_key(self, temp_audio_file):
    """Cache-Key enthaelt Dateigroesse."""
    key = generate_cache_key(temp_audio_file)
    size = os.stat(temp_audio_file).st_size
    assert str(size) in key

  def test_includes_mtime_in_key(self, temp_audio_file):
    """Cache-Key enthaelt Modifikationszeit."""
    key = generate_cache_key(temp_audio_file)
    mtime = os.stat(temp_audio_file).st_mtime
    assert str(mtime) in key

  def test_different_files_different_keys(self):
    """Verschiedene Dateien = verschiedene Keys."""
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f1:
      f1.write(b"data1")
      path1 = f1.name
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f2:
      f2.write(b"data2different")
      path2 = f2.name

    try:
      key1 = generate_cache_key(path1)
      key2 = generate_cache_key(path2)
      assert key1 != key2
    finally:
      os.unlink(path1)
      os.unlink(path2)

  def test_none_returns_none(self):
    """None Input = None Output."""
    assert generate_cache_key(None) is None

  def test_empty_string_returns_none(self):
    """Leerer String = None."""
    assert generate_cache_key("") is None

  def test_nonexistent_file_returns_none(self):
    """Nicht-existente Datei = None."""
    key = generate_cache_key("/nonexistent/path/file.mp3")
    assert key is None

  def test_key_format(self, temp_audio_file):
    """Key hat Format: path-size-mtime."""
    key = generate_cache_key(temp_audio_file)
    parts = key.split("-")
    # Sollte mindestens 3 Teile haben (Pfad kann auch - enthalten)
    assert len(parts) >= 3

  def test_same_file_same_key(self, temp_audio_file):
    """Gleiche Datei = gleicher Key (deterministisch)."""
    key1 = generate_cache_key(temp_audio_file)
    key2 = generate_cache_key(temp_audio_file)
    assert key1 == key2


class TestFileLock:
  """File-Lock Mechanismus."""

  def test_lock_creates_file(self, temp_lock_file):
    """Lock erstellt Lock-Datei."""
    with file_lock(temp_lock_file):
      assert os.path.exists(temp_lock_file)

  def test_lock_context_manager(self, temp_lock_file):
    """Lock funktioniert als Context Manager."""
    with file_lock(temp_lock_file) as handle:
      assert handle is not None

  def test_lock_releases_after_context(self, temp_lock_file):
    """Lock wird nach Context Manager freigegeben."""
    with file_lock(temp_lock_file):
      pass
    # Zweiter Lock sollte sofort moeglich sein
    with file_lock(temp_lock_file):
      pass

  def test_lock_with_timeout(self, temp_lock_file):
    """Lock mit Timeout-Parameter."""
    with file_lock(temp_lock_file, timeout=1.0) as handle:
      assert handle is not None


class TestCacheKeyConsistency:
  """Cache-Key Konsistenz ueber verschiedene Szenarien."""

  def test_key_changes_after_modification(self, temp_audio_file):
    """Cache-Key aendert sich nach Dateimodifikation."""
    key_before = generate_cache_key(temp_audio_file)

    # Datei modifizieren (Groesse + mtime aendern)
    import time
    time.sleep(0.1)  # Sicherstellen dass mtime sich aendert
    with open(temp_audio_file, "ab") as f:
      f.write(b"extra data")

    key_after = generate_cache_key(temp_audio_file)
    assert key_before != key_after, (
      "Cache-Key sollte sich nach Modifikation aendern"
    )

  def test_absolute_path_consistency(self, temp_audio_file):
    """Absoluter Pfad liefert konsistenten Key."""
    abs_path = os.path.abspath(temp_audio_file)
    key1 = generate_cache_key(abs_path)
    key2 = generate_cache_key(abs_path)
    assert key1 == key2


class TestCacheIntegration:
  """Integration: Cache-Key + Track speichern/laden."""

  def test_track_is_serializable(self, sample_track):
    """Track-Objekt kann serialisiert werden (fuer shelve)."""
    import pickle
    data = pickle.dumps(sample_track)
    restored = pickle.loads(data)
    assert restored.bpm == sample_track.bpm
    assert restored.camelotCode == sample_track.camelotCode
    assert restored.title == sample_track.title

  def test_track_round_trip(self, sample_track):
    """Track-Objekt uebersteht Serialisierung/Deserialisierung."""
    import pickle
    data = pickle.dumps(sample_track)
    restored = pickle.loads(data)
    assert restored.filePath == sample_track.filePath
    assert restored.fileName == sample_track.fileName
    assert restored.artist == sample_track.artist
    assert restored.duration == sample_track.duration
    assert restored.energy == sample_track.energy
    assert restored.mix_in_point == sample_track.mix_in_point

  def test_cache_key_for_real_path_format(self):
    """Cache-Key fuer typischen DJ-Dateipfad."""
    # Erstelle Datei mit DJ-typischem Namen
    with tempfile.NamedTemporaryFile(
      suffix=".mp3",
      prefix="DJ_Snake_-_Turn_Down_",
      delete=False
    ) as f:
      f.write(b"fake audio" * 50)
      path = f.name

    try:
      key = generate_cache_key(path)
      assert key is not None
      assert isinstance(key, str)
    finally:
      os.unlink(path)
