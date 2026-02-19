# -*- coding: utf-8 -*-
"""
Batch-Analyse aller Tracks: vergleicht erkanntes Genre mit dem Genre im Dateinamen.
"""

import sys
import io
import re
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from hpg_core.analysis import analyze_track

FOLDER = r"D:\beatport_tracks_2025-08"
EXTS = {".mp3", ".aiff", ".aif", ".flac", ".wav", ".m4a", ".ogg"}

# Genre-Aliases: Was im Dateinamen steht → was der Classifier kennt
GENRE_ALIASES = {
    "Psy-Trance": ["Psytrance", "Psy-Trance", "Psy Trance"],
    "Melodic_House_&_Techno": [
        "Melodic Techno",
        "Melodic House & Techno",
        "Melodic House",
    ],
    "Techno": ["Techno"],
    "Trance": ["Trance", "Psytrance", "Psy-Trance"],
    "House": ["House"],
    "DnB": ["Drum & Bass"],
    "Progressive": ["Progressive"],
}


def genre_match(fname_genre: str, detected: str) -> bool:
    """Prüft ob detected_genre zum Dateinamen-Genre passt."""
    if not detected or detected == "n/a":
        return False
    d = detected.lower()
    f = fname_genre.lower()
    # Direkte Übereinstimmung
    if d in f or f in d:
        return True
    # Psytrance Sonderfälle
    if "psy" in f and "psy" in d:
        return True
    if "psy" in f and d in ["psytrance", "full on"]:
        return True
    # Melodic House & Techno
    if "melodic" in f and "melodic" in d:
        return True
    return False


tracks = sorted(
    [f for f in Path(FOLDER).iterdir() if f.suffix.lower() in EXTS],
    key=lambda x: x.name.lower(),
)

print(f"\nBatch-Genre-Check: {len(tracks)} Tracks\n")
print(
    f"{'#':>3}  {'BPM':>6}  {'Key':<14}  {'Datei-Genre':<25}  {'Erkannt':<22}  {'Conf':>5}  Status"
)
print("=" * 110)

falsch = []
unbekannt = []

for i, t in enumerate(tracks, 1):
    name = t.name
    # Genre aus Dateiname extrahieren (zwischen __ ... __ )
    m = re.search(r"__\(([^)]+)\)__", name)
    fname_genre = m.group(1) if m else "?"

    # BPM aus Dateiname extrahieren
    bm = re.search(r"_(\d{2,3})__", name)
    fname_bpm = int(bm.group(1)) if bm else None

    tr = analyze_track(str(t))
    if not tr:
        print(
            f"{i:>3}  {'ERROR':>6}  {'---':<14}  {fname_genre:<25}  {'---':<22}  {'---':>5}  FEHLER"
        )
        continue

    audio_genre = getattr(tr, "detected_genre", None) or "n/a"
    conf = getattr(tr, "genre_confidence", 0) or 0

    # BPM-Check
    bpm_flag = ""
    if fname_bpm:
        # Halftime/Doubletime berücksichtigen
        if (
            abs(tr.bpm - fname_bpm) > 3
            and abs(tr.bpm - fname_bpm * 2) > 3
            and abs(tr.bpm * 2 - fname_bpm) > 3
        ):
            bpm_flag = f" BPM:{fname_bpm}!={tr.bpm:.0f}"

    # Genre-Check
    ok = genre_match(fname_genre, audio_genre)
    if ok:
        status = "[OK] "
    elif audio_genre == "n/a":
        status = "[?]  "
        unbekannt.append((i, name, fname_genre, audio_genre))
    else:
        status = "[X]  "
        falsch.append((i, name, fname_genre, audio_genre, tr.bpm, bpm_flag))

    # Nur Zeilen mit Problemen oder Warnungen hervorheben
    suffix = bpm_flag if bpm_flag else ""
    print(
        f"{i:>3}  {tr.bpm:>6.1f}  {tr.keyNote} {tr.keyMode:<10}  "
        f"{fname_genre:<25}  {audio_genre:<22}  {conf:>5.2f}  {status}{suffix}"
    )

print("=" * 110)
print(f"\nERGEBNIS:")
print(f"  Richtig erkannt : {len(tracks) - len(falsch) - len(unbekannt)}/{len(tracks)}")
print(f"  Falsch erkannt  : {len(falsch)}")
print(f"  Unbekannt/n/a   : {len(unbekannt)}")

if falsch:
    print(f"\n[X] FALSCH ERKANNTE TRACKS:")
    for entry in falsch:
        i, name, fg, ag, bpm, bpm_flag = entry
        print(f"  {i:>2}. {name[:55]}")
        print(f"      Datei: {fg}  →  Erkannt: {ag}  (BPM: {bpm:.1f}{bpm_flag})")

if unbekannt:
    print(f"\n[?] NICHT ERKANNTE TRACKS (Genre=n/a):")
    for entry in unbekannt:
        i, name, fg, ag = entry
        print(f"  {i:>2}. {name[:55]}  (Datei: {fg})")
