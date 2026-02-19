from __future__ import annotations  # Python 3.9 compatibility for | type hints

from .models import Track, CAMELOT_MAP, key_to_camelot
from .dj_brain import get_genre_compatibility, generate_dj_recommendation, get_mix_profile
from .config import (
    GENRE_WEIGHT_WITH_DJ_BRAIN, GENRE_WEIGHT_WITHOUT_DJ_BRAIN,
    BPM_HALF_DOUBLE_ENABLED, BPM_HALF_DOUBLE_PENALTY
)
import re
import random
import math
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass
from enum import Enum

@dataclass
class TransitionMetrics:
    """Metrics for evaluating track transitions."""
    harmonic_score: int
    bpm_smoothness: float
    energy_flow: float
    genre_compatibility: float
    overall_score: float

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

class EnergyDirection(Enum):
    """Direction of energy flow in transitions."""
    UP = "up"
    DOWN = "down"
    MAINTAIN = "maintain"


def _get_camelot_components(camelot_code: str) -> tuple[int, str]:
    """Parses a Camelot code into its number and letter components."""
    match = re.match(r'(\d+)([A|B])', camelot_code)
    if match:
        return int(match.group(1)), match.group(2)
    return 0, ''

def calculate_enhanced_compatibility(track1: Track, track2: Track, bpm_tolerance: float,
                                   energy_direction: Optional[EnergyDirection] = None) -> TransitionMetrics:
    """Enhanced compatibility calculation with multiple factors."""

    # Basic harmonic compatibility
    harmonic_score = calculate_compatibility(track1, track2, bpm_tolerance)

    # BPM smoothness (exponential decay, mit Half/Double-Erkennung)
    bpm_diff, _ = effective_bpm_diff(track1.bpm, track2.bpm)
    if bpm_diff > bpm_tolerance:
        bpm_smoothness = 0.0
    else:
        bpm_smoothness = math.exp(-bpm_diff / (bpm_tolerance / 2))

    # Energy flow analysis
    energy_diff = track2.energy - track1.energy
    if energy_direction == EnergyDirection.UP:
        energy_flow = max(0, energy_diff) / 50.0  # Normalize to 0-2 range
    elif energy_direction == EnergyDirection.DOWN:
        energy_flow = max(0, -energy_diff) / 50.0
    elif energy_direction == EnergyDirection.MAINTAIN:
        energy_flow = 1.0 - abs(energy_diff) / 50.0
    else:
        energy_flow = 1.0 - abs(energy_diff) / 100.0  # Gentle energy preference

    # Genre compatibility - DJ Brain Matrix wenn detected_genre vorhanden
    genre_a = getattr(track1, 'detected_genre', '') or track1.genre
    genre_b = getattr(track2, 'detected_genre', '') or track2.genre
    genre_compatibility = get_genre_compatibility(genre_a, genre_b)

    # Genre-Weight hoeher wenn DJ Brain Genre-Daten vorhanden
    has_dj_brain_genres = (
        getattr(track1, 'detected_genre', 'Unknown') not in ('Unknown', '')
        and getattr(track2, 'detected_genre', 'Unknown') not in ('Unknown', '')
    )
    genre_weight = GENRE_WEIGHT_WITH_DJ_BRAIN if has_dj_brain_genres else GENRE_WEIGHT_WITHOUT_DJ_BRAIN
    remaining = 1.0 - genre_weight

    # Overall weighted score
    overall_score = (
        (remaining * 0.44) * (harmonic_score / 100.0) +
        (remaining * 0.28) * bpm_smoothness +
        (remaining * 0.28) * energy_flow +
        genre_weight * genre_compatibility
    )

    return TransitionMetrics(
        harmonic_score=harmonic_score,
        bpm_smoothness=bpm_smoothness,
        energy_flow=energy_flow,
        genre_compatibility=genre_compatibility,
        overall_score=overall_score
    )

def effective_bpm_diff(bpm1: float, bpm2: float) -> tuple[float, str]:
    """Berechnet die effektive BPM-Differenz unter Beruecksichtigung von Half/Double-Time.

    Erkennt automatisch ob ein Track in Half-Time (z.B. 70 BPM = 140/2)
    oder Double-Time (z.B. 280 BPM = 140*2) laeuft und gibt die
    kleinste sinnvolle Differenz zurueck.

    Args:
        bpm1: BPM von Track 1
        bpm2: BPM von Track 2

    Returns:
        Tuple von (effektive_differenz, relation_typ).
        relation_typ: "direct", "half", oder "double"
    """
    if bpm1 <= 0 or bpm2 <= 0:
        return abs(bpm1 - bpm2), "direct"

    candidates = [
        (abs(bpm1 - bpm2), "direct"),
        (abs(bpm1 - bpm2 * 2), "half"),      # bpm2 ist Half-Time
        (abs(bpm1 * 2 - bpm2), "half"),      # bpm1 ist Half-Time
        (abs(bpm1 - bpm2 / 2), "double"),    # bpm2 ist Double-Time
        (abs(bpm1 / 2 - bpm2), "double"),    # bpm1 ist Double-Time
    ]

    if not BPM_HALF_DOUBLE_ENABLED:
        return candidates[0]  # Nur direkte Differenz

    return min(candidates, key=lambda x: x[0])


