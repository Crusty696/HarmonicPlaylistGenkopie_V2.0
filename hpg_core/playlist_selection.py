"""Auswahl und Exportrotation fuer begrenzte Playlists.

Die Auswahl laeuft vor der bestehenden Playlist-Strategie. Sie aendert weder
Scoring noch Paar-Gates und schreibt Exporthistorie erst nach Erfolg.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import random
import tempfile
import time

from .caching import file_lock

HISTORY_VERSION = 1
MAX_PLAYLIST_LENGTH = 1000
_LOCK_TIMEOUT = 15.0


@dataclass(frozen=True)
class SelectionReport:
    requested: int | None
    eligible: int
    selected: int
    avoided_previous_set: bool


def validate_playlist_length(value: object) -> int | None:
    """Liefert None fuer Alle oder eine gueltige ganzzahlige Trackzahl."""
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= MAX_PLAYLIST_LENGTH:
        raise ValueError("Playlist-Laenge muss Alle oder eine ganze Zahl von 1 bis 1000 sein")
    return None if value == 0 else value


def _track_id(track: object) -> str:
    value = getattr(track, "track_id", None)
    if not isinstance(value, str) or not value.strip():
        path = getattr(track, "filePath", None)
        if not isinstance(path, str) or not path.strip():
            raise ValueError("Track hat keine stabile Datei-Identitaet")
        value = os.path.normcase(os.path.abspath(os.path.normpath(path)))
    return value


def _eligible_unique(tracks: Sequence[object]) -> list[object]:
    result = []
    seen = set()
    for track in tracks:
        try:
            bpm = float(getattr(track, "bpm", None))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(bpm) or bpm <= 0:
            continue
        identity = _track_id(track)
        if identity in seen:
            continue
        seen.add(identity)
        result.append(track)
    return result


def retain_membership(source_tracks: Sequence[object], current_tracks: Sequence[object]) -> list[object]:
    """Nutzt aktualisierte Trackobjekte bei gleicher Playlist-Mitgliedschaft."""
    available: dict[str, list[object]] = {}
    for track in source_tracks:
        available.setdefault(_track_id(track), []).append(track)
    retained = []
    for current in current_tracks:
        identity = _track_id(current)
        matches = available.get(identity)
        if not matches:
            raise ValueError(f"Playlist-Track fehlt im aktuellen Analyselauf: {identity}")
        retained.append(matches.pop(0))
    return retained


def empty_history() -> dict:
    return {"version": HISTORY_VERSION, "last_exported": {}, "last_set": []}


def validate_history(value: object) -> dict:
    if not isinstance(value, Mapping) or set(value) != {"version", "last_exported", "last_set"}:
        raise ValueError("Playlist-Exporthistorie hat ein ungueltiges Schema")
    if type(value["version"]) is not int or value["version"] != HISTORY_VERSION:
        raise ValueError("Playlist-Exporthistorie hat eine unbekannte Version")
    exported = value["last_exported"]
    last_set = value["last_set"]
    if not isinstance(exported, Mapping) or not isinstance(last_set, list):
        raise ValueError("Playlist-Exporthistorie hat ungueltige Werte")
    for identity, timestamp in exported.items():
        if (not isinstance(identity, str) or not identity.strip()
                or type(timestamp) is not int or timestamp < 0):
            raise ValueError("Playlist-Exporthistorie enthaelt einen ungueltigen Trackeintrag")
    if (any(not isinstance(identity, str) or not identity.strip() for identity in last_set)
            or len(last_set) != len(set(last_set))):
        raise ValueError("Playlist-Exporthistorie enthaelt eine ungueltige letzte Playlist")
    return {
        "version": HISTORY_VERSION,
        "last_exported": dict(exported),
        "last_set": list(last_set),
    }


def load_history(path: str | os.PathLike[str]) -> dict:
    target = Path(path)
    try:
        raw = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return empty_history()
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Playlist-Exporthistorie ist nicht lesbares JSON") from exc
    return validate_history(value)


def _atomic_write(path: Path, history: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(history, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def record_successful_export(
    path: str | os.PathLike[str], tracks: Sequence[object], *, timestamp: int | None = None,
) -> dict:
    """Speichert Trackzeiten atomar; ungueltige Historie bleibt unangetastet."""
    target = Path(path)
    identities = list(dict.fromkeys(_track_id(track) for track in tracks))
    if not identities:
        raise ValueError("Leere Playlist kann nicht in die Exporthistorie aufgenommen werden")
    if timestamp is None:
        timestamp = time.time_ns()
    if type(timestamp) is not int or timestamp < 0:
        raise ValueError("Exportzeitpunkt muss eine nichtnegative Ganzzahl sein")
    with file_lock(f"{target}.lock", timeout=_LOCK_TIMEOUT):
        history = load_history(target)
        for identity in identities:
            history["last_exported"][identity] = timestamp
        history["last_set"] = identities
        _atomic_write(target, history)
        return history


def _weights(identities: list[str], history: dict) -> list[int]:
    exported = history["last_exported"]
    ordered = sorted(enumerate(identities), key=lambda item: (exported.get(item[1], 0), item[0]))
    by_identity = {identity: len(identities) - rank for rank, (_, identity) in enumerate(ordered)}
    return [by_identity[identity] for identity in identities]


def select_tracks(
    tracks: Sequence[object], requested: int | None, history: Mapping | None = None,
    *, rng: random.Random | random.SystemRandom | None = None,
    compatibility: Callable[[object, object], int] | None = None,
    transition_score: Callable[[object, object], int] | None = None,
) -> tuple[list[object], SelectionReport]:
    """Waehlt ohne Zuruecklegen; die existierende Strategie sortiert danach."""
    requested = validate_playlist_length(requested)
    if requested is None:
        return list(tracks), SelectionReport(
            requested=None, eligible=len(tracks), selected=len(tracks),
            avoided_previous_set=False,
        )
    eligible = _eligible_unique(tracks)
    checked_history = validate_history(history if history is not None else empty_history())
    limit = min(requested, len(eligible))
    if limit >= len(eligible):
        selected = list(eligible)
        avoided = False
    else:
        generator = rng or random.SystemRandom()
        identities = [_track_id(track) for track in eligible]
        weights = _weights(identities, checked_history)
        remaining = list(zip(eligible, weights))
        selected = []
        previous = set(checked_history["last_set"])
        avoided = False
        while remaining and len(selected) < limit:
            candidates = list(range(len(remaining)))
            if (transition_score is not None and len(previous) == limit
                    and len(selected) == limit - 1
                    and all(_track_id(t) in previous for t in selected)):
                candidates = [i for i in candidates if _track_id(remaining[i][0]) not in previous]
                avoided = True
            if compatibility is not None and selected:
                scores = [compatibility(selected[-1], track) for track, _ in remaining]
                if transition_score is None:
                    strongest = max(scores)
                    candidates = [i for i in candidates if scores[i] == strongest]
                else:
                    # Actual mix-window scoring reads local evidence. Bound
                    # that work while admitting alternatives to an ideal key.
                    candidates.sort(key=lambda i: (scores[i], remaining[i][1]), reverse=True)
                    shortlist = candidates[:12]
                    ranked = {i: (transition_score(selected[-1], remaining[i][0]), scores[i])
                              for i in shortlist}
                    strongest = max(ranked.values())
                    candidates = [i for i in shortlist if ranked[i] == strongest]
            index = generator.choices(
                candidates, weights=[remaining[i][1] for i in candidates], k=1
            )[0]
            selected.append(remaining.pop(index)[0])
        selected_ids = {_track_id(track) for track in selected}
        if (selected_ids == previous and previous
                and len(eligible) > limit and limit > 0):
            remaining_ids = {_track_id(track) for track, _ in remaining}
            replacements = [track for track in eligible if _track_id(track) in remaining_ids]
            replacement = min(
                replacements,
                key=lambda track: (checked_history["last_exported"].get(_track_id(track), 0), _track_id(track)),
            )
            replace_index = max(
                range(len(selected)),
                key=lambda index: (
                    checked_history["last_exported"].get(_track_id(selected[index]), 0),
                    index,
                ),
            )
            selected[replace_index] = replacement
            avoided = True
    return selected, SelectionReport(
        requested=requested, eligible=len(eligible), selected=len(selected),
        avoided_previous_set=avoided,
    )
