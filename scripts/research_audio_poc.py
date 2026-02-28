"""
Research PoC: Audio-Bibliotheken Vergleich fuer Transition Preview
=================================================================

Testet drei Verbesserungen gegenueber der aktuellen transition_renderer.py:
  1. RMS-Lautheitsnormalisierung (scipy only, kein neues Dep)
  2. Butterworth vs LR4-aehnliche Filter (scipy only)
  3. pedalboard Compressor fuer Lautheitsausgleich (optional, neues Dep)

Ergebnis: 3 WAV-Dateien zum direkten Verhoer in %TEMP%\\hpg_research_*.wav

Ausfuehren:
  python scripts/research_audio_poc.py
"""

import os
import sys
import time
import tempfile
import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfiltfilt
from pathlib import Path

# Projekt-Root zum Pfad hinzufuegen
sys.path.insert(0, str(Path(__file__).parent.parent))
from hpg_core.transition_renderer import TransitionClipSpec, render_transition_clip

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------
TRACKS_DIR = r"D:\beatport_tracks_2025-08"
TMP = tempfile.gettempdir()

# Zwei Tracks auswaehlen (Khainz 126 BPM und Aqualize 122 BPM)
def find_tracks():
    """Sucht 2 geeignete AIFF-Tracks im Verzeichnis."""
    files = sorted([
        os.path.join(TRACKS_DIR, f)
        for f in os.listdir(TRACKS_DIR)
        if f.endswith(".aiff") and not f.startswith(".")
    ])
    if len(files) < 2:
        raise FileNotFoundError(f"Zu wenige AIFF-Dateien in {TRACKS_DIR}")
    return files[0], files[2]  # Khainz + Aqualize


# ---------------------------------------------------------------------------
# Version 1: AKTUELL (Butterworth + Soft-Limiter) — unveraendert
# ---------------------------------------------------------------------------
def render_current(track_a: str, track_b: str, out_path: str):
    """Renderert genau so wie die aktuelle transition_renderer.py."""
    spec = TransitionClipSpec(
        track_a_path   = track_a,
        track_b_path   = track_b,
        mix_out_sec    = 200.0,   # Ende von Track A
        mix_in_sec     = 60.0,    # Nach dem Intro von Track B
        crossfade_sec  = 16.0,
        transition_type= "bass_swap",
        pre_roll_sec   = 20.0,
        post_roll_sec  = 20.0,
    )
    return render_transition_clip(spec, out_path)


# ---------------------------------------------------------------------------
# Version 2: MIT RMS-Normalisierung (scipy only, kein neues Dep)
# ---------------------------------------------------------------------------
def _load_seg(path, start_sec, dur_sec, sr=44100):
    """Laedt Segment als (frames, 2) float32."""
    with sf.SoundFile(path) as f:
        sr_file = f.samplerate
        f.seek(max(0, int(start_sec * sr_file)))
        audio = f.read(int(dur_sec * sr_file), dtype='float32', always_2d=True)
    if audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)
    return audio


def rms_normalize(seg: np.ndarray, target_rms_db: float = -14.0) -> np.ndarray:
    """
    Normalisiert ein Audio-Segment auf einen Ziel-RMS-Pegel.

    Vorteil: Tracks mit sehr unterschiedlichen Lautheitspegeln klingen
    im Crossfade gleichmaessig — kein ploetzlicher Lautheitssprung.

    Hinweis: Berechnet RMS ohne die stillen Intro/Outro-Bereiche
    (untere 10% und obere 10% werden ignoriert).
    """
    # Flache Frames finden (oberste 80% Energie)
    energy = np.mean(seg**2, axis=1)
    threshold = np.percentile(energy, 20)  # 20. Perzentile
    active = seg[energy > threshold]

    if len(active) < 100:
        active = seg  # Fallback: ganzes Segment

    current_rms = np.sqrt(np.mean(active**2))
    if current_rms < 1e-6:
        return seg  # Stille → unveraendert

    target_rms_linear = 10 ** (target_rms_db / 20.0)
    gain = target_rms_linear / current_rms

    # Gain clampen: max. +12dB / -20dB (keine aggressiven Eingriffe)
    gain = np.clip(gain, 0.1, 4.0)
    return (seg * gain).astype(np.float32)


def _make_sos(cutoff_hz, sr, btype, order=4):
    return butter(order, cutoff_hz, btype=btype, fs=sr, output='sos')