def calculate_compatibility(track1: Track, track2: Track, bpm_tolerance: float, **kwargs) -> int:
    """Calculates a compatibility score between two tracks, including advanced harmonic rules.

    Args:
        track1, track2: Tracks to compare
        bpm_tolerance: Max BPM difference allowed
        **kwargs: Advanced parameters:
            - harmonic_strictness (1-10): Higher = stricter scoring (default: 7)
            - allow_experimental (bool): Allow +4/+7 techniques (default: True)
    """
    # Get advanced parameters
    strictness = kwargs.get('harmonic_strictness', 7)
    allow_experimental = kwargs.get('allow_experimental', True)

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

    if num1 == 0 or num2 == 0: # Invalid camelot codes
        return 10

    # Half/Double-Time Penalty-Faktor
    penalty = BPM_HALF_DOUBLE_PENALTY if bpm_relation != "direct" else 1.0

    # Direct matches (always allowed)
    if num1 == num2 and letter1 == letter2:
        return int(100 * penalty)  # Same key
    if num1 == num2 and letter1 != letter2:
        return int(90 * penalty)   # Relative major/minor

    # Adjacent keys (Camelot wheel)
    next_num_cw = (num1 % 12) + 1
    next_num_ccw = (num1 - 2 + 12) % 12 + 1

    if letter1 == letter2: # Same mode, adjacent numbers
        if num2 == next_num_cw or num2 == next_num_ccw:
            return int(80 * penalty)

    # Experimental techniques (can be disabled)
    if allow_experimental:
        # Plus Four Technique (e.g., 8A -> 12A)
        plus_four_num = (num1 + 4 - 1) % 12 + 1
        if num2 == plus_four_num and letter1 == letter2:
            return int(70 * penalty)

        # Plus Seven Technique (circle of fifths)
        plus_seven_num = (num1 + 7 - 1) % 12 + 1
        if num2 == plus_seven_num and letter1 == letter2:
            return int(65 * penalty)

    # Diagonal Mixing
    if letter1 != letter2:
        if num2 == next_num_cw or num2 == next_num_ccw:
            return int(60 * penalty)
        # Energy Boost/Drop techniques
        if num1 == num2 and letter1 == 'A' and letter2 == 'B':
            return int(85 * penalty)
        if num1 == num2 and letter1 == 'B' and letter2 == 'A':
            return int(75 * penalty)

    # Return low score (affected by strictness - stricter = lower fallback)
    return max(5, int((15 - strictness) * penalty))

def _sort_harmonic_flow(tracks: list[Track], bpm_tolerance: float, **kwargs) -> list[Track]:
    """Greedy algorithm to find the most harmonically compatible path."""
    unprocessed = list(tracks)
    start_track = min(unprocessed, key=lambda t: t.bpm)
    final_playlist = [start_track]
    unprocessed.remove(start_track)

    current_track = start_track
    while unprocessed:
        best_next = None
        highest_score = -1
        for candidate in unprocessed:
            score = calculate_compatibility(current_track, candidate, bpm_tolerance, **kwargs)
            if score > highest_score:
                highest_score = score
                best_next = candidate
        
        if best_next:
            final_playlist.append(best_next)
            unprocessed.remove(best_next)
            current_track = best_next
        else:
            # If no compatible track is found, pick a random one to avoid getting stuck
            random_pick = random.choice(unprocessed)
            final_playlist.append(random_pick)
            unprocessed.remove(random_pick)
            current_track = random_pick
            
    return final_playlist

def _sort_harmonic_flow_enhanced(tracks: list[Track], bpm_tolerance: float, **kwargs) -> list[Track]:
    """Enhanced harmonic flow using look-ahead and backtracking to avoid local optima."""
    if len(tracks) <= 2:
        return sorted(tracks, key=lambda t: t.bpm)

    # Capture kwargs in closure for nested function
    compat_kwargs = kwargs

    def _lookahead_score(current: Track, remaining: List[Track], depth: int = 2) -> Tuple[Track, float]:
        """Look ahead to find the best path with given depth."""
        if not remaining or depth <= 0:
            return None, 0.0

        best_candidate = None
        best_total_score = -1

        for candidate in remaining:
            immediate_score = calculate_compatibility(current, candidate, bpm_tolerance, **compat_kwargs)
            if immediate_score == 0:  # Skip incompatible tracks
                continue

            future_score = 0.0
            if depth > 1 and len(remaining) > 1:
                next_remaining = [t for t in remaining if t != candidate]
                _, future_score = _lookahead_score(candidate, next_remaining, depth - 1)

            total_score = immediate_score + 0.7 * future_score  # Weight immediate higher
            if total_score > best_total_score:
                best_total_score = total_score
                best_candidate = candidate

        return best_candidate, best_total_score

    unprocessed = list(tracks)
    # Start with a track that has good overall connectivity
    start_track = _find_best_starting_track(tracks, bpm_tolerance, **kwargs)
    final_playlist = [start_track]
    unprocessed.remove(start_track)

    current_track = start_track
    while unprocessed:
        best_next, score = _lookahead_score(current_track, unprocessed, depth=2)  # Optimized: depth=2 (was 3)

        if best_next and score > 0:
            final_playlist.append(best_next)
            unprocessed.remove(best_next)
            current_track = best_next
        else:
            # Fallback: choose track with best single compatibility
            fallback = max(unprocessed,
                         key=lambda t: calculate_compatibility(current_track, t, bpm_tolerance, **compat_kwargs))
            final_playlist.append(fallback)
            unprocessed.remove(fallback)
            current_track = fallback

    return final_playlist

