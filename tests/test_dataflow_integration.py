"""
Umfassender Integrations- und Datenqualitaets-Test
Prueft den gesamten Datenfluss: Audio-Datei → Analyse → Cache → Playlist
"""
import os
import sys
import time
import glob
import traceback

# Projekt-Pfad
sys.path.insert(0, os.path.dirname(__file__))

AUDIO_DIR = r"D:\beatport_tracks_2025-08"
RESULTS = {"pass": 0, "fail": 0, "warn": 0}


def check(name, condition, detail=""):
    if condition:
        RESULTS["pass"] += 1
        print(f"  [PASS] {name}")
    else:
        RESULTS["fail"] += 1
        print(f"  [FAIL] {name} — {detail}")


def warn(name, detail=""):
    RESULTS["warn"] += 1
    print(f"  [WARN] {name} — {detail}")


def get_test_files(n=5):
    """Hole n Audio-Dateien zum Testen."""
    patterns = ["*.wav", "*.mp3", "*.flac", "*.aiff"]
    files = []
    for pat in patterns:
        files.extend(glob.glob(os.path.join(AUDIO_DIR, pat)))
    if not files:
        print(f"FATAL: Keine Audio-Dateien in {AUDIO_DIR}")
        sys.exit(1)
    return files[:n]


# ============================================================
# TEST 1: Einzeltrack-Analyse — Datenqualitaet
# ============================================================
def test_single_track_quality():
    print("\n" + "=" * 60)
    print("TEST 1: Einzeltrack-Analyse — Datenqualitaet")
    print("=" * 60)

    from hpg_core.analysis import analyze_track

    files = get_test_files(3)

    for fp in files:
        fname = os.path.basename(fp)
        print(f"\n  Analysiere: {fname}")
        t0 = time.time()
        track = analyze_track(fp)
        elapsed = time.time() - t0
        print(f"  Dauer: {elapsed:.1f}s")

        check(f"{fname}: Track nicht None", track is not None, "analyze_track gab None zurueck")
        if not track:
            continue

        # Core Fields
        check(f"{fname}: filePath gesetzt", track.filePath == fp)
        check(f"{fname}: fileName gesetzt", track.fileName == fname)

        # BPM plausibel (elektronische Musik: 70-200 BPM)
        check(f"{fname}: BPM > 0", track.bpm > 0, f"BPM={track.bpm}")
        check(f"{fname}: BPM plausibel (70-200)", 70 <= track.bpm <= 200,
              f"BPM={track.bpm} — ausserhalb typischem Range")

        # Duration plausibel (30s - 15min)
        check(f"{fname}: Duration > 0", track.duration > 0, f"duration={track.duration}")
        check(f"{fname}: Duration plausibel (30-900s)", 30 < track.duration < 900,
              f"duration={track.duration}s")

        # Key/Camelot
        check(f"{fname}: keyNote gesetzt", bool(track.keyNote), f"keyNote='{track.keyNote}'")
        check(f"{fname}: keyMode gesetzt", track.keyMode in ("Major", "Minor"),
              f"keyMode='{track.keyMode}'")
        check(f"{fname}: camelotCode gesetzt", bool(track.camelotCode),
              f"camelotCode='{track.camelotCode}'")
        if track.camelotCode:
            # Camelot Format: 1A-12A, 1B-12B
            num = track.camelotCode[:-1]
            letter = track.camelotCode[-1]
            check(f"{fname}: Camelot-Format korrekt",
                  num.isdigit() and 1 <= int(num) <= 12 and letter in ("A", "B"),
                  f"camelotCode='{track.camelotCode}'")

        # Energy & Bass (0-100)
        check(f"{fname}: Energy 0-100", 0 <= track.energy <= 100,
              f"energy={track.energy}")
        check(f"{fname}: Bass 0-100", 0 <= track.bass_intensity <= 100,
              f"bass={track.bass_intensity}")

        # Mix Points
        check(f"{fname}: mix_in < mix_out",
              track.mix_in_point < track.mix_out_point,
              f"in={track.mix_in_point}, out={track.mix_out_point}")
        check(f"{fname}: mix_in >= 0", track.mix_in_point >= 0)
        check(f"{fname}: mix_out <= duration",
              track.mix_out_point <= track.duration + 1,
              f"out={track.mix_out_point}, dur={track.duration}")

        # DJ Brain Fields
        check(f"{fname}: detected_genre gesetzt", bool(track.detected_genre),
              f"genre='{track.detected_genre}'")
        check(f"{fname}: genre_confidence 0-1",
              0 <= track.genre_confidence <= 1,
              f"conf={track.genre_confidence}")

        # Sections (sollte mindestens 1 haben)
        check(f"{fname}: Sections vorhanden", len(track.sections) > 0,
              f"sections={len(track.sections)}")
        if track.sections:
            # Jede Section hat start_time, end_time, label (TrackSection.to_dict() via asdict)
            for i, sec in enumerate(track.sections):
                if not all(k in sec for k in ("start_time", "end_time", "label")):
                    check(f"{fname}: Section[{i}] hat start_time/end_time/label", False,
                          f"keys={list(sec.keys())}")
                    break
            else:
                check(f"{fname}: Alle Sections haben start_time/end_time/label", True)

        # Audio Features
        check(f"{fname}: brightness 0-100", 0 <= track.brightness <= 100,
              f"brightness={track.brightness}")
        check(f"{fname}: vocal_instrumental valid",
              track.vocal_instrumental in ("vocal", "instrumental", "unknown"),
              f"vocal={track.vocal_instrumental}")
        check(f"{fname}: danceability 0-100", 0 <= track.danceability <= 100,
              f"dance={track.danceability}")
        check(f"{fname}: mfcc_fingerprint nicht leer",
              len(track.mfcc_fingerprint) > 0,
              f"mfcc_len={len(track.mfcc_fingerprint)}")


