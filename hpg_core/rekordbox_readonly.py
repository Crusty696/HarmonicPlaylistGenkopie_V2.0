"""Begrenzter Rekordbox-Leser mit abfrageweisen Windows-Dateisperren.

Nichtleere Journale werden abgelehnt: immutable darf kein Live-WAL verstecken.
DB-Abfragen und ANLZ-Lesevorgaenge bilden keinen gemeinsamen Snapshot.
"""
from contextlib import ExitStack, contextmanager
import ctypes
from ctypes import wintypes
import os
from pathlib import Path, PureWindowsPath
import threading


class ReadOnlyRekordboxError(RuntimeError):
    """Absichtlich ohne Pfade, SQL, Treiberfehler oder Schluessel."""


class RekordboxAnlzReadError(RuntimeError):
    """Optionaler Parserfehler, keine Verletzung des Dateischutzes."""


_ERROR = "Rekordbox read-only access unavailable"


def _fail():
    raise ReadOnlyRekordboxError(_ERROR) from None


@contextmanager
def _file_guard(path):
    if os.name != "nt":
        _fail()
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                       ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    final = kernel.GetFinalPathNameByHandleW
    final.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    final.restype = wintypes.DWORD
    handle = create(str(path), 0x80000000, 1, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise OSError(ctypes.get_last_error(), "Read-only handle unavailable")
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        length = final(handle, buffer, len(buffer), 0)
        if not length or length >= len(buffer):
            _fail()
        actual = buffer.value
        if actual.startswith("\\\\?\\UNC\\"):
            actual = "\\\\" + actual[8:]
        elif actual.startswith("\\\\?\\"):
            actual = actual[4:]
        if os.path.normcase(actual) != os.path.normcase(str(path)):
            _fail()
        yield handle
    finally:
        close(handle)


@contextmanager
def _guard(path):
    """Alle vorhandenen Dateien zuerst sperren, dann Journalgroessen pruefen."""
    path = Path(path).resolve(strict=True)
    family = [path, *(Path(str(path) + suffix) for suffix in ("-wal", "-journal", "-shm"))]

    def fingerprint():
        result = {}
        for member in family:
            try:
                stat = member.stat()
            except FileNotFoundError:
                result[member] = None
            else:
                result[member] = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
        return result

    with ExitStack() as stack:
        stack.enter_context(_file_guard(path))
        before = fingerprint()
        journals = []
        for suffix in ("-wal", "-journal", "-shm"):
            sidecar = Path(str(path) + suffix)
            try:
                stack.enter_context(_file_guard(sidecar))
            except OSError as exc:
                if exc.errno not in (2, 3):
                    raise
            else:
                if suffix != "-shm":
                    journals.append(sidecar)
        if any(item.stat().st_size for item in journals):
            _fail()
        if fingerprint() != before:
            _fail()
        try:
            yield
        finally:
            # Auch neue, zuvor fehlende Sidecars machen das Ergebnis ungueltig.
            # Keine Zusage ueber unbemerkte Erstellung plus Entfernung dazwischen.
            if fingerprint() != before:
                _fail()


def _authorizer(driver):
    # Nur explizite Leseaktionen; unbekannte Aktionen bleiben verboten.
    allowed = {driver.SQLITE_SELECT, driver.SQLITE_READ,
               driver.SQLITE_FUNCTION, driver.SQLITE_TRANSACTION}
    if hasattr(driver, "SQLITE_RECURSIVE"):
        allowed.add(driver.SQLITE_RECURSIVE)
    readable_pragmas = {"table_info", "table_xinfo", "index_list", "index_info",
                        "foreign_key_list", "database_list", "query_only", "read_uncommitted"}

    def authorize(action, first, second, database, trigger):
        if action == driver.SQLITE_FUNCTION:
            return (driver.SQLITE_DENY if (second or first or "").lower() == "load_extension"
                    else driver.SQLITE_OK)
        if action == driver.SQLITE_PRAGMA:
            name = (first or "").lower()
            # PRAGMA-Argumente koennen Tabellen-Namen oder Schreibwerte sein.
            if name in readable_pragmas and (second is None or name in {
                    "table_info", "table_xinfo", "index_list", "index_info", "foreign_key_list"}):
                return driver.SQLITE_OK
            return driver.SQLITE_DENY
        return driver.SQLITE_OK if action in allowed else driver.SQLITE_DENY

    return authorize


class _ReadQuery:
    def __init__(self, owner, model, options=(), filters=None):
        self._owner = owner
        self._model = model
        self._options = options
        self._filters = dict(filters or {})

    def options(self, *options):
        return _ReadQuery(self._owner, self._model, self._options + options, self._filters)

    def filter_by(self, **kwargs):
        return _ReadQuery(self._owner, self._model, self._options, {**self._filters, **kwargs})

    def all(self):
        from sqlalchemy import inspect
        from sqlalchemy.orm import selectinload

        def read(session):
            query = session.query(self._model)
            if self._options:
                query = query.options(*self._options)
            else:
                # Ohne Vorgaben direkte Beziehungen gebuendelt laden.
                defaults = [selectinload(getattr(self._model, rel.key))
                            for rel in inspect(self._model).relationships]
                query = query.options(*defaults)
            rows = query.filter_by(**self._filters).all()
            session.expunge_all()
            return rows

        return self._owner._run(read)

    def __iter__(self):
        return iter(self.all())

    def __getitem__(self, item):
        return self.all()[item]


class ReadOnlyRekordboxDatabase:
    """Keine langlebige Verbindung und keine oeffentlichen Schreibmethoden."""

    def __init__(self, path, *, key=None, unlock=True):
        self._path = Path(path).resolve(strict=True)
        self._key = key
        self._unlock = unlock
        self._closed = False
        self._lock = threading.RLock()

    def _check(self):
        if self._closed:
            _fail()

    def close(self):
        with self._lock:
            self._closed = True
            self._key = None

    def __enter__(self):
        self._check()
        return self

    def __exit__(self, *args):
        self.close()

    def query(self, model):
        self._check()
        return _ReadQuery(self, model)

    def _run(self, operation):
        try:
            with self._lock:
                self._check()
                with _guard(self._path):
                    from sqlalchemy import create_engine
                    from sqlalchemy.orm import Session
                    from sqlalchemy.pool import NullPool
                    if self._unlock:
                        from sqlcipher3 import dbapi2 as driver
                        flags = {"flags": driver.SQLITE_OPEN_READONLY | driver.SQLITE_OPEN_URI}
                    else:
                        import sqlite3 as driver
                        flags = {}
                    connection = driver.connect(
                        self._path.as_uri() + "?mode=ro&immutable=1", uri=True, **flags)
                    engine = None
                    try:
                        if self._unlock:
                            key = self._key
                            if key is None:
                                from pyrekordbox.db6.database import BLOB
                                from pyrekordbox.utils import deobfuscate
                                key = deobfuscate(BLOB)
                            if not isinstance(key, str) or not key or "\x00" in key:
                                _fail()
                            connection.execute("PRAGMA key='" + key.replace("'", "''") + "'")
                        connection.execute("PRAGMA query_only=ON")
                        connection.enable_load_extension(False)
                        connection.set_authorizer(_authorizer(driver))
                        engine = create_engine("sqlite://", module=driver,
                                               creator=lambda: connection, poolclass=NullPool,
                                               echo=False, hide_parameters=True,
                                               logging_name="hpg_readonly",
                                               pool_logging_name="hpg_readonly")
                        # Lokaler Engine-Logger: auch globale DEBUG-Konfiguration
                        # darf keine SQL-Literale oder entschluesselte Zeilen ausgeben.
                        engine.logger.disabled = True
                        engine.pool.logger.disabled = True
                        with Session(engine, autoflush=False, expire_on_commit=False) as session:
                            return operation(session)
                    finally:
                        try:
                            if engine is not None:
                                engine.dispose()
                        finally:
                            connection.close()
        except Exception:
            pass
        _fail()

    def get_content(self, **kwargs):
        try:
            from pyrekordbox.db6.tables import DjmdContent
            from sqlalchemy.orm import selectinload
            query = self.query(DjmdContent).options(*(
                selectinload(getattr(DjmdContent, name))
                for name in ("Cues", "Key", "Artist", "Genre", "Album", "Color")
            )).filter_by(**kwargs)
            if "ID" not in kwargs:
                return query
            rows = query.all()
            if len(rows) > 1:
                _fail()
            return rows[0] if rows else None
        except Exception:
            pass
        _fail()

    def _anlz_paths(self, content):
        """Sichere Abwesenheit ist normal; Traversal und Links bleiben gesperrt."""
        from pyrekordbox.anlz import get_anlz_paths

        row = self.get_content(ID=content)
        if row is None or not row.AnalysisDataPath:
            return {}
        relative = PureWindowsPath(row.AnalysisDataPath)
        if relative.drive or ".." in relative.parts:
            _fail()
        relative = Path(str(relative).lstrip("\\/").replace("\\", "/"))
        expected_root = self._path.parent / "share"
        root = expected_root.resolve(strict=False)
        if os.path.normcase(str(root)) != os.path.normcase(str(expected_root)):
            _fail()
        directory = (root / relative.parent).resolve(strict=False)
        if not directory.is_relative_to(root):
            _fail()
        # Nur wirklich fehlende optionale Verzeichnisse liefern einen Leerwert.
        # Zugriffssperren und falsche Dateitypen bleiben Sicherheitsfehler.
        try:
            if not root.stat() or not directory.stat():
                return {}
        except FileNotFoundError:
            return {}
        if not root.is_dir() or not directory.is_dir():
            _fail()
        paths = {}
        for kind, candidate in get_anlz_paths(directory).items():
            if candidate is not None:
                path = candidate.resolve(strict=True)
                if not path.is_relative_to(root):
                    _fail()
                paths[kind] = path
        return paths

    @staticmethod
    def _parse_anlz(path):
        from pyrekordbox.anlz import AnlzFile

        failed = False
        with _file_guard(path):
            raw = path.read_bytes()
            try:
                parsed = AnlzFile.parse(raw)
            except Exception:
                failed = True
        # Ausserhalb des except-Blocks: keine vertraulichen Fehlerkontexte.
        if failed:
            raise RekordboxAnlzReadError("Optional Rekordbox analysis data unreadable")
        return parsed

    def read_anlz_files(self, content):
        """Dateien einzeln gesichert lesen; kein globaler ANLZ-Snapshot."""
        try:
            with self._lock:
                self._check()
                result = {}
                for path in self._anlz_paths(content).values():
                    result[path] = self._parse_anlz(path)
                return result
        except (ReadOnlyRekordboxError, RekordboxAnlzReadError):
            raise
        except Exception:
            pass
        _fail()

    def read_anlz_file(self, content, type_="DAT"):
        try:
            with self._lock:
                self._check()
                requested = type_.upper()
                if requested not in ("DAT", "EXT", "2EX"):
                    _fail()
                path = self._anlz_paths(content).get(requested)
                return self._parse_anlz(path) if path is not None else None
        except (ReadOnlyRekordboxError, RekordboxAnlzReadError):
            raise
        except Exception:
            pass
        _fail()


def open_rekordbox_readonly(path=None, *, key=None, unlock=True) -> ReadOnlyRekordboxDatabase:
    """Nur Konfiguration; Dateisperren entstehen erst waehrend einer Abfrage."""
    try:
        if path is None:
            from pyrekordbox.config import get_config
            config = get_config("rekordbox7") or get_config("rekordbox6")
            path = config["db_path"]
        return ReadOnlyRekordboxDatabase(path, key=key, unlock=unlock)
    except Exception:
        pass
    _fail()