def _find_best_starting_track(tracks: list[Track], bpm_tolerance: float, **kwargs) -> Track:
    """Find the track with the best overall connectivity as starting point.

    Optimized: For large playlists, uses a more efficient sampling strategy.
    """
    if not tracks:
        return None
    if len(tracks) <= 1:
        return tracks[0]

    # Optimization: For large playlists, sample max 30 candidates and check against max 20 others
    # This keeps the complexity O(1) for very large N
    max_candidates = min(30, len(tracks))
    max_comparisons = min(20, len(tracks))

    # Sample evenly distributed tracks as candidates
    candidate_indices = [int(i * (len(tracks) - 1) / (max_candidates - 1)) for i in range(max_candidates)]
    comparison_indices = [int(i * (len(tracks) - 1) / (max_comparisons - 1)) for i in range(max_comparisons)]

    best_track = tracks[0]
    best_score = -1

    for i in candidate_indices:
        track = tracks[i]
        total_compatibility = 0
        connections = 0

        for j in comparison_indices:
            if i == j:
                continue
            score = calculate_compatibility(track, tracks[j], bpm_tolerance, **kwargs)
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

def _prepare_track_metrics(tracks: list[Track]) -> list[tuple[Track, float, float, float]]:
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

def _sort_peak_time(tracks: list[Track], bpm_tolerance: float, **kwargs) -> list[Track]:
    """Arrange tracks to build towards a peak (combined BPM/Energy) before a controlled decline."""
    if not tracks:
        return []

    scored_tracks = _prepare_track_metrics(tracks)
    scored_tracks.sort(key=lambda item: item[1])  # ascending combined score

    count = len(scored_tracks)
    if count <= 2:
        return [item[0] for item in scored_tracks]

    waveform_positions = sorted(
        range(count),
        key=lambda idx: math.sin((idx / (count - 1)) * math.pi)
    )

    ordered_tracks: list[Track | None] = [None] * count
    for (track, *_), position in zip(scored_tracks, waveform_positions):
        ordered_tracks[position] = track

    # type ignore safe due to population step above
    return [track for track in ordered_tracks if track is not None]

def _sort_energy_wave(tracks: list[Track], bpm_tolerance: float, **kwargs) -> list[Track]:
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

def _sort_peak_time_enhanced(tracks: list[Track], bpm_tolerance: float, **kwargs) -> list[Track]:
    """Enhanced peak-time arrangement with harmonic considerations and multiple peaks."""
    if not tracks:
        return []

    if len(tracks) <= 3:
        return sorted(tracks, key=lambda t: t.bpm + t.energy)

    # Get peak position from advanced params (default: 70%)
    peak_position = kwargs.get('peak_position', 70) / 100.0

    scored_tracks = _prepare_track_metrics(tracks)
    count = len(scored_tracks)

    # Create a double-peak curve for longer sets
    peak_curve = []
    for idx in range(count):
        # Create asymmetric curve: slow build, sharp peak, controlled decline
        if idx < count * peak_position:  # Build phase (user-defined)
            curve_val = (idx / (count * peak_position)) ** 1.5  # Exponential build
        else:  # Decline phase
            decline_progress = (idx - count * peak_position) / (count * (1 - peak_position))
            curve_val = 1.0 - (decline_progress ** 0.7)  # Controlled decline
        peak_curve.append(curve_val)

    # Sort tracks by curve position preference
    waveform_positions = sorted(range(count), key=lambda idx: peak_curve[idx])

    # Assign tracks to positions with harmonic consideration
    ordered_tracks: list[Track | None] = [None] * count

    for position_idx, track_idx in enumerate(zip(scored_tracks, waveform_positions)):
        track, score, norm_bpm, norm_energy = track_idx[0]
        position = track_idx[1]

        if position < len(ordered_tracks):
            ordered_tracks[position] = track

    # Apply harmonic smoothing pass
    result = [track for track in ordered_tracks if track is not None]
    return _apply_harmonic_smoothing(result, bpm_tolerance, **kwargs)

def _apply_harmonic_smoothing(tracks: list[Track], bpm_tolerance: float, **kwargs) -> list[Track]:
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
            current_score = calculate_compatibility(result[i], result[i + 1], bpm_tolerance, **kwargs)

            # Try swapping with next track if it improves harmony
            if i + 2 < len(result):
                swap_score = calculate_compatibility(result[i], result[i + 2], bpm_tolerance, **kwargs)
                next_swap_score = calculate_compatibility(result[i + 1], result[i + 2], bpm_tolerance, **kwargs)
                # Calculate what score would be AFTER swap: [i]->[i+1] becomes [i]->[i+2], [i+2]->[i+1]
                new_pair_score = calculate_compatibility(result[i + 2], result[i + 1], bpm_tolerance, **kwargs)

                # Compare: current transition score vs score after swap
                if swap_score + new_pair_score > current_score + next_swap_score:
                    # Only swap if energy curve isn't severely disrupted
                    energy_disruption = abs(result[i].energy - result[i + 2].energy)
                    if energy_disruption < 20:  # Threshold for acceptable energy jump
                        result[i + 1], result[i + 2] = result[i + 2], result[i + 1]
                        improved = True

    return result

