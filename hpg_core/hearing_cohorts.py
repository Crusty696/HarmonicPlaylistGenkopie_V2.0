"""Deterministische Metadaten-Kohorten; keine Audio-/Datei-/Bewertungszugriffe."""
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math

from .collection_index import CollectionIndex, _key, _validated
from .config import SECURITY_MAX_PLAYLIST_SIZE


@dataclass(frozen=True)
class CohortContext:
    # Vom Aufrufer gelieferte Bindungen sind kein hier erbrachter Quellnachweis.
    cache_binding: str | None = None
    build_binding: str | None = None


@dataclass(frozen=True)
class CohortFeature:
    path: str
    size: int
    mtime_ns: int
    context: CohortContext
    genre: str | None = None
    bpm: float | None = None
    energy: float | None = None
    # Expliziter Beatgridstatus, nicht die gesamte Analysequalitaet.
    beatgrid_status: str | None = None


@dataclass(frozen=True)
class CohortSelection:
    version: int
    binding_digest: str
    count: int
    seed: int
    paths: tuple[str, ...]
    strata: tuple[tuple[tuple[str, str, str, str], int, int], ...]
    total_entries: int
    missing_entries: int
    eligible_entries: int
    unselected_entries: int
    unknown_feature_entries: int
    stale_feature_records: int
    shortfall: int
    selection_reused: bool = False


def _context(value):
    if type(value) is not CohortContext:
        raise ValueError("CohortContext erforderlich")
    for binding in (value.cache_binding, value.build_binding):
        if binding is not None and (type(binding) is not str or not binding or "\x00" in binding):
            raise ValueError("Bindung muss nichtleerer String oder unbekannt sein")
    return value.cache_binding is not None and value.build_binding is not None


def _feature(value):
    if type(value) is not CohortFeature:
        raise ValueError("CohortFeature erforderlich")
    _context(value.context)
    if (type(value.path) is not str or "\x00" in value.path
            or any(type(n) is not int or n < 0 for n in (value.size, value.mtime_ns))):
        raise ValueError("Ungueltige Feature-Quellbindung")
    if value.genre is not None and (type(value.genre) is not str or not value.genre.strip()):
        raise ValueError("Genre muss explizit oder unbekannt sein")
    for name in ("bpm", "energy"):
        number = getattr(value, name)
        if number is not None and (type(number) not in (int, float) or not math.isfinite(number)
                or (number <= 0 if name == "bpm" else not 0 <= number <= 1)):
            raise ValueError("Ungueltiger expliziter Messwert")
    if value.beatgrid_status is not None and (
            type(value.beatgrid_status) is not str or value.beatgrid_status not in
            {"unknown", "unverifiable", "unsupported", "mismatch", "verified"}):
        raise ValueError("Ungueltiger Beatgridstatus")


