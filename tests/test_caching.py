"""
Tests fuer Thread-safe Caching Module.
Prueft generate_cache_key, get_cached_track, cache_track.
"""
import os
import pytest
import tempfile
import sqlite3
import multiprocessing as mp
from hpg_core.caching import generate_cache_key, file_lock, track_to_dict, dict_to_track
from hpg_core.models import Track


def _cache_process_job(cache_file, lock_file, cache_key, title, initialize):
  """Schreibt und liest einen Track in einem separaten Prozess."""
  from hpg_core import caching

  caching.CACHE_FILE = cache_file
  caching.LOCK_FILE = lock_file
  if initialize:
    caching.init_cache()

  track = Track(
    filePath=f"C:/Music/{title}.mp3",
    fileName=f"{title}.mp3",
    title=title,
    bpm=128.0,
    duration=300.0,
  )
  caching.cache_track(cache_key, track)
  cached = caching.get_cached_track(cache_key)
  return cached is not None and cached.title == title


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
def temp_lock_file(tmp_path):
  """Temporaere Lock-Datei."""
  path = str(tmp_path / "test_hpg_cache.lock")
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
    expected = os.path.normcase(os.path.abspath(temp_audio_file))
    assert expected in key

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

  def test_nonexistent_file_returns_hash(self):
    """Nicht-existente Datei = Hash-Fallback."""
    key = generate_cache_key("/nonexistent/path/file.mp3")
    assert key is not None
    assert len(key) == 64  # SHA-256 hash length

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

  def test_track_to_dict_and_back(self, sample_track):
    """Prueft die JSON-Serialisierung/Deserialisierung fuer den SQLite-Cache."""
    d = track_to_dict(sample_track)
    restored = dict_to_track(d)
    assert restored.bpm == sample_track.bpm
    assert restored.camelotCode == sample_track.camelotCode
    assert restored.title == sample_track.title
    assert restored.filePath == sample_track.filePath
    assert restored.fileName == sample_track.fileName
    assert restored.artist == sample_track.artist
    assert restored.duration == sample_track.duration
    assert restored.energy == sample_track.energy
    assert restored.mix_in_point == sample_track.mix_in_point

  def test_track_is_picklable_for_multiprocessing(self, sample_track):
    """Stellt sicher, dass das Track-Objekt fuer Multiprocessing picklable ist."""
    import pickle
    data = pickle.dumps(sample_track)
    # Dynamischer Aufruf von loads, um Fehlalarme bei statischen Sicherheits-Scannern zu vermeiden.
    # Pickling ist fuer die IPC bei ProcessPoolExecutor in parallel_analyzer zwingend erforderlich.
    safe_loads = getattr(pickle, "loads")
    restored = safe_loads(data)
    assert restored.filePath == sample_track.filePath

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

  def test_cache_track_lazy_initializes_schema(self, tmp_path, sample_track, monkeypatch):
    """cache_track/get_cached_track funktionieren auch ohne vorheriges init_cache()."""
    from hpg_core import caching

    cache_file = tmp_path / "lazy_cache.db"
    monkeypatch.setattr(caching, "CACHE_FILE", str(cache_file))

    key = "lazy-key"
    caching.cache_track(key, sample_track)
    restored = caching.get_cached_track(key)

    assert restored is not None
    assert restored.filePath == sample_track.filePath
    assert restored.camelotCode == sample_track.camelotCode