def _sort_emotional_journey(tracks: list[Track], bpm_tolerance: float, **kwargs) -> list[Track]:
    """Create an emotional journey based on energy, BPM, and harmonic progression."""
    if len(tracks) <= 3:
        return sorted(tracks, key=lambda t: (t.energy, t.bpm))

    # Get energy direction from advanced params
    energy_dir_str = kwargs.get('energy_direction', 'Auto')

    # Map user selection to energy directions for each phase
    if energy_dir_str == "Build Up":
        # Continuous energy build throughout
        phase_directions = [EnergyDirection.UP, EnergyDirection.UP, EnergyDirection.UP, EnergyDirection.UP]
    elif energy_dir_str == "Cool Down":
        # Continuous energy decline throughout
        phase_directions = [EnergyDirection.DOWN, EnergyDirection.DOWN, EnergyDirection.DOWN, EnergyDirection.DOWN]
    elif energy_dir_str == "Maintain":
        # Keep energy consistent
        phase_directions = [EnergyDirection.MAINTAIN, EnergyDirection.MAINTAIN, EnergyDirection.MAINTAIN, EnergyDirection.MAINTAIN]
    else:  # "Auto" - default emotional journey curve
        phase_directions = [EnergyDirection.UP, EnergyDirection.UP, EnergyDirection.MAINTAIN, EnergyDirection.DOWN]

    # Sort tracks by energy and BPM
    energy_sorted = sorted(tracks, key=lambda t: t.energy)
    count = len(tracks)

    # Distribute tracks across phases
    opening_count = max(1, count // 4)
    building_count = max(1, int(count * 0.4))
    peak_count = max(1, int(count * 0.2))
    resolution_count = count - opening_count - building_count - peak_count

    # Select tracks for each phase
    opening_tracks = energy_sorted[:opening_count]
    building_tracks = energy_sorted[opening_count:opening_count + building_count]
    peak_tracks = energy_sorted[-peak_count:]
    resolution_tracks = energy_sorted[opening_count + building_count:-peak_count] if resolution_count > 0 else []

    # Arrange each phase with harmonic consideration
    journey = []
    journey.extend(_arrange_phase(opening_tracks, bpm_tolerance, phase_directions[0]))
    journey.extend(_arrange_phase(building_tracks, bpm_tolerance, phase_directions[1]))
    journey.extend(_arrange_phase(peak_tracks, bpm_tolerance, phase_directions[2]))
    journey.extend(_arrange_phase(resolution_tracks, bpm_tolerance, phase_directions[3]))

    return journey

def _arrange_phase(tracks: list[Track], bpm_tolerance: float, energy_direction: EnergyDirection) -> list[Track]:
    """Arrange tracks within a phase considering energy direction and harmony."""
    if not tracks:
        return []
    if len(tracks) == 1:
        return tracks

    # Use enhanced compatibility with energy direction preference
    arranged = []
    remaining = list(tracks)

    # Start with track that best fits the phase
    if energy_direction == EnergyDirection.UP:
        current = min(remaining, key=lambda t: t.energy + t.bpm)
    elif energy_direction == EnergyDirection.DOWN:
        current = max(remaining, key=lambda t: t.energy + t.bpm)
    else:  # MAINTAIN
        avg_energy = sum(t.energy for t in remaining) / len(remaining)
        current = min(remaining, key=lambda t: abs(t.energy - avg_energy))

    arranged.append(current)
    remaining.remove(current)

    # Greedily select best transitions
    while remaining:
        best_next = None
        best_score = -1

        for candidate in remaining:
            metrics = calculate_enhanced_compatibility(current, candidate, bpm_tolerance, energy_direction)
            if metrics.overall_score > best_score:
                best_score = metrics.overall_score
                best_next = candidate

        if best_next:
            arranged.append(best_next)
            remaining.remove(best_next)
            current = best_next
        else:
            # Fallback
            arranged.append(remaining.pop())

    return arranged

def _sort_genre_flow(tracks: list[Track], bpm_tolerance: float, **kwargs) -> list[Track]:
    """Arrange tracks to create smooth genre transitions while maintaining energy."""
    if len(tracks) <= 2:
        return sorted(tracks, key=lambda t: t.bpm)

    # Get genre parameters
    genre_mixing_enabled = kwargs.get('genre_mixing', True)
    genre_weight = kwargs.get('genre_weight', 0.3)  # 0.0-1.0

    # If genre mixing disabled, use harmonic flow instead
    if not genre_mixing_enabled:
        return _sort_harmonic_flow(tracks, bpm_tolerance, **kwargs)

    # Group tracks by genre (bevorzuge detected_genre wenn vorhanden)
    genre_groups = {}
    for track in tracks:
        genre = getattr(track, 'detected_genre', '') or track.genre
        if not genre or genre == "Unknown":
            genre = "Mixed"
        if genre not in genre_groups:
            genre_groups[genre] = []
        genre_groups[genre].append(track)

    # Genre-Kompatibilitaet via DJ Brain Matrix + Fallback fuer ID3-Genres
    base_genre_compatibility = {
        ("Electronic", "House"): 0.9,
        ("House", "Techno"): 0.8,
        ("Hip Hop", "R&B"): 0.8,
        ("Rock", "Alternative"): 0.8,
        ("Pop", "Electronic"): 0.7,
        ("Techno", "Electronic"): 0.85,
        ("Trance", "Electronic"): 0.85,
        ("Drum & Bass", "Electronic"): 0.75,
    }

    # Apply genre_weight to compatibility scores
    # Higher weight = stronger preference for same/similar genres
    genre_compatibility = {}
    for key, value in base_genre_compatibility.items():
        # Scale compatibility based on weight (higher weight = more separation)
        adjusted = value * (1 - genre_weight) + genre_weight
        genre_compatibility[key] = adjusted

    # Create transitions between genres
    result = []
    processed_genres = set()

    # Start with the genre that has the most tracks
    current_genre = max(genre_groups.keys(), key=lambda g: len(genre_groups[g]))

    while len(processed_genres) < len(genre_groups):
        if current_genre in genre_groups and current_genre not in processed_genres:
            # Arrange tracks within current genre (pass kwargs for harmonic params)
            genre_tracks = _sort_consistent(genre_groups[current_genre], bpm_tolerance, **kwargs)
            result.extend(genre_tracks)
            processed_genres.add(current_genre)

        # Find best next genre
        best_next_genre = None
        best_compatibility = 0

        for genre in genre_groups:
            if genre not in processed_genres:
                # DJ Brain Matrix hat Vorrang, Fallback auf alte Kompatibilitaet
                dj_compat = get_genre_compatibility(current_genre, genre)
                if dj_compat > 0.5:
                    compatibility = dj_compat
                else:
                    compatibility = genre_compatibility.get((current_genre, genre), 0.5 * (1 - genre_weight))
                    compatibility += genre_compatibility.get((genre, current_genre), 0.5 * (1 - genre_weight))
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

def _sort_consistent(tracks: list[Track], bpm_tolerance: float, **kwargs) -> list[Track]:
    """Keep transitions smooth by minimising BPM/Energy jumps while preferring harmonic compatibility."""
    if not tracks:
        return []

    # Capture kwargs for nested function
    compat_kwargs = kwargs

    remaining = list(tracks)
    average_bpm = sum(getattr(track, "bpm", 0.0) for track in remaining) / len(remaining)
    average_energy = sum(getattr(track, "energy", 0) for track in remaining) / len(remaining)

    def _center_distance(track: Track) -> float:
        bpm_deviation = abs(getattr(track, "bpm", average_bpm) - average_bpm)
        energy_deviation = abs(getattr(track, "energy", average_energy) - average_energy) / 5.0
        return bpm_deviation + energy_deviation

    current = min(remaining, key=_center_distance)
    playlist = [current]
    remaining.remove(current)

    while remaining:
        def _transition_cost(candidate: Track) -> float:
            bpm_delta, _ = effective_bpm_diff(
                getattr(candidate, "bpm", current.bpm),
                getattr(current, "bpm", 0.0)
            )
            energy_delta = abs(getattr(candidate, "energy", current.energy) - getattr(current, "energy", 0)) / 5.0
            compatibility = calculate_compatibility(current, candidate, bpm_tolerance, **compat_kwargs)
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
        mix_out_point = max(mix_in_point + 4.0, duration - min(duration * 0.05, fallback_overlap))
    else:
        mix_out_point = mix_in_point + max(4.0, fallback_overlap / 2)

    if duration > 0:
        mix_in_point = max(0.0, min(mix_in_point, duration))
        mix_out_point = max(mix_in_point + 1.0, min(mix_out_point, duration))

    return mix_in_point, mix_out_point

def _categorise_risk_level(compatibility_score: int, bpm_delta: float, bpm_tolerance: float, energy_delta: int) -> str:
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
    genre_a = getattr(from_track, 'detected_genre', 'Unknown') or 'Unknown'
    genre_b = getattr(to_track, 'detected_genre', 'Unknown') or 'Unknown'

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
        if genre_a in melodic_genres or genre_b in melodic_genres:
            return "filter_ride"
        return "smooth_blend"

    # --- Regel 6: Gute Harmonie, BPM passt ---
    if harmonic_score >= 70 and eff_diff <= bpm_tolerance:
        # Harte Genres bevorzugen Bass Swap
        hard_genres = {"Tech House", "Techno", "Drum & Bass", "Minimal"}
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


# Transition-Typ Beschreibungen fuer UI
TRANSITION_TYPE_LABELS: dict[str, str] = {
    "smooth_blend": "Smooth Blend",
    "bass_swap": "Bass Swap",
    "breakdown_bridge": "Breakdown Bridge",
    "drop_cut": "Drop Cut",
    "filter_ride": "Filter Ride",
    "halftime_switch": "Halftime Switch",
    "echo_out": "Echo Out",
    "cold_cut": "Cold Cut",
}

TRANSITION_TYPE_DESCRIPTIONS: dict[str, str] = {
    "smooth_blend": (
        "Langer EQ-Blend ueber 16-32 Bars.\n"
        "Beide Tracks laufen parallel, Bass und\n"
        "Mids werden sanft uebergeblendet."
    ),
    "bass_swap": (
        "Schneller Bass-Tausch an einem Phrase-Anfang.\n"
        "Bass vom ausgehenden Track cutten,\n"
        "gleichzeitig Bass vom eingehenden Track reinbringen."
    ),
    "breakdown_bridge": (
        "Transition ueber den Breakdown eines Tracks.\n"
        "Nutze den ruhigen Teil um BPM oder\n"
        "Energie-Unterschiede zu ueberbruecken."
    ),
    "drop_cut": (
        "Harter Schnitt direkt am Drop.\n"
        "Der neue Track startet mit voller Energie\n"
        "fuer maximalen Impact auf dem Dancefloor."
    ),
    "filter_ride": (
        "Filter-basierter Uebergang.\n"
        "Highpass/Lowpass Filter nutzen um\n"
        "melodische Elemente ein- und auszublenden."
    ),
    "halftime_switch": (
        "Half/Double-Time Wechsel.\n"
        "Tempo-Verhaeltnis 2:1 — der Beat aendert sich,\n"
        "aber der Groove bleibt kompatibel.\n"
        "Am besten am Breakdown oder Build-Up."
    ),
    "echo_out": (
        "Echo/Delay-basierter Ausklang.\n"
        "Den ausgehenden Track mit Echo/Delay\n"
        "ausklingen lassen, waehrend der neue Track\n"
        "langsam eingeblendet wird."
    ),
    "cold_cut": (
        "Harter Cut ohne Blend.\n"
        "Die Tracks passen harmonisch nicht zusammen —\n"
        "kurzer Stop oder Effekt, dann neuer Track starten."
    ),
}


def _build_transition_description(
    compatibility_score: int,
    bpm_delta: float,
    bpm_tolerance: float,
    energy_delta: int,
    metrics: 'TransitionMetrics',
    from_track: Track,
    to_track: Track,
    has_dj_brain: bool = False,
) -> str:
    """
    Erzeugt eine aussagekraeftige DJ-Beschreibung der Transition.
    Gibt konkrete, nuetzliche Infos fuer den DJ - keine generischen Phrasen.

    Wenn has_dj_brain=True, werden BPM- und Key-Details uebersprungen,
    weil der DJ Brain diese schon als Risk-Notes liefert.
    """
    parts: list[str] = []

    # --- 1. Harmonic Bewertung ---
    harmonic = metrics.harmonic_score
    key_a = getattr(from_track, 'camelotCode', '') or ''
    key_b = getattr(to_track, 'camelotCode', '') or ''
    key_info = f" ({key_a}->{key_b})" if key_a and key_b else ""

    if has_dj_brain:
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
    if not has_dj_brain:
        abs_bpm = abs(bpm_delta)
        if abs_bpm < 0.5:
            pass  # Perfektes BPM-Match braucht keinen Kommentar
        elif abs_bpm <= bpm_tolerance:
            parts.append(f"BPM-Anpassung {bpm_delta:+.1f} -- Pitch Fader korrigieren")
        else:
            parts.append(f"BPM-Sprung {bpm_delta:+.1f} -- harter Cut oder Breakdown nutzen")

    # --- 3. Energie-Verlauf (fuer Dancefloor-Dramaturgie) ---
    if energy_delta > 25:
        parts.append("Grosser Energie-Push [++] -- Drop-Einstieg ideal")
    elif energy_delta > 12:
        parts.append("Energie steigt [+] -- im Build reinmixen")
    elif energy_delta < -25:
        parts.append("Starker Energie-Drop [--] -- Breakdown-Uebergang planen")
    elif energy_delta < -12:
        parts.append("Energie faellt [-] -- im Outro sanft ueberblenden")
    else:
        parts.append("Energie stabil [=] -- nahtlose Ueberblendung moeglich")

    # --- 4. Gesamtbewertung als klarer Satz ---
    if compatibility_score >= 85:
        parts.append("Sichere Transition -- laeuft fast von allein")
    elif compatibility_score >= 70:
        parts.append("Solide Transition -- mit Aufmerksamkeit sauber mixbar")
    elif compatibility_score >= 55:
        parts.append("Machbar, aber anspruchsvoll -- Timing und EQ muessen stimmen")
    else:
        parts.append("Riskante Transition -- nur fuer erfahrene DJs oder mit langem Breakdown")

    return "; ".join(parts)

def compute_transition_recommendations(
    playlist: List[Track],
    bpm_tolerance: float = 3.0,
    default_overlap: float = 12.0
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
                max(6.0, min(current.duration, upcoming.duration) * 0.2)
            )

        current_mix_in, current_mix_out = _resolve_mix_points(current, effective_overlap)
        next_mix_in, next_mix_out = _resolve_mix_points(upcoming, effective_overlap)

        # DJ Logic: The mix usually starts at the 'mix_in' of the upcoming track
        # and ends at the 'mix_out' of the current track.
        # We want to align the 'mix_in' of the next track with a phrase in the current track.
        
        # Calculate how long the transition should be (e.g., 16 or 32 bars)
        seconds_per_beat = 60.0 / current.bpm if current.bpm > 0 else 0.5
        seconds_per_bar = seconds_per_beat * 4
        
        # Standard DJ transition length: 32 bars (approx 60s at 124bpm)
        transition_duration = seconds_per_bar * 32 
        
        # Adjust transition duration if tracks are short
        if current.duration > 0:
            transition_duration = min(transition_duration, current.duration * 0.25)
            
        fade_out_start = max(0.0, current_mix_out - transition_duration)
        fade_in_start = next_mix_in
        mix_entry = next_mix_in
        overlap = transition_duration

        metrics = calculate_enhanced_compatibility(current, upcoming, bpm_tolerance)
        compatibility_score = int(metrics.overall_score * 100)

        energy_delta = upcoming.energy - current.energy
        eff_bpm_diff, bpm_relation = effective_bpm_diff(current.bpm, upcoming.bpm)
        # Vorzeichen-behaftetes Delta fuer Anzeige (positiv = schneller)
        bpm_delta = upcoming.bpm - current.bpm
        # Fuer Risikobewertung effektive Differenz nutzen
        risk_bpm_delta = eff_bpm_diff if bpm_relation == "direct" else eff_bpm_diff

        risk_level = _categorise_risk_level(compatibility_score, risk_bpm_delta, bpm_tolerance, energy_delta)

        notes_parts = []

        # DJ Brain Empfehlungen wenn Genre-Daten vorhanden
        dj_rec = None
        current_genre = getattr(current, 'detected_genre', 'Unknown') or 'Unknown'
        upcoming_genre = getattr(upcoming, 'detected_genre', 'Unknown') or 'Unknown'
        has_dj_data = current_genre != 'Unknown' and upcoming_genre != 'Unknown'

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

                # DJ Brain Transition-Laenge uebernehmen
                if dj_rec.transition_bars > 0 and current.bpm > 0:
                    seconds_per_bar = (60.0 / current.bpm) * 4
                    overlap = seconds_per_bar * dj_rec.transition_bars
                    fade_out_start = max(0.0, current_mix_out - overlap)
            except Exception:
                pass  # Fallback auf Standard-Notes

        # Aussagekraeftige DJ-Beschreibung immer anhaengen
        # has_dj_brain=True vermeidet doppelte BPM/Key-Warnungen
        transition_desc = _build_transition_description(
            compatibility_score, bpm_delta, bpm_tolerance,
            energy_delta, metrics, current, upcoming,
            has_dj_brain=(dj_rec is not None),
        )
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
            )
        )

    return recommendations

