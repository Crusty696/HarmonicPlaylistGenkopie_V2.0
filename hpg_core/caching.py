"""
Thread-safe caching module for multi-process audio analysis

Provides cross-platform file-based locking to prevent race conditions when
multiple worker processes access the cache simultaneously.

Works on both Windows (msvcrt) and Unix/Linux (fcntl).
"""

from __future__ import annotations  # Python 3.9 compatibility for | type hints

import sqlite3
import json
import os
import sys
import hashlib
import time
import logging
import errno
from contextlib import contextmanager
from dataclasses import asdict
from .models import Track, TrackSection
from .config import CACHE_LOCK_TIMEOUT

logger = logging.getLogger(__name__)

CACHE_FILE = "hpg_cache_v10.db"
CACHE_VERSION = 10
LOCK_FILE = "hpg_cache_v10.lock"


# Platform-specific locking imports
if sys.platform == 'win32':
    import msvcrt

    def _lock_file(file_handle):
        """Lock file on Windows using msvcrt"""
        # Lock first byte. LK_NBLCK = Non-blocking lock
        msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock_file(file_handle):
        """Unlock file on Windows using msvcrt"""
        try:
            msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
        except (IOError, OSError):
            pass  # Ignore unlock errors - file may already be unlocked
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
            pass  # Ignore unlock errors - file may already be unlocked


@contextmanager
def file_lock(lock_path: str, timeout: float = 5.0):
    """
    Cross-platform file-based locking context manager for multi-process synchronization.
    Includes robust retry logic for Windows PermissionErrors.
    """
    lock_file_handle = None
    start_time = time.time()

    try:
        # Step 1: Open the lock file with retries for PermissionError (Windows)
        while True:
            try:
                lock_file_handle = open(lock_path, 'w')
                break
            except (PermissionError, IOError) as e:
                # On Windows, open() can fail with Errno 13 if another process just closed it
                # but the OS hasn't released the handle yet.
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
                time.sleep(0.01)  # Wait 10ms before retry

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


def init_cache() -> None:
    """Initializes the cache with thread-safe version checking."""
    cache_dir = os.path.dirname(CACHE_FILE)
    if cache_dir and not os.path.exists(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)

    try:
        with file_lock(LOCK_FILE):
            with sqlite3.connect(CACHE_FILE) as conn:
                cur = conn.cursor()
                cur.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT)")

                cur.execute("SELECT value FROM cache WHERE key = ?", ("cache_version",))
                row = cur.fetchone()

                if row is None:
                    cur.execute("INSERT INTO cache (key, value) VALUES (?, ?)", ("cache_version", str(CACHE_VERSION)))
                    conn.commit()
                    logger.info(f"Cache initialisiert (Version {CACHE_VERSION})")
                else:
                    try:
                        current_version = int(row[0])
                    except ValueError:
                        current_version = -1

                    if current_version != CACHE_VERSION:
                        logger.warning(f"Cache-Version veraltet. Cache geleert.")
                        cur.execute("DELETE FROM cache")
                        cur.execute("INSERT INTO cache (key, value) VALUES (?, ?)", ("cache_version", str(CACHE_VERSION)))
                        conn.commit()
    except Exception as e:
        logger.error(f"Init-Fehler: {e}")


def generate_cache_key(file_path: str) -> str | None:
    """Generates a cache key based on file path, size, and modification time."""
    if not file_path:
        return None

    # If the file doesn't exist, return None
    if not os.path.exists(file_path):
        return None

    identifier = str(file_path)
    try:
        stat = os.stat(identifier)
        return f"{identifier}-{stat.st_size}-{stat.st_mtime}"
    except:
        return hashlib.sha256(identifier.encode("utf-8", "ignore")).hexdigest()


def get_cached_track(cache_key: str, file_path: str = None) -> Track | None:
    """Retrieves a track from the cache using thread-safe locking."""
    if not cache_key:
        return None

    try:
        # Increase timeout slightly for reading to reduce collision risk
        with file_lock(LOCK_FILE, timeout=CACHE_LOCK_TIMEOUT + 2.0):
            with sqlite3.connect(CACHE_FILE) as conn:
                cur = conn.cursor()
                cur.execute("SELECT value FROM cache WHERE key = ?", (cache_key,))
                row = cur.fetchone()

                track = None
                if row:
                    track_data = json.loads(row[0])
                    # Reconstruct nested objects (e.g. TrackSection)
                    sections_data = track_data.pop("sections", [])
                    track = Track(**track_data)
                    track.sections = [TrackSection(**sec) if isinstance(sec, dict) else sec for sec in sections_data]

                if track and file_path:
                    try:
                        stat = os.stat(file_path)
                        expected_key = f"{file_path}-{stat.st_size}-{stat.st_mtime}"
                        if expected_key != cache_key:
                            return None
                    except OSError:
                        pass
                return track
    except Exception as e:
        # Fail silently on cache miss due to lock
        logger.debug(f"Cache miss or error: {e}")
        return None


def cache_track(cache_key: str, track: Track) -> None:
    """Saves a track to the cache using thread-safe locking."""
    if not cache_key:
        return

    try:
        track_data = json.dumps(asdict(track))
        with file_lock(LOCK_FILE, timeout=CACHE_LOCK_TIMEOUT + 2.0):
            with sqlite3.connect(CACHE_FILE) as conn:
                cur = conn.cursor()
                cur.execute("INSERT OR REPLACE INTO cache (key, value) VALUES (?, ?)", (cache_key, track_data))
                conn.commit()
    except Exception as e:
        logger.debug(f"Caching skipped due to lock: {e}")