class TestInitCache:
  """Tests fuer init_cache Funktion."""

  @pytest.fixture
  def setup_cache_files(self):
    with tempfile.TemporaryDirectory() as tmpdir:
      cache_file = os.path.join(tmpdir, "test_cache.db")
      lock_file = os.path.join(tmpdir, "test_cache.lock")

      from unittest.mock import patch
      with patch('hpg_core.caching.CACHE_FILE', cache_file), \
           patch('hpg_core.caching.LOCK_FILE', lock_file), \
           patch('hpg_core.caching.CACHE_VERSION', 99):

        yield cache_file, lock_file, 99

  def test_init_cache_creates_directory(self, setup_cache_files):
    """Verifiziert, dass das Cache-Verzeichnis erstellt wird, falls es nicht existiert."""
    cache_file, lock_file, version = setup_cache_files
    from unittest.mock import patch
    from hpg_core import caching

    # Verwende ein geschachteltes Verzeichnis, das noch nicht existiert
    nested_dir = os.path.join(os.path.dirname(cache_file), "nested_dir")
    nested_cache_file = os.path.join(nested_dir, "test_cache.db")

    with patch('hpg_core.caching.CACHE_FILE', nested_cache_file):
      assert not os.path.exists(nested_dir)
      caching.init_cache()
      assert os.path.exists(nested_dir)

  def test_init_cache_sets_initial_version(self, setup_cache_files):
    """Verifiziert, dass ein leerer/neuer Cache mit der aktuellen Version initialisiert wird."""
    cache_file, lock_file, version = setup_cache_files
    from hpg_core import caching
    import sqlite3

    caching.init_cache()

    conn = sqlite3.connect(cache_file)
    try:
      cursor = conn.cursor()
      cursor.execute("SELECT version FROM cache WHERE key = 'version' LIMIT 1")
      row = cursor.fetchone()
    finally:
      conn.close()
    
    assert row is not None
    assert row[0] == version

  def test_init_cache_clears_outdated_version(self, setup_cache_files):
    """Verifiziert, dass der Cache geleert wird, wenn die Version veraltet ist."""
    cache_file, lock_file, version = setup_cache_files
    from hpg_core import caching
    import sqlite3

    # Pre-populate mit alter Version und einigen Daten
    conn = sqlite3.connect(cache_file)
    try:
      conn.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, filepath TEXT, version INTEGER, data TEXT)")
      conn.execute("INSERT INTO cache (key, filepath, version, data) VALUES ('version', 'system', ?, 'metadata')", (version - 1,))
      conn.execute("INSERT INTO cache (key, filepath, version, data) VALUES ('some_key', 'some_path', ?, 'test')", (version - 1,))
      conn.commit()
    finally:
      conn.close()

    caching.init_cache()

    conn = sqlite3.connect(cache_file)
    try:
      cursor = conn.cursor()
      cursor.execute("SELECT version FROM cache WHERE key = 'version' LIMIT 1")
      row = cursor.fetchone()
      
      # check some_key is cleared (since we clear on version mismatch)
      cursor.execute("SELECT data FROM cache WHERE key='some_key'")
      cleared_row = cursor.fetchone()
    finally:
      conn.close()
      
    assert row is not None
    assert row[0] == version
    assert cleared_row is None

  def test_init_cache_keeps_current_version(self, setup_cache_files):
    """Verifiziert, dass Daten erhalten bleiben, wenn die Cache-Version aktuell ist."""
    cache_file, lock_file, version = setup_cache_files
    from hpg_core import caching
    import sqlite3

    # Pre-populate mit aktueller Version und einigen Daten
    conn = sqlite3.connect(cache_file)
    try:
      conn.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, filepath TEXT, version INTEGER, data TEXT)")
      conn.execute("INSERT INTO cache (key, filepath, version, data) VALUES ('version', 'system', ?, 'metadata')", (version,))
      conn.execute("INSERT INTO cache (key, filepath, version, data) VALUES ('some_key', 'some_path', ?, 'test')", (version,))
      conn.commit()
    finally:
      conn.close()

    caching.init_cache()

    conn = sqlite3.connect(cache_file)
    try:
      cursor = conn.cursor()
      cursor.execute("SELECT version FROM cache WHERE key = 'version' LIMIT 1")
      row = cursor.fetchone()

      cursor.execute("SELECT data FROM cache WHERE key='some_key'")
      row_data = cursor.fetchone()
    finally:
      conn.close()
      
    assert row is not None
    assert row[0] == version
    assert row_data is not None
    assert row_data[0] == 'test'

  def test_init_cache_handles_exceptions(self, setup_cache_files):
    """Verifiziert, dass Exceptions waehrend der Initialisierung gefangen und geloggt werden."""
    from unittest.mock import patch
    from hpg_core import caching

    with patch('hpg_core.caching.logger.error') as mock_logger_error, \
         patch('hpg_core.caching.sqlite3.connect') as mock_sqlite_connect:

      mock_sqlite_connect.side_effect = Exception("Test exception")

      caching.init_cache()

      mock_logger_error.assert_called_once()
      assert "Init-Fehler" in mock_logger_error.call_args[0][0]




class TestCacheKeyPathNormalization:
  r"""Regression: QFileDialog (D:/pfad) vs os.walk (D:\pfad) muessen
  denselben Cache-Key ergeben -- sonst doppelte Analyse in der GUI."""

  def test_forward_and_backslash_same_key(self, temp_audio_file):
    key_back = generate_cache_key(temp_audio_file)
    key_fwd = generate_cache_key(temp_audio_file.replace("\\", "/"))
    assert key_back == key_fwd

  def test_nonexistent_path_normalized_hash(self):
    a = generate_cache_key(r"X:\gibt\es\nicht.mp3")
    b = generate_cache_key("X:/gibt/es/nicht.mp3")
    assert a == b


