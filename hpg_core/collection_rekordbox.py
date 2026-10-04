"""Unveraenderliche Inventarzuordnung aus vorhandenem Rekordbox-Importer.

Keine Audio-/Dateianalyse und keine eigene DB-Verbindung. Leere Legacy-Memos
sind ohne expliziten Lesestatus unbestaetigt: der Importer kann Lesefehler
intern in leere Listen umwandeln. DB und ANLZ bilden keinen globalen Snapshot.
"""
from dataclasses import dataclass, replace
import json
import math
import os
from pathlib import Path

from . import caching
from .rekordbox_readonly import (
    ReadOnlyRekordboxDatabase, ReadOnlyRekordboxError, RekordboxAnlzReadError,
)


@dataclass(frozen=True)
class CollectionRekordboxRow:
    path: str
    source_roots: tuple[str, ...]
    inventory_size: int
    inventory_mtime_ns: int
    match_status: str
    bpm_present: bool | None = None
    key_present: bool | None = None
    beatgrid_count: int | None = None
    phrases_count: int | None = None
    source_signature: str | None = None
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class CollectionRekordboxMap:
    roots: tuple[str, ...]
    rows: tuple[CollectionRekordboxRow, ...]
    cache_version: int
    source_db_path: str | None = None
    valid: bool = False
    cancelled: bool = False
    errors: tuple[str, ...] = ()


class _Cancelled(Exception):
    pass


def _checkpoint(cancel):
    if cancel is not None and bool(cancel() if callable(cancel) else cancel.is_set()):
        raise _Cancelled()


def _normalized(path):
    return os.path.normpath(path).lower()


def _contains(root, path):
    try:
        return (os.path.isabs(root) and os.path.isabs(path)
                and os.path.commonpath((_normalized(root), _normalized(path))) == _normalized(root))
    except (TypeError, ValueError):
        return False


def _duration(value):
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else 0.0
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _details(importer, path, record, cancel):
    """Signatur fuellt Memos; keine zweiten oeffentlichen Detailabrufe."""
    try:
        _checkpoint(cancel)
        signature = importer.get_track_signature(path)
        _checkpoint(cancel)
        content_id = getattr(record, "content_id", None)
        grid = getattr(importer, "_beatgrid_cache", {}).get(content_id)
        phrases = getattr(importer, "_phrases_cache", {}).get(
            (content_id, _duration(getattr(record, "duration", None))))
        # Optionaler schmaler Protokollvorschlag; Legacy-Importer hat ihn nicht.
        # Ohne Status keine bestaetigten Nullcounts aus verschluckten Fehlern.
        status_reader = getattr(importer, "get_track_read_status", None)
        statuses = status_reader(path) if callable(status_reader) else {}
        _checkpoint(cancel)
        errors = []

        def count(items, name):
            status = statuses.get(name) if isinstance(statuses, dict) else None
            if status in ("error", "unverified") or (status == "missing" and items):
                errors.append("detail_read_status_unverified")
                return None
            if isinstance(items, (list, tuple)) and (items or status in ("ok", "missing")):
                return len(items)
            errors.append("detail_read_status_unverified")
            return None

        grid_count = count(grid, "beatgrid")
        phrase_count = count(phrases, "phrases")
        if errors or not isinstance(signature, str) or not signature:
            signature = None
            if not errors:
                errors.append("source_signature_unavailable")
        return grid_count, phrase_count, signature, tuple(dict.fromkeys(errors))
    except (ReadOnlyRekordboxError, _Cancelled):
        raise
    except RekordboxAnlzReadError:
        return None, None, None, ("anlz_read_error",)
    except Exception:
        return None, None, None, ("detail_read_error",)


