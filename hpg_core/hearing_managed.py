"""Private Analyse-Snapshots fuer ordnergebundene Hoertests, ohne globalen Cache-Writer."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import quote

from .caching import CACHE_VERSION, track_to_dict, validate_track_dict
from .hearing_workflow import PrepareConfig


@dataclass(frozen=True)
class FileIdentity:
    device: int
    inode: int
    born_ns: int
    kind: int


@dataclass(frozen=True)
class SnapshotOwnership:
    root: Path
    directory: Path
    root_identity: FileIdentity
    directory_identity: FileIdentity
    file_identity: FileIdentity | None = None
    analysis_origin: str = "unknown"
    analysis_origins: tuple[tuple[str, str], ...] = ()


def _identity_from_stat(value, kind):
    born = getattr(value, "st_birthtime_ns", None)
    if (type(born) is not int or born <= 0 or value.st_ino <= 0
            or stat.S_IFMT(value.st_mode) != kind
            or getattr(value, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        raise ValueError("Objektidentitaet fehlt oder Objekttyp ist unsicher")
    return FileIdentity(value.st_dev, value.st_ino, born, kind)


def _identity(path, kind):
    return _identity_from_stat(path.lstat(), kind)


def _require_identity(path, expected):
    if not isinstance(expected, FileIdentity) or _identity(path, expected.kind) != expected:
        raise ValueError(f"Objektidentitaet geaendert: {path}")


def _require_owner(owner):
    if not isinstance(owner, SnapshotOwnership) or owner.directory.parent != owner.root:
        raise ValueError("Snapshot-Ownership fehlt")
    _require_identity(owner.root, owner.root_identity)
    _require_identity(owner.directory, owner.directory_identity)
    if owner.root.resolve() != owner.root or owner.directory.resolve() != owner.directory:
        raise ValueError("Snapshot-Pfad wurde umgeleitet")


def _present(path):
    try:
        path.lstat()
        return True
    except FileNotFoundError:
        return False


def managed_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base or not Path(base).is_absolute():
        raise ValueError("LOCALAPPDATA muss ein absoluter Pfad sein")
    return (Path(base) / "HPG" / "hearing_sets").resolve()


def freeze_tracks(tracks, folder, *, require_fresh=False) -> tuple[str, ...]:
    """Track-JSON plus Laufzeit-Herkunft separat und tief unveraenderlich einfrieren."""
    if type(require_fresh) is not bool:
        raise ValueError("require_fresh muss Boolean sein")
    root = Path(folder).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Musikordner fehlt")
    result, seen = [], set()
    for track in tracks:
        data = track_to_dict(track)
        path = Path(data["filePath"]).resolve()
        if not path.is_relative_to(root):
            continue
        key = str(path).casefold()
        if key in seen:
            raise ValueError("Doppelter Track im Analyse-Snapshot")
        seen.add(key)
        data = validate_track_dict(data)
        origin = getattr(track, "analysis_origin", "unknown")
        if origin not in {"fresh", "cache"}:
            origin = "unknown"
        if require_fresh and origin != "fresh":
            raise ValueError("Hoertest-Snapshot enthaelt keine nachweislich frische Trackanalyse")
        result.append(json.dumps({"track": data, "analysis_origin": origin},
                                 ensure_ascii=False, allow_nan=False, sort_keys=True))
    if not result:
        raise ValueError("Keine bestaetigten Analyse-Tracks im Musikordner")
    return tuple(result)


def managed_config(folder, **options) -> PrepareConfig:
    root = Path(folder).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Musikordner fehlt")
    private = managed_root() / str(uuid.uuid4())
    return PrepareConfig(cache=private / "analysis.sqlite", output_dir=private / "set",
                         source_roots=(root,), **options)


def managed_config_from_roots(roots, **options) -> PrepareConfig:
    """Mehrere Quellordner an einen neuen privaten Satz binden."""
    from .hearing_sources import normalize_source_roots

    source_roots = normalize_source_roots(tuple(roots))
    private = managed_root() / str(uuid.uuid4())
    return PrepareConfig(cache=private / "analysis.sqlite", output_dir=private / "set",
                         source_roots=source_roots, **options)


def _private_directory(config) -> Path:
    private = config.cache.parent
    root = managed_root()
    if (private.parent != root or str(uuid.UUID(private.name)) != private.name
            or private.resolve() != private or config.cache != private / "analysis.sqlite"
            or config.output_dir != private / "set"
            or config.cache.resolve() != config.cache or config.output_dir.resolve() != config.output_dir):
        raise ValueError("Snapshot-Ziel liegt nicht im privaten Hoertest-Ordner")
    return private


def write_snapshot(config, snapshots, *, cancel=None):
    """Neue DB exklusiv erstellen; Trackdaten unveraendert, Herkunft separat zurueckgeben."""
    private = _private_directory(config)
    roots = _validated_roots(config.source_roots)
    rows, seen, origins = [], set(), []
    for raw in snapshots:
        if cancel:
            cancel.checkpoint()
        snapshot = json.loads(raw)
        if type(snapshot) is dict and set(snapshot) == {"track", "analysis_origin"}:
            data = snapshot["track"]
            origin = snapshot["analysis_origin"]
            if type(origin) is not str or origin not in {"fresh", "cache", "unknown"}:
                raise ValueError("Analyseherkunft im Track-Snapshot ist ungueltig")
        else:
            data, origin = snapshot, "unknown"
        data = validate_track_dict(data)
        path = Path(data["filePath"]).resolve()
        key = str(path).casefold()
        if not any(path.is_relative_to(root) for root in roots) or key in seen:
            raise ValueError("Snapshot enthaelt fremde oder doppelte Tracks")
        seen.add(key)
        origins.append((data["filePath"], origin))
        rows.append((hashlib.sha256(key.encode()).hexdigest(), data["filePath"], CACHE_VERSION,
                     json.dumps(data, allow_nan=False, ensure_ascii=False)))
    if not rows:
        raise ValueError("Leerer Analyse-Snapshot")
    origin_values = {origin for _, origin in origins}
    analysis_origin = (
        next(iter(origin_values)) if len(origin_values) == 1
        else "mixed" if origin_values == {"fresh", "cache"}
        else "unknown"
    )
    if cancel:
        cancel.checkpoint()
    private.parent.mkdir(parents=True, exist_ok=True)
    root_identity = _identity(private.parent, stat.S_IFDIR)
    private.mkdir()  # Exklusiver Besitz; vorhandene Saetze bleiben unangetastet.
    owner = None
    try:
        owner = SnapshotOwnership(private.parent, private, root_identity,
                                  _identity(private, stat.S_IFDIR))
        _require_owner(owner)
        _private_directory(config)
        with config.cache.open("xb") as stream:
            owner = replace(owner, file_identity=_identity_from_stat(os.fstat(stream.fileno()), stat.S_IFREG))
            _require_identity(config.cache, owner.file_identity)
        _require_owner(owner)
        _require_identity(config.cache, owner.file_identity)
        connection = sqlite3.connect(str(config.cache))
        try:
            with connection:
                connection.execute("CREATE TABLE cache (key TEXT PRIMARY KEY, filepath TEXT, version INTEGER, data TEXT)")
                connection.execute("INSERT INTO cache VALUES (?, ?, ?, ?)", ("version", "system", CACHE_VERSION, "metadata"))
                connection.executemany("INSERT INTO cache VALUES (?, ?, ?, ?)", rows)
                connection.execute(
                    "CREATE TABLE hpg_analysis_origin (file_path TEXT PRIMARY KEY, origin TEXT NOT NULL)"
                )
                connection.executemany(
                    "INSERT INTO hpg_analysis_origin VALUES (?, ?)", origins
                )
        finally:
            connection.close()
        _require_owner(owner)
        _require_identity(config.cache, owner.file_identity)
        if cancel:
            cancel.checkpoint()
        return replace(owner, analysis_origin=analysis_origin,
                       analysis_origins=tuple(origins))
    except Exception as original:
        try:
            discard_unpublished_snapshot(owner)
        except Exception as cleanup:
            original.add_note(f"Eigener Snapshot blieb erhalten: {cleanup}")
        raise


def read_snapshot_origins(cache_path) -> tuple[tuple[str, str], ...]:
    """Liest optionale Herkunft aus privatem Hoertestcache; alte Caches bleiben unknown."""
    path = Path(cache_path).resolve(strict=True)
    uri = f"file:{quote(path.as_posix(), safe='/:')}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    try:
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "hpg_analysis_origin" not in tables:
            return ()
        columns = [row[1] for row in connection.execute(
            "PRAGMA table_info(hpg_analysis_origin)")]
        if columns != ["file_path", "origin"]:
            raise ValueError("Analyseherkunftstabelle hat ein unbekanntes Schema")
        rows = tuple(connection.execute(
            "SELECT file_path, origin FROM hpg_analysis_origin ORDER BY file_path"))
        cache_columns = [row[1] for row in connection.execute(
            "PRAGMA table_info(cache)")]
        if cache_columns != ["key", "filepath", "version", "data"]:
            raise ValueError("Track-Snapshot hat ein unbekanntes Schema")
        track_paths = tuple(row[0] for row in connection.execute(
            "SELECT filepath FROM cache WHERE key <> ? ORDER BY filepath", ("version",)))
    finally:
        connection.close()
    expected = {value.casefold() for value in track_paths if type(value) is str}
    actual = [value.casefold() for value, _ in rows if type(value) is str]
    if (len(expected) != len(track_paths) or len(actual) != len(rows)
            or len(set(actual)) != len(actual) or set(actual) != expected):
        raise ValueError("Analyseherkunft stimmt nicht mit dem Track-Snapshot ueberein")
    for path_value, origin in rows:
        if (type(path_value) is not str or not Path(path_value).is_absolute()
                or type(origin) is not str or origin not in {"fresh", "cache", "unknown"}):
            raise ValueError("Analyseherkunft im privaten Hoertestcache ist ungueltig")
    return rows


def discard_unpublished_snapshot(owner):
    """Nur nach exklusivem mkdir/erfolgreichem Schreiben durch diesen Aufrufer.

    Keine rekursive Bereinigung. Veroeffentlichte Saetze und unerwartete Inhalte
    bleiben unangetastet, auch nach einem fehlgeschlagenen Vorbereitungslauf.
    """
    # Identitaetschecks begrenzen Pfadersetzungen, sind aber kein atomarer
    # Schutz gegen Austausch zwischen letzter Pruefung und unlink/rmdir.
    _require_owner(owner)
    private = owner.directory
    if _present(private / "set"):
        return
    children = tuple(private.iterdir())
    cache = private / "analysis.sqlite"
    if any(p != cache for p in children):
        raise ValueError("Unbekannter Snapshot-Inhalt; auch Journal wird nicht geloescht")
    if children:
        _require_identity(cache, owner.file_identity)
        _require_owner(owner)
        if _present(private / "set") or tuple(private.iterdir()) != (cache,):
            raise ValueError("Snapshot-Inventar geaendert")
        _require_identity(cache, owner.file_identity)
        cache.unlink()
    _require_owner(owner)
    private.rmdir()


def _sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _validated_roots(roots):
    """Quellroots ausschliesslich per Verzeichnis-Metadaten pruefen."""
    from .hearing_sources import normalize_source_roots

    if type(roots) is not tuple or not roots or any(not isinstance(root, Path) for root in roots):
        raise ValueError("Ungueltige Quellordner")
    normalized = normalize_source_roots(roots)
    if normalized != roots:
        raise ValueError("Quellordner sind nicht kanonisch oder doppelt")
    return normalized


def _stored_roots(values):
    """Gespeicherte Wurzeln niemals still normalisieren oder neu ordnen."""
    if type(values) is not list or not values or any(type(value) is not str or not value
                                                  or "\0" in value for value in values):
        raise ValueError("Ungueltige Quellordner in der Zuordnung")
    roots = []
    for value in values:
        path = Path(value)
        if not path.is_absolute() or str(path) != value or path == Path(path.anchor):
            raise ValueError("Ungueltiger Quellordner in der Zuordnung")
        try:
            if path.resolve(strict=True) != path or not path.is_dir():
                raise ValueError("Quellordner nicht kanonisch")
        except (OSError, RuntimeError) as exc:
            raise ValueError("Quellordner nicht verfuegbar") from exc
        if path in roots:
            raise ValueError("Doppelter Quellordner")
        roots.append(path)
    return tuple(roots)


def _manifest_roots(path):
    from .hearing_sources import strict_json_bytes

    data = strict_json_bytes(path.read_bytes())
    if type(data) is not dict or "source_roots" not in data:
        raise ValueError("Quellordner fehlen im Hoertest-Manifest")
    return _stored_roots(data["source_roots"])


def bind_set(config, *, ownership=None):
    """Zuordnung ausserhalb des streng inventarisierten Satzes speichern."""
    private = _private_directory(config)
    # Ohne Schreibkontext nur die Tempdatei besitzen; keinen Snapshot loeschen.
    parent_owner = ownership or SnapshotOwnership(
        private.parent, private, _identity(private.parent, stat.S_IFDIR),
        _identity(private, stat.S_IFDIR))
    _require_owner(parent_owner)
    if parent_owner.directory != private:
        raise ValueError("Association gehoert nicht zum Snapshot")
    if ownership is not None:
        _require_identity(config.cache, ownership.file_identity)
    roots = _validated_roots(config.source_roots)
    if len(roots) > 1 and _manifest_roots(config.output_dir / "hearing_source_manifest.json") != roots:
        raise ValueError("Quellordner des Manifests stimmen nicht ueberein")
    association = {"format": "hpg-hearing-association-v2" if len(roots) > 1 else "hpg-hearing-association-v1",
                   "cache_version": CACHE_VERSION, "cache": "analysis.sqlite", "set": "set",
                   "cache_sha256": _sha(config.cache),
                   "manifest_sha256": _sha(config.output_dir / "hearing_source_manifest.json")}
    if len(roots) > 1:
        association["source_roots"] = [str(root) for root in roots]
    else:
        association["source_folder"] = str(roots[0])
    temporary = private / (".association-" + uuid.uuid4().hex + ".tmp")
    bound = False
    warning = ""
    temp_identity = None
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            temp_identity = _identity_from_stat(os.fstat(stream.fileno()), stat.S_IFREG)
            json.dump(association, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        # Hardlink publiziert atomar und exklusiv; keine existierende Zuordnung ersetzen.
        _require_owner(parent_owner)
        _require_identity(temporary, temp_identity)
        if ownership is not None:
            _require_identity(config.cache, ownership.file_identity)
        os.link(temporary, private / "association.json")
        _require_owner(parent_owner)
        _require_identity(private / "association.json", temp_identity)
        bound = True
    finally:
        try:
            if temp_identity is not None:
                _require_owner(parent_owner)
                _require_identity(temporary, temp_identity)
                temporary.unlink()
        except (OSError, ValueError) as exc:
            if bound:
                warning = f"Satz gebunden; temporäre Metadaten erhalten: {temporary}: {exc}"
            else:
                import logging
                logging.getLogger(__name__).warning("Temporäre Zuordnung erhalten: %s: %s", temporary, exc)
    return warning


def resolve_association(folder) -> Path | None:
    """Hashgebundene Zuordnung; alte Snapshot-Versionen bleiben bewertbar."""
    from .hearing_sources import strict_json_bytes
    directory = Path(folder).resolve(strict=True)
    association = directory.parent / "association.json"
    if not association.exists():
        # Ein verwalteter Satz ohne Zuordnung ist unvollstaendig.
        local = os.environ.get("LOCALAPPDATA")
        if (local and Path(local).is_absolute() and directory.name == "set"
                and directory.parent.parent == managed_root()):
            raise ValueError("Verwalteter Satz unvollstaendig: Zuordnung fehlt")
        return None
    if association.is_symlink() or association.resolve().parent != directory.parent:
        raise ValueError("Ungueltiger Zuordnungspfad")
    data = strict_json_bytes(association.read_bytes())
    common = {"format", "cache_version", "cache", "set", "cache_sha256", "manifest_sha256"}
    if (type(data) is not dict or data.get("format") not in
            ("hpg-hearing-association-v1", "hpg-hearing-association-v2")
            or set(data) != common | ({"source_folder"} if data["format"].endswith("v1")
                                     else {"source_roots"})
            or type(data["cache_version"]) is not int
            or not 0 < data["cache_version"] <= CACHE_VERSION
            or data["cache"] != "analysis.sqlite" or data["set"] != "set"
            or any(type(data[key]) is not str for key in ("cache_sha256", "manifest_sha256"))):
        raise ValueError("Ungueltige Hoertest-Zuordnung")
    if data["format"].endswith("v2"):
        roots = _stored_roots(data["source_roots"])
        if len(roots) < 2 or _manifest_roots(directory / "hearing_source_manifest.json") != roots:
            raise ValueError("Quellordner stimmen nicht mit dem Manifest ueberein")
    else:
        roots = _stored_roots([data["source_folder"]])
    config = PrepareConfig("einzel", directory, directory.parent / "analysis.sqlite",
                           source_roots=roots)
    _private_directory(config)
    if association.is_symlink() or association.resolve().parent != directory.parent:
        raise ValueError("Ungueltiger Zuordnungspfad")
    if (_sha(config.cache) != data["cache_sha256"]
            or _sha(directory / "hearing_source_manifest.json") != data["manifest_sha256"]):
        raise ValueError("Hash der Hoertest-Zuordnung stimmt nicht")
    return config.cache