def render_with_normalization(track_a: str, track_b: str, out_path: str):
    """
    Verbessert gegenueber Version 1:
      - RMS-Normalisierung auf -14 dBRMS vor dem Crossfade
      - Gleiche Butterworth-Filter wie bisher
    """
    sr = 44100
    mix_out = 200.0
    mix_in  = 60.0
    cf_sec  = 16.0
    pre     = 20.0
    post    = 20.0

    # Segmente laden
    seg_a = _load_seg(track_a, max(0, mix_out - pre), pre + cf_sec, sr)
    seg_b = _load_seg(track_b, max(0, mix_in),        cf_sec + post, sr)

    # RMS normalisieren
    seg_a = rms_normalize(seg_a, target_rms_db=-14.0)
    seg_b = rms_normalize(seg_b, target_rms_db=-14.0)

    # Crossfade (identisch zu transition_renderer.py)
    pre_f  = int(pre * sr)
    cf_f   = int(cf_sec * sr)
    post_f = int(post * sr)

    def ensure_len(arr, n):
        if len(arr) >= n: return arr[:n]
        return np.concatenate([arr, np.zeros((n-len(arr), 2), dtype=np.float32)])

    seg_a = ensure_len(seg_a, pre_f + cf_f)
    seg_b = ensure_len(seg_b, cf_f + post_f)

    fo = np.linspace(1.0, 0.0, cf_f, dtype=np.float32)[:, np.newaxis]
    fi = np.linspace(0.0, 1.0, cf_f, dtype=np.float32)[:, np.newaxis]

    a_cf = seg_a[pre_f:]
    b_cf = seg_b[:cf_f]
    sos_lp = _make_sos(200.0, sr, 'low')
    sos_hp = _make_sos(200.0, sr, 'high')

    highs_a = sosfiltfilt(sos_hp, a_cf, axis=0)
    highs_b = sosfiltfilt(sos_hp, b_cf, axis=0)
    bass_a  = sosfiltfilt(sos_lp, a_cf, axis=0)
    bass_b  = sosfiltfilt(sos_lp, b_cf, axis=0)

    mixed = highs_a * fo + highs_b * fi
    bass_a_fo = np.clip(fo * 1.5, 0.0, 1.0)
    bass_b_fi = np.clip(fi * 1.5 - 0.5, 0.0, 1.0)
    mixed += bass_a * bass_a_fo + bass_b * bass_b_fi

    part_cf   = mixed.astype(np.float32)
    part_pre  = seg_a[:pre_f]
    part_post = seg_b[cf_f:]

    result = np.concatenate([part_pre, part_cf, part_post], axis=0)
    peak = np.max(np.abs(result))
    if peak > 0.95:
        result = result * (0.95 / peak)

    sf.write(out_path, result, sr, subtype='PCM_16')
    return out_path


# ---------------------------------------------------------------------------
# Version 3: MIT RMS-Normalisierung + pedalboard Compressor
# ---------------------------------------------------------------------------
def render_with_compressor(track_a: str, track_b: str, out_path: str):
    """
    Versuch 3: pedalboard Compressor nach dem Mix fuer glaetteren Klang.
    Reduziert Lautheitssprueenge die durch Normalisierung nicht komplett
    behoben werden koennen.
    """
    try:
        from pedalboard import Pedalboard, Compressor, Limiter
    except ImportError:
        print("  pedalboard nicht verfuegbar, ueberspringe Version 3")
        return None

    sr = 44100
    mix_out = 200.0
    mix_in  = 60.0
    cf_sec  = 16.0
    pre     = 20.0
    post    = 20.0

    seg_a = _load_seg(track_a, max(0, mix_out - pre), pre + cf_sec, sr)
    seg_b = _load_seg(track_b, max(0, mix_in),        cf_sec + post, sr)

    # RMS normalisieren
    seg_a = rms_normalize(seg_a, target_rms_db=-14.0)
    seg_b = rms_normalize(seg_b, target_rms_db=-14.0)

    pre_f  = int(pre * sr)
    cf_f   = int(cf_sec * sr)
    post_f = int(post * sr)

    def ensure_len(arr, n):
        if len(arr) >= n: return arr[:n]
        return np.concatenate([arr, np.zeros((n-len(arr), 2), dtype=np.float32)])

    seg_a = ensure_len(seg_a, pre_f + cf_f)
    seg_b = ensure_len(seg_b, cf_f + post_f)

    fo = np.linspace(1.0, 0.0, cf_f, dtype=np.float32)[:, np.newaxis]
    fi = np.linspace(0.0, 1.0, cf_f, dtype=np.float32)[:, np.newaxis]

    a_cf = seg_a[pre_f:]
    b_cf = seg_b[:cf_f]
    sos_lp = _make_sos(200.0, sr, 'low')
    sos_hp = _make_sos(200.0, sr, 'high')

    highs_a = sosfiltfilt(sos_hp, a_cf, axis=0)
    highs_b = sosfiltfilt(sos_hp, b_cf, axis=0)
    bass_a  = sosfiltfilt(sos_lp, a_cf, axis=0)
    bass_b  = sosfiltfilt(sos_lp, b_cf, axis=0)

    mixed = highs_a * fo + highs_b * fi
    bass_a_fo = np.clip(fo * 1.5, 0.0, 1.0)
    bass_b_fi = np.clip(fi * 1.5 - 0.5, 0.0, 1.0)
    mixed += bass_a * bass_a_fo + bass_b * bass_b_fi

    part_cf   = mixed.astype(np.float32)
    part_pre  = seg_a[:pre_f]
    part_post = seg_b[cf_f:]

    result = np.concatenate([part_pre, part_cf, part_post], axis=0)

    # pedalboard Compressor: sanfte Kompression fuer gleichmaessigere Lautheit
    stereo = result.T  # (2, frames) fuer pedalboard
    board = Pedalboard([
        Compressor(
            threshold_db=-12.0,  # Erst bei -12 dBFS anfangen zu komprimieren
            ratio=2.0,           # 2:1 = sanfte, nicht-destruktive Kompression
            attack_ms=20.0,      # Langsamer Attack = Transienten bleiben erhalten
            release_ms=200.0,    # Normaler Release
        ),
    ])
    compressed = board(stereo, sr).T  # Zurueck zu (frames, 2)

    # Soft-Limiter am Ende
    peak = np.max(np.abs(compressed))
    if peak > 0.95:
        compressed = compressed * (0.95 / peak)

    sf.write(out_path, compressed.astype(np.float32), sr, subtype='PCM_16')
    return out_path


