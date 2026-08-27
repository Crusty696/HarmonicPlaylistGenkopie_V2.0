# End-to-End-Check (2026-07-26): echte Analyse -> Playlist -> Empfehlungen ->
# Render, mit Invarianten-Pruefung. Laeuft auf dem Zielrechner mit venv312.
# Aufruf: venv312\Scripts\python.exe e2e_check.py
import argparse
import glob
import os
import sys
import tempfile

os.environ.setdefault("PYTHONUTF8", "1")
# Nur der direkt gestartete E2E-Prozess darf die Umgebung umbiegen. Ein Import
# (insbesondere durch pytest) muss den bereits gebundenen Testcache unveraendert
# lassen. Die Aktivierung steht vor allen hpg_core-Imports.
_E2E_CACHE_DIR = None
if __name__ == "__main__":
    _E2E_CACHE_DIR = tempfile.TemporaryDirectory(prefix="hpg-e2e-")
    os.environ["HPG_CACHE_FILE"] = os.path.join(_E2E_CACHE_DIR.name, "cache.db")

from hpg_core.analysis import analyze_track
from hpg_core.config import PAAR_BPM_MAX
from hpg_core.models import METER
from hpg_core.playlist import (
    calculate_enhanced_compatibility,
    generate_playlist,
    compute_transition_recommendations,
    resolve_scoring_context,
)
from hpg_core.transition_renderer import TransitionClipSpec, render_transition_clip
from hpg_core.rekordbox_importer import RekordboxImporter

PASS, FAIL, INFO = [], [], []
E2E_BPM_TOLERANCE = PAAR_BPM_MAX


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(f"{name}: {detail}")


def positive_int(value: str) -> int:
    result = int(value)
    if result < 2:
        raise argparse.ArgumentTypeError("muss mindestens 2 sein")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="HPG-E2E-Check mit echtem Audio und lokalem Paarvertrag."
    )
    parser.add_argument(
        "--audio-dir",
        default=os.environ.get("HPG_TEST_AUDIO_DIR", r"D:\beatport_tracks_2025-08"),
        help="Ordner mit echten Audio-Fixtures",
    )
    parser.add_argument(
        "--audio-file",
        action="append",
        default=[],
        help=(
            "Explizite Original-Audiodatei; mindestens zweimal verwendbar. "
            "Umgeht die automatische Fixture-Suche."
        ),
    )
    parser.add_argument(
        "--max-fixtures",
        type=positive_int,
        default=12,
        help="Maximal sequenziell zu analysierende Fixtures (Standard: 12)",
    )
    parser.add_argument(
        "--with-rekordbox",
        action="store_true",
        help="Optional auch die lokale Rekordbox-Installation abfragen",
    )
    return parser


def find_first_local_pair(tracks, bpm_tolerance, scoring_context):
    """Liefert das erste gerichtete Paar mit vollwertigem lokalem Kandidaten."""
    for index_b, track_b in enumerate(tracks):
        for track_a in tracks[:index_b]:
            for source, target in ((track_a, track_b), (track_b, track_a)):
                metrics = calculate_enhanced_compatibility(
                    source,
                    target,
                    bpm_tolerance,
                    **scoring_context,
                )
                if metrics.kandidat is not None:
                    return [source, target]
    return None


