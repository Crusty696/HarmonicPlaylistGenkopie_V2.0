from .models import (
    Track,
    key_to_camelot,
    effective_bpm_diff,
    get_camelot_components,
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
    TRANSITION_FEATURES_ENABLED,
)
from .genres import CANONICAL_GENRES
from .tolerances import get_tolerances

# Fuer den Genre-Aufloesungs-Check in calculate_enhanced_compatibility:
# derselbe casefold wie in dj_brain.get_genre_compatibility.
_CANONICAL_CASEFOLD = frozenset(g.casefold() for g in CANONICAL_GENRES)
from .transition_features import (
    bass_continuity,
    groove_match,
    mood_match,
    timbre_match,
)
import logging
import heapq
import math
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# AUDIT-FIX D6/F28 (2026-07-24): vormals hartkodierte Scoring-Konstanten
# (Magic Numbers) zentralisiert. Bei Bedarf spaeter nach config.py heben.
SMOOTHING_ENERGY_DISRUPTION_MAX = 20  # max. Energiesprung fuer harmonischen Swap
SMOOTHING_MAX_ITERATIONS = 3          # Passes im harmonic-smoothing-Loop
LOOKAHEAD_FUTURE_WEIGHT = 0.7         # Gewicht des Lookahead-Zukunftsterms
VOCAL_CLASH_PENALTY = 0.06            # Abzug wenn BEIDE Tracks vocal sind (D2-light)


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
    overlap: float = 16.0

    @classmethod
    def from_mapping(cls, values: Optional[Dict]) -> "StrategyConfig":
        source = values or {}
        return cls(
            energy_direction=str(source.get("energy_direction", "Auto")),
            peak_position=max(40, min(80, int(source.get("peak_position", 70)))),
            harmonic_strictness=max(
                1, min(10, int(source.get("harmonic_strictness", 7)))
            ),
            allow_experimental=bool(source.get("allow_experimental", True)),
            genre_mixing=bool(source.get("genre_mixing", True)),
            genre_weight=max(0.0, min(1.0, float(source.get("genre_weight", 0.3)))),
            target_energy=(
                None
                if source.get("target_energy") is None
                else max(0.0, min(100.0, float(source["target_energy"])))
            ),
            overlap=max(4.0, min(64.0, float(source.get("overlap", 16.0)))),
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
            "overlap": self.overlap,
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
    # Vier neue Transition-Faktoren (nur befuellt bei TRANSITION_FEATURES_ENABLED).
    # None = nicht bestimmbar (Umverteilung): der Faktor faellt samt Gewicht aus
    # der gewichteten Summe, statt als 0 still zu bestrafen.
    groove_match: Optional[float] = None
    bass_continuity: Optional[float] = None
    timbre_match: Optional[float] = None
    mood_match: Optional[float] = None


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


def _track_cache_key(track: Track) -> str | int:
    """Liefert eine stabile Identitaet fuer Scoring-Caches und Entnahmen."""
    track_id = getattr(track, "track_id", None)
    return track_id if track_id else id(track)


def _remove_track(items: list[Track], target: Track) -> None:
    """Entfernt einen Track ohne den teuren Deep-Vergleich der Track-Dataclass."""
    target_key = _track_cache_key(target)
    for index, candidate in enumerate(items):
        if candidate is target or _track_cache_key(candidate) == target_key:
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
    direction = (
        energy_direction.value
        if isinstance(energy_direction, EnergyDirection)
        else str(energy_direction)
    )
    options = tuple(sorted((key, repr(value)) for key, value in kwargs.items()))
    return (
        _track_cache_key(track1),
        _track_cache_key(track2),
        float(bpm_tolerance),
        direction,
        options,
    )


def calculate_ai_compatibility_bonus(track1: Track, track2: Track) -> float:
    """Liefert den einzigen KI-Bonus als normierten Wert von 0 bis 0.14.

    HPG-002-Fix: Bonus nur bei gueltiger, aktueller Provenienz beider Tracks —
    beliebige oder veraltete ai_metadata ergeben deterministisch 0.0.
    """
    # Lazy-Import: ai_engine zieht requests, das Core-Scoring soll ohne laufen.
    # MED-Fix: defensiv importieren — ein Fehler in ai_engine (fehlendes
    # requests, kaputter Import) darf nicht die gesamte Scoring-Kette (und damit
    # alle Sortier-Strategien) abbrechen; dann verhaelt es sich wie dokumentiert
    # (kein KI-Bonus -> 0.0).
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


def calculate_enhanced_compatibility(
    track1: Track,
    track2: Track,
    bpm_tolerance: float,
    energy_direction: Optional[EnergyDirection] = None,
    **kwargs,
) -> TransitionMetrics:
    """Enhanced compatibility calculation with multiple factors."""

    cache_key = _enhanced_cache_key(
        track1, track2, bpm_tolerance, energy_direction, kwargs
    )
    if _ENHANCED_COMPAT_CACHE is not None:
        cached = _ENHANCED_COMPAT_CACHE.get(cache_key)
        if cached is not None:
            return cached

    # AUDIT-FIX F06 (2026-07-24): energy_direction kommt aus den Strategien als
    # STRING ("Build Up"/"Cool Down"/"Maintain") ueber **kwargs an den
    # Enum-Parameter — vorher band der String dort still an und ALLE
    # Enum-Vergleiche schlugen fehl (energy_flow degradierte stumm zum
    # else-Zweig). Jetzt: String defensiv auf den Enum mappen.
    if isinstance(energy_direction, str):
        energy_direction = {
            "Build Up": EnergyDirection.UP,
            "up": EnergyDirection.UP,
            "Cool Down": EnergyDirection.DOWN,
            "down": EnergyDirection.DOWN,
            "Maintain": EnergyDirection.MAINTAIN,
            "maintain": EnergyDirection.MAINTAIN,
        }.get(energy_direction, None)

    # Basic harmonic compatibility
    # M2-Fix: kwargs (harmonic_strictness, allow_experimental) durchreichen —
    # vorher fielen die UI-Parameter im Enhanced-Pfad auf Defaults zurueck
    harmonic_score = _calculate_compatibility_inner(
        track1, track2, bpm_tolerance, **kwargs
    )

    # BPM smoothness (exponential decay, mit Half/Double-Erkennung)
    bpm_diff, _ = effective_bpm_diff(track1.bpm, track2.bpm)
    if bpm_diff > bpm_tolerance:
        bpm_smoothness = 0.0
    else:
        # Audit-Fix 2026-07-21: bpm_tolerance==0 ergab exp(-0/0) -> ZeroDivisionError.
        # calculate_playlist_quality gated bereits <=0; der Enhanced-Pfad jetzt auch.
        denom = max(bpm_tolerance / 2, 1e-9)
        bpm_smoothness = math.exp(-bpm_diff / denom)

    # Energy flow analysis
    energy_diff = track2.energy - track1.energy
    # M12-Fix: alle Zweige liefern [0,1] — vorher lief UP/DOWN bis 2.0 und
    # MAINTAIN unter 0, was die Gewichtung im overall_score verzerrte
    if energy_direction == EnergyDirection.UP:
        energy_flow = min(1.0, max(0.0, energy_diff) / 50.0)
    elif energy_direction == EnergyDirection.DOWN:
        energy_flow = min(1.0, max(0.0, -energy_diff) / 50.0)
    elif energy_direction == EnergyDirection.MAINTAIN:
        energy_flow = max(0.0, 1.0 - abs(energy_diff) / 50.0)
    else:
        energy_flow = max(0.0, 1.0 - abs(energy_diff) / 100.0)  # Gentle energy preference

    # Genre compatibility - DJ Brain Matrix wenn detected_genre vorhanden
    # AUDIT-FIX F12 (2026-07-24): detected_genre-Default "Unknown" ist TRUTHY,
    # der bisherige `or`-Fallback auf das ID3-Genre war damit toter Code —
    # Tracks mit sauberem ID3-Genre, aber ohne DJ-Brain-Klassifikation,
    # bekamen konstant 0.5-Kompatibilitaet. Explizit aufloesen.
    def _resolve_genre(t: Track) -> str:
        dg = getattr(t, "detected_genre", "") or ""
        if dg and dg != "Unknown":
            return dg
        return t.genre if (t.genre and t.genre != "Unknown") else "Unknown"

    genre_a = _resolve_genre(track1)
    genre_b = _resolve_genre(track2)
    genre_compatibility = get_genre_compatibility(genre_a, genre_b)

    # Genre-Weight hoeher wenn ueberhaupt aufgeloeste Genre-Daten vorhanden
    # (gleiche Quelle wie der Score — vorher zwei divergierende Kriterien).
    has_dj_brain_genres = genre_a != "Unknown" and genre_b != "Unknown"
    genre_weight = (
        GENRE_WEIGHT_WITH_DJ_BRAIN
        if has_dj_brain_genres
        else GENRE_WEIGHT_WITHOUT_DJ_BRAIN
    )
    remaining = 1.0 - genre_weight

    # Overall weighted score
    groove_val = bass_val = timbre_val = mood_val = None

    if TRANSITION_FEATURES_ENABLED:
        # genre_a (abgehender Track) setzt den Kontext des Uebergangs.
        tol = get_tolerances(genre_a)
        # Nicht aufgeloestes Genre: Gewicht halbieren. Der Altpfad tat das
        # fuer "Unknown" ueber GENRE_WEIGHT_WITHOUT_DJ_BRAIN (0.1 statt 0.2);
        # hier gilt es zusaetzlich fuer nicht-kanonische Tags wie "House",
        # denen get_genre_compatibility denselben 0.5-Fallback gibt — auf
        # vollem Gewicht verloeren zwei identische Tracks damit Punkte, die
        # sie nicht verdienen (test_two_identical_tracks, gemessen:
        # Altpfad 0.90, neuer Pfad ohne Halbierung 0.88, mit 0.93).
        # combine_weighted renormiert auf die verbleibende Gewichtssumme.
        # Vergleich casefold, weil get_genre_compatibility (dj_brain.py)
        # Genres ebenfalls casefold aufloest — sonst bekaeme ein ID3-Tag
        # "psytrance" den echten Matrix-Score bei halbiertem Gewicht.
        genres_aufgeloest = (
            has_dj_brain_genres
            and genre_a.casefold() in _CANONICAL_CASEFOLD
            and genre_b.casefold() in _CANONICAL_CASEFOLD
        )
        genre_tol_weight = (
            tol["genre_weight"]
            if genres_aufgeloest
            else tol["genre_weight"] * (
                GENRE_WEIGHT_WITHOUT_DJ_BRAIN / GENRE_WEIGHT_WITH_DJ_BRAIN
            )
        )
        groove_val = groove_match(track1, track2, genre_a)
        bass_val = bass_continuity(track1, track2, genre_a)
        timbre_val = timbre_match(track1, track2, genre_a)
        mood_val = mood_match(track1, track2, genre_a)
        overall_score = combine_weighted(
            {
                "harmonic": harmonic_score / 100.0,
                "bpm": bpm_smoothness,
                "energy": energy_flow,
                "genre": genre_compatibility,
                "groove": groove_val,
                "bass": bass_val,
                "timbre": timbre_val,
                "mood": mood_val,
            },
            {
                "harmonic": tol["harmonic_weight"],
                "bpm": tol["bpm_weight"],
                "energy": tol["energy_weight"],
                "genre": genre_tol_weight,
                "groove": tol["groove_weight"],
                "bass": tol["bass_weight"],
                "timbre": tol["timbre_weight"],
                "mood": tol["mood_weight"],
            },
        )
    else:
        # Unveraenderter Altpfad — Referenz fuer den Regressionstest.
        overall_score = (
            (remaining * 0.44) * (harmonic_score / 100.0)
            + (remaining * 0.28) * bpm_smoothness
            + (remaining * 0.28) * energy_flow
            + genre_weight * genre_compatibility
        )

    ai_bonus = calculate_ai_compatibility_bonus(track1, track2)
    overall_score = min(1.0, overall_score + ai_bonus)

    # AUDIT-FIX D2-light (2026-07-26): Vocal-Clash-Penalty. Zwei Lead-Vocals
    # uebereinander sind einer der haeufigsten Mixfehler; das Feld
    # vocal_instrumental hatte bisher KEINEN Scoring-Consumer. Konservativ:
    # nur wenn BEIDE Tracks als "vocal" erkannt sind (Heuristik ist auf
    # 22kHz-Mono unsicher, "unknown" wird nie bestraft).
    if (
        getattr(track1, "vocal_instrumental", "unknown") == "vocal"
        and getattr(track2, "vocal_instrumental", "unknown") == "vocal"
    ):
        overall_score = max(0.0, overall_score - VOCAL_CLASH_PENALTY)

    # BPM-Hard-Gate (Audit 2026-07-17): ein am Pitchfader unmixbarer Sprung
    # darf nicht ueber Genre/Energie auf ~40% "gerettet" werden — die 0-100-
    # Strategien gaten hart, Enhanced muss dieselbe Grundentscheidung treffen
    if bpm_diff > bpm_tolerance:
        overall_score = 0.0

    metrics = TransitionMetrics(
        harmonic_score=harmonic_score,
        bpm_smoothness=bpm_smoothness,
        energy_flow=energy_flow,
        genre_compatibility=genre_compatibility,
        overall_score=overall_score,
        ai_bonus=ai_bonus,
        groove_match=groove_val,
        bass_continuity=bass_val,
        timbre_match=timbre_val,
        mood_match=mood_val,
    )
    if _ENHANCED_COMPAT_CACHE is not None:
        _ENHANCED_COMPAT_CACHE[cache_key] = metrics
    return metrics


def calculate_transition_objective(
    track1: Track, track2: Track, bpm_tolerance: float, **kwargs
) -> int:
    """Gemeinsame Zielfunktion fuer Sortierung, Anzeige und Empfehlungen."""
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
    if not track1.camelotCode or not track2.camelotCode:
        # Half/Double-Time Penalty fuer fehlende Harmonic-Daten
        base = 10
        if bpm_relation != "direct":
            base = int(base * BPM_HALF_DOUBLE_PENALTY)
        return base

    num1, letter1 = _get_camelot_components(track1.camelotCode)
    num2, letter2 = _get_camelot_components(track2.camelotCode)

    if num1 == 0 or num2 == 0:  # Invalid camelot codes
        # AUDIT-FIX F21 (2026-07-24): Half/Double-Penalty konsistent anwenden
        # (der strukturgleiche Zweig oben bei fehlendem Code tut es auch).
        base = 10
        if bpm_relation != "direct":
            base = int(base * BPM_HALF_DOUBLE_PENALTY)
        return base

    # Half/Double-Time Penalty-Faktor
    penalty = BPM_HALF_DOUBLE_PENALTY if bpm_relation != "direct" else 1.0

    # Direct matches (always allowed)
    if num1 == num2 and letter1 == letter2:
        return int(100 * penalty)  # Same key
    if num1 == num2 and letter1 != letter2:
        # H4-Fix: richtungsabhaengig — Moll->Dur (A->B) wirkt als Energy-Boost,
        # Dur->Moll (B->A) als leichter Energy-Drop. Vorher fing diese Regel
        # beide Richtungen mit 90 ab und der Boost/Drop-Code weiter unten war tot.
        if letter1 == "A" and letter2 == "B":
            return int(90 * penalty)  # Relative minor -> major (Energy Boost)
        return int(85 * penalty)  # Relative major -> minor (Energy Drop)

    # Adjacent keys (Camelot wheel)
    next_num_cw = (num1 % 12) + 1
    next_num_ccw = (num1 - 2 + 12) % 12 + 1

    if letter1 == letter2:  # Same mode, adjacent numbers
        if num2 == next_num_cw or num2 == next_num_ccw:
            return int(80 * penalty)

    # H5-Fix: strictness wirkt jetzt auch auf die lockeren Kategorien
    # (experimentell/diagonal), nicht nur auf den Fallback-Score.
    # Default 7 = neutral (Faktor 1.0), 10 = streng, 1 = locker.
    # AUDIT-FIX F03 (2026-07-24): Obergrenze 1.0 statt 1.2 — eine experimentelle
    # Technik darf den sicheren ±1-Nachbarn (feste 80) NIE ueberholen. Vorher
    # wurde +4 bei strictness<=5 zu 84 und schlug den Quintschritt.
    loose_factor = max(0.4, min(1.0, 1.0 - (strictness - 7) * 0.08))

    # AUDIT-FIX F04 (2026-07-24): "+2 Energy Boost" (8A->10A, Ganztonschritt)
    # war komplett unbekannt und fiel in den Rest-Zweig (Score wie ein echter
    # Key-Clash). Als eigene Technik zwischen ±1 (80) und +4 (70) einordnen.
    plus_two_num = (num1 + 2 - 1) % 12 + 1
    if num2 == plus_two_num and letter1 == letter2:
        return int(75 * penalty * loose_factor)

    # Experimental techniques (can be disabled)
    if allow_experimental:
        # Plus Four Technique (e.g., 8A -> 12A)
        plus_four_num = (num1 + 4 - 1) % 12 + 1
        if num2 == plus_four_num and letter1 == letter2:
            return int(70 * penalty * loose_factor)

        # Plus Seven Technique (+7 Camelot-Positionen — energetischer
        # "Mood-Shift", deutlich dissonanter als der ±1-Quintschritt)
        plus_seven_num = (num1 + 7 - 1) % 12 + 1
        if num2 == plus_seven_num and letter1 == letter2:
            return int(65 * penalty * loose_factor)

    # Diagonal Mixing
    if letter1 != letter2:
        if num2 == next_num_cw or num2 == next_num_ccw:
            return int(60 * penalty * loose_factor)

    # Return low score (affected by strictness - stricter = lower fallback)
    return max(5, int((15 - strictness) * penalty))


# Global thread-local-like cache containers for the current playlist generation
# session. They remain opt-in so direct API calls preserve their existing behavior.
#
# Context Flow und die Genre-Flow-Gruppengrenzen nutzen bewusst die reine
# Harmonik und damit _COMPAT_CACHE. Die uebrigen Strategien verwenden die
# erweiterte Zielfunktion und _ENHANCED_COMPAT_CACHE.
_ENHANCED_COMPAT_CACHE = None
_COMPAT_CACHE = None


def calculate_compatibility(
    track1: Track, track2: Track, bpm_tolerance: float, **kwargs
) -> int:
    """Wrapper around _calculate_compatibility_inner that uses a global dictionary cache
    if one is currently set up by generate_playlist or benchmark.

    AUDIT-FIX F05 (2026-07-24): Der KI-Bonus wird hier NICHT mehr addiert.
    Vorher blies er die 0-100-Harmonik-Skala auf (bis +14), waehrend
    calculate_enhanced_compatibility den Bonus separat aufs Overall addiert —
    doppelte Zaehlung. predict_transition_type entschied dadurch ueber einen
    verfaelschten Score, und calculate_playlist_quality verbuchte KI-Stimmung
    als Harmonik. Dieser Wrapper liefert jetzt reine harmonische Kompatibilitaet.
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


def _sort_harmonic_flow(
    tracks: list[Track], bpm_tolerance: float, **kwargs
) -> list[Track]:
    """Enhanced harmonic flow using look-ahead and backtracking to avoid local optima."""
    if len(tracks) <= 2:
        return sorted(tracks, key=lambda t: t.bpm)

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
        track = tracks[i]
        total_compatibility = 0
        connections = 0

        for j in comparison_indices:
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
    """Sortiert BPM-richtungsgebunden und nutzt Harmonik nur bei Gleichstand."""
    if len(tracks) <= 1:
        return list(tracks)

    bpm_ordered = sorted(tracks, key=lambda track: track.bpm, reverse=reverse)
    result: list[Track] = []
    position = 0

    while position < len(bpm_ordered):
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
    if not tracks:
        return []

    if len(tracks) <= 3:
        return sorted(tracks, key=lambda t: t.bpm + t.energy)

    # Get peak position from advanced params (default: 70%)
    peak_position = kwargs.get("peak_position", 70) / 100.0

    scored_tracks = _prepare_track_metrics(tracks)
    count = len(scored_tracks)

    # Create a double-peak curve for longer sets
    peak_curve = []
    for idx in range(count):
        # Create asymmetric curve: slow build, sharp peak, controlled decline
        if idx < count * peak_position:  # Build phase (user-defined)
            curve_val = (idx / (count * peak_position)) ** 1.5  # Exponential build
        else:  # Decline phase
            decline_progress = (idx - count * peak_position) / (
                count * (1 - peak_position)
            )
            curve_val = 1.0 - (decline_progress**0.7)  # Controlled decline
        peak_curve.append(curve_val)

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
        track, score, norm_bpm, norm_energy = track_idx[0]
        position = track_idx[1]

        if position < len(ordered_tracks):
            ordered_tracks[position] = track

    # Apply harmonic smoothing pass
    result = [track for track in ordered_tracks if track is not None]
    return _apply_harmonic_smoothing(result, bpm_tolerance, **kwargs)


def _apply_harmonic_smoothing(
    tracks: list[Track], bpm_tolerance: float, **kwargs
) -> list[Track]:
    """Apply local swaps to improve harmonic flow while preserving energy curve.

    Optimized: Max 3 iterations (was len/2) - most improvements happen in first 2-3 passes.
    """
    if len(tracks) <= 2:
        return tracks

    result = list(tracks)
    improved = True
    iterations = 0
    max_iterations = SMOOTHING_MAX_ITERATIONS

    while improved and iterations < max_iterations:
        improved = False
        iterations += 1

        for i in range(len(result) - 1):
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
    if len(tracks) <= 2:
        return sorted(tracks, key=lambda t: t.bpm)

    # Get genre parameters
    genre_mixing_enabled = kwargs.get("genre_mixing", True)
    genre_weight = kwargs.get("genre_weight", 0.3)  # 0.0-1.0

    # If genre mixing disabled, use harmonic flow instead
    if not genre_mixing_enabled:
        return _sort_harmonic_flow(tracks, bpm_tolerance, **kwargs)

    # Group tracks by genre (bevorzuge eine echte Klassifikation, sonst ID3)
    genre_groups = {}
    for track in tracks:
        detected = getattr(track, "detected_genre", "") or ""
        genre = detected if detected != "Unknown" else (track.genre or "")
        if not genre or genre == "Unknown":
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
            if genre not in processed_genres:
                # genre_weight blendet zwischen dem besten realen Uebergang
                # in die Gruppe (0 = Genre ignorieren) und der DJ-Brain-Matrix
                # (1 = Genre ist ausschlaggebend). Die fruehere affine Formel
                # war fuer alle Gewichte < 1 streng monoton und konnte deshalb
                # die Rangfolge niemals veraendern.
                dj_compat = get_genre_compatibility(current_genre, genre)
                current_track = result[-1]
                transition_compat = max(
                    calculate_compatibility(
                        current_track, candidate, bpm_tolerance, **kwargs
                    )
                    for candidate in genre_groups[genre]
                ) / 100.0
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
    ``mix_in_b >= intro_end_B`` (siehe tests/test_dj_brain.py), dieser Term
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
    energy_delta = to_track.energy - from_track.energy
    abs_energy_delta = abs(energy_delta)

    # Harmonic Compatibility pruefen — mit gewaehltem Scoring-Kontext (HPG-001):
    # der vorhergesagte Typ muss zum angezeigten Score passen, nicht zu Defaults.
    harmonic_score = calculate_compatibility(
        from_track, to_track, bpm_tolerance, **kwargs
    )

    # Genre-Info
    def _resolved_genre(track: Track) -> str:
        detected = getattr(track, "detected_genre", "") or ""
        if detected and detected != "Unknown":
            return detected
        return track.genre if track.genre and track.genre != "Unknown" else "Unknown"

    genre_a = _resolved_genre(from_track)
    genre_b = _resolved_genre(to_track)

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

    current_genre = getattr(current, "detected_genre", "Unknown") or "Unknown"
    upcoming_genre = getattr(upcoming, "detected_genre", "Unknown") or "Unknown"
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
        except Exception as e:
            logger.warning(f"DJ-Brain Transition-Verarbeitung fehlgeschlagen: {e}")
            # Fallback auf Standard-Notes

    return dj_rec, notes_parts, overlap


def compute_adjacent_transition_metrics(
    playlist: List[Track],
    bpm_tolerance: float = 3.0,
    scoring_context: Optional[Dict] = None,
) -> List[TransitionMetrics]:
    """Berechnet den gemeinsamen Enhanced-Score einmal pro Nachbarpaar."""
    ctx = dict(scoring_context or {})
    return [
        calculate_enhanced_compatibility(
            playlist[index], playlist[index + 1], bpm_tolerance, **ctx
        )
        for index in range(max(0, len(playlist) - 1))
    ]


def compute_transition_recommendations(
    playlist: List[Track],
    bpm_tolerance: float = 3.0,
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
    if len(playlist) < 2:
        return []

    ctx = dict(scoring_context or {})
    metrics_by_pair = (
        list(transition_metrics)
        if transition_metrics is not None
        else compute_adjacent_transition_metrics(playlist, bpm_tolerance, ctx)
    )
    if len(metrics_by_pair) != len(playlist) - 1:
        raise ValueError("transition_metrics muss genau ein Element pro Nachbarpaar enthalten")
    configured_overlap = ctx.get("overlap", default_overlap)
    try:
        configured_overlap = float(configured_overlap)
    except (TypeError, ValueError):
        configured_overlap = float(default_overlap)
    configured_overlap = max(4.0, min(64.0, configured_overlap))

    recommendations: List[TransitionRecommendation] = []

    for index in range(len(playlist) - 1):
        current = playlist[index]
        upcoming = playlist[index + 1]

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

        metrics = metrics_by_pair[index]
        compatibility_score = int(round(metrics.overall_score * 100))

        energy_delta = upcoming.energy - current.energy
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
        dj_rec, dj_notes_parts, dj_overlap = (
            _process_dj_brain_recommendations(current, upcoming)
        )
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

        has_dynamic_bar_source = dj_rec is not None and hasattr(
            dj_rec, "transition_bars"
        )
        overlap = _clamp_transition_overlap(
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
        overlap = min(float(overlap), MAX_TRANSITION_OVERLAP_SECONDS)
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

        transition_type = predict_transition_type(
            current, upcoming, bpm_tolerance, **ctx
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

    scoring_context (HPG-001): identischer Scoring-Vertrag wie bei der
    Generierung, damit die angezeigte Qualitaet zum Sortierziel passt.
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
    energy_diffs = []
    bpm_diffs = []

    for i in range(len(tracks) - 1):
        current, next_track = tracks[i], tracks[i + 1]

        # Energy differences
        energy_diffs.append(abs(current.energy - next_track.energy))

        # BPM differences (mit Half/Double-Erkennung)
        eff_diff, _ = effective_bpm_diff(current.bpm, next_track.bpm)
        bpm_diffs.append(eff_diff)

    # Calculate metrics
    avg_harmonic = sum(m.harmonic_score for m in metrics_by_pair) / len(metrics_by_pair) / 100.0
    avg_energy_diff = sum(energy_diffs) / len(energy_diffs)
    avg_bpm_diff = sum(bpm_diffs) / len(bpm_diffs)

    # Normalize scores (0-1, higher is better)
    harmonic_flow = avg_harmonic
    energy_consistency = max(
        0, 1 - avg_energy_diff / 50.0
    )  # 50 is max reasonable energy diff
    if bpm_tolerance <= 0:
        bpm_smoothness = 1.0 if avg_bpm_diff == 0 else 0.0
    else:
        bpm_smoothness = max(0.0, 1 - avg_bpm_diff / bpm_tolerance)

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
        "avg_energy_jump": avg_energy_diff,
        "avg_bpm_jump": avg_bpm_diff,
    }


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
    if len(tracks) <= 2:
        return sorted(tracks, key=lambda t: t.energy)

    energy_dir = str(kwargs.get("energy_direction", "Auto"))
    peak_position = max(0.4, min(0.8, float(kwargs.get("peak_position", 70)) / 100.0))
    genre_mixing = bool(kwargs.get("genre_mixing", True))
    genre_weight = max(0.0, min(1.0, float(kwargs.get("genre_weight", 0.3))))
    pool_avg_energy = sum(t.energy for t in tracks) / len(tracks)
    configured_target = kwargs.get("target_energy")
    if configured_target is not None:
        configured_target = max(0.0, min(100.0, float(configured_target)))

    def _target_energy(position: int, total: int) -> float:
        if configured_target is not None:
            return configured_target
        progress = position / max(1, total - 1)
        if energy_dir == "Build Up":
            return 30.0 + 55.0 * progress
        if energy_dir == "Cool Down":
            return 85.0 - 55.0 * progress
        if energy_dir == "Maintain":
            return pool_avg_energy
        # Auto-Dramaturgie mit dem sichtbaren Peak-Regler: 30 -> 85 am
        # gewaehlten Peak -> 40 am Set-Ende.
        if progress <= peak_position:
            return 30.0 + 55.0 * (progress / peak_position)
        decline = (progress - peak_position) / max(1e-9, 1.0 - peak_position)
        return 85.0 - 45.0 * decline

    def _genre(t: Track) -> str:
        detected = getattr(t, "detected_genre", "") or ""
        if detected and detected != "Unknown":
            return detected
        return t.genre if t.genre and t.genre != "Unknown" else "Unknown"

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
        current = final_playlist[-1]
        target_energy = _target_energy(len(final_playlist), total)

        # Energie-Trend aus den letzten 3 Tracks
        recent = [t.energy for t in final_playlist[-3:]]
        trend = recent[-1] - recent[0] if len(recent) >= 2 else 0.0

        # Genre-Streak am Playlist-Ende
        streak_genre = _genre(current)
        streak = 0
        for t in reversed(final_playlist):
            if _genre(t) == streak_genre:
                streak += 1
            else:
                break

        best_next = None
        highest_score = -999999.0
        for candidate in unprocessed:
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
                    streak_genre, _genre(candidate)
                )
                score += genre_weight * (genre_compat - 0.5) * 20.0
                # Fatigue bleibt ein kleiner Zusatz innerhalb desselben Reglers.
                if streak >= 4:
                    fatigue = 4.0 if _genre(candidate) != streak_genre else -6.0
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
SCORING_PARAMETERS = {"harmonic_strictness", "allow_experimental"}

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
        "overlap",
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
    liefern {} — dann bewerten Sortierung UND Anzeige einheitlich mit Defaults.
    Anzeige, Reorder, Preview, Quality und Empfehlungen muessen genau diesen
    Kontext verwenden, damit sie denselben Optimierungsvertrag darstellen wie
    die Generierung.
    """
    resolved_mode = STRATEGY_ALIASES.get(mode, mode)
    effective = StrategyConfig.from_mapping(advanced_params).effective_kwargs(
        resolved_mode
    )
    return {
        key: value
        for key, value in effective.items()
        if key in SCORING_PARAMETERS or key in {"target_energy", "overlap"}
    }


def generate_playlist(
    tracks: list[Track],
    mode: str,
    bpm_tolerance: float = 3.0,
    advanced_params: Optional[Dict] = None,
) -> list[Track]:
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
    """
    if not tracks:
        return []

    strategy_config = StrategyConfig.from_mapping(advanced_params)

    # Ensure all tracks have a camelot code before sorting
    for track in tracks:
        key_to_camelot(track)

    # Nur unbrauchbare BPM-Werte ausschliessen. Fehlende Keys bleiben erhalten
    # und nutzen den dokumentierten neutralen Harmonic-Fallback.
    valid_tracks: list[Track] = []
    unresolved_keys = []
    for candidate in tracks:
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
        if not getattr(candidate, "camelotCode", ""):
            unresolved_keys.append(candidate.filePath)

    if unresolved_keys:
        logger.warning(
            "%s Tracks ohne aufloesbaren Key bleiben mit neutralem Fallback enthalten.",
            len(unresolved_keys),
        )

    if not valid_tracks:
        return []

    # Alte Strategie-Namen (vor dem 11->8-Merge) aufloesen
    mode = STRATEGY_ALIASES.get(mode, mode)
    # Get the sorting function from the strategy map
    sorter = STRATEGIES.get(mode, _sort_harmonic_flow)  # Default to harmonic flow

    # Initialize thread-local-like cache container
    global _COMPAT_CACHE, _ENHANCED_COMPAT_CACHE
    old_cache = _COMPAT_CACHE
    old_enhanced_cache = _ENHANCED_COMPAT_CACHE
    _COMPAT_CACHE = {}
    _ENHANCED_COMPAT_CACHE = {}

    try:
        # Call the selected sorting strategy with advanced params
        effective_config = strategy_config.effective_kwargs(mode)
        logger.info("Effektive Strategieparameter %s: %s", mode, effective_config)
        result = sorter(valid_tracks, bpm_tolerance=bpm_tolerance, **effective_config)
    finally:
        # Restore old cache containers (usually None)
        _COMPAT_CACHE = old_cache
        _ENHANCED_COMPAT_CACHE = old_enhanced_cache

    # Log quality metrics for analysis — mit demselben Scoring-Kontext (HPG-001)
    scoring_context = {
        k: v for k, v in effective_config.items() if k in SCORING_PARAMETERS
    }
    quality = calculate_playlist_quality(result, bpm_tolerance, scoring_context)
    logger.info(
        f"Playlist-Qualitaet ({mode}): "
        f"Score={quality['overall_score']:.2f}, "
        f"Harmonic={quality['harmonic_flow']:.2f}, "
        f"Energy={quality['energy_consistency']:.2f}, "
        f"BPM={quality['bpm_smoothness']:.2f}"
    )

    return result


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
    end_time: float  # Ende in Sekunden (nach Overlap-Abzug)
    playing_duration: float  # Effektive Spieldauer in Sekunden
    overlap_with_next: float  # Overlap in Sekunden zum naechsten Track
    is_peak: bool  # Ist dieser Track am Peak-Punkt?
    energy_phase: str  # "intro", "warmup", "build", "peak", "sustain", "cooldown"


def _calculate_timeline_entries(
    tracks: list[Track], default_overlap: float,
    transition_plans: Optional[list[TransitionPlan]] = None,
) -> tuple[list[SetTimelineEntry], float]:
    """Berechnet Start- und Endzeiten fuer jeden Track.

    Zeitmodell (Konvention seit dem Blenden-Fix 1ebaa96): Track B startet
    seine Wiedergabe an mix_in_b in dem Moment, in dem Track A mix_out_a
    erreicht; die Blende dauert overlap Sekunden, A ist also bis
    mix_out_a + overlap hoerbar. Ein Track traegt damit nur das Stueck
    zwischen Mix-In und Mix-Out zur Set-Laenge bei, nicht seine ganze Dauer.
    Vorher galt playing_duration = dauer - overlap (Overlap am Track-ENDE
    abgezogen) — das zeigte ein 10er-Set um rund 20 Minuten zu lang an.

    Sonderfaelle: der erste Track beginnt bei Position 0 (der DJ spielt ihn
    von vorn), der letzte spielt bis zu seinem Ende. Ohne Plan gelten die
    Fallbacks aus _resolve_mix_points — dieselben wie in den Empfehlungen,
    damit Timeline und Empfehlung nicht verschiedene Mixpunkte zeigen.
    """
    entries: list[SetTimelineEntry] = []
    current_time = 0.0
    n = len(tracks)

    for i, track in enumerate(tracks):
        track_dur = max(track.duration, 30.0)  # Minimum 30s pro Track
        plan_in = transition_plans[i - 1] if (
            transition_plans and 0 < i <= len(transition_plans)
        ) else None
        plan_out = transition_plans[i] if (
            transition_plans and i < len(transition_plans)
        ) else None
        fallback_in, fallback_out = _resolve_mix_points(track, default_overlap)

        # Mix-In: erster Track von vorn, sonst aus dem Plan des Vorgaengers
        if i == 0:
            mix_in = 0.0
        elif plan_in is not None:
            mix_in = float(plan_in.mix_in_b)
        else:
            mix_in = fallback_in
        mix_in = min(max(mix_in, 0.0), track_dur)

        # Mix-Out: aus dem eigenen Plan, sonst Fallback; nie vor dem Mix-In
        if plan_out is not None:
            mix_out = float(plan_out.mix_out_a)
        else:
            mix_out = fallback_out
        if not (mix_in < mix_out <= track_dur):
            mix_out = fallback_out
        if not (mix_in < mix_out <= track_dur):
            mix_out = track_dur

        # Overlap zum naechsten Track
        if i < n - 1:
            if plan_out is not None:
                overlap = float(plan_out.overlap)
            else:
                overlap = track_dur - mix_out
                overlap = max(4.0, min(overlap, default_overlap, track_dur * 0.3))
            # AUDIT-FIX F10 (2026-07-24): Plan-Overlap war ungeklemmt — bei
            # kurzen Tracks (Edits/Tools/Acapellas) ergab ein 64-s-Overlap
            # negative Spieldauer und rueckwaerts laufende Startzeiten. Overlap
            # nie ueber die halbe Trackdauer — und nie laenger als das Audio,
            # das A nach dem Mix-Out noch hat.
            overlap = max(0.0, min(overlap, track_dur * 0.5, track_dur - mix_out))
            playing_duration = (mix_out - mix_in) + overlap
            next_start = current_time + (mix_out - mix_in)
        else:
            overlap = 0.0  # Letzter Track hat keinen Overlap, spielt bis zum Ende
            playing_duration = track_dur - mix_in
            next_start = current_time + playing_duration

        end_time = current_time + playing_duration

        entries.append(
            SetTimelineEntry(
                track=track,
                start_time=round(current_time, 2),
                end_time=round(end_time, 2),
                playing_duration=round(playing_duration, 2),
                overlap_with_next=round(overlap, 2),
                is_peak=False,  # Wird spaeter gesetzt
                energy_phase="build",  # Wird spaeter gesetzt
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
    Eintraege ueberlappen um den Overlap — siehe _calculate_timeline_entries.
    Der Peak-Track wird identifiziert.

    Args:
      tracks: Sortierte Playlist
      target_minutes: Gewuenschte Set-Laenge in Minuten
      peak_position_pct: Peak-Position als Anteil (0.0-1.0, default 0.65)
      default_overlap: Standard-Overlap in Sekunden wenn keine Mix-Points

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
        total_duration_minutes=round(total_minutes, 2),
        target_duration_minutes=target_minutes,
        peak_position_minutes=round(peak_minutes, 2),
        entries=entries,
        overflow_minutes=round(total_minutes - target_minutes, 2),
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
        "avg_track_duration": round(avg_dur, 1),
    }