def map_collection_rekordbox(index, importer, cancel=None, progress=None) -> CollectionRekordboxMap:
    """Mappt einen Index ohne Quellzugriffe ausser denen des uebergebenen Importers.

Abbruch oder Sicherheitsfehler verwirft alle aktiven Resultate. Gewoehnliche
Detailfehler bleiben zeilenlokal und werden niemals als leere Erfolge gemeldet.
"""
    roots = tuple(index.roots)
    entries = tuple(index.entries)
    initial = tuple(CollectionRekordboxRow(
        path=entry.path,
        source_roots=tuple(root for root in roots if _contains(root, entry.path)),
        inventory_size=entry.size, inventory_mtime_ns=entry.mtime_ns,
        match_status="missing" if entry.status == "missing" else "unavailable",
    ) for entry in entries)
    result = CollectionRekordboxMap(roots, initial, caching.CACHE_VERSION)

    def invalid(code, cancelled=False):
        rows = tuple(replace(row, errors=(code,)) if row.match_status != "missing" else row
                     for row in initial)
        return replace(result, rows=rows, errors=(code,), cancelled=cancelled)

    try:
        _checkpoint(cancel)
        if index.cancelled:
            return invalid("index_cancelled", True)
        if index.errors:
            return invalid("index_invalid")
        if not roots or any(not os.path.isabs(root) for root in roots):
            return invalid("index_invalid")
        seen = set()
        for entry, row in zip(entries, initial):
            normalized = _normalized(entry.path)
            if (not row.source_roots or normalized in seen
                    or entry.status not in ("new", "changed", "unchanged", "missing")
                    or type(entry.size) is not int or entry.size < 0
                    or type(entry.mtime_ns) is not int or entry.mtime_ns < 0):
                return invalid("index_invalid")
            seen.add(normalized)
        if not importer.is_available():
            return invalid("importer_unavailable")
        db = getattr(importer, "db", None)
        if type(db) is ReadOnlyRekordboxDatabase and isinstance(db._path, Path):
            result = replace(result, source_db_path=str(db._path))
        memo = {}
        rows = []
        for position, (entry, row) in enumerate(zip(entries, initial), 1):
            _checkpoint(cancel)
            if entry.status != "missing":
                normalized = _normalized(entry.path)
                basename = os.path.basename(normalized)
                if normalized in importer._ambiguous_paths:
                    row = replace(row, match_status="ambiguous")
                elif normalized in importer.track_cache:
                    row = replace(row, match_status="exact")
                elif basename in importer.basename_cache:
                    row = replace(row, match_status=("ambiguous" if importer.basename_cache[basename] is None
                                                     else "basename"))
                else:
                    row = replace(row, match_status="missing")
                if row.match_status in ("exact", "basename"):
                    record = importer.get_track_data(entry.path)
                    _checkpoint(cancel)
                    if record is None:
                        row = replace(row, match_status="missing")
                    else:
                        # Gleicher Kontext wie Signatur: alle Metadaten inkl. Cues.
                        # Ohne Content-ID niemals verschiedene Pfade verschmelzen.
                        context = (getattr(record, "content_id", None) or normalized,
                                   json.dumps(vars(record), sort_keys=True, default=str))
                        if context not in memo:
                            memo[context] = _details(importer, entry.path, record, cancel)
                        grid, phrases, signature, errors = memo[context]
                        row = replace(row,
                            bpm_present=_duration(getattr(record, "bpm", None)) > 0,
                            key_present=any(isinstance(value, str) and bool(value.strip()) for value in (
                                getattr(record, "key", None), getattr(record, "camelot_code", None))),
                            beatgrid_count=grid, phrases_count=phrases,
                            source_signature=signature, errors=errors)
            rows.append(row)
            _checkpoint(cancel)
            if progress is not None:
                try:
                    progress(position, entry.path)
                except Exception:
                    return invalid("progress_callback_failed")
            _checkpoint(cancel)
        _checkpoint(cancel)
        return replace(result, rows=tuple(rows), valid=True)
    except _Cancelled:
        return invalid("mapping_cancelled", True)
    except ReadOnlyRekordboxError:
        return invalid("source_read_guard_failed")
    except Exception:
        return invalid("mapping_failed")
