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
import logging
import tempfile
from dataclasses import dataclass

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfiltfilt
import librosa

from .config import MAX_TRANSITION_OVERLAP_SECONDS

logger = logging.getLogger(__name__)

# EQ-Cutoffs der Transition-Typen (L2-Fix: zentral statt hartkodiert im Code)
FILTER_RIDE_HP_HZ = 800.0    # Hochpass-Sweep beim Ausblenden (filter_ride)
SMOOTH_BLEND_LP_HZ = 300.0   # Tiefpass auf Track A (smooth_blend)
BREAKDOWN_HP_HZ = 250.0      # Bass-Kill auf Track A (breakdown_bridge)


# ---------------------------------------------------------------------------
# Daten-Klassen
# ---------------------------------------------------------------------------

@dataclass
class EqCrossfadeConfig:
    """Parameter fuer den EQ-Crossfade."""
    cf_frames: int
    sr: int
    bass_cutoff_hz: float
    transition_type: str


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
    bpm_a: float = 120.0         # BPM von Track A (fuer Time-Stretching)
    bpm_b: float = 120.0         # BPM von Track B (fuer Time-Stretching)
    # Downbeat-Feature 2026-07-17: bekannte erste Downbeats (Sekunden) beider
    # Tracks — ermoeglicht exaktes Beat-Alignment ohne Laufzeit-Schaetzung.
    # downbeat_reliable_* = True nur bei hoher Konfidenz (ANLZ-Beatgrid);
    # 0.0 ist dann ein LEGITIMER Anker (Track startet auf der "1").
    # Validierung 2026-07-17: die eigene Schaetzung ist fuers sample-genaue
    # Alignment zu ungenau (30-380ms Phasenfehler) -> dort Segment-Schaetzung.
    first_downbeat_a: float = 0.0
    first_downbeat_b: float = 0.0
    downbeat_reliable_a: bool = False
    downbeat_reliable_b: bool = False
    # Lautheits-Normalisierung (Research 2026-02-28: verhindert Lautheitssprunge)
    normalize_rms: bool = True          # RMS-Normalisierung vor Crossfade
    normalize_target_db: float = -14.0  # Ziel-Pegel in dBRMS (EBU R128: -14 LUFS)
    use_compressor: bool = False        # Optionaler pedalboard Compressor (experimentell)

    @classmethod
    def from_plan(cls, plan, from_track, to_track):
        """Erzeugt eine Render-Spezifikation ohne zweite Timing-Berechnung."""
        return cls(
            track_a_path=from_track.filePath,
            track_b_path=to_track.filePath,
            mix_out_sec=plan.mix_out_a,
            mix_in_sec=plan.mix_in_b,
            crossfade_sec=plan.overlap,
            transition_type=plan.transition_type,
            target_sr=plan.target_sr,
            bpm_a=float(from_track.bpm or 120.0),
            bpm_b=float(to_track.bpm or 120.0),
            first_downbeat_a=float(getattr(from_track, "first_downbeat", 0.0) or 0.0),
            first_downbeat_b=float(getattr(to_track, "first_downbeat", 0.0) or 0.0),
            downbeat_reliable_a=(
                getattr(from_track, "downbeat_confidence", 0.0) >= 0.9
            ),
            downbeat_reliable_b=(
                getattr(to_track, "downbeat_confidence", 0.0) >= 0.9
            ),
        )


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
    # Sicherheitslimit: max 64s Crossfade -- Trance/Progressive blenden 32-64 Bars
    # (~55-110s bei 138 BPM), 32s kappte die Preview systematisch vor dem Mix-Out
    cf_sec = min(spec.crossfade_sec, MAX_TRANSITION_OVERLAP_SECONDS)

    # Segmente berechnen
    a_start = max(0.0, spec.mix_out_sec - spec.pre_roll_sec)
    a_dur   = spec.pre_roll_sec + cf_sec
    b_start = max(0.0, spec.mix_in_sec)
    b_dur   = cf_sec + spec.post_roll_sec

    # Audio laden (beide Segmente)
    seg_a = _load_segment(spec.track_a_path, a_start, a_dur, sr)
    seg_b = _load_segment(spec.track_b_path, b_start, b_dur, sr)

    # Dynamic BPM Time-Stretching (echter DJ Pitchfader!)
    # Wenn Track B ein anderes Tempo als Track A besitzt, passen wir sein Tempo an Track A an.
    applied_stretch_rate = 1.0  # fuer die Downbeat-Phasen-Umrechnung unten
    if spec.bpm_a > 0 and spec.bpm_b > 0 and abs(spec.bpm_a - spec.bpm_b) > 0.05:
        target_bpm_b = spec.bpm_b
        
        # Half/Double-Erkennung relativ zum Zieltempo: DJ-Pitchfader-Praxis
        # erlaubt ~3-4% Anpassung, absolute 10-BPM-Fenster triggerten falsch
        half_double_tolerance = spec.bpm_a * 0.04

        # Check fuer Halftime-Switch (BPM_B ist ca. die Haelfte von BPM_A)
        if abs(spec.bpm_b * 2.0 - spec.bpm_a) < half_double_tolerance:
            target_bpm_b = spec.bpm_b * 2.0
            logger.info(f"Halftime-Switch erkannt fuer Track B: Virtuelle BPM verdoppelt von {spec.bpm_b:.1f} auf {target_bpm_b:.1f}")
        # Check fuer Doubletime-Switch (BPM_B ist ca. das Doppelte von BPM_A)
        elif abs(spec.bpm_b / 2.0 - spec.bpm_a) < half_double_tolerance:
            target_bpm_b = spec.bpm_b / 2.0
            logger.info(f"Doubletime-Switch erkannt fuer Track B: Virtuelle BPM halbiert von {spec.bpm_b:.1f} auf {target_bpm_b:.1f}")

        # Rate: rate = target_bpm_b / bpm_a.
        # Wenn rate > 1.0, wird das Signal verlangsamt. Wenn rate < 1.0, wird es beschleunigt.
        raw_rate = float(target_bpm_b / spec.bpm_a)

        # Sicherheitslimit fuer extremen Pitch (max +-15% vom Zieltempo)
        rate = max(0.85, min(1.15, raw_rate))
        # H3-Fix: geclampter Stretch bedeutet, dass der Preview NICHT
        # tempo-synchron laeuft — das muss sichtbar geloggt werden
        if abs(rate - raw_rate) > 1e-6:
            logger.warning(
                f"Time-Stretch geclamped (benoetigt Rate {raw_rate:.3f}, erlaubt 0.85-1.15): "
                f"Preview laeuft NICHT tempo-synchron ({spec.bpm_b:.1f} vs {spec.bpm_a:.1f} BPM)"
            )

        try:
            # librosa.effects.time_stretch arbeitet auf der LETZTEN Achse.
            # seg_b ist (frames, 2) → transponieren auf (2, frames), stretchen,
            # zurueck transponieren. (Das frueher genutzte axis=-Kwarg existiert
            # in dieser librosa-Version nicht und wuerde an stft() durchgereicht.)
            seg_b = librosa.effects.time_stretch(seg_b.T, rate=rate).T
            applied_stretch_rate = rate
            logger.info(f"BPM Time-Stretching angewendet: Track B ({spec.bpm_b:.1f} BPM -> {target_bpm_b:.1f} BPM) auf Track A ({spec.bpm_a:.1f} BPM) angepasst (Rate={rate:.4f})")
        except Exception as ts_err:
            logger.warning(f"BPM Time-Stretching fehlgeschlagen: {ts_err}")

    # RMS-Normalisierung: beide Tracks auf gleichen Lautheitspegel bringen
    # Verhindert hoerbare Lautheitssprunge im Crossfade (echte Tracks: bis 22 dB Differenz)
    if spec.normalize_rms:
        seg_a = _rms_normalize(seg_a, spec.normalize_target_db)
        seg_b = _rms_normalize(seg_b, spec.normalize_target_db)

    # Soll-Laengen in Frames
    cf_frames   = int(cf_sec * sr)
    pre_frames  = int(spec.pre_roll_sec * sr)
    post_frames = int(spec.post_roll_sec * sr)

    # H2-Fix: Beat-Phase-Alignment — Track B wird um den Phasenversatz
    # (< 1 Beat) verschoben, damit die Kicks im Crossfade uebereinander liegen.
    # Downbeat-Feature 2026-07-17: sind die ersten Downbeats beider Tracks
    # bekannt, wird der Versatz EXAKT aus den Beatgrids berechnet statt zur
    # Renderzeit geschaetzt (schneller und praeziser).
    if spec.bpm_a > 0 and len(seg_a) > pre_frames:
        try:
            known_a = known_b = None
            if spec.downbeat_reliable_a and spec.downbeat_reliable_b:
                beat_sec_a = 60.0 / spec.bpm_a
                # Zeit vom Segmentstart bis zum naechsten Grid-Beat
                known_a = (spec.first_downbeat_a - spec.mix_out_sec) % beat_sec_a
                beat_sec_b = 60.0 / spec.bpm_b if spec.bpm_b > 0 else beat_sec_a
                phase_b = (spec.first_downbeat_b - spec.mix_in_sec) % beat_sec_b
                # Track B wurde ggf. gestretcht: Zeitpunkte skalieren mit 1/rate
                known_b = phase_b / applied_stretch_rate
            seg_b = _align_beat_phase(
                seg_a[pre_frames:], seg_b, spec.bpm_a, sr,
                known_first_beat_a=known_a, known_first_beat_b=known_b,
            )
        except Exception as align_err:
            logger.warning(f"Beat-Phase-Alignment fehlgeschlagen: {align_err}")

    # Sicherstellen dass Segmente lang genug sind (Null-Padding falls noetig)
    seg_a = _ensure_len(seg_a, pre_frames + cf_frames)
    seg_b = _ensure_len(seg_b, cf_frames + post_frames)

    # Clip zusammenbauen
    part_pre  = seg_a[:pre_frames]             # Nur Track A vor dem Mix
    a_cf      = seg_a[pre_frames:]             # Track A im Crossfade-Bereich
    b_cf      = seg_b[:cf_frames]              # Track B im Crossfade-Bereich

    config = EqCrossfadeConfig(
        cf_frames=cf_frames,
        sr=sr,
        bass_cutoff_hz=spec.bass_cutoff_hz,
        transition_type=spec.transition_type,
    )
    part_cf   = _apply_eq_crossfade(a_cf, b_cf, config)
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


