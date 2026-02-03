from __future__ import annotations  # Python 3.9 compatibility for | type hints

from .models import Track, CAMELOT_MAP, key_to_camelot
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

    # BPM smoothness (exponential decay for large differences)
    bpm_diff = abs(track1.bpm - track2.bpm)
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

    # Genre compatibility (basic implementation)
    genre_compatibility = 1.0 if track1.genre == track2.genre else 0.7
    if track1.genre == "Unknown" or track2.genre == "Unknown":
        genre_compatibility = 0.8

    # Overall weighted score
    overall_score = (
        0.4 * (harmonic_score / 100.0) +
        0.25 * bpm_smoothness +
        0.25 * energy_flow +
        0.1 * genre_compatibility
    )

    return TransitionMetrics(
        harmonic_score=harmonic_score,
        bpm_smoothness=bpm_smoothness,
        energy_flow=energy_flow,
        genre_compatibility=genre_compatibility,
        overall_score=overall_score
    )

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

    if abs(track1.bpm - track2.bpm) > bpm_tolerance:
        return 0 # No compatibility if BPM difference is too high
    if not track1.camelotCode or not track2.camelotCode:
        return 10 # Minimal compatibility if Camelot code is missing

    num1, letter1 = _get_camelot_components(track1.camelotCode)
    num2, letter2 = _get_camelot_components(track2.camelotCode)

    if num1 == 0 or num2 == 0: # Invalid camelot codes
        return 10

    # Direct matches (always allowed)
    if num1 == num2 and letter1 == letter2: return 100 # Same key
    if num1 == num2 and letter1 != letter2: return 90  # Relative major/minor

    # Adjacent keys (Camelot wheel)
    next_num_cw = (num1 % 12) + 1
    next_num_ccw = (num1 - 2 + 12) % 12 + 1

    if letter1 == letter2: # Same mode, adjacent numbers
        if num2 == next_num_cw or num2 == next_num_ccw: return 80

    # Experimental techniques (can be disabled)
    if allow_experimental:
        # Plus Four Technique (e.g., 8A -> 12A)
        plus_four_num = (num1 + 4 - 1) % 12 + 1
        if num2 == plus_four_num and letter1 == letter2: return 70

        # Plus Seven Technique (circle of fifths)
        plus_seven_num = (num1 + 7 - 1) % 12 + 1
        if num2 == plus_seven_num and letter1 == letter2: return 65

    # Diagonal Mixing
    if letter1 != letter2:
        if num2 == next_num_cw or num2 == next_num_ccw: return 60
        # Energy Boost/Drop techniques
        if num1 == num2 and letter1 == 'A' and letter2 == 'B': return 85
        if num1 == num2 and letter1 == 'B' and letter2 == 'A': return 75

    # Return low score (affected by strictness - stricter = lower fallback)
    return max(5, 15 - strictness)

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

    # Group tracks by genre
    genre_groups = {}
    for track in tracks:
        genre = track.genre if track.genre != "Unknown" else "Mixed"
        if genre not in genre_groups:
            genre_groups[genre] = []
        genre_groups[genre].append(track)

    # Define genre compatibility matrix (simplified)
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
            bpm_delta = abs(getattr(candidate, "bpm", current.bpm) - getattr(current, "bpm", 0.0))
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

        fade_out_start = max(0.0, current_mix_out - effective_overlap)
        fade_in_start = max(0.0, next_mix_in - effective_overlap / 2)
        overlap = max(0.0, current_mix_out - fade_out_start)

        metrics = calculate_enhanced_compatibility(current, upcoming, bpm_tolerance)
        compatibility_score = int(metrics.overall_score * 100)

        energy_delta = upcoming.energy - current.energy
        bpm_delta = upcoming.bpm - current.bpm

        risk_level = _categorise_risk_level(compatibility_score, bpm_delta, bpm_tolerance, energy_delta)

        notes_parts = []
        if energy_delta > 12:
            notes_parts.append("Energy lift")
        elif energy_delta < -12:
            notes_parts.append("Energy dip")
        else:
            notes_parts.append("Energy steady")

        if abs(bpm_delta) > bpm_tolerance:
            notes_parts.append("Beatmatch manually")

        if compatibility_score >= 80:
            notes_parts.append("Harmonic safe zone")
        elif compatibility_score >= 60:
            notes_parts.append("Monitor harmony")
        else:
            notes_parts.append("Consider alternative")

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
                notes=notes
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

        # BPM differences
        bpm_diffs.append(abs(current.bpm - next_track.bpm))

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
