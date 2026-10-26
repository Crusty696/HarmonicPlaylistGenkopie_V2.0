"""Begrenzter Feintempokandidat aus einem festen Audio-Trainingsfenster."""

from __future__ import annotations

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import butter, find_peaks, sosfiltfilt
from scipy.stats import theilslopes

from .downbeat import (
    BEATGRID_MIN_FOLD_LOCK,
    EXACT_BEAT_SYNC_TOLERANCE_SECONDS,
    _beat_phase_from_fold,
)

# Feste Extraktorannahmen, keine aus 6 ms abgeleiteten Schwellen: am
# 2026-10-13 an 16 synthetischen Familien mit je sechs Gains sowie neun
# Gegenproben geprueft. Ein extremer Einzelimpuls kann Peaks unterdruecken;
# dieser Fall bleibt ohne Kandidat. Keine Parametersuche am Prueffenster.
TEMPO_TRAINING_SECONDS = 32
_PEAK_LOWPASS_HZ = 150.0
_PEAK_SMOOTH_SECONDS = 0.005
_PEAK_DISTANCE_SECONDS = 0.2
_PEAK_PROMINENCE = 0.04


def estimate_fine_tempo(
    y: np.ndarray,
    sr: int,
    prior_bpm: float,
    horizon_seconds: float,
    *,
    factor_candidates,
    diagnostics: dict | None = None,
) -> tuple[float, float] | None:
    """Liefert nur einen Kandidaten; unabhaengige Zeitfenster fehlen hier noch.

    Der Trainingsfit begrenzt Restfehler und beobachtete Steigungsstreuung
    ueber die gesamte beanspruchte Dauer. Das ist eine Konsistenzpruefung,
    keine Garantie fuer unbeobachtete Tempowechsel oder musikalische Eins.
    """
    detail = diagnostics if diagnostics is not None else {}
    detail.clear()

    def reject(reason: str):
        detail["reason"] = reason
        return None

    try:
        sample_rate = float(sr)
        prior = float(prior_bpm)
        horizon = float(horizon_seconds)
        audio = np.asarray(y)
        factors = np.asarray(factor_candidates, dtype=float)
        if (
            not np.isfinite(sample_rate) or sample_rate <= 2 * _PEAK_LOWPASS_HZ
            or not sample_rate.is_integer()
            or not np.isfinite(prior) or prior <= 0
            or not np.isfinite(horizon) or horizon < TEMPO_TRAINING_SECONDS
            or audio.ndim != 1 or np.iscomplexobj(audio)
            or factors.ndim != 1 or not factors.size
            or not np.all(np.isfinite(factors)) or np.any(factors <= 0)
            or not np.any(factors == 1.0)
        ):
            return reject("invalid_input")
        sample_rate = int(sample_rate)
        training_samples = TEMPO_TRAINING_SECONDS * sample_rate
        if len(audio) < training_samples:
            return reject("insufficient_training")
        training = np.asarray(audio[:training_samples], dtype=np.float64)
        if not np.all(np.isfinite(training)):
            return reject("invalid_input")
        scale = float(np.max(np.abs(training)))
        if scale <= 0:
            return reject("invalid_or_insufficient")
        normalized = training / scale
        envelope = uniform_filter1d(
            np.abs(sosfiltfilt(
                butter(4, _PEAK_LOWPASS_HZ, fs=sample_rate, output="sos"),
                normalized,
            )),
            max(3, int(_PEAK_SMOOTH_SECONDS * sample_rate) | 1),
        )
        peaks, _ = find_peaks(
            envelope,
            distance=max(1, int(_PEAK_DISTANCE_SECONDS * sample_rate)),
            prominence=_PEAK_PROMINENCE,
        )
        times = peaks / sample_rate
        detail["peak_count"] = len(times)
        # Vier Peaks erlauben gerade zwei getrennte Zweipunktfits. Die
        # 16 Familien oben pruefen diesen unveraenderten Prototypvertrag.
        if len(times) < 4:
            return reject("invalid_or_insufficient")
        raw_steps = np.rint(np.diff(times) / (60.0 / prior))
        if not np.all(np.isfinite(raw_steps)) or np.any(raw_steps < 1):
            return reject("multiple_peaks_per_target_beat")
        numbers = np.r_[0.0, np.cumsum(raw_steps)]
        if not np.all(np.isfinite(numbers)) or np.any(np.diff(numbers) <= 0):
            return reject("invalid_input")
        occupancy = (len(numbers) - 1) / numbers[-1]
        detail["occupancy"] = float(occupancy)
        # Mehr als die Haelfte belegt: strukturelle Alias-Abwehr des
        # Prototyps, keine statistische Ableitung aus der Synchrongrenze.
        if occupancy <= 0.5 or not np.any(raw_steps == 1):
            return reject("unobserved_subdivision_alias")
        slope, _, lower, upper = theilslopes(times, numbers)
        if not np.all(np.isfinite([slope, lower, upper])) or slope <= 0:
            return reject("invalid_fit")
        candidate = 60.0 / slope
        if not np.isfinite(candidate) or candidate <= 0:
            return reject("invalid_fit")
        detail["candidate_bpm"] = float(candidate)
        nearest = factors[np.argmin(np.abs(np.log((candidate / prior) / factors)))]
        if nearest != 1.0:
            return reject("different_factor")
        midpoint = (times[0] + times[-1]) / 2.0
        masks = (times < midpoint, times >= midpoint)
        if min(np.sum(mask) for mask in masks) < 2:
            return reject("insufficient_split_support")
        split = [float(theilslopes(times[mask], numbers[mask])[0]) for mask in masks]
        if not np.all(np.isfinite(split)) or min(split) <= 0:
            return reject("invalid_fit")
        intercept = float(np.median(times - slope * numbers))
        residual = float(np.max(np.abs(times - (intercept + slope * numbers))))
        spread = max(abs(lower - slope), abs(upper - slope),
                     *(abs(value - slope) for value in split))
        forecast = residual + horizon * spread / slope
        detail.update(
            max_training_residual_ms=1000.0 * residual,
            forecast_bound_ms=1000.0 * forecast,
            split_bpm=[60.0 / value for value in split],
            slope_ci=[float(lower), float(upper)],
        )
        if not np.isfinite(forecast) or forecast > EXACT_BEAT_SYNC_TOLERANCE_SECONDS:
            return reject("training_uncertainty_exceeds_sync_budget")
        phase, lock = _beat_phase_from_fold(training, sample_rate, 60.0 / candidate)
        if (phase is None or not np.isfinite(phase) or not 0 <= phase < 60.0 / candidate
                or not np.isfinite(lock) or lock < BEATGRID_MIN_FOLD_LOCK):
            return reject("invalid_training_fold")
        detail.update(reason="candidate_only", training_fold_lock=float(lock))
        return float(candidate), float(phase)
    except (TypeError, ValueError, OverflowError, FloatingPointError) as error:
        detail["error_type"] = type(error).__name__
        return reject("estimation_error")
