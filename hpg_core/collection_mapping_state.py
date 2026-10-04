"""Eigenes atomisches Mapping-JSON; gespeicherte Beobachtung ist nicht frisch."""
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import stat
import tempfile

from .collection_index import (
    CollectionEntry, CollectionIndex, _canonical, _contains, _key, _unlinked,
)
from .collection_rekordbox import CollectionRekordboxMap, CollectionRekordboxRow
from .config import SUPPORTED_AUDIO_EXTENSIONS


_ERRORS = frozenset({
    "unknown", "index_cancelled", "index_invalid", "importer_unavailable",
    "mapping_cancelled", "source_read_guard_failed", "mapping_failed",
    "progress_callback_failed", "detail_read_status_unverified",
    "source_signature_unavailable", "anlz_read_error", "detail_read_error",
    "mapping_operation_failed", "importer_close_failed",
})
_DETAILS = ("bpm_present", "key_present", "beatgrid_count", "phrases_count", "source_signature")
_ROW_FIELDS = frozenset({
    "path", "source_roots", "inventory_size", "inventory_mtime_ns", "match_status",
    *_DETAILS, "errors",
})


class CollectionMappingStateError(ValueError):
    """Eigene Persistenz oder Snapshotbindung verletzt den Vertrag."""


@dataclass(frozen=True)
class CollectionMappingState:
    map_version: int
    cache_version: int
    observed_at_ns: int
    index_snapshot: CollectionIndex
    mapping: CollectionRekordboxMap


@dataclass(frozen=True)
class SavedCollectionMapping:
    state: CollectionMappingState
    provenance: str = "saved_not_fresh"


def _fail(message="Ungültiger Mapping-State"):
    raise CollectionMappingStateError(message)