def _estimate_first_beat(seg: np.ndarray, sr: int, bpm: float) -> float:
    """Schaetzt den Zeitpunkt (Sekunden) des ersten Beats im Segment (max. 8s Fenster)."""
    mono = seg.mean(axis=1)
    window = mono[: int(min(len(mono), sr * 8))]
    if len(window) < sr:
        return 0.0
    _, beats = librosa.beat.beat_track(y=window, sr=sr, start_bpm=bpm, trim=False)
    beats = np.atleast_1d(beats)
    if beats.size == 0:
        return 0.0
    return float(librosa.frames_to_time(beats[0], sr=sr))


def _align_beat_phase(ref_seg: np.ndarray, seg_b: np.ndarray,
                      bpm: float, sr: int,
                      known_first_beat_a: float | None = None,
                      known_first_beat_b: float | None = None) -> np.ndarray:
    """
    Verschiebt seg_b um weniger als einen Beat, sodass sein erster Beat auf
    das Beat-Raster von ref_seg (Track A im Crossfade-Bereich) faellt.

    Downbeat-Feature 2026-07-17: sind die ersten Beat-Zeitpunkte beider
    Segmente aus den Beatgrids bekannt, entfaellt die (teurere und
    unsicherere) Laufzeit-Schaetzung via librosa.beat.beat_track.

    Verschiebung nach vorne = Samples am Anfang verwerfen, nach hinten =
    Null-Padding (< 1/2 Beat, unhoerbar da im Fade-In).
    """
    if bpm <= 0 or len(ref_seg) < sr or len(seg_b) < sr:
        return seg_b
    beat_len = int(round(60.0 / bpm * sr))
    if beat_len <= 0:
        return seg_b

    if known_first_beat_a is not None and known_first_beat_b is not None:
        t_a = float(known_first_beat_a)
        t_b = float(known_first_beat_b)
    else:
        t_a = _estimate_first_beat(ref_seg, sr, bpm)
        t_b = _estimate_first_beat(seg_b, sr, bpm)
    offset = int(round((t_b - t_a) * sr)) % beat_len
    if offset == 0:
        return seg_b

    if offset <= beat_len // 2:
        shifted = seg_b[offset:]
        shift_info = -offset
    else:
        pad = beat_len - offset
        shifted = np.concatenate(
            [np.zeros((pad, seg_b.shape[1]), dtype=seg_b.dtype), seg_b], axis=0
        )
        shift_info = pad
    logger.info(
        f"Beat-Phase-Alignment: Track B um {shift_info / sr * 1000:.0f}ms verschoben"
    )
    return shifted


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
                # L5-Fix: hoerbar stiller Preview braucht eine sichtbare Ursache im Log
                logger.warning(
                    f"Segment-Start {start_sec:.1f}s liegt hinter dem Dateiende — "
                    f"stilles Segment fuer {os.path.basename(path)} (Mix-Punkt pruefen)"
                )
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


