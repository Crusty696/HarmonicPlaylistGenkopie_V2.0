"""Gebundene Kohorte durch vorhandenen Analyzer verarbeiten, ohne eigene Persistenz.

Die vorhandene Analyse nutzt ihren Cache unveraendert. Dieser Dienst schreibt
keine Datenbank und erzeugt keine Audiodateien. Stat-Pruefungen sind weder
Inhalts-SHA-Nachweis noch atomare Quellsperre, Cachehits werden nicht erfunden.
"""
from dataclasses import asdict, dataclass, replace
import json
import os
import stat

from .caching import VALID_ANALYSIS_MODES, track_to_dict, validate_track_dict
from .collection_index import _contains, _key, _unlinked
from .hearing_cohorts import CohortSelection, select_cohort
from .resource_limits import sanitize_playlist


@dataclass(frozen=True)
class CohortAnalysisIssue:
    path: str
    code: str


@dataclass(frozen=True)
class CohortAnalysisResult:
    version: int
    selection_binding: str
    requested_paths: tuple[str, ...]
    track_snapshots: tuple[str, ...]
    selected_roots: tuple[str, ...]
    issues: tuple[CohortAnalysisIssue, ...]
    complete: bool
    source_proof: str = "stat_checked_before_after"
    analysis_origin: str = "existing_analyzer_fresh_or_cache_unreported"


def _checkpoint(cancel):
    if cancel is None:
        return False
    try:
        value = cancel() if callable(cancel) else cancel.is_set()
    except Exception:
        raise InterruptedError("Kohorten-Abbruchpruefung fehlgeschlagen") from None
    if type(value) is not bool:
        raise InterruptedError("Kohorten-Abbruchpruefung verletzt den Vertrag")
    if value:
        raise InterruptedError("Kohortenanalyse abgebrochen")
    return False


def _encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _checked_source(entry):
    # Keine Audiodatei oeffnen; auch verlinkte Vorfahren ablehnen.
    _unlinked(entry.path)
    info = os.lstat(entry.path)
    if (not stat.S_ISREG(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            or (info.st_size, info.st_mtime_ns) != (entry.size, entry.mtime_ns)):
        raise ValueError("Kohortenquelle stimmt nicht mit dem Inventar ueberein")


def analyze_cohort(index, selection, *, context, features=(), analyzer=None, cancel=None, progress=None):
    """Keine Nachzieh-Tracks oder Positionsannahmen bei Analyseausfaellen."""
    if type(selection) is not CohortSelection or type(selection.selection_reused) is not bool:
        raise ValueError("Gebundene Kohortenauswahl erforderlich")
    expected = select_cohort(index, count=selection.count, seed=selection.seed,
                             context=context, features=features, previous=selection)
    if (_encoded(asdict(replace(selection, selection_reused=False)))
            != _encoded(asdict(replace(expected, selection_reused=False)))):
        raise ValueError("Kohortenbindung stimmt nicht mit Eingaben ueberein")
    if not selection.paths:
        raise ValueError("Keine analysierbaren Kohortenpfade")
    if progress is not None and not callable(progress):
        raise ValueError("Ungueltiger Fortschrittscallback")
    _checkpoint(cancel)
    entries = {_key(entry.path): entry for entry in index.entries}
    selected = tuple(entries[_key(path)] for path in selection.paths)
    for entry in selected:
        _checkpoint(cancel)
        _checked_source(entry)
    roots = tuple(root for root in index.roots if any(_contains(root, entry.path) for entry in selected))

    def report(current, total, message):
        _checkpoint(cancel)
        if progress is not None:
            try:
                progress(current, total, message)
            except Exception:
                # Analyzer behandelt InterruptedError ohne teuren Recovery-Lauf.
                raise InterruptedError("Kohorten-Fortschrittsmeldung fehlgeschlagen") from None

    _checkpoint(cancel)
    if analyzer is None:
        from .parallel_analyzer import ParallelAnalyzer
        analyzer = ParallelAnalyzer()
    returned = analyzer.analyze_files(list(selection.paths), progress_callback=report,
                                      cancel_callback=lambda: _checkpoint(cancel))
    _checkpoint(cancel)
    if type(returned) not in (tuple, list):
        raise ValueError("Analyzer-Ergebnis muss eine Trackliste sein")
    tracks_by_path = {}
    requested = {_key(path) for path in selection.paths}
    for track in returned:
        if track is None:
            continue
        path = getattr(track, "filePath", None)
        if type(path) is not str or not path or "\x00" in path:
            raise ValueError("Analyzer-Ergebnis ohne gueltigen Quellpfad")
        key = _key(path)
        if key not in requested or key in tracks_by_path or path != entries[key].path:
            raise ValueError("Fremdes, doppeltes oder nichtkanonisches Analyzer-Ergebnis")
        tracks_by_path[key] = track
    issues, snapshots = [], []
    for entry in selected:
        _checkpoint(cancel)
        track = tracks_by_path.get(_key(entry.path))
        if track is None:
            issues.append(CohortAnalysisIssue(entry.path, "analysis_result_missing"))
        elif getattr(track, "analysis_mode", None) not in VALID_ANALYSIS_MODES:
            issues.append(CohortAnalysisIssue(entry.path, "invalid_analysis_mode"))
        elif not sanitize_playlist([track]):
            issues.append(CohortAnalysisIssue(entry.path, "resource_limit_excluded"))
        else:
            try:
                snapshots.append(_encoded(validate_track_dict(track_to_dict(track))))
            except (TypeError, ValueError, OverflowError):
                issues.append(CohortAnalysisIssue(entry.path, "snapshot_invalid"))
    # Auch fehlgeschlagene Quellen nochmals pruefen: keine Teilfreigabe nach Aenderung.
    for entry in selected:
        _checkpoint(cancel)
        _checked_source(entry)
    _checkpoint(cancel)
    return CohortAnalysisResult(1, selection.binding_digest, selection.paths, tuple(snapshots),
                                roots, tuple(issues), not issues and len(snapshots) == len(selected))