def _object(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        _fail("Unbekanntes oder unvollständiges Mapping-Schema")


def _integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        _fail("Ganzzahlfeld verletzt den Mapping-Vertrag")


def _boolean(value):
    if type(value) is not bool:
        _fail("Booleanfeld verletzt den Mapping-Vertrag")


def _path(value):
    if (type(value) is not str or not value or "\x00" in value
            or not os.path.isabs(value) or _canonical(value) != value):
        _fail("Pfad muss absolut, normalisiert und NUL-frei sein")
    return value


def _errors(value):
    if type(value) is not list or any(type(code) is not str or code not in _ERRORS for code in value):
        _fail("Unbekannter Mapping-Fehlercode")
    return tuple(value)


def _index_raw(index):
    if (type(index) is not CollectionIndex or type(index.cancelled) is not bool
            or index.cancelled or type(index.errors) not in (tuple, list) or index.errors):
        _fail("Abgebrochener oder fehlerhafter Index ist keine Snapshotbasis")
    if type(index.roots) not in (tuple, list) or type(index.entries) not in (tuple, list):
        _fail()
    if any(type(entry) is not CollectionEntry for entry in index.entries):
        _fail()
    return {"roots": list(index.roots), "entries": [asdict(entry) for entry in index.entries]}


def _decode_index(raw):
    _object(raw, {"roots", "entries"})
    if type(raw["roots"]) is not list or not raw["roots"] or type(raw["entries"]) is not list:
        _fail("Ungültige Root-/Eintragsliste")
    roots = tuple(_path(root) for root in raw["roots"])
    if len({_key(root) for root in roots}) != len(roots):
        _fail("Doppelte Root")
    entries, seen = [], set()
    for entry in raw["entries"]:
        _object(entry, {"path", "size", "mtime_ns", "status"})
        path = _path(entry["path"])
        if (not any(_contains(root, path) for root in roots)
                or Path(path).suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS):
            _fail("Inventarpfad liegt außerhalb der Roots oder ist kein Audioformat")
        if _key(path) in seen:
            _fail("Doppelter Inventarpfad")
        seen.add(_key(path))
        _integer(entry["size"])
        _integer(entry["mtime_ns"])
        if type(entry["status"]) is not str or entry["status"] not in ("new", "unchanged", "changed", "missing"):
            _fail("Unbekannter Inventarstatus")
        entries.append(CollectionEntry(**entry))
    return CollectionIndex(roots, tuple(entries))


def _raw(index, mapping, map_version, cache_version, observed_at_ns):
    if type(mapping) is not CollectionRekordboxMap:
        _fail()
    index_raw = _index_raw(index)
    if (type(mapping.roots) not in (tuple, list) or tuple(mapping.roots) != tuple(index.roots)
            or type(mapping.cache_version) is not int or mapping.cache_version != cache_version
            or type(mapping.rows) not in (tuple, list) or type(mapping.errors) not in (tuple, list)):
        _fail("Map und Index-/Cachebindung widersprechen sich")
    rows = []
    for row in mapping.rows:
        if (type(row) is not CollectionRekordboxRow or type(row.source_roots) not in (tuple, list)
                or type(row.errors) not in (tuple, list)):
            _fail()
        item = asdict(row)
        item["source_roots"] = list(row.source_roots)
        item["errors"] = list(row.errors)
        rows.append(item)
    return {"kind": "hpg_collection_mapping", "map_version": map_version,
            "cache_version": cache_version, "observed_at_ns": observed_at_ns,
            "index_snapshot": index_raw,
            "mapping": {"source_db_path": mapping.source_db_path,
                        "valid": mapping.valid, "cancelled": mapping.cancelled,
                        "errors": list(mapping.errors), "rows": rows}}


def _decode(raw):
    _object(raw, {"kind", "map_version", "cache_version", "observed_at_ns", "index_snapshot", "mapping"})
    if type(raw["kind"]) is not str or raw["kind"] != "hpg_collection_mapping":
        _fail("Unbekanntes Mapping-Format")
    _integer(raw["map_version"], 1)
    if raw["map_version"] != 1:
        _fail("Unbekannte Mapping-Version")
    _integer(raw["cache_version"], 1)
    _integer(raw["observed_at_ns"])
    index = _decode_index(raw["index_snapshot"])
    report = raw["mapping"]
    _object(report, {"source_db_path", "valid", "cancelled", "errors", "rows"})
    if report["source_db_path"] is not None:
        _path(report["source_db_path"])
    _boolean(report["valid"])
    _boolean(report["cancelled"])
    errors = _errors(report["errors"])
    if (report["valid"] and errors) or (report["cancelled"] and report["valid"]):
        _fail("Gültigkeitsstatus und Fehler widersprechen sich")
    if type(report["rows"]) is not list or len(report["rows"]) != len(index.entries):
        _fail("Mapping-Zeilenanzahl widerspricht dem Index")
    rows = []
    for entry, row in zip(index.entries, report["rows"]):
        _object(row, _ROW_FIELDS)
        _path(row["path"])
        _integer(row["inventory_size"])
        _integer(row["inventory_mtime_ns"])
        if (row["path"], row["inventory_size"], row["inventory_mtime_ns"]) != (entry.path, entry.size, entry.mtime_ns):
            _fail("Mapping-Zeilenreihenfolge oder Inventarbindung widerspricht dem Index")
        expected_roots = tuple(root for root in index.roots if _contains(root, entry.path))
        if (type(row["source_roots"]) is not list
                or any(type(root) is not str for root in row["source_roots"])
                or tuple(row["source_roots"]) != expected_roots):
            _fail("Mapping-Rootbindung widerspricht dem Index")
        status = row["match_status"]
        if type(status) is not str or status not in ("exact", "basename", "ambiguous", "missing", "unavailable"):
            _fail("Unbekannter Mapping-Status")
        if entry.status == "missing" and status != "missing":
            _fail("Fehlender Inventareintrag darf nur missing sein")
        if not report["valid"] and status in ("exact", "basename"):
            _fail("Ungültige Map darf keine bestätigten Zuordnungen enthalten")
        for name in ("bpm_present", "key_present"):
            if row[name] is not None:
                _boolean(row[name])
        for name in ("beatgrid_count", "phrases_count"):
            if row[name] is not None:
                _integer(row[name])
        signature = row["source_signature"]
        if signature is not None and (type(signature) is not str or not signature):
            _fail("Signatur muss nichtleerer String oder unbekannt sein")
        if status in ("unavailable", "ambiguous", "missing") and any(row[name] is not None for name in _DETAILS):
            _fail("Unbestätigte Zeile darf keine bestätigten Details enthalten")
        row_errors = _errors(row["errors"])
        rows.append(CollectionRekordboxRow(**dict(row, source_roots=expected_roots, errors=row_errors)))
    mapping = CollectionRekordboxMap(index.roots, tuple(rows), raw["cache_version"],
                                    report["source_db_path"], report["valid"], report["cancelled"], errors)
    return CollectionMappingState(raw["map_version"], raw["cache_version"], raw["observed_at_ns"], index, mapping)


def make_mapping_state(index, mapping, *, observed_at_ns):
    """Nur RAM validieren und entkoppeln; keine Zeit oder Signatur erraten."""
    if type(mapping) is not CollectionRekordboxMap:
        _fail()
    return _decode(_raw(index, mapping, 1, mapping.cache_version, observed_at_ns))


def _state_raw(state):
    if type(state) is not CollectionMappingState:
        _fail()
    raw = _raw(state.index_snapshot, state.mapping, state.map_version,
               state.cache_version, state.observed_at_ns)
    _decode(raw)
    return raw


def _destination():
    local = os.environ.get("LOCALAPPDATA")
    _path(local)
    return Path(local) / "HPG" / "collection_mapping.json"


def _outside(destination, roots):
    if any(_contains(root, str(destination)) for root in roots):
        _fail("Mapping-Speicher darf nicht im Musikordner liegen")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("Doppelter JSON-Schlüssel")
        result[key] = value
    return result


def _nonfinite(_):
    _fail("Nichtendliche JSON-Konstante")


def _load_own(destination):
    # Ausschließlich die eigene JSON und deren Vorfahren anfassen.
    _unlinked(destination)
    try:
        info = os.lstat(destination)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode):
        _fail("Mapping-State ist keine reguläre Datei")
    with destination.open("r", encoding="utf-8") as handle:
        state = _decode(json.load(handle, object_pairs_hook=_unique_object, parse_constant=_nonfinite))
    _outside(destination, state.index_snapshot.roots)
    return state


