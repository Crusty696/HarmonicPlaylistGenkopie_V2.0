import shelve
import os
import hashlib
from .models import Track

CACHE_FILE = "hpg_cache_v3.dbm" # Using .dbm for shelve
CACHE_VERSION = 3

def init_cache():
    """Initializes the cache, checking for version compatibility."""
    with shelve.open(CACHE_FILE) as db:
        current_version = db.get('cache_version')
        if current_version is None:
            db['cache_version'] = CACHE_VERSION
        elif current_version != CACHE_VERSION:
            print(f"Cache version mismatch. Clearing cache. Old: {current_version}, New: {CACHE_VERSION}")
            db.clear() # Clear all data if version mismatch
            db['cache_version'] = CACHE_VERSION

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
        with shelve.open(CACHE_FILE) as db:
            return db.get(cache_key)
    except Exception as e:
        print(f"Error retrieving from cache: {e}")
        return None

def cache_track(cache_key: str, track: Track):
    """Saves a track's analysis data to the cache."""
    if not cache_key:
        return
    with shelve.open(CACHE_FILE) as db:
        db[cache_key] = track
