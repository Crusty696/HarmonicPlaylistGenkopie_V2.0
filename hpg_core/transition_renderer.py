"""
hpg_core/transition_renderer.py

Rendert einen Transition-Preview-Clip als WAV-Datei.
Verwendet: scipy.signal (EQ-Filter) + soundfile (I/O) + numpy (Mix)
Keine neuen pip-Abhaengigkeiten noetig — scipy und soundfile sind bereits
implizite Abhaengigkeiten von librosa.

Aufbau eines gerenderten Clips:
    [pre_roll]  |  [crossfade]  |  [post_roll]
    Nur Track A    Beide gemischt  Nur Track B
"""

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfiltfilt


# ---------------------------------------------------------------------------
# Daten-Klassen
# ---------------------------------------------------------------------------

@dataclass
class TransitionClipSpec:
    """Parameter fuer einen Transition-Preview-Clip."""
    track_a_path: str            # Voller Dateipfad zu Track A
    track_b_path: str            # Voller Dateipfad zu Track B
    mix_out_sec: float           # Position in Track A, wo Crossfade beginnt
    mix_in_sec: float            # Position in Track B, wo Crossfade beginnt
    crossfade_sec: float         # Laenge des Crossfade-Bereichs (Sekunden)
    transition_type: str = "smooth_blend"  # bass_swap / smooth_blend / filter_ride / ...
    pre_roll_sec: float = 30.0   # Sekunden von Track A VOR dem Crossfade
    post_roll_sec: float = 30.0  # Sekunden von Track B NACH dem Crossfade
    bass_cutoff_hz: float = 200.0
    target_sr: int = 44100
    # Lautheits-Normalisierung (Research 2026-02-28: verhindert Lautheitssprunge)
    normalize_rms: bool = True          # RMS-Normalisierung vor Crossfade
    normalize_target_db: float = -14.0  # Ziel-Pegel in dBRMS (EBU R128: -14 LUFS)
    use_compressor: bool = False        # Optionaler pedalboard Compressor (experimentell)


# ---------------------------------------------------------------------------
# Oeffentliche Hauptfunktion
# ---------------------------------------------------------------------------

def render_transition_clip(spec: TransitionClipSpec, output_path: str) -> str:
    """
    Rendert den Transition-Clip und speichert ihn als 16-bit PCM WAV.

    Lade-Strategie:
      Track A: start = mix_out_sec - pre_roll_sec,  dauer = pre_roll_sec + crossfade_sec
      Track B: start = mix_in_sec,                   dauer = crossfade_sec + post_roll_sec

    Gibt den output_path zurueck.
    """
    sr = spec.target_sr
    cf_sec = min(spec.crossfade_sec, 32.0)  # Sicherheitslimit: max 32s Crossfade

    # Segmente berechnen
    a_start = max(0.0, spec.mix_out_sec - spec.pre_roll_sec)
    a_dur   = spec.pre_roll_sec + cf_sec
    b_start = max(0.0, spec.mix_in_sec)
    b_dur   = cf_sec + spec.post_roll_sec

    # Audio laden (beide Segmente)
    seg_a = _load_segment(spec.track_a_path, a_start, a_dur, sr)
    seg_b = _load_segment(spec.track_b_path, b_start, b_dur, sr)

    # RMS-Normalisierung: beide Tracks auf gleichen Lautheitspegel bringen
    # Verhindert hoerbare Lautheitssprunge im Crossfade (echte Tracks: bis 22 dB Differenz)
    if spec.normalize_rms:
        seg_a = _rms_normalize(seg_a, spec.normalize_target_db)
        seg_b = _rms_normalize(seg_b, spec.normalize_target_db)

    # Soll-Laengen in Frames
    cf_frames   = int(cf_sec * sr)
    pre_frames  = int(spec.pre_roll_sec * sr)
    post_frames = int(spec.post_roll_sec * sr)

    # Sicherstellen dass Segmente lang genug sind (Null-Padding falls noetig)
    seg_a = _ensure_len(seg_a, pre_frames + cf_frames)
    seg_b = _ensure_len(seg_b, cf_frames + post_frames)

    # Clip zusammenbauen
    part_pre  = seg_a[:pre_frames]             # Nur Track A vor dem Mix
    a_cf      = seg_a[pre_frames:]             # Track A im Crossfade-Bereich
    b_cf      = seg_b[:cf_frames]              # Track B im Crossfade-Bereich

    part_cf   = _apply_eq_crossfade(
        a_cf, b_cf, cf_frames, sr,
        spec.bass_cutoff_hz, spec.transition_type
    )
    part_post = seg_b[cf_frames:]              # Nur Track B nach dem Mix

    # Zusammenfuegen
    mixed = np.concatenate([part_pre, part_cf, part_post], axis=0)

    # Optionaler Compressor (pedalboard) fuer gleichmaessigere Lautheit im Mix
    # Glaettet residuale Schwankungen die RMS-Norm nicht vollstaendig behebt
    if spec.use_compressor:
        mixed = _apply_compressor(mixed, sr)

    # Soft-Limiter gegen Clipping (kein hartes Brick-Wall)
    peak = np.max(np.abs(mixed))
    if peak > 0.95:
        mixed = mixed * (0.95 / peak)

    # Als 16-bit PCM WAV exportieren
    sf.write(output_path, mixed.astype(np.float32), samplerate=sr, subtype='PCM_16')
    return output_path


