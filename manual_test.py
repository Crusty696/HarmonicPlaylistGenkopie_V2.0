# -*- coding: utf-8 -*-
"""
HPG Manueller Test - Interaktiver DJ-Report
Analysiert beliebige Tracks aus dem beatport-Ordner.

Aufruf:
  python manual_test.py                          # Zeigt Track-Liste + Eingabe
  python manual_test.py <pfad>                   # Analysiert direkt einen Pfad
  python manual_test.py --folder <ordner>        # Anderer Ordner
"""

import sys
import io
import os
import argparse
from pathlib import Path

# UTF-8 Ausgabe fuer Windows erzwingen
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from hpg_core.analysis import analyze_track

# ── Konfiguration ────────────────────────────────────────────────────────────
DEFAULT_FOLDER = r"D:\beatport_tracks_2025-08"
AUDIO_EXTENSIONS = {".mp3", ".aiff", ".aif", ".flac", ".wav", ".m4a", ".ogg"}

OK = "[OK] "
WARN = "[!]  "
ERR = "[X]  "
SEP = "=" * 65


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────


def list_tracks(folder: str) -> list[Path]:
    """Gibt sortierte Liste aller Audio-Dateien im Ordner zurueck."""
    p = Path(folder)
    if not p.exists():
        print(f"{ERR}Ordner nicht gefunden: {folder}")
        return []
    tracks = sorted(
        [f for f in p.iterdir() if f.suffix.lower() in AUDIO_EXTENSIONS],
        key=lambda x: x.name.lower(),
    )
    return tracks


def print_track_list(tracks: list[Path]) -> None:
    """Gibt nummerierte Track-Liste aus."""
    print(f"\n{SEP}")
    print(f"  VERFUEGBARE TRACKS ({len(tracks)} Dateien)")
    print(SEP)
    for i, t in enumerate(tracks, 1):
        print(f"  {i:3d}. {t.name}")
    print(SEP)


