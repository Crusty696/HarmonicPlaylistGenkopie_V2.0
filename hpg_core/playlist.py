from .models import (
    Track,
    key_to_camelot,
    effective_bpm_diff,
    get_camelot_components,
)
from typing import TYPE_CHECKING
from .dj_brain import (
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
)
import logging
import re
import random
import math
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


@dataclass
class TransitionMetrics:
    """Metrics for evaluating track transitions."""

    harmonic_score: int
    bpm_smoothness: float
    energy_flow: float
    genre_compatibility: float
    overall_score: float
    ai_bonus: float = 0.0


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


def _get_camelot_components(camelot_code: str) -> tuple[int, str]:
    """Parses a Camelot code into its number and letter components.

    Delegiert an die zentrale Definition in models (Audit 2026-07-17).
    """
    return get_camelot_components(camelot_code)


def calculate_enhanced_compatibility(
    track1: Track,
    track2: Track,
    bpm_tolerance: float,
    energy_direction: Optional[EnergyDirection] = None,
    **kwargs,
) -> TransitionMetrics:
    """Enhanced compatibility calculation with multiple factors."""

    # Basic harmonic compatibility
    # M2-Fix: kwargs (harmonic_strictness, allow_experimental) durchreichen —
    # vorher fielen die UI-Parameter im Enhanced-Pfad auf Defaults zurueck
    harmonic_score = calculate_compatibility(track1, track2, bpm_tolerance, **kwargs)

    # BPM smoothness (exponential decay, mit Half/Double-Erkennung)
    bpm_diff, _ = effective_bpm_diff(track1.bpm, track2.bpm)
    if bpm_diff > bpm_tolerance:
        bpm_smoothness = 0.0
    else:
        bpm_smoothness = math.exp(-bpm_diff / (bpm_tolerance / 2))

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
    genre_a = getattr(track1, "detected_genre", "") or track1.genre
    genre_b = getattr(track2, "detected_genre", "") or track2.genre
    genre_compatibility = get_genre_compatibility(genre_a, genre_b)

    # Genre-Weight hoeher wenn DJ Brain Genre-Daten vorhanden
    has_dj_brain_genres = getattr(track1, "detected_genre", "Unknown") not in (
        "Unknown",
        "",
    ) and getattr(track2, "detected_genre", "Unknown") not in ("Unknown", "")
    genre_weight = (
        GENRE_WEIGHT_WITH_DJ_BRAIN
        if has_dj_brain_genres
        else GENRE_WEIGHT_WITHOUT_DJ_BRAIN
    )
    remaining = 1.0 - genre_weight

    # Overall weighted score
    overall_score = (
        (remaining * 0.44) * (harmonic_score / 100.0)
        + (remaining * 0.28) * bpm_smoothness
        + (remaining * 0.28) * energy_flow
        + genre_weight * genre_compatibility
    )

    # Calculate AI Mood & Sub-Genre Bonus
    ai_bonus = 0.0
    ai_meta1 = getattr(track1, "ai_metadata", {})
    ai_meta2 = getattr(track2, "ai_metadata", {})
    if isinstance(ai_meta1, dict) and isinstance(ai_meta2, dict) and ai_meta1 and ai_meta2:
        # 1. Moods
        moods1 = ai_meta1.get("moods", [])
        moods2 = ai_meta2.get("moods", [])
        if isinstance(moods1, list) and isinstance(moods2, list):
            moods1_set = {str(m).strip().lower() for m in moods1 if m}
            moods2_set = {str(m).strip().lower() for m in moods2 if m}
            if moods1_set and moods2_set:
                intersect = moods1_set.intersection(moods2_set)
                # Up to 0.08 bonus for matching moods
                ai_bonus += 0.08 * (len(intersect) / max(len(moods1_set), len(moods2_set)))

        # 2. Sub-genres
        sub1 = ai_meta1.get("sub_genre", "")
        sub2 = ai_meta2.get("sub_genre", "")
        if isinstance(sub1, str) and isinstance(sub2, str) and sub1 and sub2:
            s1 = sub1.strip().lower()
            s2 = sub2.strip().lower()
            if s1 == s2:
                ai_bonus += 0.06
            elif s1 in s2 or s2 in s1:
                ai_bonus += 0.03

    overall_score = min(1.0, overall_score + ai_bonus)

    # BPM-Hard-Gate (Audit 2026-07-17): ein am Pitchfader unmixbarer Sprung
    # darf nicht ueber Genre/Energie auf ~40% "gerettet" werden — die 0-100-
    # Strategien gaten hart, Enhanced muss dieselbe Grundentscheidung treffen
    if bpm_diff > bpm_tolerance:
        overall_score = 0.0

    return TransitionMetrics(
        harmonic_score=harmonic_score,
        bpm_smoothness=bpm_smoothness,
        energy_flow=energy_flow,
        genre_compatibility=genre_compatibility,
        overall_score=overall_score,
        ai_bonus=ai_bonus,
    )


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
        return 10

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
    loose_factor = max(0.4, min(1.2, 1.0 - (strictness - 7) * 0.08))

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


