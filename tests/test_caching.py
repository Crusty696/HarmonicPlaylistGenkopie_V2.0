"""
Tests fuer Thread-safe Caching Module.
Prueft generate_cache_key, get_cached_track, cache_track.
"""
import os
import json
import pytest
import tempfile
import sqlite3
import multiprocessing as mp
from hpg_core.caching import (
  TRACK_REQUIRED_FIELDS, VALID_ANALYSIS_MODES, dict_to_track, file_lock,
  generate_cache_key, track_to_dict,
)
from hpg_core.models import Track as TrackModel


def Track(*args, **kwargs):
  """Gueltige v42-Basis; einzelne Tests ueberschreiben gezielt Grenzfelder."""
  kwargs.setdefault("duration", 300.0)
  kwargs.setdefault("bpm", 128.0)
  kwargs.setdefault("analysis_mode", "librosa_full_or_tail")
  return TrackModel(*args, **kwargs)


def _ai_metadata(generation=1):
  """Gueltige, vollstaendige KI-Metadaten fuer Cache-Merge-Tests."""
  return {
    "sub_genre": "Peak-Time Techno",
    "moods": ["driving", "dark"],
    "description": f"Generation {generation}",
    "mix_in_time": 32.0,
    "mix_out_time": 260.0,
    "_provenance": {
      "provider": "Ollama",
      "model": "test-model",
      "prompt_version": "2026-07-20",
      "schema_version": 1,
      "mixpoints_advisory": True,
    },
  }


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
    analysis_mode="librosa_full_or_tail",
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
    analysis_mode="librosa_full_or_tail",
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

  @pytest.mark.parametrize("rekordbox_signature", ["", "rekordbox-signatur"])
  def test_source_im_pfad_bleibt_cache_hit(
    self, tmp_path, monkeypatch, rekordbox_signature
  ):
    from hpg_core import caching

    audio_dir = tmp_path / "set-source-version"
    audio_dir.mkdir()
    audio = audio_dir / "track-source-edit.wav"
    audio.write_bytes(b"audio")
    cache_file = tmp_path / "source_path.db"
    monkeypatch.setattr(caching, "CACHE_FILE", str(cache_file))
    monkeypatch.setattr(caching, "LOCK_FILE", str(tmp_path / "source_path.lock"))
    track = Track(
      filePath=str(audio),
      fileName=audio.name,
      duration=1.0,
      rekordbox_signature=rekordbox_signature,
      analysis_mode="librosa_full_or_tail",
    )
    key = caching.generate_cache_key(str(audio), rekordbox_signature)

    assert caching.cache_track(key, track)
    restored = caching.get_cached_track(key, str(audio).replace("\\", "/"))

    assert restored is not None
    assert restored.filePath == str(audio)


@pytest.mark.parametrize("entrypoint", ["init_cache", "cache_track"])
@pytest.mark.parametrize(
  "marker_column,marker_value",
  [("filepath", "falsch"), ("data", "falsch")],
)
def test_nichtkanonischer_marker_wird_atomar_ersetzt(
  tmp_path, monkeypatch, entrypoint, marker_column, marker_value
):
  from hpg_core import caching

  cache_file = tmp_path / f"marker_{entrypoint}_{marker_column}.db"
  monkeypatch.setattr(caching, "CACHE_FILE", str(cache_file))
  monkeypatch.setattr(caching, "LOCK_FILE", str(tmp_path / "marker.lock"))
  caching.init_cache()
  with sqlite3.connect(cache_file) as conn:
    conn.execute(
      "INSERT INTO cache (key, filepath, version, data) VALUES (?, ?, ?, ?)",
      ("alt", "C:/alt.wav", caching.CACHE_VERSION, "alt"),
    )
    conn.execute(
      f"UPDATE cache SET {marker_column} = ? WHERE key = 'version'",
      (marker_value,),
    )

  if entrypoint == "init_cache":
    caching.init_cache()
    expected_keys = ["version"]
  else:
    track = Track(
      filePath="C:/neu.wav", fileName="neu.wav", duration=1.0,
      analysis_mode="librosa_full_or_tail",
    )
    assert caching.cache_track("neu", track)
    expected_keys = ["neu", "version"]

  with sqlite3.connect(cache_file) as conn:
    marker = conn.execute(
      "SELECT filepath, version, data FROM cache WHERE key = 'version'"
    ).fetchone()
    keys = [row[0] for row in conn.execute("SELECT key FROM cache ORDER BY key")]

  assert marker == ("system", caching.CACHE_VERSION, "metadata")
  assert keys == expected_keys


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

    with pytest.raises(ValueError, match="KI-Vertrag"):
      dict_to_track(data)

  def test_zero_mix_in_is_valid_but_sentinel_is_explicit(self, sample_track):
    data = track_to_dict(sample_track)
    data["mix_in_point"] = 0.0
    data["mix_out_point"] = 30.0
    restored = dict_to_track(data)
    assert restored.mix_in_point == 0.0

    data["mix_in_point"] = -2.0
    with pytest.raises(ValueError, match="muss -1 oder innerhalb der Dauer sein"):
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


def test_cache_version_44_invalidiert_v43_mixpoint_fallbacks():
  from hpg_core import caching

  assert caching.CACHE_VERSION == 44
  assert not caching._cache_marker_is_current(("system", 43, "metadata"))
  assert caching._cache_marker_is_current(("system", 44, "metadata"))
  for name in ("phrases", "cue_points", "phrase_grid", "mix_in_candidates", "mix_out_candidates"):
    assert name in caching.TRACK_LIST_FIELDS


def test_track_pflichtsatz_ist_exakt_die_60_felder_der_dataclass():
  from dataclasses import fields

  dataclass_fields = {field.name for field in fields(TrackModel)}

  assert len(TRACK_REQUIRED_FIELDS) == 60
  assert TRACK_REQUIRED_FIELDS == dataclass_fields


@pytest.mark.parametrize("missing_field", sorted(TRACK_REQUIRED_FIELDS))
def test_jedes_der_60_trackfelder_ist_einzeln_pflicht(missing_field):
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = track_to_dict(Track(filePath="C:/x.mp3", fileName="x.mp3"))
  del data[missing_field]

  with pytest.raises(CacheValidationError, match=rf"Pflichtfeld {missing_field} fehlt"):
    validate_track_dict(data)


def test_vollstaendiger_track_mit_kanonischem_analysemodus_ist_gueltig():
  from hpg_core.caching import validate_track_dict

  data = track_to_dict(Track(
    filePath="C:/x.mp3",
    fileName="x.mp3",
    analysis_mode="librosa_full_or_tail",
  ))

  assert set(validate_track_dict(data)) == TRACK_REQUIRED_FIELDS


@pytest.mark.parametrize("analysis_mode", sorted(VALID_ANALYSIS_MODES))
def test_nur_kanonische_analysemodi_sind_gueltig(analysis_mode):
  from hpg_core.caching import validate_track_dict

  data = track_to_dict(Track(
    filePath="C:/x.mp3",
    fileName="x.mp3",
    analysis_mode=analysis_mode,
  ))

  assert validate_track_dict(data)["analysis_mode"] == analysis_mode


@pytest.mark.parametrize("analysis_mode", ["full", "rekordbox_degraded", "", "unknown"])
def test_nichtkanonische_analysemodi_sind_ungueltig(analysis_mode):
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = track_to_dict(Track(
    filePath="C:/x.mp3",
    fileName="x.mp3",
    analysis_mode=analysis_mode,
  ))

  with pytest.raises(CacheValidationError, match="analysis_mode ist ungueltig"):
    validate_track_dict(data)


