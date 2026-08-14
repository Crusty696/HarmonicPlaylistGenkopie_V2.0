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
from .config import MIX_POINT_UNSET

logger = logging.getLogger(__name__)

# v17: Key-Confidence (Essentia-Muster strength+margin) + LUFS-Loudness
# (EBU R128 via pyloudnorm/DeMan) 2026-07-17 — neue Track-Felder
# key_confidence und lufs werden bei der Analyse gefuellt
# AUDIT-FIX Welle 1 (2026-07-24): Version-Bump 18 -> 19 — die gecachten
# Mix-Punkte/Downbeats stammen aus der fehlerhaften Logik (N1/B7/B4/B5/B1/N10)
# und muessen neu berechnet werden.
# AUDIT-FEATURE A1 (2026-07-26): 19 -> 20 — neue Felder first_phrase/
# phrase_confidence; Mix-Punkte sind jetzt phrasen-verankert und muessen
# fuer alle Tracks neu berechnet werden.
# Analyse-/Quantisierungsvertrag geaendert: ungerundete Mixpunkte und
# gemessene Phrase-Units/erweiterte Novelty.
# AUDIT-FIX 2026-07-26: Mixpoints verwenden -1.0 als "nicht gesetzt";
# 0.0 bleibt ein gueltiger Zeitpunkt.
# AUDIT-FIX 2026-08-14: 24 -> 25. Drei Analysewerte aendern sich messbar und
# muessen neu berechnet werden:
#   - LUFS: die blockweise Messung lieferte fuer 24 von 52 Tracks NaN
#     ("lufs_status": "invalid", lufs 0.0), weil die Blockzahl aufgerundet
#     wurde und der letzte 400-ms-Block nicht mehr ins Signal passte.
#   - bass_intensity: die Skala endete bei einem Bass-Anteil von 0.5 und
#     klemmte real gemessene 0.78-0.89 auf konstant 100 (ein einziger
#     distinkter Wert ueber die ganze Bibliothek).
#   - bpm: ID3-Tags werden jetzt gegen das Audio auf Halftime/Doubletime und
#     2/3-Fehltagging geprueft; betroffene Tracks aendern BPM, Genre und
#     phrase_unit.
# AUDIT-FIX 2026-08-14 (Runde 2): 25 -> 26. Die Downbeat-Schaetzung wurde an
# zwei Stellen korrigiert: die Taktlaenge kam aus einem hop-gerasterten
# Median (-2,5 % Bias, der linear mit der Tracklaenge wuchs — bis 4,2 s
# Ankerfehler bei 330 s), und ein inkommensurables librosa-Beatraster
# (11 von 34 Tracks) lieferte Takte einer fremden Metrik. Folge:
# first_downbeat aendert sich auf 34/34 gemessenen Tracks,
# downbeat_confidence faellt bei 11/34 auf 0.0, phrase_anchor und die
# Sektions-Startzeiten verschieben sich — und damit die Mixpunkte.
# AUDIT-FIX 2026-08-14 (Runde 3): 26 -> 27. Die Downbeat-Feinausrichtung
# rastete auf den staerksten Bass-Onset-FRAME (46-ms-Hopraster) und lag
# dadurch ueber 35 Referenztracks konsistent +116 ms zu spaet (Gruppen-
# laufzeit des Onset-Detektors). Ersetzt durch nullphasigen Tiefpass +
# beat-synchrone Faltung: Sub-Beat-Fehler 117 ms -> 16 ms Median.
# Zusaetzlich ist die Konfidenz-Skala neu normiert (der alte 2/3-Deckel
# war ein Artefakt der Vote-Normierung, 1.0 bleibt Rekordbox vorbehalten).
# first_downbeat UND downbeat_confidence aendern sich auf jedem selbst
# geschaetzten Track; phrase_anchor, Sektionsgrenzen und Mixpunkte folgen.
# AUDIT-FIX 2026-08-14 (Runde 4): 27 -> 28. Das Phrasen-Voting faltet jetzt
# auf die GEMESSENE Periode, bevor es bewertet. Grund: Psytrance/Trance
# sind die einzigen Genres mit phrase_unit=16, viele Tracks haben real
# aber eine 8-Bar-Periode. Dann sammeln zwei Bins (p und p+8) dieselbe
# echte Phrasengrenze, die Margin bricht zusammen — und zwar umso mehr,
# je klarer die Struktur ist. Gefaltet wird nur bei zirkularer
# Selbstkorrelation >= 0.70 (kalibriert: echte 16-Bar-Tracks max 0.60,
# erkannte 8-Bar-Tracks min 0.78).
# Geaendert: first_phrase, phrase_confidence und darueber phrase_anchor,
# sections sowie alle Mixpunkte.
CACHE_VERSION = 28
_CACHE_FILE_OVERRIDE = os.environ.get("HPG_CACHE_FILE", "").strip()


