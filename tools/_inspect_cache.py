"""Zeigt alle gecachten Track-Einträge mit BPM/Genre."""

import sys, io, shelve

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import os; from pathlib import Path; sys.path.insert(0, str(Path(__file__).parent.parent))

CACHE_FILE = os.path.join(str(Path(__file__).parent.parent), 'hpg_cache_v10.dbm')

with shelve.open(CACHE_FILE) as db:
    print(f"Cache-Einträge gesamt: {len(db)}\n")
    print(f"{'BPM':>7}  {'Genre-Audio':<22}  {'Key':<14}  Dateiname")
    print("-" * 90)
    for key, val in db.items():
        if key == "cache_version":
            continue
        bpm = getattr(val, "bpm", "?")
        genre = getattr(val, "detected_genre", None) or getattr(val, "genre", "?")
        key_note = getattr(val, "keyNote", "?")
        key_mode = getattr(val, "keyMode", "?")
        fname = getattr(val, "fileName", key[:50])
        print(f"{bpm:>7}  {genre:<22}  {key_note} {key_mode:<10}  {fname[:55]}")
