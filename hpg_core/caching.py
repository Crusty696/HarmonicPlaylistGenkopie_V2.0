from __future__ import annotations  # Python 3.9 compatibility for | type hints

import shelve
import os
import hashlib
import time
from .models import Track

CACHE_FILE = "hpg_cache_v4.dbm" # Using .dbm for shelve
CACHE_VERSION = 4

def init_cache():
    """Initializes the cache, checking for version compatibility."""
    max_retries = 3
    retry_delay = 0.5  # seconds

    for attempt in range(max_retries):
        try:
            with shelve.open(CACHE_FILE, writeback=False) as db:
                current_version = db.get('cache_version')
                if current_version is None:
                    db['cache_version'] = CACHE_VERSION
                elif current_version != CACHE_VERSION:
                    print(f"Cache version mismatch. Clearing cache. Old: {current_version}, New: {CACHE_VERSION}")
                    db.clear() # Clear all data if version mismatch
                    db['cache_version'] = CACHE_VERSION
            return  # Success, exit function
        except PermissionError as e:
            if attempt < max_retries - 1:
                print(f"Cache locked (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay}s...")
                time.sleep(retry_delay)
            else:
                print(f"Warning: Could not initialize cache after {max_retries} attempts: {e}")
                print("The application will work without caching.")
        except Exception as e:
            print(f"Error initializing cache: {e}")
            print("The application will work without caching.")
            return

def generate_cache_key(file_path: str) -> str:
    """Generates a cache key based on file path, size, and modification time."""
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
    """Retrieves a track from the cache using the cache key."""
    if not cache_key:
        return None
    try:
        with shelve.open(CACHE_FILE, flag='r', writeback=False) as db:
            return db.get(cache_key)
    except (PermissionError, OSError) as e:
        # Cache is locked or not accessible, continue without cache
        return None
    except Exception as e:
        print(f"Error retrieving from cache: {e}")
        return None

def cache_track(cache_key: str, track: Track):
    """Saves a track's analysis data to the cache."""
    if not cache_key:
        return
    try:
        with shelve.open(CACHE_FILE, writeback=False) as db:
            db[cache_key] = track
    except (PermissionError, OSError) as e:
        # Cache is locked, skip caching
        pass
    except Exception as e:
        print(f"Error caching track: {e}")
