# -*- coding: utf-8 -*-
"""DJ Test Agent - Report Script"""

import sys
import io

# UTF-8 Ausgabe erzwingen fuer Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

sys.path.insert(0, ".")
from hpg_core.analysis import analyze_track

OK = "[OK]"
WARN = "[!] "
ERR = "[X] "

TEST_TRACK = r"D:\beatport_tracks_2025-08\Antinomy_-_Imagination_(Kalki_remix)_143__(Psy-Trance)_G_Major_02_21.aiff"

print("=" * 60)
print("DJ TEST AGENT - EINZELTRACK REPORT")
print("=" * 60)

print("\n[1] Analysiere Track...")
track = analyze_track(TEST_TRACK)
if not track:
    print("  FEHLER: Track konnte nicht analysiert werden!")
    sys.exit(1)

print(f"  Titel   : {track.title or track.fileName}")
print(f"  Artist  : {track.artist or 'Unbekannt'}")
print(f"  BPM     : {track.bpm:.2f}")
print(f"  Key     : {track.keyNote} {track.keyMode} ({track.camelotCode})")
print(f"  Genre   : {track.genre}")
print(f"  Energy  : {track.energy:.1f}")
print(f"  Bass    : {track.bass_intensity:.1f}")
print(f"  Dauer   : {track.duration:.1f}s ({track.duration / 60:.1f} min)")

seconds_per_phrase = (60.0 / track.bpm) * 4 * 8
seconds_per_bar = (60.0 / track.bpm) * 4
# DJ Brain quantisiert Mix-Punkte auf 4-Bar-Grid (nicht 8-Bar-Phrase)
MIX_GRID_BARS = 4
seconds_per_grid = seconds_per_bar * MIX_GRID_BARS

print(f"\n[2] Phrasing-Analyse (BPM={track.bpm:.1f})")
print(f"  Sekunden/Bar    : {seconds_per_bar:.2f}s")
print(f"  Sekunden/Phrase : {seconds_per_phrase:.2f}s (8 Bars)")
print(f"  Mix-Grid        : {seconds_per_grid:.2f}s (4 Bars, DJ Brain-Raster)")

mix_in = track.mix_in_point
mix_out = track.mix_out_point
print(f"\n[3] Mix-Punkte")
print(f"  Mix-In  : {mix_in:.1f}s")
print(f"  Mix-Out : {mix_out:.1f}s")
print(f"  Overlap : {mix_out - mix_in:.1f}s Platz zum Mixen")

# Phrasing-Check gegen 4-Bar-Grid (reales DJ Brain-Raster)
bars_at_mix_in = mix_in / seconds_per_bar
grid_at_mix_in = mix_in / seconds_per_grid
grid_deviation = abs(grid_at_mix_in - round(grid_at_mix_in)) * seconds_per_grid
# Auch 8-Bar-Phrase-Alignment pruefen (ideal)
phrase_at_mix_in = mix_in / seconds_per_phrase
phrase_deviation = abs(phrase_at_mix_in - round(phrase_at_mix_in)) * seconds_per_phrase

bars_at_mix_out = mix_out / seconds_per_bar
outro_bars = (track.duration - mix_out) / seconds_per_bar

print(f"\n[4] Phrase-Alignment Check")
print(
    f"  Mix-In bei Bar  : {bars_at_mix_in:.1f} (4-Bar-Grid: {grid_at_mix_in:.2f}, 8-Bar-Phrase: {phrase_at_mix_in:.2f})"
)

# Bewertung: Primaer 4-Bar-Grid (DJ Brain-Standard), sekundaer 8-Bar-Phrase (Ideal)
status = OK if grid_deviation < 0.5 else (WARN if grid_deviation < 2.0 else ERR)
if grid_deviation < 0.5 and phrase_deviation < 0.5:
    label = "Exakt auf 8-Bar-Phrasegrenze (perfekt!)"
elif grid_deviation < 0.5:
    label = f"Auf 4-Bar-Grid (8-Bar-Abw. {phrase_deviation:.1f}s)"