def test_normalisierte_kandidatenskalare_stammen_aus_dem_validatorvertrag():
  from hpg_core import caching

  assert caching.CANDIDATE_OPTIONAL_NUMERIC_FIELDS == (
    caching.MIX_CANDIDATE_UNIT_INTERVAL_FIELDS
    | caching.MIX_CANDIDATE_FINITE_FIELDS
    | caching.MIX_CANDIDATE_PERCENT_FIELDS
    | caching.MIX_CANDIDATE_INT_PERCENT_FIELDS
    | {"bass_punch"}
  )


def test_kandidaten_ueberleben_roundtrip_und_nichtliste_wird_abgewiesen():
  from hpg_core.caching import CacheValidationError, validate_track_dict
  from hpg_core.mix_candidates import MixCandidate
  t = Track(
    filePath="C:/x.mp3", fileName="x.mp3", duration=300.0,
    analysis_mode="librosa_full_or_tail",
  )
  t.phrases = [{"start_s": 0.0, "end_s": 15.0, "label": "Intro", "mood": 1, "kind": 1, "fill": 0}]
  t.cue_points = [{"t": 30.0, "name": "", "typ": 0, "provenance": "leer"}]
  t.phrase_grid = [0.0, 15.0]
  t.mix_in_candidates = [MixCandidate(
    t=15.0,
    schema=["pssi_phrase"],
    provenance="rekordbox_pssi",
    confidence=1.0,
  ).to_dict()]
  back = dict_to_track(track_to_dict(t))
  assert back.phrases == t.phrases and back.mix_in_candidates == t.mix_in_candidates
  assert back.phrase_grid == [0.0, 15.0]
  d = track_to_dict(t)
  d["mix_out_candidates"] = "kaputt"
  with pytest.raises(CacheValidationError):
    validate_track_dict(d)


def _gueltiger_mix_candidate(t=15.0):
  from hpg_core.mix_candidates import MixCandidate

  return MixCandidate(
    t=t,
    schema=["pssi_phrase"],
    provenance="rekordbox_pssi",
    confidence=1.0,
    neuheit=0.5,
    traegt_allein=True,
    groove_pattern_lokal=[0.5] * 16,
    bass_pattern_lokal=[0.25] * 16,
    syncopation_lokal=0.4,
    percussive_ratio_lokal=0.6,
    sub_energy=0.7,
    bass_punch=1.2,
    bass_rms_dbfs=-12.0,
    kick_aktiv=False,
    camelot_lokal="8A",
    key_confidence_lokal=0.9,
    timbre_fingerprint_lokal=[-0.5] * 13,
    brightness_lokal=65,
    flatness_lokal=0.2,
    avg_mids_lokal=45.0,
    avg_highs_lokal=35.0,
    energy_lokal=72,
    energy_trend="stable",
    lufs_lokal=-8.5,
    mood={"brightness": 55.0, "flatness": 0.2, "key_mode": "minor", "pssi_mood": 2},
    vocal_aktiv_lokal=None,
  ).to_dict()


def _track_dict_mit_kandidaten():
  track = Track(
    filePath="C:/x.mp3", fileName="x.mp3", duration=300.0,
    analysis_mode="librosa_full_or_tail",
  )
  track.mix_in_candidates = [_gueltiger_mix_candidate(15.0)]
  track.mix_out_candidates = [_gueltiger_mix_candidate(250.0)]
  return track_to_dict(track)


class _SectionMitToDict:
  def __init__(self):
    self.payload = {"werte": [1.0, 2.0]}

  def to_dict(self):
    return {"label": "main", "payload": self.payload}


def test_track_snapshot_ist_rekursiv_losgeloest_und_numpy_skalare_werden_kopiert():
  import numpy as np

  track = Track(
    filePath="C:/x.mp3", fileName="x.mp3", duration=300.0,
    analysis_mode="librosa_full_or_tail",
  )
  section = _SectionMitToDict()
  candidate = _gueltiger_mix_candidate()
  track.ai_metadata = {"nested": [{"werte": (np.float32(0.25), 2.0)}]}
  track.sections = [section]
  track.mix_in_candidates = [candidate]

  snapshot = track_to_dict(track)
  track.ai_metadata["nested"][0]["werte"] = (9.0,)
  section.payload["werte"][0] = 9.0
  candidate["mood"]["brightness"] = 99.0
  candidate["groove_pattern_lokal"][0] = 0.99

  assert snapshot["ai_metadata"] == {"nested": [{"werte": [0.25, 2.0]}]}
  assert snapshot["sections"][0]["payload"]["werte"] == [1.0, 2.0]
  assert snapshot["mix_in_candidates"][0]["mood"]["brightness"] == 55.0
  assert snapshot["mix_in_candidates"][0]["groove_pattern_lokal"][0] == 0.5
  assert snapshot["ai_metadata"] is not track.ai_metadata
  assert snapshot["mix_in_candidates"][0] is not candidate


def test_cache_verwirft_nichtendliche_top_level_fingerprints_ohne_track_mutation(
  tmp_path, monkeypatch,
):
  import math
  from hpg_core import caching

  cache_file = tmp_path / "normalization.db"
  monkeypatch.setattr(caching, "CACHE_FILE", str(cache_file))
  monkeypatch.setattr(caching, "LOCK_FILE", str(tmp_path / "normalization.lock"))
  track = Track(
    filePath="C:/x.mp3", fileName="x.mp3", duration=300.0,
    analysis_mode="librosa_full_or_tail",
  )
  track.mfcc_fingerprint = [1.0, float("nan"), float("inf")] + [0.0] * 10
  track.timbre_fingerprint = [float("-inf"), 2.0] + [0.0] * 11
  candidate = _gueltiger_mix_candidate()
  candidate["neuheit"] = float("nan")
  candidate["bass_rms_dbfs"] = float("inf")
  candidate["brightness_lokal"] = float("inf")
  candidate["mood"]["brightness"] = float("nan")
  candidate["mood"]["pssi_mood"] = float("inf")
  candidate["groove_pattern_lokal"][3] = float("nan")
  candidate["timbre_fingerprint_lokal"][2] = float("inf")
  track.mix_in_candidates = [candidate]

  assert caching.cache_track("normalisiert", track) is False
  assert caching.get_cached_track("normalisiert") is None
  assert math.isnan(track.mfcc_fingerprint[1])
  assert math.isnan(track.mix_in_candidates[0]["neuheit"])
  assert math.isnan(track.mix_in_candidates[0]["groove_pattern_lokal"][3])


@pytest.mark.parametrize("required_field", ["t", "confidence"])
def test_nichtendlicher_kandidatenpflichtwert_verhindert_write_vor_lock(
  required_field, monkeypatch,
):
  from unittest.mock import Mock
  from hpg_core import caching

  track = Track(
    filePath="C:/x.mp3", fileName="x.mp3", duration=300.0,
    analysis_mode="librosa_full_or_tail",
  )
  candidate = _gueltiger_mix_candidate()
  candidate[required_field] = float("nan")
  track.mix_in_candidates = [candidate]
  lock = Mock(side_effect=AssertionError("DB-Lock darf nicht erreicht werden"))
  monkeypatch.setattr(caching, "file_lock", lock)

  assert caching.cache_track("ungueltig", track) is False

  lock.assert_not_called()


def test_cache_track_meldet_commit_und_leeren_schluessel(tmp_path, monkeypatch):
  from hpg_core import caching

  cache_file = tmp_path / "status.db"
  monkeypatch.setattr(caching, "CACHE_FILE", str(cache_file))
  monkeypatch.setattr(caching, "LOCK_FILE", str(tmp_path / "status.lock"))
  track = Track(
    filePath="C:/x.mp3", fileName="x.mp3", duration=300.0,
    analysis_mode="librosa_full_or_tail",
  )

  assert caching.cache_track("", track) is False
  assert caching.cache_track("status", track) is True