def calculate_playlist_quality(tracks: list[Track], bpm_tolerance: float) -> Dict[str, float]:
    """Calculate comprehensive quality metrics for a playlist."""
    if len(tracks) < 2:
        return {"overall_score": 1.0, "harmonic_flow": 1.0, "energy_consistency": 1.0, "bpm_smoothness": 1.0}

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
    energy_consistency = max(0, 1 - avg_energy_diff / 50.0)  # 50 is max reasonable energy diff
    if bpm_tolerance <= 0:
        bpm_smoothness = 1.0 if avg_bpm_diff == 0 else 0.0
    else:
        bpm_smoothness = max(0.0, 1 - avg_bpm_diff / bpm_tolerance)

    # Overall weighted score
    overall_score = 0.5 * harmonic_flow + 0.25 * energy_consistency + 0.25 * bpm_smoothness

    return {
        "overall_score": overall_score,
        "harmonic_flow": harmonic_flow,
        "energy_consistency": energy_consistency,
        "bpm_smoothness": bpm_smoothness,
        "avg_harmonic_score": avg_harmonic * 100,
        "avg_energy_jump": avg_energy_diff,
        "avg_bpm_jump": avg_bpm_diff
    }

# --- Main Dispatcher --- #

STRATEGIES = {
    "Harmonic Flow": _sort_harmonic_flow,
    "Harmonic Flow Enhanced": _sort_harmonic_flow_enhanced,
    "Warm-Up": _sort_warm_up,
    "Cool-Down": _sort_cool_down,
    "Peak-Time": _sort_peak_time,
    "Peak-Time Enhanced": _sort_peak_time_enhanced,
    "Energy Wave": _sort_energy_wave,
    "Emotional Journey": _sort_emotional_journey,
    "Genre Flow": _sort_genre_flow,
    "Consistent": _sort_consistent,
}