def load_collection_mapping_state(*, index=None, expected_cache_version=None):
    """Gespeichert, nicht frisch geprüft; kein Originalpfad wird statiert."""
    try:
        if expected_cache_version is not None:
            _integer(expected_cache_version, 1)
        expected_index = _decode_index(_index_raw(index)) if index is not None else None
        state = _load_own(_destination())
        if state is None:
            return None
        if expected_cache_version is not None and state.cache_version != expected_cache_version:
            _fail("Gespeicherte Cacheversion passt nicht zur erwarteten Version")
        if expected_index is not None and state.index_snapshot != expected_index:
            _fail("Gespeicherter Mapping-State gehört zu einem anderen Indexsnapshot")
        return SavedCollectionMapping(state)
    except CollectionMappingStateError:
        raise
    except (OSError, UnicodeError, TypeError, ValueError, OverflowError) as error:
        raise CollectionMappingStateError("Mapping-State konnte nicht geladen werden") from error


def _checkpoint(cancel):
    if cancel is not None and bool(cancel() if callable(cancel) else cancel.is_set()):
        raise InterruptedError("Mapping-Speicherung abgebrochen")


def save_collection_mapping_state(state, *, cancel=None):
    """Alte eigene Datei erst am Replace-Commitpunkt ersetzen, nie Fremdformate."""
    temporary = None
    descriptor = None
    try:
        raw = _state_raw(state)
        destination = _destination()
        _outside(destination, state.index_snapshot.roots)
        for root in state.index_snapshot.roots:
            _unlinked(root)
        _load_own(destination)
        _checkpoint(cancel)
        destination.parent.mkdir(parents=True, exist_ok=True)
        _unlinked(destination.parent)
        descriptor, name = tempfile.mkstemp(prefix=".collection-mapping-", suffix=".tmp", dir=destination.parent)
        temporary = Path(name)
        handle = os.fdopen(descriptor, "w", encoding="utf-8")
        descriptor = None
        with handle:
            json.dump(raw, handle, ensure_ascii=False, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        _checkpoint(cancel)
        _load_own(destination)
        _checkpoint(cancel)
        # Kein Cancel nach dem Commit: erfolgreiches Replace bleibt committed.
        os.replace(temporary, destination)
        temporary = None
    except (CollectionMappingStateError, InterruptedError):
        raise
    except (OSError, UnicodeError, TypeError, ValueError, OverflowError) as error:
        raise CollectionMappingStateError("Mapping-State konnte nicht gespeichert werden") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            temporary.unlink(missing_ok=True)