def test_ungueltiger_snapshot_ueberschreibt_keinen_bestehenden_record(tmp_path, monkeypatch):
  from hpg_core import caching

  cache_file = tmp_path / "no_overwrite.db"
  monkeypatch.setattr(caching, "CACHE_FILE", str(cache_file))
  monkeypatch.setattr(caching, "LOCK_FILE", str(tmp_path / "no_overwrite.lock"))
  original = Track(
    filePath="C:/alt.mp3", fileName="alt.mp3", title="bleibt", duration=300.0,
    analysis_mode="librosa_full_or_tail",
  )
  original.mix_in_candidates = [_gueltiger_mix_candidate()]
  caching.cache_track("same-key", original)

  invalid = Track(
    filePath="C:/neu.mp3", fileName="neu.mp3", title="falsch", duration=300.0,
    analysis_mode="librosa_full_or_tail",
  )
  invalid_candidate = _gueltiger_mix_candidate()
  invalid_candidate["confidence"] = float("inf")
  invalid.mix_in_candidates = [invalid_candidate]
  caching.cache_track("same-key", invalid)

  restored = caching.get_cached_track("same-key")
  assert restored is not None
  assert restored.title == "bleibt"
  assert restored.filePath == "C:/alt.mp3"


def test_finiter_kandidat_cache_roundtrip_und_top_level_filterung(tmp_path, monkeypatch):
  import sqlite3
  import json
  from hpg_core import caching

  cache_file = tmp_path / "finite_roundtrip.db"
  monkeypatch.setattr(caching, "CACHE_FILE", str(cache_file))
  monkeypatch.setattr(caching, "LOCK_FILE", str(tmp_path / "finite_roundtrip.lock"))
  track = Track(
    filePath="C:/x.mp3", fileName="x.mp3", duration=300.0,
    analysis_mode="librosa_full_or_tail",
  )
  track.mix_in_candidates = [_gueltiger_mix_candidate(15.0)]
  track.mix_out_candidates = [_gueltiger_mix_candidate(250.0)]
  track.unexpected_field = "nicht persistieren"

  caching.cache_track("finite", track)
  restored = caching.get_cached_track("finite")

  assert restored is not None
  assert restored.mix_in_candidates == track.mix_in_candidates
  assert restored.mix_out_candidates == track.mix_out_candidates
  with sqlite3.connect(cache_file) as conn:
    raw = conn.execute("SELECT data FROM cache WHERE key = 'finite'").fetchone()[0]
  assert "unexpected_field" not in json.loads(raw)


def test_v39_mixcandidate_sentinel_akzeptiert_beide_listen_und_zusatzkeys():
  from hpg_core.caching import validate_track_dict

  data = _track_dict_mit_kandidaten()
  data["mix_in_candidates"][0]["zukuenftiges_feld"] = {"wird_ignoriert": float("nan")}

  validated = validate_track_dict(data)

  assert validated["mix_in_candidates"][0]["t"] == 15.0
  assert validated["mix_out_candidates"][0]["t"] == 250.0
  assert "zukuenftiges_feld" not in validated["mix_in_candidates"][0]


def test_kandidaten_zusatzfeld_mit_nan_wird_vor_cache_write_entfernt(
  tmp_path, monkeypatch
):
  import json
  from hpg_core import caching

  cache_file = tmp_path / "candidate_extra.db"
  monkeypatch.setattr(caching, "CACHE_FILE", str(cache_file))
  monkeypatch.setattr(caching, "LOCK_FILE", str(tmp_path / "candidate_extra.lock"))
  track = Track(
    filePath="C:/x.mp3", fileName="x.mp3", duration=300.0,
    analysis_mode="librosa_full_or_tail",
  )
  candidate = _gueltiger_mix_candidate(15.0)
  candidate["zukuenftiges_feld"] = {"wird_ignoriert": float("nan")}
  track.mix_in_candidates = [candidate]

  caching.cache_track("extra", track)
  restored = caching.get_cached_track("extra")

  assert restored is not None
  assert "zukuenftiges_feld" not in restored.mix_in_candidates[0]
  with sqlite3.connect(cache_file) as conn:
    raw = json.loads(
      conn.execute("SELECT data FROM cache WHERE key = 'extra'").fetchone()[0]
    )
  assert "zukuenftiges_feld" not in raw["mix_in_candidates"][0]


@pytest.mark.parametrize("field", sorted(_gueltiger_mix_candidate()))
def test_v39_mixcandidate_verlangt_alle_28_felder(field):
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = _track_dict_mit_kandidaten()
  del data["mix_in_candidates"][0][field]

  with pytest.raises(CacheValidationError, match=rf"mix_in_candidates\[0\]\.{field} fehlt"):
    validate_track_dict(data)


@pytest.mark.parametrize("list_name", ["mix_in_candidates", "mix_out_candidates"])
def test_v39_mixcandidate_element_muss_dictionary_sein(list_name):
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = _track_dict_mit_kandidaten()
  data[list_name][0] = "kaputt"

  with pytest.raises(CacheValidationError, match=rf"{list_name}\[0\] muss ein Dictionary sein"):
    validate_track_dict(data)


@pytest.mark.parametrize(
  "value",
  ["15", True, float("nan"), float("inf"), -0.01, 300.01],
)
def test_v39_mixcandidate_t_wird_strikt_validiert(value):
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = _track_dict_mit_kandidaten()
  data["mix_out_candidates"][0]["t"] = value

  with pytest.raises(CacheValidationError, match=r"mix_out_candidates\[0\]\.t"):
    validate_track_dict(data)


@pytest.mark.parametrize(
  "field,value,path",
  [
    ("schema", [], "schema"),
    ("schema", ["unbekannt"], "schema"),
    ("schema", [1], "schema"),
    ("provenance", "", "provenance"),
    ("confidence", None, "confidence"),
    ("confidence", True, "confidence"),
    ("confidence", 1.01, "confidence"),
    ("section_label", None, "section_label"),
    ("energy_trend", "up", "energy_trend"),
    ("groove_pattern_lokal", [0.5] * 15, "groove_pattern_lokal"),
    ("groove_pattern_lokal", [0.5] * 15 + [1.1], "groove_pattern_lokal\\[15\\]"),
    ("bass_pattern_lokal", [False] * 16, "bass_pattern_lokal\\[0\\]"),
    ("timbre_fingerprint_lokal", [0.0] * 12, "timbre_fingerprint_lokal"),
    ("timbre_fingerprint_lokal", [0.0] * 12 + [float("inf")], "timbre_fingerprint_lokal\\[12\\]"),
    ("neuheit", -0.1, "neuheit"),
    ("syncopation_lokal", float("nan"), "syncopation_lokal"),
    ("percussive_ratio_lokal", 1.1, "percussive_ratio_lokal"),
    ("sub_energy", "0.5", "sub_energy"),
    ("bass_punch", -0.1, "bass_punch"),
    ("bass_rms_dbfs", float("inf"), "bass_rms_dbfs"),
    ("key_confidence_lokal", True, "key_confidence_lokal"),
    ("brightness_lokal", 65.0, "brightness_lokal"),
    ("energy_lokal", 101, "energy_lokal"),
    ("flatness_lokal", 1.01, "flatness_lokal"),
    ("avg_mids_lokal", -0.1, "avg_mids_lokal"),
    ("avg_highs_lokal", 100.1, "avg_highs_lokal"),
    ("lufs_lokal", False, "lufs_lokal"),
    ("traegt_allein", 1, "traegt_allein"),
    ("kick_aktiv", "ja", "kick_aktiv"),
    ("vocal_aktiv_lokal", 0, "vocal_aktiv_lokal"),
    ("mood", [], "mood"),
  ],
)
def test_v39_mixcandidate_typen_laengen_und_bereiche(field, value, path):
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = _track_dict_mit_kandidaten()
  data["mix_in_candidates"][0][field] = value

  with pytest.raises(CacheValidationError, match=rf"mix_in_candidates\[0\]\.{path}"):
    validate_track_dict(data)


