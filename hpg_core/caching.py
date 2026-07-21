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
import math
import shutil
import sys
import time
from contextlib import contextmanager
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path
from .models import Track

logger = logging.getLogger(__name__)

# v17: Key-Confidence (Essentia-Muster strength+margin) + LUFS-Loudness
# (EBU R128 via pyloudnorm/DeMan) 2026-07-17 — neue Track-Felder
# key_confidence und lufs werden bei der Analyse gefuellt
CACHE_VERSION = 18
_CACHE_FILE_OVERRIDE = os.environ.get("HPG_CACHE_FILE", "").strip()


def _default_cache_file() -> str:
    """Liefert einen CWD-unabhaengigen Cachepfad im Benutzerprofil."""
    configured_dir = os.environ.get("HPG_CACHE_DIR", "").strip()
    if configured_dir:
        base_dir = Path(configured_dir)
    else:
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        base_dir = Path(local_app_data) / "HPG" if local_app_data else Path.home() / ".hpg"
    return str(base_dir / f"hpg_cache_v{CACHE_VERSION}.db")


CACHE_FILE = _CACHE_FILE_OVERRIDE or _default_cache_file()
LOCK_FILE = os.path.splitext(CACHE_FILE)[0] + ".lock"

SQLITE_BUSY_CODES = {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
SQLITE_CORRUPTION_CODES = {sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB}
SQLITE_RETRY_DELAYS = (0.05, 0.1, 0.2, 0.4)


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
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cache_quarantine ("
        "key TEXT, data TEXT, error TEXT, quarantined_at TEXT"
        ")"
    )


TRACK_FIELD_NAMES = {field.name for field in fields(Track)}
TRACK_LIST_FIELDS = {"sections", "mfcc_fingerprint", "timbre_fingerprint", "analysis_coverage"}
TRACK_DICT_FIELDS = {"ai_metadata"}
TRACK_CONFIDENCE_FIELDS = {"downbeat_confidence", "key_confidence", "genre_confidence"}


class CacheValidationError(ValueError):
    """Ein einzelner Cache-Record verletzt den Track-Datenvertrag."""


def _validate_finite_values(value, path: str) -> None:
    """Verhindert nicht-endliche Zahlen auch in verschachtelten JSON-Feldern."""
    if isinstance(value, float) and not math.isfinite(value):
        raise CacheValidationError(f"{path} ist nicht endlich")
    if isinstance(value, dict):
        for key, nested in value.items():
            _validate_finite_values(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _validate_finite_values(nested, f"{path}[{index}]")


def validate_track_dict(data: dict) -> dict:
    """Validiert Typen und Kerninvarianten eines flachen Track-Records."""
    if not isinstance(data, dict):
        raise CacheValidationError("Track-Record ist kein Dictionary")

    filtered = {key: value for key, value in data.items() if key in TRACK_FIELD_NAMES}
    for required in ("filePath", "fileName"):
        if not isinstance(filtered.get(required), str) or not filtered[required]:
            raise CacheValidationError(f"Pflichtfeld {required} fehlt oder ist ungueltig")

    for name in TRACK_LIST_FIELDS:
        if name in filtered and not isinstance(filtered[name], list):
            raise CacheValidationError(f"{name} muss eine Liste sein")
    for name in TRACK_DICT_FIELDS:
        if name in filtered and not isinstance(filtered[name], dict):
            raise CacheValidationError(f"{name} muss ein Dictionary sein")

    for name, value in filtered.items():
        _validate_finite_values(value, name)
    for name in TRACK_CONFIDENCE_FIELDS:
        value = filtered.get(name)
        if value is not None and not 0.0 <= float(value) <= 1.0:
            raise CacheValidationError(f"{name} liegt ausserhalb 0..1")

    duration = float(filtered.get("duration") or 0.0)
    mix_in = float(filtered.get("mix_in_point") or 0.0)
    mix_out = float(filtered.get("mix_out_point") or 0.0)
    if duration < 0 or mix_in < 0 or mix_out < 0:
        raise CacheValidationError("Dauer oder Mixpoint ist negativ")
    if mix_out > 0 and not mix_in < mix_out:
        raise CacheValidationError("Mix-In muss vor Mix-Out liegen")
    if duration > 0 and mix_out > duration + 1e-6:
        raise CacheValidationError("Mix-Out liegt hinter dem Trackende")
    return filtered


def _quarantine_cache_row(cache_key: str, data: str, error: Exception) -> None:
    """Isoliert nur den ungueltigen Record; die restliche DB bleibt erhalten."""
    # Audit-Fix 2026-07-21: `with sqlite3.Connection` committet zwar, SCHLIESST
    # die Verbindung aber NICHT -> jeder quarantinisierte Record leakte ein
    # Datei-Handle (auf Windows blockiert das spaeter das Verschieben der DB).
    # Explizit schliessen wie alle anderen Cache-Zugriffe.
    conn = _connect_cache()
    try:
        _ensure_cache_schema(conn)
        conn.execute(
            "INSERT INTO cache_quarantine (key, data, error, quarantined_at) VALUES (?, ?, ?, ?)",
            (cache_key, data, str(error), datetime.now(timezone.utc).isoformat()),
        )
        conn.execute("DELETE FROM cache WHERE key = ?", (cache_key,))
        conn.commit()
    finally:
        conn.close()


def _sqlite_error_code(error: sqlite3.Error) -> int | None:
    """Extrahiert den primaeren SQLite-Code ohne Extended-Code-Bits."""
    code = getattr(error, "sqlite_errorcode", None)
    return code & 0xFF if isinstance(code, int) else None


def _connect_cache() -> sqlite3.Connection:
    """Oeffnet den Cache mit begrenztem Retry nur fuer BUSY/LOCKED."""
    last_error = None
    for delay in (*SQLITE_RETRY_DELAYS, None):
        try:
            conn = sqlite3.connect(CACHE_FILE, timeout=15.0)
            conn.execute("PRAGMA busy_timeout=15000;")
            return conn
        except sqlite3.OperationalError as error:
            last_error = error
            if _sqlite_error_code(error) not in SQLITE_BUSY_CODES or delay is None:
                raise
            time.sleep(delay)
    raise last_error


def _is_confirmed_corrupt() -> bool:
    """Bestaetigt Korruption per integrity_check oder eindeutigem Resultcode."""
    conn = None
    try:
        conn = sqlite3.connect(CACHE_FILE, timeout=2.0)
        row = conn.execute("PRAGMA integrity_check;").fetchone()
        return not row or str(row[0]).lower() != "ok"
    except sqlite3.DatabaseError as error:
        return _sqlite_error_code(error) in SQLITE_CORRUPTION_CODES
    finally:
        if conn is not None:
            conn.close()


def _quarantine_corrupt_cache() -> bool:
    """Verschiebt eine bestaetigt defekte DB reversibel statt sie zu loeschen."""
    if not os.path.exists(CACHE_FILE) or not _is_confirmed_corrupt():
        return False

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    quarantine_dir = Path(CACHE_FILE).parent / "quarantine"
    quarantine_dir.mkdir(parents=True, exist_ok=True)

    with file_lock(LOCK_FILE, timeout=15.0):
        for suffix in ("", "-wal", "-shm"):
            source = Path(CACHE_FILE + suffix)
            if source.exists():
                destination = quarantine_dir / f"{source.name}.{timestamp}.corrupt"
                shutil.move(str(source), str(destination))
    logger.error("Bestaetigt defekter Cache wurde nach %s verschoben", quarantine_dir)
    return True


def _handle_database_error(operation: str, error: sqlite3.DatabaseError) -> None:
    """Trennt Korruption von transienten oder programmatischen DB-Fehlern."""
    code = _sqlite_error_code(error)
    if code in SQLITE_CORRUPTION_CODES and _quarantine_corrupt_cache():
        logger.error("SQLite-%s scheiterte wegen bestaetigter Korruption: %s", operation, error)
        init_cache()
        return
    logger.warning(
        "SQLite-%s fehlgeschlagen ohne Korruptions-Recovery (Code=%s): %s",
        operation,
        code,
        error,
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
    d = validate_track_dict(d)
    filePath = d['filePath']
    fileName = d['fileName']
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

    conn = None
    try:
        # Establish connection with a generous timeout for concurrent writes
        conn = _connect_cache()
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
    except sqlite3.DatabaseError as e:
        if conn is not None:
            conn.close()
            conn = None
        # M14-Fix: korrupte DB ("database disk image is malformed") nicht nur
        # loggen, sondern loeschen und neu anlegen — sonst bleibt der Cache tot
        _handle_database_error("Init", e)
    except Exception as e:
        logger.error(f"Init-Fehler des SQLite-Caches: {e}")
    finally:
        if conn is not None:
            conn.close()


def generate_cache_key(file_path: str) -> str | None:
    """Generates a cache key based on file path, size, and modification time."""
    if not file_path:
        return None
    # normpath: QFileDialog liefert D:/pfad, os.walk D:\pfad -- ohne
    # Normalisierung entstehen doppelte Cache-Eintraege und die GUI
    # verfehlt vorhandene Analysen (Cache-Miss trotz identischer Datei)
    identifier = os.path.normcase(os.path.abspath(os.path.normpath(str(file_path))))
    try:
        stat = os.stat(identifier)
        return f"{identifier}-{stat.st_size}-{stat.st_mtime}"
    except OSError:
        return hashlib.sha256(identifier.encode("utf-8", "ignore")).hexdigest()


def get_cached_track(cache_key: str, file_path: str = None) -> Track | None:
    """Retrieves a track from the SQLite cache."""
    if not cache_key:
        return None

    conn = None
    try:
        conn = _connect_cache()
        _ensure_cache_schema(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT data FROM cache WHERE key = ?", (cache_key,))
        row = cursor.fetchone()
        conn.close()

        if row:
            try:
                data_dict = json.loads(row[0])
                track = dict_to_track(data_dict)
            except (json.JSONDecodeError, CacheValidationError) as error:
                _quarantine_cache_row(cache_key, row[0], error)
                logger.warning("Ungueltiger Cache-Record %s quarantinisiert: %s", cache_key, error)
                return None

            # Validate cache key against physical file changes
            if file_path:
                try:
                    # H8-Fix: gleiche Normalisierung wie generate_cache_key,
                    # sonst False-Cache-Miss bei Forward-Slash-Pfaden
                    identifier = os.path.normcase(
                        os.path.abspath(os.path.normpath(str(file_path)))
                    )
                    stat = os.stat(identifier)
                    expected_key = f"{identifier}-{stat.st_size}-{stat.st_mtime}"
                    if expected_key != cache_key:
                        return None
                except OSError:
                    pass
            return track
    except sqlite3.DatabaseError as e:
        if conn is not None:
            conn.close()
            conn = None
        _handle_database_error("Lesen", e)
        return None
    except Exception as e:
        logger.debug(f"SQLite cache read error: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()
    return None


def cache_track(cache_key: str, track: Track) -> None:
    """Saves a track to the SQLite cache."""
    if not cache_key or not track:
        return

    conn = None
    try:
        data_dict = track_to_dict(track)
        data_json = json.dumps(data_dict, allow_nan=False)

        conn = _connect_cache()
        conn.execute("PRAGMA journal_mode=WAL;")
        _ensure_cache_schema(conn)
        conn.execute(
            "INSERT OR REPLACE INTO cache (key, filepath, version, data) VALUES (?, ?, ?, ?)",
            (cache_key, track.filePath, CACHE_VERSION, data_json)
        )
        conn.commit()
        conn.close()
    except sqlite3.DatabaseError as e:
        if conn is not None:
            conn.close()
            conn = None
        _handle_database_error("Schreiben", e)
    except Exception as e:
        logger.warning(f"SQLite cache write failed: {e}")
    finally:
        if conn is not None:
            conn.close()


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
            except OSError:
                pass
            try:
                lock_file_handle.close()
            except OSError:
                pass

