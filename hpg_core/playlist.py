from __future__ import annotations

from .models import (
    Track,
    key_to_camelot,
    effective_bpm_diff,
    get_camelot_components,
    camelot_relation_score,
    seconds_per_bar,
    QUANTIZE_TOLERANCE_SEC,
)
from typing import TYPE_CHECKING
from .dj_brain import (
    _get_outro_start_from_sections,
    get_genre_compatibility,
    generate_dj_recommendation,
)

if TYPE_CHECKING:
    from .dj_brain import DJRecommendation
from .config import (
    GENRE_WEIGHT_WITH_DJ_BRAIN,
    GENRE_WEIGHT_WITHOUT_DJ_BRAIN,
    BPM_HALF_DOUBLE_PENALTY,
    LOOKAHEAD_TOP_K,
    METER,
    DEFAULT_BPM,
    MAX_TRANSITION_OVERLAP_SECONDS,
    MIN_TRANSITION_BARS,
    PAAR_BPM_MAX,
)
from .genres import CANONICAL_GENRES, resolve_track_genre
from .transition_features import (
    bass_continuity,
    groove_match,
    mood_match,
    timbre_match,
)

_CANONICAL_CASEFOLD = frozenset(genre.casefold() for genre in CANONICAL_GENRES)
import logging
import heapq
import math
import unicodedata
import uuid
import weakref
from numbers import Real
from itertools import permutations
from copy import deepcopy
from collections.abc import Mapping
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class _FrozenMapping(tuple):
    """Markiert eingefrorene Mappings, auch wenn sie leer sind."""


class _FrozenSequence(tuple):
    """Markiert eingefrorene Sequenzen, auch wenn sie leer sind."""

# AUDIT-FIX D6/F28 (2026-07-24): vormals hartkodierte Scoring-Konstanten
# (Magic Numbers) zentralisiert. Bei Bedarf spaeter nach config.py heben.
SMOOTHING_ENERGY_DISRUPTION_MAX = 20  # max. Energiesprung fuer harmonischen Swap
SMOOTHING_MAX_ITERATIONS = 3          # Passes im harmonic-smoothing-Loop
LOOKAHEAD_FUTURE_WEIGHT = 0.7         # Gewicht des Lookahead-Zukunftsterms
VOCAL_CLASH_PENALTY = 0.06            # Abzug wenn BEIDE Tracks vocal sind (D2-light)


def _freeze_immutable(value):
    """Kanonische, tief unveraenderliche Result-Repräsentation."""
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Result-Wert muss endlich sein")
        return value
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Enum):
        return _freeze_immutable(value.value)
    if isinstance(value, Mapping):
        return _FrozenMapping(
            (
                unicodedata.normalize("NFC", str(key)),
                _freeze_immutable(item),
            )
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        )
    if isinstance(value, (list, tuple)):
        return _FrozenSequence(_freeze_immutable(item) for item in value)
    if isinstance(value, (set, frozenset)):
        frozen = [_freeze_immutable(item) for item in value]
        return _FrozenSequence(sorted(frozen, key=repr))
    raise ValueError(f"Result-Werttyp nicht unterstuetzt: {type(value).__name__}")


def _thaw_immutable(value):
    """Defensive Legacy-Kopie einer eingefrorenen Result-Struktur."""
    if isinstance(value, _FrozenMapping):
        return {key: _thaw_immutable(item) for key, item in value}
    if isinstance(value, _FrozenSequence):
        return [_thaw_immutable(item) for item in value]
    if isinstance(value, dict):
        return {key: _thaw_immutable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        if all(
            isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str)
            for item in value
        ):
            return {key: _thaw_immutable(item) for key, item in value}
        return [_thaw_immutable(item) for item in value]
    return value


def _freeze_choice_snapshot(value: Mapping) -> tuple:
    """Friert Kandidatenwahlen ein, ohne ihre Tupel-Schluessel zu verlieren."""
    if not isinstance(value, Mapping):
        raise ValueError("candidate_choice_snapshot muss ein Mapping sein")
    return tuple(
        sorted(
            (
                (_freeze_immutable(key), _freeze_immutable(item))
                for key, item in value.items()
            ),
            key=lambda pair: repr(pair[0]),
        )
    )


def _thaw_choice_key(value):
    if isinstance(value, tuple):
        return tuple(_thaw_choice_key(item) for item in value)
    return value


def _thaw_choice_snapshot(value: tuple) -> dict:
    return {
        _thaw_choice_key(key): _thaw_immutable(item)
        for key, item in value
    }


@dataclass(frozen=True)
class StrategyConfig:
    """Typisierter, validierter Vertrag der sichtbaren Strategieparameter."""

    energy_direction: str = "Auto"
    peak_position: int = 70
    harmonic_strictness: int = 7
    allow_experimental: bool = True
    genre_mixing: bool = True
    genre_weight: float = 0.3
    target_energy: Optional[float] = None

    @classmethod
    def from_mapping(cls, values: Optional[Mapping]) -> "StrategyConfig":
        if values is None:
            source = {}
        elif not isinstance(values, Mapping):
            raise ValueError("advanced_params muss ein Mapping oder None sein")
        else:
            source = dict(values)
        allowed = {
            "energy_direction", "peak_position", "harmonic_strictness",
            "allow_experimental", "genre_mixing", "genre_weight",
            "target_energy",
        }
        unknown = sorted(set(source) - allowed, key=repr)
        if unknown:
            raise ValueError(
                "advanced_params enthaelt unbekannte Schluessel: "
                + ", ".join(repr(key) for key in unknown)
            )

        energy_direction = source.get("energy_direction", "Auto")
        if type(energy_direction) is not str or energy_direction not in SCORING_ENERGY_DIRECTIONS:
            raise ValueError("advanced_params.energy_direction ist nicht unterstuetzt")

        peak_position = source.get("peak_position", 70)
        if type(peak_position) is not int or not 40 <= peak_position <= 80:
            raise ValueError("advanced_params.peak_position muss eine Ganzzahl 40..80 sein")

        harmonic_strictness = source.get("harmonic_strictness", 7)
        if type(harmonic_strictness) is not int or not 1 <= harmonic_strictness <= 10:
            raise ValueError(
                "advanced_params.harmonic_strictness muss eine Ganzzahl 1..10 sein"
            )

        allow_experimental = source.get("allow_experimental", True)
        if type(allow_experimental) is not bool:
            raise ValueError("advanced_params.allow_experimental muss Boolean sein")
        genre_mixing = source.get("genre_mixing", True)
        if type(genre_mixing) is not bool:
            raise ValueError("advanced_params.genre_mixing muss Boolean sein")

        def finite_real(name, default, minimum, maximum, *, allow_none=False):
            value = source.get(name, default)
            if allow_none and value is None:
                return None
            if (
                isinstance(value, bool)
                or not isinstance(value, Real)
                or not math.isfinite(float(value))
                or not minimum <= float(value) <= maximum
            ):
                raise ValueError(
                    f"advanced_params.{name} muss eine endliche Zahl "
                    f"zwischen {minimum:g} und {maximum:g} sein"
                )
            return float(value)

        return cls(
            energy_direction=energy_direction,
            peak_position=peak_position,
            harmonic_strictness=harmonic_strictness,
            allow_experimental=allow_experimental,
            genre_mixing=genre_mixing,
            genre_weight=finite_real("genre_weight", 0.3, 0.0, 1.0),
            target_energy=finite_real(
                "target_energy", None, 0.0, 100.0, allow_none=True
            ),
        )

    def effective_kwargs(self, strategy: str) -> Dict:
        supported = SUPPORTED_STRATEGY_PARAMETERS.get(strategy, set())
        values = {
            "energy_direction": self.energy_direction,
            "peak_position": self.peak_position,
            "harmonic_strictness": self.harmonic_strictness,
            "allow_experimental": self.allow_experimental,
            "genre_mixing": self.genre_mixing,
            "genre_weight": self.genre_weight,
            "target_energy": self.target_energy,
        }
        return {key: value for key, value in values.items() if key in supported}


@dataclass
class TransitionMetrics:
    """Metrics for evaluating track transitions."""

    harmonic_score: int
    bpm_smoothness: float
    energy_flow: float
    genre_compatibility: float
    overall_score: float
    ai_bonus: float = 0.0
    # Lokale Faktoren des konkreten Mixfenster-Paars. None bedeutet, dass kein
    # vollstaendig bewertbarer lokaler Uebergang vorhanden ist.
    groove_match: Optional[float] = None
    bass_continuity: Optional[float] = None
    timbre_match: Optional[float] = None
    mood_match: Optional[float] = None
    # Kandidatenpfad (Spec 2026-08-21 Abschnitt 4): lokale Teilwerte des besten
    # PairCandidate; None, wenn das Paar ohne Kandidaten bewertet wurde.
    loudness_match: Optional[float] = None
    structure_match: Optional[float] = None
    energy_delta: Optional[float] = None
    lufs_delta: Optional[float] = None
    kandidat: Optional[dict] = None   # PairCandidate.to_dict() der aktiven Result-Kette


@dataclass
class TransitionRecommendation:
    """Suggested mix window details for consecutive tracks."""

    index: int
    from_track: Track
    to_track: Track
    fade_out_start: float
    fade_out_end: float
    fade_in_start: float
    mix_entry: float
    overlap: float
    bpm_delta: float
    energy_delta: int
    compatibility_score: int
    risk_level: str
    notes: str
    transition_type: str = "blend"  # Vorhergesagter Transition-Typ
    dj_rec: Optional["DJRecommendation"] = None  # Paar-spezifische DJ-Brain-Empfehlung
    plan: Optional["TransitionPlan"] = None
    # Alle PairCandidates des Paars (to_dict) in App-Reihenfolge und der Rang des
    # aktiven Kandidaten (0 = keiner; dann tragen Plan/Track die Zeitpunkte).
    kandidaten: List[dict] = field(default_factory=list)
    kandidat_aktiv: int = 0
    # False, wenn kein Kandidat hinter dem Mix-In des vorigen Paars lag und
    # deshalb Rang 1 genommen wurde (Invariante 1 je Track dann verletzt).
    kandidat_konsistent: bool = True


@dataclass(frozen=True)
class TransitionPlan:
    """Unveraenderlicher Zeit- und Rendervertrag eines Uebergangs."""

    mix_out_a: float
    mix_in_b: float
    fade_out_start: float
    fade_out_end: float
    overlap: float
    transition_type: str
    curve: str = "linear"
    eq_mode: str = "default"
    tempo_ratio: float = 1.0
    target_sr: int = 44100

    @property
    def crossfade_frames(self) -> int:
        return int(round(self.overlap * self.target_sr))


@dataclass(frozen=True, slots=True)
class TrackOccurrence:
    run_id: str
    ordinal: int
    track: Track

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id:
            raise ValueError("run_id muss eine nichtleere Zeichenkette sein")
        if (
            isinstance(self.ordinal, bool)
            or not isinstance(self.ordinal, int)
            or self.ordinal < 0
        ):
            raise ValueError("ordinal muss eine nichtnegative ganze Zahl sein")
        if not isinstance(self.track, Track):
            raise ValueError("track muss ein Track sein")

    @property
    def occurrence_id(self) -> tuple[str, int]:
        return (self.run_id, self.ordinal)


@dataclass(frozen=True, slots=True)
class ImmutableMetricsSnapshot:
    harmonic_score: int
    bpm_smoothness: float
    energy_flow: float
    genre_compatibility: float
    overall_score: float
    ai_bonus: float = 0.0
    groove_match: Optional[float] = None
    bass_continuity: Optional[float] = None
    timbre_match: Optional[float] = None
    mood_match: Optional[float] = None
    loudness_match: Optional[float] = None
    structure_match: Optional[float] = None
    energy_delta: Optional[float] = None
    lufs_delta: Optional[float] = None
    kandidat: Optional["CandidateSnapshot"] = None


@dataclass(frozen=True, slots=True)
class ImmutableRecommendationSnapshot:
    index: int
    from_occurrence_id: tuple[str, int]
    to_occurrence_id: tuple[str, int]
    fade_out_start: float
    fade_out_end: float
    fade_in_start: float
    mix_entry: float
    overlap: float
    bpm_delta: float
    energy_delta: int
    compatibility_score: int
    risk_level: str
    notes: str
    transition_type: str
    plan: Optional[TransitionPlan]
    candidates: tuple["CandidateSnapshot", ...]
    active_candidate_key: Optional[tuple]
    candidate_consistent: bool


@dataclass(frozen=True, slots=True)
class BoundaryResult:
    index: int
    from_occurrence_id: tuple[str, int]
    to_occurrence_id: tuple[str, int]
    snapshots: tuple["CandidateSnapshot", ...]
    selected: Optional["CandidateSnapshot"]
    metrics: ImmutableMetricsSnapshot
    recommendation: ImmutableRecommendationSnapshot
    consistent: bool


@dataclass(frozen=True, slots=True)
class GraphStats:
    input_tracks: int
    valid_tracks: int
    invalid_bpm_excluded: int
    boundaries_total: int
    boundaries_with_candidates: int
    boundaries_without_candidates: int
    candidate_snapshots: int
    saved_present: int


@dataclass(frozen=True, slots=True)
class PathStats:
    boundaries_total: int
    with_candidates: int
    planned: int
    unplanned: int
    saved_present: int
    saved_honored: int
    link_checks: int
    consistent_links: int
    segments: int
    segment_restarts: int
    states_retained: int
    total_score: float


@dataclass(frozen=True, slots=True)
class PlaylistGenerationResult:
    run_id: str
    mode: str
    tracks: tuple[Track, ...]
    occurrences: tuple[TrackOccurrence, ...]
    boundaries: tuple[BoundaryResult, ...]
    metrics: tuple[ImmutableMetricsSnapshot, ...]
    recommendations: tuple[ImmutableRecommendationSnapshot, ...]
    quality: tuple[tuple[str, float], ...]
    scoring_context: tuple[tuple[str, object], ...]
    candidate_choice_snapshot: tuple
    graph_stats: GraphStats
    path_stats: PathStats
    bpm_tolerance: float

    def quality_dict(self) -> dict[str, float]:
        return dict(self.quality)

    def scoring_context_dict(self) -> dict:
        return _thaw_immutable(dict(self.scoring_context))

    def candidate_choice_snapshot_dict(self) -> dict:
        return _thaw_choice_snapshot(self.candidate_choice_snapshot)


@dataclass
class TransitionDescriptionParams:
    """Parameters for building a transition description."""

    compatibility_score: int
    bpm_delta: float
    bpm_tolerance: float
    energy_delta: int
    metrics: "TransitionMetrics"
    from_track: Track
    to_track: Track
    has_dj_brain: bool = False


class EnergyDirection(Enum):
    """Direction of energy flow in transitions."""

    UP = "up"
    DOWN = "down"
    MAINTAIN = "maintain"


def _normalize_energy_direction(value) -> Optional[EnergyDirection]:
    """Normalisiert GUI-Presets und API-Werte auf den einen Scoring-Vertrag."""
    if isinstance(value, EnergyDirection):
        return value
    if not isinstance(value, str):
        return None
    return {
        "build up": EnergyDirection.UP,
        "up": EnergyDirection.UP,
        "cool down": EnergyDirection.DOWN,
        "down": EnergyDirection.DOWN,
        "maintain": EnergyDirection.MAINTAIN,
    }.get(value.strip().casefold())


def _check_cancel(cancel_check) -> None:
    """Bricht kooperativ ab; Aufrufer publizieren dadurch kein Teilergebnis."""
    if cancel_check is not None and cancel_check():
        raise InterruptedError("Playlist-Generierung abgebrochen")


def _track_cache_key(track: Track) -> int:
    """Trennt Track-Instanzen in den kurzlebigen Scoring-Caches.

    ``track_id`` ist absichtlich pfadbasiert und kann deshalb mehrere
    Occurrences oder verschieden analysierte Instanzen derselben Datei
    bezeichnen. Die Caches leben nur waehrend einer Generierung; dort ist die
    Objektidentitaet stabil und verhindert falsche Treffer zwischen Instanzen.
    """
    return id(track)


def _remove_track(items: list[Track], target: Track) -> None:
    """Entfernt einen Track ohne den teuren Deep-Vergleich der Track-Dataclass."""
    for index, candidate in enumerate(items):
        if candidate is target:
            del items[index]
            return
    raise ValueError("Track nicht in der Arbeitsliste gefunden")


def _enhanced_cache_key(
    track1: Track,
    track2: Track,
    bpm_tolerance: float,
    energy_direction: Optional[EnergyDirection],
    kwargs: Dict,
) -> tuple:
    normalized_direction = _normalize_energy_direction(energy_direction)
    direction = normalized_direction.value if normalized_direction is not None else None
    options = _stable_fingerprint({
        key: value for key, value in kwargs.items() if key != "cancel_check"
    })
    return (
        _track_cache_key(track1),
        _track_cache_key(track2),
        float(bpm_tolerance),
        direction,
        options,
    )