# ============================================================
# TEST 2: Cache-Integritaet
# ============================================================
def test_cache_integrity():
    print("\n" + "=" * 60)
    print("TEST 2: Cache-Integritaet")
    print("=" * 60)

    from hpg_core.analysis import analyze_track
    from hpg_core.caching import generate_cache_key, get_cached_track

    files = get_test_files(2)

    for fp in files:
        fname = os.path.basename(fp)
        print(f"\n  Teste Cache fuer: {fname}")

        # Erste Analyse (ggf. Cache-Hit wenn vorher schon analysiert)
        track1 = analyze_track(fp)
        check(f"{fname}: Erste Analyse OK", track1 is not None)
        if not track1:
            continue

        # Cache-Key generieren
        cache_key = generate_cache_key(fp)
        check(f"{fname}: Cache-Key generiert", cache_key is not None)

        # Cache-Lookup (mit file_path fuer TOCTOU-Check)
        cached = get_cached_track(cache_key, file_path=fp)
        check(f"{fname}: Cache-Hit", cached is not None, "Cache liefert None")

        if cached:
            # Vergleiche kritische Felder
            check(f"{fname}: Cache BPM == Original",
                  cached.bpm == track1.bpm,
                  f"cached={cached.bpm}, orig={track1.bpm}")
            check(f"{fname}: Cache Key == Original",
                  cached.camelotCode == track1.camelotCode,
                  f"cached={cached.camelotCode}, orig={track1.camelotCode}")
            check(f"{fname}: Cache Energy == Original",
                  cached.energy == track1.energy,
                  f"cached={cached.energy}, orig={track1.energy}")
            check(f"{fname}: Cache Genre == Original",
                  cached.detected_genre == track1.detected_genre,
                  f"cached={cached.detected_genre}, orig={track1.detected_genre}")
            check(f"{fname}: Cache Sections == Original",
                  len(cached.sections) == len(track1.sections),
                  f"cached={len(cached.sections)}, orig={len(track1.sections)}")
            check(f"{fname}: Cache MFCC == Original",
                  len(cached.mfcc_fingerprint) == len(track1.mfcc_fingerprint),
                  f"cached={len(cached.mfcc_fingerprint)}, orig={len(track1.mfcc_fingerprint)}")