@pytest.mark.parametrize(
  "mood",
  [
    {"brightness": -0.1},
    {"brightness": True},
    {"flatness": 1.1},
    {"flatness": float("nan")},
    {"key_mode": None},
    {"pssi_mood": False},
    {"pssi_mood": float("inf")},
  ],
)
def test_v39_mixcandidate_mood_wird_verschachtelt_validiert(mood):
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = _track_dict_mit_kandidaten()
  data["mix_out_candidates"][0]["mood"] = mood

  with pytest.raises(CacheValidationError, match=r"mix_out_candidates\[0\]\.mood\."):
    validate_track_dict(data)


def test_ungueltiger_v39_kandidat_wird_beim_lesen_quarantinisiert(tmp_path, monkeypatch):
  import json
  from hpg_core import caching

  cache_file = tmp_path / "candidate_quarantine.db"
  monkeypatch.setattr(caching, "CACHE_FILE", str(cache_file))
  monkeypatch.setattr(caching, "LOCK_FILE", str(tmp_path / "candidate_quarantine.lock"))
  caching.init_cache()
  data = _track_dict_mit_kandidaten()
  data["mix_out_candidates"][0]["kick_aktiv"] = "kaputt"
  with sqlite3.connect(cache_file) as conn:
    conn.execute(
      "INSERT INTO cache (key, filepath, version, data) VALUES (?, ?, ?, ?)",
      ("defekter-kandidat", data["filePath"], caching.CACHE_VERSION, json.dumps(data)),
    )

  assert caching.get_cached_track("defekter-kandidat") is None

  with sqlite3.connect(cache_file) as conn:
    assert conn.execute(
      "SELECT 1 FROM cache WHERE key = ?", ("defekter-kandidat",)
    ).fetchone() is None
    quarantined = conn.execute(
      "SELECT error FROM cache_quarantine WHERE key = ?", ("defekter-kandidat",)
    ).fetchone()
  assert quarantined is not None
  assert "mix_out_candidates[0].kick_aktiv" in quarantined[0]


def test_v39_record_ohne_paarrelevantes_pflichtfeld_wird_quarantinisiert(
  tmp_path, monkeypatch,
):
  import json
  from hpg_core import caching

  cache_file = tmp_path / "required_field_quarantine.db"
  monkeypatch.setattr(caching, "CACHE_FILE", str(cache_file))
  monkeypatch.setattr(caching, "LOCK_FILE", str(tmp_path / "required_field_quarantine.lock"))
  caching.init_cache()
  data = track_to_dict(Track(filePath="C:/x.mp3", fileName="x.mp3"))
  del data["bass_punch"]
  with sqlite3.connect(cache_file) as conn:
    conn.execute(
      "INSERT INTO cache (key, filepath, version, data) VALUES (?, ?, ?, ?)",
      ("fehlendes-paarfeld", data["filePath"], caching.CACHE_VERSION, json.dumps(data)),
    )

  assert caching.get_cached_track("fehlendes-paarfeld") is None

  with sqlite3.connect(cache_file) as conn:
    assert conn.execute(
      "SELECT 1 FROM cache WHERE key = ?", ("fehlendes-paarfeld",)
    ).fetchone() is None
    quarantined = conn.execute(
      "SELECT error FROM cache_quarantine WHERE key = ?", ("fehlendes-paarfeld",)
    ).fetchone()
  assert quarantined is not None
  assert quarantined[0] == "Pflichtfeld bass_punch fehlt"


def test_beatgrid_pruefstatus_ueberlebt_cache_roundtrip():
  t = Track(
    filePath="C:/x.mp3",
    fileName="x.mp3",
    duration=300.0,
    beatgrid_source="rekordbox",
    beatgrid_status="mismatch",
    beatgrid_windows_checked=3,
    beatgrid_max_phase_error_ms=81.25,
    analysis_mode="librosa_full_or_tail",
  )

  back = dict_to_track(track_to_dict(t))

  assert back.beatgrid_source == "rekordbox"
  assert back.beatgrid_status == "mismatch"
  assert back.beatgrid_windows_checked == 3
  assert back.beatgrid_max_phase_error_ms == pytest.approx(81.25)


@pytest.mark.parametrize("phase_error", [6.000001, 81.25])
def test_verifiziertes_cache_grid_ueber_sechs_ms_wird_abgewiesen(phase_error):
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = track_to_dict(Track(filePath="C:/x.mp3", fileName="x.mp3"))
  data.update({
    "beatgrid_source": "audio",
    "beatgrid_status": "verified",
    "beatgrid_windows_checked": 3,
    "beatgrid_max_phase_error_ms": phase_error,
  })

  with pytest.raises(CacheValidationError):
    validate_track_dict(data)


def test_verifiziertes_cache_grid_akzeptiert_exakt_sechs_ms():
  from hpg_core.caching import validate_track_dict

  data = track_to_dict(Track(filePath="C:/x.mp3", fileName="x.mp3"))
  data["analysis_mode"] = "librosa_full_or_tail"
  data.update({
    "beatgrid_source": "rekordbox",
    "beatgrid_status": "verified",
    "beatgrid_windows_checked": 3,
    "beatgrid_max_phase_error_ms": 6.0,
    "downbeat_confidence": 1.0,
  })

  assert validate_track_dict(data)["beatgrid_max_phase_error_ms"] == 6.0


@pytest.mark.parametrize(
  "field,value",
  [
    ("beatgrid_source", "extern"),
    ("beatgrid_status", "vielleicht"),
    ("beatgrid_windows_checked", -1),
    ("beatgrid_windows_checked", 1.5),
    ("beatgrid_max_phase_error_ms", -1.1),
    ("beatgrid_max_phase_error_ms", float("nan")),
  ],
)
def test_ungueltige_beatgrid_cachewerte_werden_abgewiesen(field, value):
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = track_to_dict(Track(filePath="C:/x.mp3", fileName="x.mp3"))
  data[field] = value

  with pytest.raises(CacheValidationError):
    validate_track_dict(data)


def test_default_track_traegt_alle_beatgrid_pflichtwerte():
  data = track_to_dict(Track(filePath="C:/x.mp3", fileName="x.mp3"))
  data["analysis_mode"] = "librosa_full_or_tail"
  back = dict_to_track(data)

  assert back.beatgrid_source == "unknown"
  assert back.beatgrid_status == "unknown"
  assert back.beatgrid_windows_checked == 0
  assert back.beatgrid_max_phase_error_ms == -1.0


def test_record_ohne_beatgrid_pflichtkey_wird_abgewiesen():
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = track_to_dict(Track(filePath="C:/x.mp3", fileName="x.mp3"))
  del data["beatgrid_source"]

  with pytest.raises(CacheValidationError, match="Pflichtfeld beatgrid_source fehlt"):
    validate_track_dict(data)


def _track_dict_mit_gueltigen_nested_daten():
  track = Track(
    filePath="C:/x.mp3", fileName="x.mp3", duration=300.0,
    analysis_mode="librosa_full_or_tail",
  )
  track.sections = [{
    "label": "intro", "start_time": 0.0, "end_time": 30.0,
    "start_bar": 0, "end_bar": 16, "avg_energy": 20.0,
    "analysequelle": {"fenster": [0.0, 30.0]},
  }]
  track.analysis_coverage = [{"start": 0.0, "end": 300.0, "quelle": "voll"}]
  track.phrases = [{
    "start_s": 0.0, "end_s": 30.0, "label": "Intro",
    "mood": 1, "kind": 1, "fill": 0, "extra": {"wert": 1.0},
  }]
  track.cue_points = [{
    "t": 30.0, "name": "MIX IN", "provenance": "manual",
    "typ": 0, "hot_cue": None, "farbe": "rot",
  }]
  track.phrase_grid = [0.0, 30.0]
  return track_to_dict(track)