def _stable_fingerprint(value):
    """Hashbarer, reihenfolgeunabhaengiger Fingerprint fuer Run-Kontexte."""
    if isinstance(value, Mapping):
        return tuple(
            (str(key), _stable_fingerprint(item))
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        )
    if isinstance(value, (list, tuple)):
        return tuple(_stable_fingerprint(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted((_stable_fingerprint(item) for item in value), key=repr))
    if isinstance(value, Enum):
        return (type(value).__name__, value.value)
    try:
        hash(value)
    except TypeError:
        return repr(value)
    return value


def calculate_ai_compatibility_bonus(track1: Track, track2: Track) -> float:
    """Berechnet den stillgelegten Legacy-KI-Abgleich von 0 bis 0.14.

    Die Funktion bleibt vorerst fuer API-/Datenkompatibilitaet erhalten. Kein
    produktiver Scorepfad konsumiert ihren Rueckgabewert; die lokale Wertung
    stammt ausschliesslich aus ``PairCandidate.score``.
    """
    # Lazy-Import: ai_engine zieht requests, das Core-Scoring soll ohne laufen.
    # Defensiver Lazy-Import fuer bestehende externe Aufrufer.
    try:
        from .ai_engine import has_valid_provenance
    except Exception:
        return 0.0

    ai_meta1 = getattr(track1, "ai_metadata", {})
    ai_meta2 = getattr(track2, "ai_metadata", {})
    if not (has_valid_provenance(ai_meta1) and has_valid_provenance(ai_meta2)):
        return 0.0

    bonus = 0.0
    moods1 = ai_meta1.get("moods", [])
    moods2 = ai_meta2.get("moods", [])
    if isinstance(moods1, list) and isinstance(moods2, list):
        moods1_set = {str(m).strip().lower() for m in moods1 if m}
        moods2_set = {str(m).strip().lower() for m in moods2 if m}
        if moods1_set and moods2_set:
            overlap = moods1_set.intersection(moods2_set)
            bonus += 0.08 * (
                len(overlap) / max(len(moods1_set), len(moods2_set))
            )

    sub1 = ai_meta1.get("sub_genre", "")
    sub2 = ai_meta2.get("sub_genre", "")
    if isinstance(sub1, str) and isinstance(sub2, str) and sub1 and sub2:
        normalized1 = sub1.strip().lower()
        normalized2 = sub2.strip().lower()
        if normalized1 == normalized2:
            bonus += 0.06
        elif normalized1 in normalized2 or normalized2 in normalized1:
            bonus += 0.03
    return min(0.14, bonus)


def _get_camelot_components(camelot_code: str) -> tuple[int, str]:
    """Parses a Camelot code into its number and letter components.

    Delegiert an die zentrale Definition in models (Audit 2026-07-17).
    """
    return get_camelot_components(camelot_code)


def combine_weighted(
    components: dict[str, float | None], weights: dict[str, float]
) -> float:
    """Gewichtete Summe; fehlende Komponenten werden umverteilt.

    Ein Faktor mit Wert None ist "nicht bestimmbar" und wird NICHT mit 0
    bewertet — das waere eine stille Bestrafung fuer Tracks ohne Groove-Daten.
    Stattdessen faellt er samt Gewicht aus der Summe, und die verbleibenden
    Gewichte werden auf 1.0 renormiert.
    """
    verfuegbar = {k: v for k, v in components.items() if v is not None}
    if not verfuegbar:
        return 0.0
    gewicht_summe = sum(weights.get(k, 0.0) for k in verfuegbar)
    if gewicht_summe <= 0.0:
        return 0.0
    roh = sum(weights.get(k, 0.0) * float(v) for k, v in verfuegbar.items())
    return roh / gewicht_summe


def _resolve_track_genre(track: Track) -> str:
    """Genre eines Tracks fuer das Scoring: DJ-Brain-Klassifikation vor ID3.

    AUDIT-FIX F12 (2026-07-24): detected_genre-Default "Unknown" ist TRUTHY,
    ein `or`-Fallback auf das ID3-Genre war damit toter Code. Explizit
    aufloesen — vorher dreimal identisch lokal definiert (enhanced
    compatibility, predict_transition_type, Context Flow).
    """
    return resolve_track_genre(track)


def _kandidaten_fuer_paar(
    track1: Track,
    track2: Track,
    bpm_tolerance: float,
    energy_direction,
    kwargs: dict,
) -> list:
    """PairCandidates des Paars in App-Reihenfolge (pair_candidates.rank_pair_candidates),
    dauerhaft gecacht in _PAIR_CANDIDATE_CACHE (Schluessel: Track-Identitaet,
    energy_direction, kwargs; geleert von reset_pair_candidate_cache, das Wahl,
    Praeferenz und Toleranzen lazy aufrufen). Leer, wenn eine Seite keine
    Kandidaten traegt."""
    cancel_check = kwargs.get("cancel_check")
    _check_cancel(cancel_check)
    if not (getattr(track1, "mix_out_candidates", None) and getattr(track2, "mix_in_candidates", None)):
        return []
    try:
        tolerance = float(bpm_tolerance)
    except (TypeError, ValueError):
        return []
    bpm_diff, _ = effective_bpm_diff(track1.bpm, track2.bpm)
    if not math.isfinite(tolerance) or tolerance < 0.0 or bpm_diff > tolerance:
        return []
    direction = _normalize_energy_direction(energy_direction)
    genre = _resolve_track_genre(track1)
    toleranzprofile = kwargs.get("candidate_tolerances_by_genre")
    if isinstance(toleranzprofile, Mapping):
        tolerances = toleranzprofile.get(
            genre, toleranzprofile.get("Unknown", {})
        )
    else:
        tolerances = None
    schema_profile = kwargs.get("candidate_schema_ranks_by_genre")
    if isinstance(schema_profile, Mapping):
        schema_rang = schema_profile.get(
            genre, schema_profile.get("Unknown", [])
        )
    else:
        schema_rang = None
    choice_snapshot = kwargs.get("candidate_choice_snapshot")
    if isinstance(choice_snapshot, Mapping):
        from . import candidate_choices

        wahl = choice_snapshot.get(
            candidate_choices.schluessel(track1.filePath, track2.filePath), {}
        )
    else:
        wahl = None
    # Lazy: pair_candidates importiert playlist-Teile lazy — kein Zyklus auf Modulebene.
    from .pair_candidates import rank_pair_candidates
    key = (
        id(track1), id(track2), _track_cache_key(track1), _track_cache_key(track2),
        tolerance, direction.value if direction is not None else None,
        _stable_fingerprint({
            k: v for k, v in kwargs.items()
            if k not in {
                "energy_direction",
                "candidate_tolerances_by_genre",
                "candidate_schema_ranks_by_genre",
                "candidate_choice_snapshot",
                "cancel_check",
            }
        }),
        _stable_fingerprint(tolerances),
        _stable_fingerprint(schema_rang),
        _stable_fingerprint(wahl),
    )
    cached = _PAIR_CANDIDATE_CACHE.get(key)
    if cached is not None:
        cached_track1, cached_track2, paare = cached
        if cached_track1() is track1 and cached_track2() is track2:
            return paare
    paare = rank_pair_candidates(
        track1, track2, bpm_tolerance=tolerance, energy_direction=direction,
        harmonic_strictness=kwargs.get("harmonic_strictness", 7),
        allow_experimental=kwargs.get("allow_experimental", True),
        tolerances=tolerances,
        wahl=wahl,
        schema_rang=schema_rang,
    )
    _check_cancel(cancel_check)
    # Weakrefs pruefen bei einer spaeteren id()-Wiederverwendung die Identitaet,
    # ohne alte Analyse-Trackobjekte dauerhaft im Speicher zu halten.
    _PAIR_CANDIDATE_CACHE[key] = (weakref.ref(track1), weakref.ref(track2), paare)
    return paare


def calculate_enhanced_compatibility(
    track1: Track,
    track2: Track,
    bpm_tolerance: float,
    energy_direction: Optional[EnergyDirection] = None,
    **kwargs,
) -> TransitionMetrics:
    """Bewertet nur individuelle lokale Mixfenster beider Tracks."""

    energy_direction = _normalize_energy_direction(energy_direction)
    cache_key = _enhanced_cache_key(
        track1, track2, bpm_tolerance, energy_direction, kwargs
    )
    if _ENHANCED_COMPAT_CACHE is not None:
        cached = _ENHANCED_COMPAT_CACHE.get(cache_key)
        if cached is not None:
            return cached

    bpm_diff, _ = effective_bpm_diff(track1.bpm, track2.bpm)
    kandidat = None
    if bpm_diff <= bpm_tolerance:
        paare = _kandidaten_fuer_paar(
            track1, track2, bpm_tolerance, energy_direction, kwargs
        )
        if paare:
            kandidat = paare[0]
    metrics = _calculate_track_edge_metrics(
        track1, track2, bpm_tolerance, energy_direction, kwargs, kandidat
    )
    if _ENHANCED_COMPAT_CACHE is not None:
        _ENHANCED_COMPAT_CACHE[cache_key] = metrics
    return metrics


def _candidate_delta(kandidat, feld: str) -> Optional[float]:
    """Signierte lokale B-minus-A-Differenz, robust fuer alte API-Shims."""
    try:
        out_wert = getattr(kandidat.out_a, feld)
        in_wert = getattr(kandidat.in_b, feld)
        if out_wert is None or in_wert is None:
            return None
        return float(in_wert) - float(out_wert)
    except (AttributeError, TypeError, ValueError):
        return None


def transition_metrics_from_candidate(kandidat) -> TransitionMetrics:
    """Erzeugt alle sichtbaren Werte ausschliesslich aus dem lokalen Paar-Score."""
    if kandidat is None:
        return TransitionMetrics(0, 0.0, 0.0, 0.0, 0.0)
    tw = kandidat.teilwerte
    return TransitionMetrics(
        harmonic_score=int(round(float(tw["harmonic"]) * 100)),
        bpm_smoothness=float(tw["bpm"]),
        energy_flow=float(tw["energy"]),
        genre_compatibility=float(tw["genre"]),
        overall_score=float(kandidat.score),
        ai_bonus=0.0,
        groove_match=float(tw["groove"]),
        bass_continuity=float(tw["bass"]),
        timbre_match=float(tw["timbre"]),
        mood_match=float(tw["mood"]),
        loudness_match=float(tw["loudness"]),
        structure_match=float(tw["structure"]),
        energy_delta=_candidate_delta(kandidat, "energy_lokal"),
        lufs_delta=_candidate_delta(kandidat, "lufs_lokal"),
        kandidat=kandidat.to_dict(),
    )


_TRACK_EDGE_FACTORS = (
    "harmonic", "bpm", "energy", "genre", "groove", "bass", "timbre", "mood",
)


def _track_edge_weights(profile: Mapping, path: str) -> dict[str, float]:
    """Liest genau den vollstaendigen Acht-Faktoren-Kreis eines Run-Snapshots."""
    if not isinstance(profile, Mapping):
        raise ValueError(f"{path} muss ein Mapping sein")
    weights: dict[str, float] = {}
    for factor in _TRACK_EDGE_FACTORS:
        key = f"{factor}_weight"
        value = profile.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, Real)
            or not math.isfinite(float(value))
            or float(value) < 0.0
        ):
            raise ValueError(f"{path}[{key!r}] muss ein endliches Gewicht >= 0 sein")
        weights[factor] = float(value)
    total = sum(weights.values())
    if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError(f"{path} Track-Gewichte summieren auf {total}, erwartet ist 1.0")
    return weights


def _track_tolerance_profile(track: Track, kwargs: Mapping) -> tuple[str, Mapping]:
    """Nimmt den pro Run eingefrorenen Gewichtskreis des Quellgenres."""
    genre = _resolve_track_genre(track)
    profiles = kwargs.get("track_tolerances_by_genre")
    if isinstance(profiles, Mapping):
        profile = profiles.get(genre, profiles.get("Unknown"))
        if profile is None:
            raise ValueError(f"track_tolerances_by_genre fehlt Profil fuer {genre!r}")
        return genre, profile
    # Direkte API-Aufrufe bleiben moeglich; Generation/Rebuild liefern immer
    # den eingefrorenen Snapshot und lesen diese Fallback-Quelle daher nicht.
    from .tolerances import get_tolerances
    return genre, get_tolerances(genre)


def _calculate_track_edge_metrics(
    track1: Track,
    track2: Track,
    bpm_tolerance: float,
    energy_direction: Optional[EnergyDirection],
    kwargs: Mapping,
    kandidat=None,
) -> TransitionMetrics:
    """Acht-Faktoren-Score der Trackkante, unabhaengig von Mixpunkt-Ranking."""
    energy_direction = _normalize_energy_direction(energy_direction)
    harmonic_score = _calculate_compatibility_inner(
        track1, track2, bpm_tolerance, **kwargs
    )
    bpm_diff, _ = effective_bpm_diff(track1.bpm, track2.bpm)
    bpm_smoothness = (
        math.exp(-bpm_diff / max(float(bpm_tolerance) / 2.0, 1e-9))
        if bpm_diff <= bpm_tolerance else 0.0
    )
    candidate_delta_energy = _candidate_delta(kandidat, "energy_lokal")
    if candidate_delta_energy is not None:
        energy_delta = candidate_delta_energy
    else:
        energy_delta = float(track2.energy) - float(track1.energy)
    if energy_direction == EnergyDirection.UP:
        energy_flow = min(1.0, max(0.0, energy_delta) / 50.0)
    elif energy_direction == EnergyDirection.DOWN:
        energy_flow = min(1.0, max(0.0, -energy_delta) / 50.0)
    elif energy_direction == EnergyDirection.MAINTAIN:
        energy_flow = max(0.0, 1.0 - abs(energy_delta) / 50.0)
    else:
        energy_flow = max(0.0, 1.0 - abs(energy_delta) / 100.0)

    genre_a, profile = _track_tolerance_profile(track1, kwargs)
    genre_b = _resolve_track_genre(track2)
    weights = _track_edge_weights(
        profile, f"track_tolerances_by_genre[{genre_a!r}]"
    )
    resolved_genres = (
        genre_a.casefold() in _CANONICAL_CASEFOLD
        and genre_b.casefold() in _CANONICAL_CASEFOLD
    )
    if not resolved_genres:
        weights = dict(weights)
        weights["genre"] *= GENRE_WEIGHT_WITHOUT_DJ_BRAIN / GENRE_WEIGHT_WITH_DJ_BRAIN
    components = {
        "harmonic": harmonic_score / 100.0,
        "bpm": bpm_smoothness,
        "energy": energy_flow,
        "genre": get_genre_compatibility(genre_a, genre_b),
        "groove": groove_match(track1, track2, genre_a, profile),
        "bass": bass_continuity(track1, track2, genre_a, profile),
        "timbre": timbre_match(track1, track2, genre_a),
        "mood": mood_match(track1, track2, genre_a, profile),
    }
    overall_score = combine_weighted(components, weights)
    if bpm_diff > bpm_tolerance:
        overall_score = 0.0

    candidate_values = kandidat.teilwerte if kandidat is not None else {}
    def display_value(name: str, track_value):
        if kandidat is None or candidate_values.get(name) is None:
            return track_value
        return float(candidate_values[name])

    return TransitionMetrics(
        harmonic_score=harmonic_score,
        bpm_smoothness=bpm_smoothness,
        energy_flow=energy_flow,
        genre_compatibility=(
            float(candidate_values["genre"])
            if kandidat is not None and candidate_values.get("genre") is not None
            else 0.0
        ),
        overall_score=overall_score,
        ai_bonus=0.0,
        groove_match=display_value("groove", components["groove"]),
        bass_continuity=display_value("bass", components["bass"]),
        timbre_match=display_value("timbre", components["timbre"]),
        mood_match=display_value("mood", components["mood"]),
        loudness_match=(
            float(candidate_values["loudness"])
            if kandidat is not None else None
        ),
        structure_match=(
            float(candidate_values["structure"])
            if kandidat is not None else None
        ),
        energy_delta=energy_delta,
        lufs_delta=_candidate_delta(kandidat, "lufs_lokal"),
        kandidat=kandidat.to_dict() if kandidat is not None else None,
    )


def calculate_track_edge_score(
    track1: Track,
    track2: Track,
    bpm_tolerance: float,
    energy_direction: Optional[EnergyDirection] = None,
    **kwargs,
) -> TransitionMetrics:
    """Bewertet eine Trackkante ohne Kandidatenrang oder Mixpunktwahl."""
    return _calculate_track_edge_metrics(
        track1, track2, bpm_tolerance, energy_direction, kwargs
    )


def calculate_transition_objective(
    track1: Track, track2: Track, bpm_tolerance: float, **kwargs
) -> int:
    """Gemeinsame Zielfunktion fuer Sortierung, Anzeige und Empfehlungen."""
    _check_cancel(kwargs.get("cancel_check"))
    metrics = calculate_enhanced_compatibility(
        track1, track2, bpm_tolerance, **kwargs
    )
    return int(round(metrics.overall_score * 100))


# effective_bpm_diff lebt jetzt zentral in models.py (Audit 2026-07-17) —
# hier re-exportiert, damit bestehende Importe/Tests weiter funktionieren.


def _calculate_compatibility_inner(
    track1: Track, track2: Track, bpm_tolerance: float, **kwargs
) -> int:
    """Calculates a compatibility score between two tracks, including advanced harmonic rules.

    Args:
        track1, track2: Tracks to compare
        bpm_tolerance: Max BPM difference allowed
        **kwargs: Advanced parameters:
            - harmonic_strictness (1-10): Higher = stricter scoring (default: 7)
            - allow_experimental (bool): Allow +4/+7 techniques (default: True)
    """
    # Get advanced parameters
    strictness = kwargs.get("harmonic_strictness", 7)
    allow_experimental = kwargs.get("allow_experimental", True)

    bpm_diff, bpm_relation = effective_bpm_diff(track1.bpm, track2.bpm)
    if bpm_diff > bpm_tolerance:
        return 0  # No compatibility if BPM difference is too high
    penalty = BPM_HALF_DOUBLE_PENALTY if bpm_relation != "direct" else 1.0
    # Camelot-Tabelle zentral in models.camelot_relation_score (2026-08-22),
    # damit die Kandidaten-Paarbewertung (camelot_lokal) dieselbe Tabelle nutzt.
    return camelot_relation_score(
        track1.camelotCode, track2.camelotCode,
        harmonic_strictness=strictness, allow_experimental=allow_experimental,
        penalty=penalty,
    )


# Global thread-local-like cache containers for the current playlist generation
# session. They remain opt-in so direct API calls preserve their existing behavior.
#
# Context Flow und die Genre-Flow-Gruppengrenzen nutzen bewusst die reine
# Harmonik und damit _COMPAT_CACHE. Die uebrigen Strategien verwenden die
# erweiterte Zielfunktion und _ENHANCED_COMPAT_CACHE.
_ENHANCED_COMPAT_CACHE = None
_COMPAT_CACHE = None
# Kandidatenlisten je Paar. Anders als die beiden Caches oben DAUERHAFT aktiv:
# rank_pair_candidates kostet ~9 ms je Paar (gemessen 2026-08-22, 231 Tracks),
# und Sortierung, Metriken, Empfehlungen, Tabelle und Preview brauchen dieselbe
# Liste. Geleert ueber reset_pair_candidate_cache() — aufgerufen, wenn sich
# Wahl (candidate_choices), Praeferenzen (candidate_preferences) oder Gewichte
# (tolerances) aendern.
_PAIR_CANDIDATE_CACHE: dict = {}


def reset_pair_candidate_cache() -> None:
    """Leert den Kandidaten-Cache (Wahl/Praeferenz/Gewichte geaendert)."""
    _PAIR_CANDIDATE_CACHE.clear()


def calculate_compatibility(
    track1: Track, track2: Track, bpm_tolerance: float, **kwargs
) -> int:
    """Wrapper around _calculate_compatibility_inner that uses a global dictionary cache
    if one is currently set up by generate_playlist or benchmark.

    KI-Metadaten fliessen weder hier noch in die lokale PairCandidate-Wertung
    ein. Dieser Wrapper liefert reine harmonische Kompatibilitaet.
    """
    if _COMPAT_CACHE is not None:
        cache_key = (
            _track_cache_key(track1),
            _track_cache_key(track2),
            bpm_tolerance,
            kwargs.get("harmonic_strictness", 7),
            kwargs.get("allow_experimental", True),
        )
        cached = _COMPAT_CACHE.get(cache_key)
        if cached is not None:
            return cached
        score = _calculate_compatibility_inner(track1, track2, bpm_tolerance, **kwargs)
        _COMPAT_CACHE[cache_key] = score
        return score

    return _calculate_compatibility_inner(track1, track2, bpm_tolerance, **kwargs)


def _small_pool_order(tracks: list[Track], score_key, cancel_check=None) -> list[Track]:
    """Wertet kleine Pools vollstaendig und eingabereihenfolgefest aus."""
    if len(tracks) <= 1:
        return list(tracks)

    def stable_key(order) -> tuple:
        return tuple(
            (
                str(getattr(track, "filePath", "") or ""),
                str(getattr(track, "fileName", "") or ""),
                str(getattr(track, "title", "") or ""),
                float(getattr(track, "bpm", 0.0) or 0.0),
                float(getattr(track, "energy", 0.0) or 0.0),
                str(getattr(track, "camelotCode", "") or ""),
            )
            for track in order
        )

    best_order = None
    best_score = None
    best_stable_key = None
    for order in permutations(tracks):
        _check_cancel(cancel_check)
        score = tuple(score_key(order))
        order_stable_key = stable_key(order)
        if (
            best_order is None
            or score > best_score
            or score == best_score and order_stable_key < best_stable_key
        ):
            best_order = order
            best_score = score
            best_stable_key = order_stable_key
    return list(best_order)


def _transition_path_score(order, bpm_tolerance: float, kwargs: dict) -> tuple:
    scores = [
        calculate_transition_objective(a, b, bpm_tolerance, **kwargs)
        for a, b in zip(order, order[1:])
    ]
    return sum(score > 0 for score in scores), sum(scores)


def _sort_harmonic_flow(
    tracks: list[Track], bpm_tolerance: float, **kwargs
) -> list[Track]:
    """Enhanced harmonic flow using look-ahead and backtracking to avoid local optima."""
    cancel_check = kwargs.get("cancel_check")
    _check_cancel(cancel_check)
    if len(tracks) <= 2:
        return _small_pool_order(
            tracks,
            lambda order: _transition_path_score(order, bpm_tolerance, kwargs),
            cancel_check,
        )

    # Create a local cache specifically to avoid repeated function calls during lookahead
    # and pass it to _find_best_starting_track as well.
    compat_cache = {}

    # Capture kwargs in closure for nested function
    compat_kwargs = kwargs.copy()
    compat_kwargs["compat_cache"] = compat_cache

    def _lookahead_score(
        current: Track, remaining: List[Track], depth: int = 2
    ) -> Tuple[Track, float]:
        """Look ahead to find the best path with given depth."""
        if not remaining or depth <= 0:
            return None, 0.0

        # H6-Fix: Immediate-Scores zuerst berechnen, Rekursion nur fuer die
        # Top-K Kandidaten — reduziert O(n^3) auf O(n^2 * K) bei grossen Listen
        scored = []
        for candidate in remaining:
            _check_cancel(cancel_check)
            cache_key = (_track_cache_key(current), _track_cache_key(candidate))
            if cache_key in compat_cache:
                immediate_score = compat_cache[cache_key]
            else:
                immediate_score = calculate_transition_objective(
                    current, candidate, bpm_tolerance, **kwargs
                )
                compat_cache[cache_key] = immediate_score

            if immediate_score == 0:  # Skip incompatible tracks
                continue
            scored.append((immediate_score, candidate))

        if not scored:
            return None, -1

        scored = heapq.nlargest(
            LOOKAHEAD_TOP_K,
            scored,
            key=lambda item: item[0],
        )

        best_candidate = None
        best_total_score = -1
        for immediate_score, candidate in scored[:LOOKAHEAD_TOP_K]:
            _check_cancel(cancel_check)
            future_score = 0.0
            if depth > 1 and len(remaining) > 1:
                next_remaining = [t for t in remaining if t is not candidate]
                _, future_score = _lookahead_score(candidate, next_remaining, depth - 1)

            # Konstante statt Literal: derselbe Wert stand hier doppelt, ein
            # Aendern von LOOKAHEAD_FUTURE_WEIGHT haette nur die andere
            # Fundstelle erwischt und die Gewichtung still auseinanderlaufen
            # lassen. Sofort-Score wiegt schwerer als die Vorausschau.
            total_score = immediate_score + LOOKAHEAD_FUTURE_WEIGHT * future_score
            if total_score > best_total_score:
                best_total_score = total_score
                best_candidate = candidate

        return best_candidate, best_total_score

    unprocessed = list(tracks)
    # Start with a track that has good overall connectivity
    start_track = _find_best_starting_track(tracks, bpm_tolerance, **compat_kwargs)
    final_playlist = [start_track]
    _remove_track(unprocessed, start_track)

    current_track = start_track
    while unprocessed:
        _check_cancel(cancel_check)
        best_next, score = _lookahead_score(
            current_track, unprocessed, depth=2
        )  # Optimized: depth=2 (was 3)

        if best_next and score > 0:
            final_playlist.append(best_next)
            _remove_track(unprocessed, best_next)
            current_track = best_next
        else:
            # Fallback (Strategien-Merge 2026-07-17, portiert aus der frueheren
            # Plain-Variante): kein harmonisch kompatibler Kandidat mehr —
            # waehle den Track mit der kleinsten EFFEKTIVEN BPM-Differenz
            # (Half/Double-Time-bewusst) statt roher Kompatibilitaets-Maxima
            fallback = min(
                unprocessed,
                key=lambda t: effective_bpm_diff(t.bpm, current_track.bpm)[0],
            )
            final_playlist.append(fallback)
            _remove_track(unprocessed, fallback)
            current_track = fallback

    return final_playlist