# Global thread-local-like cache container for the current playlist generation session
# Avoids mutating dictionaries while keeping cache simple.
_COMPAT_CACHE = None


def calculate_compatibility(
    track1: Track, track2: Track, bpm_tolerance: float, **kwargs
) -> int:
    """Wrapper around _calculate_compatibility_inner that uses a global dictionary cache
    if one is currently set up by generate_playlist or benchmark."""
    global _COMPAT_CACHE

    # Inner helper to apply AI metadata bonus
    def _apply_ai_bonus(t1: Track, t2: Track, base_score: int) -> int:
        if base_score <= 0:
            return base_score

        ai_bonus = 0
        ai_meta1 = getattr(t1, "ai_metadata", {})
        ai_meta2 = getattr(t2, "ai_metadata", {})

        if isinstance(ai_meta1, dict) and isinstance(ai_meta2, dict) and ai_meta1 and ai_meta2:
            # 1. Compare moods
            moods1 = ai_meta1.get("moods", [])
            moods2 = ai_meta2.get("moods", [])
            if isinstance(moods1, list) and isinstance(moods2, list):
                moods1_set = {str(m).strip().lower() for m in moods1 if m}
                moods2_set = {str(m).strip().lower() for m in moods2 if m}
                if moods1_set and moods2_set:
                    intersect = moods1_set.intersection(moods2_set)
                    # Up to +8 bonus points for overlapping moods
                    ai_bonus += int(8 * (len(intersect) / max(len(moods1_set), len(moods2_set))))

            # 2. Compare sub-genres
            sub1 = ai_meta1.get("sub_genre", "")
            sub2 = ai_meta2.get("sub_genre", "")
            if isinstance(sub1, str) and isinstance(sub2, str) and sub1 and sub2:
                s1 = sub1.strip().lower()
                s2 = sub2.strip().lower()
                if s1 == s2:
                    ai_bonus += 6
                elif s1 in s2 or s2 in s1:
                    ai_bonus += 3

        return min(100, base_score + ai_bonus)

    if _COMPAT_CACHE is not None:
        cache_key = (
            id(track1),
            id(track2),
            bpm_tolerance,
            kwargs.get("harmonic_strictness", 7),
            kwargs.get("allow_experimental", True),
        )
        if cache_key in _COMPAT_CACHE:
            return _COMPAT_CACHE[cache_key]

        score = _calculate_compatibility_inner(track1, track2, bpm_tolerance, **kwargs)
        score = _apply_ai_bonus(track1, track2, score)
        _COMPAT_CACHE[cache_key] = score
        return score

    score = _calculate_compatibility_inner(track1, track2, bpm_tolerance, **kwargs)
    return _apply_ai_bonus(track1, track2, score)


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
            cache_key = (id(current), id(candidate))
            if cache_key in compat_cache:
                immediate_score = compat_cache[cache_key]
            else:
                immediate_score = calculate_compatibility(
                    current, candidate, bpm_tolerance, **kwargs
                )
                compat_cache[cache_key] = immediate_score

            if immediate_score == 0:  # Skip incompatible tracks
                continue
            scored.append((immediate_score, candidate))

        if not scored:
            return None, -1

        scored.sort(key=lambda item: -item[0])

        best_candidate = None
        best_total_score = -1
        for immediate_score, candidate in scored[:LOOKAHEAD_TOP_K]:
            future_score = 0.0
            if depth > 1 and len(remaining) > 1:
                next_remaining = [t for t in remaining if t is not candidate]
                _, future_score = _lookahead_score(candidate, next_remaining, depth - 1)

            total_score = (
                immediate_score + 0.7 * future_score
            )  # Weight immediate higher
            if total_score > best_total_score:
                best_total_score = total_score
                best_candidate = candidate

        return best_candidate, best_total_score

    unprocessed = list(tracks)
    # Start with a track that has good overall connectivity
    start_track = _find_best_starting_track(tracks, bpm_tolerance, **compat_kwargs)
    final_playlist = [start_track]
    unprocessed.remove(start_track)

    current_track = start_track
    while unprocessed:
        best_next, score = _lookahead_score(
            current_track, unprocessed, depth=2
        )  # Optimized: depth=2 (was 3)

        if best_next and score > 0:
            final_playlist.append(best_next)
            unprocessed.remove(best_next)
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
            unprocessed.remove(fallback)
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

            cache_key = (id(track), id(tracks[j]))
            if cache_key in compat_cache:
                score = compat_cache[cache_key]
            else:
                score = calculate_compatibility(
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


def _sort_warm_up(tracks: list[Track], bpm_tolerance: float, **kwargs) -> list[Track]:
    """Sorts tracks by ascending BPM."""
    return sorted(tracks, key=lambda t: t.bpm)


def _sort_cool_down(tracks: list[Track], bpm_tolerance: float, **kwargs) -> list[Track]:
    """Sorts tracks by descending BPM."""
    return sorted(tracks, key=lambda t: t.bpm, reverse=True)


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


def _sort_energy_wave(
    tracks: list[Track], bpm_tolerance: float, **kwargs
) -> list[Track]:
    """Create a wave-like journey that alternates between higher and lower energy tracks."""
    if not tracks:
        return []

    ordered_by_energy = sorted(tracks, key=lambda track: track.energy)
    count = len(ordered_by_energy)
    if count <= 2:
        return ordered_by_energy

    center_index = (count - 1) // 2
    result: list[Track] = [ordered_by_energy[center_index]]

    left = center_index - 1
    right = center_index + 1
    take_high = True

    while left >= 0 or right < count:
        if take_high and right < count:
            result.append(ordered_by_energy[right])
            right += 1
        elif left >= 0:
            result.append(ordered_by_energy[left])
            left -= 1
        else:
            # If no left values remain, continue with the right side
            result.append(ordered_by_energy[right])
            right += 1
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

    for position_idx, track_idx in enumerate(zip(scored_tracks, waveform_positions)):
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
    max_iterations = 3  # Optimized: Fixed limit instead of len(tracks) // 2

    while improved and iterations < max_iterations:
        improved = False
        iterations += 1

        for i in range(len(result) - 1):
            current_score = calculate_compatibility(
                result[i], result[i + 1], bpm_tolerance, **kwargs
            )

            # Try swapping with next track if it improves harmony
            if i + 2 < len(result):
                swap_score = calculate_compatibility(
                    result[i], result[i + 2], bpm_tolerance, **kwargs
                )
                next_swap_score = calculate_compatibility(
                    result[i + 1], result[i + 2], bpm_tolerance, **kwargs
                )
                # Calculate what score would be AFTER swap: [i]->[i+1] becomes [i]->[i+2], [i+2]->[i+1]
                new_pair_score = calculate_compatibility(
                    result[i + 2], result[i + 1], bpm_tolerance, **kwargs
                )

                # Compare: current transition score vs score after swap
                if swap_score + new_pair_score > current_score + next_swap_score:
                    # Only swap if energy curve isn't severely disrupted
                    energy_disruption = abs(result[i].energy - result[i + 2].energy)
                    if energy_disruption < 20:  # Threshold for acceptable energy jump
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

    # Group tracks by genre (bevorzuge detected_genre wenn vorhanden)
    genre_groups = {}
    for track in tracks:
        genre = getattr(track, "detected_genre", "") or track.genre
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
                # Einzige Quelle: DJ-Brain-Matrix (0.5 = unbekannte Kombination),
                # skaliert mit genre_weight (hoeher = staerkere Genre-Praeferenz)
                dj_compat = get_genre_compatibility(current_genre, genre)
                compatibility = dj_compat * (1 - genre_weight) + genre_weight
                if compatibility > best_compatibility:
                    best_compatibility = compatibility
                    best_next_genre = genre

        if best_next_genre:
            current_genre = best_next_genre
        else:
            # If no compatible genre found, pick any remaining genre
            remaining_genres = set(genre_groups.keys()) - processed_genres
            if remaining_genres:
                current_genre = list(remaining_genres)[0]
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
    remaining.remove(current)

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
            compatibility = calculate_compatibility(
                current, candidate, bpm_tolerance, **compat_kwargs
            )
            compatibility_penalty = (100 - compatibility) / 8.0
            if compatibility == 0:
                compatibility_penalty += 10.0
            return bpm_delta + energy_delta + compatibility_penalty

        next_track = min(remaining, key=_transition_cost)
        playlist.append(next_track)
        remaining.remove(next_track)
        current = next_track

    return playlist


def _resolve_mix_points(track: Track, fallback_overlap: float) -> tuple[float, float]:
    """Ensure mix-in/out points are usable, applying sensible fallbacks."""
    duration = max(track.duration, 0.0)

    if track.mix_in_point > 0:
        mix_in_point = track.mix_in_point
    elif duration > 0:
        mix_in_point = min(duration * 0.1, max(4.0, fallback_overlap / 2))
    else:
        mix_in_point = max(0.0, fallback_overlap / 2)

    if track.mix_out_point > 0:
        mix_out_point = track.mix_out_point
    elif duration > 0:
        mix_out_point = max(
            mix_in_point + 4.0, duration - min(duration * 0.05, fallback_overlap)
        )
    else:
        mix_out_point = mix_in_point + max(4.0, fallback_overlap / 2)

    if duration > 0:
        mix_in_point = max(0.0, min(mix_in_point, duration))
        mix_out_point = max(mix_in_point + 1.0, min(mix_out_point, duration))

    return mix_in_point, mix_out_point


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

    # Harmonic Compatibility pruefen
    harmonic_score = calculate_compatibility(from_track, to_track, bpm_tolerance)

    # Genre-Info
    genre_a = getattr(from_track, "detected_genre", "Unknown") or "Unknown"
    genre_b = getattr(to_track, "detected_genre", "Unknown") or "Unknown"

    # --- Regel 1: Half/Double-Time Wechsel ---
    if bpm_relation in ("half", "double") and eff_diff <= bpm_tolerance:
        return "halftime_switch"

    # --- Regel 2: BPM ausserhalb Toleranz ---
    if eff_diff > bpm_tolerance:
        if harmonic_score >= 50:
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
        if genre_a in melodic_genres or genre_b in melodic_genres:
            return "filter_ride"
        if genre_a in hard_genres or genre_b in hard_genres:
            return "bass_swap"
        return "smooth_blend"

    # --- Regel 6: Gute Harmonie, BPM passt ---
    if harmonic_score >= 70 and eff_diff <= bpm_tolerance:
        # Harte Genres bevorzugen Bass Swap
        hard_genres = {"Tech House", "Techno", "Drum & Bass", "Minimal", "Psytrance"}
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
    current_mix_out: float,
) -> tuple["DJRecommendation | None", list[str], float | None, float | None]:
    """
    Processes DJ Brain recommendations and returns the updated transition details.

    Returns:
        tuple containing:
        - dj_rec: The DJRecommendation object if successful, else None
        - notes_parts: Additional notes from the DJ Brain
        - overlap: Adjusted overlap if DJ Brain provided transition bars
        - fade_out_start: Adjusted fade out start based on overlap
    """
    dj_rec = None
    notes_parts = []
    overlap = None
    fade_out_start = None

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

            # DJ Brain Transition-Laenge uebernehmen
            if dj_rec.transition_bars > 0 and current.bpm > 0:
                seconds_per_bar = (60.0 / current.bpm) * METER
                overlap = seconds_per_bar * dj_rec.transition_bars
                fade_out_start = max(0.0, current_mix_out - overlap)
        except Exception as e:
            logger.warning(f"DJ-Brain Transition-Verarbeitung fehlgeschlagen: {e}")
            # Fallback auf Standard-Notes

    return dj_rec, notes_parts, overlap, fade_out_start


