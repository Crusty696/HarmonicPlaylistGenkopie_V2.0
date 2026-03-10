#!/usr/bin/env python3
"""
Debug-Skript: Analysiert einen einzelnen Track mit voller Debug-Ausgabe.
Optionaler zweiter Track zeigt paar-spezifische Mix-Points.

Verwendung:
    python scripts/debug_single_track.py "D:\\beatport_tracks_2025-08\\track.wav"
    python scripts/debug_single_track.py "D:\\beatport_tracks_2025-08\\a.wav" "D:\\beatport_tracks_2025-08\\b.wav"
    python scripts/debug_single_track.py "D:\\beatport_tracks_2025-08\\track.wav" --profile
    python scripts/debug_single_track.py "D:\\beatport_tracks_2025-08\\track.wav" --no-cache

Zeigt:
- Alle Analyse-Schritte mit Timing
- BPM, Key, Genre, Struktur, Mix-Punkte
- Paar-spezifische Mix-Points wenn zweiter Track angegeben
- Optionales Profiling der einzelnen Schritte
"""

import sys
import os
import argparse

# Projekt-Root zum Python-Path hinzufuegen
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hpg_core.logging_config import setup_logging
from hpg_core.analysis import analyze_track
from hpg_core.caching import generate_cache_key, get_cached_track
from hpg_core.profiling import AnalysisProfiler, TimerContext
from hpg_core.dj_brain import calculate_paired_mix_points, generate_dj_recommendation


def main():
    parser = argparse.ArgumentParser(description="Debug: Einzelnen Track analysieren")
    parser.add_argument("file", help="Pfad zur Audio-Datei (Track A)")
    parser.add_argument(
        "file_b",
        nargs="?",
        default=None,
        help="Optionaler Track B fuer paar-spezifische Mix-Points",
    )
    parser.add_argument("--profile", action="store_true", help="Profiling aktivieren")
    parser.add_argument("--no-cache", action="store_true", help="Cache ignorieren")
    parser.add_argument(
        "--level", default="DEBUG", help="Log-Level (DEBUG, INFO, WARNING)"
    )
    args = parser.parse_args()

    # Logging mit vollem Debug-Level
    setup_logging(level=args.level, log_to_file=True, log_to_console=True)

    file_path = os.path.abspath(args.file)
    if not os.path.exists(file_path):
        print(f"FEHLER: Datei nicht gefunden: {file_path}")
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"DEBUG ANALYSE: {os.path.basename(file_path)}")
    print(f"{'=' * 60}\n")

    # Track A laden (Cache oder frische Analyse)
    cache_key = generate_cache_key(file_path)
    cached = get_cached_track(cache_key, file_path=file_path)
    if cached and not args.no_cache:
        print(f"  Cache-Status: HIT (Key: {cache_key[:40]}...)")
        print(f"\n--- Cached Track-Daten ---")
        track_a = cached
        _print_track(cached)
    else:
        if cached and args.no_cache:
            print(f"  Cache-Status: HIT aber --no-cache aktiv: ignoriert")
        else:
            print(f"  Cache-Status: MISS")
        with TimerContext("Gesamt-Analyse"):
            track_a = analyze_track(file_path)
        if track_a:
            print(f"\n--- Analyse-Ergebnis ---")
            _print_track(track_a)
        else:
            print(f"\nFEHLER: Analyse fehlgeschlagen!")
            sys.exit(1)

    # Optionaler Track B fuer paar-spezifische Mix-Points
    if args.file_b and track_a:
        file_b_path = os.path.abspath(args.file_b)
        if not os.path.exists(file_b_path):
            print(f"\nFEHLER: Track B nicht gefunden: {file_b_path}")
            sys.exit(1)

        print(f"\n{'=' * 60}")
        print(f"TRACK B: {os.path.basename(file_b_path)}")
        print(f"{'=' * 60}\n")

        cache_key_b = generate_cache_key(file_b_path)
        cached_b = get_cached_track(cache_key_b, file_path=file_b_path)
        if cached_b and not args.no_cache:
            track_b = cached_b
            _print_track(cached_b)
        else:
            with TimerContext("Track-B-Analyse"):
                track_b = analyze_track(file_b_path)
            if track_b:
                _print_track(track_b)
            else:
                print(f"FEHLER: Track-B-Analyse fehlgeschlagen!")
                sys.exit(1)

        # Paar-spezifische Mix-Points berechnen
        print(f"\n{'=' * 60}")
        print(f"PAAR-SPEZIFISCHE MIX-POINTS (A -> B)")
        print(f"{'=' * 60}\n")

        adj_mix_out_a, adj_mix_in_b = calculate_paired_mix_points(track_a, track_b)
        overlap = (
            max(0.0, track_a.duration - adj_mix_out_a) if track_a.duration > 0 else 0.0
        )

        print(f"  Track A Mix-Out (adjusted):  {adj_mix_out_a:.2f}s")
        print(f"  Track B Mix-In  (adjusted):  {adj_mix_in_b:.2f}s")
        print(f"  Berechneter Overlap:         {overlap:.2f}s")
        print(f"  (per-track Mix-Out A:        {track_a.mix_out_point:.2f}s)")
        print(f"  (per-track Mix-In  B:        {track_b.mix_in_point:.2f}s)")

        # DJ-Empfehlung
        try:
            dj = generate_dj_recommendation(track_a, track_b)
            print(f"\n  --- DJ-Empfehlung ---")
            if dj.mix_technique:
                print(f"  Technik:      {dj.mix_technique}")
            if dj.eq_advice:
                print(f"  EQ:           {dj.eq_advice}")
            if dj.transition_bars > 0:
                print(f"  Bars:         {dj.transition_bars}")
            if dj.bpm_advice:
                print(f"  BPM:          {dj.bpm_advice}")
            if dj.key_advice:
                print(f"  Key:          {dj.key_advice}")
            if dj.energy_advice:
                print(f"  Energie:      {dj.energy_advice}")
            for risk in dj.risk_notes:
                print(f"  ! RISK:       {risk}")
        except Exception as e:
            print(f"  DJ-Empfehlung fehlgeschlagen: {e}")