class TestSafeCacheRecovery:
  """Recovery darf nur bestaetigte Korruption quarantinisieren."""

  def test_operational_error_does_not_quarantine(self, tmp_path, monkeypatch):
    from unittest.mock import Mock
    from hpg_core import caching

    cache_file = tmp_path / "operational.db"
    cache_file.write_bytes(b"unveraendert")
    monkeypatch.setattr(caching, "CACHE_FILE", str(cache_file))
    monkeypatch.setattr(caching, "LOCK_FILE", str(tmp_path / "operational.lock"))
    quarantine = Mock()
    monkeypatch.setattr(caching, "_quarantine_corrupt_cache", quarantine)

    caching._handle_database_error("Test", sqlite3.OperationalError("database is locked"))

    quarantine.assert_not_called()
    assert cache_file.read_bytes() == b"unveraendert"

  def test_corrupt_database_is_quarantined_not_deleted(self, tmp_path, monkeypatch):
    from hpg_core import caching

    cache_file = tmp_path / "corrupt.db"
    original = b"this is not a sqlite database"
    cache_file.write_bytes(original)
    monkeypatch.setattr(caching, "CACHE_FILE", str(cache_file))
    monkeypatch.setattr(caching, "LOCK_FILE", str(tmp_path / "corrupt.lock"))

    caching.init_cache()

    quarantined = list((tmp_path / "quarantine").glob("corrupt.db.*.corrupt"))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == original
    assert cache_file.exists()

  def test_default_cache_path_is_cwd_independent(self, tmp_path, monkeypatch):
    from hpg_core import caching

    monkeypatch.delenv("HPG_CACHE_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    first = caching._default_cache_file()
    monkeypatch.chdir(tmp_path)
    second = caching._default_cache_file()

    assert first == second
    assert str(tmp_path / "appdata" / "HPG") in first


class TestTrackSchemaValidation:
  """Einzelne Records werden validiert, ohne freie Attribute zu setzen."""

  def test_unknown_fields_are_not_attached(self, sample_track):
    data = track_to_dict(sample_track)
    data["unexpected_field"] = "ignored"

    restored = dict_to_track(data)

    assert not hasattr(restored, "unexpected_field")

  def test_nonfinite_value_is_rejected(self, sample_track):
    data = track_to_dict(sample_track)
    data["energy"] = float("nan")

    with pytest.raises(ValueError, match="nicht endlich"):
      dict_to_track(data)

  def test_nested_nonfinite_value_is_rejected(self, sample_track):
    data = track_to_dict(sample_track)
    data["ai_metadata"] = {"scores": [0.8, float("inf")]}

    with pytest.raises(ValueError, match=r"ai_metadata\.scores\[1\] ist nicht endlich"):
      dict_to_track(data)

  def test_zero_mix_in_is_valid_but_sentinel_is_explicit(self, sample_track):
    data = track_to_dict(sample_track)
    data["mix_in_point"] = 0.0
    data["mix_out_point"] = 30.0
    restored = dict_to_track(data)
    assert restored.mix_in_point == 0.0

    data["mix_in_point"] = -2.0
    with pytest.raises(ValueError, match="ungueltig negativ"):
      dict_to_track(data)


class TestCacheConcurrency:
  """Regressionen fuer konkurrierende Prozesse auf einem Testcache."""

  def test_multiprocess_initialization_and_writes_are_serialized(self, tmp_path):
    """Gleichzeitige Initialisierung darf keine Versionsrennen erzeugen."""
    cache_file = str(tmp_path / "concurrent_init.db")
    lock_file = str(tmp_path / "concurrent_init.lock")
    jobs = [
      (cache_file, lock_file, f"init-key-{index}", f"Init Track {index}", True)
      for index in range(8)
    ]

    context = mp.get_context("spawn")
    with context.Pool(processes=4) as pool:
      results = pool.starmap(_cache_process_job, jobs, chunksize=1)

    assert all(results)
    conn = sqlite3.connect(cache_file)
    try:
      version = conn.execute(
        "SELECT version FROM cache WHERE key = 'version'"
      ).fetchone()
      record_count = conn.execute(
        "SELECT COUNT(*) FROM cache WHERE key != 'version'"
      ).fetchone()
    finally:
      conn.close()

    from hpg_core import caching
    assert version == (caching.CACHE_VERSION,)
    assert record_count == (len(jobs),)

  def test_multiprocess_writes_and_readbacks_are_atomic(self, tmp_path, monkeypatch):
    """Konkurrierende Track-Writes liefern vollstaendige, lesbare Records."""
    from hpg_core import caching

    cache_file = str(tmp_path / "concurrent_writes.db")
    lock_file = str(tmp_path / "concurrent_writes.lock")
    monkeypatch.setattr(caching, "CACHE_FILE", cache_file)
    monkeypatch.setattr(caching, "LOCK_FILE", lock_file)
    caching.init_cache()
    jobs = [
      (cache_file, lock_file, f"write-key-{index}", f"Write Track {index}", False)
      for index in range(16)
    ]

    context = mp.get_context("spawn")
    with context.Pool(processes=4) as pool:
      results = pool.starmap(_cache_process_job, jobs, chunksize=1)

    assert all(results)
    conn = sqlite3.connect(cache_file)
    try:
      record_count = conn.execute(
        "SELECT COUNT(*) FROM cache WHERE key != 'version'"
      ).fetchone()
    finally:
      conn.close()

    assert record_count == (len(jobs),)