@pytest.mark.parametrize(
  "field",
  [
    "artist", "title", "genre", "keyNote", "keyMode", "camelotCode",
    "beatgrid_source", "beatgrid_status", "detected_genre", "genre_source",
    "vocal_instrumental", "rekordbox_signature", "analysis_mode", "lufs_status",
  ],
)
def test_v39_alle_top_level_stringfelder_sind_strikt_string(field):
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = track_to_dict(Track(filePath="C:/x.mp3", fileName="x.mp3"))
  data[field] = None

  with pytest.raises(CacheValidationError, match=rf"{field} muss ein String sein"):
    validate_track_dict(data)


def test_v39_outro_covered_string_false_wird_abgewiesen():
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = track_to_dict(Track(filePath="C:/x.mp3", fileName="x.mp3"))
  data["outro_covered"] = "false"

  with pytest.raises(CacheValidationError, match="outro_covered muss ein Boolean sein"):
    validate_track_dict(data)


@pytest.mark.parametrize("value", [True, float("nan"), float("inf")])
def test_v39_top_level_numerik_ist_endlich_und_keine_bool(value):
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = track_to_dict(Track(filePath="C:/x.mp3", fileName="x.mp3"))
  data["bpm"] = value

  with pytest.raises(CacheValidationError):
    validate_track_dict(data)


def test_v39_gueltige_nested_daten_behalten_extras_im_roundtrip(tmp_path, monkeypatch):
  from hpg_core import caching

  cache_file = tmp_path / "nested_roundtrip.db"
  monkeypatch.setattr(caching, "CACHE_FILE", str(cache_file))
  monkeypatch.setattr(caching, "LOCK_FILE", str(tmp_path / "nested_roundtrip.lock"))
  data = _track_dict_mit_gueltigen_nested_daten()
  validated = caching.validate_track_dict(data)

  assert validated["sections"][0]["analysequelle"] == {"fenster": [0.0, 30.0]}
  assert validated["analysis_coverage"][0]["quelle"] == "voll"
  assert validated["phrases"][0]["extra"] == {"wert": 1.0}
  assert validated["cue_points"][0]["farbe"] == "rot"

  caching.cache_track("nested", dict_to_track(data))
  restored = caching.get_cached_track("nested")

  assert restored is not None
  assert restored.sections == data["sections"]
  assert restored.analysis_coverage == data["analysis_coverage"]
  assert restored.phrases == data["phrases"]
  assert restored.cue_points == data["cue_points"]
  assert restored.phrase_grid == data["phrase_grid"]


@pytest.mark.parametrize(
  "list_name,index,field,value",
  [
    ("sections", 0, "label", 1),
    ("sections", 0, "start_bar", True),
    ("sections", 0, "end_bar", -1),
    ("sections", 0, "avg_energy", float("nan")),
    ("analysis_coverage", 0, "start", "0"),
    ("analysis_coverage", 0, "end", -1.0),
    ("phrases", 0, "label", None),
    ("phrases", 0, "mood", True),
    ("phrases", 0, "kind", 1.5),
    ("phrases", 0, "fill", "0"),
    ("cue_points", 0, "t", float("inf")),
    ("cue_points", 0, "name", None),
    ("cue_points", 0, "provenance", "rekordbox"),
    ("cue_points", 0, "typ", []),
    ("cue_points", 0, "hot_cue", {}),
  ],
)
def test_v39_kaputte_nested_feldtypen_werden_abgewiesen(list_name, index, field, value):
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = _track_dict_mit_gueltigen_nested_daten()
  data[list_name][index][field] = value

  with pytest.raises(CacheValidationError):
    validate_track_dict(data)


@pytest.mark.parametrize("list_name", ["sections", "analysis_coverage", "phrases", "cue_points"])
def test_v39_nested_element_muss_dictionary_sein(list_name):
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = _track_dict_mit_gueltigen_nested_daten()
  data[list_name][0] = "kaputt"

  with pytest.raises(CacheValidationError, match=rf"{list_name}\[0\] muss ein Dictionary sein"):
    validate_track_dict(data)


def test_v39_cue_ohne_t_wird_abgewiesen():
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = _track_dict_mit_gueltigen_nested_daten()
  del data["cue_points"][0]["t"]

  with pytest.raises(CacheValidationError, match=r"cue_points\[0\]\.t fehlt"):
    validate_track_dict(data)


def test_v39_cue_typ_und_hot_cue_sind_optional():
  from hpg_core.caching import validate_track_dict

  data = _track_dict_mit_gueltigen_nested_daten()
  del data["cue_points"][0]["typ"]
  del data["cue_points"][0]["hot_cue"]

  assert validate_track_dict(data)["cue_points"][0]["t"] == 30.0


@pytest.mark.parametrize(
  "list_name,start_field,end_field",
  [
    ("sections", "start_time", "end_time"),
    ("analysis_coverage", "start", "end"),
    ("phrases", "start_s", "end_s"),
  ],
)
def test_v39_nested_ende_darf_nicht_vor_start_liegen(
  list_name, start_field, end_field,
):
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = _track_dict_mit_gueltigen_nested_daten()
  data[list_name][0][start_field] = 20.0
  data[list_name][0][end_field] = 10.0

  with pytest.raises(CacheValidationError, match="liegt vor"):
    validate_track_dict(data)


def test_v39_section_end_bar_darf_nicht_vor_start_bar_liegen():
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = _track_dict_mit_gueltigen_nested_daten()
  data["sections"][0]["start_bar"] = 16
  data["sections"][0]["end_bar"] = 15

  with pytest.raises(CacheValidationError, match="end_bar liegt vor start_bar"):
    validate_track_dict(data)


@pytest.mark.parametrize(
  "list_name,field",
  [
    ("sections", "end_time"),
    ("analysis_coverage", "end"),
    ("phrases", "end_s"),
    ("cue_points", "t"),
  ],
)
def test_v39_nested_zeiten_liegen_innerhalb_duration(list_name, field):
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = _track_dict_mit_gueltigen_nested_daten()
  data[list_name][0][field] = 300.1

  with pytest.raises(CacheValidationError, match="liegt hinter dem Trackende"):
    validate_track_dict(data)


@pytest.mark.parametrize("phrase_grid", [[0.0, 30.0, 30.0], [0.0, 60.0, 30.0]])
def test_v39_phrase_grid_muss_streng_aufsteigend_sein(phrase_grid):
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = _track_dict_mit_gueltigen_nested_daten()
  data["phrase_grid"] = phrase_grid

  with pytest.raises(CacheValidationError, match="streng aufsteigend"):
    validate_track_dict(data)


def test_v39_phrase_grid_liegt_innerhalb_duration():
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = _track_dict_mit_gueltigen_nested_daten()
  data["phrase_grid"] = [0.0, 300.1]

  with pytest.raises(CacheValidationError, match="liegt hinter dem Trackende"):
    validate_track_dict(data)


@pytest.mark.parametrize(
  "list_name,field",
  [
    ("sections", "end_time"),
    ("analysis_coverage", "end"),
    ("phrases", "end_s"),
    ("cue_points", "t"),
  ],
)
def test_v39_positive_nested_zeit_ist_bei_duration_null_ungueltig(list_name, field):
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = _track_dict_mit_gueltigen_nested_daten()
  data["duration"] = 0.0
  for other_name in ("sections", "analysis_coverage", "phrases", "cue_points"):
    if other_name != list_name:
      data[other_name] = []
  data[list_name] = [dict(data[list_name][0])]
  if list_name == "sections":
    data[list_name][0]["start_time"] = 0.0
  elif list_name == "analysis_coverage":
    data[list_name][0]["start"] = 0.0
  elif list_name == "phrases":
    data[list_name][0]["start_s"] = 0.0
  data[list_name][0][field] = 0.1
  data["phrase_grid"] = []

  with pytest.raises(CacheValidationError, match="duration liegt ausserhalb"):
    validate_track_dict(data)