def _stratum(feature):
    if feature is None:
        return ("unknown",) * 4
    # V1: Tempo in 10-BPM-Baendern [n*10,(n+1)*10), Energie 0/.25/.5/.75/1.
    tempo = "unknown" if feature.bpm is None else str(math.floor(feature.bpm / 10))
    energy = "unknown" if feature.energy is None else str(min(3, math.floor(feature.energy * 4)))
    return (feature.genre if feature.genre is not None else "unknown", tempo, energy,
            feature.beatgrid_status if feature.beatgrid_status is not None else "unknown")


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def select_cohort(index, *, count, seed, context, features=(), previous=None):
    """Gesamten Index betrachten; nur Auswahl begrenzen. Kein Qualitaetsversprechen.

    Veraltete Features werden unbekannt, nicht der zugehoerige Track entfernt.
    Auswahlreuse betrifft keine Audiomessung, Rating- oder Variantenfreigabe.
    """
    complete = _context(context)
    if type(count) is not int or not 1 <= count <= SECURITY_MAX_PLAYLIST_SIZE or type(seed) is not int:
        raise ValueError("Count und Seed muessen gueltige Ganzzahlen sein")
    if (type(index) is not CollectionIndex or type(index.cancelled) is not bool
            or index.cancelled or index.errors):
        raise ValueError("Vollstaendiger fehlerfreier Index erforderlich")
    if type(index.roots) not in (tuple, list) or type(index.entries) not in (tuple, list):
        raise ValueError("Ungueltiger Index")
    raw = {"kind": "hpg_collection_index", "version": 1, "roots": list(index.roots),
           "entries": [asdict(entry) for entry in index.entries]}
    if any(type(path) is not str or "\x00" in path for path in raw["roots"]):
        raise ValueError("Ungueltige Root")
    if any(type(entry["path"]) is not str or "\x00" in entry["path"] for entry in raw["entries"]):
        raise ValueError("Ungueltiger Eintragspfad")
    checked = _validated(raw)
    roots = tuple(sorted(checked.roots, key=_key))
    entries = tuple(sorted(checked.entries, key=lambda entry: _key(entry.path)))
    if type(features) not in (tuple, list):
        raise ValueError("Featurefolge erforderlich")
    feature_map = {}
    entry_map = {_key(entry.path): entry for entry in entries}
    for feature in features:
        _feature(feature)
        key = _key(feature.path)
        if key not in entry_map or feature.path != entry_map[key].path or key in feature_map:
            raise ValueError("Fremder, nichtkanonischer oder doppelter Featurepfad")
        feature_map[key] = feature
    binding = _digest({"selector_version": 1, "index_version": 1, "roots": roots,
                       "entries": [asdict(entry) for entry in entries], "context": asdict(context),
                       "features": [asdict(feature_map[key]) for key in sorted(feature_map)],
                       "count": count, "seed": seed})
    buckets = defaultdict(list)
    stale = unknown = missing = 0
    for entry in entries:
        feature = feature_map.get(_key(entry.path))
        if feature is not None and (not complete or feature.context != context
                or (feature.size, feature.mtime_ns) != (entry.size, entry.mtime_ns)):
            stale += 1
            feature = None
        if entry.status == "missing":
            missing += 1
            continue
        stratum = _stratum(feature)
        unknown += int("unknown" in stratum)
        buckets[stratum].append(entry.path)
    # Digest-Tiebreaks statt globalem RNG; unabhaengig von Eingabereihenfolge.
    strata_order = sorted(buckets, key=lambda group: (_digest([seed, group]), group))
    for group in strata_order:
        buckets[group].sort(key=lambda path: (_digest([seed, group, path]), _key(path)))
    selected = []
    positions = dict.fromkeys(strata_order, 0)
    while len(selected) < count:
        advanced = False
        for group in strata_order:
            position = positions[group]
            if position < len(buckets[group]) and len(selected) < count:
                selected.append(buckets[group][position])
                positions[group] += 1
                advanced = True
        if not advanced:
            break
    eligible = len(entries) - missing
    result = CohortSelection(1, binding, count, seed, tuple(selected),
        tuple((group, len(buckets[group]), positions[group]) for group in strata_order),
        len(entries), missing, eligible, eligible - len(selected), unknown, stale,
        count - len(selected))
    if previous is not None:
        if type(previous) is not CohortSelection:
            raise ValueError("Ungueltige vorherige Auswahl")
        if previous.binding_digest == binding:
            if (type(previous.selection_reused) is not bool or type(previous.paths) is not tuple
                    or type(previous.strata) is not tuple
                    or any(type(row) is not tuple or len(row) != 3 or type(row[0]) is not tuple
                           for row in previous.strata)
                    or _digest(asdict(replace(previous, selection_reused=False))) != _digest(asdict(result))):
                raise ValueError("Vorherige Auswahl widerspricht ihrer Bindung")
            if complete:
                result = replace(result, selection_reused=True)
    return result