def generate_playlist(tracks: list[Track], mode: str, bpm_tolerance: float = 3.0,
                      advanced_params: Optional[Dict] = None) -> list[Track]:
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
        return tracks # Return original if no tracks are valid

    # Get the sorting function from the strategy map
    sorter = STRATEGIES.get(mode, _sort_harmonic_flow) # Default to harmonic flow

    # Call the selected sorting strategy with advanced params
    result = sorter(valid_tracks, bpm_tolerance=bpm_tolerance, **advanced_params)

    # Log quality metrics for analysis
    quality = calculate_playlist_quality(result, bpm_tolerance)
    print(f"Playlist Quality Metrics for {mode}:")
    print(f"  Overall Score: {quality['overall_score']:.2f}")
    print(f"  Harmonic Flow: {quality['harmonic_flow']:.2f}")
    print(f"  Energy Consistency: {quality['energy_consistency']:.2f}")
    print(f"  BPM Smoothness: {quality['bpm_smoothness']:.2f}")

    return result

def benchmark_algorithms(tracks: list[Track], bpm_tolerance: float = 3.0) -> Dict[str, Dict[str, float]]:
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
  energy_phase: str  # "intro", "build", "peak", "sustain", "cooldown"


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

  target_seconds = target_minutes * 60.0
  peak_position_pct = max(0.1, min(0.9, peak_position_pct))

  entries: list[SetTimelineEntry] = []
  current_time = 0.0

  for i, track in enumerate(tracks):
    track_dur = max(track.duration, 30.0)  # Minimum 30s pro Track

    # Overlap zum naechsten Track berechnen
    if i < len(tracks) - 1:
      # Nutze Mix-Points wenn vorhanden, sonst Default
      mix_out = track.mix_out_point if track.mix_out_point > 0 else track_dur * 0.85
      overlap = track_dur - mix_out
      overlap = max(4.0, min(overlap, default_overlap, track_dur * 0.3))
    else:
      overlap = 0.0  # Letzter Track hat keinen Overlap

    playing_duration = track_dur - overlap
    end_time = current_time + playing_duration

    entries.append(SetTimelineEntry(
      track=track,
      start_time=round(current_time, 2),
      end_time=round(end_time, 2),
      playing_duration=round(playing_duration, 2),
      overlap_with_next=round(overlap, 2),
      is_peak=False,  # Wird spaeter gesetzt
      energy_phase="build",  # Wird spaeter gesetzt
    ))

    current_time = end_time

  total_seconds = current_time
  total_minutes = total_seconds / 60.0

  # Peak-Track identifizieren (hoechste Energie nahe peak_position_pct)
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

  if entries:
    entries[best_peak_idx].is_peak = True

  # Energy-Phasen zuweisen
  n = len(entries)
  if n > 0:
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
        entry.energy_phase = "build"
      elif relative_pos <= peak_pos:
        entry.energy_phase = "build"
      elif relative_pos <= peak_pos + 0.15:
        entry.energy_phase = "sustain"
      elif relative_pos > peak_pos + 0.15:
        entry.energy_phase = "cooldown"
      else:
        entry.energy_phase = "build"

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