def _find_best_starting_track(
    tracks: list[Track], bpm_tolerance: float, **kwargs
) -> Track:
    """Find the track with the best overall connectivity as starting point.

    Optimized: For large playlists, uses a more efficient sampling strategy.
    """
    cancel_check = kwargs.get("cancel_check")
    _check_cancel(cancel_check)
    if not tracks:
        return None
    if len(tracks) <= 1:
        return tracks[0]

    # Allow passing a compat_cache dictionary to avoid redundant compatibility calculations
    compat_cache = kwargs.pop("compat_cache", None)
    if compat_cache is None:
        compat_cache = {}

    # Optimization: For large playlists, sample max 30 candidates and check against max 20 others
    # This keeps the complexity O(1) for very large N
    max_candidates = min(30, len(tracks))
    max_comparisons = min(20, len(tracks))

    # Sample evenly distributed tracks as candidates
    candidate_indices = [
        int(i * (len(tracks) - 1) / (max_candidates - 1)) for i in range(max_candidates)
    ]
    comparison_indices = [
        int(i * (len(tracks) - 1) / (max_comparisons - 1))
        for i in range(max_comparisons)
    ]

    best_track = tracks[0]
    best_score = -1

    for i in candidate_indices:
        _check_cancel(cancel_check)
        track = tracks[i]
        total_compatibility = 0
        connections = 0

        for j in comparison_indices:
            _check_cancel(cancel_check)
            if i == j:
                continue

            cache_key = (_track_cache_key(track), _track_cache_key(tracks[j]))
            if cache_key in compat_cache:
                score = compat_cache[cache_key]
            else:
                score = calculate_transition_objective(
                    track, tracks[j], bpm_tolerance, **kwargs
                )
                compat_cache[cache_key] = score

            if score > 0:
                total_compatibility += score
                connections += 1

        connectivity_score = total_compatibility / connections if connections > 0 else 0
        if connectivity_score > best_score:
            best_score = connectivity_score
            best_track = track

    return best_track


def _sort_directional_bpm(
    tracks: list[Track],
    bpm_tolerance: float,
    reverse: bool,
    **kwargs,
) -> list[Track]:
    """Sortiert nach BPM und nutzt bei Gleichstand das volle Uebergangsziel."""
    cancel_check = kwargs.get("cancel_check")
    _check_cancel(cancel_check)
    if len(tracks) <= 1:
        return list(tracks)

    bpm_ordered = sorted(tracks, key=lambda track: track.bpm, reverse=reverse)
    result: list[Track] = []
    position = 0

    while position < len(bpm_ordered):
        _check_cancel(cancel_check)
        reference_bpm = bpm_ordered[position].bpm
        group = []
        while position < len(bpm_ordered) and math.isclose(
            bpm_ordered[position].bpm, reference_bpm, abs_tol=1e-9
        ):
            group.append(bpm_ordered[position])
            position += 1

        if len(group) == 1:
            result.extend(group)
            continue

        remaining = list(group)
        if result:
            current = result[-1]
        else:
            current = max(
                remaining,
                key=lambda candidate: sum(
                    calculate_transition_objective(
                        candidate, other, bpm_tolerance, **kwargs
                    )
                    for other in remaining
                    if other is not candidate
                ),
            )
            result.append(current)
            _remove_track(remaining, current)

        while remaining:
            _check_cancel(cancel_check)
            def _tie_break_score(candidate: Track) -> float:
                immediate = calculate_transition_objective(
                    current, candidate, bpm_tolerance, **kwargs
                )
                # AUDIT-FIX 2026-08-14: Guard (len(remaining) > 1) passte nicht
                # zum Filter (other is not candidate). Steht DASSELBE Track-
                # Objekt mehrfach in der BPM-Gruppe (Nutzer laedt eine Datei
                # doppelt), filtert der Generator alle Kopien heraus und max()
                # lief auf einer leeren Sequenz -> ValueError mitten in
                # Warm-Up/Cool-Down. default=0.0 ist bei nicht-leerer Sequenz
                # verhaltensgleich.
                future = max(
                    (
                        calculate_transition_objective(
                            candidate, other, bpm_tolerance, **kwargs
                        )
                        for other in remaining
                        if other is not candidate
                    ),
                    default=0.0,
                )
                return immediate + LOOKAHEAD_FUTURE_WEIGHT * future

            next_track = max(remaining, key=_tie_break_score)
            result.append(next_track)
            _remove_track(remaining, next_track)
            current = next_track

    return result


def _sort_warm_up(tracks: list[Track], bpm_tolerance: float, **kwargs) -> list[Track]:
    """BPM aufsteigend, Harmonik als Tiebreaker innerhalb gleicher BPM."""
    return _sort_directional_bpm(tracks, bpm_tolerance, reverse=False, **kwargs)


def _sort_cool_down(tracks: list[Track], bpm_tolerance: float, **kwargs) -> list[Track]:
    """BPM absteigend, Harmonik als Tiebreaker innerhalb gleicher BPM."""
    return _sort_directional_bpm(tracks, bpm_tolerance, reverse=True, **kwargs)


def _normalize_series(values: list[float]) -> list[float]:
    """Normalize a series into the range [0, 1]."""
    if not values:
        return []
    min_value = min(values)
    max_value = max(values)
    if math.isclose(min_value, max_value):
        return [0.5 for _ in values]
    span = max_value - min_value
    return [(value - min_value) / span for value in values]


def _prepare_track_metrics(
    tracks: list[Track],
) -> list[tuple[Track, float, float, float]]:
    """Return tuples of (track, combined_score, normalized_bpm, normalized_energy)."""
    bpm_values = [track.bpm for track in tracks]
    energy_values = [track.energy for track in tracks]
    normalized_bpm = _normalize_series(bpm_values)
    normalized_energy = _normalize_series(energy_values)

    metrics: list[tuple[Track, float, float, float]] = []
    for track, norm_bpm, norm_energy in zip(tracks, normalized_bpm, normalized_energy):
        combined_score = 0.45 * norm_bpm + 0.55 * norm_energy
        metrics.append((track, combined_score, norm_bpm, norm_energy))
    return metrics


# Energy Wave waehlt innerhalb der naechsten ENERGY_WAVE_FENSTER Kandidaten
# einer Seite nach BPM-Naehe. 1 waere exakt das alte Verhalten (immer der
# zentrumsnaechste), unendlich waere freie Wahl ueber die ganze Seite.
#
# Der Wert ist eine Abwaegung zwischen zwei Zielen der Strategie, gemessen an
# den ersten 80 Tracks des Cache-Stands v32 (93-146 BPM). Am spaeteren Stand
# v33 ergibt dasselbe Fenster 28 % unmixbar bei Amplitude 0.742 — andere
# Trackauswahl, gleiche Richtung:
#
#   Fenster   unmixbare Nachbarpaare   Amplitudenaufbau
#         1            63 %                  0.819   (= altes Verhalten)
#         2            49 %                  0.773
#         5            41 %                  0.740
#         8            23 %                  0.599
#      frei            14 %                 -0.071   (Aufbau vollstaendig weg)
#
# "Unmixbar" heisst overall_score == 0 wegen des BPM-Hard-Gates.
# "Amplitudenaufbau" ist die Korrelation zwischen Position und Abstand zur
# Startenergie: die Welle soll vom Zentrum aus immer weiter ausschlagen.
# Freie Wahl macht die Uebergaenge am besten mixbar, zerstoert aber genau
# diese Dramaturgie — deshalb das Fenster statt freier Wahl.
ENERGY_WAVE_FENSTER = 8


def _sort_energy_wave(
    tracks: list[Track], bpm_tolerance: float, **kwargs
) -> list[Track]:
    """Wellenfoermige Reise: abwechselnd hoehere und niedrigere Energie,
    vom Zentrum aus mit wachsendem Ausschlag.

    Die Reihenfolge der Seiten und der wachsende Ausschlag sind unveraendert.
    Neu ist nur die AUSWAHL innerhalb einer Seite: statt immer den
    zentrumsnaechsten Track zu nehmen, wird unter den naechsten
    ENERGY_WAVE_FENSTER Kandidaten der mit der kleinsten effektiven
    BPM-Differenz zum zuletzt gesetzten Track gewaehlt.

    Anlass: die Strategie nahm `bpm_tolerance` entgegen und benutzte sie nie.
    Gemessen an 80 Tracks mit 93-146 BPM waren dadurch 63 % der Nachbarpaare
    unmixbar (Median-BPM-Differenz 10,0) — zum Vergleich liegen Harmonic
    Flow, Warm-Up, Cool-Down und Consistent bei 2-5 %. Bei einem engen Pool
    (137-141 BPM) trat das Problem nicht auf; es trifft, wer die Strategie
    auf einen gemischten Bestand anwendet.

    Kein Hard-Gate, sondern eine Praeferenz: es wird immer der BPM-naechste
    Kandidat des Fensters genommen, ohne Schwellenvergleich. Ein Gate wuerde
    die Welle abbrechen lassen, sobald eine Seite erschoepft ist, und die
    Strategie hat keine Zielfunktion, auf die sie ausweichen koennte.
    `bpm_tolerance` bleibt deshalb ungenutzt — die Naehe entscheidet.
    """
    cancel_check = kwargs.get("cancel_check")
    _check_cancel(cancel_check)
    if not tracks:
        return []

    ordered_by_energy = sorted(tracks, key=lambda track: track.energy)
    count = len(ordered_by_energy)
    if count <= 2:
        return ordered_by_energy

    center_index = (count - 1) // 2
    result: list[Track] = [ordered_by_energy[center_index]]

    # Zentrumsnaechster Kandidat steht in beiden Listen vorne
    nach_unten = list(reversed(ordered_by_energy[:center_index]))
    nach_oben = ordered_by_energy[center_index + 1:]
    take_high = True

    while nach_unten or nach_oben:
        _check_cancel(cancel_check)
        seite = nach_oben if (take_high and nach_oben) else (
            nach_unten if nach_unten else nach_oben
        )
        if not seite:
            break
        aktuell = result[-1]
        grenze = min(len(seite), max(1, ENERGY_WAVE_FENSTER))
        # Ueber den INDEX waehlen, nicht ueber den Wert: Track vergleicht
        # sich ueber `track_id`, also den normalisierten Dateipfad
        # (models.py, `__eq__`). Zwei Objekte mit demselben Pfad sind gleich,
        # unabhaengig von BPM und Energie. `list.remove(track)` entfernte
        # deshalb den erstbesten Treffer statt des gewaehlten — im Test mit
        # der Fixture `make_track`, die allen Tracks denselben Default-Pfad
        # gibt, verschwanden dadurch Tracks aus der Playlist.
        #
        # Tie-Break bewusst gegen den ZULETZT GESETZTEN Track, nicht gegen das
        # Zentrum: bei gleicher BPM-Naehe gewinnt der sanftere Energiesprung.
        index = min(
            range(grenze),
            key=lambda i: (
                effective_bpm_diff(aktuell.bpm, seite[i].bpm)[0],
                abs(seite[i].energy - aktuell.energy),
            ),
        )
        result.append(seite.pop(index))
        take_high = not take_high

    return result


def _sort_peak_time(
    tracks: list[Track], bpm_tolerance: float, **kwargs
) -> list[Track]:
    """Enhanced peak-time arrangement with harmonic considerations and multiple peaks."""
    cancel_check = kwargs.get("cancel_check")
    _check_cancel(cancel_check)
    if not tracks:
        return []

    peak_position = kwargs.get("peak_position", 70) / 100.0
    if len(tracks) <= 3:
        combined_by_track = {
            id(track): combined
            for track, combined, _norm_bpm, _norm_energy
            in _prepare_track_metrics(tracks)
        }
        peak_curve = _peak_time_curve(len(tracks), peak_position)

        def small_score(order) -> tuple:
            valid, transition_score = _transition_path_score(
                order, bpm_tolerance, kwargs
            )
            curve_fit = -sum(
                abs(combined_by_track[id(track)] - peak_curve[index])
                for index, track in enumerate(order)
            )
            return valid, curve_fit, transition_score

        return _small_pool_order(tracks, small_score, cancel_check)

    scored_tracks = _prepare_track_metrics(tracks)
    count = len(scored_tracks)

    # Create a double-peak curve for longer sets
    peak_curve = _peak_time_curve(count, peak_position)

    # Sort tracks by curve position preference
    waveform_positions = sorted(range(count), key=lambda idx: peak_curve[idx])

    # Assign tracks to positions with harmonic consideration
    ordered_tracks: list[Optional[Track]] = [None] * count

    # Audit-Fix 2026-07-21: Tracks nach combined_score (Energie+BPM) sortieren,
    # BEVOR sie auf die Peak-Kurve gelegt werden. Vorher lief die Zuweisung ueber
    # den Eingabe-Index -> die Peak-Dramaturgie (ruhige Tracks an Start/Ende,
    # energiereiche am Peak) entstand nie und das Ergebnis haing an der Ladereihenfolge.
    scored_by_energy = sorted(scored_tracks, key=lambda item: item[1])

    for track_idx in zip(scored_by_energy, waveform_positions):
        _check_cancel(cancel_check)
        track, score, norm_bpm, norm_energy = track_idx[0]
        position = track_idx[1]

        if position < len(ordered_tracks):
            ordered_tracks[position] = track

    # Apply harmonic smoothing pass
    result = [track for track in ordered_tracks if track is not None]
    return _apply_harmonic_smoothing(result, bpm_tolerance, **kwargs)


def _peak_time_curve(count: int, peak_position: float) -> list[float]:
    """Eine gemeinsame Peak-Kurve fuer normale und exhaustive kleine Pools."""
    curve = []
    for idx in range(count):
        if idx < count * peak_position:
            curve.append((idx / (count * peak_position)) ** 1.5)
        else:
            decline_progress = (idx - count * peak_position) / (
                count * (1 - peak_position)
            )
            curve.append(1.0 - decline_progress**0.7)
    return curve


def _apply_harmonic_smoothing(
    tracks: list[Track], bpm_tolerance: float, **kwargs
) -> list[Track]:
    """Apply local swaps to improve harmonic flow while preserving energy curve.

    Optimized: Max 3 iterations (was len/2) - most improvements happen in first 2-3 passes.
    """
    cancel_check = kwargs.get("cancel_check")
    _check_cancel(cancel_check)
    if len(tracks) <= 2:
        return tracks

    result = list(tracks)
    improved = True
    iterations = 0
    max_iterations = SMOOTHING_MAX_ITERATIONS

    while improved and iterations < max_iterations:
        _check_cancel(cancel_check)
        improved = False
        iterations += 1

        for i in range(len(result) - 1):
            _check_cancel(cancel_check)
            current_score = calculate_transition_objective(
                result[i], result[i + 1], bpm_tolerance, **kwargs
            )

            # Try swapping with next track if it improves harmony
            if i + 2 < len(result):
                swap_score = calculate_transition_objective(
                    result[i], result[i + 2], bpm_tolerance, **kwargs
                )
                next_swap_score = calculate_transition_objective(
                    result[i + 1], result[i + 2], bpm_tolerance, **kwargs
                )
                # Calculate what score would be AFTER swap: [i]->[i+1] becomes [i]->[i+2], [i+2]->[i+1]
                new_pair_score = calculate_transition_objective(
                    result[i + 2], result[i + 1], bpm_tolerance, **kwargs
                )

                # AUDIT-FIX F08 (2026-07-24): Auch die ANSCHLUSS-Transition
                # bewerten. Der Swap [i+1]<->[i+2] veraendert DREI Uebergaenge;
                # vorher fehlte [i+2]->[i+3] (vorher) bzw. [i+1]->[i+3] (nachher)
                # auf beiden Seiten der Ungleichung — dadurch verschlechterte
                # ein lokal "besserer" Tausch nachweislich die Gesamtkette.
                tail_before = 0
                tail_after = 0
                if i + 3 < len(result):
                    tail_before = calculate_transition_objective(
                        result[i + 2], result[i + 3], bpm_tolerance, **kwargs
                    )
                    tail_after = calculate_transition_objective(
                        result[i + 1], result[i + 3], bpm_tolerance, **kwargs
                    )

                # Compare: Summe der betroffenen Uebergaenge vorher vs. nachher
                before_sum = current_score + next_swap_score + tail_before
                after_sum = swap_score + new_pair_score + tail_after
                if after_sum > before_sum:
                    # Only swap if energy curve isn't severely disrupted
                    energy_disruption = abs(result[i].energy - result[i + 2].energy)
                    if energy_disruption < SMOOTHING_ENERGY_DISRUPTION_MAX:
                        result[i + 1], result[i + 2] = result[i + 2], result[i + 1]
                        improved = True

    return result


def _sort_genre_flow(
    tracks: list[Track], bpm_tolerance: float, **kwargs
) -> list[Track]:
    """Arrange tracks to create smooth genre transitions while maintaining energy."""
    cancel_check = kwargs.get("cancel_check")
    _check_cancel(cancel_check)
    # Get genre parameters
    genre_mixing_enabled = kwargs.get("genre_mixing", True)
    genre_weight = kwargs.get("genre_weight", 0.3)  # 0.0-1.0

    if len(tracks) <= 2:
        # For 2 oder weniger Tracks wird die Richtung per Vergleich der
        # paarweisen Verträglichkeit eindeutig aufgelöst. ``_sort_harmonic_flow``
        # ist für kleine Pools zu passiv und würde bei [B, A] die Reihenfolge
        # nicht stabil in Richtung des erwarteten Contracts ändern.
        def small_score(order) -> tuple:
            harmonic_scores = [
                calculate_compatibility(a, b, bpm_tolerance, **kwargs)
                for a, b in zip(order, order[1:])
            ]
            if not genre_mixing_enabled:
                blended_scores = [
                    harmonic / 100.0 for harmonic in harmonic_scores
                ]
            else:
                blended_scores = [
                    (1.0 - genre_weight) * harmonic / 100.0
                    + genre_weight * get_genre_compatibility(
                        _resolve_track_genre(a), _resolve_track_genre(b)
                    )
                    for (a, b), harmonic in zip(
                        zip(order, order[1:]), harmonic_scores
                    )
                ]
            return (
                sum(score > 0 for score in harmonic_scores),
                sum(blended_scores),
                sum(harmonic_scores),
            )

        return _small_pool_order(tracks, small_score, cancel_check)

    # Group tracks by genre (bevorzuge eine echte Klassifikation, sonst ID3)
    genre_groups = {}
    for track in tracks:
        _check_cancel(cancel_check)
        genre = _resolve_track_genre(track)
        if genre == "Unknown":
            genre = "Mixed"
        if genre not in genre_groups:
            genre_groups[genre] = []
        genre_groups[genre].append(track)

    # Audit-Fix 2026-07-17 (Runde 2): die frühere lokale Fallback-Tabelle
    # (base_genre_compatibility) war ein zweites, teils widersprüchliches
    # Duplikat der DJ-Brain-Matrix — entfernt. Einzige Quelle ist jetzt
    # get_genre_compatibility (dj_brain), skaliert mit genre_weight.

    # Create transitions between genres
    result = []
    processed_genres = set()

    # Start with the genre that has the most tracks
    current_genre = max(genre_groups.keys(), key=lambda g: len(genre_groups[g]))

    while len(processed_genres) < len(genre_groups):
        _check_cancel(cancel_check)
        if current_genre in genre_groups and current_genre not in processed_genres:
            # Arrange tracks within current genre (pass kwargs for harmonic params)
            genre_tracks = _sort_consistent(
                genre_groups[current_genre], bpm_tolerance, **kwargs
            )
            result.extend(genre_tracks)
            processed_genres.add(current_genre)

        # Find best next genre
        best_next_genre = None
        best_compatibility = 0

        for genre in genre_groups:
            _check_cancel(cancel_check)
            if genre not in processed_genres:
                # genre_weight blendet zwischen dem besten realen Uebergang
                # in die Gruppe (0 = Genre ignorieren) und der DJ-Brain-Matrix
                # (1 = Genre ist ausschlaggebend). Die fruehere affine Formel
                # war fuer alle Gewichte < 1 streng monoton und konnte deshalb
                # die Rangfolge niemals veraendern.
                dj_compat = get_genre_compatibility(current_genre, genre)
                current_track = result[-1]
                transition_compat = 0
                for candidate in genre_groups[genre]:
                    _check_cancel(cancel_check)
                    transition_compat = max(
                        transition_compat,
                        calculate_compatibility(
                            current_track, candidate, bpm_tolerance, **kwargs
                        ),
                    )
                transition_compat /= 100.0
                compatibility = (
                    (1.0 - genre_weight) * transition_compat
                    + genre_weight * dj_compat
                )
                if compatibility > best_compatibility:
                    best_compatibility = compatibility
                    best_next_genre = genre

        if best_next_genre:
            current_genre = best_next_genre
        else:
            # If no compatible genre found, pick any remaining genre.
            # sorted() statt list(set(...)): Set-Iteration haengt vom
            # PYTHONHASHSEED ab -> sonst nichtdeterministische Playlist-Reihenfolge
            # ueber Programmlaeufe hinweg bei identischem Track-Pool.
            remaining_genres = set(genre_groups.keys()) - processed_genres
            if remaining_genres:
                current_genre = sorted(remaining_genres)[0]
            else:
                break  # All genres processed

    return result