_pedalboard_warned = False


def _apply_compressor(mixed: np.ndarray, sr: int) -> np.ndarray:
    """
    Wendet einen sanften pedalboard-Compressor an.

    2:1 Ratio + -12 dBFS Threshold = nicht destruktiv, Transienten bleiben erhalten.
    Fallback auf Eingangssignal wenn pedalboard nicht installiert ist.

    Testwert (2026-02-28 PoC): reduziert Lautheitssprung von ~2 dB auf ~0.1 dB
    nach vorheriger RMS-Normalisierung.
    """
    global _pedalboard_warned
    try:
        from pedalboard import Pedalboard, Compressor  # type: ignore[import]
    except ImportError:
        if not _pedalboard_warned:
            logger.warning(
                "Optional library 'pedalboard' is not installed. High-end transition compression is disabled. "
                "You can install it using 'pip install pedalboard' to enable smooth multi-band compression."
            )
            _pedalboard_warned = True
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
    config: EqCrossfadeConfig,
) -> np.ndarray:
    """
    Wendet hochpraezise, echt verdrahtete EQ- und DSP-Effekte fuer DJ-Übergänge an.

    Fade-Envelopes:
      fo (fade_out): 1.0 -> 0.0 linear (Track A verschwindet)
      fi (fade_in):  0.0 -> 1.0 linear (Track B erscheint)
    """
    fo = np.linspace(1.0, 0.0, config.cf_frames, dtype=np.float32)[:, np.newaxis]
    fi = np.linspace(0.0, 1.0, config.cf_frames, dtype=np.float32)[:, np.newaxis]

    t_type = str(config.transition_type).lower()

    if t_type == "bass_swap":
        # Bass (Tief) und Hoehen separat faden (klassischer EQ-Bass-Swap)
        sos_lp = _make_sos(config.bass_cutoff_hz, config.sr, 'low')
        sos_hp = _make_sos(config.bass_cutoff_hz, config.sr, 'high')

        highs_a = sosfiltfilt(sos_hp, seg_a, axis=0)
        highs_b = sosfiltfilt(sos_hp, seg_b, axis=0)
        bass_a  = sosfiltfilt(sos_lp, seg_a, axis=0)
        bass_b  = sosfiltfilt(sos_lp, seg_b, axis=0)

        # Hoehen: normaler linearer Crossfade
        mixed = highs_a * fo + highs_b * fi

        # M6-Fix: echter Bass-Handover — harter Swap am Crossfade-Mittelpunkt
        # mit kurzer 50ms-Rampe gegen Klicks. Vorher ueberlappten beide Baesse
        # (A~0.75 / B~0.25 am Mittelpunkt) — doppelter Sub-Bass.
        half = config.cf_frames // 2
        ramp = max(1, int(0.05 * config.sr))
        ramp_end = min(half + ramp, config.cf_frames)
        n_ramp = ramp_end - half
        bass_a_env = np.ones((config.cf_frames, 1), dtype=np.float32)
        bass_b_env = np.zeros((config.cf_frames, 1), dtype=np.float32)
        if n_ramp > 0:
            bass_a_env[half:ramp_end] = np.linspace(1.0, 0.0, n_ramp, dtype=np.float32)[:, np.newaxis]
            bass_b_env[half:ramp_end] = np.linspace(0.0, 1.0, n_ramp, dtype=np.float32)[:, np.newaxis]
        bass_a_env[ramp_end:] = 0.0
        bass_b_env[ramp_end:] = 1.0
        mixed = bass_a * bass_a_env + bass_b * bass_b_env + highs_a * fo + highs_b * fi

    elif t_type == "pro_eq_swap":
        # 3-Band Linkwitz-Riley EQ Simulation mit Zero-Phase Filtering (sosfiltfilt)
        fc1 = 120.0   # Low-to-Mid Crossover
        fc2 = 2500.0  # Mid-to-High Crossover

        # Filter design
        sos_lp_low  = _make_sos(fc1, config.sr, 'low', order=2)
        sos_hp_mid  = _make_sos(fc1, config.sr, 'high', order=2)
        sos_lp_mid  = _make_sos(fc2, config.sr, 'low', order=2)
        sos_hp_high = _make_sos(fc2, config.sr, 'high', order=2)

        # Trennung fuer Track A
        bass_a = sosfiltfilt(sos_lp_low, seg_a, axis=0)
        mids_a_tmp = sosfiltfilt(sos_hp_mid, seg_a, axis=0)
        mids_a = sosfiltfilt(sos_lp_mid, mids_a_tmp, axis=0)
        highs_a = sosfiltfilt(sos_hp_high, seg_a, axis=0)

        # Trennung fuer Track B
        bass_b = sosfiltfilt(sos_lp_low, seg_b, axis=0)
        mids_b_tmp = sosfiltfilt(sos_hp_mid, seg_b, axis=0)
        mids_b = sosfiltfilt(sos_lp_mid, mids_b_tmp, axis=0)
        highs_b = sosfiltfilt(sos_hp_high, seg_b, axis=0)

        # Envelopes
        # Lows (Bass-Swap auf der Haelfte mit 50ms Rampe)
        half = config.cf_frames // 2
        ramp = max(1, int(0.05 * config.sr))
        ramp_end = min(half + ramp, config.cf_frames)
        n_ramp = ramp_end - half

        bass_a_env = np.ones((config.cf_frames, 1), dtype=np.float32)
        bass_b_env = np.zeros((config.cf_frames, 1), dtype=np.float32)
        if n_ramp > 0:
            bass_a_env[half:ramp_end] = np.linspace(1.0, 0.0, n_ramp, dtype=np.float32)[:, np.newaxis]
            bass_b_env[half:ramp_end] = np.linspace(0.0, 1.0, n_ramp, dtype=np.float32)[:, np.newaxis]
        bass_a_env[ramp_end:] = 0.0
        bass_b_env[ramp_end:] = 1.0

        # Mids (Complementary -6 dB Rule: 1.0 -> 0.5 in der Mitte, dann 0.5 -> 0.0)
        mids_a_env = np.zeros((config.cf_frames, 1), dtype=np.float32)
        mids_b_env = np.zeros((config.cf_frames, 1), dtype=np.float32)

        mids_a_env[:half] = np.linspace(1.0, 0.5, half, dtype=np.float32)[:, np.newaxis]
        mids_a_env[half:] = np.linspace(0.5, 0.0, config.cf_frames - half, dtype=np.float32)[:, np.newaxis]

        mids_b_env[:half] = np.linspace(0.0, 0.5, half, dtype=np.float32)[:, np.newaxis]
        mids_b_env[half:] = np.linspace(0.5, 1.0, config.cf_frames - half, dtype=np.float32)[:, np.newaxis]

        # Highs (Asymmetrischer Tausch: A bleibt bis 3/4 voll da, blendet dann aus. B blendet ab 1/4 ein)
        quarter = config.cf_frames // 4
        three_quarters = 3 * quarter

        highs_a_env = np.ones((config.cf_frames, 1), dtype=np.float32)
        highs_b_env = np.zeros((config.cf_frames, 1), dtype=np.float32)

        len_out = config.cf_frames - three_quarters
        highs_a_env[three_quarters:] = np.linspace(1.0, 0.0, len_out, dtype=np.float32)[:, np.newaxis]

        len_in = three_quarters - quarter
        highs_b_env[quarter:three_quarters] = np.linspace(0.0, 1.0, len_in, dtype=np.float32)[:, np.newaxis]
        highs_b_env[three_quarters:] = 1.0

        # Rekonstruktion
        mixed = (bass_a * bass_a_env + bass_b * bass_b_env +
                 mids_a * mids_a_env + mids_b * mids_b_env +
                 highs_a * highs_a_env + highs_b * highs_b_env)

    elif t_type == "filter_ride" or t_type == "smooth_blend":
        # Hochpass- bzw. Tiefpass-Filterung zur Vermeidung von Frequenzüberlagerungen
        if t_type == "filter_ride":
            # Hochpass auf Track A simuliert einen Filter-Sweep beim Ausblenden
            sos_hp_a = _make_sos(FILTER_RIDE_HP_HZ, config.sr, 'high')
            filtered_a = sosfiltfilt(sos_hp_a, seg_a, axis=0)
            mixed = filtered_a * fo + seg_b * fi
        else:
            # smooth_blend: Tiefpass auf Track A waehrend Track B einfadet
            sos_lp_a = _make_sos(SMOOTH_BLEND_LP_HZ, config.sr, 'low')
            filtered_a = sosfiltfilt(sos_lp_a, seg_a, axis=0)
            mixed = filtered_a * fo + seg_b * fi

    elif t_type == "cold_cut":
        # Harter Cut genau in der Mitte ohne jede Blende
        half = config.cf_frames // 2
        mixed = np.zeros_like(seg_a)
        mixed[:half] = seg_a[:half]
        mixed[half:] = seg_b[half:]

    elif t_type == "drop_cut":
        # Track A blendet bis zur Mitte aus, dann bricht Track B schlagartig ein
        half = config.cf_frames // 2
        fo_half = np.linspace(1.0, 0.0, half, dtype=np.float32)[:, np.newaxis]
        mixed = np.zeros_like(seg_a)
        mixed[:half] = seg_a[:half] * fo_half
        mixed[half:] = seg_b[half:]

    elif t_type == "echo_out":
        # Track A bekommt ein echtes Echo-Delay-Feedback (Beat-synchrone Verzoegerung), waehrend Track B einfadet
        mixed = seg_b * fi
        
        # Delay-Zeit: ca. 0.5s fuer einen Viertelbeat bei 120 BPM
        delay_samples = int(0.5 * config.sr)
        echo_signal = seg_a.copy()
        
        # 3 Echo-Reflektionen mit Daempfung (Feedback)
        for i in range(1, 4):
            shift = i * delay_samples
            if shift < len(echo_signal):
                echo_signal[shift:] += seg_a[:-shift] * (0.45 ** i)
                
        mixed += echo_signal * fo

    elif t_type == "breakdown_bridge":
        # Bass aus Track A sofort komplett rausfiltern, um Platz fuer Track B zu machen
        sos_hp = _make_sos(BREAKDOWN_HP_HZ, config.sr, 'high')
        highs_a = sosfiltfilt(sos_hp, seg_a, axis=0)
        mixed = highs_a * fo + seg_b * fi

    else:
        # Standard-Fallback bei unkonfigurierten Typen: linearer Crossfade
        mixed = seg_a * fo + seg_b * fi

    return mixed.astype(np.float32)


# ---------------------------------------------------------------------------
# Direkt ausfuehrbar fuer schnellen Smoke-Test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
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