def make_temp_output_path(index: int) -> str:
    """Erstellt einen temporaeren Pfad fuer eine Preview-WAV-Datei."""
    tmp_dir = tempfile.gettempdir()
    return os.path.join(tmp_dir, f"hpg_preview_{index:03d}.wav")


# ---------------------------------------------------------------------------
# Hilfsfunktionen (intern)
# ---------------------------------------------------------------------------

def _load_segment(path: str, start_sec: float, duration_sec: float,
                  target_sr: int = 44100) -> np.ndarray:
    """
    Laedt nur den benoetigten Abschnitt einer Audio-Datei.

    soundfile unterstuetzt: WAV, FLAC, AIFF, OGG (nativ, schnell, offset-seeking).
    MP3 wird von soundfile NICHT unterstuetzt → Fallback via librosa.load().

    Gibt immer ein (frames, 2) float32 Array zurueck.
    Mono wird auf Stereo verdoppelt.
    """
    path = str(path)
    audio = None

    # Erster Versuch: soundfile (schnell, unterstuetzt offset-seeking)
    try:
        with sf.SoundFile(path) as f:
            sr_file    = f.samplerate
            start_frame = int(start_sec * sr_file)
            num_frames  = int(duration_sec * sr_file)
            # Seek jenseits Dateiende → leeres Array zurueckgeben (kein Fehler)
            if start_frame >= f.frames:
                return np.zeros((0, 2), dtype=np.float32)
            f.seek(max(0, start_frame))
            audio = f.read(num_frames, dtype='float32', always_2d=True)
            sr_loaded = sr_file
    except (sf.LibsndfileError, RuntimeError):
        # Fallback fuer MP3 und andere nicht-unterstuetzte Formate
        try:
            import librosa
            y, sr_loaded = librosa.load(
                path, sr=None, mono=False,
                offset=start_sec, duration=duration_sec
            )
            if y.ndim == 1:
                y = np.stack([y, y], axis=0)   # Mono → (2, frames)
            audio = y.T.astype(np.float32)      # → (frames, 2)
        except Exception as e:
            raise RuntimeError(f"Konnte Datei nicht laden: {path!r} — {e}") from e

    # Kanal-Normalisierung: immer (frames, 2)
    if audio.ndim == 1:
        audio = audio[:, np.newaxis]
    if audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)     # Mono → Stereo duplizieren
    elif audio.shape[1] > 2:
        audio = audio[:, :2]                    # Surround → Stereo beschraenken

    # Sample-Rate-Konvertierung wenn noetig (Ausnahme, meist 44100)
    if sr_loaded != target_sr:
        import librosa
        # librosa.resample erwartet (channels, frames)
        audio = librosa.resample(audio.T, orig_sr=sr_loaded, target_sr=target_sr).T

    return audio.astype(np.float32)


def _ensure_len(arr: np.ndarray, n: int) -> np.ndarray:
    """
    Stellt sicher dass arr mindestens n Frames hat.
    Zu kurze Arrays werden mit Null-Frames aufgefuellt (Stille am Ende).
    """
    if len(arr) >= n:
        return arr[:n]
    pad = np.zeros((n - len(arr), 2), dtype=np.float32)
    return np.concatenate([arr, pad])