elif grid_deviation < 2.0:
    label = f"Leichte Grid-Abweichung ({grid_deviation:.1f}s)"
else:
    label = f"NICHT auf Grid! ({grid_deviation:.1f}s)"
print(f"  4-Bar-Grid-Abw. : {grid_deviation:.1f}s  {status} {label}")

print(f"  Mix-Out bei Bar : {bars_at_mix_out:.1f}")
status = OK if outro_bars >= 8 else (WARN if outro_bars >= 4 else ERR)
label = (
    "Genug Outro"
    if outro_bars >= 8
    else ("Wenig Outro" if outro_bars >= 4 else "ZU WENIG Outro!")
)
print(f"  Outro-Platz     : {outro_bars:.1f} Bars  {status} {label}")

if bars_at_mix_in < 4:
    print(f"  Mix-In Timing  : {ERR} Zu frueh (< 4 Bars)")
elif bars_at_mix_in < 8:
    print(f"  Mix-In Timing  : {WARN} Kurz (< 8 Bars)")
else:
    print(f"  Mix-In Timing  : {OK} OK ({bars_at_mix_in:.0f} Bars Intro)")

# Sections
print(f"\n[5] Track-Struktur ({len(track.sections)} Sektionen)")
for s in track.sections:
    # Sections koennen dict oder TrackSection-Objekt sein
    if isinstance(s, dict):
        start = s.get("start_time", s.get("start", 0))
        end = s.get("end_time", s.get("end", 0))
        lbl = s.get("label", "?")
        energy = s.get("avg_energy", 0.0)
    else:
        start = s.start_time
        end = s.end_time
        lbl = s.label
        energy = s.avg_energy
    d = end - start
    print(
        f"  {lbl:12s} : {start:6.1f}s - {end:6.1f}s  ({d:.1f}s = {d / seconds_per_bar:.1f} Bars, Energy: {energy:.2f})"
    )

print("\n[6] Genre-Info")
# ID3-Tag hat Vorrang; falls leer/Unknown → detected_genre aus Audio-Analyse zeigen
detected_genre = getattr(track, "detected_genre", None)
display_genre = (
    track.genre
    if track.genre and track.genre != "Unknown"
    else (detected_genre or "Unknown")
)
print(
    f"  Genre     : {display_genre}  (ID3: {track.genre}, Audio: {detected_genre or 'n/a'})"
)
print(f"  Konfidenz : {getattr(track, 'genre_confidence', 'n/a')}")
print(f"  Quelle    : {getattr(track, 'genre_source', 'n/a')}")

print("\n" + "=" * 60)
print("FAZIT:")
issues = []
warnings = []
if grid_deviation >= 2.0:
    issues.append(f"Mix-In nicht auf 4-Bar-Grid ({grid_deviation:.1f}s Abweichung)")
if outro_bars < 4:
    issues.append(f"Zu wenig Outro ({outro_bars:.1f} Bars)")
elif outro_bars < 8:
    warnings.append(f"Wenig Outro ({outro_bars:.1f} Bars)")
if bars_at_mix_in < 4:
    issues.append(f"Mix-In zu frueh ({bars_at_mix_in:.0f} Bars)")
elif bars_at_mix_in < 8:
    warnings.append(f"Kurzes Intro ({bars_at_mix_in:.0f} Bars)")
if mix_out - mix_in < 30:
    issues.append(f"Enger Mix-Bereich ({mix_out - mix_in:.0f}s)")
if display_genre == "Unknown":
    warnings.append("Genre nicht erkannt")

if not issues and not warnings:
    print(f"  {OK} Track ist DJ-tauglich - alle Checks bestanden!")
else:
    if issues:
        print(f"  {ERR} {len(issues)} Problem(e):")
        for i in issues:
            print(f"     - {i}")
    if warnings:
        print(f"  {WARN} {len(warnings)} Warnung(en):")
        for w in warnings:
            print(f"     - {w}")
print("=" * 60)