# ============================================================
# TEST 3: Parallel-Analyse — Datenfluss
# ============================================================
def test_parallel_analysis():
    print("\n" + "=" * 60)
    print("TEST 3: Parallel-Analyse — Datenfluss")
    print("=" * 60)

    from hpg_core.parallel_analyzer import ParallelAnalyzer, get_optimal_worker_count

    files = get_test_files(5)
    print(f"  {len(files)} Dateien zum Testen")

    # Worker-Count
    wc = get_optimal_worker_count(len(files))
    check("Worker-Count > 0", wc > 0, f"workers={wc}")
    print(f"  Optimale Workers: {wc}")

    # Analyse
    analyzer = ParallelAnalyzer()
    progress_calls = []

    def progress_cb(current, total, msg):
        progress_calls.append((current, total, msg))

    t0 = time.time()
    tracks = analyzer.analyze_files(files, progress_callback=progress_cb)
    elapsed = time.time() - t0

    print(f"  Ergebnis: {len(tracks)}/{len(files)} Tracks in {elapsed:.1f}s")

    check("Mindestens 1 Track analysiert", len(tracks) > 0, f"got {len(tracks)}")
    check("Progress-Callbacks empfangen", len(progress_calls) > 0,
          f"calls={len(progress_calls)}")

    # Pruefe jeden Track
    for t in tracks:
        fname = t.fileName
        check(f"{fname}: BPM > 0 (parallel)", t.bpm > 0, f"BPM={t.bpm}")
        check(f"{fname}: Duration > 0 (parallel)", t.duration > 0)
        check(f"{fname}: Camelot gesetzt (parallel)", bool(t.camelotCode))
        check(f"{fname}: Genre gesetzt (parallel)", bool(t.detected_genre))
        check(f"{fname}: Sections vorhanden (parallel)", len(t.sections) > 0)
        check(f"{fname}: MFCC vorhanden (parallel)", len(t.mfcc_fingerprint) > 0)


# ============================================================
# TEST 4: Playlist-Generierung — End-to-End
# ============================================================
def test_playlist_generation():
    print("\n" + "=" * 60)
    print("TEST 4: Playlist-Generierung — End-to-End")
    print("=" * 60)

    from hpg_core.parallel_analyzer import ParallelAnalyzer
    from hpg_core.playlist import generate_playlist

    files = get_test_files(5)
    analyzer = ParallelAnalyzer()
    tracks = analyzer.analyze_files(files)

    if len(tracks) < 2:
        warn("Nicht genug Tracks fuer Playlist", f"nur {len(tracks)} analysiert")
        return

    print(f"  {len(tracks)} Tracks analysiert, generiere Playlist...")

    # Teste verschiedene Modi
    modes = ["Harmonic Flow Enhanced", "Energy Wave", "Consistent"]
    for mode in modes:
        print(f"\n  Modus: {mode}")
        try:
            result = generate_playlist(tracks, mode=mode, bpm_tolerance=3.0)

            if isinstance(result, tuple):
                playlist, quality = result
            else:
                playlist = result
                quality = {}

            check(f"{mode}: Playlist nicht leer", len(playlist) > 0,
                  f"len={len(playlist) if playlist else 0}")

            if playlist:
                # Alle Tracks in Playlist sind gueltige Track-Objekte
                for i, entry in enumerate(playlist):
                    t = entry if hasattr(entry, 'bpm') else getattr(entry, 'track', None)
                    if t:
                        check(f"{mode}[{i}]: BPM > 0", t.bpm > 0)
                        check(f"{mode}[{i}]: Camelot", bool(t.camelotCode))
                    else:
                        check(f"{mode}[{i}]: Track-Objekt vorhanden", False,
                              f"type={type(entry)}")
                        break

            if quality:
                print(f"  Quality-Metrics: {list(quality.keys())}")
                check(f"{mode}: Quality-Dict hat Keys", len(quality) > 0)

        except Exception as e:
            check(f"{mode}: Keine Exception", False, f"{e}")
            traceback.print_exc()


# ============================================================
# TEST 5: Config-Werte korrekt importiert
# ============================================================
def test_config_imports():
    print("\n" + "=" * 60)
    print("TEST 5: Config-Werte und Imports")
    print("=" * 60)

    from hpg_core.config import PARALLEL_ANALYSIS_TIMEOUT
    check("PARALLEL_ANALYSIS_TIMEOUT importierbar", True)
    check("PARALLEL_ANALYSIS_TIMEOUT = 60", PARALLEL_ANALYSIS_TIMEOUT == 60,
          f"got {PARALLEL_ANALYSIS_TIMEOUT}")

    from hpg_core.parallel_analyzer import ParallelAnalyzer
    check("ParallelAnalyzer importierbar", True)

    from hpg_core.caching import get_cached_track, generate_cache_key, cache_track
    check("Cache-Funktionen importierbar", True)

    # Signatur-Check: get_cached_track akzeptiert file_path
    import inspect
    sig = inspect.signature(get_cached_track)
    params = list(sig.parameters.keys())
    check("get_cached_track hat file_path Parameter",
          "file_path" in params, f"params={params}")


