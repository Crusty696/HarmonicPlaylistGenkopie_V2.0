# -*- coding: utf-8 -*-
"""
BPM-Accuracy Check: Vergleicht Dateinamen-BPM vs. Librosa-BPM vs. ID3-Tag-BPM.
Zeigt wo die Abweichungen herkommen.
"""

import sys
import io
import re
import os
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

FOLDER = r"D:\beatport_tracks_2025-08"
EXTS = {".mp3", ".aiff", ".aif", ".flac", ".wav", ".m4a", ".ogg"}


# ID3-Tags auslesen (ohne volle Analyse)
def get_id3_bpm(file_path: str):
    """Liest BPM direkt aus ID3-Tags (kein Librosa)."""
    try:
        import mutagen
        from mutagen import File as MutagenFile

        audio = MutagenFile(file_path, easy=True)
        if audio is None:
            return None
        # Verschiedene BPM-Tag-Felder probieren
        for key in ["bpm", "TBPM", "tempo"]:
            val = audio.get(key)
            if val:
                try:
                    return float(str(val[0]).strip())
                except (ValueError, IndexError):
                    pass
        # Fallback: mutagen ohne easy=True
        audio2 = MutagenFile(file_path)
        if audio2 is None:
            return None
        for key in ["TBPM", "bpm", "BPM"]:
            if key in audio2:
                try:
                    tag = audio2[key]
                    val = str(tag.text[0]) if hasattr(tag, "text") else str(tag)
                    return float(val.strip())
                except Exception:
                    pass
    except Exception as e:
        return None
    return None


def bpm_ok(detected: float, expected: float, tolerance: float = 3.0) -> bool:
    """True wenn BPM innerhalb Toleranz oder Halftime/Doubletime."""
    if abs(detected - expected) <= tolerance:
        return True
    if abs(detected - expected * 2) <= tolerance:
        return True
    if abs(detected * 2 - expected) <= tolerance:
        return True
    return False


tracks = sorted(
    [f for f in Path(FOLDER).iterdir() if f.suffix.lower() in EXTS],
    key=lambda x: x.name.lower(),
)

print(f"\nBPM-Accuracy Check: {len(tracks)} Tracks\n")
print(
    f"{'#':>3}  {'Datei-BPM':>9}  {'ID3-BPM':>7}  {'Analyse-BPM':>11}  Dateiname (kurz)"
)
print("=" * 90)

# Lade Analyse-BPMs aus Cache (wenn vorhanden) oder frische Analyse
from hpg_core.analysis import analyze_track

abweichungen = []

for i, t in enumerate(tracks, 1):
    name = t.name

    # BPM aus Dateiname
    bm = re.search(r"_(\d{2,3})__", name)
    fname_bpm = int(bm.group(1)) if bm else None

    # BPM aus ID3-Tags
    id3_bpm = get_id3_bpm(str(t))

    # BPM aus Analyse (Cache oder neu)
    tr = analyze_track(str(t))
    analysis_bpm = tr.bpm if tr else None

    # Kurzer Dateiname
    short = name[:50] if len(name) > 50 else name

    # Status
    fname_ok = bpm_ok(analysis_bpm, fname_bpm) if (fname_bpm and analysis_bpm) else None
    id3_ok = bpm_ok(analysis_bpm, id3_bpm) if (id3_bpm and analysis_bpm) else None

    fname_str = f"{fname_bpm:>4}" if fname_bpm else "  -?"
    id3_str = f"{id3_bpm:>6.1f}" if id3_bpm else "    -?"
    ana_str = f"{analysis_bpm:>8.1f}" if analysis_bpm else "      -?"

    flag = ""
    if fname_bpm and analysis_bpm:
        if not fname_ok:
            flag = " ← ABWEICHUNG"
            abweichungen.append((i, name, fname_bpm, id3_bpm, analysis_bpm))

    print(f"{i:>3}  {fname_str:>9}  {id3_str:>7}  {ana_str:>11}  {short}{flag}")

print("=" * 90)
print(f"\nBPM-Abweichungen (Dateiname vs. Analyse, nicht Halftime/Doubletime):")
print(f"  Abweichungen: {len(abweichungen)}/{len(tracks)}")

if abweichungen:
    print("\nDetails:")
    for i, name, fname_bpm, id3_bpm, analysis_bpm in abweichungen:
        print(f"  {i:>2}. {name[:60]}")
        print(
            f"      Datei: {fname_bpm} BPM | ID3: {id3_bpm} | Analyse: {analysis_bpm:.1f}"
        )

print("\n--- Fazit ---")
print("ID3-BPM = Beatport-Metadaten (korrekt)")
print("Datei-BPM = BPM im Dateinamen (korrekt, von Beatport)")
print("Analyse-BPM = was Librosa erkennt (kann falsch sein)")
print(
    "Abweichung = Librosa weicht von Datei/ID3-BPM ab (ausserhalb 3 BPM + Halftime/Doubletime)"
)