def dj_report(track_path: str) -> None:
    """Analysiert einen Track und gibt den vollstaendigen DJ-Report aus."""
    print(f"\n{SEP}")
    print("  DJ TEST AGENT - TRACK REPORT")
    print(SEP)
    print(f"  Datei: {Path(track_path).name}")
    print(f"{SEP}\n")

    print("[1] Analysiere Track...")
    track = analyze_track(track_path)
    if not track:
        print(f"  {ERR}Track konnte nicht analysiert werden!")
        return

    # Basis-Info
    print(f"  Titel   : {track.title or track.fileName}")
    print(f"  Artist  : {track.artist or 'Unbekannt'}")
    print(f"  BPM     : {track.bpm:.2f}")
    print(f"  Key     : {track.keyNote} {track.keyMode} ({track.camelotCode})")
    print(f"  Genre   : {track.genre}")
    print(f"  Energy  : {track.energy:.1f}")
    print(f"  Bass    : {track.bass_intensity:.1f}")
    print(f"  Dauer   : {track.duration:.1f}s ({track.duration / 60:.1f} min)")

    # Phrasing-Grundlagen
    seconds_per_bar = (60.0 / track.bpm) * 4
    seconds_per_phrase = seconds_per_bar * 8
    MIX_GRID_BARS = 4
    seconds_per_grid = seconds_per_bar * MIX_GRID_BARS

    print(f"\n[2] Phrasing-Analyse (BPM={track.bpm:.1f})")
    print(f"  Sekunden/Bar    : {seconds_per_bar:.2f}s")
    print(f"  Sekunden/Phrase : {seconds_per_phrase:.2f}s (8 Bars)")
    print(f"  Mix-Grid        : {seconds_per_grid:.2f}s (4 Bars, DJ Brain-Raster)")

    # Mix-Punkte
    mix_in = track.mix_in_point
    mix_out = track.mix_out_point
    print(f"\n[3] Mix-Punkte")
    print(f"  Mix-In  : {mix_in:.1f}s  ({mix_in / seconds_per_bar:.1f} Bars)")
    print(f"  Mix-Out : {mix_out:.1f}s  ({mix_out / seconds_per_bar:.1f} Bars)")
    print(f"  Overlap : {mix_out - mix_in:.1f}s Platz zum Mixen")

    # Alignment-Checks
    bars_at_mix_in = mix_in / seconds_per_bar
    bars_at_mix_out = mix_out / seconds_per_bar
    outro_bars = (track.duration - mix_out) / seconds_per_bar

    grid_at_mix_in = mix_in / seconds_per_grid
    grid_deviation = abs(grid_at_mix_in - round(grid_at_mix_in)) * seconds_per_grid

    phrase_at_mix_in = mix_in / seconds_per_phrase
    phrase_deviation = (
        abs(phrase_at_mix_in - round(phrase_at_mix_in)) * seconds_per_phrase
    )

    print(f"\n[4] Phrase-Alignment Check")
    print(
        f"  Mix-In bei Bar  : {bars_at_mix_in:.1f}  "
        f"(4-Bar-Grid: {grid_at_mix_in:.2f}, 8-Bar-Phrase: {phrase_at_mix_in:.2f})"
    )

    # 4-Bar-Grid Bewertung
    grid_status = (
        OK if grid_deviation < 0.5 else (WARN if grid_deviation < 2.0 else ERR)
    )
    if grid_deviation < 0.5 and phrase_deviation < 0.5:
        grid_label = "Exakt auf 8-Bar-Phrasegrenze (perfekt!)"
    elif grid_deviation < 0.5:
        grid_label = f"Auf 4-Bar-Grid  (8-Bar-Abw. {phrase_deviation:.1f}s)"
    elif grid_deviation < 2.0:
        grid_label = f"Leichte Grid-Abweichung ({grid_deviation:.1f}s)"
    else:
        grid_label = f"NICHT auf Grid! ({grid_deviation:.1f}s)"
    print(f"  4-Bar-Grid-Abw. : {grid_deviation:.1f}s  {grid_status}{grid_label}")

    # Outro
    print(f"  Mix-Out bei Bar : {bars_at_mix_out:.1f}")
    outro_status = OK if outro_bars >= 8 else (WARN if outro_bars >= 4 else ERR)
    outro_label = (
        "Genug Outro"
        if outro_bars >= 8
        else ("Wenig Outro" if outro_bars >= 4 else "ZU WENIG Outro!")
    )
    print(f"  Outro-Platz     : {outro_bars:.1f} Bars  {outro_status}{outro_label}")

    # Mix-In Timing
    if bars_at_mix_in < 4:
        print(f"  Mix-In Timing   : {ERR}Zu frueh (< 4 Bars)")
    elif bars_at_mix_in < 8:
        print(f"  Mix-In Timing   : {WARN}Kurz (< 8 Bars)")
    else:
        print(f"  Mix-In Timing   : {OK}OK ({bars_at_mix_in:.0f} Bars Intro)")

    # Track-Struktur
    print(f"\n[5] Track-Struktur ({len(track.sections)} Sektionen)")
    for s in track.sections:
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
            f"  {lbl:12s} : {start:6.1f}s - {end:6.1f}s  "
            f"({d:.1f}s = {d / seconds_per_bar:.1f} Bars, Energy: {energy:.2f})"
        )

    # Genre-Info
    detected_genre = getattr(track, "detected_genre", None)
    display_genre = (
        track.genre
        if track.genre and track.genre != "Unknown"
        else (detected_genre or "Unknown")
    )
    print(f"\n[6] Genre-Info")
    print(
        f"  Genre     : {display_genre}  (ID3: {track.genre}, Audio: {detected_genre or 'n/a'})"
    )
    print(f"  Konfidenz : {getattr(track, 'genre_confidence', 'n/a')}")
    print(f"  Quelle    : {getattr(track, 'genre_source', 'n/a')}")

    # Fazit
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

    print(f"\n{SEP}")
    print("FAZIT:")
    if not issues and not warnings:
        print(f"  {OK}Track ist DJ-tauglich - alle Checks bestanden!")
    else:
        if issues:
            print(f"  {ERR}{len(issues)} Problem(e):")
            for i in issues:
                print(f"       - {i}")
        if warnings:
            print(f"  {WARN}{len(warnings)} Warnung(en):")
            for w in warnings:
                print(f"       - {w}")
    print(SEP)


# ── Hauptprogramm ────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="HPG Manueller DJ-Test",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "track",
        nargs="?",
        help="Direkter Track-Pfad zum Analysieren (optional)",
    )
    parser.add_argument(
        "--folder",
        "-f",
        default=DEFAULT_FOLDER,
        help=f"Track-Ordner (Standard: {DEFAULT_FOLDER})",
    )
    args = parser.parse_args()

    # Modus 1: Direkter Pfad als Argument
    if args.track:
        if not os.path.exists(args.track):
            print(f"{ERR}Datei nicht gefunden: {args.track}")
            sys.exit(1)
        dj_report(args.track)
        return

    # Modus 2: Interaktive Auswahl
    tracks = list_tracks(args.folder)
    if not tracks:
        sys.exit(1)

    print_track_list(tracks)

    while True:
        try:
            print("\nNummer eingeben (oder 'q' zum Beenden, 'l' fuer Liste):")
            raw = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBeendet.")
            break

        if raw.lower() in ("q", "quit", "exit"):
            print("Beendet.")
            break

        if raw.lower() in ("l", "list", "liste"):
            print_track_list(tracks)
            continue

        try:
            idx = int(raw)
            if 1 <= idx <= len(tracks):
                dj_report(str(tracks[idx - 1]))
            else:
                print(f"  {WARN}Ungueltige Nummer. Bitte 1-{len(tracks)} eingeben.")
        except ValueError:
            print(f"  {WARN}Bitte eine Zahl eingeben.")


if __name__ == "__main__":
    main()
