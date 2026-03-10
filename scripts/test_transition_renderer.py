"""
scripts/test_transition_renderer.py

Standalone-Test des Transition-Renderers mit echten Audio-Dateien.
Testet bass_swap und smooth_blend mit AIFF-Tracks aus D:\beatport_tracks_2025-08.

Ausfuehren:
    python scripts/test_transition_renderer.py

Ergebnis: Mehrere WAV-Dateien in %TEMP%, die man mit VLC/Windows Media Player hoeren kann.
"""

import os
import sys
import time

# Sicherstellen dass das Projektverzeichnis im Pfad ist
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from hpg_core.transition_renderer import (
    TransitionClipSpec,
    render_transition_clip,
    make_temp_output_path,
)
import soundfile as sf

# ---------------------------------------------------------------------------
# Test-Tracks
# ---------------------------------------------------------------------------

# AIFF-Tracks aus D:\beatport_tracks_2025-08
TRACK_DIR = r"D:\beatport_tracks_2025-08"

TRACK_A = os.path.join(TRACK_DIR, "Antinomy_-_Imagination_(Kalki_remix)_143__(Psy-Trance)_G_Major_02_21.aiff")
TRACK_B = os.path.join(TRACK_DIR, "Aqualize_-_Land_of_2_Suns_(Liquid_Soul_remix)_122__(Psy-Trance)_Gb_Major_02_27.aiff")

# Dritten Track fuer zweiten Test-Uebergang
TRACK_C_candidates = [
    f for f in os.listdir(TRACK_DIR)
    if f.endswith('.aiff') and not f.startswith('.')
]
TRACK_C = os.path.join(TRACK_DIR, TRACK_C_candidates[0]) if TRACK_C_candidates else TRACK_B


# ---------------------------------------------------------------------------
# Test-Faelle
# ---------------------------------------------------------------------------

TEST_CASES = [
    {
        "name": "bass_swap (Psy 143->122 BPM)",
        "spec": TransitionClipSpec(
            track_a_path    = TRACK_A,
            track_b_path    = TRACK_B,
            mix_out_sec     = 7 * 60 + 30.0,   # Letzte 30s des letzten Drittels
            mix_in_sec      = 15.0,              # Fruehes Intro von Track B
            crossfade_sec   = 16.0,
            transition_type = "bass_swap",
            pre_roll_sec    = 20.0,
            post_roll_sec   = 20.0,
            bass_cutoff_hz  = 200.0,
        ),
        "out": os.path.join(os.environ.get("TEMP", "/tmp"), "hpg_test_bass_swap.wav"),
    },
    {
        "name": "smooth_blend (Psy 143->psy3)",
        "spec": TransitionClipSpec(
            track_a_path    = TRACK_A,
            track_b_path    = TRACK_C,
            mix_out_sec     = 6 * 60 + 0.0,
            mix_in_sec      = 10.0,
            crossfade_sec   = 12.0,
            transition_type = "smooth_blend",
            pre_roll_sec    = 15.0,
            post_roll_sec   = 15.0,
        ),
        "out": os.path.join(os.environ.get("TEMP", "/tmp"), "hpg_test_smooth_blend.wav"),
    },
    {
        "name": "filter_ride (kurzer Crossfade 8s)",
        "spec": TransitionClipSpec(
            track_a_path    = TRACK_B,
            track_b_path    = TRACK_A,
            mix_out_sec     = 8 * 60 + 0.0,
            mix_in_sec      = 12.0,
            crossfade_sec   = 8.0,
            transition_type = "filter_ride",
            pre_roll_sec    = 10.0,
            post_roll_sec   = 10.0,
        ),
        "out": os.path.join(os.environ.get("TEMP", "/tmp"), "hpg_test_filter_ride.wav"),
    },
]


# ---------------------------------------------------------------------------
# Hauptprogramm
# ---------------------------------------------------------------------------

def check_tracks_exist():
    """Prueft ob die Test-Tracks vorhanden sind."""
    missing = []
    for path in [TRACK_A, TRACK_B]:
        if not os.path.exists(path):
            missing.append(path)
    if missing:
        print("\nFEHLER: Folgende Test-Tracks fehlen:")
        for p in missing:
            print(f"  {p}")
        print(f"\nVerfuegbare AIFF-Dateien in {TRACK_DIR}:")
        try:
            files = [f for f in os.listdir(TRACK_DIR) if f.endswith('.aiff')][:5]
            for f in files:
                print(f"  {f}")
        except Exception:
            pass
        sys.exit(1)


def run_test(test: dict) -> bool:
    """Fuehrt einen einzelnen Test durch."""
    name = test["name"]
    spec = test["spec"]
    out = test["out"]

    print(f"\n{'='*60}")
    print(f"Test: {name}")
    print(f"  Track A:  {os.path.basename(spec.track_a_path)}")
    print(f"  Track B:  {os.path.basename(spec.track_b_path)}")
    print(f"  Crossfade: {spec.crossfade_sec}s ({spec.transition_type})")
    print(f"  Geplante Clip-Dauer: {spec.pre_roll_sec + spec.crossfade_sec + spec.post_roll_sec:.0f}s")
    print(f"  Output: {out}")

    t0 = time.time()
    try:
        result = render_transition_clip(spec, out)
        elapsed = time.time() - t0
        info = sf.info(result)

        print(f"  ERFOLG in {elapsed:.1f}s")
        print(f"    Tatsaechliche Dauer: {info.duration:.1f}s")
        print(f"    Kanaele: {info.channels}")
        print(f"    Sample-Rate: {info.samplerate} Hz")
        print(f"    Dateigroesse: {os.path.getsize(result) / 1024:.0f} KB")

        # Basisvalidierungen
        expected_dur = spec.pre_roll_sec + spec.crossfade_sec + spec.post_roll_sec
        if abs(info.duration - expected_dur) > 2.0:
            print(f"  WARNUNG: Clip-Dauer {info.duration:.1f}s weicht von Erwartung {expected_dur:.0f}s ab")
        if info.channels != 2:
            print(f"  WARNUNG: Erwartet 2 Kanaele, bekommen {info.channels}")
        if info.samplerate != spec.target_sr:
            print(f"  WARNUNG: Sample-Rate {info.samplerate} != {spec.target_sr}")

        return True

    except Exception as e:
        elapsed = time.time() - t0
        print(f"  FEHLER nach {elapsed:.1f}s: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("HPG Transition Renderer — Standalone-Test mit echten Tracks")
    print(f"Track-Verzeichnis: {TRACK_DIR}")

    check_tracks_exist()

    print(f"\nTrack A: {os.path.basename(TRACK_A)}")
    print(f"Track B: {os.path.basename(TRACK_B)}")
    print(f"Track C: {os.path.basename(TRACK_C)}")

    results = []
    for test in TEST_CASES:
        ok = run_test(test)
        results.append((test["name"], ok))

    print(f"\n{'='*60}")
    print("ZUSAMMENFASSUNG:")
    all_ok = True
    for name, ok in results:
        status = "OK" if ok else "FEHLER"
        print(f"  [{status}] {name}")
        if not ok:
            all_ok = False

    if all_ok:
        print("\nAlle Tests BESTANDEN!")
        print("\nDie WAV-Dateien koennen nun in VLC oder Windows Media Player angehoert werden:")
        for test in TEST_CASES:
            if os.path.exists(test["out"]):
                print(f"  {test['out']}")
    else:
        print("\nEinige Tests FEHLGESCHLAGEN!")
        sys.exit(1)


if __name__ == "__main__":
    main()