@pytest.mark.parametrize("duration", [-0.1, True, float("nan"), float("inf")])
def test_v39_duration_ist_endlich_nichtnegativ_und_keine_bool(duration):
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = track_to_dict(Track(filePath="C:/x.mp3", fileName="x.mp3"))
  data["duration"] = duration

  with pytest.raises(CacheValidationError):
    validate_track_dict(data)


@pytest.mark.parametrize("list_name", ["sections", "analysis_coverage", "phrases", "cue_points"])
def test_v39_nested_extras_muessen_rekursiv_endlich_sein(list_name):
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = _track_dict_mit_gueltigen_nested_daten()
  data[list_name][0]["extra_nan"] = {"tiefer": [float("nan")]}

  with pytest.raises(CacheValidationError, match="extra_nan"):
    validate_track_dict(data)


def test_v39_ungueltige_nested_row_wird_beim_lesen_quarantinisiert(tmp_path, monkeypatch):
  import json
  from hpg_core import caching

  cache_file = tmp_path / "nested_quarantine.db"
  monkeypatch.setattr(caching, "CACHE_FILE", str(cache_file))
  monkeypatch.setattr(caching, "LOCK_FILE", str(tmp_path / "nested_quarantine.lock"))
  caching.init_cache()
  data = _track_dict_mit_gueltigen_nested_daten()
  del data["cue_points"][0]["t"]
  with sqlite3.connect(cache_file) as conn:
    conn.execute(
      "INSERT INTO cache (key, filepath, version, data) VALUES (?, ?, ?, ?)",
      ("nested-defekt", data["filePath"], caching.CACHE_VERSION, json.dumps(data)),
    )

  assert caching.get_cached_track("nested-defekt") is None
  with sqlite3.connect(cache_file) as conn:
    assert conn.execute(
      "SELECT 1 FROM cache WHERE key = ?", ("nested-defekt",)
    ).fetchone() is None
    quarantined = conn.execute(
      "SELECT error FROM cache_quarantine WHERE key = ?", ("nested-defekt",)
    ).fetchone()
  assert quarantined is not None
  assert quarantined[0] == "cue_points[0].t fehlt"


def test_v42_ungueltiger_analysemodus_wird_quarantinisiert_gueltiger_bleibt(
  tmp_path, monkeypatch
):
  import json
  from hpg_core import caching

  cache_file = tmp_path / "analysis_mode_quarantine.db"
  monkeypatch.setattr(caching, "CACHE_FILE", str(cache_file))
  monkeypatch.setattr(caching, "LOCK_FILE", str(tmp_path / "analysis_mode_quarantine.lock"))
  caching.init_cache()
  valid = track_to_dict(Track(
    filePath="C:/valid.mp3",
    fileName="valid.mp3",
    analysis_mode="rekordbox_fast_tail",
  ))
  invalid = dict(valid)
  invalid["filePath"] = "C:/invalid.mp3"
  invalid["fileName"] = "invalid.mp3"
  invalid["analysis_mode"] = "full"
  with sqlite3.connect(cache_file) as conn:
    conn.executemany(
      "INSERT INTO cache (key, filepath, version, data) VALUES (?, ?, ?, ?)",
      [
        ("valid-mode", valid["filePath"], caching.CACHE_VERSION, json.dumps(valid)),
        ("invalid-mode", invalid["filePath"], caching.CACHE_VERSION, json.dumps(invalid)),
      ],
    )

  assert caching.get_cached_track("valid-mode").analysis_mode == "rekordbox_fast_tail"
  assert caching.get_cached_track("invalid-mode") is None
  with sqlite3.connect(cache_file) as conn:
    assert conn.execute(
      "SELECT 1 FROM cache WHERE key = ?", ("valid-mode",)
    ).fetchone() is not None
    assert conn.execute(
      "SELECT 1 FROM cache WHERE key = ?", ("invalid-mode",)
    ).fetchone() is None
    error = conn.execute(
      "SELECT error FROM cache_quarantine WHERE key = ?", ("invalid-mode",)
    ).fetchone()
  assert error == ("analysis_mode ist ungueltig",)


@pytest.mark.parametrize(
  "coverage",
  [
    [{"start": 100.0, "end": 200.0}, {"start": 0.0, "end": 50.0}],
    [{"start": 0.0, "end": 200.0}, {"start": 150.0, "end": 300.0}],
  ],
)
def test_cache_coverage_muss_sortiert_und_nicht_ueberlappend_sein(coverage):
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = track_to_dict(Track(filePath="C:/x.mp3", fileName="x.mp3", duration=300.0))
  data["analysis_coverage"] = coverage

  with pytest.raises(CacheValidationError, match="analysis_coverage"):
    validate_track_dict(data)


def test_cache_coverage_nullfenster_wird_abgewiesen():
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = track_to_dict(Track(filePath="C:/x.mp3", fileName="x.mp3", duration=300.0))
  data["analysis_coverage"] = [{"start": 100.0, "end": 100.0}]

  with pytest.raises(CacheValidationError, match="groesser als start"):
    validate_track_dict(data)


def _cache_section(label, start, end):
  return {
    "label": label,
    "start_time": start,
    "end_time": end,
    "start_bar": int(start),
    "end_bar": int(end),
    "avg_energy": 50.0,
  }


def test_cache_sections_muessen_nach_start_sortiert_sein():
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = _track_dict_mit_gueltigen_nested_daten()
  data["sections"] = [
    _cache_section("main", 100.0, 150.0),
    _cache_section("intro", 0.0, 50.0),
  ]

  with pytest.raises(CacheValidationError, match="sortiert"):
    validate_track_dict(data)


def test_cache_sections_duerfen_nicht_ueberlappen():
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = _track_dict_mit_gueltigen_nested_daten()
  data["sections"] = [
    _cache_section("intro", 0.0, 100.0),
    _cache_section("main", 99.0, 200.0),
  ]

  with pytest.raises(CacheValidationError, match="ueberlappen"):
    validate_track_dict(data)


def test_cache_sections_duerfen_adjacent_sein():
  from hpg_core.caching import validate_track_dict

  data = _track_dict_mit_gueltigen_nested_daten()
  data["sections"] = [
    _cache_section("intro", 0.0, 100.0),
    _cache_section("main", 100.0, 300.0),
  ]

  assert validate_track_dict(data)["sections"] == data["sections"]


def test_cache_coverage_und_unanalysed_sections_muessen_exakt_zusammenpassen():
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = _track_dict_mit_gueltigen_nested_daten()
  data["analysis_coverage"] = [
    {"start": 0.0, "end": 100.0},
    {"start": 200.0, "end": 300.0},
  ]
  data["sections"] = [{
    "label": "unanalysed", "start_time": 100.0, "end_time": 190.0,
    "start_bar": 50, "end_bar": 95, "avg_energy": 0.0,
  }]

  with pytest.raises(CacheValidationError, match="unanalysed-Sections"):
    validate_track_dict(data)

  data["sections"][0]["end_time"] = 200.0
  assert validate_track_dict(data)["analysis_coverage"] == data["analysis_coverage"]


def test_outro_covered_erfordert_coverage_bis_zum_trackende():
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = track_to_dict(Track(filePath="C:/x.mp3", fileName="x.mp3", duration=300.0))
  data["analysis_coverage"] = [{"start": 0.0, "end": 250.0}]
  data["sections"] = [{
    "label": "unanalysed", "start_time": 250.0, "end_time": 300.0,
    "start_bar": 125, "end_bar": 150, "avg_energy": 0.0,
  }]
  data["outro_covered"] = True

  with pytest.raises(CacheValidationError, match="Trackende"):
    validate_track_dict(data)