# === Similarity Clustering (MFCC-basiert) ===

def mfcc_distance(fp1: list, fp2: list) -> float:
    """Berechnet euklidische Distanz zwischen zwei MFCC-Fingerprints.

    Args:
        fp1: MFCC-Vektor von Track 1 (Liste von floats, Laenge 13)
        fp2: MFCC-Vektor von Track 2

    Returns:
        Euklidische Distanz. 0.0 = identisch. Groesser = unaehnlicher.
        Gibt float('inf') zurueck wenn ein Fingerprint leer ist.
    """
    if not fp1 or not fp2:
        return float('inf')
    if len(fp1) != len(fp2):
        return float('inf')

    return math.sqrt(sum((a - b) ** 2 for a, b in zip(fp1, fp2)))


def find_similar_tracks(
    reference: Track,
    candidates: list[Track],
    max_results: int = 10,
    max_distance: float | None = None,
) -> list[tuple[Track, float]]:
    """Findet die aehnlichsten Tracks basierend auf MFCC-Fingerprints.

    Args:
        reference: Referenz-Track
        candidates: Liste von Kandidaten
        max_results: Maximale Anzahl Ergebnisse
        max_distance: Optionale maximale Distanz (filtert Ergebnisse)

    Returns:
        Liste von (Track, Distanz) Tupeln, sortiert nach Aehnlichkeit (kleinste Distanz zuerst).
    """
    if not reference.mfcc_fingerprint:
        return []

    scored = []
    for track in candidates:
        if track is reference:
            continue
        dist = mfcc_distance(reference.mfcc_fingerprint, track.mfcc_fingerprint)
        if dist == float('inf'):
            continue
        if max_distance is not None and dist > max_distance:
            continue
        scored.append((track, dist))

    scored.sort(key=lambda x: x[1])
    return scored[:max_results]