def _sort_consistent(
    tracks: list[Track], bpm_tolerance: float, **kwargs
) -> list[Track]:
    """Keep transitions smooth by minimising BPM/Energy jumps while preferring harmonic compatibility."""
    cancel_check = kwargs.get("cancel_check")
    _check_cancel(cancel_check)
    if not tracks:
        return []

    # Capture kwargs for nested function
    compat_kwargs = kwargs

    remaining = list(tracks)
    average_bpm = sum(getattr(track, "bpm", 0.0) for track in remaining) / len(
        remaining
    )
    average_energy = sum(getattr(track, "energy", 0) for track in remaining) / len(
        remaining
    )

    def _center_distance(track: Track) -> float:
        bpm_deviation = effective_bpm_diff(
            getattr(track, "bpm", average_bpm), average_bpm
        )[0]
        energy_deviation = (
            abs(getattr(track, "energy", average_energy) - average_energy) / 5.0
        )
        return bpm_deviation + energy_deviation

    current = min(remaining, key=_center_distance)
    playlist = [current]
    _remove_track(remaining, current)

    while remaining:
        _check_cancel(cancel_check)

        def _transition_cost(candidate: Track) -> float:
            bpm_delta, _ = effective_bpm_diff(
                getattr(candidate, "bpm", current.bpm), getattr(current, "bpm", 0.0)
            )
            energy_delta = (
                abs(
                    getattr(candidate, "energy", current.energy)
                    - getattr(current, "energy", 0)
                )
                / 5.0
            )
            compatibility = calculate_transition_objective(
                current, candidate, bpm_tolerance, **compat_kwargs
            )
            compatibility_penalty = (100 - compatibility) / 8.0
            if compatibility == 0:
                compatibility_penalty += 10.0
            return bpm_delta + energy_delta + compatibility_penalty

        next_track = min(remaining, key=_transition_cost)
        playlist.append(next_track)
        _remove_track(remaining, next_track)
        current = next_track

    return playlist


def _resolve_mix_points(track: Track, fallback_overlap: float) -> tuple[float, float]:
    """Ensure mix-in/out points are usable, applying sensible fallbacks."""
    duration = max(track.duration, 0.0)

    if track.mix_in_point >= 0:
        mix_in_point = track.mix_in_point
    elif duration > 0:
        mix_in_point = min(duration * 0.1, max(4.0, fallback_overlap / 2))
    else:
        mix_in_point = max(0.0, fallback_overlap / 2)

    if track.mix_out_point >= 0:
        mix_out_point = track.mix_out_point
    elif duration > 0:
        mix_out_point = max(
            mix_in_point + 4.0, duration - min(duration * 0.05, fallback_overlap)
        )
    else:
        mix_out_point = mix_in_point + max(4.0, fallback_overlap / 2)

    if duration > 0:
        mix_in_point = max(0.0, min(mix_in_point, duration))
        # M4-Fix: aeusseres min(duration, ...) — der mix_in_point + 1.0 im max()
        # konnte mix_out sonst ueber die Track-Dauer heben (Invariante
        # mix_out <= duration verletzt -> _load_segment seekt hinter Dateiende).
        mix_out_point = min(duration, max(mix_in_point + 1.0, min(mix_out_point, duration)))
        # Bei winziger Restdauer mix_in zuruecknehmen, damit mix_in < mix_out bleibt.
        if mix_in_point >= mix_out_point:
            mix_in_point = max(0.0, mix_out_point - 1.0)

    return mix_in_point, mix_out_point


def _clamp_transition_overlap(
    overlap: float,
    current: Track,
    upcoming: Track,
    current_mix_out: float,
    next_mix_in: float,
    limit_to_windows: bool = True,
) -> float:
    """Begrenzt den Overlap auf das real vorhandene Audio beider Tracks.

    Vertrag mit dem Renderer (TransitionClipSpec.from_plan): waehrend des
    Crossfades laeuft A ab ``mix_out_a`` und B ab ``mix_in_b`` — beide also
    VORWAERTS ab ihrem Mixpunkt. Nutzbar ist damit die Restdauer hinter dem
    jeweiligen Mixpunkt.

    AUDIT-FIX 2026-08-14: Die B-Seite begrenzte vorher auf
    ``intro_end_B - mix_in_b``. dj_brain garantiert per Design
    ``mix_in_b > intro_end_B`` (siehe tests/test_dj_brain.py), dieser Term
    war also immer <= 0 — gemessen an 52 echten Tracks wurden 50 von 51
    Uebergaengen auf overlap=0.0 geklemmt (Mittel 0.67 s statt 37 s), der
    Renderer bekam faktisch ueberall harte Schnitte und der overlap-Parameter
    blieb wirkungslos. Korrekt ist die Restdauer von B hinter dem Mix-In.

    Dritte Fenstergrenze (2026-08-21): die Blende endet spaetestens am
    Outro-Beginn von A, siehe `_outro_overlap_limit`. Sie gilt bewusst nur
    unter ``limit_to_windows`` — der Zweig ohne Fensterlogik bedient alte
    externe Recommendation-Shims, die keine belastbaren Sektionen mitbringen,
    und behaelt den reinen 64-s-Deckel.
    """
    limits = [float(MAX_TRANSITION_OVERLAP_SECONDS)]
    if limit_to_windows:
        if current.duration > 0:
            limits.append(max(0.0, float(current.duration) - current_mix_out))
        if upcoming.duration > 0:
            limits.append(max(0.0, float(upcoming.duration) - next_mix_in))
        outro_limit = _outro_overlap_limit(current, current_mix_out)
        if outro_limit is not None:
            limits.append(outro_limit)
    return max(0.0, min(float(overlap), *limits))