def compute_transition_recommendations(
    playlist: List[Track], bpm_tolerance: float = 3.0, default_overlap: float = 12.0
) -> List[TransitionRecommendation]:
    """Build actionable mix recommendations between consecutive tracks."""
    if len(playlist) < 2:
        return []

    recommendations: List[TransitionRecommendation] = []

    for index in range(len(playlist) - 1):
        current = playlist[index]
        upcoming = playlist[index + 1]

        effective_overlap = max(4.0, default_overlap)
        if current.duration > 0 and upcoming.duration > 0:
            effective_overlap = min(
                default_overlap,
                max(6.0, min(current.duration, upcoming.duration) * 0.2),
            )

        current_mix_in, current_mix_out = _resolve_mix_points(
            current, effective_overlap
        )
        next_mix_in, next_mix_out = _resolve_mix_points(upcoming, effective_overlap)

        # DJ Logic: The mix usually starts at the 'mix_in' of the upcoming track
        # and ends at the 'mix_out' of the current track.
        # We want to align the 'mix_in' of the next track with a phrase in the current track.

        # Calculate how long the transition should be (e.g., 16 or 32 bars)
        seconds_per_beat = 60.0 / current.bpm if current.bpm > 0 else 60.0 / DEFAULT_BPM
        seconds_per_bar = seconds_per_beat * METER

        # Standard DJ transition length: 32 bars (approx 60s at 124bpm)
        transition_duration = seconds_per_bar * 32

        # Adjust transition duration if tracks are short
        if current.duration > 0:
            transition_duration = min(transition_duration, current.duration * 0.25)

        fade_out_start = max(0.0, current_mix_out - transition_duration)
        fade_in_start = next_mix_in
        overlap = transition_duration

        metrics = calculate_enhanced_compatibility(current, upcoming, bpm_tolerance)
        compatibility_score = int(metrics.overall_score * 100)

        energy_delta = upcoming.energy - current.energy
        eff_bpm_diff, bpm_relation = effective_bpm_diff(current.bpm, upcoming.bpm)
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
        dj_rec, dj_notes_parts, dj_overlap, dj_fade_out_start = (
            _process_dj_brain_recommendations(current, upcoming, current_mix_out)
        )
        notes_parts.extend(dj_notes_parts)
        if dj_overlap is not None:
            overlap = dj_overlap
        if dj_fade_out_start is not None:
            fade_out_start = dj_fade_out_start
        if dj_rec is not None:
            if dj_rec.adjusted_mix_out_a >= 0.0:
                current_mix_out = dj_rec.adjusted_mix_out_a
                # L4-Fix: fade_out_start gegen den AKTUALISIERTEN Mix-Out
                # rechnen — dj_fade_out_start basierte noch auf dem alten Wert
                fade_out_start = max(0.0, current_mix_out - overlap)
            if dj_rec.adjusted_mix_in_b >= 0.0:
                next_mix_in = dj_rec.adjusted_mix_in_b
                fade_in_start = next_mix_in
            if dj_rec.overlap_seconds > 0.0:
                overlap = dj_rec.overlap_seconds
                fade_out_start = max(0.0, current_mix_out - overlap)

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

        recommendations.append(
            TransitionRecommendation(
                index=index,
                from_track=current,
                to_track=upcoming,
                fade_out_start=round(fade_out_start, 2),
                fade_out_end=round(current_mix_out, 2),
                fade_in_start=round(fade_in_start, 2),
                mix_entry=round(next_mix_in, 2),
                overlap=round(overlap, 2),
                bpm_delta=round(bpm_delta, 2),
                energy_delta=energy_delta,
                compatibility_score=compatibility_score,
                risk_level=risk_level,
                notes=notes,
                transition_type=predict_transition_type(
                    current, upcoming, bpm_tolerance
                ),
                dj_rec=dj_rec,
            )
        )

    return recommendations


