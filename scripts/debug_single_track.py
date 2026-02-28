#!/usr/bin/env python3
"""
Debug-Skript: Analysiert einen einzelnen Track mit voller Debug-Ausgabe.

Verwendung:
    python scripts/debug_single_track.py "D:\\beatport_tracks_2025-08\\track.wav"
    python scripts/debug_single_track.py "D:\\beatport_tracks_2025-08\\track.wav" --profile
    python scripts/debug_single_track.py "D:\\beatport_tracks_2025-08\\track.wav" --no-cache

Zeigt:
- Alle Analyse-Schritte mit Timing
- BPM, Key, Genre, Struktur, Mix-Punkte
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


def main():
  parser = argparse.ArgumentParser(description="Debug: Einzelnen Track analysieren")
  parser.add_argument("file", help="Pfad zur Audio-Datei")
  parser.add_argument("--profile", action="store_true", help="Profiling aktivieren")
  parser.add_argument("--no-cache", action="store_true", help="Cache ignorieren")
  parser.add_argument("--level", default="DEBUG", help="Log-Level (DEBUG, INFO, WARNING)")
  args = parser.parse_args()

  # Logging mit vollem Debug-Level
  setup_logging(level=args.level, log_to_file=True, log_to_console=True)

  file_path = os.path.abspath(args.file)
  if not os.path.exists(file_path):
    print(f"FEHLER: Datei nicht gefunden: {file_path}")
    sys.exit(1)

  print(f"\n{'='*60}")
  print(f"DEBUG ANALYSE: {os.path.basename(file_path)}")
  print(f"{'='*60}\n")

  # Cache-Status pruefen
  cache_key = generate_cache_key(file_path)
  cached = get_cached_track(cache_key, file_path=file_path)
  if cached:
    print(f"  Cache-Status: HIT (Key: {cache_key[:40]}...)")
    if args.no_cache:
      print(f"  --no-cache aktiv: Cache wird ignoriert")
    else:
      print(f"\n--- Cached Track-Daten ---")
      _print_track(cached)
      return

  # Analyse mit optionalem Profiling
  with TimerContext("Gesamt-Analyse"):
    track = analyze_track(file_path)

  if track:
    print(f"\n--- Analyse-Ergebnis ---")
    _print_track(track)
  else:
    print(f"\nFEHLER: Analyse fehlgeschlagen!")


def _print_track(track):
  """Gibt alle Track-Felder formatiert aus."""
  key_str = f"{track.keyNote} {track.keyMode} ({track.camelotCode})" if track.keyNote else "N/A"
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
      label = s.get('label', '?') if isinstance(s, dict) else getattr(s, 'label', '?')
      fields.append((f"  Sektion {i+1}", label))

  max_label = max(len(f[0]) for f in fields)
  for label, value in fields:
    print(f"  {label:<{max_label+2}} {value}")


if __name__ == "__main__":
  main()