def _outro_overlap_limit(
    current: Track, current_mix_out: float
) -> Optional[float]:
    """Laenge, die A hinter dem Mix-Out noch traegt — bis sein Outro beginnt.

    Warum: der Mix-Out selbst liegt per Outro-Guard (dj_brain) immer VOR dem
    Outro, die Blende laeuft aber vorwaerts ab diesem Punkt
    (transition_renderer.py:159-160, 322-324) und damit ueber die Grenze
    hinaus. Gemessen an 160 gerenderten Uebergaengen lief die Blende in 109
    Faellen ins Outro von A, im Median 17.3 s, im schlimmsten Fall 48.5 s —
    A duennt aus, waehrend er noch tragen soll.

    Die Laenge kommt damit aus dem Material dieses Tracks statt aus dem
    Genre-Mittel: gemessen ueber dieselben Uebergaenge liegt der Kopfraum im
    Median bei 34.4 s (Psytrance 54.9 s) und streut von 0 bis 105 s.
    Abgerundet wird auf ganze TAKTE, nicht auf Phrasen: Phrasen-Rundung warf
    die Streuung wieder weg (simuliert: 49 von 120 Psy-Clips auf demselben
    Wert), ganze Takte halten den Ausstieg trotzdem auf der Taktgrenze.

    Rueckgabe None heisst "keine Grenze": kein erkanntes Outro, unbrauchbare
    Werte, oder ein Kopfraum unter MIN_TRANSITION_BARS. Der letzte Fall ist
    Absicht — dort waere die Alternative ein harter Schnitt.
    """
    sections = getattr(current, "sections", None)
    duration = float(getattr(current, "duration", 0.0) or 0.0)
    bpm = float(getattr(current, "bpm", 0.0) or 0.0)
    if not sections or duration <= 0 or bpm <= 0:
        return None

    outro_start = _get_outro_start_from_sections(sections, duration)
    # Kein Outro erkannt: die Funktion gibt dann die Trackdauer zurueck.
    if outro_start >= duration:
        return None

    headroom = outro_start - float(current_mix_out)
    seconds_per_bar = (60.0 / bpm) * METER
    if seconds_per_bar <= 0:
        return None
    # Gitter-Toleranz (Teil 1 rundet Mixpunkte auf 3 Dezimalen; Kandidaten-
    # Blenden sind mit derselben Toleranz auf ganze Takte geklemmt): ohne sie
    # kostete ein 1-ms-Rundungsrest einen ganzen Takt Blende (gemessen
    # 2026-08-22: 12 von 220 Paaren). Dieselbe Fehlerklasse wie der
    # 3-ms-Phrasenfehler in models.quantize_to_grid.
    headroom += QUANTIZE_TOLERANCE_SEC
    if headroom < MIN_TRANSITION_BARS * seconds_per_bar:
        return None
    return (headroom // seconds_per_bar) * seconds_per_bar


def _handoff_pair_point_risks(
    dj_rec: Optional["DJRecommendation"],
    current: Track,
    upcoming: Track,
    current_mix_out: float,
    next_mix_in: float,
    notes_parts: list[str],
) -> list[str]:
    """Bewertet Bass-Risiken an den paarspezifischen statt Track-Default-Punkten.

    NICHT ENTFERNEN, auch wenn es nach Dopplung aussieht. Seit dj_brain die
    Risiken selbst an den Paar-Punkten bewertet (Audit 2026-08-14, N2), sind die
    erzeugten `risk_notes` tatsaechlich identisch — gemessen 0 Abweichungen ueber
    51 reale Uebergaenge. Diese Funktion ist aber die EINZIGE Stelle, die die
    Kollisionswarnung zusaetzlich in den nutzersichtbaren Notiztext (`notes_parts`,
    mit "! "-Praefix) hebt. Ohne sie fehlt die Warnung in der Anzeige — gemessen
    bei 43 von 51 Uebergaengen.
    """
    if dj_rec is None:
        return notes_parts

    def _section_value(track: Track, point: float, field: str) -> float:
        for section in getattr(track, "sections", None) or []:
            if isinstance(section, dict):
                start = section.get("start_time")
                end = section.get("end_time")
                value = section.get(field)
            else:
                start = getattr(section, "start_time", None)
                end = getattr(section, "end_time", None)
                value = getattr(section, field, None)
            if start is not None and end is not None and start <= point <= end:
                if value is not None:
                    return float(value)
        return float(getattr(track, field, 0.0))

    bass_a = _section_value(current, current_mix_out, "avg_bass")
    bass_b = _section_value(upcoming, next_mix_in, "avg_bass")
    risk_notes = list(getattr(dj_rec, "risk_notes", None) or [])
    risk_notes = [
        note for note in risk_notes if not note.startswith("Bass-Kollision droht!")
    ]
    if bass_a > 60 and bass_b > 60:
        risk_notes.append(
            f"Bass-Kollision droht! (A:{bass_a:.0f}%, B:{bass_b:.0f}%) -- Bass von Track A hart cutten"
        )
    dj_rec.risk_notes = risk_notes

    notes_parts = [
        note for note in notes_parts if "Bass-Kollision droht!" not in note
    ]
    collision = next(
        (note for note in risk_notes if note.startswith("Bass-Kollision droht!")),
        None,
    )
    if collision:
        notes_parts.append(f"! {collision}")
    return notes_parts


def _categorise_risk_level(
    compatibility_score: int, bpm_delta: float, bpm_tolerance: float, energy_delta: int
) -> str:
    """Convert compatibility metrics into a qualitative risk label."""
    if abs(bpm_delta) > bpm_tolerance or compatibility_score < 50:
        return "high"
    if compatibility_score >= 80 and abs(energy_delta) <= 20:
        return "low"
    if abs(energy_delta) > 35 and compatibility_score < 70:
        return "high"
    if compatibility_score >= 70:
        return "medium-low"
    return "medium"


def predict_transition_type(
    from_track: Track,
    to_track: Track,
    bpm_tolerance: float = 3.0,
    kandidat=None,
    **kwargs,
) -> str:
    """
    Sagt den optimalen Transition-Typ vorher basierend auf Track-Eigenschaften.

    Transition-Typen:
      - "smooth_blend": Langer EQ-Blend (beides harmonisch kompatibel, aehnliche Energie)
      - "bass_swap": Schneller Bass-Tausch (gleicher BPM-Bereich, aehnlicher Groove)
      - "breakdown_bridge": Transition ueber Breakdown (grosse BPM/Energie-Differenz)
      - "drop_cut": Harter Schnitt am Drop (Energie-Push, passende Tonart)
      - "filter_ride": Filter-basierter Uebergang (melodische Tracks, aehnliches BPM)
      - "halftime_switch": Half/Double-Time Wechsel (BPM-Verhaeltnis 2:1)
      - "echo_out": Echo/Delay-basierter Ausklang (schwierige Tonart-Kombi)
      - "cold_cut": Harter Cut ohne Blend (letzte Option bei Inkompatibilitaet)

    Returns:
      Einer der oben genannten Transition-Typen als String.
    """
    eff_diff, bpm_relation = effective_bpm_diff(from_track.bpm, to_track.bpm)
    lokales_energy_delta = _candidate_delta(kandidat, "energy_lokal")
    energy_delta = (
        lokales_energy_delta
        if lokales_energy_delta is not None
        else to_track.energy - from_track.energy
    )
    abs_energy_delta = abs(energy_delta)

    # Harmonic Compatibility pruefen — mit gewaehltem Scoring-Kontext (HPG-001):
    # der vorhergesagte Typ muss zum angezeigten Score passen, nicht zu Defaults.
    harmonic_score = (
        int(round(float(kandidat.teilwerte["harmonic"]) * 100))
        if kandidat is not None
        else calculate_compatibility(from_track, to_track, bpm_tolerance, **kwargs)
    )

    # Genre-Info
    genre_a = _resolve_track_genre(from_track)
    genre_b = _resolve_track_genre(to_track)

    # --- Regel 1: Half/Double-Time Wechsel ---
    if bpm_relation in ("half", "double") and eff_diff <= bpm_tolerance:
        return "halftime_switch"

    # --- Regel 2: BPM ausserhalb Toleranz ---
    if eff_diff > bpm_tolerance:
        # Die normale Kompatibilitaet ist hier wegen ihres BPM-Hard-Gates
        # definitionsgemaess 0. Fuer die Breakdown-Entscheidung die reine
        # Harmonie deshalb ohne dieses Gate bewerten.
        harmonic_without_bpm_gate = calculate_compatibility(
            from_track, to_track, float("inf"), **kwargs
        )
        if harmonic_without_bpm_gate >= 50:
            return "breakdown_bridge"
        return "cold_cut"

    # --- Regel 3: Grosser Energie-Push nach oben ---
    if energy_delta > 25 and harmonic_score >= 70:
        return "drop_cut"

    # --- Regel 4: Grosser Energie-Drop nach unten ---
    if energy_delta < -25:
        if harmonic_score >= 60:
            return "echo_out"
        return "breakdown_bridge"

    # --- Regel 5: Harmonisch perfekt + aehnliche Energie ---
    if harmonic_score >= 85 and abs_energy_delta <= 15 and eff_diff <= 2.0:
        # Melodische Genres bevorzugen Filter Rides
        melodic_genres = {"Melodic Techno", "Progressive", "Trance", "Deep House"}
        hard_genres = {"Tech House", "Techno", "Drum & Bass", "Minimal", "Psytrance"}
        pro_eq_genres = {"Tech House", "Techno", "Minimal", "Psytrance"}
        if genre_a in melodic_genres or genre_b in melodic_genres:
            return "filter_ride"
        if genre_a in pro_eq_genres or genre_b in pro_eq_genres:
            return "pro_eq_swap"
        if genre_a in hard_genres or genre_b in hard_genres:
            return "bass_swap"
        return "smooth_blend"

    # --- Regel 6: Gute Harmonie, BPM passt ---
    if harmonic_score >= 70 and eff_diff <= bpm_tolerance:
        # Harte Genres bevorzugen Bass Swap
        hard_genres = {"Tech House", "Techno", "Drum & Bass", "Minimal", "Psytrance"}
        pro_eq_genres = {"Tech House", "Techno", "Minimal", "Psytrance"}
        if genre_a in pro_eq_genres or genre_b in pro_eq_genres:
            return "pro_eq_swap"
        if genre_a in hard_genres or genre_b in hard_genres:
            return "bass_swap"
        return "smooth_blend"

    # --- Regel 7: Moderate Harmonie ---
    if harmonic_score >= 50:
        if abs_energy_delta > 15:
            return "breakdown_bridge"
        return "filter_ride"

    # --- Regel 8: Schlechte Harmonie ---
    if harmonic_score >= 30:
        return "echo_out"

    # --- Fallback: Inkompatibel ---
    return "cold_cut"


def transition_type_for_candidate(
    from_track: Track,
    to_track: Track,
    kandidat,
    bpm_tolerance: float = 3.0,
    scoring_context: Optional[Dict] = None,
) -> str:
    """Eine gemeinsame Typentscheidung fuer App und produktionsnahen Hoertest."""
    if kandidat is not None and kandidat.flags.get("bass_swap_pflicht"):
        return "bass_swap"
    return predict_transition_type(
        from_track,
        to_track,
        bpm_tolerance,
        kandidat=kandidat,
        **dict(scoring_context or {}),
    )


def _build_transition_description(
    params: TransitionDescriptionParams,
) -> str:
    """
    Erzeugt eine aussagekraeftige DJ-Beschreibung der Transition.
    Gibt konkrete, nuetzliche Infos fuer den DJ - keine generischen Phrasen.

    Wenn params.has_dj_brain=True, werden BPM- und Key-Details uebersprungen,
    weil der DJ Brain diese schon als Risk-Notes liefert.
    """
    parts: list[str] = []

    # --- 1. Harmonic Bewertung ---
    harmonic = params.metrics.harmonic_score
    key_a = getattr(params.from_track, "camelotCode", "") or ""
    key_b = getattr(params.to_track, "camelotCode", "") or ""
    key_info = f" ({key_a}->{key_b})" if key_a and key_b else ""

    if params.has_dj_brain:
        # DJ Brain liefert Key-Risks -- nur Kurzform mit Camelot-Codes
        if harmonic >= 90:
            parts.append(f"Perfekte Tonart{key_info}")
        elif harmonic >= 70:
            parts.append(f"Harmonisch{key_info}")
        # Bei schlechter Harmonie nichts: DJ Brain warnt schon
    else:
        # Kein DJ Brain -- vollstaendige Tonart-Bewertung
        if harmonic >= 90:
            parts.append(f"Perfekte Tonart{key_info}")
        elif harmonic >= 70:
            parts.append(f"Harmonisch kompatibel{key_info}")
        elif harmonic >= 50:
            parts.append(f"Tonart geht, kurz mixen{key_info}")
        else:
            parts.append(f"Tonart-Clash{key_info} -- EQ-Filter nutzen")

    # --- 2. BPM Situation ---
    # Ueberspringe wenn DJ Brain schon BPM-Risk liefert
    if not params.has_dj_brain:
        abs_bpm = abs(params.bpm_delta)
        if abs_bpm < 0.5:
            pass  # Perfektes BPM-Match braucht keinen Kommentar
        elif abs_bpm <= params.bpm_tolerance:
            parts.append(
                f"BPM-Anpassung {params.bpm_delta:+.1f} -- Pitch Fader korrigieren"
            )
        else:
            parts.append(
                f"BPM-Sprung {params.bpm_delta:+.1f} -- harter Cut oder Breakdown nutzen"
            )

    # --- 3. Energie-Verlauf (nur ohne DJ Brain -- DJ Brain liefert energy_advice) ---
    if not params.has_dj_brain:
        if params.energy_delta > 25:
            parts.append("Grosser Energie-Push [++] -- Drop-Einstieg ideal")
        elif params.energy_delta > 12:
            parts.append("Energie steigt [+] -- im Build reinmixen")
        elif params.energy_delta < -25:
            parts.append("Starker Energie-Drop [--] -- Breakdown-Uebergang planen")
        elif params.energy_delta < -12:
            parts.append("Energie faellt [-] -- im Outro sanft ueberblenden")
        else:
            parts.append("Energie stabil [=] -- nahtlose Ueberblendung moeglich")

    # --- 4. Gesamtbewertung als klarer Satz ---
    if params.compatibility_score >= 85:
        parts.append("Sichere Transition -- laeuft fast von allein")
    elif params.compatibility_score >= 70:
        parts.append("Solide Transition -- mit Aufmerksamkeit sauber mixbar")
    elif params.compatibility_score >= 55:
        parts.append("Machbar, aber anspruchsvoll -- Timing und EQ muessen stimmen")
    else:
        parts.append(
            "Riskante Transition -- nur fuer erfahrene DJs oder mit langem Breakdown"
        )

    return "; ".join(parts)


def _process_dj_brain_recommendations(
    current: Track,
    upcoming: Track,
) -> tuple["DJRecommendation | None", list[str], float | None]:
    """
    Processes DJ Brain recommendations and returns the updated transition details.

    Returns:
        tuple containing:
        - dj_rec: The DJRecommendation object if successful, else None
        - notes_parts: Additional notes from the DJ Brain
        - overlap: Adjusted overlap if DJ Brain provided transition bars
    """
    dj_rec = None
    notes_parts = []
    overlap = None

    current_genre = _resolve_track_genre(current)
    upcoming_genre = _resolve_track_genre(upcoming)
    has_dj_data = current_genre != "Unknown" and upcoming_genre != "Unknown"

    if has_dj_data:
        try:
            dj_rec = generate_dj_recommendation(current, upcoming)
            if dj_rec.mix_technique:
                notes_parts.append(f"Mix: {dj_rec.mix_technique}")
            if dj_rec.eq_advice:
                notes_parts.append(f"EQ: {dj_rec.eq_advice}")
            if dj_rec.transition_bars > 0:
                notes_parts.append(f"Transition: {dj_rec.transition_bars} bars")
            # Nur anzeigen wenn echte Struktur-Daten vorhanden
            if dj_rec.structure_note:
                notes_parts.append(dj_rec.structure_note)
            if dj_rec.genre_pair:
                notes_parts.append(f"[{dj_rec.genre_pair}]")
            for risk in dj_rec.risk_notes:
                notes_parts.append(f"! {risk}")
            # Konkrete Track-Empfehlungen mit echten Messwerten
            if dj_rec.bpm_advice:
                notes_parts.append(f"BPM: {dj_rec.bpm_advice}")
            if dj_rec.key_advice:
                notes_parts.append(f"Key: {dj_rec.key_advice}")
            if dj_rec.energy_advice:
                notes_parts.append(f"Energy: {dj_rec.energy_advice}")
            if getattr(dj_rec, "gain_advice", ""):
                notes_parts.append(f"Gain: {dj_rec.gain_advice}")
            # rhythm_advice wurde in dj_brain.py:537-544 berechnet und
            # gesetzt, aber nie in die Notes uebernommen — das einzige
            # GESETZTE advice-Feld, das fehlte (bass_match_advice fehlt auch,
            # wird aber nirgends befuellt). Landet in der GUI wie "Gain:" in
            # der grauen Meta-Zeile (main.py else-Zweig nach der
            # Schluesselwortliste), nicht im DJ-Brain-Block; die Praefixliste
            # dort anzufassen waere eine GUI-Aenderung.
            if getattr(dj_rec, "rhythm_advice", ""):
                notes_parts.append(f"Rhythmus: {dj_rec.rhythm_advice}")

            # DJ Brain Transition-Laenge uebernehmen
            if dj_rec.transition_bars > 0 and current.bpm > 0:
                seconds_per_bar = (60.0 / current.bpm) * METER
                overlap = seconds_per_bar * dj_rec.transition_bars
        except ValueError:
            raise
        except Exception as e:
            logger.warning(f"DJ-Brain Transition-Verarbeitung fehlgeschlagen: {e}")
            # Fallback auf Standard-Notes

    return dj_rec, notes_parts, overlap


def compute_adjacent_transition_metrics(
    playlist: List[Track],
    bpm_tolerance: float = 3.0,
    scoring_context: Optional[Dict] = None,
) -> List[TransitionMetrics]:
    """Berechnet alle sichtbaren Werte aus der wirklich aktiven lokalen Kette."""
    ctx = dict(scoring_context or {})
    if "overlap" in ctx:
        raise ValueError(
            "scoring_context enthaelt unbekannten Schluessel: 'overlap'"
        )
    if len(playlist) < 2:
        return []
    energy_direction = ctx.get("energy_direction")
    kandidaten_je_paar = [
        _kandidaten_fuer_paar(
            playlist[index], playlist[index + 1], bpm_tolerance,
            energy_direction, ctx
        )
        for index in range(len(playlist) - 1)
    ]
    aktive_kette = _kette_waehlen(kandidaten_je_paar, playlist)
    return [
        _calculate_track_edge_metrics(
            playlist[index],
            playlist[index + 1],
            bpm_tolerance,
            energy_direction,
            ctx,
            kandidat,
        )
        for index, (kandidat, _konsistent) in enumerate(aktive_kette)
    ]


def _kette_waehlen(kandidaten_je_paar: list, playlist: List[Track]) -> list:
    """Legacy-Sicht auf denselben V6-DP, ohne numerischen Wahl-Bonus."""
    from .pair_candidates import CandidateSnapshot

    run_id = "legacy-chain"
    occurrences = tuple(
        TrackOccurrence(run_id=run_id, ordinal=index, track=track)
        for index, track in enumerate(playlist)
    )
    snapshots_by_boundary = tuple(
        tuple(
            CandidateSnapshot.from_pair_candidate(candidate, original_ordinal=ordinal)
            for ordinal, candidate in enumerate(candidates[:12])
        )
        for candidates in kandidaten_je_paar
    )
    selected, consistencies, _checks, _passed, _states = _select_snapshot_path(
        snapshots_by_boundary, occurrences
    )
    result = []
    for index, snapshot in enumerate(selected):
        if snapshot is None:
            result.append((None, False))
            continue
        mutable = next(
            candidate
            for ordinal, candidate in enumerate(kandidaten_je_paar[index][:12])
            if ordinal == snapshot.original_ordinal
        )
        result.append((mutable, consistencies[index]))
    return result


def compute_transition_recommendations(
    playlist: List[Track],
    bpm_tolerance: float = PAAR_BPM_MAX,
    default_overlap: float = 12.0,
    scoring_context: Optional[Dict] = None,
    transition_metrics: Optional[List[TransitionMetrics]] = None,
) -> List[TransitionRecommendation]:
    """Build actionable mix recommendations between consecutive tracks.

    scoring_context (HPG-001): die bei der Generierung gewaehlten
    Scoring-Parameter (harmonic_strictness/allow_experimental). Ohne Kontext
    faellt die Bewertung auf die Defaults zurueck — dann muessen aber auch
    Sortierung und Anzeige denselben Default nutzen.
    """
    ctx = dict(scoring_context or {})
    if "overlap" in ctx:
        raise ValueError(
            "scoring_context enthaelt unbekannten Schluessel: 'overlap'"
        )
    if len(playlist) < 2:
        return []
    metrics_by_pair = (
        list(transition_metrics)
        if transition_metrics is not None
        else compute_adjacent_transition_metrics(playlist, bpm_tolerance, ctx)
    )
    if len(metrics_by_pair) != len(playlist) - 1:
        raise ValueError("transition_metrics muss genau ein Element pro Nachbarpaar enthalten")
    configured_overlap = default_overlap
    try:
        configured_overlap = float(configured_overlap)
    except (TypeError, ValueError):
        configured_overlap = float(default_overlap)
    configured_overlap = max(4.0, min(64.0, configured_overlap))

    recommendations: List[TransitionRecommendation] = []
    # Kandidatenpfad (Spec 2026-08-21 Abschnitt 4): erst je Paar die Kandidaten
    # holen (Cache), dann ueber die ganze Playlist konsistent waehlen — Mix-Out
    # von Track i muss hinter seinem Mix-In aus dem vorigen Paar liegen
    # (Invariante 1/3 je Track); Einzelpaar-Rang-1 wuerde das in ~1/3 der
    # Paare verletzen (gemessen 2026-08-22, 231 Tracks).
    kandidaten_je_paar = [
        _kandidaten_fuer_paar(
            playlist[i], playlist[i + 1], bpm_tolerance,
            ctx.get("energy_direction"), ctx
        )
        if getattr(metrics_by_pair[i], "kandidat", None) is not None else []
        for i in range(len(playlist) - 1)
    ]
    kette = _kette_waehlen(kandidaten_je_paar, playlist)

    for index in range(len(playlist) - 1):
        current = playlist[index]
        upcoming = playlist[index + 1]
        metrics = metrics_by_pair[index]
        kandidaten = kandidaten_je_paar[index]
        if (metrics.overall_score <= 0.0 or metrics.kandidat is None
                or not kandidaten):
            logger.warning(
                "Uebergang %s ohne vollstaendig qualifizierten lokalen Kandidaten verworfen",
                index,
            )
            continue

        effective_overlap = configured_overlap
        if current.duration > 0 and upcoming.duration > 0:
            effective_overlap = min(
                configured_overlap,
                max(6.0, min(current.duration, upcoming.duration) * 0.2),
            )

        current_mix_in, current_mix_out = _resolve_mix_points(
            current, effective_overlap
        )
        next_mix_in, _ = _resolve_mix_points(upcoming, effective_overlap)

        # DJ Logic: The mix usually starts at the 'mix_in' of the upcoming track
        # and ends at the 'mix_out' of the current track.
        # We want to align the 'mix_in' of the next track with a phrase in the current track.

        # Calculate how long the transition should be (e.g., 16 or 32 bars)
        seconds_per_beat = 60.0 / current.bpm if current.bpm > 0 else 60.0 / DEFAULT_BPM
        seconds_per_bar = seconds_per_beat * METER

        # Fallback-Overlap kommt aus dem API-/Strategie-Kontext. Bei DJ-Brain-
        # Daten wird er spaeter genau einmal durch transition_bars ersetzt.
        transition_duration = effective_overlap

        # Die Blende laeuft VORWAERTS ab dem Mix-Out — genauso rendert sie der
        # Renderer (transition_renderer.py:159-160: a_start = mix_out - pre_roll,
        # a_dur = pre_roll + cf_sec; :322-324: a_cf = seg_a[pre_frames:]).
        # Fix 2026-08-21: hier stand `current_mix_out - transition_duration`,
        # also die Rueckwaerts-Konvention. Plan und Anzeige lagen damit um die
        # volle Blendenlaenge neben dem, was tatsaechlich klang; in der GUI
        # endete die Blende scheinbar am Mix-Out und lief nie ins Outro.
        fade_out_start = current_mix_out
        fade_in_start = next_mix_in
        overlap = transition_duration

        compatibility_score = int(round(metrics.overall_score * 100))

        energy_delta = int(round(float(metrics.energy_delta or 0.0)))
        eff_bpm_diff, _ = effective_bpm_diff(current.bpm, upcoming.bpm)
        # Vorzeichen-behaftetes Delta fuer Anzeige (positiv = schneller)
        bpm_delta = upcoming.bpm - current.bpm
        # Fuer Risikobewertung effektive Differenz nutzen (L1-Fix: toter
        # Ternary entfernt — beide Zweige waren identisch)
        risk_bpm_delta = eff_bpm_diff

        risk_level = _categorise_risk_level(
            compatibility_score, risk_bpm_delta, bpm_tolerance, energy_delta
        )

        notes_parts = []

        # DJ Brain Empfehlungen wenn Genre-Daten vorhanden
        try:
            dj_rec, dj_notes_parts, dj_overlap = (
                _process_dj_brain_recommendations(current, upcoming)
            )
        except ValueError as error:
            logger.warning(
                "Uebergang %s ohne gueltige Strukturpunkte verworfen: %s",
                index, error,
            )
            continue
        notes_parts.extend(dj_notes_parts)
        if dj_rec is not None:
            if dj_rec.adjusted_mix_out_a >= 0.0:
                current_mix_out = dj_rec.adjusted_mix_out_a
            if dj_rec.adjusted_mix_in_b >= 0.0:
                next_mix_in = dj_rec.adjusted_mix_in_b
                fade_in_start = next_mix_in

            # B3: transition_bars ist die einzige DJ-Brain-Quelle fuer die
            # Overlap-Laenge. overlap_seconds ist nur noch ein synchronisierter
            # Rueckgabewert fuer bestehende UI-/API-Aufrufer.
            dynamic_bars = getattr(dj_rec, "transition_bars", 0)
            if dynamic_bars > 0 and current.bpm > 0:
                overlap = seconds_per_bar * dynamic_bars
            elif dj_overlap is not None:
                # Rueckwaertskompatibilitaet fuer externe/alte Recommendation-
                # Objekte ohne transition_bars.
                overlap = dj_overlap

        # Kandidaten (Spec 2026-08-21 Abschnitt 4): der aktive PairCandidate
        # (Rang 1 bzw. gespeicherte Wahl) traegt Mix-Out, Mix-In und Blende;
        # Track-Felder bleiben Analyse-Werte, alle Leser nehmen den Plan.
        kandidat_aktiv = 0
        kandidat_konsistent = True
        if kandidaten:
            aktiv, kandidat_konsistent = kette[index]
            if aktiv is None:
                aktiv = kandidaten[0]
            compatibility_score = int(round(metrics.overall_score * 100))
            energy_delta = int(round(float(metrics.energy_delta or 0.0)))
            risk_level = _categorise_risk_level(
                compatibility_score, risk_bpm_delta, bpm_tolerance, energy_delta
            )
            kandidat_aktiv = int(aktiv.rang)
            current_mix_out = float(aktiv.t_out)
            next_mix_in = float(aktiv.t_in)
            fade_in_start = next_mix_in
            overlap = float(aktiv.overlap_sec)
            if dj_rec is not None:
                # Sentinel-Felder mitziehen, damit Leser ohne Plan dieselben
                # Zeitpunkte sehen (resolve_transition_mix_points, Karten-Text).
                dj_rec.adjusted_mix_out_a = current_mix_out
                dj_rec.adjusted_mix_in_b = next_mix_in

        has_dynamic_bar_source = dj_rec is not None and hasattr(
            dj_rec, "transition_bars"
        )
        requested_overlap = float(overlap)
        validated_overlap = _clamp_transition_overlap(
            overlap,
            current,
            upcoming,
            current_mix_out,
            next_mix_in,
            # Reale DJ-Brain-Objekte und der normale Fallback haben belastbare
            # Fenster; alte externe Recommendation-Shims behalten den bisherigen
            # reinen 64-s-Sicherheitsdeckel.
            limit_to_windows=dj_rec is None or has_dynamic_bar_source,
        )
        if kandidaten and not math.isclose(
            validated_overlap, requested_overlap, rel_tol=0.0, abs_tol=1e-9
        ):
            logger.error(
                "Uebergang %s verworfen: Kandidaten-Overlap %.9f s waere "
                "defensiv auf %.9f s veraendert worden",
                index,
                requested_overlap,
                validated_overlap,
            )
            continue
        overlap = validated_overlap
        fade_out_start = current_mix_out

        if dj_rec is not None:
            dj_rec.overlap_seconds = overlap
            notes_parts = _handoff_pair_point_risks(
                dj_rec,
                current,
                upcoming,
                current_mix_out,
                next_mix_in,
                notes_parts,
            )

        # Empfehlung, Timeline und Renderer muessen dieselbe Dauer verwenden.
        if (
            not math.isfinite(float(overlap))
            or not 0.0 < float(overlap) <= MAX_TRANSITION_OVERLAP_SECONDS
        ):
            logger.error(
                "Uebergang %s verworfen: ungueltiger Overlap %r", index, overlap
            )
            continue
        overlap = float(overlap)
        fade_out_start = current_mix_out

        # Aussagekraeftige DJ-Beschreibung immer anhaengen
        # has_dj_brain=True vermeidet doppelte BPM/Key-Warnungen
        desc_params = TransitionDescriptionParams(
            compatibility_score=compatibility_score,
            bpm_delta=bpm_delta,
            bpm_tolerance=bpm_tolerance,
            energy_delta=energy_delta,
            metrics=metrics,
            from_track=current,
            to_track=upcoming,
            has_dj_brain=(dj_rec is not None),
        )
        transition_desc = _build_transition_description(desc_params)
        notes_parts.append(transition_desc)

        notes = "; ".join(notes_parts)

        transition_type = transition_type_for_candidate(
            current,
            upcoming,
            aktiv,
            bpm_tolerance=bpm_tolerance,
            scoring_context=ctx,
        )
        tempo_ratio = (
            float(upcoming.bpm / current.bpm)
            if current.bpm > 0 and upcoming.bpm > 0
            else 1.0
        )
        # Ende der Blende, begrenzt auf das real vorhandene Audio von A. Ohne
        # die Begrenzung koennte der Wert auf dem Pfad limit_to_windows=False
        # (nur 64-s-Deckel) hinter die Trackdauer fallen und eine Blende
        # anzeigen, die es nicht gibt.
        fade_out_end = current_mix_out + overlap
        if current.duration > 0:
            fade_out_end = min(fade_out_end, float(current.duration))

        plan = TransitionPlan(
            mix_out_a=float(current_mix_out),
            mix_in_b=float(next_mix_in),
            fade_out_start=float(fade_out_start),
            fade_out_end=float(fade_out_end),
            overlap=float(overlap),
            transition_type=transition_type,
            eq_mode=transition_type,
            tempo_ratio=tempo_ratio,
        )
        recommendations.append(
            TransitionRecommendation(
                index=index,
                from_track=current,
                to_track=upcoming,
                fade_out_start=float(fade_out_start),
                fade_out_end=float(fade_out_end),
                fade_in_start=float(fade_in_start),
                mix_entry=float(next_mix_in),
                overlap=float(overlap),
                bpm_delta=round(bpm_delta, 2),
                energy_delta=energy_delta,
                compatibility_score=compatibility_score,
                risk_level=risk_level,
                notes=notes,
                transition_type=transition_type,
                dj_rec=dj_rec,
                plan=plan,
                kandidaten=[k.to_dict() for k in kandidaten],
                kandidat_aktiv=kandidat_aktiv,
                kandidat_konsistent=kandidat_konsistent,
            )
        )

    return recommendations


def calculate_playlist_quality(
    tracks: list[Track],
    bpm_tolerance: float,
    scoring_context: Optional[Dict] = None,
    transition_metrics: Optional[List[TransitionMetrics]] = None,
) -> Dict[str, float]:
    """Calculate comprehensive quality metrics for a playlist.

    scoring_context (HPG-001): derselbe Laufkontext wie bei der Generierung.
    Die Qualitaet bewertet jedoch die aktive Mixpoint-Kette, nicht die davon
    getrennte Zielfunktion der Tracksortierung.
    """
    if len(tracks) < 2:
        return {
            "overall_score": 1.0,
            "harmonic_flow": 1.0,
            "energy_consistency": 1.0,
            "bpm_smoothness": 1.0,
        }

    ctx = scoring_context or {}
    metrics_by_pair = (
        list(transition_metrics)
        if transition_metrics is not None
        else compute_adjacent_transition_metrics(tracks, bpm_tolerance, ctx)
    )
    if len(metrics_by_pair) != len(tracks) - 1:
        raise ValueError("transition_metrics muss genau ein Element pro Nachbarpaar enthalten")
    # Alle Qualitaetswerte stammen aus den individuellen lokalen Messungen
    # genau der aktiven Mix-Out-/Mix-In-Kandidaten. Ganztrackwerte sind hier
    # weder Ersatz noch Bonus.
    avg_harmonic = sum(m.harmonic_score for m in metrics_by_pair) / len(metrics_by_pair) / 100.0
    avg_energy = sum(m.energy_flow for m in metrics_by_pair) / len(metrics_by_pair)
    avg_bpm = sum(m.bpm_smoothness for m in metrics_by_pair) / len(metrics_by_pair)
    energy_deltas = [
        abs(float(m.energy_delta))
        for m in metrics_by_pair
        if m.energy_delta is not None and math.isfinite(float(m.energy_delta))
    ]
    bpm_deltas = [
        effective_bpm_diff(tracks[index].bpm, tracks[index + 1].bpm)[0]
        for index in range(len(tracks) - 1)
    ]
    bpm_deltas = [float(delta) for delta in bpm_deltas if math.isfinite(float(delta))]

    # Normalize scores (0-1, higher is better)
    harmonic_flow = avg_harmonic
    energy_consistency = avg_energy
    bpm_smoothness = avg_bpm

    # Der Overall-Wert ist der Mittelwert der gerundeten 0-100-Werte, die
    # compute_transition_recommendations anzeigt. Damit sind UI-Qualitaet und
    # einzelne Empfehlung auch nach der Anzeige-Rundung identisch.
    displayed_scores = [round(m.overall_score * 100) for m in metrics_by_pair]
    overall_score = sum(displayed_scores) / len(displayed_scores) / 100.0

    return {
        "overall_score": overall_score,
        "harmonic_flow": harmonic_flow,
        "energy_consistency": energy_consistency,
        "bpm_smoothness": bpm_smoothness,
        "avg_harmonic_score": avg_harmonic * 100,
        "avg_transition_score": overall_score * 100,
        "avg_energy_jump": (
            sum(energy_deltas) / len(energy_deltas) if energy_deltas else 0.0
        ),
        "avg_bpm_jump": sum(bpm_deltas) / len(bpm_deltas) if bpm_deltas else 0.0,
    }


def _context_target_energy(
    position: int,
    total: int,
    *,
    energy_direction: str,
    peak_position: float,
    pool_average: float,
    configured_target: Optional[float],
) -> float:
    if configured_target is not None:
        return configured_target
    progress = position / max(1, total - 1)
    if energy_direction == "Build Up":
        return 30.0 + 55.0 * progress
    if energy_direction == "Cool Down":
        return 85.0 - 55.0 * progress
    if energy_direction == "Maintain":
        return pool_average
    if progress <= peak_position:
        return 30.0 + 55.0 * (progress / peak_position)
    decline = (progress - peak_position) / max(1e-9, 1.0 - peak_position)
    return 85.0 - 45.0 * decline


def _sort_context_flow(
    tracks: list[Track], bpm_tolerance: float, **kwargs
) -> list[Track]:
    """
    Kontext-bewusster Greedy-Sort. Harmonische Basis ist calculate_compatibility
    (korrektes Camelot-Wheel + BPM-Gate); darauf DJ-Kontext-Modifikatoren,
    portiert aus der frueheren Intelligent-Scoring-Schicht:
      - Set-Phase mit Ziel-Energie (Warm-up 30 / Build 60 / Peak 85 / Cool-down 40)
      - Energie-Trend-Fortfuehrung (steigende Kurve nicht abwuergen)
      - Genre-Fatigue (nach 4 gleichen Genres Wechsel belohnen)
      - Repetition-Penalty (Beinahe-Klone nicht back-to-back)
      - Energie-Cliff-Penalty (Spruenge > 35 Punkte vermeiden)

    Strategien-Merge 2026-07-17: uebernimmt die energy_direction-Presets der
    frueheren "Emotional Journey"-Strategie — "Build Up"/"Cool Down"/"Maintain"
    formen die Zielenergie-Kurve, "Auto" = klassische Set-Dramaturgie.
    """
    cancel_check = kwargs.get("cancel_check")
    _check_cancel(cancel_check)
    if not tracks:
        return []

    raw_energy_dir = str(kwargs.get("energy_direction", "Auto"))
    energy_dir = {
        "auto": "Auto",
        "up": "Build Up",
        "down": "Cool Down",
        "maintain": "Maintain",
    }.get(raw_energy_dir, raw_energy_dir)
    peak_position = max(0.4, min(0.8, float(kwargs.get("peak_position", 70)) / 100.0))
    genre_mixing = bool(kwargs.get("genre_mixing", True))
    genre_weight = max(0.0, min(1.0, float(kwargs.get("genre_weight", 0.3))))
    pool_avg_energy = sum(t.energy for t in tracks) / len(tracks)
    configured_target = kwargs.get("target_energy")
    if configured_target is not None:
        configured_target = max(0.0, min(100.0, float(configured_target)))

    def _target_energy(position: int, total: int) -> float:
        return _context_target_energy(
            position,
            total,
            energy_direction=energy_dir,
            peak_position=peak_position,
            pool_average=pool_avg_energy,
            configured_target=configured_target,
        )

    if len(tracks) <= 2:
        def small_score(order) -> tuple:
            total_score = 0.0
            valid_edges = 0
            for position, track in enumerate(order):
                _check_cancel(cancel_check)
                target = _target_energy(position, len(order))
                total_score += 10.0 - min(30.0, abs(track.energy - target)) / 3.0
                if position == 0:
                    continue
                previous = order[position - 1]
                base = calculate_compatibility(
                    previous, track, bpm_tolerance, **kwargs
                )
                if base == 0:
                    continue
                valid_edges += 1
                total_score += float(base)
                if genre_mixing and genre_weight > 0.0:
                    genre_compat = get_genre_compatibility(
                        _resolve_track_genre(previous), _resolve_track_genre(track)
                    )
                    total_score += genre_weight * (genre_compat - 0.5) * 20.0
                if (
                    abs(track.bpm - previous.bpm) < 0.5
                    and track.camelotCode == previous.camelotCode
                    and abs(track.energy - previous.energy) < 5
                ):
                    total_score -= 12.0
                if abs(track.energy - previous.energy) > 35:
                    total_score -= 15.0
            return valid_edges, total_score

        return _small_pool_order(tracks, small_score, cancel_check)

    unprocessed = list(tracks)
    total = len(tracks)
    # Start-Track passend zur Richtung: Build Up/Auto = ruhigster Track,
    # Cool Down = energiereichster, Maintain = naechster am Durchschnitt
    if energy_dir == "Cool Down":
        start = max(unprocessed, key=lambda t: t.energy)
    elif energy_dir == "Maintain":
        start = min(unprocessed, key=lambda t: abs(t.energy - pool_avg_energy))
    else:
        start = min(unprocessed, key=lambda t: t.energy)
    final_playlist = [start]
    _remove_track(unprocessed, start)

    while unprocessed:
        _check_cancel(cancel_check)
        current = final_playlist[-1]
        target_energy = _target_energy(len(final_playlist), total)

        # Energie-Trend aus den letzten 3 Tracks
        recent = [t.energy for t in final_playlist[-3:]]
        trend = recent[-1] - recent[0] if len(recent) >= 2 else 0.0

        # Genre-Streak am Playlist-Ende
        streak_genre = _resolve_track_genre(current)
        streak = 0
        for t in reversed(final_playlist):
            _check_cancel(cancel_check)
            if _resolve_track_genre(t) == streak_genre:
                streak += 1
            else:
                break

        best_next = None
        highest_score = -999999.0
        for candidate in unprocessed:
            _check_cancel(cancel_check)
            # Reine Harmonik als Basis; Energie und Genre werden unten als
            # explizite Context-Regler addiert. So bedeutet genre_weight=0
            # tatsaechlich, dass Genre die Reihenfolge nicht beeinflusst.
            base = calculate_compatibility(
                current, candidate, bpm_tolerance, **kwargs
            )
            if base == 0:
                continue  # BPM-Hard-Gate beibehalten

            score = float(base)
            # Kalibrierung (Audit 2026-07-17): Boni in Summe max +19 — knapp
            # UNTER einer 20-Punkte-Camelot-Stufe. Kontext darf zwischen gleich
            # guten Harmonik-Kandidaten entscheiden, aber keinen Diagonal-Mix
            # (60) ueber einen Adjacent-Mix (80) heben.
            # Phase: Naehe zur Ziel-Energie (+10 bei Treffer, faellt linear ab)
            score += 10.0 - min(30.0, abs(candidate.energy - target_energy)) / 3.0
            # Trend-Fortfuehrung: Kandidat setzt erkennbare Richtung fort
            if abs(trend) >= 5.0:
                cand_delta = candidate.energy - current.energy
                if (trend > 0) == (cand_delta > 0) and abs(cand_delta) <= 25:
                    score += 5.0
            if genre_mixing and genre_weight > 0.0:
                # Genre-Matrix wirkt kontinuierlich: bei Gewicht 0 ist Genre
                # vollstaendig neutral, bei 1 maximal +/-10 Punkte.
                genre_compat = get_genre_compatibility(
                    streak_genre, _resolve_track_genre(candidate)
                )
                score += genre_weight * (genre_compat - 0.5) * 20.0
                # Fatigue bleibt ein kleiner Zusatz innerhalb desselben Reglers.
                if streak >= 4:
                    fatigue = 4.0 if _resolve_track_genre(candidate) != streak_genre else -6.0
                    score += genre_weight * fatigue
            # Repetition-Penalty: Beinahe-Klon direkt hintereinander
            if (
                abs(candidate.bpm - current.bpm) < 0.5
                and candidate.camelotCode == current.camelotCode
                and abs(candidate.energy - current.energy) < 5
            ):
                score -= 12.0
            # Energie-Cliff
            if abs(candidate.energy - current.energy) > 35:
                score -= 15.0

            if score > highest_score:
                highest_score = score
                best_next = candidate

        if best_next is None:
            best_next = min(
                unprocessed,
                key=lambda t: effective_bpm_diff(t.bpm, current.bpm)[0],
            )
        final_playlist.append(best_next)
        _remove_track(unprocessed, best_next)

    return final_playlist


# --- Main Dispatcher --- #

# Strategien-Merge 2026-07-17 (11 -> 8):
# - "Harmonic Flow" nutzt jetzt die Enhanced-Implementierung (Lookahead war
#   strikt besser, ~90% Code-Overlap zwischen beiden Varianten)
# - "Peak-Time" nutzt die Enhanced-Implementierung (peak_position-Regler +
#   Harmonic Smoothing; die simple sin-Kurve war faktisch redundant)
# - "Emotional Journey" ist in "Context Flow" aufgegangen (energy_direction-
#   Presets Build Up / Cool Down / Maintain formen dort die Zielenergie-Kurve)
STRATEGIES = {
    "Harmonic Flow": _sort_harmonic_flow,
    "Warm-Up": _sort_warm_up,
    "Cool-Down": _sort_cool_down,
    "Peak-Time": _sort_peak_time,
    "Energy Wave": _sort_energy_wave,
    "Genre Flow": _sort_genre_flow,
    "Consistent": _sort_consistent,
    "Context Flow": _sort_context_flow,
}

# HPG-001: Nur diese Parameter beeinflussen die Kompatibilitaets-Zielfunktion
# (calculate_enhanced_compatibility -> _calculate_compatibility_inner). Der
# Scoring-Kontext, der durch Reorder/Preview/Quality/Recommendations gereicht
# wird, besteht genau aus dieser Teilmenge.
SCORING_PARAMETERS = {
    "energy_direction", "harmonic_strictness", "allow_experimental"
}
SCORING_ENERGY_DIRECTIONS = frozenset({
    "Auto", "Build Up", "Cool Down", "Maintain",
    "auto", "up", "down", "maintain",
})

SUPPORTED_STRATEGY_PARAMETERS = {
    "Harmonic Flow": {"harmonic_strictness", "allow_experimental"},
    "Warm-Up": set(),
    "Cool-Down": set(),
    "Peak-Time": {"peak_position", "harmonic_strictness", "allow_experimental"},
    "Energy Wave": set(),
    "Genre Flow": {"genre_mixing", "genre_weight"},
    "Consistent": {"harmonic_strictness", "allow_experimental"},
    "Context Flow": {
        "energy_direction",
        "peak_position",
        "harmonic_strictness",
        "allow_experimental",
        "genre_mixing",
        "genre_weight",
        "target_energy",
    },
}

# Alte Namen bleiben gueltig (gespeicherte Settings, Tests, Cache-Metadaten)
STRATEGY_ALIASES = {
    "Harmonic Flow Enhanced": "Harmonic Flow",
    "Peak-Time Enhanced": "Peak-Time",
    "Emotional Journey": "Context Flow",
}


def resolve_scoring_context(
    mode: str, advanced_params: Optional[Dict] = None
) -> Dict:
    """Liefert den Scoring-Kontext (HPG-001) fuer eine Strategie.

    Genau die Scoring-Parameter, die die gewaehlte Strategie beim Sortieren
    tatsaechlich nutzt. Strategien ohne harmonic_strictness (z.B. Warm-Up)
    liefern {} — dann verwenden Sortierung und Ergebnisbewertung dieselben
    Defaults. Anzeige, Reorder, Preview, Quality und Empfehlungen muessen genau
    diesen Kontext verwenden. Die Sortierung bewertet dabei weiterhin ihre
    eigene Zielfunktion; die Ergebnisbewertung folgt der aktiven Mixpoint-Kette.
    """
    resolved_mode = STRATEGY_ALIASES.get(mode, mode)
    effective = StrategyConfig.from_mapping(advanced_params).effective_kwargs(
        resolved_mode
    )
    return {
        key: value
        for key, value in effective.items()
        if key in SCORING_PARAMETERS or key == "target_energy"
    }


def resolve_run_scoring_context(
    mode: str, advanced_params: Optional[Dict] = None
) -> Dict:
    """Friert Scoring, Kandidaten-Toleranzen und Schema-Raenge je Lauf ein."""
    from . import candidate_preferences
    from .candidate_preferences import GEWICHT_SCHLUESSEL
    from .genres import CANONICAL_GENRES
    from .tolerances import get_tolerances

    context = deepcopy(resolve_scoring_context(mode, advanced_params))
    toleranzprofile: dict[str, dict] = {}
    track_toleranzprofile: dict[str, dict] = {}
    schema_profile: dict[str, list[str]] = {}
    for genre in CANONICAL_GENRES:
        profil = deepcopy(get_tolerances(genre))
        track_toleranzprofile[genre] = deepcopy(profil)
        praferenz = candidate_preferences.kandidaten_gewichte(genre)
        if praferenz is not None:
            for key in GEWICHT_SCHLUESSEL:
                profil[key] = float(praferenz[key])
        toleranzprofile[genre] = profil
        schema_profile[genre] = deepcopy(
            candidate_preferences.schema_rangfolge(genre)
        )

    # Unknown darf nie still die Hoertestpraeferenz des ersten kanonischen
    # Genres erben. Nur dessen allgemeine Toleranzbasis wird kopiert.
    toleranzprofile["Unknown"] = deepcopy(get_tolerances("Unknown"))
    track_toleranzprofile["Unknown"] = deepcopy(toleranzprofile["Unknown"])
    schema_profile["Unknown"] = []
    context["track_tolerances_by_genre"] = track_toleranzprofile
    context["candidate_tolerances_by_genre"] = toleranzprofile
    context["candidate_schema_ranks_by_genre"] = schema_profile
    return context


def _validate_candidate_profile_genre(genre, path: str) -> str:
    """Akzeptiert nur kanonische Genres und den expliziten Unknown-Fallback."""
    from .genres import CANONICAL_GENRES

    allowed_genres = frozenset(CANONICAL_GENRES) | {"Unknown"}
    if type(genre) is not str or genre not in allowed_genres:
        raise ValueError(f"{path} enthaelt unbekanntes Genre {genre!r}")
    return genre


def _validate_candidate_tolerance_profile(profile, path: str) -> dict:
    """Validiert ein partielles Profil nach seiner realen Konsumsemantik."""
    from .tolerances import (
        ERLAUBTE_TOLERANZ_SCHLUESSEL,
        KANDIDATEN_GEWICHT_SCHLUESSEL,
        TRACK_GEWICHT_SCHLUESSEL,
    )

    if not isinstance(profile, Mapping):
        raise ValueError(f"{path} muss ein Mapping sein")
    profile = deepcopy(dict(profile))
    unknown_keys = sorted(
        set(profile) - ERLAUBTE_TOLERANZ_SCHLUESSEL, key=repr
    )
    if unknown_keys:
        raise ValueError(
            f"{path} enthaelt unbekannte Profil-Schluessel: "
            + ", ".join(repr(key) for key in unknown_keys)
        )

    weight_keys = frozenset(
        TRACK_GEWICHT_SCHLUESSEL + KANDIDATEN_GEWICHT_SCHLUESSEL
    )
    normalized = {}
    for key, value in profile.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            if key in weight_keys:
                raise ValueError(
                    f"{path}[{key!r}] ist kein endliches Gewicht zwischen 0 und 1"
                )
            raise ValueError(f"{path}[{key!r}] muss eine endliche Zahl sein")
        number = float(value)
        if key in weight_keys and not 0.0 <= number <= 1.0:
            raise ValueError(
                f"{path}[{key!r}] ist kein endliches Gewicht zwischen 0 und 1"
            )
        if key == "groove_sim_floor" and not 0.0 <= number <= 1.0:
            raise ValueError(f"{path}[{key!r}] muss zwischen 0 und 1 liegen")
        if key in {"bass_delta_max", "brightness_delta_max"} and number <= 0.0:
            raise ValueError(f"{path}[{key!r}] muss groesser als 0 sein")
        normalized[key] = number
    return normalized


def _has_complete_run_profile_snapshot(scoring_context: Mapping) -> bool:
    """Erkennt den vollstaendigen GUI-Laufstart-Snapshot ohne Live-Zugriff."""
    from .tolerances import ERLAUBTE_TOLERANZ_SCHLUESSEL

    profile_keys = (
        "track_tolerances_by_genre",
        "candidate_tolerances_by_genre",
    )
    schema_key = "candidate_schema_ranks_by_genre"
    allowed_genres = frozenset(CANONICAL_GENRES) | {"Unknown"}
    for key in profile_keys:
        profiles = scoring_context.get(key)
        if not isinstance(profiles, Mapping) or set(profiles) != allowed_genres:
            return False
        if any(
            not isinstance(profile, Mapping)
            or set(profile) != ERLAUBTE_TOLERANZ_SCHLUESSEL
            for profile in profiles.values()
        ):
            return False
    schemas = scoring_context.get(schema_key)
    return isinstance(schemas, Mapping) and set(schemas) == allowed_genres


def _complete_run_scoring_context(
    mode: str,
    advanced_params: Optional[Dict],
    scoring_context: Optional[Dict],
) -> Dict:
    """Ergaenzt alte/partielle Kontexte um den vollstaendigen Laufvertrag."""
    if scoring_context is None:
        return resolve_run_scoring_context(mode, advanced_params)
    if not isinstance(scoring_context, Mapping):
        raise ValueError("scoring_context muss ein Mapping sein")

    supplied = deepcopy(dict(scoring_context))
    tolerance_key = "candidate_tolerances_by_genre"
    track_tolerance_key = "track_tolerances_by_genre"
    schema_key = "candidate_schema_ranks_by_genre"
    if _has_complete_run_profile_snapshot(supplied):
        # Ein Laufstart-Snapshot ist bereits die Wahrheit dieses Laufs. Ein
        # erneuter Datei-/Lock-Zugriff koennte spaetere Aenderungen einmischen
        # oder einen gueltigen Lauf unnoetig scheitern lassen.
        context = deepcopy(resolve_scoring_context(mode, advanced_params))
        allowed_genres = tuple(CANONICAL_GENRES) + ("Unknown",)
        context[track_tolerance_key] = {genre: {} for genre in allowed_genres}
        context[tolerance_key] = {genre: {} for genre in allowed_genres}
        context[schema_key] = {genre: [] for genre in allowed_genres}
    else:
        context = resolve_run_scoring_context(mode, advanced_params)
    allowed_keys = SCORING_PARAMETERS | {
        "target_energy", tolerance_key, track_tolerance_key, schema_key,
    }
    unknown_keys = sorted(set(supplied) - allowed_keys, key=repr)
    if unknown_keys:
        raise ValueError(
            "scoring_context enthaelt unbekannte Schluessel: "
            + ", ".join(repr(key) for key in unknown_keys)
        )
    scalar_keys = SCORING_PARAMETERS | {"target_energy"}
    supported_scalars = (
        SUPPORTED_STRATEGY_PARAMETERS.get(STRATEGY_ALIASES.get(mode, mode), set())
        & scalar_keys
    )
    unsupported_scalars = sorted(
        (set(supplied) & scalar_keys) - supported_scalars
    )
    if unsupported_scalars:
        raise ValueError(
            f"scoring_context enthaelt fuer Strategie {mode!r} nicht "
            "unterstuetzte Schluessel: "
            + ", ".join(repr(key) for key in unsupported_scalars)
        )

    if "energy_direction" in supplied:
        energy_direction = supplied["energy_direction"]
        if type(energy_direction) is not str:
            raise ValueError("scoring_context.energy_direction muss eine Zeichenkette sein")
        if energy_direction not in SCORING_ENERGY_DIRECTIONS:
            raise ValueError("scoring_context.energy_direction ist nicht unterstuetzt")
    if "harmonic_strictness" in supplied:
        strictness = supplied["harmonic_strictness"]
        if type(strictness) is not int or not 1 <= strictness <= 10:
            raise ValueError(
                "scoring_context.harmonic_strictness muss eine ganze Zahl von 1 bis 10 sein"
            )
    if "allow_experimental" in supplied and type(supplied["allow_experimental"]) is not bool:
        raise ValueError("scoring_context.allow_experimental muss boolesch sein")
    for key, minimum, maximum in (("target_energy", 0.0, 100.0),):
        if key not in supplied or (
            key == "target_energy" and supplied[key] is None
        ):
            continue
        value = supplied[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not minimum <= float(value) <= maximum
        ):
            raise ValueError(
                f"scoring_context.{key} muss eine endliche Zahl von "
                f"{minimum:g} bis {maximum:g} sein"
            )
        supplied[key] = float(value)

    tolerances_were_supplied = tolerance_key in supplied
    track_tolerances_were_supplied = track_tolerance_key in supplied
    schemas_were_supplied = schema_key in supplied
    supplied_tolerances = supplied.pop(tolerance_key, None)
    supplied_track_tolerances = supplied.pop(track_tolerance_key, None)
    supplied_schemas = supplied.pop(schema_key, None)
    context.update(supplied)

    if track_tolerances_were_supplied:
        if not isinstance(supplied_track_tolerances, Mapping):
            raise ValueError(f"{track_tolerance_key} muss ein Mapping sein")
        merged_track = deepcopy(context[track_tolerance_key])
        for genre, profile in supplied_track_tolerances.items():
            genre = _validate_candidate_profile_genre(genre, track_tolerance_key)
            normalized = _validate_candidate_tolerance_profile(
                profile, f"{track_tolerance_key}[{genre!r}]"
            )
            base_profile = deepcopy(merged_track[genre])
            base_profile.update(normalized)
            _track_edge_weights(
                base_profile, f"{track_tolerance_key}[{genre!r}]"
            )
            merged_track[genre] = base_profile
        context[track_tolerance_key] = merged_track

    if tolerances_were_supplied:
        from .candidate_preferences import GEWICHT_SCHLUESSEL

        if not isinstance(supplied_tolerances, Mapping):
            raise ValueError(f"{tolerance_key} muss ein Mapping sein")
        merged = deepcopy(context[tolerance_key])
        for genre, profile in supplied_tolerances.items():
            genre = _validate_candidate_profile_genre(genre, tolerance_key)
            profile = _validate_candidate_tolerance_profile(
                profile, f"{tolerance_key}[{genre!r}]"
            )
            supplied_weights = {
                key: profile[key] for key in GEWICHT_SCHLUESSEL if key in profile
            }

            base_profile = deepcopy(merged.get(str(genre), {}))
            if supplied_weights:
                supplied_sum = sum(float(value) for value in supplied_weights.values())
                remaining_keys = [
                    key for key in GEWICHT_SCHLUESSEL if key not in supplied_weights
                ]
                if supplied_sum > 1.0 + 1e-12:
                    raise ValueError(
                        f"{tolerance_key}[{genre!r}] angegebene Gewichte "
                        f"summieren auf {supplied_sum}, maximal erlaubt ist 1.0"
                    )
                if not remaining_keys and not math.isclose(
                    supplied_sum, 1.0, rel_tol=0.0, abs_tol=1e-12
                ):
                    raise ValueError(
                        f"{tolerance_key}[{genre!r}] vollstaendige Gewichte "
                        f"summieren auf {supplied_sum}, erwartet ist 1.0"
                    )
                if remaining_keys:
                    remaining_sum = sum(
                        float(base_profile[key]) for key in remaining_keys
                    )
                    rest = max(0.0, 1.0 - supplied_sum)
                    if remaining_sum <= 0.0 and rest > 1e-12:
                        raise ValueError(
                            f"{tolerance_key}[{genre!r}] hat keine positive "
                            "Basis fuer die nicht angegebenen Gewichte"
                        )
                    for key in remaining_keys:
                        base_profile[key] = (
                            float(base_profile[key]) / remaining_sum * rest
                            if remaining_sum > 0.0
                            else 0.0
                        )
                for key, value in supplied_weights.items():
                    base_profile[key] = float(value)
            base_profile.update({
                key: value for key, value in profile.items()
                if key not in supplied_weights
            })
            merged[str(genre)] = base_profile
        context[tolerance_key] = merged

    if schemas_were_supplied:
        from .mix_candidates import SCHEMA_PRIORITAET

        if not isinstance(supplied_schemas, Mapping):
            raise ValueError(f"{schema_key} muss ein Mapping sein")
        merged = deepcopy(context[schema_key])
        for genre, ranks in supplied_schemas.items():
            genre = _validate_candidate_profile_genre(genre, schema_key)
            if (
                not isinstance(ranks, (list, tuple))
                or any(
                    not isinstance(rank, str) or rank not in SCHEMA_PRIORITAET
                    for rank in ranks
                )
                or len(set(ranks)) != len(ranks)
            ):
                raise ValueError(
                    f"{schema_key}[{genre!r}] muss eine eindeutige Liste "
                    "bekannter Schemata sein"
                )
            merged[str(genre)] = list(ranks)
        context[schema_key] = merged
    return context


@dataclass(frozen=True, slots=True)
class _PathState:
    selections: tuple[Optional["CandidateSnapshot"], ...]
    consistencies: tuple[bool, ...]
    planned: int
    saved_honored: int
    score: float
    path_consistent_links: int
    state_key_sequence: tuple


def _path_order(state: _PathState) -> tuple:
    return (
        -state.planned,
        -state.saved_honored,
        -state.score,
        -state.path_consistent_links,
        state.state_key_sequence,
    )


def _snapshot_flag(snapshot: "CandidateSnapshot", name: str, default=False):
    return dict(snapshot.flags).get(name, default)


def _candidate_link_consistent(
    previous: "CandidateSnapshot", current: "CandidateSnapshot", middle: Track
) -> bool:
    grid = seconds_per_bar(middle.bpm) * int(
        getattr(middle, "phrase_unit", 8) or 8
    )
    return (
        current.t_out
        >= previous.t_in + 2.0 * grid - QUANTIZE_TOLERANCE_SEC
    )


def _select_snapshot_path(
    candidates_by_boundary: tuple[tuple["CandidateSnapshot", ...], ...],
    occurrences: tuple[TrackOccurrence, ...],
    cancel_check=None,
) -> tuple[tuple[Optional["CandidateSnapshot"], ...], tuple[bool, ...], int, int, int]:
    """Begrenzter DP: hoechstens 12 Kandidaten plus UNGEPLANT je Kante."""
    if not candidates_by_boundary:
        return (), (), 0, 0, 0
    previous_states: dict[Optional[tuple], _PathState] = {}
    states_retained = 0
    link_checks = 0

    for index, snapshots in enumerate(candidates_by_boundary):
        _check_cancel(cancel_check)
        options: tuple[Optional["CandidateSnapshot"], ...] = (*snapshots[:12], None)
        current_states: dict[Optional[tuple], _PathState] = {}
        predecessors = tuple(previous_states.values()) or (
            _PathState((), (), 0, 0, 0.0, 0, ()),
        )
        for option in options:
            _check_cancel(cancel_check)
            best: Optional[_PathState] = None
            for predecessor in predecessors:
                _check_cancel(cancel_check)
                previous = predecessor.selections[-1] if predecessor.selections else None
                if option is None:
                    consistent = False
                    link_ok = False
                elif previous is None:
                    consistent = True
                    link_ok = False
                else:
                    link_checks += 1
                    link_ok = _candidate_link_consistent(
                        previous, option, occurrences[index].track
                    )
                    consistent = link_ok
                planned = predecessor.planned + (option is not None)
                honored = predecessor.saved_honored + int(
                    option is not None
                    and bool(_snapshot_flag(option, "gespeicherte_wahl"))
                )
                score = predecessor.score + (option.score if option is not None else 0.0)
                path_links = predecessor.path_consistent_links + int(link_ok)
                state_key = (0, option.key) if option is not None else (1, ())
                candidate = _PathState(
                    selections=(*predecessor.selections, option),
                    consistencies=(*predecessor.consistencies, consistent),
                    planned=planned,
                    saved_honored=honored,
                    score=score,
                    path_consistent_links=path_links,
                    state_key_sequence=(*predecessor.state_key_sequence, state_key),
                )
                if best is None or _path_order(candidate) < _path_order(best):
                    best = candidate
            assert best is not None
            current_states[option.key if option is not None else None] = best
        states_retained += len(current_states)
        previous_states = current_states

    winner = min(previous_states.values(), key=_path_order)
    return (
        winner.selections,
        winner.consistencies,
        link_checks,
        winner.path_consistent_links,
        states_retained,
    )


def _immutable_metrics_from_candidate(kandidat) -> ImmutableMetricsSnapshot:
    legacy = transition_metrics_from_candidate(kandidat)
    from .pair_candidates import CandidateSnapshot

    snapshot = CandidateSnapshot.from_pair_candidate(
        kandidat, original_ordinal=max(0, int(kandidat.rang) - 1)
    )
    return ImmutableMetricsSnapshot(
        harmonic_score=legacy.harmonic_score,
        bpm_smoothness=legacy.bpm_smoothness,
        energy_flow=legacy.energy_flow,
        genre_compatibility=legacy.genre_compatibility,
        overall_score=legacy.overall_score,
        ai_bonus=0.0,
        groove_match=legacy.groove_match,
        bass_continuity=legacy.bass_continuity,
        timbre_match=legacy.timbre_match,
        mood_match=legacy.mood_match,
        loudness_match=legacy.loudness_match,
        structure_match=legacy.structure_match,
        energy_delta=legacy.energy_delta,
        lufs_delta=legacy.lufs_delta,
        kandidat=snapshot,
    )


def _immutable_metrics_for_snapshot(
    track1: Track,
    track2: Track,
    bpm_tolerance: float,
    context: Mapping,
    snapshot: Optional["CandidateSnapshot"],
    mutable_by_key: Mapping,
) -> ImmutableMetricsSnapshot:
    """Bewertet den aktiven Result-Kandidaten; planlose Kanten bleiben null."""
    if snapshot is None:
        return ImmutableMetricsSnapshot(
            harmonic_score=0,
            bpm_smoothness=0.0,
            energy_flow=0.0,
            genre_compatibility=0.0,
            overall_score=0.0,
        )
    mutable = mutable_by_key[snapshot.key]
    metrics = _calculate_track_edge_metrics(
        track1,
        track2,
        bpm_tolerance,
        context.get("energy_direction"),
        context,
        mutable,
    )
    return ImmutableMetricsSnapshot(
        harmonic_score=metrics.harmonic_score,
        bpm_smoothness=metrics.bpm_smoothness,
        energy_flow=metrics.energy_flow,
        genre_compatibility=metrics.genre_compatibility,
        overall_score=metrics.overall_score,
        ai_bonus=0.0,
        groove_match=metrics.groove_match,
        bass_continuity=metrics.bass_continuity,
        timbre_match=metrics.timbre_match,
        mood_match=metrics.mood_match,
        loudness_match=metrics.loudness_match,
        structure_match=metrics.structure_match,
        energy_delta=metrics.energy_delta,
        lufs_delta=metrics.lufs_delta,
        kandidat=snapshot,
    )


def legacy_transition_metrics(
    result: PlaylistGenerationResult,
) -> list[TransitionMetrics]:
    """Neue mutable Legacy-Objekte; Result-Snapshots bleiben unangetastet."""
    return [
        TransitionMetrics(
            harmonic_score=item.harmonic_score,
            bpm_smoothness=item.bpm_smoothness,
            energy_flow=item.energy_flow,
            genre_compatibility=item.genre_compatibility,
            overall_score=item.overall_score,
            ai_bonus=item.ai_bonus,
            groove_match=item.groove_match,
            bass_continuity=item.bass_continuity,
            timbre_match=item.timbre_match,
            mood_match=item.mood_match,
            loudness_match=item.loudness_match,
            structure_match=item.structure_match,
            energy_delta=item.energy_delta,
            lufs_delta=item.lufs_delta,
            kandidat=item.kandidat.to_dict() if item.kandidat is not None else None,
        )
        for item in result.metrics
    ]


def legacy_transition_recommendations(
    result: PlaylistGenerationResult,
) -> list[TransitionRecommendation]:
    """Defensive GUI-/Exporter-Sicht ohne mutable Referenz im Result."""
    occurrence_by_id = {
        occurrence.occurrence_id: occurrence for occurrence in result.occurrences
    }
    legacy: list[TransitionRecommendation] = []
    for item in result.recommendations:
        active_rank = 0
        if item.active_candidate_key is not None:
            active = next(
                (
                    candidate
                    for candidate in item.candidates
                    if candidate.key == item.active_candidate_key
                ),
                None,
            )
            active_rank = active.rang if active is not None else 0
        legacy.append(
            TransitionRecommendation(
                index=item.index,
                from_track=occurrence_by_id[item.from_occurrence_id].track,
                to_track=occurrence_by_id[item.to_occurrence_id].track,
                fade_out_start=item.fade_out_start,
                fade_out_end=item.fade_out_end,
                fade_in_start=item.fade_in_start,
                mix_entry=item.mix_entry,
                overlap=item.overlap,
                bpm_delta=item.bpm_delta,
                energy_delta=item.energy_delta,
                compatibility_score=item.compatibility_score,
                risk_level=item.risk_level,
                notes=item.notes,
                transition_type=item.transition_type,
                dj_rec=None,
                plan=item.plan,
                kandidaten=[candidate.to_dict() for candidate in item.candidates],
                kandidat_aktiv=active_rank,
                kandidat_konsistent=item.candidate_consistent,
            )
        )
    return legacy


def _rank_fixed_boundaries(
    occurrences: tuple[TrackOccurrence, ...],
    bpm_tolerance: float,
    context: dict,
    choice_snapshot: Mapping,
    cancel_check=None,
) -> tuple[
    tuple[tuple["CandidateSnapshot", ...], ...],
    tuple[dict[tuple, object], ...],
    int,
]:
    from . import candidate_choices
    from .pair_candidates import CandidateSnapshot, rank_pair_candidates

    all_snapshots: list[tuple[CandidateSnapshot, ...]] = []
    mutable_maps: list[dict[tuple, object]] = []
    saved_present = 0
    for index in range(max(0, len(occurrences) - 1)):
        _check_cancel(cancel_check)
        track_a = occurrences[index].track
        track_b = occurrences[index + 1].track
        choice_key = candidate_choices.schluessel(track_a.filePath, track_b.filePath)
        persisted = choice_snapshot.get(choice_key, {})
        if choice_key in choice_snapshot:
            saved_present += 1
        genre = _resolve_track_genre(track_a)
        tolerance_profiles = context.get("candidate_tolerances_by_genre", {})
        schema_profiles = context.get("candidate_schema_ranks_by_genre", {})
        tolerances = tolerance_profiles.get(
            genre, tolerance_profiles.get("Unknown", {})
        ) if isinstance(tolerance_profiles, Mapping) else None
        schema_rank = schema_profiles.get(
            genre, schema_profiles.get("Unknown", [])
        ) if isinstance(schema_profiles, Mapping) else None
        mutable = rank_pair_candidates(
            track_a,
            track_b,
            bpm_tolerance=bpm_tolerance,
            energy_direction=_normalize_energy_direction(
                context.get("energy_direction")
            ),
            harmonic_strictness=context.get("harmonic_strictness", 7),
            allow_experimental=context.get("allow_experimental", True),
            tolerances=tolerances,
            wahl=persisted,
            schema_rang=schema_rank,
        )[:12]
        _check_cancel(cancel_check)
        snapshots = tuple(
            CandidateSnapshot.from_pair_candidate(candidate, original_ordinal=ordinal)
            for ordinal, candidate in enumerate(mutable)
        )
        all_snapshots.append(snapshots)
        mutable_maps.append(
            {snapshot.key: candidate for snapshot, candidate in zip(snapshots, mutable)}
        )
    return tuple(all_snapshots), tuple(mutable_maps), saved_present


def _recommendation_snapshot(
    index: int,
    occurrences: tuple[TrackOccurrence, ...],
    candidates: tuple["CandidateSnapshot", ...],
    selected: Optional["CandidateSnapshot"],
    metrics: ImmutableMetricsSnapshot,
    consistent: bool,
    mutable_by_key: Mapping,
    bpm_tolerance: float,
    context: dict,
) -> ImmutableRecommendationSnapshot:
    current = occurrences[index]
    upcoming = occurrences[index + 1]
    bpm_delta = float(upcoming.track.bpm) - float(current.track.bpm)
    if selected is None:
        return ImmutableRecommendationSnapshot(
            index=index,
            from_occurrence_id=current.occurrence_id,
            to_occurrence_id=upcoming.occurrence_id,
            fade_out_start=0.0,
            fade_out_end=0.0,
            fade_in_start=0.0,
            mix_entry=0.0,
            overlap=0.0,
            bpm_delta=bpm_delta,
            energy_delta=0,
            compatibility_score=0,
            risk_level="unplanned",
            notes="UNGEPLANT — kein ausführbarer TransitionPlan",
            transition_type="unplanned",
            plan=None,
            candidates=candidates,
            active_candidate_key=None,
            candidate_consistent=False,
        )

    candidate = mutable_by_key[selected.key]
    overlap = selected.overlap_sec
    fade_out_end = selected.t_out + overlap
    if current.track.duration > 0:
        fade_out_end = min(fade_out_end, float(current.track.duration))
    transition_type = transition_type_for_candidate(
        current.track,
        upcoming.track,
        candidate,
        bpm_tolerance=bpm_tolerance,
        scoring_context=context,
    )
    tempo_ratio = (
        float(upcoming.track.bpm / current.track.bpm)
        if current.track.bpm > 0 and upcoming.track.bpm > 0
        else 1.0
    )
    plan = TransitionPlan(
        mix_out_a=selected.t_out,
        mix_in_b=selected.t_in,
        fade_out_start=selected.t_out,
        fade_out_end=fade_out_end,
        overlap=overlap,
        transition_type=transition_type,
        eq_mode=transition_type,
        tempo_ratio=tempo_ratio,
    )
    score = int(round(metrics.overall_score * 100))
    energy_delta = int(round(float(metrics.energy_delta or 0.0)))
    effective_delta, _ = effective_bpm_diff(current.track.bpm, upcoming.track.bpm)
    risk = _categorise_risk_level(
        score, effective_delta, bpm_tolerance, energy_delta
    )
    dj_rec = None
    dj_notes: list[str] = []
    try:
        dj_rec, dj_notes, _dj_overlap = _process_dj_brain_recommendations(
            current.track, upcoming.track
        )
        if dj_rec is not None:
            dj_rec.adjusted_mix_out_a = selected.t_out
            dj_rec.adjusted_mix_in_b = selected.t_in
            dj_rec.overlap_seconds = overlap
            dj_notes = _handoff_pair_point_risks(
                dj_rec,
                current.track,
                upcoming.track,
                selected.t_out,
                selected.t_in,
                dj_notes,
            )
    except Exception as exc:  # DJ-Hinweise duerfen den gueltigen Kandidatenplan nicht kippen
        logger.warning(
            "DJ-Hinweise fuer Result-Kante %s nicht verfuegbar: %s", index, exc
        )
        dj_rec = None
        dj_notes = []
    description = _build_transition_description(
        TransitionDescriptionParams(
            compatibility_score=score,
            bpm_delta=bpm_delta,
            bpm_tolerance=bpm_tolerance,
            energy_delta=energy_delta,
            metrics=legacy_transition_metrics_for_snapshot(metrics),
            from_track=current.track,
            to_track=upcoming.track,
            has_dj_brain=(dj_rec is not None),
        )
    )
    notes = "; ".join(
        part for part in (selected.begruendung, *dj_notes, description) if part
    )
    return ImmutableRecommendationSnapshot(
        index=index,
        from_occurrence_id=current.occurrence_id,
        to_occurrence_id=upcoming.occurrence_id,
        fade_out_start=selected.t_out,
        fade_out_end=fade_out_end,
        fade_in_start=selected.t_in,
        mix_entry=selected.t_in,
        overlap=overlap,
        bpm_delta=bpm_delta,
        energy_delta=energy_delta,
        compatibility_score=score,
        risk_level=risk,
        notes=notes,
        transition_type=transition_type,
        plan=plan,
        candidates=candidates,
        active_candidate_key=selected.key,
        candidate_consistent=consistent,
    )


def legacy_transition_metrics_for_snapshot(
    item: ImmutableMetricsSnapshot,
) -> TransitionMetrics:
    return TransitionMetrics(
        harmonic_score=item.harmonic_score,
        bpm_smoothness=item.bpm_smoothness,
        energy_flow=item.energy_flow,
        genre_compatibility=item.genre_compatibility,
        overall_score=item.overall_score,
        ai_bonus=item.ai_bonus,
        groove_match=item.groove_match,
        bass_continuity=item.bass_continuity,
        timbre_match=item.timbre_match,
        mood_match=item.mood_match,
        loudness_match=item.loudness_match,
        structure_match=item.structure_match,
        energy_delta=item.energy_delta,
        lufs_delta=item.lufs_delta,
        kandidat=item.kandidat.to_dict() if item.kandidat is not None else None,
    )


def _build_generation_result(
    *,
    run_id: str,
    mode: str,
    occurrences: tuple[TrackOccurrence, ...],
    input_tracks: int,
    invalid_bpm_excluded: int,
    bpm_tolerance: float,
    context: dict,
    choice_snapshot: Mapping,
    cancel_check=None,
) -> PlaylistGenerationResult:
    _check_cancel(cancel_check)
    snapshots_by_boundary, mutable_maps, saved_present = _rank_fixed_boundaries(
        occurrences, bpm_tolerance, context, choice_snapshot, cancel_check
    )
    selected, consistencies, link_checks, passed_links, states_retained = (
        _select_snapshot_path(snapshots_by_boundary, occurrences, cancel_check)
    )
    boundaries: list[BoundaryResult] = []
    metrics: list[ImmutableMetricsSnapshot] = []
    recommendations: list[ImmutableRecommendationSnapshot] = []
    for index, candidates in enumerate(snapshots_by_boundary):
        _check_cancel(cancel_check)
        chosen = selected[index]
        consistent = consistencies[index]
        metric = _immutable_metrics_for_snapshot(
            occurrences[index].track,
            occurrences[index + 1].track,
            bpm_tolerance,
            context,
            chosen,
            mutable_maps[index],
        )
        recommendation = _recommendation_snapshot(
            index,
            occurrences,
            candidates,
            chosen,
            metric,
            consistent,
            mutable_maps[index],
            bpm_tolerance,
            context,
        )
        boundary = BoundaryResult(
            index=index,
            from_occurrence_id=occurrences[index].occurrence_id,
            to_occurrence_id=occurrences[index + 1].occurrence_id,
            snapshots=candidates,
            selected=chosen,
            metrics=metric,
            recommendation=recommendation,
            consistent=consistent,
        )
        boundaries.append(boundary)
        metrics.append(metric)
        recommendations.append(recommendation)

    legacy_metrics = [legacy_transition_metrics_for_snapshot(item) for item in metrics]
    _check_cancel(cancel_check)
    quality = calculate_playlist_quality(
        [occurrence.track for occurrence in occurrences],
        bpm_tolerance,
        context,
        transition_metrics=legacy_metrics,
    )
    _check_cancel(cancel_check)
    planned = sum(item is not None for item in selected)
    total = len(snapshots_by_boundary)
    segments = 0
    in_segment = False
    for item in selected:
        _check_cancel(cancel_check)
        if item is not None and not in_segment:
            segments += 1
            in_segment = True
        elif item is None:
            in_segment = False
    saved_honored = sum(
        item is not None and bool(_snapshot_flag(item, "gespeicherte_wahl"))
        for item in selected
    )
    with_candidates = sum(bool(items) for items in snapshots_by_boundary)
    graph_stats = GraphStats(
        input_tracks=input_tracks,
        valid_tracks=len(occurrences),
        invalid_bpm_excluded=invalid_bpm_excluded,
        boundaries_total=total,
        boundaries_with_candidates=with_candidates,
        boundaries_without_candidates=total - with_candidates,
        candidate_snapshots=sum(len(items) for items in snapshots_by_boundary),
        saved_present=saved_present,
    )
    path_stats = PathStats(
        boundaries_total=total,
        with_candidates=with_candidates,
        planned=planned,
        unplanned=total - planned,
        saved_present=saved_present,
        saved_honored=saved_honored,
        link_checks=link_checks,
        consistent_links=passed_links,
        segments=segments,
        segment_restarts=max(segments - 1, 0),
        states_retained=states_retained,
        total_score=sum(item.score for item in selected if item is not None),
    )
    _check_cancel(cancel_check)
    return PlaylistGenerationResult(
        run_id=run_id,
        mode=mode,
        tracks=tuple(occurrence.track for occurrence in occurrences),
        occurrences=occurrences,
        boundaries=tuple(boundaries),
        metrics=tuple(metrics),
        recommendations=tuple(recommendations),
        quality=tuple((str(key), float(value)) for key, value in sorted(quality.items())),
        scoring_context=_freeze_immutable(context),
        candidate_choice_snapshot=_freeze_choice_snapshot(choice_snapshot),
        graph_stats=graph_stats,
        path_stats=path_stats,
        bpm_tolerance=float(bpm_tolerance),
    )


def generate_playlist_result(
    tracks: list[Track],
    mode: str,
    bpm_tolerance: float = PAAR_BPM_MAX,
    advanced_params: Optional[Dict] = None,
    scoring_context: Optional[Dict] = None,
    *,
    candidate_choice_snapshot: Optional[Mapping] = None,
    cancel_check=None,
) -> PlaylistGenerationResult:
    """
    Generates a playlist based on the selected mode and parameters.

    Args:
        tracks: List of Track objects to sort
        mode: Sorting strategy name
        bpm_tolerance: Maximum BPM difference for compatible transitions
        advanced_params: Optional dict with advanced settings:
            - energy_direction: "Auto", "Build Up", "Cool Down", "Maintain"
            - peak_position: 40-80 (percentage for peak placement)
            - harmonic_strictness: 1-10 (weight for harmonic matching)
            - allow_experimental: bool (allow +4/+7 techniques)
            - genre_mixing: bool (enable genre-based sorting)
            - genre_weight: 0.0-1.0 (weight for genre similarity)
        scoring_context: Expliziter, bereits eingefrorener Scoring-Vertrag.
        candidate_choice_snapshot: Optional eingefrorene Kandidatenwahlen vom
            Run-Start. Ohne Wert wird der bisherige Live-Snapshot verwendet.
        cancel_check: Optionaler Callback; ein wahrer Wert bricht kooperativ
            mit ``InterruptedError`` ab.
    """
    from . import candidate_choices

    if (
        isinstance(bpm_tolerance, bool)
        or not isinstance(bpm_tolerance, Real)
        or not math.isfinite(float(bpm_tolerance))
        or float(bpm_tolerance) < 0.0
    ):
        raise ValueError("bpm_tolerance muss endlich und nichtnegativ sein")
    bpm_tolerance = float(bpm_tolerance)
    if not isinstance(mode, str) or not mode.strip():
        raise ValueError("mode muss eine bekannte Playlist-Strategie sein")
    mode = STRATEGY_ALIASES.get(mode, mode)
    if mode not in STRATEGIES:
        raise ValueError(f"Unbekannte Playlist-Strategie: {mode!r}")
    if cancel_check is not None and not callable(cancel_check):
        raise ValueError("cancel_check muss aufrufbar oder None sein")
    _check_cancel(cancel_check)
    if advanced_params is None:
        advanced_snapshot = None
    elif isinstance(advanced_params, Mapping):
        advanced_snapshot = deepcopy(dict(advanced_params))
    else:
        advanced_snapshot = advanced_params
    strategy_config = StrategyConfig.from_mapping(advanced_snapshot)
    if candidate_choice_snapshot is None:
        snapshot_source = candidate_choices.snapshot()
    elif not isinstance(candidate_choice_snapshot, Mapping):
        raise ValueError("candidate_choice_snapshot muss ein Mapping sein")
    else:
        snapshot_source = candidate_choice_snapshot
    frozen_choice_snapshot = _freeze_choice_snapshot(snapshot_source)
    choice_snapshot = _thaw_choice_snapshot(frozen_choice_snapshot)
    run_id = str(uuid.uuid4())
    input_tracks = len(tracks)
    run_context = _complete_run_scoring_context(
        mode, advanced_snapshot, scoring_context
    )

    # Ensure all tracks have a camelot code before sorting
    for track in tracks:
        _check_cancel(cancel_check)
        key_to_camelot(track)

    # Nur unbrauchbare BPM-Werte ausschliessen. Fehlende Keys bleiben erhalten
    # und nutzen den dokumentierten neutralen Harmonic-Fallback.
    valid_tracks: list[Track] = []
    valid_ordinals: list[int] = []
    unresolved_keys = []
    for ordinal, candidate in enumerate(tracks):
        _check_cancel(cancel_check)
        bpm_value = getattr(candidate, "bpm", None)
        try:
            bpm_numeric = float(bpm_value)
        except (TypeError, ValueError):
            logger.warning("Track ohne gueltige BPM ausgeschlossen: %s", candidate.filePath)
            continue

        if not math.isfinite(bpm_numeric) or bpm_numeric <= 0:
            logger.warning("Track ohne positive BPM ausgeschlossen: %s", candidate.filePath)
            continue

        candidate.bpm = bpm_numeric
        valid_tracks.append(candidate)
        valid_ordinals.append(ordinal)
        if not getattr(candidate, "camelotCode", ""):
            unresolved_keys.append(candidate.filePath)

    if unresolved_keys:
        logger.warning(
            "%s Tracks ohne aufloesbaren Key bleiben mit neutralem Fallback enthalten.",
            len(unresolved_keys),
        )

    if not valid_tracks:
        return _build_generation_result(
            run_id=run_id,
            mode=mode,
            occurrences=(),
            input_tracks=input_tracks,
            invalid_bpm_excluded=input_tracks,
            bpm_tolerance=bpm_tolerance,
            context=run_context,
            choice_snapshot=choice_snapshot,
            cancel_check=cancel_check,
        )

    # Get the sorting function from the strategy map
    sorter = STRATEGIES[mode]

    # Initialize thread-local-like cache container
    global _COMPAT_CACHE, _ENHANCED_COMPAT_CACHE
    old_cache = _COMPAT_CACHE
    old_enhanced_cache = _ENHANCED_COMPAT_CACHE
    _COMPAT_CACHE = {}
    _ENHANCED_COMPAT_CACHE = {}

    try:
        # Call the selected sorting strategy with advanced params
        effective_config = strategy_config.effective_kwargs(mode)
        sorter_params = deepcopy(effective_config)
        sorter_params.update(run_context)
        sorter_params["candidate_choice_snapshot"] = choice_snapshot
        sorter_params["cancel_check"] = cancel_check
        logger.info("Effektive Strategieparameter %s: %s", mode, effective_config)
        sorted_tracks = sorter(
            valid_tracks, bpm_tolerance=bpm_tolerance, **sorter_params
        )
    finally:
        # Restore old cache containers (usually None)
        _COMPAT_CACHE = old_cache
        _ENHANCED_COMPAT_CACHE = old_enhanced_cache

    pools: dict[int, list[int]] = {}
    for ordinal, track in zip(valid_ordinals, valid_tracks):
        _check_cancel(cancel_check)
        pools.setdefault(id(track), []).append(ordinal)
    occurrences: list[TrackOccurrence] = []
    for track in sorted_tracks:
        _check_cancel(cancel_check)
        ordinals = pools.get(id(track), [])
        if not ordinals:
            raise RuntimeError(
                "Strategie-Ergebnis ist keine exakte Occurrence-Permutation"
            )
        occurrences.append(
            TrackOccurrence(run_id=run_id, ordinal=ordinals.pop(0), track=track)
        )
    if len(occurrences) != len(valid_tracks) or any(pools.values()):
        raise RuntimeError(
            "Strategie-Ergebnis hat Tracks verloren oder hinzugefuegt"
        )

    generation_result = _build_generation_result(
        run_id=run_id,
        mode=mode,
        occurrences=tuple(occurrences),
        input_tracks=input_tracks,
        invalid_bpm_excluded=input_tracks - len(valid_tracks),
        bpm_tolerance=bpm_tolerance,
        context=run_context,
        choice_snapshot=choice_snapshot,
        cancel_check=cancel_check,
    )
    quality = generation_result.quality_dict()
    logger.info(
        f"Playlist-Qualitaet ({mode}): "
        f"Score={quality['overall_score']:.2f}, "
        f"Harmonic={quality['harmonic_flow']:.2f}, "
        f"Energy={quality['energy_consistency']:.2f}, "
        f"BPM={quality['bpm_smoothness']:.2f}"
    )

    _check_cancel(cancel_check)
    return generation_result


def generate_playlist(
    tracks: list[Track],
    mode: str,
    bpm_tolerance: float = PAAR_BPM_MAX,
    advanced_params: Optional[Dict] = None,
    scoring_context: Optional[Dict] = None,
    *,
    candidate_choice_snapshot: Optional[Mapping] = None,
) -> list[Track]:
    """Kompatibler Listen-Wrapper um den einen GenerationResult-Lauf."""
    return list(
        generate_playlist_result(
            tracks,
            mode,
            bpm_tolerance,
            advanced_params,
            scoring_context,
            candidate_choice_snapshot=candidate_choice_snapshot,
        ).tracks
    )


def rebuild_result_for_order(
    previous_result: PlaylistGenerationResult,
    ordered_occurrence_ids,
    choice_snapshot: Optional[Mapping] = None,
) -> PlaylistGenerationResult:
    """Baut nur Kanten neu; Trackstrategie und Occurrence-IDs bleiben unangetastet."""
    requested = tuple(tuple(item) for item in ordered_occurrence_ids)
    existing = tuple(
        occurrence.occurrence_id for occurrence in previous_result.occurrences
    )
    if len(set(requested)) != len(requested):
        raise ValueError("Occurrence-ID-Permutation darf keine Duplikate enthalten")
    if len(requested) != len(existing) or set(requested) != set(existing):
        raise ValueError(
            "ordered_occurrence_ids muss eine exakte Occurrence-ID-Permutation sein"
        )
    by_id = {
        occurrence.occurrence_id: occurrence
        for occurrence in previous_result.occurrences
    }
    selected_choices = (
        previous_result.candidate_choice_snapshot_dict()
        if choice_snapshot is None
        else choice_snapshot
    )
    if not isinstance(selected_choices, Mapping):
        raise ValueError("choice_snapshot muss ein Mapping sein")
    selected_choices = _thaw_choice_snapshot(
        _freeze_choice_snapshot(selected_choices)
    )
    return _build_generation_result(
        run_id=previous_result.run_id,
        mode=previous_result.mode,
        occurrences=tuple(by_id[item] for item in requested),
        input_tracks=previous_result.graph_stats.input_tracks,
        invalid_bpm_excluded=previous_result.graph_stats.invalid_bpm_excluded,
        bpm_tolerance=previous_result.bpm_tolerance,
        context=previous_result.scoring_context_dict(),
        choice_snapshot=selected_choices,
    )


def benchmark_algorithms(
    tracks: list[Track], bpm_tolerance: float = 3.0
) -> Dict[str, Dict[str, float]]:
    """Benchmark all algorithms and return quality metrics comparison."""
    results = {}

    for strategy_name in STRATEGIES.keys():
        playlist = generate_playlist(tracks, strategy_name, bpm_tolerance)
        quality_metrics = calculate_playlist_quality(playlist, bpm_tolerance)
        results[strategy_name] = quality_metrics

    return results


# === Set-Timing / Time-based Planning ===


@dataclass
class SetTimeline:
    """Zeitplanung fuer ein DJ-Set."""

    total_duration_minutes: float  # Gesamtlaenge in Minuten
    target_duration_minutes: float  # Gewuenschte Laenge
    peak_position_minutes: float  # Peak-Zeitpunkt
    entries: list  # Liste von SetTimelineEntry dicts
    overflow_minutes: float  # Ueberschuss/Defizit in Minuten


@dataclass
class SetTimelineEntry:
    """Ein Track-Eintrag in der Set-Timeline."""

    track: Track
    start_time: float  # Start in Sekunden
    end_time: float  # Ende der hoerbaren Trackstrecke in Set-Sekunden
    playing_duration: float  # Effektive Spieldauer in Sekunden
    overlap_with_next: float  # Overlap in Sekunden zum naechsten Track
    is_peak: bool  # Ist dieser Track am Peak-Punkt?
    energy_phase: str  # "intro", "warmup", "build", "peak", "sustain", "cooldown"
    transition_planned: Optional[bool] = None  # True/False; letzter Track None


def _timeline_track_duration(track: Track, index: int) -> float:
    """Liefert eine echte, positive Trackdauer oder bricht sichtbar ab."""
    try:
        duration = float(track.duration)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Track {index + 1}: ungueltige Dauer") from exc
    if not math.isfinite(duration) or duration <= 0.0:
        raise ValueError(f"Track {index + 1}: Dauer muss endlich und positiv sein")
    return duration


def _validated_timeline_plan(
    plan: TransitionPlan,
    edge_index: int,
    duration_a: float,
    duration_b: float,
) -> tuple[float, float, float]:
    """Validiert den unveraendert zu uebernehmenden Plan einer Kante."""
    edge = f"Kante {edge_index + 1}->{edge_index + 2}"
    try:
        mix_out = float(plan.mix_out_a)
        mix_in = float(plan.mix_in_b)
        overlap = float(plan.overlap)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{edge}: unvollstaendiger TransitionPlan") from exc

    if not all(math.isfinite(value) for value in (mix_out, mix_in, overlap)):
        raise ValueError(f"{edge}: TransitionPlan enthaelt nicht-endliche Werte")
    if overlap <= 0.0:
        raise ValueError(f"{edge}: Overlap muss positiv sein")
    if not (0.0 <= mix_out and mix_out + overlap <= duration_a):
        raise ValueError(f"{edge}: Mix-Out oder Overlap liegt ausserhalb von Track A")
    if not (0.0 <= mix_in and mix_in + overlap <= duration_b):
        raise ValueError(f"{edge}: Mix-In oder Overlap liegt ausserhalb von Track B")
    return mix_out, mix_in, overlap


def _calculate_timeline_entries(
    tracks: list[Track], default_overlap: float,
    transition_plans: Optional[list[TransitionPlan]] = None,
) -> tuple[list[SetTimelineEntry], float]:
    """Berechnet die Timeline ausschliesslich aus gueltigen Plaenen.

    Eine planlose Kante spielt den aktuellen Track bis zum echten Ende und
    hat keinen erfundenen Overlap. Planwerte bleiben exakt; ungueltige Plaene
    werden nicht geklemmt oder durch Analysewerte ersetzt.
    """
    del default_overlap  # Oeffentlicher Legacy-Parameter; kein Timing-Fallback.
    entries: list[SetTimelineEntry] = []
    current_time = 0.0
    n = len(tracks)
    durations = [
        _timeline_track_duration(track, i) for i, track in enumerate(tracks)
    ]
    plans: list[Optional[tuple[float, float, float]]] = [None] * max(0, n - 1)

    for edge_index in range(n - 1):
        plan = (
            transition_plans[edge_index]
            if transition_plans is not None and edge_index < len(transition_plans)
            else None
        )
        if plan is not None:
            plans[edge_index] = _validated_timeline_plan(
                plan, edge_index, durations[edge_index], durations[edge_index + 1]
            )

    for index in range(1, n - 1):
        incoming = plans[index - 1]
        outgoing = plans[index]
        if incoming is not None and outgoing is not None:
            incoming_mix_in = incoming[1]
            outgoing_mix_out = outgoing[0]
            if not incoming_mix_in < outgoing_mix_out:
                raise ValueError(
                    f"Track {index + 1}: eingehender Mix-In muss vor "
                    "ausgehendem Mix-Out liegen"
                )

    for i, track in enumerate(tracks):
        track_dur = durations[i]
        plan_in = plans[i - 1] if i > 0 else None
        plan_out = plans[i] if i < n - 1 else None
        mix_in = plan_in[1] if plan_in is not None else 0.0
        mix_out = plan_out[0] if plan_out is not None else track_dur

        if plan_out is not None:
            overlap = plan_out[2]
            playing_duration = mix_out - mix_in + overlap
            transition_planned: Optional[bool] = True
        else:
            overlap = 0.0
            playing_duration = track_dur - mix_in
            transition_planned = False if i < n - 1 else None

        end_time = current_time + playing_duration
        next_start = current_time + mix_out - mix_in

        entries.append(
            SetTimelineEntry(
                track=track,
                start_time=current_time,
                end_time=end_time,
                playing_duration=playing_duration,
                overlap_with_next=overlap,
                is_peak=False,  # Wird spaeter gesetzt
                energy_phase="build",  # Wird spaeter gesetzt
                transition_planned=transition_planned,
            )
        )

        current_time = next_start

    total = entries[-1].end_time if entries else 0.0
    return entries, total


def _identify_peak_track(
    entries: list[SetTimelineEntry], total_seconds: float, peak_position_pct: float
) -> int:
    """Findet den Index des Peak-Tracks."""
    if not entries:
        return 0

    peak_time = total_seconds * peak_position_pct
    best_peak_idx = 0
    best_peak_score = -1.0

    for i, entry in enumerate(entries):
        mid = (entry.start_time + entry.end_time) / 2.0
        # Score: Energie * (1 - Abstand zum Peak-Zeitpunkt)
        time_factor = 1.0 - min(abs(mid - peak_time) / max(total_seconds, 1.0), 1.0)
        energy_factor = entry.track.energy / 100.0
        score = energy_factor * 0.6 + time_factor * 0.4
        if score > best_peak_score:
            best_peak_score = score
            best_peak_idx = i

    entries[best_peak_idx].is_peak = True
    return best_peak_idx


def _assign_energy_phases(entries: list[SetTimelineEntry], best_peak_idx: int) -> None:
    """Weist jedem Track eine Energy-Phase zu."""
    n = len(entries)
    if n == 0:
        return

    peak_pos = best_peak_idx / max(n - 1, 1)
    for i, entry in enumerate(entries):
        relative_pos = i / max(n - 1, 1)
        if entry.is_peak:
            entry.energy_phase = "peak"
        elif i == 0:
            entry.energy_phase = "intro"
        elif i == n - 1:
            entry.energy_phase = "cooldown"
        elif relative_pos < peak_pos * 0.5:
            # L3-Fix: echte Warm-up-Phase — vorher lieferten beide Branches
            # "build" und der finale else-Zweig war unerreichbar
            entry.energy_phase = "warmup"
        elif relative_pos <= peak_pos:
            entry.energy_phase = "build"
        elif relative_pos <= peak_pos + 0.15:
            entry.energy_phase = "sustain"
        else:
            entry.energy_phase = "cooldown"


def compute_set_timeline(
    tracks: list[Track],
    target_minutes: float = 60.0,
    peak_position_pct: float = 0.65,
    default_overlap: float = 16.0,
    transition_plans: Optional[list[TransitionPlan]] = None,
) -> SetTimeline:
    """
    Berechnet eine zeitbasierte Timeline fuer ein DJ-Set.

    Jeder Track bekommt einen Start/Ende-Zeitpunkt. Gesamtlaenge = Summe
    der Stuecke Mix-In..Mix-Out (erster Track ab 0, letzter bis zum Ende),
    Geplante Eintraege ueberlappen um den Plan-Overlap; ungeplante Kanten
    spielen ohne erfundene Blende bis zum Trackende.
    Der Peak-Track wird identifiziert.

    Args:
      tracks: Sortierte Playlist
      target_minutes: Gewuenschte Set-Laenge in Minuten
      peak_position_pct: Peak-Position als Anteil (0.0-1.0, default 0.65)
      default_overlap: Oeffentlicher Legacy-Parameter; ohne Plan keine Blende

    Returns:
      SetTimeline mit allen Eintraegen
    """
    if not tracks:
        return SetTimeline(
            total_duration_minutes=0.0,
            target_duration_minutes=target_minutes,
            peak_position_minutes=0.0,
            entries=[],
            overflow_minutes=0.0,
        )

    peak_position_pct = max(0.1, min(0.9, peak_position_pct))

    entries, total_seconds = _calculate_timeline_entries(
        tracks, default_overlap, transition_plans
    )
    best_peak_idx = _identify_peak_track(entries, total_seconds, peak_position_pct)
    _assign_energy_phases(entries, best_peak_idx)

    total_minutes = total_seconds / 60.0
    peak_minutes = entries[best_peak_idx].start_time / 60.0 if entries else 0.0

    return SetTimeline(
        total_duration_minutes=total_minutes,
        target_duration_minutes=target_minutes,
        peak_position_minutes=peak_minutes,
        entries=entries,
        overflow_minutes=total_minutes - target_minutes,
    )


def get_set_timing_summary(timeline: SetTimeline) -> dict:
    """
    Erstellt eine menschenlesbare Zusammenfassung der Set-Timeline.

    Returns:
      Dict mit: total_time, target_time, overflow, peak_track, peak_time,
      phase_breakdown, track_count, avg_track_duration
    """
    if not timeline.entries:
        return {
            "total_time": "0:00",
            "target_time": f"{timeline.target_duration_minutes:.0f}:00",
            "overflow": "0:00",
            "overflow_seconds": 0.0,
            "peak_track": None,
            "peak_time": "0:00",
            "phase_breakdown": {},
            "track_count": 0,
            "avg_track_duration": 0.0,
        }

    total_sec = timeline.total_duration_minutes * 60
    target_sec = timeline.target_duration_minutes * 60
    overflow_sec = timeline.overflow_minutes * 60

    # Formatiere Zeiten
    def _fmt(seconds: float) -> str:
        sign = "-" if seconds < 0 else ""
        s = abs(seconds)
        m = int(s // 60)
        sec = int(s % 60)
        return f"{sign}{m}:{sec:02d}"

    # Peak-Track finden
    peak_entry = next((e for e in timeline.entries if e.is_peak), None)
    peak_track_name = peak_entry.track.title if peak_entry else "?"
    peak_time = _fmt(peak_entry.start_time) if peak_entry else "0:00"

    # Phasen-Breakdown
    phases: dict[str, int] = {}
    for entry in timeline.entries:
        phases[entry.energy_phase] = phases.get(entry.energy_phase, 0) + 1

    # Durchschnittliche Track-Dauer
    durations = [e.playing_duration for e in timeline.entries]
    avg_dur = sum(durations) / len(durations) if durations else 0

    return {
        "total_time": _fmt(total_sec),
        "target_time": _fmt(target_sec),
        "overflow": _fmt(overflow_sec),
        "overflow_seconds": overflow_sec,
        "peak_track": peak_track_name,
        "peak_time": peak_time,
        "phase_breakdown": phases,
        "track_count": len(timeline.entries),
        "avg_track_duration": avg_dur,
    }
