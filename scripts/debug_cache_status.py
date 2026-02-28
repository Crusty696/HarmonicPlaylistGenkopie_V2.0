#!/usr/bin/env python3
"""
Debug-Skript: Cache-Status und Statistiken anzeigen.

Verwendung:
    python scripts/debug_cache_status.py
    python scripts/debug_cache_status.py --clear
    python scripts/debug_cache_status.py --details

Zeigt:
- Cache-Version und Groesse
- Anzahl gespeicherter Tracks
- Optionales Leeren des Caches
"""

import sys
import os
import shelve

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hpg_core.caching import CACHE_FILE, CACHE_VERSION, LOCK_FILE, file_lock
import argparse


def main():
  parser = argparse.ArgumentParser(description="Cache-Status und Verwaltung")
  parser.add_argument("--clear", action="store_true", help="Cache leeren")
  parser.add_argument("--details", action="store_true", help="Alle Keys anzeigen")
  args = parser.parse_args()

  print(f"\n{'='*60}")
  print(f"HPG CACHE STATUS")
  print(f"{'='*60}")
  print(f"  Cache-Datei: {os.path.abspath(CACHE_FILE)}")
  print(f"  Erwartete Version: {CACHE_VERSION}")

  # Pruefe ob Cache existiert
  cache_exists = False
  for ext in ['', '.db', '.dir', '.dat', '.bak']:
    if os.path.exists(CACHE_FILE + ext):
      cache_exists = True
      size = os.path.getsize(CACHE_FILE + ext)
      print(f"  Datei: {CACHE_FILE + ext} ({size / 1024:.1f} KB)")

  if not cache_exists:
    print(f"\n  Cache existiert nicht (noch keine Analyse durchgefuehrt)")
    return

  try:
    with file_lock(LOCK_FILE, timeout=5.0):
      with shelve.open(CACHE_FILE) as db:
        version = db.get('cache_version', 'UNBEKANNT')
        keys = [k for k in db.keys() if k != 'cache_version']

        print(f"\n  Version: {version}")
        print(f"  Eintraege: {len(keys)}")

        if version != CACHE_VERSION:
          print(f"  WARNUNG: Version stimmt nicht ueberein! (erwartet: {CACHE_VERSION})")

        if args.details and keys:
          print(f"\n  --- Gespeicherte Tracks ---")
          for i, key in enumerate(sorted(keys)[:50]):
            track = db.get(key)
            if track:
              name = getattr(track, 'fileName', '?')
              bpm = getattr(track, 'bpm', 0)
              genre = getattr(track, 'detected_genre', None) or getattr(track, 'genre', '?')
              print(f"  {i+1:3d}. {name:40s} BPM={bpm:6.1f} Genre={genre}")
          if len(keys) > 50:
            print(f"  ... und {len(keys) - 50} weitere")

        if args.clear:
          print(f"\n  Cache wird geleert...")
          db.clear()
          db['cache_version'] = CACHE_VERSION
          print(f"  OK: Cache geleert und neu initialisiert")

  except TimeoutError:
    print(f"\n  FEHLER: Konnte Lock nicht erhalten (anderer Prozess laeuft?)")
  except Exception as e:
    print(f"\n  FEHLER: {e}")


if __name__ == "__main__":
  main()
