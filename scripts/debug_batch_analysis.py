#!/usr/bin/env python3
"""
Debug-Skript: Batch-Analyse mit Profiling und Zusammenfassung.

Verwendung:
    python scripts/debug_batch_analysis.py "D:\\beatport_tracks_2025-08" --limit 10
    python scripts/debug_batch_analysis.py "D:\\beatport_tracks_2025-08" --ext .wav .mp3

Zeigt:
- Gesamt-Timing und Durchschnitt pro Track
- Erfolgs/Fehler-Quote
- Genre-Verteilung
- BPM-Bereich
"""

import sys
import os
import glob
import argparse
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hpg_core.logging_config import setup_logging
from hpg_core.parallel_analyzer import ParallelAnalyzer, get_optimal_worker_count
from hpg_core.profiling import TimerContext, get_memory_usage_mb
from collections import Counter


AUDIO_EXTENSIONS = {'.wav', '.mp3', '.flac', '.aiff', '.ogg', '.m4a', '.aac'}


def main():
  parser = argparse.ArgumentParser(description="Debug: Batch-Analyse mit Profiling")
  parser.add_argument("directory", help="Ordner mit Audio-Dateien")
  parser.add_argument("--limit", type=int, default=0, help="Max. Anzahl Dateien (0=alle)")
  parser.add_argument("--ext", nargs="+", default=None, help="Dateiendungen (.wav .mp3)")
  parser.add_argument("--workers", type=int, default=0, help="Anzahl Workers (0=auto)")
  parser.add_argument("--level", default="INFO", help="Log-Level")
  args = parser.parse_args()

  setup_logging(level=args.level, log_to_file=True, log_to_console=True)

  # Dateien sammeln
  extensions = set(args.ext) if args.ext else AUDIO_EXTENSIONS
  files = []
  for f in os.listdir(args.directory):
    ext = os.path.splitext(f)[1].lower()
    if ext in extensions:
      files.append(os.path.join(args.directory, f))

  if args.limit > 0:
    files = files[:args.limit]

  if not files:
    print(f"Keine Audio-Dateien gefunden in: {args.directory}")
    sys.exit(1)

  workers = args.workers or get_optimal_worker_count(len(files))

  print(f"\n{'='*60}")
  print(f"BATCH DEBUG ANALYSE")
  print(f"  Dateien: {len(files)}")
  print(f"  Workers: {workers}")
  print(f"  Ordner:  {args.directory}")
  print(f"{'='*60}\n")

  # Speicher vorher
  mem_before = get_memory_usage_mb()

  # Analyse starten
  analyzer = ParallelAnalyzer(max_workers=workers)
  start = time.perf_counter()

  tracks = analyzer.analyze_files(files, progress_callback=_progress)

  elapsed = time.perf_counter() - start

  # Speicher nachher
  mem_after = get_memory_usage_mb()

  # Zusammenfassung
  print(f"\n{'='*60}")
  print(f"ERGEBNIS")
  print(f"{'='*60}")
  print(f"  Erfolgreich:  {len(tracks)}/{len(files)}")
  print(f"  Fehlgeschlagen: {len(files) - len(tracks)}")
  print(f"  Gesamt-Zeit:  {elapsed:.1f}s")
  if tracks:
    print(f"  Pro Track:    {elapsed/len(files)*1000:.0f}ms")

  if mem_before and mem_after:
    print(f"  Speicher:     {mem_before:.0f}MB -> {mem_after:.0f}MB ({mem_after-mem_before:+.0f}MB)")

  if tracks:
    # Genre-Verteilung
    genres = Counter(t.detected_genre or t.genre or "Unknown" for t in tracks)
    print(f"\n  Genre-Verteilung:")
    for genre, count in genres.most_common():
      print(f"    {genre:25s} {count:3d} ({count/len(tracks)*100:.0f}%)")

    # BPM-Bereich
    bpms = [t.bpm for t in tracks if t.bpm and t.bpm > 0]
    if bpms:
      print(f"\n  BPM: {min(bpms):.0f} - {max(bpms):.0f} (Mittel: {sum(bpms)/len(bpms):.0f})")


def _progress(current, total, msg):
  """Fortschritts-Callback."""
  pct = current / total * 100 if total > 0 else 0
  print(f"  [{current:3d}/{total}] ({pct:5.1f}%) {msg}")


if __name__ == "__main__":
  main()
