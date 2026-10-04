"""Transaktionales Dateiinventar; Musikdateien werden nur per stat erfasst."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .config import SUPPORTED_AUDIO_EXTENSIONS


class CollectionIndexError(ValueError):
    """Inventar oder eigener Speicherort erfuellt den Vertrag nicht."""


@dataclass(frozen=True)
class CollectionEntry:
    path: str
    size: int
    mtime_ns: int
    status: str


@dataclass(frozen=True)
class CollectionIndex:
    roots: tuple[str, ...] = ()
    entries: tuple[CollectionEntry, ...] = ()
    errors: tuple[str, ...] = ()
    cancelled: bool = False


def _canonical(path):
    return os.path.abspath(os.path.normpath(os.fspath(path)))


def _key(path):
    return os.path.normcase(_canonical(path))


def _contains(root, path):
    try:
        return os.path.commonpath((_key(root), _key(path))) == _key(root)
    except ValueError:
        return False


def _unlinked(path):
    """Auch Junctions und verlinkte Vorfahren vor einem Zugriff ablehnen."""
    target = Path(_canonical(path))
    for component in (*reversed(target.parents), target):
        try:
            info = os.lstat(component)
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or (
            getattr(info, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        ):
            raise CollectionIndexError(f"Verlinkter Pfad abgelehnt: {component}")


def _cancel_requested(cancel):
    if cancel is None:
        return False
    return bool(cancel() if callable(cancel) else cancel.is_set())


def _rollback(previous, roots, errors=(), cancelled=False):
    return CollectionIndex(
        previous.roots if previous is not None else roots,
        previous.entries if previous is not None else (),
        tuple(errors), cancelled,
    )


def scan_collection(roots, previous=None, cancel=None, progress=None) -> CollectionIndex:
    """Alle unterstuetzten Dateien per lstat erfassen, ohne Audio zu oeffnen.

    Ein Fehler oder Abbruch verwirft den ganzen neuen Scan. Alte Eintraege
    bleiben unveraendert; damit bedeutet ein Zugriffsfehler nie 'missing'.
    """
    selected = ()
    errors = []
    try:
        if isinstance(roots, (str, bytes, os.PathLike)):
            raise CollectionIndexError("Roots muessen eine Pfadliste sein")
        unique = {}
        for root in roots:
            normalized = _canonical(root)
            unique.setdefault(_key(normalized), normalized)
        selected = tuple(unique[key] for key in sorted(unique))
        if not selected:
            raise CollectionIndexError("Keine Musikordner ausgewaehlt")
        for root in selected:
            _unlinked(root)
            if not stat.S_ISDIR(os.lstat(root).st_mode):
                raise CollectionIndexError(f"Kein Verzeichnis: {root}")
    except (OSError, TypeError, ValueError) as exc:
        return _rollback(previous, selected, (str(exc),))

    old = {_key(entry.path): entry for entry in previous.entries} if previous else {}
    found = {}
    visited = set()
    pending = list(reversed(selected))
    while pending:
        if _cancel_requested(cancel):
            return _rollback(previous, selected, errors, True)
        folder = pending.pop()
        folder_key = _key(folder)
        if folder_key in visited:
            continue
        visited.add(folder_key)
        try:
            _unlinked(folder)
            with os.scandir(folder) as children:
                for child in children:
                    if _cancel_requested(cancel):
                        return _rollback(previous, selected, errors, True)
                    path = _canonical(child.path)
                    if not _contains(folder, path):
                        raise CollectionIndexError(f"Pfad ausserhalb des Verzeichnisses: {path}")
                    _unlinked(path)
                    info = child.stat(follow_symlinks=False)
                    if stat.S_ISDIR(info.st_mode):
                        pending.append(path)
                    elif stat.S_ISREG(info.st_mode) and Path(path).suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS:
                        identity = _key(path)
                        if identity in found:
                            continue
                        prior = old.get(identity)
                        status = "new"
                        if prior is not None and prior.status != "missing":
                            status = "unchanged" if (prior.size, prior.mtime_ns) == (
                                info.st_size, info.st_mtime_ns
                            ) else "changed"
                        found[identity] = CollectionEntry(path, info.st_size, info.st_mtime_ns, status)
                        if progress is not None:
                            progress(len(found), path)
        except (OSError, TypeError, ValueError) as exc:
            errors.append(f"{folder}: {exc}")

    if errors:
        return _rollback(previous, selected, errors)
    for identity, entry in old.items():
        if identity not in found and any(_contains(root, entry.path) for root in selected):
            found[identity] = CollectionEntry(entry.path, entry.size, entry.mtime_ns, "missing")
    entries = tuple(found[key] for key in sorted(found))
    # Letzter Checkpoint: auch Cancel am letzten Fortschritt darf nichts publizieren.
    if _cancel_requested(cancel):
        return _rollback(previous, selected, (), True)
    return CollectionIndex(selected, entries)


def _state_path(path):
    if path is not None:
        return Path(_canonical(path))
    local = os.environ.get("LOCALAPPDATA")
    if not local or not os.path.isabs(local):
        raise CollectionIndexError("LOCALAPPDATA fehlt oder ist kein absoluter Pfad")
    return Path(local) / "HPG" / "collection_index.json"


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CollectionIndexError(f"Doppelter JSON-Schluessel: {key}")
        result[key] = value
    return result


def _validated(raw):
    if not isinstance(raw, dict) or set(raw) != {"kind", "version", "roots", "entries"}:
        raise CollectionIndexError("Unbekanntes Inventarformat")
    if raw["kind"] != "hpg_collection_index" or type(raw["version"]) is not int or raw["version"] != 1:
        raise CollectionIndexError("Unbekannte Inventarversion")
    if not isinstance(raw["roots"], list) or not raw["roots"] or not isinstance(raw["entries"], list):
        raise CollectionIndexError("Ungueltige Root-/Eintragsliste")
    roots, root_keys = [], set()
    for root in raw["roots"]:
        if not isinstance(root, str) or not os.path.isabs(root) or _canonical(root) != root:
            raise CollectionIndexError("Root ist nicht absolut und normalisiert")
        identity = _key(root)
        if identity in root_keys:
            raise CollectionIndexError("Doppelte Root")
        root_keys.add(identity)
        roots.append(root)
    entries, seen = [], set()
    for item in raw["entries"]:
        if not isinstance(item, dict) or set(item) != {"path", "size", "mtime_ns", "status"}:
            raise CollectionIndexError("Ungueltiger Inventareintrag")
        path = item["path"]
        if not isinstance(path, str) or not os.path.isabs(path) or _canonical(path) != path:
            raise CollectionIndexError("Eintragspfad ist nicht absolut und normalisiert")
        if not any(_contains(root, path) for root in roots) or Path(path).suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
            raise CollectionIndexError("Eintrag ausserhalb der Roots oder kein Audioformat")
        identity = _key(path)
        if identity in seen:
            raise CollectionIndexError("Doppelter Eintrag")
        if any(type(item[field]) is not int or item[field] < 0 for field in ("size", "mtime_ns")):
            raise CollectionIndexError("Groesse und mtime_ns muessen nichtnegative Ganzzahlen sein")
        if item["status"] not in ("new", "unchanged", "changed", "missing"):
            raise CollectionIndexError("Unbekannter Inventarstatus")
        seen.add(identity)
        entries.append(CollectionEntry(**item))
    return CollectionIndex(tuple(roots), tuple(entries))


def load_collection_index(path=None, roots=None):
    """Eigene JSON laden und lexikalisch validieren, ohne Musikpfade zu statten.

    Ein gespeicherter Pfad ist keine aktuelle Dateisystempruefung. Verlinkte
    Musikpfade werden erst beim ausdruecklichen Scan/Speichern geprueft.
    """
    destination = _state_path(path)
    try:
        _unlinked(destination)
        if not destination.exists():
            return None
        if not stat.S_ISREG(os.lstat(destination).st_mode):
            raise CollectionIndexError("Inventardatei ist keine regulaere Datei")
        with destination.open("r", encoding="utf-8") as handle:
            index = _validated(json.load(handle, object_pairs_hook=_unique_object))
        if roots is not None and {_key(root) for root in roots} != {_key(root) for root in index.roots}:
            raise CollectionIndexError("Inventar gehoert zu anderen Roots")
        return index
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        raise CollectionIndexError(f"Inventar konnte nicht geladen werden: {exc}") from exc


def save_collection_index(index, path=None, *, cancel=None):
    """Nur eigenes vollstaendiges Inventar atomar ersetzen, nie Benutzerformate."""
    destination = _state_path(path)
    temporary = None
    try:
        if index.cancelled or index.errors:
            raise CollectionIndexError("Abgebrochenes oder fehlerhaftes Inventar wird nicht gespeichert")
        raw = {"kind": "hpg_collection_index", "version": 1, "roots": list(index.roots),
               "entries": [{"path": entry.path, "size": entry.size,
                            "mtime_ns": entry.mtime_ns, "status": entry.status}
                           for entry in index.entries]}
        _validated(raw)
        for root in index.roots:
            _unlinked(root)
        for entry in index.entries:
            _unlinked(entry.path)
        if any(_contains(root, destination) for root in index.roots):
            raise CollectionIndexError("Inventarspeicher darf nicht im Musikordner liegen")
        _unlinked(destination)
        # Vorhandene Daten nur nach erfolgreicher Formatvalidierung ersetzen.
        load_collection_index(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        _unlinked(destination.parent)
        if _cancel_requested(cancel):
            raise InterruptedError("Inventarspeicherung abgebrochen")
        descriptor, name = tempfile.mkstemp(prefix=".collection-index-", suffix=".tmp", dir=destination.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(raw, handle, ensure_ascii=False, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        if _cancel_requested(cancel):
            raise InterruptedError("Inventarspeicherung abgebrochen")
        _unlinked(destination)
        load_collection_index(destination)
        if _cancel_requested(cancel):
            raise InterruptedError("Inventarspeicherung abgebrochen")
        os.replace(temporary, destination)
        temporary = None
    except InterruptedError:
        raise
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        raise CollectionIndexError(f"Inventar konnte nicht gespeichert werden: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
