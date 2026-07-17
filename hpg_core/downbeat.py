"""
hpg_core/downbeat.py — Downbeat-Erkennung (die "1") fuer 4/4-Elektronik.

Ansatz nach Vande Veire & De Bie (EURASIP 2018, "From raw audio to a seamless
mix" — dort 98,1% korrekte Downbeat-Phase auf elektronischer Musik) als
leichtgewichtige Eigenimplementierung ohne neue Dependencies:

1. Beat-Raster via librosa.beat.beat_track (BPM-Prior aus der Analyse)
2. Leise Beats trimmen (Intro/Breakdown verwaessern das Voting)
3. Pro Beat drei z-normierte Indizien fuer "das ist eine 1":
   - Bass-Onset-Staerke (Hockman et al., ISMIR 2012: Low-Frequency-Onsets
     allein erreichen 72,8% — Kicks/Basswechsel markieren die 1)
   - Chroma-Novelty an der Beatgrenze (Davies/Plumbley-Prinzip:
     Harmoniewechsel fallen auf die 1)
   - Loudness-Akzent relativ zu den Nachbar-Beats
4. Phase-Voting ueber die 4 Hypothesen (Beat-Index mod 4) ueber den GANZEN
   Track — Einzel-Beat-Klassifikation darf mittelmaessig sein, die Summe
   ueber hunderte Takte ist robust und liefert EINE konsistente Phase.

Plan + Quellen: docs/plans/2026-07-17-downbeat-erkennung.md
"""

from __future__ import annotations

import logging

import numpy as np
import librosa

from .config import HOP_LENGTH

logger = logging.getLogger(__name__)

# Beats unterhalb dieses Anteils der Maximal-Loudness werden nicht gewertet
# (Vande Veire trimmt Intro/Outro vor dem Voting)
_TRIM_RATIO = 0.3

# Gewichte der drei Indizien (Bass, Chroma-Novelty, Loudness-Akzent)
_WEIGHTS = (1.0, 1.0, 0.5)

# Mindestanzahl auswertbarer Beats fuer ein belastbares Voting
_MIN_BEATS = 16


def _znorm(values: np.ndarray) -> np.ndarray:
    """Z-Normalisierung mit Guard gegen Null-Varianz."""
    std = float(np.std(values))
    if std < 1e-9:
        return np.zeros_like(values)
    return (values - float(np.mean(values))) / std