def calculate_playlist_quality(
    tracks: list[Track], bpm_tolerance: float
) -> Dict[str, float]:
    """Calculate comprehensive quality metrics for a playlist."""
    if len(tracks) < 2:
        return {
            "overall_score": 1.0,
            "harmonic_flow": 1.0,
            "energy_consistency": 1.0,
            "bpm_smoothness": 1.0,
        }

    harmonic_scores = []
    energy_diffs = []
    bpm_diffs = []

    for i in range(len(tracks) - 1):
        current, next_track = tracks[i], tracks[i + 1]

        # Harmonic compatibility
        harmonic_score = calculate_compatibility(current, next_track, bpm_tolerance)
        harmonic_scores.append(harmonic_score)

        # Energy differences
        energy_diffs.append(abs(current.energy - next_track.energy))

        # BPM differences (mit Half/Double-Erkennung)
        eff_diff, _ = effective_bpm_diff(current.bpm, next_track.bpm)
        bpm_diffs.append(eff_diff)

    # Calculate metrics
    avg_harmonic = sum(harmonic_scores) / len(harmonic_scores) / 100.0
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

    # Overall weighted score
    overall_score = (
        0.5 * harmonic_flow + 0.25 * energy_consistency + 0.25 * bpm_smoothness
    )

    return {
        "overall_score": overall_score,
        "harmonic_flow": harmonic_flow,
        "energy_consistency": energy_consistency,
        "bpm_smoothness": bpm_smoothness,
        "avg_harmonic_score": avg_harmonic * 100,
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

    phase_target_energy = {"warmup": 30.0, "build": 60.0, "peak": 85.0, "cooldown": 40.0}
    energy_dir = str(kwargs.get("energy_direction", "Auto"))
    pool_avg_energy = sum(t.energy for t in tracks) / len(tracks)

    def _phase(position: int, total: int) -> str:
        p = position / max(1, total - 1)
        if p < 0.2:
            return "warmup"
        if p < 0.5:
            return "build"
        if p < 0.8:
            return "peak"
        return "cooldown"

    def _target_energy(position: int, total: int) -> float:
        progress = position / max(1, total - 1)
        if energy_dir == "Build Up":
            return 30.0 + 55.0 * progress
        if energy_dir == "Cool Down":
            return 85.0 - 55.0 * progress
        if energy_dir == "Maintain":
            return pool_avg_energy
        return phase_target_energy[_phase(position, total)]

    def _genre(t: Track) -> str:
        return getattr(t, "detected_genre", "") or t.genre or "Unknown"

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
    unprocessed.remove(start)

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
            base = calculate_compatibility(current, candidate, bpm_tolerance, **kwargs)
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
            # Genre-Fatigue
            if streak >= 4:
                score += 4.0 if _genre(candidate) != streak_genre else -6.0
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
        unprocessed.remove(best_next)

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

# Alte Namen bleiben gueltig (gespeicherte Settings, Tests, Cache-Metadaten)
STRATEGY_ALIASES = {
    "Harmonic Flow Enhanced": "Harmonic Flow",
    "Peak-Time Enhanced": "Peak-Time",
    "Emotional Journey": "Context Flow",
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

    # Default advanced params if not provided
    if advanced_params is None:
        advanced_params = {}

    # Ensure all tracks have a camelot code before sorting
    for track in tracks:
        key_to_camelot(track)

    # Filter out tracks that couldn't be analyzed properly
    valid_tracks: list[Track] = []
    for candidate in tracks:
        bpm_value = getattr(candidate, "bpm", None)
        camelot = getattr(candidate, "camelotCode", "")

        try:
            bpm_numeric = float(bpm_value)
        except (TypeError, ValueError):
            continue

        if bpm_numeric <= 0 or not camelot:
            continue

        candidate.bpm = bpm_numeric
        valid_tracks.append(candidate)

    if not valid_tracks:
        return tracks  # Return original if no tracks are valid

    # Alte Strategie-Namen (vor dem 11->8-Merge) aufloesen
    mode = STRATEGY_ALIASES.get(mode, mode)
    # Get the sorting function from the strategy map
    sorter = STRATEGIES.get(mode, _sort_harmonic_flow)  # Default to harmonic flow

    # Initialize thread-local-like cache container
    global _COMPAT_CACHE
    old_cache = _COMPAT_CACHE
    _COMPAT_CACHE = {}

    try:
        # Call the selected sorting strategy with advanced params
        result = sorter(valid_tracks, bpm_tolerance=bpm_tolerance, **advanced_params)
    finally:
        # Restore old cache container (usually None)
        _COMPAT_CACHE = old_cache

    # Log quality metrics for analysis
    quality = calculate_playlist_quality(result, bpm_tolerance)
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
    tracks: list[Track], default_overlap: float
) -> tuple[list[SetTimelineEntry], float]:
    """Berechnet Start- und Endzeiten fuer jeden Track."""
    entries: list[SetTimelineEntry] = []
    current_time = 0.0

    for i, track in enumerate(tracks):
        track_dur = max(track.duration, 30.0)  # Minimum 30s pro Track

        # Overlap zum naechsten Track berechnen
        if i < len(tracks) - 1:
            # Nutze Mix-Points wenn vorhanden, sonst Default
            mix_out = (
                track.mix_out_point if track.mix_out_point > 0 else track_dur * 0.85
            )
            overlap = track_dur - mix_out
            overlap = max(4.0, min(overlap, default_overlap, track_dur * 0.3))
        else:
            overlap = 0.0  # Letzter Track hat keinen Overlap

        playing_duration = track_dur - overlap
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

        current_time = end_time

    return entries, current_time


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
) -> SetTimeline:
    """
    Berechnet eine zeitbasierte Timeline fuer ein DJ-Set.

    Jeder Track bekommt einen Start/Ende-Zeitpunkt. Overlaps werden
    von der Gesamtdauer abgezogen. Der Peak-Track wird identifiziert.

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

    entries, total_seconds = _calculate_timeline_entries(tracks, default_overlap)
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


