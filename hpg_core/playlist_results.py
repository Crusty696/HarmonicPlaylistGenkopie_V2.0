"""Gemeinsame Ergebnisverträge ohne Abhängigkeit von der Playlist-Suche."""
from __future__ import annotations

import math
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, TYPE_CHECKING
from .models import Track

if TYPE_CHECKING:
    from .dj_brain import DJRecommendation
    from .pair_candidates import CandidateSnapshot

class _FrozenMapping(tuple):
    """Markiert eingefrorene Mappings, auch wenn sie leer sind."""


class _FrozenSequence(tuple):
    """Markiert eingefrorene Sequenzen, auch wenn sie leer sind."""


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
    # Optionaler, lokaler Stem-Kandidat als Anteil der Blende (0..1).
    # Er steuert nur die Preview-Rampe und ist keine kalibrierte Aussage.
    bass_swap_fraction: float | None = None

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