# ============================================================
# TEST 6: Edge-Cases
# ============================================================
def test_edge_cases():
    print("\n" + "=" * 60)
    print("TEST 6: Edge-Cases")
    print("=" * 60)

    from hpg_core.analysis import analyze_track
    from hpg_core.caching import generate_cache_key, get_cached_track

    # None-Input
    check("analyze_track(None) = None", analyze_track(None) is None)

    # Leerer String
    check("analyze_track('') = None", analyze_track("") is None)

    # Nicht existierende Datei
    check("analyze_track('nonexistent.wav') = None",
          analyze_track("nonexistent.wav") is None)

    # Cache mit None-Key
    check("get_cached_track(None) = None", get_cached_track(None) is None)

    # Cache mit leerem Key
    check("get_cached_track('') = None", get_cached_track("") is None)

    # Cache-Key fuer nicht existierende Datei
    key = generate_cache_key("nonexistent_file.wav")
    check("generate_cache_key('nonexistent') = None", key is None)

    # Parallel-Analyse mit leerer Liste
    from hpg_core.parallel_analyzer import ParallelAnalyzer
    analyzer = ParallelAnalyzer()
    result = analyzer.analyze_files([])
    check("analyze_files([]) = []", result == [])

    # Parallel-Analyse mit nicht existierenden Dateien
    result = analyzer.analyze_files(["fake1.mp3", "fake2.wav"])
    check("analyze_files(fake_files) = []", len(result) == 0,
          f"got {len(result)} tracks")


# ============================================================
# TEST 7: Cooperative Cancel (simuliert)
# ============================================================
def test_cooperative_cancel():
    print("\n" + "=" * 60)
    print("TEST 7: Cooperative Cancel Check (Code-Pruefung)")
    print("=" * 60)

    # Pruefe ob AnalysisWorker._should_cancel existiert
    # (Wir koennen es nicht GUI-maessig starten, aber Code pruefen)
    import importlib
    spec = importlib.util.spec_from_file_location(
        "main", os.path.join(os.path.dirname(__file__), "main.py"))

    # Einfacher Code-Check
    with open(os.path.join(os.path.dirname(__file__), "main.py"), "r", encoding="utf-8") as f:
        source = f.read()

    check("_should_cancel in AnalysisWorker", "_should_cancel" in source)
    check("request_cancel() Methode existiert", "def request_cancel(self)" in source)
    check("InterruptedError Handler existiert", "except InterruptedError" in source)
    check("html_mod.escape in set_timing", "html_mod.escape" in source)
    check("import html as html_mod", "import html as html_mod" in source)
    check("setUpdatesEnabled(False) in mix_recs", "setUpdatesEnabled(False)" in source)
    check("setUpdatesEnabled(True) in mix_recs", "setUpdatesEnabled(True)" in source)
    check("os.access(path, os.R_OK) in set_folder", "os.access(path, os.R_OK)" in source)
    check("start_button.setEnabled(False) vorhanden",
          "start_button.setEnabled(False)" in source)


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("HPG V2.0 — Umfassender Datenfluss- und Qualitaets-Test")
    print("=" * 60)
    print(f"Audio-Dir: {AUDIO_DIR}")
    print(f"Audio-Dateien vorhanden: {os.path.isdir(AUDIO_DIR)}")

    tests = [
        ("Config & Imports", test_config_imports),
        ("Edge-Cases", test_edge_cases),
        ("Cooperative Cancel (Code)", test_cooperative_cancel),
        ("Einzeltrack-Qualitaet", test_single_track_quality),
        ("Cache-Integritaet", test_cache_integrity),
        ("Parallel-Analyse", test_parallel_analysis),
        ("Playlist End-to-End", test_playlist_generation),
    ]

    for test_name, test_fn in tests:
        try:
            test_fn()
        except Exception as e:
            print(f"\n  [FATAL] {test_name} abgebrochen: {e}")
            traceback.print_exc()
            RESULTS["fail"] += 1

    # Zusammenfassung
    total = RESULTS["pass"] + RESULTS["fail"] + RESULTS["warn"]
    print("\n" + "=" * 60)
    print(f"ERGEBNIS: {RESULTS['pass']} PASS / {RESULTS['fail']} FAIL / {RESULTS['warn']} WARN (von {total})")
    print("=" * 60)

    if RESULTS["fail"] > 0:
        print(">>> FEHLER GEFUNDEN — siehe oben <<<")
        sys.exit(1)
    else:
        print(">>> ALLES OK <<<")
        sys.exit(0)