# ---------------------------------------------------------------------------
# Analyse-Ausgabe
# ---------------------------------------------------------------------------
def analyze_wav(path: str, label: str):
    """Gibt Lautheitsstatistiken eines WAV-Files aus."""
    with sf.SoundFile(path) as f:
        audio = f.read(dtype='float32')
        sr = f.samplerate
        dur = f.frames / sr

    # RMS im ersten und letzten Viertel
    q = len(audio) // 4
    rms_start = 20 * np.log10(np.sqrt(np.mean(audio[:q]**2)) + 1e-10)
    rms_end   = 20 * np.log10(np.sqrt(np.mean(audio[-q:]**2)) + 1e-10)
    rms_all   = 20 * np.log10(np.sqrt(np.mean(audio**2)) + 1e-10)
    peak      = 20 * np.log10(np.max(np.abs(audio)) + 1e-10)
    jump      = abs(rms_start - rms_end)

    print(f"  {label}:")
    print(f"    Dauer:  {dur:.1f}s | Peak: {peak:.1f} dBFS")
    print(f"    RMS Anfang: {rms_start:.1f} dB | RMS Ende: {rms_end:.1f} dB")
    print(f"    Lautheitssprung: {jump:.1f} dB {'<<<< HOERBAR' if jump > 6 else 'OK'}")
    print(f"    Gesamt-RMS: {rms_all:.1f} dBRMS")
    print()


# ---------------------------------------------------------------------------
# Hauptprogramm
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("HPG Audio-Library Research PoC")
    print("=" * 60)

    try:
        track_a, track_b = find_tracks()
    except FileNotFoundError as e:
        print(f"FEHLER: {e}")
        sys.exit(1)

    print(f"\nTrack A: {os.path.basename(track_a)}")
    print(f"Track B: {os.path.basename(track_b)}")
    print()

    results = {}

    # Version 1: Aktuell
    out1 = os.path.join(TMP, "hpg_research_v1_current.wav")
    print("Rendere Version 1 (Aktuell, Butterworth + Soft-Limiter)...")
    t0 = time.time()
    render_current(track_a, track_b, out1)
    t1 = time.time() - t0
    results["v1"] = (out1, t1)
    print(f"  Fertig in {t1:.1f}s -> {out1}")

    # Version 2: Mit RMS-Normalisierung
    out2 = os.path.join(TMP, "hpg_research_v2_rms_norm.wav")
    print("Rendere Version 2 (+ RMS-Normalisierung)...")
    t0 = time.time()
    render_with_normalization(track_a, track_b, out2)
    t1 = time.time() - t0
    results["v2"] = (out2, t1)
    print(f"  Fertig in {t1:.1f}s -> {out2}")

    # Version 3: Mit Compressor
    out3 = os.path.join(TMP, "hpg_research_v3_compressor.wav")
    print("Rendere Version 3 (+ RMS-Norm + pedalboard Compressor)...")
    t0 = time.time()
    render_with_compressor(track_a, track_b, out3)
    t1 = time.time() - t0
    results["v3"] = (out3, t1)
    print(f"  Fertig in {t1:.1f}s -> {out3}")

    # Analyse
    print("\n=== LAUTHEIT-ANALYSE ===\n")
    for key, (path, elapsed) in results.items():
        if path and os.path.exists(path):
            analyze_wav(path, f"Version {key[-1]} (Render: {elapsed:.1f}s)")

    print("=== HAER-TEST ===")
    print("Oeffne folgende Dateien in Windows Media Player oder VLC:")
    for _, (path, _) in results.items():
        if path and os.path.exists(path):
            print(f"  {path}")
    print()
    print("CHECKLISTE:")
    print("  1. Ist der Lautheitssprung in V1 hoerbar?")
    print("  2. Verbessert V2 (RMS-Norm) den Uebergang subjektiv?")
    print("  3. Verbessert V3 (Compressor) zusaetzlich?")
    print("  4. Klingt der Bass-Swap natuerlich oder holprig?")
    print("  5. Gibt es Clipping oder Verzerrung?")