def _default_cache_file() -> str:
    """Liefert einen CWD-unabhaengigen Cachepfad im Benutzerprofil."""
    configured_dir = os.environ.get("HPG_CACHE_DIR", "").strip()
    if configured_dir:
        base_dir = Path(configured_dir).expanduser().resolve()
    else:
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        base_dir = (
            Path(local_app_data).expanduser().resolve() / "HPG"
            if local_app_data
            else (Path.home() / ".hpg").resolve()
        )
    return str((base_dir / f"hpg_cache_v{CACHE_VERSION}.db").resolve())


CACHE_FILE = _CACHE_FILE_OVERRIDE or _default_cache_file()
LOCK_FILE = os.path.splitext(CACHE_FILE)[0] + ".lock"

SQLITE_BUSY_CODES = {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
SQLITE_CORRUPTION_CODES = {sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB}
SQLITE_RETRY_DELAYS = (0.05, 0.1, 0.2, 0.4)
CACHE_LOCK_TIMEOUT = 15.0


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
TRACK_NUMERIC_FIELDS = {
    field.name
    for field in fields(Track)
    if isinstance(field.default, (int, float))
    and not isinstance(field.default, bool)
}


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

    for name in TRACK_NUMERIC_FIELDS:
        if name in filtered and (
            isinstance(filtered[name], bool)
            or not isinstance(filtered[name], (int, float))
        ):
            raise CacheValidationError(f"{name} muss numerisch sein")

    for name, value in filtered.items():
        _validate_finite_values(value, name)
    for name in TRACK_CONFIDENCE_FIELDS:
        value = filtered.get(name)
        if value is not None and not 0.0 <= float(value) <= 1.0:
            raise CacheValidationError(f"{name} liegt ausserhalb 0..1")

    try:
        duration = float(filtered.get("duration") or 0.0)
        mix_in = float(filtered.get("mix_in_point", MIX_POINT_UNSET))
        mix_out = float(filtered.get("mix_out_point", MIX_POINT_UNSET))
    except (TypeError, ValueError, OverflowError) as error:
        raise CacheValidationError("Numerischer Track-Wert ist ungueltig") from error
    if duration < 0 or mix_in < MIX_POINT_UNSET or mix_out < MIX_POINT_UNSET:
        raise CacheValidationError("Dauer oder Mixpoint ist ungueltig negativ")
    if mix_in >= 0 and mix_out >= 0 and not mix_in < mix_out:
        raise CacheValidationError("Mix-In muss vor Mix-Out liegen")
    if duration > 0 and mix_out >= 0 and mix_out > duration + 1e-6:
        raise CacheValidationError("Mix-Out liegt hinter dem Trackende")
    return filtered


def _quarantine_cache_row_on_connection(
    conn: sqlite3.Connection,
    cache_key: str,
    data: str,
    error: Exception,
) -> None:
    """Isoliert einen ungueltigen Record auf einer bereits gesperrten Verbindung."""
    _ensure_cache_schema(conn)
    conn.execute(
        "INSERT INTO cache_quarantine (key, data, error, quarantined_at) VALUES (?, ?, ?, ?)",
        (cache_key, data, str(error), datetime.now(timezone.utc).isoformat()),
    )
    conn.execute("DELETE FROM cache WHERE key = ?", (cache_key,))
    conn.commit()


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
            conn.execute("PRAGMA foreign_keys=ON;")
            return conn
        except sqlite3.OperationalError as error:
            last_error = error
            if _sqlite_error_code(error) not in SQLITE_BUSY_CODES or delay is None:
                raise
            time.sleep(delay)
    raise last_error


def _is_confirmed_corrupt_on_connection() -> bool:
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
    with file_lock(LOCK_FILE, timeout=CACHE_LOCK_TIMEOUT):
        if not os.path.exists(CACHE_FILE) or not _is_confirmed_corrupt_on_connection():
            return False

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        quarantine_dir = Path(CACHE_FILE).parent / "quarantine"
        quarantine_dir.mkdir(parents=True, exist_ok=True)

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
        with file_lock(LOCK_FILE, timeout=CACHE_LOCK_TIMEOUT):
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
                # Ohne Marker sind vorhandene Records nicht vertrauenswuerdig.
                cursor.execute("DELETE FROM cache")
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
            else:
                cursor.execute(
                    "DELETE FROM cache WHERE key <> 'version' AND (version IS NULL OR version <> ?)",
                    (CACHE_VERSION,),
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


def generate_cache_key(file_path: str, source_signature: str = "") -> str | None:
    """Generiert einen stabilen Key aus Pfad und mehreren Dateizeitstempeln."""
    if not file_path:
        return None
    # normpath: QFileDialog liefert D:/pfad, os.walk D:\pfad -- ohne
    # Normalisierung entstehen doppelte Cache-Eintraege und die GUI
    # verfehlt vorhandene Analysen (Cache-Miss trotz identischer Datei)
    identifier = os.path.normcase(os.path.abspath(os.path.normpath(str(file_path))))
    try:
        stat = os.stat(identifier)
        key = (
            f"{identifier}-{stat.st_size}-{stat.st_mtime}-"
            f"{stat.st_mtime_ns}-{stat.st_ctime_ns}"
        )
        if source_signature:
            key = f"{key}-source-{source_signature}"
        return key
    except OSError:
        return hashlib.sha256(identifier.encode("utf-8", "ignore")).hexdigest()


def get_cached_track(cache_key: str, file_path: str = None) -> Track | None:
    """Retrieves a track from the SQLite cache."""
    if not cache_key:
        return None

    conn = None
    try:
        with file_lock(LOCK_FILE, timeout=CACHE_LOCK_TIMEOUT):
            conn = _connect_cache()
            _ensure_cache_schema(conn)
            conn.commit()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT data FROM cache WHERE key = ? AND version = ?",
                (cache_key, CACHE_VERSION),
            )
            row = cursor.fetchone()

            if row:
                try:
                    data_dict = json.loads(row[0])
                    track = dict_to_track(data_dict)
                except (
                    json.JSONDecodeError,
                    CacheValidationError,
                    TypeError,
                    ValueError,
                    OverflowError,
                ) as error:
                    _quarantine_cache_row_on_connection(conn, cache_key, row[0], error)
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
                        expected_key = (
                            f"{identifier}-{stat.st_size}-{stat.st_mtime}-"
                            f"{stat.st_mtime_ns}-{stat.st_ctime_ns}"
                        )
                        if "-source-" in cache_key:
                            expected_key = f"{expected_key}{cache_key[cache_key.index('-source-'):]}"
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
        # AUDIT-FIX C-02 (2026-07-24): auf WARNING statt DEBUG. Schema-Drift
        # nach einem Track-Feld-Rename (dict_to_track wirft) fuehrte sonst
        # dazu, dass JEDER Track bei jedem Start neu analysiert wurde — im Log
        # unsichtbar, User merkte nur "ploetzlich langsam".
        logger.warning(f"SQLite cache read error (Track wird neu analysiert): {e}")
        return None
    finally:
        if conn is not None:
            conn.close()
    return None


def _sanitize_nan(obj):
    """Ersetzt NaN/Inf rekursiv durch 0.0, damit json.dumps(allow_nan=False)
    nicht wirft (AUDIT-FIX C-02)."""
    import math
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, float) and not math.isfinite(v):
                obj[k] = 0.0
            elif isinstance(v, (dict, list)):
                _sanitize_nan(v)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, float) and not math.isfinite(v):
                obj[i] = 0.0
            elif isinstance(v, (dict, list)):
                _sanitize_nan(v)
    return obj