def _make_sos(cutoff_hz: float, sr: int, btype: str, order: int = 4) -> np.ndarray:
    """
    Erstellt einen Butterworth-Filter als Second-Order-Sections (SOS).
    Butterworth = maximale Flachheit im Durchlassbereich, kein Ripple.
    """
    return butter(order, cutoff_hz, btype=btype, fs=sr, output='sos')


def _rms_normalize(seg: np.ndarray, target_rms_db: float = -14.0) -> np.ndarray:
    """
    Normalisiert ein Audio-Segment auf einen Ziel-RMS-Pegel.

    Berechnet RMS nur anhand aktiver Frames (obere 80% Energie) um stille
    Intro/Outro-Bereiche zu ignorieren. Gain wird auf +12dB/-20dB begrenzt.

    Hintergrund: EBU R128 definiert -14 LUFS als Streaming-Norm (Spotify, YouTube).
    Durch Normalisierung auf -14 dBRMS klingen unterschiedlich gemasterte Tracks
    im Crossfade gleichmaessig — kein ploetzlicher Lautheitssprung.
    """
    # Aktive Frames finden (obere 80% Energie — ignoriert stille Passagen)
    energy = np.mean(seg**2, axis=1)
    threshold = np.percentile(energy, 20)
    active = seg[energy > threshold]

    # Fallback: gesamtes Segment wenn zu wenige aktive Frames
    if len(active) < 100:
        active = seg

    current_rms = np.sqrt(np.mean(active**2))
    if current_rms < 1e-6:
        return seg  # Stilles Segment unveraendert lassen

    target_rms_linear = 10 ** (target_rms_db / 20.0)
    gain = target_rms_linear / current_rms

    # Gain clampen: max. +12 dB (4.0x) / -20 dB (0.1x) — verhindert aggressive Eingriffe
    gain = float(np.clip(gain, 0.1, 4.0))
    return (seg * gain).astype(np.float32)


def _apply_compressor(mixed: np.ndarray, sr: int) -> np.ndarray:
    """
    Wendet einen sanften pedalboard-Compressor an.

    2:1 Ratio + -12 dBFS Threshold = nicht destruktiv, Transienten bleiben erhalten.
    Fallback auf Eingangssignal wenn pedalboard nicht installiert ist.

    Testwert (2026-02-28 PoC): reduziert Lautheitssprung von ~2 dB auf ~0.1 dB
    nach vorheriger RMS-Normalisierung.
    """
    try:
        from pedalboard import Pedalboard, Compressor  # type: ignore[import]
    except ImportError:
        # pedalboard nicht installiert — kein Fehler, kein Compressor
        return mixed

    # pedalboard erwartet (channels, frames) — wir haben (frames, channels)
    stereo = mixed.T
    board = Pedalboard([
        Compressor(
            threshold_db=-12.0,  # Erst ab -12 dBFS komprimieren
            ratio=2.0,           # 2:1 = sanfte Kompression
            attack_ms=20.0,      # Langer Attack = Transienten bleiben erhalten
            release_ms=200.0,    # Normaler Release
        ),
    ])
    compressed = board(stereo, sr).T  # Zurueck zu (frames, channels)
    return compressed.astype(np.float32)