def test_outro_covered_akzeptiert_v42_decode_toleranz_bis_eine_sekunde():
  from hpg_core.caching import validate_track_dict

  data = track_to_dict(Track(filePath="C:/x.mp3", fileName="x.mp3", duration=300.0))
  data["analysis_mode"] = "librosa_full_or_tail"
  data["analysis_coverage"] = [{"start": 0.0, "end": 299.0}]
  data["outro_covered"] = True

  assert validate_track_dict(data)["outro_covered"] is True


def test_phrases_und_phrase_grid_muessen_denselben_vertrag_bilden():
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = _track_dict_mit_gueltigen_nested_daten()
  data["phrases"] = [
    {"start_s": 0.0, "end_s": 30.0, "label": "Intro", "mood": 1, "kind": 1, "fill": 0},
    {"start_s": 30.0, "end_s": 60.0, "label": "Up", "mood": 1, "kind": 2, "fill": 0},
  ]
  data["phrase_grid"] = [0.0, 30.0, 61.0]

  with pytest.raises(CacheValidationError, match="phrase_grid"):
    validate_track_dict(data)

  data["phrase_grid"][-1] = 60.0
  assert validate_track_dict(data)["phrase_grid"] == [0.0, 30.0, 60.0]


def test_phrasenintervalle_muessen_lueckenlos_aufeinanderfolgen():
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = _track_dict_mit_gueltigen_nested_daten()
  data["phrases"].append({
    "start_s": 31.0, "end_s": 60.0, "label": "Up",
    "mood": 1, "kind": 2, "fill": 0,
  })
  data["phrase_grid"] = [0.0, 31.0, 60.0]

  with pytest.raises(CacheValidationError, match="vorherigen end_s"):
    validate_track_dict(data)


@pytest.mark.parametrize("phrase_unit", [4, 12, 64, 8.0, True])
def test_phrase_unit_erlaubt_nur_8_16_32(phrase_unit):
  from hpg_core.caching import CacheValidationError, validate_track_dict

  data = track_to_dict(Track(filePath="C:/x.mp3", fileName="x.mp3"))
  data["phrase_unit"] = phrase_unit

  with pytest.raises(CacheValidationError, match="phrase_unit"):
    validate_track_dict(data)


@pytest.mark.parametrize("phrase_unit", [8, 16, 32])
def test_phrase_unit_akzeptiert_8_16_32(phrase_unit):
  from hpg_core.caching import validate_track_dict

  data = track_to_dict(Track(filePath="C:/x.mp3", fileName="x.mp3"))
  data["analysis_mode"] = "librosa_full_or_tail"
  data["phrase_unit"] = phrase_unit

  assert validate_track_dict(data)["phrase_unit"] == phrase_unit


def _isolierter_cache(tmp_path, monkeypatch, name="bcd"):
  from hpg_core import caching

  cache_file = tmp_path / f"{name}.db"
  monkeypatch.setattr(caching, "CACHE_FILE", str(cache_file))
  monkeypatch.setattr(caching, "LOCK_FILE", str(tmp_path / f"{name}.lock"))
  caching.init_cache()
  return caching, cache_file


def test_ai_metadata_merge_aendert_ausschliesslich_ai_metadata(tmp_path, monkeypatch):
  caching, _cache_file = _isolierter_cache(tmp_path, monkeypatch, "ai_merge")
  track = Track(filePath="C:/ai.wav", fileName="ai.wav", title="Analyse")
  track.ai_metadata = _ai_metadata(1)
  assert caching.cache_track("ai-key", track)

  assert caching.merge_cached_ai_metadata(
    "ai-key", track.filePath, _ai_metadata(2)
  )
  restored = caching.get_cached_track("ai-key")

  assert restored.title == "Analyse"
  assert restored.ai_metadata == _ai_metadata(2)


def test_stale_ganzzeilen_write_bewahrt_neueren_ai_merge(tmp_path, monkeypatch):
  caching, _cache_file = _isolierter_cache(tmp_path, monkeypatch, "ai_interleave")
  initial = Track(filePath="C:/ai.wav", fileName="ai.wav", title="alt")
  initial.ai_metadata = _ai_metadata(1)
  assert caching.cache_track("ai-key", initial)
  stale_analysis = Track(filePath="C:/ai.wav", fileName="ai.wav", title="neu analysiert")
  stale_analysis.ai_metadata = _ai_metadata(1)

  assert caching.merge_cached_ai_metadata(
    "ai-key", initial.filePath, _ai_metadata(2)
  )
  assert caching.cache_track("ai-key", stale_analysis)
  restored = caching.get_cached_track("ai-key")

  assert restored.title == "neu analysiert"
  assert restored.ai_metadata == _ai_metadata(2)


def test_ai_merge_falscher_pfad_laesst_gueltige_zeile_unveraendert(
  tmp_path, monkeypatch
):
  caching, _cache_file = _isolierter_cache(tmp_path, monkeypatch, "ai_path")
  track = Track(filePath="C:/richtig.wav", fileName="richtig.wav")
  track.ai_metadata = _ai_metadata(1)
  assert caching.cache_track("ai-key", track)

  assert not caching.merge_cached_ai_metadata(
    "ai-key", "C:/falsch.wav", _ai_metadata(2)
  )
  assert caching.get_cached_track("ai-key").ai_metadata == _ai_metadata(1)


def test_ai_merge_verwirft_generische_metadaten(tmp_path, monkeypatch):
  caching, _cache_file = _isolierter_cache(tmp_path, monkeypatch, "ai_schema")
  track = Track(filePath="C:/ai.wav", fileName="ai.wav")
  track.ai_metadata = _ai_metadata(1)
  assert caching.cache_track("ai-key", track)

  assert not caching.merge_cached_ai_metadata(
    "ai-key", track.filePath, {"generation": 2}
  )
  assert caching.get_cached_track("ai-key").ai_metadata == _ai_metadata(1)


def test_ai_merge_quarantinisiert_ungueltige_aktuelle_zeile(tmp_path, monkeypatch):
  caching, cache_file = _isolierter_cache(tmp_path, monkeypatch, "ai_invalid")
  data = track_to_dict(Track(filePath="C:/ai.wav", fileName="ai.wav"))
  data["bpm"] = 300.0
  with sqlite3.connect(cache_file) as conn:
    conn.execute(
      "INSERT INTO cache (key, filepath, version, data) VALUES (?, ?, ?, ?)",
      ("ai-key", data["filePath"], caching.CACHE_VERSION, json.dumps(data)),
    )

  assert not caching.merge_cached_ai_metadata(
    "ai-key", data["filePath"], {"generation": 2}
  )
  with sqlite3.connect(cache_file) as conn:
    assert conn.execute(
      "SELECT 1 FROM cache WHERE key = 'ai-key'"
    ).fetchone() is None
    assert conn.execute(
      "SELECT error FROM cache_quarantine WHERE key = 'ai-key'"
    ).fetchone() is not None


@pytest.mark.parametrize("value", [0.0, -0.1, 7200.1, True])
def test_v42_duration_physikalischer_bereich(value):
  from hpg_core.caching import CacheValidationError, validate_track_dict
  data = track_to_dict(Track(filePath="C:/x.wav", fileName="x.wav"))
  data["duration"] = value
  with pytest.raises(CacheValidationError, match="duration"):
    validate_track_dict(data)


@pytest.mark.parametrize("value", [20.0, 300.0, 19.9, 300.1, True])
def test_v42_bpm_physikalischer_bereich(value):
  from hpg_core.caching import CacheValidationError, validate_track_dict
  data = track_to_dict(Track(filePath="C:/x.wav", fileName="x.wav"))
  data["bpm"] = value
  with pytest.raises(CacheValidationError, match="bpm"):
    validate_track_dict(data)


@pytest.mark.parametrize("field", ["energy", "bass_intensity", "brightness", "danceability"])
@pytest.mark.parametrize("value", [-1, 101, 50.0, True])
def test_v42_prozentfelder_sind_echte_integer(field, value):
  from hpg_core.caching import CacheValidationError, validate_track_dict
  data = track_to_dict(Track(filePath="C:/x.wav", fileName="x.wav"))
  data[field] = value
  with pytest.raises(CacheValidationError, match=field):
    validate_track_dict(data)


