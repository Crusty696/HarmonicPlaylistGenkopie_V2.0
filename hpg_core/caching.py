"""
Thread-safe caching module for multi-process audio analysis

Provides cross-platform file-based locking to prevent race conditions when
multiple worker processes access the cache simultaneously.

Works on both Windows (msvcrt) and Unix/Linux (fcntl).
"""

from __future__ import annotations  # Python 3.9 compatibility for | type hints

import shelve
import os
import sys
import hashlib
import time
from contextlib import contextmanager
from .models import Track

CACHE_FILE = "hpg_cache_v4.dbm"
CACHE_VERSION = 4
LOCK_FILE = "hpg_cache_v4.lock"


# Platform-specific locking imports
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

    Args:
        lock_path: Path to lock file
        timeout: Maximum time to wait for lock (seconds)

    Yields:
        File handle (locked)

    Raises:
        TimeoutError: If lock cannot be acquired within timeout
    """
    lock_file_handle = None
    start_time = time.time()

    try:
        # Create lock file if it doesn't exist
        lock_file_handle = open(lock_path, 'w')

        # Try to acquire exclusive lock with timeout
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
            _unlock_file(lock_file_handle)
            lock_file_handle.close()


def init_cache():
    """Initializes the cache with thread-safe version checking."""
    # Ensure directory exists if path is provided
    cache_dir = os.path.dirname(CACHE_FILE)
    if cache_dir and not os.path.exists(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)

    with file_lock(LOCK_FILE):
        with shelve.open(CACHE_FILE) as db:
            current_version = db.get('cache_version')
            if current_version is None:
                db['cache_version'] = CACHE_VERSION
                print(f"[CACHE] Initialized new cache (version {CACHE_VERSION})")
            elif current_version != CACHE_VERSION:
                print(f"[CACHE] Version mismatch. Clearing cache. Old: {current_version}, New: {CACHE_VERSION}")
                db.clear()
                db['cache_version'] = CACHE_VERSION


def generate_cache_key(file_path: str) -> str:
    """
    Generates a cache key based on file path, size, and modification time.

    Args:
        file_path: Path to audio file

    Returns:
        Cache key string or None if file not found
    """
    if not file_path:
        return None

    identifier = str(file_path)

    try:
        stat = os.stat(identifier)
        return f"{identifier}-{stat.st_size}-{stat.st_mtime}"
    except (FileNotFoundError, TypeError, ValueError):
        return None
    except OSError:
        digest = hashlib.sha256(identifier.encode("utf-8", "ignore")).hexdigest()
        return f"{digest}"


def get_cached_track(cache_key: str) -> Track | None:
    """
    Retrieves a track from the cache using thread-safe locking.

    Args:
        cache_key: Cache key for the track

    Returns:
        Track object or None if not found
    """
    if not cache_key:
        return None

    try:
        with file_lock(LOCK_FILE, timeout=2.0):
            with shelve.open(CACHE_FILE) as db:
                return db.get(cache_key)
    except TimeoutError:
        print(f"[CACHE] Warning: Lock timeout for key {cache_key[:50]}...")
        return None
    except Exception as e:
        print(f"[CACHE] Error retrieving from cache: {e}")
        return None


def cache_track(cache_key: str, track: Track):
    """
    Saves a track to the cache using thread-safe locking.

    Args:
        cache_key: Cache key for the track
        track: Track object to cache
    """
    if not cache_key:
        return

    try:
        with file_lock(LOCK_FILE, timeout=2.0):
            with shelve.open(CACHE_FILE) as db:
                db[cache_key] = track
    except TimeoutError:
        print(f"[CACHE] Warning: Lock timeout when caching {track.fileName}")
    except Exception as e:
        print(f"[CACHE] Error saving to cache: {e}")