def _apply_eq_crossfade(
    seg_a: np.ndarray,       # (cf_frames, 2) float32 — Track A im Crossfade
    seg_b: np.ndarray,       # (cf_frames, 2) float32 — Track B im Crossfade
    cf_frames: int,
    sr: int,
    bass_cutoff_hz: float,
    transition_type: str,
) -> np.ndarray:
    """
    Wendet EQ-basierten Crossfade an.

    Fade-Envelopes:
      fo (fade_out): 1.0 → 0.0 linear (Track A verschwindet)
      fi (fade_in):  0.0 → 1.0 linear (Track B erscheint)

    Typen:
      bass_swap    — Bass und Hoehen getrennt faden, Bass verzoevert
      filter_ride  — Hochpass-Filter auf Track A, dann normaler Crossfade
      alle anderen — einfacher linearer Crossfade (safe)
    """
    fo = np.linspace(1.0, 0.0, cf_frames, dtype=np.float32)[:, np.newaxis]
    fi = np.linspace(0.0, 1.0, cf_frames, dtype=np.float32)[:, np.newaxis]

    if transition_type == "bass_swap":
        # Bass (Tief) und Hoehen separat faden
        sos_lp = _make_sos(bass_cutoff_hz, sr, 'low')
        sos_hp = _make_sos(bass_cutoff_hz, sr, 'high')

        # sosfiltfilt: zero-phase (vorwaerts + rueckwaerts) — kein Phasenfehler
        highs_a = sosfiltfilt(sos_hp, seg_a, axis=0)
        highs_b = sosfiltfilt(sos_hp, seg_b, axis=0)
        bass_a  = sosfiltfilt(sos_lp, seg_a, axis=0)
        bass_b  = sosfiltfilt(sos_lp, seg_b, axis=0)

        # Hoehen: normaler linearer Crossfade
        mixed = highs_a * fo + highs_b * fi

        # Bass von Track A bleibt laenger (spaeter abfaden)
        bass_a_fo = np.clip(fo * 1.5, 0.0, 1.0)
        # Bass von Track B kommt spaeter (verspaetetes Einblenden)
        bass_b_fi = np.clip(fi * 1.5 - 0.5, 0.0, 1.0)
        mixed += bass_a * bass_a_fo + bass_b * bass_b_fi

    elif transition_type == "filter_ride":
        # Hochpass auf Track A simuliert einen Filter-Sweep beim Ausblenden
        # (vereinfacht: fester 800 Hz HP statt dynamisch sweepender Cutoff)
        sos_hp_a = _make_sos(800.0, sr, 'high')
        filtered_a = sosfiltfilt(sos_hp_a, seg_a, axis=0)
        mixed = filtered_a * fo + seg_b * fi

    else:
        # smooth_blend, drop_cut, breakdown_bridge, echo_out, cold_cut,
        # halftime_switch und alle unbekannten Typen: linearer Crossfade
        mixed = seg_a * fo + seg_b * fi

    return mixed.astype(np.float32)


# ---------------------------------------------------------------------------
# Direkt ausfuehrbar fuer schnellen Smoke-Test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    print("transition_renderer — Smoke-Test mit synthetischen Daten")

    # Synthetischen Stereo-Sinus erzeugen und als WAV schreiben
    test_sr = 44100
    duration = 60.0  # 1 Minute pro Test-Track
    t = np.linspace(0, duration, int(test_sr * duration), endpoint=False)
    track_a_data = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
    track_b_data = (np.sin(2 * np.pi * 528 * t) * 0.5).astype(np.float32)
    track_a_stereo = np.stack([track_a_data, track_a_data], axis=1)
    track_b_stereo = np.stack([track_b_data, track_b_data], axis=1)

    tmp = tempfile.gettempdir()
    path_a = os.path.join(tmp, "hpg_test_track_a.wav")
    path_b = os.path.join(tmp, "hpg_test_track_b.wav")
    out_path = os.path.join(tmp, "hpg_smoke_test_preview.wav")

    sf.write(path_a, track_a_stereo, test_sr, subtype='PCM_16')
    sf.write(path_b, track_b_stereo, test_sr, subtype='PCM_16')

    spec = TransitionClipSpec(
        track_a_path    = path_a,
        track_b_path    = path_b,
        mix_out_sec     = 40.0,
        mix_in_sec      = 5.0,
        crossfade_sec   = 16.0,
        transition_type = "bass_swap",
        pre_roll_sec    = 10.0,
        post_roll_sec   = 10.0,
    )

    result = render_transition_clip(spec, out_path)
    file_info = sf.info(result)
    print(f"  Output: {result}")
    print(f"  Dauer:  {file_info.duration:.1f}s")
    print(f"  Kanaele: {file_info.channels}")
    print(f"  Sample-Rate: {file_info.samplerate} Hz")

    expected_dur = spec.pre_roll_sec + spec.crossfade_sec + spec.post_roll_sec
    assert abs(file_info.duration - expected_dur) < 0.5, \
        f"Erwartete Dauer {expected_dur}s, bekommen {file_info.duration:.1f}s"
    print(f"  Smoke-Test BESTANDEN (Erwartete Dauer: ~{expected_dur:.0f}s)")

    # Aufraeumen
    for p in [path_a, path_b, out_path]:
        if os.path.exists(p):
            os.remove(p)