def has_local_edge(tracks, bpm_tolerance, scoring_context) -> bool:
    if len(tracks) < 2:
        return False
    metrics = calculate_enhanced_compatibility(
        tracks[0], tracks[1], bpm_tolerance, **scoring_context
    )
    return metrics.kandidat is not None


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    PASS.clear()
    FAIL.clear()
    INFO.clear()
    # --- Audio-Fixtures finden (Tests/Validation) ---
    if args.audio_file:
        candidates = []
        seen = set()
        for candidate in args.audio_file:
            identity = os.path.normcase(os.path.abspath(candidate))
            if identity not in seen:
                seen.add(identity)
                candidates.append(candidate)
        candidates = candidates[:args.max_fixtures]
    else:
        candidates = []
        for pattern in (
            "tests/**/*.aiff",
            "tests/**/*.aif",
            "tests/**/*.wav",
            "tests/**/*.mp3",
            "validation/**/*.aiff",
            "validation/**/*.aif",
            "validation/**/*.wav",
            os.path.join(args.audio_dir, "*.aiff"),
            os.path.join(args.audio_dir, "*.aif"),
            os.path.join(args.audio_dir, "*.wav"),
            os.path.join(args.audio_dir, "*.mp3"),
        ):
            candidates.extend(glob.glob(pattern, recursive=True))
        candidates = sorted(set(candidates))
    grosse_candidates = []
    for candidate in candidates:
        try:
            if os.path.getsize(candidate) > 500_000:
                grosse_candidates.append(candidate)
        except OSError as exc:
            print(
                "E2E FEHLER: Audio-Fixture kann nicht gelesen werden: "
                f"{candidate}: {exc}"
            )
            return 1
    candidates = grosse_candidates[:args.max_fixtures]
    if len(candidates) < 2:
        print("E2E FEHLER: mindestens 2 Audio-Fixtures erforderlich")
        return 2

    print(f"Fixtures: {[os.path.basename(c) for c in candidates]}")

    # --- 1) Echte Analyse + A1-Invarianten ---
    tracks = []
    selected_pair = None
    ctx = resolve_scoring_context("Harmonic Flow", {})
    for path in candidates:
        try:
            t = analyze_track(path)
        except Exception as exc:
            check(f"Analyse {os.path.basename(path)[:40]}", False, str(exc))
            continue
        check(f"Analyse {os.path.basename(path)[:40]}", t is not None and t.duration > 0,
              f"dur={getattr(t, 'duration', 0):.0f}s bpm={getattr(t, 'bpm', 0):.1f}")
        if t is None:
            continue
        tracks.append(t)
        INFO.append(
            f"  {os.path.basename(path)[:44]}: downbeat={t.first_downbeat:.3f} "
            f"(conf {t.downbeat_confidence:.2f}) phrase={t.first_phrase:.3f} "
            f"(conf {t.phrase_confidence:.2f}) anchor={t.phrase_anchor:.3f} "
            f"mix=[{t.mix_in_point:.1f}, {t.mix_out_point:.1f}] phrase_unit={t.phrase_unit}"
        )
        # A1-Invariante: Mix-Punkte liegen auf dem Phrasen-Gitter des Ankers
        if t.bpm > 0 and t.phrase_unit > 0 and t.mix_out_point > t.mix_in_point > 0:
            grid = (60.0 / t.bpm) * METER * t.phrase_unit
            anchor = t.phrase_anchor
            for label, v in (("mix_in", t.mix_in_point), ("mix_out", t.mix_out_point)):
                ph = (v - anchor) % grid
                on_grid = min(ph, grid - ph) < 1e-3  # Arbeitsplan: 1 ms Rastertoleranz
                check(f"A1 Gitter {label} {os.path.basename(path)[:24]}", on_grid,
                      f"Phase {min(ph, grid - ph) * 1000:.1f}ms (Gitter {grid:.1f}s)")
        # first_phrase liegt auf dem Bar-Raster des Downbeats
        if t.first_phrase > 0 and t.bpm > 0:
            bar = (60.0 / t.bpm) * METER
            ph = (t.first_phrase - t.first_downbeat) % bar
            check(f"A1 first_phrase auf Bar-Raster {os.path.basename(path)[:24]}",
                  min(ph, bar - ph) < 1e-3, f"{min(ph, bar - ph) * 1000:.1f}ms")

        selected_pair = find_first_local_pair(tracks, E2E_BPM_TOLERANCE, ctx)
        if selected_pair is not None:
            break

    if selected_pair is None:
        if FAIL or len(tracks) < 2:
            print("\n=== FAIL ===")
            for failure in FAIL:
                print(" XX ", failure)
            if len(tracks) < 2 and not FAIL:
                print(" XX  Weniger als zwei Fixtures erfolgreich analysiert")
            return 1
        print(
            "E2E FIXTURE-SATZ UNZUREICHEND: innerhalb von "
            f"{args.max_fixtures} Fixtures keine lokal gueltige gerichtete Kante"
        )
        return 3
    else:
        # --- 2) Playlist + Empfehlungen ---
        ordered = generate_playlist(
            selected_pair,
            "Harmonic Flow",
            bpm_tolerance=E2E_BPM_TOLERANCE,
        )
        check("Playlist generiert", len(ordered) >= 2, f"{len(ordered)} Tracks")
        check(
            "Playlist behaelt eine gueltige gerichtete Kante",
            has_local_edge(ordered, E2E_BPM_TOLERANCE, ctx),
            "A -> B nach Sortierung",
        )
        recs = compute_transition_recommendations(
            ordered, bpm_tolerance=E2E_BPM_TOLERANCE, scoring_context=ctx
        )
        plans = [r.plan for r in recs if getattr(r, "plan", None) is not None]
        check("Empfehlungen", len(recs) >= 1, f"{len(recs)} Uebergaenge")
        check("Renderbarer Plan", bool(plans), f"{len(plans)} Plaene")

        # --- 3) Render + DSP-Invarianten ---
        if plans:
            import numpy as np
            import soundfile as sf
            with tempfile.TemporaryDirectory(prefix="hpg_e2e_") as temp_dir:
                out = os.path.join(temp_dir, "preview.wav")
                spec = TransitionClipSpec.from_plan(plans[0], ordered[0], ordered[1])
                render_transition_clip(spec, out)
                data, sr = sf.read(out, dtype="float32", always_2d=True)
                peak = float(np.max(np.abs(data)))
                check("Render laeuft", data.size > 0, f"{len(data)/sr:.1f}s @ {sr}Hz")
                check("Kein Clipping", peak <= 1.0 + 1e-4, f"peak={peak:.3f}")
                # Kein Lautheitsloch: RMS Fenstermitte vs. Raender (grob)
                n = len(data)
                mid = data[n // 2 - sr:n // 2 + sr]
                head = data[: 2 * sr]
                rms = lambda x: float(np.sqrt(np.mean(x ** 2)) + 1e-12)
                ratio_db = 20 * np.log10(rms(mid) / rms(head))
                check("Kein Pegel-Loch in der Mitte", ratio_db > -6.0,
                      f"Mitte vs Anfang {ratio_db:+.1f} dB")

    # --- 4) Rekordbox-Verfuegbarkeit (explizit, sonst reproduzierbar aus) ---
    if args.with_rekordbox:
        try:
            imp = RekordboxImporter()
            avail = imp.is_available()
            INFO.append(f"  Rekordbox-DB verfuegbar: {avail}")
            if avail and tracks:
                db_down = imp.get_first_downbeat(tracks[0].filePath)
                INFO.append(f"  ANLZ-Downbeat fuer Fixture: {db_down}")
        except Exception as exc:
            INFO.append(f"  Rekordbox-Check: {exc}")
    else:
        INFO.append("  Rekordbox-Check: deaktiviert (mit --with-rekordbox aktivieren)")

    print("\n=== INFO ===")
    for i in INFO:
        print(i)
    print("\n=== PASS ===")
    for p in PASS:
        print(" OK ", p)
    if FAIL:
        print("\n=== FAIL ===")
        for f in FAIL:
            print(" XX ", f)
        return 1
    print(f"\nE2E: {len(PASS)} Checks bestanden, 0 Fehler.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