def cache_track(cache_key: str, track: Track) -> None:
    """Saves a track to the SQLite cache."""
    if not cache_key or not track:
        return

    conn = None
    try:
        data_dict = track_to_dict(track)
        # AUDIT-FIX C-02 (2026-07-24): NaN/Inf in Fingerprint-Listen wuerde
        # json.dumps(allow_nan=False) werfen -> Track waere NIE gecacht und bei
        # jedem Lauf neu analysiert worden. Vorab bereinigen.
        _sanitize_nan(data_dict)
        data_json = json.dumps(data_dict, allow_nan=False)

        with file_lock(LOCK_FILE, timeout=CACHE_LOCK_TIMEOUT):
            conn = _connect_cache()
            conn.execute("PRAGMA journal_mode=WAL;")
            _ensure_cache_schema(conn)
            marker = conn.execute(
                "SELECT version FROM cache WHERE key = 'version' LIMIT 1"
            ).fetchone()
            if marker is None or marker[0] != CACHE_VERSION:
                conn.execute("DELETE FROM cache")
                conn.execute(
                    "INSERT INTO cache (key, filepath, version, data) VALUES ('version', 'system', ?, 'metadata')",
                    (CACHE_VERSION,),
                )
            else:
                conn.execute(
                    "DELETE FROM cache WHERE key <> 'version' AND (version IS NULL OR version <> ?)",
                    (CACHE_VERSION,),
                )
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, filepath, version, data) VALUES (?, ?, ?, ?)",
                (cache_key, track.filePath, CACHE_VERSION, data_json)
            )
            conn.commit()
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
        lock_path_obj = Path(lock_path)
        lock_path_obj.parent.mkdir(parents=True, exist_ok=True)

        # Step 1: Open the lock file with retries
        while True:
            try:
                lock_file_handle = open(lock_path, 'a+b')
                if lock_file_handle.seek(0, os.SEEK_END) == 0:
                    lock_file_handle.write(b'\0')
                    lock_file_handle.flush()
                lock_file_handle.seek(0)
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
                lock_file_handle.close()
                lock_file_handle = None
                time.sleep(0.01)
                lock_file_handle = open(lock_path, 'a+b')
                lock_file_handle.seek(0)

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

