# -*- coding: utf-8 -*-
"""
Batch-Analyse aller Tracks: vergleicht erkanntes Genre mit dem Genre im Dateinamen.
Optimiert für Beatport-Dateiformate (z.B. (Psy-Trance) oder (Melodic House & Techno)).
"""

import sys
import io
import re
import argparse
from pathlib import Path

# UTF-8 Ausgabe erzwingen
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent))

from hpg_core.analysis import analyze_track

DEFAULT_FOLDER = r"D:\beatport_tracks_2025-08"
EXTS = {".mp3", ".aiff", ".aif", ".flac", ".wav", ".m4a", ".ogg"}

# Genre-Aliases: Was im Dateinamen steht -> was der Classifier kennt
GENRE_ALIASES = {
    "Psytrance": ["Psytrance", "Psy-Trance", "Psy Trance", "Psy"],
    "Melodic Techno": ["Melodic Techno", "Melodic House & Techno", "Melodic House", "Melodic_House_&_Techno"],
    "Techno": ["Techno"],
    "Trance": ["Trance"],
    "House": ["House"],
    "Drum & Bass": ["DnB", "Drum & Bass", "Drum and Bass"],
    "Progressive": ["Progressive", "Progressive House"],
}

def extract_genre_from_filename(name):
    """Versucht das Genre aus dem Dateinamen zu extrahieren (z.B. in Klammern)."""
    # 1. Bekannte Genres direkt im Namen suchen (als Ganzes Wort)
    for canonical, aliases in GENRE_ALIASES.items():
        for alias in aliases:
            # Suche alias als Wort, z.B. (Psy-Trance) oder _Psy-Trance_
            pattern = re.compile(rf"[\(_]{re.escape(alias)}[\)_]", re.IGNORECASE)
            if pattern.search(name):
                return alias
    
    # 2. Versuche Beatport Style: __(Genre)__
    m = re.search(r"__\(([^)]+)\)__", name)
    if m: return m.group(1)
    
    # 3. Versuche einfache Klammern: (Genre), aber filtere Mix/Remix aus
    all_brackets = re.findall(r"\(([^)]+)\)", name)
    for g in all_brackets:
        if not any(x in g.lower() for x in ["mix", "remix", "edit", "original", "rework"]):
            return g
            
    return "?"

def genre_match(fname_genre, detected):
    """Prüft ob detected_genre zum Dateinamen-Genre passt."""
    if not detected or detected == "n/a" or fname_genre == "?":
        return False
        
    d = detected.lower()
    f = fname_genre.lower().replace("_", " ").replace("-", " ")
    
    # Check Aliases
    for canonical, aliases in GENRE_ALIASES.items():
        if detected == canonical:
            for alias in aliases:
                a_clean = alias.lower().replace("-", " ")
                if a_clean in f or f in a_clean:
                    return True
                    
    # Direkte Übereinstimmung
    if d in f or f in d:
        return True
        
    # Psytrance Sonderfälle
    if "psy" in f and "psy" in d: return True
    
    return False

# Argument Parsing
parser = argparse.ArgumentParser()
parser.add_argument("--folder", default=DEFAULT_FOLDER)
parser.add_argument("--limit", type=int, default=None)
args = parser.parse_args()

tracks = sorted(
    [f for f in Path(args.folder).iterdir() if f.suffix.lower() in EXTS],
    key=lambda x: x.name.lower(),
)

if args.limit:
    tracks = tracks[:args.limit]

print(f"\nBatch-Genre-Check: {len(tracks)} Tracks\n")
print(f"{'#':>3}  {'BPM':>6}  {'Key':<14}  {'Datei-Genre':<25}  {'Erkannt':<22}  {'Conf':>5}  Status")
print("=" * 110)

falsch = []
unbekannt = []

for i, t in enumerate(tracks, 1):
    name = t.name
    fname_genre = extract_genre_from_filename(name)

    # BPM aus Dateiname extrahieren (z.B. _140__)
    bm = re.search(r"_(\d{2,3})__", name)
    if not bm: # Fallback: suche Zahl vor dem Genre
        bm = re.search(r"(\d{2,3})_", name)
    fname_bpm = int(bm.group(1)) if bm else None

    try:
        tr = analyze_track(str(t))
    except Exception as e:
        print(f"{i:>3}  {'ERROR':>6}  {'---':<14}  {fname_genre:<25}  {'ERROR':<22}  {'---':>5}  {str(e)[:20]}")
        continue
        
    if not tr:
        print(f"{i:>3}  {'FAIL':>6}  {'---':<14}  {fname_genre:<25}  {'---':<22}  {'---':>5}  FAILED")
        continue

    audio_genre = getattr(tr, 'detected_genre', 'Unknown') or "Unknown"
    conf = getattr(tr, 'genre_confidence', 0) or 0

    # Genre-Check
    ok = genre_match(fname_genre, audio_genre)
    
    if ok:
        status = "[OK] "
    elif fname_genre == "?":
        status = "[?]  "
        unbekannt.append((i, name, fname_genre, audio_genre))
    else:
        status = "[X]  "
        falsch.append((i, name, fname_genre, audio_genre, tr.bpm))

    print(f"{i:>3}  {tr.bpm:>6.1f}  {tr.keyNote} {tr.keyMode:<10}  {fname_genre:<25}  {audio_genre:<22}  {conf:>5.2f}  {status}")

print("=" * 110)
print(f"\nERGEBNIS:")
print(f"  Richtig erkannt : {len(tracks) - len(falsch) - len(unbekannt)}/{len(tracks)}")
print(f"  Falsch erkannt  : {len(falsch)}")
print(f"  Unbekannt/n/a   : {len(unbekannt)}")

if falsch:
    print(f"\n[X] FALSCH ERKANNTE TRACKS (Audio passt nicht zu Dateiname):")
    for entry in falsch:
        i, name, fg, ag, bpm = entry
        print(f"  {i:>2}. {name[:55]}")
        print(f"      Datei: {fg}  ->  Erkannt: {ag}  (BPM: {bpm:.1f})")