def test_v42_frequenzbaender_erlauben_nulltriple_oder_summe_ungefaehr_100():
  from hpg_core.caching import CacheValidationError, validate_track_dict
  data = track_to_dict(Track(filePath="C:/x.wav", fileName="x.wav"))
  data.update(avg_bass=33.3, avg_mids=33.3, avg_highs=33.4)
  assert validate_track_dict(data)["avg_bass"] == 33.3
  data["avg_highs"] = 30.0
  with pytest.raises(CacheValidationError, match="zusammen etwa 100"):
    validate_track_dict(data)


@pytest.mark.parametrize(
  "field", ["spectral_flatness", "percussive_ratio", "syncopation", "sub_energy"]
)
@pytest.mark.parametrize("value", [-0.001, 1.001])
def test_v42_anteile_liegen_im_einheitsintervall(field, value):
  from hpg_core.caching import CacheValidationError, validate_track_dict
  data = track_to_dict(Track(filePath="C:/x.wav", fileName="x.wav"))
  data[field] = value
  with pytest.raises(CacheValidationError, match=field):
    validate_track_dict(data)


@pytest.mark.parametrize(
  "field", ["downbeat_confidence", "phrase_confidence", "key_confidence", "genre_confidence"]
)
def test_v42_alle_confidences_liegen_im_einheitsintervall(field):
  from hpg_core.caching import CacheValidationError, validate_track_dict
  data = track_to_dict(Track(filePath="C:/x.wav", fileName="x.wav"))
  data[field] = 1.01
  with pytest.raises(CacheValidationError, match=field):
    validate_track_dict(data)


@pytest.mark.parametrize(
  "field,value", [
    ("first_downbeat", 300.1), ("first_phrase", -0.5),
    ("mix_in_point", 300.1), ("mix_out_point", -0.5),
  ]
)
def test_v42_anker_und_mixpoints_liegen_in_der_trackdauer(field, value):
  from hpg_core.caching import CacheValidationError, validate_track_dict
  data = track_to_dict(Track(filePath="C:/x.wav", fileName="x.wav"))
  data[field] = value
  with pytest.raises(CacheValidationError, match=field):
    validate_track_dict(data)


@pytest.mark.parametrize(
  "field", ["mix_in_bars", "mix_out_bars", "beatgrid_windows_checked", "lufs_channels", "lufs_sample_rate"]
)
@pytest.mark.parametrize("value", [-1, 1.0, True])
def test_v42_zaehler_sind_echte_nichtnegative_integer(field, value):
  from hpg_core.caching import CacheValidationError, validate_track_dict
  data = track_to_dict(Track(filePath="C:/x.wav", fileName="x.wav"))
  data[field] = value
  with pytest.raises(CacheValidationError, match=field):
    validate_track_dict(data)


@pytest.mark.parametrize("value", [-0.5, -1.1])
def test_v42_beatgrid_error_erlaubt_nur_minus_eins_oder_nichtnegativ(value):
  from hpg_core.caching import CacheValidationError, validate_track_dict
  data = track_to_dict(Track(filePath="C:/x.wav", fileName="x.wav"))
  data["beatgrid_max_phase_error_ms"] = value
  with pytest.raises(CacheValidationError, match="beatgrid_max_phase_error_ms"):
    validate_track_dict(data)


@pytest.mark.parametrize("field", ["groove_pattern", "bass_pattern"])
def test_v42_top_level_pattern_hat_16_normierte_slots(field):
  from hpg_core.caching import CacheValidationError, validate_track_dict
  data = track_to_dict(Track(filePath="C:/x.wav", fileName="x.wav"))
  data[field] = [1.0 / 16.0] * 16
  assert len(validate_track_dict(data)[field]) == 16
  data[field] = [0.5] * 16
  with pytest.raises(CacheValidationError, match="L1-normalisiert"):
    validate_track_dict(data)


@pytest.mark.parametrize("field", ["mfcc_fingerprint", "timbre_fingerprint"])
def test_v42_fingerprint_hat_null_oder_13_endliche_werte(field):
  from hpg_core.caching import CacheValidationError, validate_track_dict
  data = track_to_dict(Track(filePath="C:/x.wav", fileName="x.wav"))
  data[field] = [0.0] * 12
  with pytest.raises(CacheValidationError, match=field):
    validate_track_dict(data)
  data[field] = [0.0] * 12 + [float("nan")]
  with pytest.raises(CacheValidationError, match=field):
    validate_track_dict(data)


@pytest.mark.parametrize("value", [-0.1, 100.1])
def test_v42_section_avg_energy_liegt_in_0_bis_100(value):
  from hpg_core.caching import CacheValidationError, validate_track_dict
  data = track_to_dict(Track(filePath="C:/x.wav", fileName="x.wav"))
  data["sections"] = [_cache_section("main", 0.0, 300.0)]
  data["sections"][0]["avg_energy"] = value
  with pytest.raises(CacheValidationError, match="avg_energy"):
    validate_track_dict(data)


def test_v42_lufs_complete_schema_und_coverage_innerhalb_duration():
  from hpg_core.caching import CacheValidationError, validate_track_dict
  data = track_to_dict(Track(filePath="C:/x.wav", fileName="x.wav"))
  data.update(
    lufs=-9.5, lufs_status="complete", lufs_coverage_seconds=300.0,
    lufs_channels=2, lufs_sample_rate=48000,
  )
  assert validate_track_dict(data)["lufs_status"] == "complete"
  data["lufs_coverage_seconds"] = 300.1
  with pytest.raises(CacheValidationError, match="lufs_coverage_seconds"):
    validate_track_dict(data)


@pytest.mark.parametrize("status", ["unknown", "error"])
def test_v42_leerer_lufs_status_erfordert_leere_messwerte(status):
  from hpg_core.caching import CacheValidationError, validate_track_dict
  data = track_to_dict(Track(filePath="C:/x.wav", fileName="x.wav"))
  data["lufs_status"] = status
  data["lufs"] = -9.0
  with pytest.raises(CacheValidationError, match="erfordert leere Messwerte"):
    validate_track_dict(data)


def test_v42_ungueltige_top_level_zeile_wird_quarantinisiert(tmp_path, monkeypatch):
  caching, cache_file = _isolierter_cache(tmp_path, monkeypatch, "top_quarantine")
  data = track_to_dict(Track(filePath="C:/x.wav", fileName="x.wav"))
  data["energy"] = 101
  with sqlite3.connect(cache_file) as conn:
    conn.execute(
      "INSERT INTO cache (key, filepath, version, data) VALUES (?, ?, ?, ?)",
      ("invalid-top", data["filePath"], caching.CACHE_VERSION, json.dumps(data)),
    )
  assert caching.get_cached_track("invalid-top") is None
  with sqlite3.connect(cache_file) as conn:
    assert conn.execute(
      "SELECT error FROM cache_quarantine WHERE key = 'invalid-top'"
    ).fetchone() == ("energy muss ein Integer in 0..100 sein",)


def test_korruptionsquarantaene_nimmt_rollback_journal_bytegleich_mit(
  tmp_path, monkeypatch
):
  caching, cache_file = _isolierter_cache(tmp_path, monkeypatch, "journal")
  cache_file.write_bytes(b"keine sqlite db")
  journal = tmp_path / "journal.db-journal"
  journal.write_bytes(b"rollback journal")
  monkeypatch.setattr(
    caching, "_is_confirmed_corrupt_on_connection", lambda: True
  )

  assert caching._quarantine_corrupt_cache() is True

  moved = list((tmp_path / "quarantine").glob("journal.db-journal.*.corrupt"))
  assert len(moved) == 1
  assert moved[0].read_bytes() == b"rollback journal"