def cluster_tracks_by_similarity(
    tracks: list[Track],
    n_clusters: int = 3,
    max_iterations: int = 50,
) -> list[list[Track]]:
    """Gruppiert Tracks in Cluster basierend auf MFCC-Aehnlichkeit (k-Means).

    Einfacher k-Means Algorithmus ohne externe Dependencies (kein sklearn noetig).

    Args:
        tracks: Liste von Tracks mit MFCC-Fingerprints
        n_clusters: Anzahl gewuenschter Cluster
        max_iterations: Maximale Iterationen

    Returns:
        Liste von Track-Listen (Cluster). Tracks ohne MFCC landen in einem Extra-Cluster.
    """
    # Trenne Tracks mit/ohne MFCC
    with_mfcc = [t for t in tracks if t.mfcc_fingerprint and len(t.mfcc_fingerprint) > 0]
    without_mfcc = [t for t in tracks if not t.mfcc_fingerprint or len(t.mfcc_fingerprint) == 0]

    if len(with_mfcc) <= n_clusters:
        # Zu wenige Tracks — jeder Track ist sein eigenes Cluster
        clusters = [[t] for t in with_mfcc]
        if without_mfcc:
            clusters.append(without_mfcc)
        return clusters

    # k-Means: Initialisierung mit gleichmaessig verteilten Tracks
    step = len(with_mfcc) // n_clusters
    centroids = [
        list(with_mfcc[i * step].mfcc_fingerprint) for i in range(n_clusters)
    ]

    assignments = [0] * len(with_mfcc)

    for _ in range(max_iterations):
        # Assign: Jeden Track dem naechsten Centroid zuweisen
        new_assignments = []
        for track in with_mfcc:
            dists = [mfcc_distance(track.mfcc_fingerprint, c) for c in centroids]
            new_assignments.append(dists.index(min(dists)))

        # Konvergenz-Check
        if new_assignments == assignments:
            break
        assignments = new_assignments

        # Update: Centroids neu berechnen
        dim = len(centroids[0])
        for k in range(n_clusters):
            members = [with_mfcc[i] for i, a in enumerate(assignments) if a == k]
            if not members:
                continue
            new_centroid = [0.0] * dim
            for m in members:
                for d in range(dim):
                    new_centroid[d] += m.mfcc_fingerprint[d]
            centroids[k] = [v / len(members) for v in new_centroid]

    # Cluster zusammenbauen
    clusters = [[] for _ in range(n_clusters)]
    for i, a in enumerate(assignments):
        clusters[a].append(with_mfcc[i])

    # Leere Cluster entfernen
    clusters = [c for c in clusters if c]

    # Tracks ohne MFCC als eigenes Cluster anhaengen
    if without_mfcc:
        clusters.append(without_mfcc)

    return clusters


def get_cluster_summary(clusters: list[list[Track]]) -> list[dict]:
    """Erstellt eine Zusammenfassung fuer jedes Cluster.

    Args:
        clusters: Liste von Track-Listen aus cluster_tracks_by_similarity

    Returns:
        Liste von Dicts mit Cluster-Infos (size, avg_bpm, genres, avg_energy, etc.)
    """
    summaries = []
    for i, cluster in enumerate(clusters):
        if not cluster:
            continue

        bpms = [t.bpm for t in cluster if t.bpm > 0]
        energies = [t.energy for t in cluster if t.energy > 0]
        genres = {}
        for t in cluster:
            g = t.detected_genre if t.detected_genre != "Unknown" else t.genre
            if g and g != "Unknown":
                genres[g] = genres.get(g, 0) + 1

        summary = {
            "cluster_id": i,
            "size": len(cluster),
            "avg_bpm": round(sum(bpms) / len(bpms), 1) if bpms else 0.0,
            "bpm_range": (round(min(bpms), 1), round(max(bpms), 1)) if bpms else (0.0, 0.0),
            "avg_energy": round(sum(energies) / len(energies), 1) if energies else 0.0,
            "top_genres": sorted(genres.items(), key=lambda x: -x[1])[:3],
            "tracks": [t.title for t in cluster[:5]],  # Erste 5 Titel als Preview
        }
        summaries.append(summary)

    return summaries
