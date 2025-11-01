#!/usr/bin/env python3
"""
Demonstration script for the enhanced playlist algorithms in HarmonicPlaylistGenerator.

This script showcases the new algorithmic improvements:
- Enhanced harmonic compatibility scoring
- Optimized harmonic flow with look-ahead
- Improved peak-time with energy curve modeling
- New Emotional Journey algorithm
- Genre Flow for cross-genre transitions
- Playlist quality metrics and benchmarking
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hpg_core.models import Track
from hpg_core.playlist import (
    generate_playlist, benchmark_algorithms, calculate_playlist_quality,
    calculate_enhanced_compatibility, EnergyDirection, STRATEGIES
)

def create_demo_tracks():
    """Create a diverse set of tracks for demonstration."""
    demo_tracks = [
        # House tracks - compatible keys
        Track("house1.mp3", "Deep House Track", bpm=124, keyNote="C", keyMode="Major",
              camelotCode="8B", energy=70, genre="House", bass_intensity=60),
        Track("house2.mp3", "Soulful House", bpm=126, keyNote="G", keyMode="Major",
              camelotCode="9B", energy=75, genre="House", bass_intensity=65),
        Track("house3.mp3", "Progressive House", bpm=128, keyNote="F", keyMode="Major",
              camelotCode="7B", energy=80, genre="House", bass_intensity=70),

        # Techno tracks - higher energy
        Track("techno1.mp3", "Deep Techno", bpm=130, keyNote="A", keyMode="Minor",
              camelotCode="8A", energy=85, genre="Techno", bass_intensity=75),
        Track("techno2.mp3", "Driving Techno", bpm=132, keyNote="E", keyMode="Minor",
              camelotCode="9A", energy=90, genre="Techno", bass_intensity=80),

        # Ambient/Chill tracks - lower energy
        Track("ambient1.mp3", "Ambient Pad", bpm=115, keyNote="D", keyMode="Minor",
              camelotCode="7A", energy=30, genre="Ambient", bass_intensity=25),
        Track("chill1.mp3", "Downtempo Chill", bpm=118, keyNote="Bb", keyMode="Major",
              camelotCode="6B", energy=40, genre="Chill", bass_intensity=35),

        # Electronic/Breaks
        Track("breaks1.mp3", "Funky Breaks", bpm=134, keyNote="F#", keyMode="Minor",
              camelotCode="11A", energy=82, genre="Breaks", bass_intensity=78),
        Track("electro1.mp3", "Electro Funk", bpm=120, keyNote="D", keyMode="Major",
              camelotCode="10B", energy=65, genre="Electronic", bass_intensity=55),

        # High energy closer
        Track("closer.mp3", "Peak Time Anthem", bpm=136, keyNote="G", keyMode="Minor",
              camelotCode="6A", energy=95, genre="Techno", bass_intensity=85),
    ]

    # Ensure all tracks have camelot codes
    from hpg_core.playlist import key_to_camelot
    for track in demo_tracks:
        key_to_camelot(track)

    return demo_tracks

def demo_enhanced_compatibility():
    """Demonstrate enhanced compatibility calculation."""
    print("\n=== Enhanced Compatibility Demonstration ===")

    tracks = create_demo_tracks()
    track1 = tracks[0]  # House track, 8B
    track2 = tracks[1]  # House track, 9B (adjacent key)

    print(f"\nComparing tracks:")
    print(f"Track 1: {track1.fileName} - {track1.camelotCode}, {track1.bpm} BPM, Energy: {track1.energy}")
    print(f"Track 2: {track2.fileName} - {track2.camelotCode}, {track2.bpm} BPM, Energy: {track2.energy}")

    # Test different energy directions
    for direction in [EnergyDirection.UP, EnergyDirection.DOWN, EnergyDirection.MAINTAIN, None]:
        metrics = calculate_enhanced_compatibility(track1, track2, 5.0, direction)
        print(f"\nEnergy Direction: {direction.value if direction else 'None'}")
        print(f"  Harmonic Score: {metrics.harmonic_score}")
        print(f"  BPM Smoothness: {metrics.bpm_smoothness:.3f}")
        print(f"  Energy Flow: {metrics.energy_flow:.3f}")
        print(f"  Genre Compatibility: {metrics.genre_compatibility:.3f}")
        print(f"  Overall Score: {metrics.overall_score:.3f}")

def demo_algorithm_comparison():
    """Compare all algorithms using the same track set."""
    print("\n=== Algorithm Performance Comparison ===")

    tracks = create_demo_tracks()

    print(f"\nAnalyzing {len(tracks)} tracks:")
    for i, track in enumerate(tracks, 1):
        print(f"{i:2d}. {track.fileName:<20} | {track.camelotCode:<3} | {track.bpm:3.0f} BPM | Energy: {track.energy:2d} | {track.genre}")

    print("\n" + "="*80)
    print("ALGORITHM PERFORMANCE COMPARISON")
    print("="*80)

    # Test each strategy
    for strategy_name in STRATEGIES.keys():
        print(f"\n{strategy_name.upper()}")
        print("-" * 50)

        try:
            # Generate playlist (suppress quality output)
            import io
            import contextlib

            with contextlib.redirect_stdout(io.StringIO()):
                playlist = generate_playlist(tracks, strategy_name, 3.0)

            # Calculate quality metrics
            quality = calculate_playlist_quality(playlist, 3.0)

            print(f"Overall Score:       {quality['overall_score']:.3f}")
            print(f"Harmonic Flow:       {quality['harmonic_flow']:.3f}")
            print(f"Energy Consistency:  {quality['energy_consistency']:.3f}")
            print(f"BPM Smoothness:      {quality['bpm_smoothness']:.3f}")
            print(f"Avg Harmonic Score:  {quality['avg_harmonic_score']:.1f}")
            print(f"Avg Energy Jump:     {quality['avg_energy_jump']:.1f}")
            print(f"Avg BPM Jump:        {quality['avg_bpm_jump']:.1f}")

            # Show first few tracks in playlist
            print(f"\nPlaylist order (first 5):")
            for i, track in enumerate(playlist[:5], 1):
                print(f"  {i}. {track.fileName:<20} | {track.camelotCode} | {track.bpm:3.0f} BPM | E:{track.energy:2d}")

        except Exception as e:
            print(f"Error with {strategy_name}: {e}")

def demo_emotional_journey():
    """Demonstrate the emotional journey algorithm in detail."""
    print("\n=== Emotional Journey Algorithm Demonstration ===")

    tracks = create_demo_tracks()

    # Suppress quality output
    import io
    import contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        journey_playlist = generate_playlist(tracks, "Emotional Journey", 3.0)

    print(f"\nEmotional Journey Playlist ({len(journey_playlist)} tracks):")
    print("-" * 70)

    # Analyze phases
    total_tracks = len(journey_playlist)
    opening_end = max(1, total_tracks // 4)
    building_end = opening_end + max(1, int(total_tracks * 0.4))
    peak_end = building_end + max(1, int(total_tracks * 0.2))

    for i, track in enumerate(journey_playlist, 1):
        # Determine phase
        if i <= opening_end:
            phase = "OPENING"
        elif i <= building_end:
            phase = "BUILDING"
        elif i <= peak_end:
            phase = "PEAK"
        else:
            phase = "RESOLUTION"

        print(f"{i:2d}. {track.fileName:<20} | {track.camelotCode} | {track.bpm:3.0f} BPM | E:{track.energy:2d} | {phase}")

    # Energy progression analysis
    energies = [track.energy for track in journey_playlist]
    print(f"\nEnergy Progression: {' -> '.join(map(str, energies))}")

def demo_benchmarking():
    """Demonstrate the benchmarking functionality."""
    print("\n=== Benchmarking All Algorithms ===")

    tracks = create_demo_tracks()

    # Suppress quality output during benchmarking
    import io
    import contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        results = benchmark_algorithms(tracks, 3.0)

    # Sort algorithms by overall score
    sorted_results = sorted(results.items(), key=lambda x: x[1]['overall_score'], reverse=True)

    print(f"\nAlgorithm Rankings (by Overall Score):")
    print("=" * 80)
    print(f"{'Rank':<5}{'Algorithm':<25}{'Overall':<10}{'Harmonic':<10}{'Energy':<10}{'BPM':<10}")
    print("-" * 80)

    for rank, (algorithm, metrics) in enumerate(sorted_results, 1):
        print(f"{rank:<5}{algorithm:<25}{metrics['overall_score']:<10.3f}"
              f"{metrics['harmonic_flow']:<10.3f}{metrics['energy_consistency']:<10.3f}"
              f"{metrics['bpm_smoothness']:<10.3f}")

    # Find best algorithm for each metric
    print(f"\nBest Algorithm by Metric:")
    print("-" * 40)

    metrics_to_check = ['overall_score', 'harmonic_flow', 'energy_consistency', 'bpm_smoothness']

    for metric in metrics_to_check:
        best_algo = max(results.keys(), key=lambda k: results[k][metric])
        best_score = results[best_algo][metric]
        print(f"{metric.replace('_', ' ').title():<20}: {best_algo} ({best_score:.3f})")

def main():
    """Run all demonstrations."""
    print("HarmonicPlaylistGenerator Enhanced Algorithms Demo")
    print("=" * 60)
    print("\nThis demo showcases the enhanced playlist generation algorithms")
    print("with improved harmonic compatibility, energy management, and DJ-focused features.")

    demo_enhanced_compatibility()
    demo_algorithm_comparison()
    demo_emotional_journey()
    demo_benchmarking()

    print("\n" + "="*60)
    print("Demo completed! The enhanced algorithms provide:")
    print("• Advanced harmonic rules (Energy Boost/Drop, Plus Seven)")
    print("• Look-ahead optimization for better track sequencing")
    print("• Multi-dimensional compatibility scoring")
    print("• Emotional journey with phase-based arrangement")
    print("• Genre-aware transitions")
    print("• Comprehensive quality metrics")
    print("• Performance benchmarking tools")

if __name__ == "__main__":
    main()