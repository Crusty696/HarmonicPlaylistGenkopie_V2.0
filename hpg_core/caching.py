"""
SQLite-based caching module for multi-process audio analysis

Provides cross-platform thread-safe and process-safe SQLite caching with WAL
(Write-Ahead Logging) mode enabled for optimal concurrent read/write operations.
"""

import sqlite3
import json
import os
import hashlib
import logging
from .models import Track

logger = logging.getLogger(__name__)

# v12: Mixpoint-Logik geaendert (sektionsbasierte Guards, Phrase-Alignment,
# Genre-Profile) -- gecachte Mixpoints aus v11 sind veraltet
CACHE_VERSION = 12
CACHE_FILE = f"hpg_cache_v{CACHE_VERSION}.db"
LOCK_FILE = f"hpg_cache_v{CACHE_VERSION}.lock"


def _ensure_cache_schema(conn: sqlite3.Connection) -> None:
    """Creates the cache schema on an open SQLite connection if missing."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cache ("
        "key TEXT PRIMARY KEY, "
        "filepath TEXT, "
        "version INTEGER, "
        "data TEXT"
        ")"
    )


def track_to_dict(track: Track) -> dict:
    """Converts a Track object to a serializable dictionary, handling NumPy types."""
    d = {}
    for k, v in track.__dict__.items():
        if isinstance(v, (list, tuple)):
            new_list = []
            for item in v:
                if hasattr(item, 'item'):  # numpy scalar
                    new_list.append(item.item())
                elif isinstance(item, dict):
                    new_list.append(item)
                elif hasattr(item, 'to_dict'):  # TrackSection object
                    new_list.append(item.to_dict())
                else:
                    new_list.append(item)
            d[k] = new_list
        elif hasattr(v, 'item'):  # numpy scalar
            d[k] = v.item()
        elif isinstance(v, dict):
            d[k] = v
        else:
            d[k] = v
    return d


def dict_to_track(d: dict) -> Track:
    """Creates a Track object from a dictionary, ensuring all keys are present."""
    filePath = d.get('filePath', '')
    fileName = d.get('fileName', '')
    track = Track(filePath=filePath, fileName=fileName)
    for k, v in d.items():
        if k in ('filePath', 'fileName'):
            continue
        setattr(track, k, v)
    return track


def init_cache() -> None:
    """Initializes the SQLite database and creates the cache table."""
    cache_dir = os.path.dirname(CACHE_FILE)
    if cache_dir and not os.path.exists(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)

    try:
        # Establish connection with a generous timeout for concurrent writes
        conn = sqlite3.connect(CACHE_FILE, timeout=15.0)
        # Enable WAL mode for high concurrency
        conn.execute("PRAGMA journal_mode=WAL;")
        _ensure_cache_schema(conn)
        conn.commit()

        # Check version and clear cache if it was created with an old version
        cursor = conn.cursor()
        cursor.execute("SELECT version FROM cache WHERE key = 'version' LIMIT 1")
        row = cursor.fetchone()
        if row is None:
            # Set initial version
            conn.execute(
                "INSERT INTO cache (key, filepath, version, data) VALUES ('version', 'system', ?, 'metadata')",
                (CACHE_VERSION,)
            )
            conn.commit()
            logger.info(f"Cache initialisiert (Version {CACHE_VERSION})")
        elif row[0] != CACHE_VERSION:
            logger.warning(f"Cache-Version veraltet (Erwartet: {CACHE_VERSION}, Gefunden: {row[0]}). Cache geleert.")
            cursor.execute("DELETE FROM cache")
            conn.execute(
                "INSERT INTO cache (key, filepath, version, data) VALUES ('version', 'system', ?, 'metadata')",
                (CACHE_VERSION,)
            )
            conn.commit()

        conn.close()
    except Exception as e:
        logger.error(f"Init-Fehler des SQLite-Caches: {e}")


def generate_cache_key(file_path: str) -> str | None:
    """Generates a cache key based on file path, size, and modification time."""
    if not file_path:
        return None
    identifier = str(file_path)
    try:
        stat = os.stat(identifier)
        return f"{identifier}-{stat.st_size}-{stat.st_mtime}"
    except:
        return hashlib.sha256(identifier.encode("utf-8", "ignore")).hexdigest()


def get_cached_track(cache_key: str, file_path: str = None) -> Track | None:
    """Retrieves a track from the SQLite cache."""
    if not cache_key:
        return None

    try:
        conn = sqlite3.connect(CACHE_FILE, timeout=15.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        _ensure_cache_schema(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT data FROM cache WHERE key = ?", (cache_key,))
        row = cursor.fetchone()
        conn.close()

        if row:
            data_dict = json.loads(row[0])
            track = dict_to_track(data_dict)

            # Validate cache key against physical file changes
            if file_path:
                try:
                    stat = os.stat(file_path)
                    expected_key = f"{file_path}-{stat.st_size}-{stat.st_mtime}"
                    if expected_key != cache_key:
                        return None
                except OSError:
                    pass
            return track
    except Exception as e:
        logger.debug(f"SQLite cache read error: {e}")
        return None
    return None


def cache_track(cache_key: str, track: Track) -> None:
    """Saves a track to the SQLite cache."""
    if not cache_key or not track:
        return

    try:
        data_dict = track_to_dict(track)
        data_json = json.dumps(data_dict)

        conn = sqlite3.connect(CACHE_FILE, timeout=15.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        _ensure_cache_schema(conn)
        conn.execute(
            "INSERT OR REPLACE INTO cache (key, filepath, version, data) VALUES (?, ?, ?, ?)",
            (cache_key, track.filePath, CACHE_VERSION, data_json)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"SQLite cache write failed: {e}")


import sys
import time
from contextlib import contextmanager

# Platform-specific locking imports for backward compatibility
if sys.platform == 'win32':
    import msvcrt

    def _lock_file(file_handle):
        """Lock file on Windows using msvcrt"""
        msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock_file(file_handle):
        """Unlock file on Windows using msvcrt"""
        try:
            msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
        except (IOError, OSError):
            pass
else:
    import fcntl

    def _lock_file(file_handle):
        """Lock file on Unix/Linux using fcntl"""
        fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock_file(file_handle):
        """Unlock file on Unix/Linux using fcntl"""
        try:
            fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)
        except (IOError, OSError):
            pass


@contextmanager
def file_lock(lock_path: str, timeout: float = 5.0):
    """
    Cross-platform file-based locking context manager for backward compatibility and testing.
    """
    lock_file_handle = None
    start_time = time.time()

    try:
        # Step 1: Open the lock file with retries
        while True:
            try:
                lock_file_handle = open(lock_path, 'w')
                break
            except (PermissionError, IOError) as e:
                if time.time() - start_time > timeout:
                    raise TimeoutError(f"Could not open lock file {lock_path} within {timeout}s: {e}")
                time.sleep(0.02)

        # Step 2: Acquire exclusive lock with timeout
        while True:
            try:
                _lock_file(lock_file_handle)
                break  # Lock acquired
            except (BlockingIOError, IOError):
                if time.time() - start_time > timeout:
                    raise TimeoutError(f"Could not acquire lock on {lock_path} within {timeout}s")
                time.sleep(0.01)

        yield lock_file_handle

    finally:
        if lock_file_handle:
            try:
                _unlock_file(lock_file_handle)
            except:
                pass
            try:
                lock_file_handle.close()
            except:
                pass