def _print_track(track):
    """Gibt alle Track-Felder formatiert aus."""
    key_str = (
        f"{track.keyNote} {track.keyMode} ({track.camelotCode})"
        if track.keyNote
        else "N/A"
    )
    fields = [
        ("Datei", track.fileName),
        ("Kuenstler", track.artist),
        ("Titel", track.title),
        ("ID3 Genre", track.genre),
        ("BPM", f"{track.bpm:.2f}" if track.bpm else "N/A"),
        ("Key", key_str),
        ("Dauer", f"{track.duration:.1f}s" if track.duration else "N/A"),
        ("Energie", track.energy),
        ("Bass", track.bass_intensity),
        ("Brightness", track.brightness),
        ("Vocal", track.vocal_instrumental),
        ("Danceability", track.danceability),
        ("Mix-In", f"{track.mix_in_point:.1f}s (Bar {track.mix_in_bars})"),
        ("Mix-Out", f"{track.mix_out_point:.1f}s (Bar {track.mix_out_bars})"),
    ]

    # DJ Brain Felder
    if track.detected_genre and track.detected_genre != "Unknown":
        fields.append(("Detected Genre", track.detected_genre))
    if track.genre_confidence:
        fields.append(("Genre-Confidence", f"{track.genre_confidence:.2f}"))
    if track.genre_source:
        fields.append(("Genre-Source", track.genre_source))
    if track.sections:
        fields.append(("Sektionen", f"{len(track.sections)} Stueck"))
        for i, s in enumerate(track.sections):
            label = (
                s.get("label", "?") if isinstance(s, dict) else getattr(s, "label", "?")
            )
            fields.append((f"  Sektion {i + 1}", label))

    max_label = max(len(f[0]) for f in fields)
    for label, value in fields:
        print(f"  {label:<{max_label + 2}} {value}")


if __name__ == "__main__":
    main()
