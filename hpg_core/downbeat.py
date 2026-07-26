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

from .config import HOP_LENGTH, METER

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
        # AUDIT-FIX N11 (2026-07-24): mode="same" behandelt Werte ausserhalb
        # des Arrays als 0, teilte aber weiter durch 5 — die Raender bekamen
        # dadurch einen kuenstlich ueberhoehten Akzent, der das Phase-Voting
        # systematisch zugunsten der ersten Beats verzerrte. Jetzt: durch die
        # tatsaechliche Fensterbreite pro Position normieren.
        kernel = np.ones(5)
        window_counts = np.convolve(np.ones_like(loud_score), kernel, mode="same")
        local_avg = np.convolve(loud_score, kernel, mode="same") / np.maximum(
            window_counts, 1.0
        )
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

        # AUDIT-FIX N10 (2026-07-24): Der Anker wurde vorher direkt aus einem
        # der ersten vier Beats gelesen (beat_times[best_phase]) — genau dem
        # Bereich, den das Trim-Kriterium als zu leise vom Voting ausschliesst
        # (Intro/Stille, maximaler Beat-Tracking-Jitter). Der Fehler propagierte
        # in JEDE Quantisierung des Projekts. Jetzt: aus allen VALIDEN Beats
        # der Gewinner-Phase per Median auf t0 zurueckrechnen — robust gegen
        # einzelne verschobene Beats.
        ibi = float(np.median(np.diff(beat_times)))
        first_downbeat = float(beat_times[best_phase])
        if ibi > 0:
            idx = np.arange(n_beats)
            phase_mask = valid & ((idx % 4) == best_phase)
            if int(np.sum(phase_mask)) >= 2:
                bar_len = 4.0 * ibi
                t0_estimates = (
                    beat_times[phase_mask] - (idx[phase_mask] // 4) * bar_len
                )
                t0 = float(np.median(t0_estimates))
                # auf den ersten nicht-negativen Rasterpunkt schieben
                if t0 < 0:
                    t0 += float(np.ceil(-t0 / bar_len)) * bar_len
                first_downbeat = t0

        # Feintuning: das Beat-Raster von librosa hat Hop-/Attack-Jitter —
        # den gewaehlten Downbeat auf den staerksten Bass-Onset im
        # +-1/2-Beat-Fenster snappen (Kick-Attack = praezise "1")
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


# Kalibrierungs-Basis von PHRASE_CONFIDENCE_MIN: die Schwelle wurde fuer
# 8-Bar-Phrasen gewaehlt (haeufigster Fall, Techno/House)
_PHRASE_UNIT_REFERENCE = 8


def _vote_margin_confidence(votes: np.ndarray) -> float:
    """AUDIT-FIX N-03 (2026-07-26): phrase_unit-invariante Voting-Konfidenz.

    Die rohe Margin-Konfidenz (v1 - v2) / sum(|votes|) faellt systematisch
    mit der Bin-Anzahl P: die Gewinner-Stimme buendelt nur noch n_bars/P
    Bars, waehrend die Rauschsumme im Nenner mit P waechst.
    PHRASE_CONFIDENCE_MIN wurde bei phrase_unit=8 kalibriert — bei
    16-Bar-Genres (Psytrance/Trance, Kern-Genres!) erreichte selbst starke
    2-Sigma-Struktur nur ~49 % Pass-Rate; die Phrasen-Erkennung war dort
    faktisch abgeschaltet.

    Fix: Konfidenz auf die 8er-Referenz normieren (Faktor P/8). Bei P=8 ist
    das exakt die alte, kalibrierte Groesse (kein Verhaltens-Drift, Noise-
    Rejection bleibt unveraendert streng); bei P=16/32 wird der strukturelle
    Nachteil der duenner besetzten Bins kompensiert. Feinkalibrierung an
    gelabelten Tracks: Plan 3.4.
    """
    p = int(votes.size)
    if p < 2:
        return 0.0
    order = np.argsort(votes)[::-1]
    margin = float(votes[order[0]] - votes[order[1]])
    spread = float(np.sum(np.abs(votes)))
    if spread < 1e-9:
        return 0.0
    scale = p / float(_PHRASE_UNIT_REFERENCE)
    return float(np.clip((margin / spread) * scale, 0.0, 1.0))


def estimate_first_phrase(
    y: np.ndarray,
    sr: int,
    bpm: float,
    first_downbeat: float,
    phrase_unit: int = 8,
) -> tuple[float, float]:
    """AUDIT-FEATURE A1 (2026-07-26): Schaetzt die PHRASEN-Phase eines Tracks.

    estimate_first_downbeat liefert nur die Takt-Phase (welcher Beat ist die
    "1"). Ein DJ denkt aber in Phrasen (8/16 Bars): Mix-Punkte, die auf einem
    Phrasengitter mit falscher Phrasen-Phase liegen, koennen bis zu
    phrase_unit-1 Bars neben der echten Phrasengrenze sitzen — hoerbar falsch.

    Erweiterung der Voting-Idee von estimate_first_downbeat auf Bar-Ebene:
    In EDM beginnen Phrasen dort, wo Elemente ein-/aussetzen — Kick-Einsatz,
    Filter-Oeffnung, harmonischer Wechsel, Energie-Sprung. Pro Bar-Grenze
    werden drei z-normierte Indizien berechnet und ueber bar_index %
    phrase_unit abgestimmt.

    Args:
        y: Audio (mono), idealerweise der Analyse-Head (>= ~2 Phrasen).
        sr: Samplerate.
        bpm: Tempo (validiert, > 0).
        first_downbeat: Takt-Anker in Sekunden (Basis des Bar-Rasters).
        phrase_unit: Phrasenlaenge in Bars (Genre-Profil: 8 oder 16).

    Returns:
        (first_phrase_seconds, confidence 0..1). first_phrase liegt auf dem
        Bar-Raster (first_downbeat + k * bar_len) innerhalb der ersten Phrase.
        (-1.0, 0.0) wenn keine belastbare Schaetzung moeglich ist.
        AUDIT-FIX R4 (2026-07-26): Sentinel ist -1.0 statt 0.0 — eine Phase
        von exakt 0.0 (Track startet auf der Phrasengrenze) ist GUELTIG und
        wurde vorher vom `> 0.0`-Gate der Aufrufer verworfen.
    """
    try:
        if bpm <= 0 or phrase_unit <= 1 or y is None or len(y) == 0:
            return -1.0, 0.0

        bar_len = (60.0 / bpm) * METER
        duration = len(y) / float(sr)
        # Anker in den Bereich [0, bar_len) falten, damit auch Bars vor dem
        # (ggf. spaeten) first_downbeat gezaehlt werden
        anchor = float(first_downbeat) % bar_len if bar_len > 0 else 0.0
        n_bars = int((duration - anchor) / bar_len)
        # Mindestens 2 volle Phrasen, sonst ist das Voting Rauschen
        if n_bars < phrase_unit * 2:
            return -1.0, 0.0

        bar_times = anchor + np.arange(n_bars) * bar_len

        # --- Feature-Grundlagen (einmal berechnen) ---
        bass_env = librosa.onset.onset_strength(
            y=y, sr=sr, hop_length=HOP_LENGTH, fmax=160, n_mels=16
        )
        chroma = librosa.feature.chroma_stft(y=y, sr=sr, hop_length=HOP_LENGTH)
        rms = librosa.feature.rms(y=y, hop_length=HOP_LENGTH)[0]
        bar_frames = librosa.time_to_frames(
            bar_times, sr=sr, hop_length=HOP_LENGTH
        ).astype(int)
        n_frames = min(len(bass_env), chroma.shape[1], len(rms))

        bass_score = np.zeros(n_bars)
        nov_score = np.zeros(n_bars)
        rms_delta = np.zeros(n_bars)

        for i in range(n_bars):
            f = int(bar_frames[i])
            if f < 0 or f >= n_frames:
                continue
            # Bass-Onset direkt an der Bar-Grenze (Kick-/Bass-Einsatz)
            lo = max(0, f - 1)
            hi = min(n_frames, f + 3)
            bass_score[i] = float(np.max(bass_env[lo:hi]))

            # Chroma-Novelty: Harmoniewechsel ueber die Bar-Grenze
            f_prev = int(bar_frames[i - 1]) if i > 0 else 0
            f_next = int(bar_frames[i + 1]) if i + 1 < n_bars else n_frames
            f_prev = max(0, min(f_prev, n_frames))
            f_next = max(f, min(f_next, n_frames))
            before = chroma[:, f_prev:f]
            after = chroma[:, f:f_next]
            if before.shape[1] > 0 and after.shape[1] > 0:
                b = before.mean(axis=1)
                a = after.mean(axis=1)
                nb, na = np.linalg.norm(b), np.linalg.norm(a)
                if nb > 1e-9 and na > 1e-9:
                    nov_score[i] = 1.0 - float(np.dot(b, a) / (nb * na))

            # RMS-Sprung: Energie der Bar vs. Vorgaenger-Bar
            if i > 0:
                cur = rms[f:min(n_frames, int(bar_frames[i + 1]) if i + 1 < n_bars else n_frames)]
                prev = rms[f_prev:f]
                if cur.size and prev.size:
                    rms_delta[i] = float(np.mean(cur) - np.mean(prev))

        z_bass = _znorm(bass_score)
        z_nov = _znorm(nov_score)
        # Nur POSITIVE Energie-Spruenge zaehlen (Element-Einsatz, nicht -Ausstieg)
        z_rms = _znorm(np.maximum(rms_delta, 0.0))

        combined = 1.0 * z_bass + 1.0 * z_nov + 0.75 * z_rms

        # --- Phase-Voting ueber bar_index % phrase_unit ---
        votes = np.zeros(phrase_unit)
        idx = np.arange(n_bars)
        for p in range(phrase_unit):
            mask = (idx % phrase_unit) == p
            if np.any(mask):
                votes[p] = float(np.sum(combined[mask]))

        best_phase = int(np.argmax(votes))
        # AUDIT-FIX N-03 (2026-07-26): phrase_unit-invariante Konfidenz —
        # Margin/Spread auf die 8-Bar-Referenz normiert (Faktor P/8), sonst
        # skaliert die Konfidenz mit der Bin-Anzahl und 16-Bar-Genres
        # fallen systematisch durch das PHRASE_CONFIDENCE_MIN-Gate.
        confidence = _vote_margin_confidence(votes)

        first_phrase = float(anchor + best_phase * bar_len)

        logger.debug(
            f"Phrasen-Phase: Bar {best_phase}/{phrase_unit}, "
            f"t={first_phrase:.3f}s, Konfidenz {confidence:.3f}"
        )
        return round(first_phrase, 4), round(confidence, 3)

    except Exception as e:
        logger.warning(f"Phrasen-Phase-Erkennung fehlgeschlagen: {e}")
        return -1.0, 0.0