def estimate_first_downbeat(
    y: np.ndarray, sr: int, bpm: float
) -> tuple[float, float]:
    """
    Schaetzt den Zeitpunkt der ersten "1" (Downbeat) und eine Konfidenz.

    Args:
        y: Audio (mono)
        sr: Sample-Rate
        bpm: bekannte BPM (Prior fuers Beat-Tracking)

    Returns:
        (first_downbeat_seconds, confidence 0-1).
        (0.0, 0.0) bei Fehler/zu wenig Material — Verhalten wie ohne Anker.
    """
    if y is None or bpm <= 0 or len(y) < sr * 8:
        return 0.0, 0.0

    try:
        _, beat_frames = librosa.beat.beat_track(
            y=y, sr=sr, hop_length=HOP_LENGTH, start_bpm=bpm, trim=False
        )
        beat_frames = np.atleast_1d(beat_frames)
        if beat_frames.size < _MIN_BEATS:
            return 0.0, 0.0
        beat_times = librosa.frames_to_time(
            beat_frames, sr=sr, hop_length=HOP_LENGTH
        )
        beat_samples = (beat_times * sr).astype(int)

        # --- Feature-Kurven (frame-basiert) ---
        # Bass-Onsets: Mel-Spektrum auf <= 160 Hz beschraenkt (Kick/Sub)
        bass_env = librosa.onset.onset_strength(
            y=y, sr=sr, hop_length=HOP_LENGTH, fmax=160, n_mels=16
        )
        chroma = librosa.feature.chroma_stft(y=y, sr=sr, hop_length=HOP_LENGTH)

        n_beats = len(beat_times)
        bass_score = np.zeros(n_beats)
        nov_score = np.zeros(n_beats)
        loud_score = np.zeros(n_beats)

        for i in range(n_beats):
            f = int(beat_frames[i])
            # Bass-Onset am Beat (kleines Fenster gegen Frame-Jitter)
            lo, hi = max(0, f - 1), min(len(bass_env), f + 2)
            if hi > lo:
                bass_score[i] = float(np.max(bass_env[lo:hi]))

            # Chroma-Novelty: Cosinus-Distanz zwischen dem Beat-Fenster
            # davor und danach (Harmoniewechsel auf der 1)
            f_next = int(beat_frames[i + 1]) if i + 1 < n_beats else chroma.shape[1]
            f_prev = int(beat_frames[i - 1]) if i > 0 else 0
            before = chroma[:, f_prev:f]
            after = chroma[:, f:f_next]
            if before.shape[1] > 0 and after.shape[1] > 0:
                b = before.mean(axis=1)
                a = after.mean(axis=1)
                nb, na = np.linalg.norm(b), np.linalg.norm(a)
                if nb > 1e-9 and na > 1e-9:
                    nov_score[i] = 1.0 - float(np.dot(b, a) / (nb * na))

            # Loudness des Beat-Fensters
            s_end = beat_samples[i + 1] if i + 1 < n_beats else len(y)
            seg = y[beat_samples[i]:s_end]
            if seg.size:
                loud_score[i] = float(np.sqrt(np.mean(seg.astype(np.float64) ** 2)))

        # --- Trim: leise Beats (Intro/Breakdown) nicht werten ---
        loud_max = float(np.max(loud_score))
        if loud_max < 1e-9:
            return 0.0, 0.0
        valid = loud_score >= loud_max * _TRIM_RATIO
        if int(np.sum(valid)) < _MIN_BEATS:
            return 0.0, 0.0

        # Loudness-AKZENT: relativ zum lokalen Umfeld (nicht absolute Lautheit)
        kernel = np.ones(5) / 5.0
        local_avg = np.convolve(loud_score, kernel, mode="same")
        accent = loud_score - local_avg

        z_bass = _znorm(bass_score[valid])
        z_nov = _znorm(nov_score[valid])
        z_accent = _znorm(accent[valid])
        phases = (np.arange(n_beats) % 4)[valid]

        # --- Phase-Voting ---
        votes = np.zeros(4)
        combined = (
            _WEIGHTS[0] * z_bass + _WEIGHTS[1] * z_nov + _WEIGHTS[2] * z_accent
        )
        for p in range(4):
            mask = phases == p
            if np.any(mask):
                votes[p] = float(np.sum(combined[mask]))

        order = np.argsort(votes)[::-1]
        best_phase = int(order[0])
        spread = float(np.sum(np.abs(votes)))
        confidence = 0.0
        if spread > 1e-9:
            confidence = float(
                np.clip((votes[order[0]] - votes[order[1]]) / spread, 0.0, 1.0)
            )

        first_downbeat = float(beat_times[best_phase])

        # Feintuning: das Beat-Raster von librosa hat Hop-/Attack-Jitter —
        # den gewaehlten Downbeat auf den staerksten Bass-Onset im
        # +-1/2-Beat-Fenster snappen (Kick-Attack = praezise "1")
        ibi = float(np.median(np.diff(beat_times)))
        if ibi > 0:
            half = ibi / 2.0
            f_lo = int(librosa.time_to_frames(
                max(0.0, first_downbeat - half), sr=sr, hop_length=HOP_LENGTH
            ))
            f_hi = int(librosa.time_to_frames(
                first_downbeat + half, sr=sr, hop_length=HOP_LENGTH
            )) + 1
            f_lo = max(0, min(f_lo, len(bass_env) - 1))
            f_hi = max(f_lo + 1, min(f_hi, len(bass_env)))
            local = bass_env[f_lo:f_hi]
            if local.size and float(np.max(local)) > 0:
                peak_frame = f_lo + int(np.argmax(local))
                first_downbeat = float(librosa.frames_to_time(
                    peak_frame, sr=sr, hop_length=HOP_LENGTH
                ))

        logger.debug(
            f"Downbeat: Phase {best_phase}, t={first_downbeat:.3f}s, "
            f"Konfidenz {confidence:.2f}"
        )
        return round(first_downbeat, 4), round(confidence, 3)

    except Exception as e:
        logger.warning(f"Downbeat-Erkennung fehlgeschlagen: {e}")
        return 0.0, 0.0
