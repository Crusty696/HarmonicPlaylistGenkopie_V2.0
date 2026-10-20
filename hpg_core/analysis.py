from __future__ import annotations  # Python 3.9 compatibility for | type hints

import hashlib
import json
import logging
import math
import os
import re
import time
from bisect import bisect_left
from dataclasses import dataclass, field

import librosa
import mutagen
import numpy as np
import soundfile as sf

from .caching import (
    VALID_ANALYSIS_MODES,
    cache_track,
    generate_cache_key,
    get_cached_track,
)
from .config import (
    SUPPORTED_AUDIO_EXTENSIONS,
    HOP_LENGTH,
    METER,
    MIX_POINT_UNSET,
    MIX_IN_SEARCH_WINDOW_PCT,
    MIX_OUT_SEARCH_WINDOW_PCT,
    RMS_THRESHOLD,
    DEFAULT_BPM,
    BPM_HALFTIME_MAX_RESULT,
    FEATURE_WINDOW_DURATION,
    LIBROSA_FAST_PATH_DURATION,
    LIBROSA_MAX_DURATION,
    LIBROSA_TAIL_DURATION,
    PHRASE_CONFIDENCE_MIN,
    SECURITY_MAX_FILE_SIZE,
    SECURITY_MAX_TRACK_DURATION,
)
from .dj_brain import (
    _get_intro_end_from_sections,
    _get_outro_start_from_sections,
    align_ai_mix_points,
    calculate_genre_aware_mix_points,
)
from .downbeat import (
    BeatgridValidation,
    BEATGRID_MIN_FOLD_LOCK,
    BEATGRID_MIN_WINDOWS,
    BEATGRID_MAX_INTERVAL_DEVIATION,
    EXACT_BEAT_SYNC_TOLERANCE_SECONDS,
    DOWNBEAT_RELIABLE_MIN,
    _beat_phase_from_fold,
    estimate_first_downbeat,
    estimate_first_phrase,
    validate_beatgrid_windows,
)
from .genre_classifier import classify_genre, match_id3_genre
from .measurement_contract import DOWNBEAT_REASONS, GRID_REASONS, measurement_snapshot
from .ai_models import cue_service
from contextlib import nullcontext
from .genres import GENRE_PROFILES
from .groove import (
    BASS_KENNWERTE_MIN_SEC,
    GrooveFeatures,
    bass_kennwerte,
    extract_groove,
)
from .mix_candidates import (
    CUE_IN_PATTERN,
    CUE_OUT_PATTERN,
    build_track_candidates,
    normalize_cues,
)
from .models import (
    CAMELOT_MAP,
    QUANTIZE_TOLERANCE_SEC,
    Track,
    bar_position_usage_blocked,
    get_camelot_components,
    quantize_to_grid,
    seconds_to_bars,
)
from .rekordbox_importer import get_rekordbox_importer
from .rekordbox_phrases import phrase_grid_from_phrases
from .structure_analyzer import (
    GENRE_PHRASE_UNITS,
    TrackSection,
    TrackStructure,
    analyze_structure,
)
from .tempo_refinement import TEMPO_TRAINING_SECONDS, estimate_fine_tempo

logger = logging.getLogger(__name__)

_BEATGRID_WINDOW_SECONDS = 16.0
ID3_BPM_FACTOR_CANDIDATES = (
    0.5,
    2.0 / 3.0,
    3.0 / 4.0,
    1.0,
    4.0 / 3.0,
    1.5,
    2.0,
)
ID3_BPM_DIRECT_DEVIATION_MIN = 0.08
ID3_BPM_FACTOR_DEVIATION_MAX = 0.06


def _correct_id3_bpm_factor(
    tag_bpm: float,
    measured_bpm: float,
    id3_genre: str,
) -> float:
    """Korrigiert ausschliesslich klare Faktorfehler eines ID3-BPM-Tags."""
    tag = float(tag_bpm)
    try:
        measured = float(measured_bpm)
    except (TypeError, ValueError):
        return tag
    if not np.isfinite(measured) or measured <= 0.0:
        return tag

    canonical = match_id3_genre(id3_genre or "")
    if not canonical or canonical not in GENRE_PROFILES:
        return tag
    lower, upper = GENRE_PROFILES[canonical].bpm_range
    if lower <= tag <= upper:
        return tag

    direct = abs(tag - measured) / measured
    if direct <= ID3_BPM_DIRECT_DEVIATION_MIN:
        return tag
    candidates = [
        (abs(tag * factor - measured) / measured, factor)
        for factor in ID3_BPM_FACTOR_CANDIDATES
        if lower <= tag * factor <= upper
    ]
    if not candidates:
        return tag
    deviation, factor = min(candidates)
    corrected = tag * factor
    if (
        factor == 1.0
        or (
            deviation > ID3_BPM_FACTOR_DEVIATION_MAX
            and not math.isclose(
                deviation,
                ID3_BPM_FACTOR_DEVIATION_MAX,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        )
        or not lower <= corrected <= upper
    ):
        return tag
    return round(corrected, 2)


def _refine_audio_tempo(
    y: np.ndarray, sr: int, bpm: float, *, file_path: str, duration: float,
    diagnostics: dict | None = None,
) -> float:
    """Feintempo nur nach drei vollstaendigen, getrennten Audiopruefungen."""
    detail = diagnostics if diagnostics is not None else {}
    detail.clear()

    def retain(reason: str) -> float:
        detail["reason"] = reason
        logger.debug("Feintempo unveraendert: %s (%s)", reason, file_path)
        return bpm

    try:
        sample_rate, track_duration, prior = float(sr), float(duration), float(bpm)
        audio = np.asarray(y)
        if (
            not np.isfinite(sample_rate) or sample_rate <= 300
            or not sample_rate.is_integer()
            or not np.isfinite(track_duration) or track_duration <= 0
            or not np.isfinite(prior) or prior <= 0
            or audio.ndim != 1 or np.iscomplexobj(audio)
            or not np.all(np.isfinite(audio))
        ):
            return retain("invalid_input")
        sample_rate = int(sample_rate)
        training_end = TEMPO_TRAINING_SECONDS * sample_rate
        if len(audio) < training_end:
            return retain("insufficient_training")
        width = int(_BEATGRID_WINDOW_SECONDS * sample_rate)
        starts = (
            training_end,
            math.floor((track_duration / 2.0 - _BEATGRID_WINDOW_SECONDS / 2.0) * sample_rate),
            math.floor((track_duration - _BEATGRID_WINDOW_SECONDS) * sample_rate),
        )
        total_samples = math.floor(track_duration * sample_rate)
        # Feste Fensterpolitik der 16 synthetischen Tempo-Familien und des
        # Originalfalls You Never Alone (2026-10-13): keine Trainingssamples
        # als Gegenprobe wiederverwenden. Diese Anordnung benoetigt >=112 s.
        previous_end = training_end
        for start in starts:
            if start < previous_end or start + width > total_samples:
                return retain("overlapping_windows")
            previous_end = start + width

        fit_detail = {}
        candidate = estimate_fine_tempo(
            audio[:training_end], sample_rate, prior, track_duration,
            factor_candidates=ID3_BPM_FACTOR_CANDIDATES, diagnostics=fit_detail,
        )
        detail["training"] = fit_detail
        if candidate is None:
            return retain("candidate_rejected")
        candidate_bpm, candidate_phase = candidate
        if (not np.isfinite(candidate_bpm) or candidate_bpm <= 0
                or not np.isfinite(candidate_phase)
                or not 0 <= candidate_phase < 60.0 / candidate_bpm):
            return retain("candidate_rejected")

        windows = []
        for start in starts:
            if start + width <= len(audio):
                window = audio[start:start + width]
            else:
                try:
                    window, loaded_sr = _load_analysis_audio(
                        file_path, sr=sample_rate,
                        offset=start / sample_rate,
                        duration=_BEATGRID_WINDOW_SECONDS,
                    )
                except (OSError, RuntimeError, ValueError, sf.LibsndfileError) as error:
                    detail["error_type"] = type(error).__name__
                    return retain("decode_error")
                if loaded_sr != sample_rate:
                    return retain("invalid_window")
            window = np.asarray(window)
            if (window.ndim != 1 or len(window) != width or np.iscomplexobj(window)
                    or not np.all(np.isfinite(window))):
                return retain("invalid_window")
            windows.append((start / sample_rate, window))

        prior_phase, prior_lock = _beat_phase_from_fold(
            np.asarray(audio[:training_end], dtype=np.float64), sample_rate, 60.0 / prior,
        )
        detail["prior_status"] = "unverifiable"
        if (prior_phase is not None and np.isfinite(prior_phase)
                and 0 <= prior_phase < 60.0 / prior
                and np.isfinite(prior_lock) and prior_lock >= BEATGRID_MIN_FOLD_LOCK):
            prior_validation = validate_beatgrid_windows(
                windows, sample_rate, prior, anchor=prior_phase,
            )
            detail["prior_status"] = prior_validation.status
            if prior_validation.status == "verified":
                return retain("prior_verified")
        validation = validate_beatgrid_windows(
            windows, sample_rate, candidate_bpm, anchor=candidate_phase,
        )
        detail["candidate_status"] = validation.status
        if validation.status != "verified":
            return retain("candidate_grid_rejected")
        detail["reason"] = "accepted"
        logger.info(
            "Feintempo am Audio bestaetigt: %.9f -> %.9f BPM, Restfehler %.3f ms (%s)",
            prior, candidate_bpm, validation.max_phase_error_ms, file_path,
        )
        return float(candidate_bpm)
    except (TypeError, ValueError, OverflowError, FloatingPointError, RuntimeError) as error:
        detail["error_type"] = type(error).__name__
        return retain("estimation_error")


def _validate_track_beatgrid(
    file_path: str,
    duration: float,
    bpm: float,
    anchor: float,
    *,
    grid_points: list[dict] | None = None,
    head_audio: np.ndarray | None = None,
    head_sr: int = 0,
    diagnostics: dict | None = None,
    window_starts=None,
    phase_method='bass_fold',
) -> BeatgridValidation:
    """Laedt bis zu drei getrennte Fenster und prueft deren reale Kickphase."""
    if diagnostics is not None:
        diagnostics["decode_failures"] = []
    span = min(_BEATGRID_WINDOW_SECONDS, max(1.0, float(duration)))
    raw_offsets = (
        0.0,
        max(0.0, float(duration) / 2.0 - span / 2.0),
        max(0.0, float(duration) - span),
    )
    offsets = tuple(dict.fromkeys(raw_offsets if window_starts is None else window_starts))
    if any(not math.isfinite(offset) or offset < 0 or offset+span > duration+1e-6 for offset in offsets):
        raise ValueError("Invalid beatgrid evidence window")
    windows: list[tuple[float, np.ndarray]] = []
    sample_rate = int(head_sr or 0)
    for index, offset in enumerate(offsets):
        try:
            if offset == 0 and head_audio is not None and sample_rate > 0:
                audio = np.asarray(head_audio)[: int(span * sample_rate)]
            else:
                audio, loaded_sr = _load_analysis_audio(
                    file_path, sr=sample_rate or None, offset=offset,
                    duration=span,
                )
                sample_rate = int(loaded_sr)
        except (OSError, RuntimeError, ValueError, sf.LibsndfileError) as error:
            if diagnostics is not None:
                diagnostics["decode_failures"].append({
                    "offset_seconds": float(offset), "reason": "decode_error",
                })
            logger.warning("Beatgrid-Fenster %.2fs nicht lesbar: %s", offset, error)
            continue
        windows.append((offset, np.asarray(audio)))
    grid_times = (
        [float(point["time"]) for point in grid_points]
        if grid_points is not None else None
    )
    return validate_beatgrid_windows(
        windows, sample_rate, bpm, anchor=anchor, grid_times=grid_times,
        collect_diagnostics=True, phase_method=phase_method,
    )

def _estimate_audio_downbeat(
    y: np.ndarray, sr: int, bpm: float, *, file_path: str, duration: float,
    diagnostics: dict,
) -> tuple[float, float]:
    """Bei langem Tracker-Drift drei lokale Taktanker unabhaengig vergleichen."""
    original = _estimate_audio_downbeat_full(
        y, sr, bpm, file_path=file_path, duration=duration, diagnostics=diagnostics,
    )
    if (original[1] >= DOWNBEAT_RELIABLE_MIN
            or 'fold_alignment' not in (diagnostics.get('reason'), diagnostics.get('retry_reason'))
            or not math.isfinite(duration) or duration < 5 * _BEATGRID_WINDOW_SECONDS
            or not math.isfinite(bpm) or bpm <= 0 or sr <= 0):
        return original
    span = _BEATGRID_WINDOW_SECONDS
    bar = METER * 60. / bpm
    candidates = []
    local_diagnostics = []
    try:
        for fraction in (.2, .5, .8):
            first = int((duration * fraction - span / 2.) * sr)
            count = int(span * sr)
            start = first / sr
            if first + count <= len(y):
                audio = y[first:first + count]
            else:
                audio, loaded_sr = _load_analysis_audio(
                    file_path, sr=sr, offset=start, duration=span,
                    res_type='soxr_hq',
                )
                if loaded_sr != sr:
                    return original
            if len(audio) != count or not np.isfinite(audio).all():
                return original
            details = {}
            anchor, confidence = estimate_first_downbeat(audio, sr, bpm,
                diagnostics=details, _fixed_bpm=True, _allow_metric_retry=False)
            if (not math.isfinite(anchor) or not math.isfinite(confidence)
                    or confidence < DOWNBEAT_RELIABLE_MIN or confidence >= 1.):
                return original
            candidates.append(((anchor + start) % bar, confidence))
            local_diagnostics.append(details)
        anchor = candidates[0][0]
        if any(abs((value-anchor+bar/2) % bar-bar/2) > EXACT_BEAT_SYNC_TOLERANCE_SECONDS
               for value, _ in candidates[1:]):
            return original
        validation = _validate_track_beatgrid(file_path, duration, bpm, anchor,
                                              head_audio=y, head_sr=sr)
        if validation.status != 'verified':
            return original
        diagnostics.update(local_diagnostics[0])
        diagnostics['retry_reason'] = 'fold_alignment'
        logger.info('Lokaler Downbeat-Retry: drei disjunkte Taktanker und Gesamtgrid bestaetigt')
        return anchor, min(confidence for _, confidence in candidates)
    except Exception as error:
        logger.warning('Lokaler Downbeat-Retry verworfen: %s', type(error).__name__)
        return original


def _estimate_audio_downbeat_full(
    y: np.ndarray, sr: int, bpm: float, *, file_path: str, duration: float,
    diagnostics: dict,
) -> tuple[float, float]:
    """Fremde Tracker-Metrik nur nach strenger Audiopruefung korrigieren."""
    original = estimate_first_downbeat(
        y, sr, bpm, diagnostics=diagnostics, _allow_metric_retry=False,
    )
    if diagnostics.get("reason") != "incommensurate":
        return original

    # Fresh30 (2026-10-13): 9/30 Tracker-Raster widersprachen dem Zieltempo.
    # Explizites BPM allein rettete 3 Konfidenzen, aber nur 1 bestand auch
    # die unveraenderte Drei-Fenster-Pruefung. Daher beide Bedingungen.
    retry_diagnostics = {}
    candidate = estimate_first_downbeat(
        y, sr, bpm, diagnostics=retry_diagnostics, _fixed_bpm=True,
        _allow_metric_retry=False,
    )
    if candidate[1] < DOWNBEAT_RELIABLE_MIN:
        logger.debug("Downbeat-Tempo-Retry verworfen: Konfidenz %.3f", candidate[1])
        retry_reason = retry_diagnostics.get("reason")
        if retry_reason in DOWNBEAT_REASONS:
            diagnostics["retry_reason"] = retry_reason
        return original
    validation = _validate_track_beatgrid(
        file_path, duration, bpm, candidate[0], head_audio=y, head_sr=sr,
    )
    if validation.status != "verified":
        logger.debug(
            "Downbeat-Tempo-Retry verworfen: Grid %s, Restfehler %.3f ms",
            validation.status, validation.max_phase_error_ms,
        )
        retry_reason = validation.reason
        if retry_reason in GRID_REASONS:
            diagnostics["retry_reason"] = retry_reason
        return original
    logger.info(
        "Downbeat-Tempo-Retry am Audio bestaetigt: %.2f BPM, Konfidenz %.3f, "
        "Restfehler %.3f ms", bpm, candidate[1], validation.max_phase_error_ms,
    )
    # Erfolgreiche Retries uebernehmen ihre Messung; abgewiesene Retries
    # behalten den Hauptgrund und persistieren den separaten retry_reason.
    diagnostics.update(retry_diagnostics)
    return candidate


# Reverse mapping: Camelot code → (Note, Mode)
REVERSE_CAMELOT_MAP = {v: k for k, v in CAMELOT_MAP.items()}


@dataclass
class FeatureCache:
    """Lazy, track-lokaler Cache für wiederverwendete Librosa-Features.

    Die Cache-Einträge werden erst beim ersten Zugriff berechnet. Dadurch
    bleibt der bestehende Fast-Path leichtgewichtig, während Struktur-,
    Fingerprint- und Track-Feature-Pfade dieselben Matrizen teilen können.
    Module außerhalb des Ownership-Scope bleiben bewusst über ihre alten
    Signaturen angebunden.
    """

    y: np.ndarray
    sr: int
    _mfcc: dict[tuple[int, int | None], np.ndarray] = field(
        default_factory=dict, init=False, repr=False
    )
    _rms: dict[int, np.ndarray] = field(default_factory=dict, init=False, repr=False)
    _stft: dict[tuple[int, int], np.ndarray] = field(
        default_factory=dict, init=False, repr=False
    )
    _chroma: dict[int | None, np.ndarray] = field(
        default_factory=dict, init=False, repr=False
    )
    _centroid: dict[int, np.ndarray] = field(
        default_factory=dict, init=False, repr=False
    )
    _flatness: dict[int | None, np.ndarray] = field(
        default_factory=dict, init=False, repr=False
    )
    _contrast: dict[int | None, np.ndarray] = field(
        default_factory=dict, init=False, repr=False
    )
    _onset: dict[int | None, np.ndarray] = field(
        default_factory=dict, init=False, repr=False
    )
    _hpss: tuple[np.ndarray, np.ndarray] | None = field(
        default=None, init=False, repr=False
    )

    def fenster(self, max_samples: int) -> "FeatureCache":
        """Abgeleiteter Cache ueber die ersten `max_samples` Samples.

        Warum ueberhaupt: Fast-Path und Vollpfad laden verschieden lange
        Signale und rechnen dieselben Merkmalsfunktionen darauf. Das Ergebnis
        haengt damit daran, ob Rekordbox-Metadaten vorliegen -- und genau
        diese Werte vergleicht das Scoring miteinander (D8).

        Ist das Signal nicht laenger als das Fenster, kommt das ELTERNOBJEKT
        selbst zurueck. Der Fast-Path bekommt es heute, weil
        `FEATURE_WINDOW_DURATION` GLEICH `LIBROSA_FAST_PATH_DURATION` ist --
        `config.py` koppelt beide ueber `min`, beide stehen auf 360. Nicht
        "nie groesser als": der `return self`-Zweig verlangt ein Fenster, das
        MINDESTENS so lang ist wie das geladene Signal. Stiege die Ladegrenze
        ueber 360, entstuende auch im Fast-Path ein Kindcache -- fachlich
        folgenlos, weil das Kind denselben Ausschnitt frisch rechnet. Was
        wirklich zaehlt, ist `FEATURE_WINDOW_DURATION <= `
        `LIBROSA_FAST_PATH_DURATION`; das sichert
        `TestMerkmalsfensterKopplung` in tests/test_config.py.

        Sonst entsteht ein LEERER Cache auf dem Ausschnitt. Er rechnet jede
        Matrix selbst und ist damit wertgleich zu einer Rechnung auf
        `self.y[:max_samples]` -- nicht gemessen, sondern dadurch, dass
        dieselbe Funktion mit denselben Parametern auf denselben Samples
        laeuft. Ueber das Verhaeltnis der beiden PFADE zueinander sagt das
        nichts: was Fast-Path und Vollpfad laden, entscheidet `librosa.load`.

        Frueher wurden hier die Matrizen des Elternteils zugeschnitten. Das
        war toter Code -- an beiden Aufrufstellen steht `fenster()` direkt
        hinter `FeatureCache(y, sr)`, der Elterncache ist also leer, und der
        Schnitt lief ueber leere Dicts. Er trug dafuer einen echten Fehler:
        `chroma_stft` schaetzt `tuning` global ueber das ganze Signal, ein
        geschnittenes Chroma haette also zu einer anderen Stimmung gehoert
        als das Fenster (Journal 2026-09-05).
        """
        if max_samples >= len(self.y):
            return self
        return FeatureCache(y=self.y[:max_samples], sr=self.sr)

    def get_mfcc(self, n_mfcc: int = 13, hop_length: int | None = None) -> np.ndarray:
        key = (n_mfcc, hop_length)
        if key not in self._mfcc:
            kwargs = {"y": self.y, "sr": self.sr, "n_mfcc": n_mfcc}
            if hop_length is not None:
                kwargs["hop_length"] = hop_length
            self._mfcc[key] = librosa.feature.mfcc(**kwargs)
        return self._mfcc[key]

    def get_rms(self, hop_length: int = HOP_LENGTH) -> np.ndarray:
        if hop_length not in self._rms:
            self._rms[hop_length] = librosa.feature.rms(
                y=self.y, hop_length=hop_length
            )
        return self._rms[hop_length]

    def get_stft_magnitude(
        self, n_fft: int = 2048, hop_length: int = HOP_LENGTH
    ) -> np.ndarray:
        key = (n_fft, hop_length)
        if key not in self._stft:
            self._stft[key] = np.abs(
                librosa.stft(self.y, n_fft=n_fft, hop_length=hop_length)
            )
        return self._stft[key]

    def get_chroma(self, hop_length: int | None = None) -> np.ndarray:
        if hop_length not in self._chroma:
            kwargs = {"y": self.y, "sr": self.sr}
            if hop_length is not None:
                kwargs["hop_length"] = hop_length
            self._chroma[hop_length] = librosa.feature.chroma_stft(**kwargs)
        return self._chroma[hop_length]

    def get_spectral_centroid(self, hop_length: int = HOP_LENGTH) -> np.ndarray:
        if hop_length not in self._centroid:
            self._centroid[hop_length] = librosa.feature.spectral_centroid(
                y=self.y, sr=self.sr, hop_length=hop_length
            )
        return self._centroid[hop_length]

    def get_spectral_flatness(self, hop_length: int | None = None) -> np.ndarray:
        if hop_length not in self._flatness:
            kwargs = {"y": self.y}
            if hop_length is not None:
                kwargs["hop_length"] = hop_length
            self._flatness[hop_length] = librosa.feature.spectral_flatness(**kwargs)
        return self._flatness[hop_length]

    def get_spectral_contrast(self, hop_length: int | None = None) -> np.ndarray:
        if hop_length not in self._contrast:
            kwargs = {"y": self.y, "sr": self.sr}
            if hop_length is not None:
                kwargs["hop_length"] = hop_length
            self._contrast[hop_length] = librosa.feature.spectral_contrast(**kwargs)
        return self._contrast[hop_length]

    def get_onset_strength(self, hop_length: int | None = None) -> np.ndarray:
        if hop_length not in self._onset:
            kwargs = {"y": self.y, "sr": self.sr}
            if hop_length is not None:
                kwargs["hop_length"] = hop_length
            self._onset[hop_length] = librosa.onset.onset_strength(**kwargs)
        return self._onset[hop_length]

    def get_hpss(self) -> tuple[np.ndarray, np.ndarray]:
        if self._hpss is None:
            self._hpss = librosa.effects.hpss(self.y)
        return self._hpss


def analyze_frequency_bands(
    y: np.ndarray, sr: int, feature_cache: FeatureCache | None = None
) -> tuple[float, float, float]:
    if y is None or len(y) == 0:
        return 0.0, 0.0, 0.0
    # MED-Fix: NaN/Inf abfangen (librosa.stft wirft sonst ParameterError und
    # reisst den ganzen Advanced-Analysis-Block), konsistent mit den uebrigen
    # Feature-Funktionen (generate_timbre_fingerprint etc.).
    if not np.all(np.isfinite(y)):
        y = np.nan_to_num(y)
    S = (
        feature_cache.get_stft_magnitude(hop_length=HOP_LENGTH)
        if feature_cache is not None
        else np.abs(librosa.stft(y, hop_length=HOP_LENGTH))
    )
    freqs = librosa.fft_frequencies(sr=sr)
    bass_mask = (freqs >= 20) & (freqs <= 200)
    mids_mask = (freqs > 200) & (freqs <= 4000)
    highs_mask = (freqs > 4000)
    def get_e(mask):
        if not np.any(mask):
            return 0.0
        return float(np.sqrt(np.mean(S[mask]**2)))
    b, m, h = get_e(bass_mask), get_e(mids_mask), get_e(highs_mask)
    t = b + m + h + 1e-6
    return round(b/t*100, 1), round(m/t*100, 1), round(h/t*100, 1)

# Sektions-Label, die verlaesslich Drums tragen. Nur ueber diese wird das
# Groove-Muster gefaltet (Spec 5.1) — ein Breakdown ohne Drums oder ein
# Ambient-Intro wuerde das Muster sonst verwaessern.
BEAT_SECTION_LABELS = ("main", "drop")


def _beat_sektionen(sections: list | None) -> list[tuple[float, float]]:
    """Sammelt die Zeitbereiche der Sektionen mit Beat."""
    if not sections:
        return []
    bereiche = []
    for sec in sections:
        if not isinstance(sec, dict):
            continue
        if sec.get('label') not in BEAT_SECTION_LABELS:
            continue
        start_s = sec.get('start_time')
        end_s = sec.get('end_time')
        if start_s is None or end_s is None or end_s <= start_s:
            continue
        bereiche.append((float(start_s), float(end_s)))
    return bereiche


def compute_groove_fields(
    y: np.ndarray,
    sr: int,
    bpm: float,
    first_downbeat: float,
    downbeat_confidence: float,
    feature_cache: FeatureCache | None = None,
    sections: list | None = None,
) -> GrooveFeatures:
    """Groove-Features berechnen, aber nur auf belastbarem Taktraster.

    Ein Muster auf einem erfundenen Raster ist schlechter als gar keins. Eine
    falsche TAKT-Phase verwischt das Muster naemlich nicht, sie ROTIERT es um
    4, 8 oder 12 Slots — der denkbar schlechteste Fehler fuer einen
    Fingerabdruck, dessen einziger Zweck der Vergleich zweier Tracks ist.

    Die Schwelle ist DOWNBEAT_RELIABLE_MIN (0.30) aus downbeat.py, kalibriert
    an 35 Tracks mit Rekordbox-ANLZ-Beatgrid als Ground Truth: ab 0.30 liegt
    der Sub-Beat-Fehler im Median bei 16 ms (Max 43 ms), waehrend die Zone
    <= 0.241 ALLE Ausreisser (83 / 153 / 188 ms) enthaelt. Dieselbe Schwelle
    entscheidet bereits in transition_renderer.py und main.py ueber das
    Beat-Phase-Alignment.
    """
    if downbeat_confidence < DOWNBEAT_RELIABLE_MIN or bpm <= 0:
        return GrooveFeatures()
    try:
        return extract_groove(
            y, sr, bpm, first_downbeat, feature_cache=feature_cache,
            beat_sektionen=_beat_sektionen(sections),
        )
    except Exception as exc:  # Groove darf die Analyse nie kippen
        logger.warning(f"Groove-Extraktion fehlgeschlagen: {exc}")
        return GrooveFeatures()

def analyze_rhythm_complexity(
    y: np.ndarray,
    sr: int,
    feature_cache: FeatureCache | None = None,
    sample_range: tuple[int, int] | None = None,
) -> tuple[float, float]:
    """Perkussiv-Anteil und spektrale Flachheit.

    sample_range (PERF 2026-08-14): Sektions-Grenzen in Samples, bezogen auf das
    Signal des feature_cache. Damit wird die HPSS EINMAL fuer den ganzen Track
    berechnet und pro Sektion nur noch geschnitten, statt sie je Sektion neu zu
    rechnen (gemessen: 11 Aufrufe = 11,5 s pro Track). Der Perkussiv-Anteil
    weicht dadurch leicht vom Segment-HPSS ab, weil der Medianfilter mehr
    Kontext sieht — an den Sektionsraendern ist das genauer, nicht ungenauer.
    """
    if y is None or len(y) == 0:
        return 0.0, 0.0
    # MED-Fix: NaN/Inf abfangen (librosa.effects.hpss wirft sonst ParameterError).
    if not np.all(np.isfinite(y)):
        y = np.nan_to_num(y)

    cached_hpss = None
    if feature_cache is not None:
        if sample_range is not None:
            start, end = sample_range
            full_h, full_p = feature_cache.get_hpss()
            if 0 <= start < end <= len(full_h):
                cached_hpss = (full_h[start:end], full_p[start:end])
        elif len(feature_cache.y) == len(y):
            cached_hpss = feature_cache.get_hpss()

    y_h, y_p = cached_hpss if cached_hpss is not None else librosa.effects.hpss(y)

    pe = np.sqrt(np.mean(y_p**2))
    he = np.sqrt(np.mean(y_h**2))
    pr = pe / (pe + he + 1e-6)

    # Die Flachheit des Caches gilt fuer den GANZEN Track — fuer eine Sektion
    # muss sie auf deren Ausschnitt gerechnet werden.
    if (
        feature_cache is not None
        and sample_range is None
        and len(feature_cache.y) == len(y)
    ):
        flatness = feature_cache.get_spectral_flatness()
    else:
        flatness = librosa.feature.spectral_flatness(y=y)
    sf = np.mean(flatness)
    return round(float(pr), 3), round(float(sf), 3)

def generate_timbre_fingerprint(
    y: np.ndarray, sr: int, feature_cache: FeatureCache | None = None
) -> list[float]:
    if y is None or len(y) == 0:
        return []
    # Handle NaN/Inf values
    if not np.all(np.isfinite(y)):
        y = np.nan_to_num(y)
    mfccs = (
        feature_cache.get_mfcc(n_mfcc=13)
        if feature_cache is not None
        else librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    )
    return [round(float(v), 3) for v in np.mean(mfccs, axis=1)]

# Krumhansl-Schmuckler key profiles (simplified)
# C, C#, D, D#, E, F, F#, G, G#, A, A#, B
MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]

NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def get_key_with_confidence(
    chroma_vector: np.ndarray,
) -> tuple[str, str, float, float, str, str]:
    """Bestimmt die Tonart per Krumhansl-Schmuckler-Korrelation MIT Konfidenz.

    Key-Confidence-Feature 2026-07-17 nach dem Essentia-Muster (key.cpp):
      - strength: absolute Pearson-Korrelation des Gewinners (passt das
        Profil ueberhaupt?)
      - margin: (max - max2) / max — relative Erst-zu-Zweit-Marge (wie
        eindeutig ist der Sieg?)
    Beide zusammen sind die publizierte Standard-Metrik; der Zweitkandidat
    wird mitgeliefert, weil "nahe" Fehler (Quinte, relative Dur/Moll)
    fuers Harmonic Mixing harmlos sind (MIREX-Fehlerklassen).

    Returns:
        (note, mode, strength, margin, second_note, second_mode)
    """
    # Cosine-Similarity statt Pearson-Korrelation (Validierungs-Iteration
    # 2026-07-17): Sha'ath (KeyFinder-Thesis, Kap. 4.3.6) zeigte Cosine auf
    # EDM als konsistent treffsicherer; empirisch gegen die Beatport-
    # Ground-Truth gemessen (tools/validation_run.py --no-rekordbox).
    chroma = np.asarray(chroma_vector, dtype=float)
    chroma_norm = float(np.linalg.norm(chroma))
    major = np.asarray(MAJOR_PROFILE, dtype=float)
    minor = np.asarray(MINOR_PROFILE, dtype=float)
    major_norm = float(np.linalg.norm(major))
    minor_norm = float(np.linalg.norm(minor))

    correlations: list[tuple[float, str, str]] = []
    for i in range(12):
        rolled = np.roll(chroma, -i)
        if chroma_norm > 1e-9:
            major_corr = float(np.dot(rolled, major) / (chroma_norm * major_norm))
            minor_corr = float(np.dot(rolled, minor) / (chroma_norm * minor_norm))
        else:
            major_corr = minor_corr = 0.0
        correlations.append((major_corr, NOTES[i], "Major"))
        correlations.append((minor_corr, NOTES[i], "Minor"))

    correlations.sort(key=lambda item: item[0], reverse=True)
    best_corr, key_note, key_mode = correlations[0]
    second_corr, second_note, second_mode = correlations[1]

    # AUDIT-FIX F02 (2026-07-24): "strength" ist jetzt ein KONTRAST-Wert
    # (z-Score des Gewinners gegen alle 24 Kandidaten), nicht der rohe
    # Cosine-Wert. Cosine ueber nicht-zentrierte, durchweg positive Chroma
    # komprimiert alle Kandidaten auf ~0,94-1,00 — der rohe Wert war damit
    # nicht-diskriminierend (auch eine FLACHE Chroma liefert ~0,95). Der
    # z-Score trennt "ein Profil sticht heraus" (peaked chroma) sauber von
    # "alle gleich" (flache/stille Chroma -> ~0). Die Key-AUSWAHL bleibt
    # cosine-basiert (unveraendert). margin bleibt der relative Cosine-Abstand.
    all_corrs = np.array([c[0] for c in correlations], dtype=float)
    finite = all_corrs[np.isfinite(all_corrs)]
    if finite.size >= 2:
        mean_all = float(np.mean(finite))
        std_all = float(np.std(finite))
        contrast = (best_corr - mean_all) / std_all if std_all > 1e-9 else 0.0
    else:
        contrast = 0.0

    margin = 0.0
    if np.isfinite(second_corr) and abs(best_corr) > 1e-9:
        margin = (best_corr - second_corr) / abs(best_corr)

    return (
        key_note,
        key_mode,
        round(max(0.0, contrast), 4),
        round(max(0.0, margin), 4),
        second_note,
        second_mode,
    )


def get_key(chroma_vector: np.ndarray) -> tuple[str, str]:
    """Determines the key from a chroma vector by correlating with major/minor profiles."""
    note, mode, _, _, _, _ = get_key_with_confidence(chroma_vector)
    return note, mode


def key_confidence_score(
    strength: float, margin: float,
    key_note: str, key_mode: str,
    second_note: str, second_mode: str,
) -> float:
    """Verdichtet Kontrast/margin zu einer 0-1-Konfidenz fuers Harmonic Mixing.

    AUDIT-FIX F02 (2026-07-24): auf die tatsaechlichen Wertebereiche kalibriert.
    `strength` ist jetzt ein z-Score-KONTRAST (siehe get_key_with_confidence),
    typisch ~2-4 fuer einen klaren Sieger, ~0-1 fuer flache Chroma. `margin`
    ist der relative Cosine-Abstand, real ~0,005-0,04 (nicht 0,05+ wie die
    alten Pearson-Schwellen annahmen — dadurch war der "sicher"-Zweig frueher
    UNERREICHBAR und praktisch jeder Track bekam 0,4).

    Sicher (>=0,8): klarer Kontrast UND deutliche Marge.
    Mittel (0,5): knapp, aber Zweitkandidat ist ein kompatibler Camelot-Nachbar.
    Unsicher (<=0,4): flache/mehrdeutige Chroma.
    """
    # Kontrast in [0..~5] auf [0..1] abbilden (2,5 sigma = voll sicher)
    contrast_norm = min(1.0, max(0.0, strength / 2.5))

    if strength >= 2.0 and margin >= 0.02:
        return round(max(0.8, contrast_norm), 3)

    # Zweitkandidat harmonisch benachbart? (Camelot-Distanz via CAMELOT_MAP)
    first_code = CAMELOT_MAP.get((key_note, key_mode), "")
    second_code = CAMELOT_MAP.get((second_note, second_mode), "")
    if first_code and second_code:
        num1, let1 = get_camelot_components(first_code)
        num2, let2 = get_camelot_components(second_code)
        if num1 and num2:
            dist = min(abs(num1 - num2), 12 - abs(num1 - num2))
            relative = num1 == num2 and let1 != let2
            quint = dist == 1 and let1 == let2
            if (relative or quint) and strength >= 1.0:
                # Verwechslung waere ein kompatibler Nachbar — quasi-sicher
                return round(max(0.5, contrast_norm * 0.8), 3)

    if strength >= 1.0 and margin >= 0.01:
        # erkennbarer, aber nicht eindeutiger Sieger
        return round(min(0.6, max(0.45, contrast_norm)), 3)

    return round(min(contrast_norm, 0.4), 3)


def calculate_lufs(y: np.ndarray, sr: int) -> float:
    """Integrated Loudness nach ITU-R BS.1770-4 / EBU R128 in LUFS.

    LUFS-Feature 2026-07-17: pyloudnorm mit "DeMan"-Filterklasse (laut
    Paper voll BS.1770-konform bei jeder Samplerate). Die Gain-Angleichung
    arbeitet rein relativ zwischen zwei Tracks (dj_brain._gain_advice gegen
    GAIN_DIFF_SHOW_DB und GAIN_DIFF_WARN_DB); einen absoluten Referenzpegel
    gibt es nicht.

    Returns:
        Integrated LUFS (negativ, z.B. -9.5) oder 0.0 als Sentinel
        (unbekannt/Messung fehlgeschlagen — 0 LUFS kommt bei Musik nicht vor).
    """
    if y is None or sr <= 0 or len(y) < sr:  # mind. 1s (Gating braucht Bloecke)
        return 0.0
    try:
        import pyloudnorm as pyln

        meter = pyln.Meter(sr, filter_class="DeMan")
        lufs = float(meter.integrated_loudness(np.asarray(y, dtype=np.float64)))
        if not np.isfinite(lufs) or lufs >= 0.0 or lufs < -70.0:
            return 0.0
        return round(lufs, 2)
    except Exception as e:
        logger.warning(f"LUFS-Messung fehlgeschlagen: {e}")
        return 0.0


def calculate_file_lufs(file_path: str) -> tuple[float, str, float, int, int]:
    """Misst LUFS blockweise über das vollständige native Mehrkanalprogramm.

    Returns:
        (lufs, status, coverage_seconds, channels, sample_rate)
    """
    try:
        import pyloudnorm as pyln

        # LUFS muss Quellrate und Quellkanäle messen. Der native Beat-Reader
        # resampelt auf 44,1 kHz und downmixt Mehrkanalton; er ist deshalb nur
        # Decoderfallback für Formate, die SoundFile nicht direkt streamen kann.
        try:
            source_info = sf.info(file_path)
            source_rate = int(source_info.samplerate)
            source_channels = int(source_info.channels)
            source_frames = int(source_info.frames)
            if source_rate <= 0 or source_channels <= 0 or source_frames <= 0:
                raise ValueError("Ungueltige SoundFile-Audiodimensionen")
            source_meter = pyln.Meter(source_rate, filter_class="DeMan")
            source_value = _integrated_loudness_from_blocks(
                file_path, source_info, source_meter,
            )
            source_coverage = source_frames / source_rate
            if (not np.isfinite(source_value) or source_value >= 0.0
                    or source_value < -70.0):
                return (0.0, "invalid", source_coverage,
                        source_channels, source_rate)
            return (round(source_value, 2), "complete", source_coverage,
                    source_channels, source_rate)
        except Exception as error:
            logger.debug("Quellformat nicht direkt fuer LUFS lesbar; gemeinsamer Reader-Fallback: %s", error)

        if os.path.splitext(file_path)[1].lower() in SUPPORTED_AUDIO_EXTENSIONS:
            from types import SimpleNamespace
            from .ai_models.native_audio_reader import NativeAudioStream
            try:
                with NativeAudioStream(file_path) as stream:
                    sample_rate = int(stream.samplerate)
                    channels = int(stream.channels)
                    frames = int(stream.frames)
                    info = SimpleNamespace(
                        samplerate=sample_rate, channels=channels, frames=frames
                    )
                    meter = pyln.Meter(sample_rate, filter_class="DeMan")
                    block_frames = max(sample_rate, sample_rate * 10)

                    def decoded_blocks():
                        remaining = frames
                        while remaining:
                            amount = min(remaining, block_frames)
                            yield stream.read(amount, dtype="float32", always_2d=True)
                            remaining -= amount

                    value = _integrated_loudness_from_blocks(
                        file_path, info, meter, blocks=decoded_blocks()
                    )
                coverage = frames / sample_rate if sample_rate > 0 else 0.0
                full_duration = _get_file_duration(file_path)
                status = (
                    "complete" if full_duration - coverage <= 1.0 / sample_rate
                    else "partial"
                )
                if not np.isfinite(value) or value >= 0.0 or value < -70.0:
                    return 0.0, "invalid", coverage, channels, sample_rate
                return round(value, 2), status, coverage, channels, sample_rate
            except Exception as error:
                logger.debug("Gemeinsamer Audio-Reader fuer LUFS nicht verfügbar; SoundFile-Fallback: %s", error)

        info = sf.info(file_path)
        sample_rate = int(info.samplerate)
        channels = int(info.channels)
        frames = int(info.frames)
        coverage = float(frames / sample_rate) if sample_rate > 0 else 0.0
        meter = pyln.Meter(sample_rate, filter_class="DeMan")
        value = _integrated_loudness_from_blocks(file_path, info, meter)
        if not np.isfinite(value) or value >= 0.0 or value < -70.0:
            return 0.0, "invalid", coverage, channels, int(sample_rate)
        return round(value, 2), "complete", coverage, channels, int(sample_rate)
    except Exception as error:
        logger.warning(f"Vollstaendige LUFS-Messung fehlgeschlagen: {error}")
        return 0.0, "error", 0.0, 0, 0


def _integrated_loudness_from_blocks(file_path: str, info, meter, *, blocks=None) -> float:
    """Berechnet BS.1770-Gating mit begrenztem Decode-Speicher.

    Die Filterzustände laufen über Chunk-Grenzen weiter. Für das Gating bleiben
    nur die 400-ms-Fenster und ein einzelnes Überlappungsfenster im Speicher;
    die Semantik entspricht damit ``pyloudnorm.Meter.integrated_loudness``.
    """
    from scipy.signal import lfilter

    sample_rate = int(info.samplerate)
    channels = int(info.channels)
    total_frames = int(info.frames)
    block_frames = int(meter.block_size * sample_rate)
    step_seconds = meter.block_size * (1.0 - meter.overlap)
    if sample_rate <= 0 or channels <= 0 or channels > 5 or total_frames < block_frames:
        return float("nan")

    # AUDIT-FIX 2026-08-14: Die Blockzahl wurde mit np.round aufgerundet. Der
    # letzte 400-ms-Block passte dann bei vielen Dateien nicht mehr vollstaendig
    # in das Signal, die Fuell-Schleife brach ab und die strikte Pruefung
    # `next_block != num_blocks` weiter unten lieferte NaN -> lufs_status
    # "invalid". Gemessen betraf das 24 von 52 Tracks der Produktivbibliothek,
    # ohne dass irgendwo ein Fehler sichtbar wurde.
    # Jetzt wird abgerundet, sodass JEDER gezaehlte Block vollstaendig im
    # Signal liegt. Hoechstens ein angebrochener Rest-Block am Dateiende
    # entfaellt — BS.1770 verwirft unvollstaendige Fenster ohnehin.
    step_frames = step_seconds * sample_rate
    if step_frames <= 0:
        return float("nan")
    num_blocks = int((total_frames - block_frames) // step_frames) + 1
    if num_blocks <= 0:
        return float("nan")

    # pyloudnorm verwendet dieselben DeMan-Koeffizienten; lfilter mit zi
    # erhält zusätzlich den Filterzustand zwischen den SoundFile-Chunks.
    filter_stages = list(meter._filters.values())
    filter_states = [np.zeros((channels, 2), dtype=np.float64) for _ in filter_stages]
    z = np.zeros((channels, num_blocks), dtype=np.float64)
    pending = np.empty((0, channels), dtype=np.float64)
    pending_start = 0
    next_block = 0
    read_frames = 0
    stream_block_frames = max(block_frames, int(sample_rate * 10.0))

    source_blocks = blocks if blocks is not None else sf.blocks(
        file_path, blocksize=stream_block_frames, dtype="float32", always_2d=True
    )
    for chunk in source_blocks:
        filtered = np.asarray(chunk, dtype=np.float64)
        for stage_index, stage in enumerate(filter_stages):
            for channel in range(channels):
                filtered[:, channel], filter_states[stage_index][channel] = lfilter(
                    stage.b,
                    stage.a,
                    filtered[:, channel],
                    zi=filter_states[stage_index][channel],
                )

        pending = np.concatenate((pending, filtered), axis=0)
        read_frames += len(filtered)
        while next_block < num_blocks:
            start = int(next_block * step_seconds * sample_rate)
            end = start + block_frames
            if end > read_frames:
                break
            local_start = start - pending_start
            window = pending[local_start:local_start + block_frames]
            z[:, next_block] = np.mean(window * window, axis=0)
            next_block += 1

            next_start = int(next_block * step_seconds * sample_rate)
            discard = next_start - pending_start
            if discard > 0:
                pending = pending[discard:]
                pending_start = next_start

    if next_block != num_blocks:
        return float("nan")

    gains = np.array([1.0, 1.0, 1.0, 1.41, 1.41], dtype=np.float64)
    gains = gains[:channels]
    with np.errstate(divide="ignore", invalid="ignore"):
        loudness = -0.691 + 10.0 * np.log10(np.sum(gains[:, None] * z, axis=0))
    absolute = loudness >= -70.0
    if not np.any(absolute):
        return float("nan")

    gated_z = np.mean(z[:, absolute], axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        relative_threshold = -0.691 + 10.0 * np.log10(np.sum(gains * gated_z)) - 10.0
    relative = absolute & (loudness > relative_threshold)
    if not np.any(relative):
        return float("nan")

    final_z = np.nan_to_num(np.mean(z[:, relative], axis=1))
    with np.errstate(divide="ignore", invalid="ignore"):
        return float(-0.691 + 10.0 * np.log10(np.sum(gains * final_z)))


def _get_file_duration(file_path: str) -> float:
    """Liest MP3-Dauer vom gemeinsamen Reader, sonst Container-Metadaten."""
    suffix = os.path.splitext(file_path)[1].lower()
    if suffix == ".mp3":
        try:
            from .ai_models.native_audio_reader import NativeAudioStream
            with NativeAudioStream(file_path) as source:
                duration = len(source) / source.samplerate
            if math.isfinite(duration) and duration > 0:
                return float(duration)
        except Exception as error:
            logger.debug(f"Gemeinsamer Reader lieferte keine Dateidauer: {error}")
    try:
        info = sf.info(file_path)
        if info.samplerate > 0:
            return float(info.frames / info.samplerate)
    except (OSError, RuntimeError, ValueError) as error:
        logger.debug(f"SoundFile-Dauer nicht verfügbar: {error}")
    from .audio_decoder import configure_audioread_ffmpeg
    configure_audioread_ffmpeg()
    return float(librosa.get_duration(path=file_path))


def _load_analysis_audio(
    file_path: str,
    *,
    duration: float,
    offset: float = 0.0,
    sr: int | None = 22050,
    res_type: str = "soxr_hq",
) -> tuple[np.ndarray, int]:
    """Lädt unterstützte Formate ausschließlich über den gemeinsamen Reader."""
    suffix = os.path.splitext(file_path)[1].lower()
    from .ai_models.native_audio_reader import MAX_SECONDS, NativeAudioStream

    if suffix not in SUPPORTED_AUDIO_EXTENSIONS:
        from .audio_decoder import configure_audioread_ffmpeg
        configure_audioread_ffmpeg()
        return librosa.load(
            file_path, sr=sr, mono=True, offset=offset, duration=duration,
            res_type=res_type,
        )
    if (offset < 0 or duration <= 0 or offset + duration > MAX_SECONDS):
        raise ValueError("Analysefenster außerhalb des gemeinsamen Readerlimits")

    with NativeAudioStream(file_path, duration=duration, offset=offset) as stream:
        audio = stream.read(stream.frames, dtype="float32", always_2d=True)
        source_rate = stream.samplerate
    if audio.ndim != 2 or not 1 <= audio.shape[1] <= 2 or not len(audio):
        raise ValueError("Audio-Reader lieferte kein gueltiges Analysefenster")
    mono = audio[:, 0] if audio.shape[1] == 1 else np.mean(audio, axis=1, dtype=np.float32)
    target_rate = 22050 if sr is None else int(sr)
    if target_rate <= 0:
        target_rate = 22050
    if source_rate != target_rate:
        mono = librosa.resample(
            mono, orig_sr=source_rate, target_sr=target_rate, res_type=res_type
        )
    expected_frames = int(round(duration * target_rate))
    return np.ascontiguousarray(mono[:expected_frames], dtype=np.float32), target_rate


def calculate_energy(y: np.ndarray) -> int:
    """Calculates the overall energy of a track and scales it to 0-100."""
    if y is None or len(y) == 0:
        return 0

    y = np.asarray(y)
    if y.size == 0:
        return 0

    # Replace NaN/inf with finite values and clamp extremes to avoid overflow
    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)
    y = np.clip(y, -1.0, 1.0)

    rms_energy = float(np.sqrt(np.mean(y**2))) if y.size else 0.0
    if not np.isfinite(rms_energy):
        rms_energy = 0.0

    energy_scaled = float(np.interp(rms_energy, [0.0, 0.4], [0.0, 100.0]))
    return int(min(max(energy_scaled, 0.0), 100.0))


def calculate_bass_intensity(y: np.ndarray, sr: int) -> int:
    """Calculates the bass intensity (20-150Hz) and scales it to 0-100."""
    if y is None or len(y) == 0 or sr is None or sr <= 0:
        return 0

    y = np.asarray(y)
    if y.size == 0:
        return 0

    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)

    if y.size < 64:
        return 0

    # Choose an FFT size appropriate for the signal length to avoid warnings
    if y.size >= 2048:
        n_fft = 2048
    else:
        n_fft = int(2 ** np.ceil(np.log2(max(y.size, 64))))
        n_fft = max(64, n_fft)
    if n_fft > y.size:
        n_fft = max(64, int(max(y.size // 2, 1)) * 2)

    stft = np.abs(librosa.stft(y, n_fft=n_fft, center=y.size >= n_fft))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

    # Find frequency bins for the bass range
    bass_indices = np.where((freqs >= 20) & (freqs <= 150))[0]

    total_energy = float(np.sum(stft**2))
    bass_energy = (
        float(np.sum(stft[bass_indices, :] ** 2)) if bass_indices.size else 0.0
    )

    if total_energy == 0:
        return 0

    bass_ratio = bass_energy / total_energy

    # AUDIT-FIX 2026-08-14: Die Skala endete bei einem Bass-Anteil von 0.5 und
    # klemmte alles darueber auf 100. Real gemessen liegt der Anteil bei
    # elektronischer Musik zwischen 0.78 und 0.89 (20 Tracks der Produktiv-
    # bibliothek) — JEDER Track landete damit auf exakt 100, ueber 52 Tracks
    # genau EIN distinkter Wert. Das Merkmal trug null Information und lag
    # ausserdem ausserhalb jedes Genre-Bereichs (25-95), zog also im Scoring
    # alle Genres gleichmaessig runter.
    # Jetzt ist der Wert die wortwoertliche Prozentzahl: Anteil der spektralen
    # Energie unter 150 Hz. Keine willkuerliche Obergrenze, keine Saettigung.
    bass_intensity = float(np.interp(bass_ratio, [0.0, 1.0], [0.0, 100.0]))
    return int(min(max(bass_intensity, 0.0), 100.0))


def calculate_brightness(
    y: np.ndarray, sr: int, feature_cache: FeatureCache | None = None
) -> int:
    """
    Berechnet die spektrale Helligkeit eines Tracks (0-100).

    Nutzt den Spectral Centroid (Schwerpunkt des Frequenzspektrums):
    - Niedrige Werte (0-30): Dunkle, bass-lastige Tracks
    - Mittlere Werte (30-60): Ausgewogene Tracks
    - Hohe Werte (60-100): Helle, höhenreiche Tracks

    Args:
        y: Audio-Signal (numpy array)
        sr: Sample-Rate

    Returns:
        int: Brightness-Score 0-100
    """
    if y is None or len(y) == 0 or sr is None or sr <= 0:
        return 0

    y = np.asarray(y)
    if y.size == 0:
        return 0

    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)

    try:
        # Spectral Centroid = gewichteter Mittelwert der Frequenzen
        centroid = (
            feature_cache.get_spectral_centroid()[0]
            if feature_cache is not None
            else librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        )
        mean_centroid = float(np.mean(centroid))

        if not np.isfinite(mean_centroid):
            return 0

        # Normalisierung: typischer Bereich 500-8000 Hz → 0-100
        # Elektronische Musik liegt meist zwischen 1000-5000 Hz
        brightness = float(np.interp(mean_centroid, [500.0, 8000.0], [0.0, 100.0]))
        return int(min(max(brightness, 0.0), 100.0))
    except Exception as e:
        logger.error(f"Brightness-Berechnung fehlgeschlagen: {e}")
        return 0


def detect_vocal_instrumental(
    y: np.ndarray, sr: int, feature_cache: FeatureCache | None = None
) -> str:
    """
    Erkennt ob ein Track Vocals oder nur Instrumental enthält.

    Heuristik basierend auf:
    1. Spectral Flatness: Vocals haben weniger flaches Spektrum als reine Synths
    2. MFCC-Varianz: Gesang hat höhere MFCC-Varianz (wechselnde Vokale/Konsonanten)
    3. Spectral Contrast: Vocals haben ausgeprägtere Kontraste

    Args:
        y: Audio-Signal (numpy array)
        sr: Sample-Rate

    Returns:
        str: "vocal", "instrumental", oder "unknown"
    """
    if y is None or len(y) == 0 or sr is None or sr <= 0:
        return "unknown"

    y = np.asarray(y)
    if y.size == 0:
        return "unknown"

    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)

    try:
        # 1. Spectral Flatness (niedriger = tonaler = eher Vocals)
        flatness = (
            feature_cache.get_spectral_flatness()[0]
            if feature_cache is not None
            else librosa.feature.spectral_flatness(y=y)[0]
        )
        mean_flatness = float(np.mean(flatness))

        # 2. MFCC-Varianz (höher = mehr spektrale Variation = eher Vocals)
        mfccs = (
            feature_cache.get_mfcc(n_mfcc=13)
            if feature_cache is not None
            else librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        )
        # Varianz über die Zeit für MFCCs 2-13 (MFCC 1 ist Lautstärke)
        mfcc_variance = float(np.mean(np.var(mfccs[1:], axis=1)))

        # 3. Spectral Contrast (grössere Unterschiede = eher Vocals)
        contrast = (
            feature_cache.get_spectral_contrast()
            if feature_cache is not None
            else librosa.feature.spectral_contrast(y=y, sr=sr)
        )
        mean_contrast = float(np.mean(contrast))

        # Scoring: Jedes Feature gibt einen Punkt für "vocal"
        vocal_score = 0

        # Spectral Flatness: Vocals typisch < 0.05, Synths > 0.1
        if mean_flatness < 0.03:
            vocal_score += 2  # Stark tonal → wahrscheinlich Vocals
        elif mean_flatness < 0.08:
            vocal_score += 1  # Mässig tonal

        # MFCC-Varianz: Vocals typisch > 50, Instrumental < 30
        if mfcc_variance > 80:
            vocal_score += 2  # Hohe Variation → Vocals
        elif mfcc_variance > 40:
            vocal_score += 1  # Mittlere Variation

        # Spectral Contrast: Vocals typisch > 25
        if mean_contrast > 30:
            vocal_score += 2
        elif mean_contrast > 20:
            vocal_score += 1

        # Entscheidung: 0-2 = instrumental, 3-4 = unknown, 5-6 = vocal
        if vocal_score >= 5:
            return "vocal"
        elif vocal_score <= 2:
            return "instrumental"
        else:
            return "unknown"

    except Exception as e:
        logger.error(f"Vocal-Erkennung fehlgeschlagen: {e}")
        return "unknown"


def calculate_danceability(
    y: np.ndarray,
    sr: int,
    bpm: float | None = None,
    feature_cache: FeatureCache | None = None,
) -> int:
    """
    Berechnet die Tanzbarkeit eines Tracks (0-100).

    Kombination aus:
    1. Beat-Regelmässigkeit: Wie gleichmässig sind die Beat-Abstände?
    2. Onset-Regelmässigkeit: Wie rhythmisch ist die perkussive Aktivität?
    3. Low-Frequency-Periodizität: Wie stark ist der Bass-Rhythmus?

    Args:
        y: Audio-Signal (numpy array)
        sr: Sample-Rate
        bpm: Optional, bereits erkannte BPM

    Returns:
        int: Danceability-Score 0-100
    """
    if y is None or len(y) == 0 or sr is None or sr <= 0:
        return 0

    y = np.asarray(y)
    if y.size == 0:
        return 0

    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)

    try:
        # 1. Beat-Regelmässigkeit (0-1): Niedrige Varianz = regelmässiger Beat
        # Beats werden immer hier erkannt. Ein Parameter fuer vorberechnete
        # Beat-Frames existierte bis D14, hatte aber seit D8 keinen Aufrufer:
        # die in `analyze_track` vorhandenen Beat-Frames stammen aus dem
        # VOLLEN Signal, waehrend hier auf dem Merkmalsfenster gerechnet wird.
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
        if beats.size > 2:
            beat_times = librosa.frames_to_time(beats, sr=sr)
            intervals = np.diff(beat_times)
            if intervals.size > 0 and np.mean(intervals) > 0:
                beat_regularity = 1.0 - min(
                    float(np.std(intervals) / np.mean(intervals)), 1.0
                )
            else:
                beat_regularity = 0.0
        else:
            beat_regularity = 0.0

        # 2. Onset-Regelmässigkeit (0-1)
        onset_env = (
            librosa.onset.onset_strength(y=y, sr=sr)
            if feature_cache is None
            else feature_cache.get_onset_strength()
        )
        if onset_env.size > 0:
            # Autokorrelation der Onset-Stärke → Periodizität
            ac = librosa.autocorrelate(onset_env, max_size=onset_env.size // 2)
            if ac.size > 1 and ac[0] > 0:
                # Normalisieren und Peak nach dem ersten finden
                ac_norm = ac / ac[0]
                # Suche nach dem stärksten periodischen Peak
                peaks = []
                for i in range(1, min(len(ac_norm), 200)):
                    if i > 0 and i < len(ac_norm) - 1:
                        if ac_norm[i] > ac_norm[i - 1] and ac_norm[i] > ac_norm[i + 1]:
                            peaks.append(ac_norm[i])
                onset_regularity = float(max(peaks)) if peaks else 0.0
                onset_regularity = min(onset_regularity, 1.0)
            else:
                onset_regularity = 0.0
        else:
            onset_regularity = 0.0

        # 3. Low-Frequency-Periodizität (0-1)
        # Stärke des Bass-Rhythmus
        if y.size >= 2048:
            stft = (
                feature_cache.get_stft_magnitude(n_fft=2048, hop_length=512)
                if feature_cache is not None
                else np.abs(librosa.stft(y, n_fft=2048))
            )
            freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
            bass_bins = np.where((freqs >= 20) & (freqs <= 200))[0]
            if bass_bins.size > 0:
                bass_energy_over_time = np.mean(stft[bass_bins, :], axis=0)
                if bass_energy_over_time.size > 1 and np.std(bass_energy_over_time) > 0:
                    # Periodizität des Bass-Signals
                    bass_ac = librosa.autocorrelate(
                        bass_energy_over_time, max_size=bass_energy_over_time.size // 2
                    )
                    if bass_ac.size > 1 and bass_ac[0] > 0:
                        bass_ac_norm = bass_ac / bass_ac[0]
                        bass_peaks = []
                        for i in range(1, min(len(bass_ac_norm), 200)):
                            if i < len(bass_ac_norm) - 1:
                                if (
                                    bass_ac_norm[i] > bass_ac_norm[i - 1]
                                    and bass_ac_norm[i] > bass_ac_norm[i + 1]
                                ):
                                    bass_peaks.append(bass_ac_norm[i])
                        bass_periodicity = float(max(bass_peaks)) if bass_peaks else 0.0
                    else:
                        bass_periodicity = 0.0
                else:
                    bass_periodicity = 0.0
            else:
                bass_periodicity = 0.0
        else:
            bass_periodicity = 0.0

        # BPM-Bonus: Elektronische Musik im typischen DJ-Bereich (120-150 BPM)
        bpm_bonus = 0.0
        effective_bpm = bpm if bpm and bpm > 0 else 0.0
        if not effective_bpm:
            tempo_val = np.atleast_1d(tempo)
            effective_bpm = float(tempo_val[0]) if tempo_val.size else 0.0
        if 118 <= effective_bpm <= 152:
            bpm_bonus = 0.15  # Optimaler Tanzbereich
        elif 100 <= effective_bpm <= 170:
            bpm_bonus = 0.08  # Akzeptabler Tanzbereich

        # Gewichtete Kombination: Beat 40%, Onset 30%, Bass 20%, BPM 10%
        base_score = (
            beat_regularity * 0.40 + onset_regularity * 0.30 + bass_periodicity * 0.20
        )
        if bpm_bonus > 0:
            raw_score = base_score + (bpm_bonus / 0.15) * 0.10
        else:
            raw_score = base_score

        danceability = raw_score * 100.0
        return int(min(max(danceability, 0.0), 100.0))

    except Exception as e:
        logger.error(f"Danceability-Berechnung fehlgeschlagen: {e}")
        return 0


def calculate_mfcc_fingerprint(
    y: np.ndarray,
    sr: int,
    n_mfcc: int = 13,
    feature_cache: FeatureCache | None = None,
) -> list[float]:
    """
    Berechnet einen kompakten MFCC-Fingerprint für Similarity-Vergleiche.

    Args:
        y: Audio-Signal
        sr: Sample-Rate
        n_mfcc: Anzahl MFCCs (Standard: 13)

    Returns:
        list: Mittelwert-Vektor der MFCCs (Länge n_mfcc)
    """
    if y is None or len(y) == 0 or sr is None or sr <= 0:
        return []

    y = np.asarray(y)
    if y.size == 0:
        return []

    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)

    try:
        mfccs = (
            feature_cache.get_mfcc(n_mfcc=n_mfcc)
            if feature_cache is not None
            else librosa.feature.mfcc(y=y, sr=sr, n_mfcc=n_mfcc)
        )
        # Mittelwert über die Zeit → kompakter Vektor
        mean_mfccs = np.mean(mfccs, axis=1)
        return [round(float(v), 4) for v in mean_mfccs]
    except Exception as e:
        logger.error(f"MFCC-Fingerprint fehlgeschlagen: {e}")
        return []


def parse_filename_for_metadata(file_path: str) -> tuple[str, str]:
    """
    Extracts Artist and Title from filename using common DJ filename patterns.

    Supported patterns:
    - "Artist - Track.ext"
    - "01 - Artist - Track.ext"
    - "Artist-Track.ext"
    - "Track Number - Artist - Track.ext"

    Returns:
        tuple: (artist, title) or (None, None) if parsing fails
    """
    filename = os.path.basename(file_path)
    # Remove file extension
    name_without_ext = os.path.splitext(filename)[0]

    # Pattern 1: "Artist - Track" (most common DJ format)
    match = re.match(r"^(?:\d+[\s.-]*)?([^-]+?)\s*-\s*(.+)$", name_without_ext)
    if match:
        artist = match.group(1).strip()
        title = match.group(2).strip()

        # Validate: artist and title should have reasonable length
        if 1 <= len(artist) <= 100 and 1 <= len(title) <= 200:
            return artist, title

    # Pattern 2: "Artist_Track" (underscore separator)
    match = re.match(r"^(?:\d+[\s._-]*)?([^_]+?)_(.+)$", name_without_ext)
    if match:
        artist = match.group(1).strip()
        title = match.group(2).strip()
        if 1 <= len(artist) <= 100 and 1 <= len(title) <= 200:
            return artist, title

    # If no pattern matched, return None
    return None, None


def _mutagen_text_value(container, key: str) -> str | None:
    """Liest einen Textwert aus Easy-Tags oder rohen Mutagen-Frames."""
    if container is None:
        return None
    sources = (container, getattr(container, "tags", None))
    for source in sources:
        if source is None:
            continue
        try:
            value = source.get(key)
        except Exception:
            continue
        if hasattr(value, "text"):
            value = value.text
        if isinstance(value, (list, tuple)):
            value = next(
                (
                    item.strip()
                    for item in value
                    if isinstance(item, str) and item.strip()
                ),
                None,
            )
        if isinstance(value, str):
            value = value.strip()
            if value:
                return value
    return None


def extract_metadata(file_path: str) -> tuple[str, str, str]:
    """
    Liest Artist, Titel und Genre aus Easy-Tags oder rohen ID3-Frames.

    Fehlende Easy-Felder werden einmalig mit TPE1/TIT2/TCON nachgelesen.
    Nur weiterhin fehlende Artist-/Titelwerte kommen aus dem Dateinamen;
    ein fehlendes Genre wird zu ``Unknown``.

    Returns:
        tuple: (artist, title, genre)
    """
    artist = None
    title = None
    genre = None

    audio_easy = None
    try:
        audio_easy = mutagen.File(file_path, easy=True)
    except Exception as e:
        logger.warning(f"Easy-Tags nicht lesbar fuer {file_path}: {e}")
    if audio_easy is not None:
        artist = _mutagen_text_value(audio_easy, "artist")
        title = _mutagen_text_value(audio_easy, "title")
        genre = _mutagen_text_value(audio_easy, "genre")
        if not artist:
            artist = _mutagen_text_value(audio_easy, "TPE1")
        if not title:
            title = _mutagen_text_value(audio_easy, "TIT2")
        if not genre:
            genre = _mutagen_text_value(audio_easy, "TCON")

    if not artist or not title or not genre:
        audio_raw = None
        try:
            audio_raw = mutagen.File(file_path, easy=False)
        except Exception as e:
            logger.warning(f"Rohe ID3-Tags nicht lesbar fuer {file_path}: {e}")
        if audio_raw is not None:
            if not artist:
                artist = _mutagen_text_value(audio_raw, "TPE1")
            if not title:
                title = _mutagen_text_value(audio_raw, "TIT2")
            if not genre:
                genre = _mutagen_text_value(audio_raw, "TCON")

    # Fallback to filename parsing if artist or title is missing
    if not artist or not title or artist == "Unknown" or title == "Unknown":
        parsed_artist, parsed_title = parse_filename_for_metadata(file_path)

        # Use parsed values if available
        if not artist or artist == "Unknown":
            artist = parsed_artist if parsed_artist else "Unknown"
        if not title or title == "Unknown":
            title = parsed_title if parsed_title else os.path.basename(file_path)

    # Fallback for genre (always from tags or Unknown)
    if not genre:
        genre = "Unknown"

    return artist, title, genre


def extract_bpm_from_tags(file_path: str) -> float | None:
    """
    Liest BPM direkt aus ID3/AIFF-Tags (kein Librosa).

    Der gelesene Wert ist nur Metadaten-Rohmaterial. ``analyze_track`` prueft
    bekannte Faktorfehler spaeter gegen Audio und kanonisches ID3-Genre.

    Returns:
        float: BPM-Wert aus Tags, oder None wenn nicht vorhanden
    """
    try:
        audio = mutagen.File(file_path, easy=True)
        if audio is not None:
            # easy=True normalisiert Tags auf lowercase-Keys
            bpm_val = audio.get("bpm") or audio.get("tempo")
            if bpm_val:
                bpm = float(str(bpm_val[0]).strip())
                if 20.0 < bpm < 300.0:  # Plausibilitaetscheck
                    return round(bpm, 2)
        # Fallback: mutagen ohne easy=True fuer nicht-standardisierte Tags
        audio_raw = mutagen.File(file_path)
        if audio_raw is not None:
            for key in ("TBPM", "BPM", "bpm", "tempo"):
                if key in audio_raw:
                    tag = audio_raw[key]
                    raw_val = str(tag.text[0]) if hasattr(tag, "text") else str(tag)
                    bpm = float(raw_val.strip())
                    if 20.0 < bpm < 300.0:
                        return round(bpm, 2)
    except Exception as e:
        logger.warning(f"Fehler beim Lesen der BPM in ID3-Tags fuer {file_path}: {e}", exc_info=True)
    return None


def analyze_structure_and_mix_points(y: np.ndarray, sr: int, duration: float, energy_level: int, bpm: float, genre: str = "Unknown", anchor: float = 0.0, first_downbeat: float | None = None, phrase_unit: int | None = None) -> tuple[float, float, int, int]:
    """
    RMS-Fallback fuer Mix-Punkte, wenn keine Struktur-Analyse (Sections) vorliegt.

    Konsolidierung 2026-07-17 (docs/plans/2026-07-17-mixpoint-pfad-b-konsolidierung.md [extern archiviert, kein aktiver Link; Manifest: docs/cleanup-manifest-2026-10-04.json]):
    Diese Funktion berechnet KEINE eigenen Mix-Punkte mehr — sie erkennt nur
    Intro-Ende und Outro-Start per RMS-Aktivitaet, baut daraus 3 Pseudo-
    Sektionen (intro/main/outro) und delegiert an calculate_genre_aware_mix_points.
    Damit existiert nur noch EINE Quantisierungs-/Clamp-Logik (Pfad A).

    Research-Basis (Web-Recherche 2026-07-17, Volltexte):
    - Zehren et al. (arXiv 2007.08411 / CMJ 2022): Abschnitt "aktiv/tragfaehig"
      wenn mittlere Energie ueber ein 4-Takt-Fenster >= 0.4 x Track-Maximum
    - Bittner et al. (ISMIR 2017, Spotify): Mix-In-Kandidaten nur in den
      ersten 20%, Mix-Out nur in den letzten 25% des Tracks
    - Vande Veire & De Bie (EURASIP 2018): 16 Takte als Standard-Fade/Fallback

    Returns:
        tuple: (mix_in_point, mix_out_point, mix_in_bars, mix_out_bars)
    """
    mix_in_point = 0.0
    mix_out_point = duration
    mix_in_bars = 0
    mix_out_bars = 0

    if bpm is not None and bpm <= 0:
        raise ValueError(f"BPM muss positiv sein, erhalten: {bpm}")

    if duration is None or duration <= 0 or bpm is None:
        return (
            round(mix_in_point, 2),
            round(mix_out_point, 2),
            mix_in_bars,
            mix_out_bars,
        )

    try:
        seconds_per_bar = (60.0 / bpm) * METER
        # 16 Takte: Standard-Fade-/Fallback-Laenge (Vande Veire, EURASIP 2018)
        fallback_len = seconds_per_bar * 16

        # --- RMS-Aktivitaetserkennung ---
        rms = librosa.feature.rms(y=y, hop_length=HOP_LENGTH)[0]
        times = librosa.frames_to_time(
            np.arange(len(rms)), sr=sr, hop_length=HOP_LENGTH
        )

        # Glaettung ueber ein 4-Takt-Fenster (Zehren: Salience ueber 4 Takte)
        # HIGH-Fix: Kernel gegen len(rms) klemmen. Bei kurzen/langsamen Tracks
        # (Audio kuerzer als 4 Takte, z.B. Jingles/IDs oder Downtempo) lieferte
        # np.convolve(mode="same") sonst ein Array in KERNEL-Laenge > len(times),
        # und times[active[-1]] warf einen (vom aeusseren except verschluckten)
        # IndexError -> RMS-Erkennung fiel komplett auf den generischen Fallback.
        window_frames = max(1, min(int((seconds_per_bar * 4) * sr / HOP_LENGTH), len(rms)))
        rms_smooth = np.convolve(
            rms, np.ones(window_frames) / window_frames, mode="same"
        )

        rms_max = float(np.max(rms_smooth)) if rms_smooth.size else 0.0
        if rms_max > 1e-6:
            # aktiv = >= 0.4 x Track-Maximum (Zehren-Salience, RMS_THRESHOLD)
            active = np.where(rms_smooth >= rms_max * RMS_THRESHOLD)[0]
        else:
            active = np.array([], dtype=int)  # Stille: nur Fallbacks

        if active.size > 0:
            intro_end_time = float(times[active[0]])
            outro_start_time = float(times[active[-1]])
        else:
            intro_end_time = min(fallback_len, duration * MIX_IN_SEARCH_WINDOW_PCT)
            outro_start_time = max(
                duration - fallback_len, duration * MIX_OUT_SEARCH_WINDOW_PCT
            )

        # --- Suchfenster-Pruning (Bittner, ISMIR 2017) ---
        # Mix-In-Kandidaten liegen in den ersten 20%, Mix-Out in den letzten 25%
        if intro_end_time > duration * MIX_IN_SEARCH_WINDOW_PCT:
            intro_end_time = min(fallback_len, duration * MIX_IN_SEARCH_WINDOW_PCT)
        if outro_start_time < duration * MIX_OUT_SEARCH_WINDOW_PCT:
            outro_start_time = max(
                duration - fallback_len, duration * MIX_OUT_SEARCH_WINDOW_PCT
            )
        if intro_end_time >= outro_start_time:
            intro_end_time = min(fallback_len, duration * MIX_IN_SEARCH_WINDOW_PCT)
            outro_start_time = max(
                duration - fallback_len, duration * MIX_OUT_SEARCH_WINDOW_PCT
            )

        # --- Pseudo-Sektionen bauen und an Pfad A delegieren ---
        def _range_energy(start_s: float, end_s: float) -> float:
            """Mittlere geglaettete RMS im Bereich, skaliert 0-100 relativ zum Max."""
            if rms_max <= 1e-6 or times.size == 0:
                return 0.0
            mask = (times >= start_s) & (times < end_s)
            if not np.any(mask):
                return 0.0
            return float(np.mean(rms_smooth[mask]) / rms_max * 100.0)

        pseudo_sections = [
            {
                "label": "intro",
                "start_time": 0.0,
                "end_time": intro_end_time,
                "avg_energy": _range_energy(0.0, intro_end_time),
            },
            {
                "label": "main",
                "start_time": intro_end_time,
                "end_time": outro_start_time,
                "avg_energy": _range_energy(intro_end_time, outro_start_time),
            },
            {
                "label": "outro",
                "start_time": outro_start_time,
                "end_time": duration,
                "avg_energy": _range_energy(outro_start_time, duration),
            },
        ]

        return calculate_genre_aware_mix_points(
            pseudo_sections, bpm, duration, genre, anchor=anchor,
            first_downbeat=first_downbeat,  # R3: Untergrenze am Takt-Anker
            phrase_unit=phrase_unit,
        )

    except Exception as e:
        logger.error(f"Fehler in analyze_structure_and_mix_points: {e}")
        # Der Fehler-Fallback bleibt auf derselben genre- und
        # phrasenbewussten Quantisierung wie der regulaere Pfad.
        safe_in = min(max(duration * 0.2, 0.0), max(duration - 1.0, 0.0))
        safe_out = max(duration * 0.8, safe_in + 1.0)
        safe_out = min(safe_out, duration)
        safe_in = min(safe_in, max(safe_out - 1.0, 0.0))
        pseudo_sections = [
            {"label": "intro", "start_time": 0.0, "end_time": safe_in},
            {"label": "main", "start_time": safe_in, "end_time": safe_out},
            {"label": "outro", "start_time": safe_out, "end_time": duration},
        ]
        return calculate_genre_aware_mix_points(
            pseudo_sections,
            bpm,
            duration,
            genre,
            anchor=anchor,
            first_downbeat=first_downbeat,
            phrase_unit=phrase_unit,
        )


def _offset_section(
    section: TrackSection,
    offset: float,
    bpm: float,
    duration: float,
    seconds_per_bar: float | None = None,
) -> TrackSection:
    """Verschiebt eine lokal analysierte Tail-Sektion auf die Track-Zeitachse."""
    seconds_bar = seconds_per_bar or ((60.0 / bpm) * METER if bpm > 0 else 0.0)
    start = section.start_time + offset
    end = section.end_time + offset
    return TrackSection(
        label=section.label,
        start_time=min(max(0.0, start), duration),
        end_time=min(max(0.0, end), duration),
        start_bar=int(round(start / seconds_bar)) if seconds_bar else 0,
        end_bar=int(round(end / seconds_bar)) if seconds_bar else 0,
        avg_energy=section.avg_energy,
    )


def _section_audio_slice(section, audio_windows, sr, fallback_cache=None):
    """Liefert Audio und Cache passend zum absoluten Zeitbereich einer Sektion."""
    start_s, end_s = section.get('start_time'), section.get('end_time')
    if (type(start_s) not in (int, float) or type(end_s) not in (int, float)
            or not math.isfinite(start_s) or not math.isfinite(end_s)
            or start_s < 0 or end_s <= start_s):
        return np.empty(0, dtype=np.float32), fallback_cache, (0, 0)
    for offset_s, audio, cache in audio_windows:
        if not isinstance(audio, np.ndarray) or audio.ndim != 1:
            continue
        first = int(round((start_s - offset_s) * sr))
        last = int(round((end_s - offset_s) * sr))
        if 0 <= first < last <= len(audio):
            selected_cache = cache if cache is not None else fallback_cache
            return audio[first:last], selected_cache, (first, last)
    return np.empty(0, dtype=np.float32), fallback_cache, (0, 0)


def _cue_phrase_identities(phrases):
    """Phrase-Kandidatenidentität in Originalreihenfolge, ohne Zeitrundung."""
    try:
        result = []
        for index, phrase in enumerate(phrases):
            start, end = phrase['start_s'], phrase['end_s']
            if (type(start) not in (int, float) or type(end) not in (int, float)
                    or not math.isfinite(start) or not math.isfinite(end) or not 0 <= start < end):
                return None
            categories = tuple(phrase[key] for key in ('kind', 'mood', 'fill'))
            if any(type(value) is not int for value in categories):
                return None
            result.append((index, start, end, *categories))
        return tuple(result)
    except (TypeError, KeyError):
        return None


def _bind_cue_scores(phrases, source_signature, verified):
    from .ai_models.cue_predictor import MODEL_HASHES, PREPROCESS_VERSION
    identity = _cue_phrase_identities(phrases)
    return dict(phrases=identity, source_signature=source_signature,
                model_hashes=dict(MODEL_HASHES), preprocess_version=PREPROCESS_VERSION,
                valid=verified is True and identity is not None
                      and type(source_signature) is str and bool(source_signature))


def _cue_source_signature(file_path, rekordbox_signature):
    """Bindet Cue-Ergebnisse an Dateiänderungen und optionalen RB-Import."""
    try:
        path = os.path.normcase(os.path.abspath(os.path.normpath(str(file_path))))
        stat = os.stat(path)
        identity = (path, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns,
                    stat.st_dev, stat.st_ino, str(rekordbox_signature or ''))
        return hashlib.sha256(json.dumps(identity, ensure_ascii=True,
            separators=(',', ':')).encode('utf8')).hexdigest()
    except (OSError, TypeError, ValueError):
        return ''


def _cue_candidates_for_structure(*, phrases, pssi_grid_usable,
                                  native_phrase_analysis, phrase_phase_usable,
                                  pssi_grid_verified):
    """Wählt verifizierte Cue-Modellkandidaten mit PSSI-Vorrang.

    Native Phrase-Ausgaben sind zulässig, wenn ihr Grid bereits für die
    Phrasenphase freigegeben wurde. Ungeprüfte Kandidaten öffnen keinen
    Modellkontext.
    """
    if pssi_grid_usable and pssi_grid_verified and phrases:
        return phrases, True
    if (phrase_phase_usable and type(native_phrase_analysis) is dict
            and native_phrase_analysis.get('status') == 'ok'):
        candidates = native_phrase_analysis.get('phrases')
        if type(candidates) is list and candidates:
            return candidates, True
    return None, False


def _bound_cue_scores(phrases, source_signature, binding, windows):
    """Nur eindeutige gebundene Phrase-Erfolge nutzen; Ausfälle bleiben neutral."""
    from .ai_models.cue_predictor import MODEL_HASHES, PREPROCESS_VERSION, CUE_SCORE_SOURCE
    identity = _cue_phrase_identities(phrases)
    if (not binding or binding.get('valid') is not True or identity is None
            or binding.get('phrases') != identity or binding.get('source_signature') != source_signature
            or binding.get('model_hashes') != MODEL_HASHES or binding.get('preprocess_version') != PREPROCESS_VERSION):
        return {}
    from collections import Counter
    counts = Counter(item[1:] for item in identity)
    successes, ambiguous = {}, set()
    for window in windows:
        if window.get('status') != 'evaluated':
            continue
        seen = set()
        for result in window.get('results', []):
            index = result.get('index')
            if type(index) is not int or not 0 <= index < len(identity):
                continue
            if index in seen:
                ambiguous.add(index)
            seen.add(index)
            if result.get('status') != 'ok':
                continue
            score = result.get('raw_score')
            if (counts[identity[index][1:]] != 1 or type(score) not in (int, float)
                    or not math.isfinite(score) or result.get('model_hashes') != binding['model_hashes']
                    or result.get('preprocess_version') != binding['preprocess_version']
                    or result.get('source') != CUE_SCORE_SOURCE):
                ambiguous.add(index)
                continue
            if index in successes and successes[index] != score:
                ambiguous.add(index)
            successes[index] = float(score)
    return {index: score for index, score in successes.items() if index not in ambiguous}


def _kandidaten_berechnen(
    file_path: str, *, pfad: str, bpm: float, duration: float, first_downbeat: float,
    downbeat_confidence: float, phrase_confidence: float, phrase_anchor: float | None,
    anchor_grid_usable: bool, phrase_phase_usable: bool, pssi_grid_usable: bool,
    phrase_unit: int, sections: list, phrases: list, cues: list,
    analyzer_in: float, analyzer_out: float, outro_covered: bool, cue_scores: dict | None = None,
    native_phrases: list[dict] | None = None,
) -> tuple[list, list] | None:
    """Mix-Kandidaten beider Seiten berechnen; Fehler kippen die Analyse nie.
    `pfad` ("fast"/"voll") erscheint im Log, damit tools/kandidaten_messen.py die
    Laufzeit je Analysepfad trennen kann."""
    # Ein stabiles Beatgrid allein belegt keine freigegebene Takt-/Phrasenphase.
    native_grid_available = bool(native_phrases) and not phrases
    if (not anchor_grid_usable or phrase_anchor is None
            or not (phrase_phase_usable or pssi_grid_usable)):
        return [], []
    candidate_phrases = phrases if pssi_grid_usable else []
    t0 = time.perf_counter()
    try:
        mix_in, mix_out = build_track_candidates(
            file_path, bpm=bpm, duration=duration, first_downbeat=first_downbeat,
            downbeat_confidence=downbeat_confidence, phrase_confidence=phrase_confidence,
            phrase_anchor=phrase_anchor, phrase_unit=phrase_unit, sections=sections,
            phrases=candidate_phrases, cues=cues, analyzer_in=analyzer_in, analyzer_out=analyzer_out,
            outro_covered=outro_covered, cue_scores=cue_scores,
            native_phrases=native_phrases,
            native_grid_verified=native_grid_available and phrase_phase_usable,
        )
    except Exception as e:
        logger.warning(f"Kandidaten [{pfad}] fehlgeschlagen: {e}")
        return None
    logger.info(
        f"Kandidaten [{pfad}]: {len(mix_in)} in / {len(mix_out)} out "
        f"in {time.perf_counter() - t0:.2f}s"
    )
    return mix_in, mix_out


def analyze_structure_windows(
    file_path: str,
    head_audio: np.ndarray,
    sr: int,
    bpm: float,
    genre: str,
    duration: float,
    anchor: float = 0.0,
    phrase_unit: int | None = None,
    seconds_per_bar: float | None = None,
    feature_cache: FeatureCache | None = None,
    cue_candidates: list[dict] | None = None,
    cue_verified_grid: bool = False,
    cue_source_signature: str = "",
    cue_score_binding: dict | None = None,
    phrase_unit_source: str | None = None,
    native_phrase_analysis: dict | None = None,
) -> tuple[TrackStructure, list[dict], bool]:
    """Kombiniert Anfang und echtes Track-Ende mit expliziter Coverage-Luecke."""
    with (cue_service.session() if cue_candidates is not None else nullcontext(None)) as cue_client:
        head_duration = min(float(librosa.get_duration(y=head_audio, sr=sr)), duration)
        structure_kwargs = {"anchor": anchor}
        if phrase_unit is not None:
            structure_kwargs["phrase_unit"] = phrase_unit
        if phrase_unit_source is not None:
            structure_kwargs["phrase_unit_source"] = phrase_unit_source
        if seconds_per_bar is not None:
            structure_kwargs["seconds_per_bar"] = seconds_per_bar
        if feature_cache is not None:
            structure_kwargs["feature_cache"] = feature_cache
        if cue_score_binding is not None:
            cue_score_binding.clear()
            cue_score_binding.update(_bind_cue_scores(cue_candidates, cue_source_signature, cue_verified_grid))
        if cue_client is not None:
            structure_kwargs['cue_context'] = dict(
                candidates=cue_candidates, **{key: cue_client.config[key] for key in
                    ('samplecnn_path', 'cue_model_path', 'prefer_directml')}, window_start_s=0.0,
                track_duration_s=duration, verified_grid=cue_verified_grid, _client=cue_client,
            )
        if native_phrase_analysis and native_phrase_analysis.get('status') == 'ok':
            structure_kwargs['native_phrase_context'] = dict(
                candidates=native_phrase_analysis['phrases'], verified_grid=True,
                window_start_s=0., track_duration_s=duration)
        head = analyze_structure(head_audio, sr, bpm, genre, **structure_kwargs)
        # Die spaetere Sektionsextraktion braucht dieselben echten Fenster wie
        # der Strukturpass; das Fast-Path-Headfenster deckt lange Tracks nicht
        # bis zum Trackende ab.
        head._section_audio_windows = [(0.0, head_audio, feature_cache)]
        if cue_client is not None:
            head.cue_diagnostics = [dict(start_s=0.0, status=(
                'unverified_grid' if not cue_verified_grid else
                'no_candidates' if not cue_candidates else 'evaluated'), results=head.cue_diagnostics)]
        for section in head.sections:
            section.end_time = min(section.end_time, head_duration)

        coverage = [{
            "start": 0.0,
            "end": min(head_duration, duration),
        }]
        if duration <= head_duration + 1.0:
            return head, coverage, True

        def mark_unanalysed_tail():
            """Mache dieselbe Coverage-Luecke fuer beide Tail-Fehlerpfade sichtbar."""
            seconds_bar = seconds_per_bar or (
                (60.0 / bpm) * METER if bpm > 0 else 0.0
            )
            head.sections.append(
                TrackSection(
                    label="unanalysed",
                    start_time=min(head_duration, duration),
                    end_time=duration,
                    start_bar=(
                        int(round(head_duration / seconds_bar)) if seconds_bar else 0
                    ),
                    end_bar=(
                        int(round(duration / seconds_bar)) if seconds_bar else 0
                    ),
                    avg_energy=0.0,
                )
            )
            head.total_bars = (
                int(duration / seconds_bar) if seconds_bar else head.total_bars
            )

        # AUDIT-FIX N1 (2026-07-24): Das Head-Fenster endet NICHT am Track-Ende —
        # ein dort vergebenes "outro"-Label ist ein Fenster-Artefakt (der Labeler
        # markiert immer die letzte Section als Outro-Kandidat, ohne zu wissen,
        # dass der Track weitergeht). Solche Labels zu "main" degradieren, sonst
        # zieht der Outro-Scanner in dj_brain den outro_start in die Track-Mitte.
        for section in head.sections:
            if section.label == "outro":
                section.label = "main"

        tail_start = max(head_duration, duration - LIBROSA_TAIL_DURATION)
        try:
            tail_audio, _ = _load_analysis_audio(
                file_path, sr=sr, offset=tail_start,
                duration=max(0.0, duration - tail_start),
            )
        except (sf.LibsndfileError, RuntimeError, OSError, ValueError) as error:
            logger.warning("Track-Ende konnte nicht analysiert werden: %s", error)
            if cue_client is not None:
                head.cue_diagnostics.append(dict(start_s=tail_start, status='decode_error', results=[]))
            mark_unanalysed_tail()
            return head, coverage, False
        tail_duration = float(librosa.get_duration(y=tail_audio, sr=sr))
        tail_end = min(duration, tail_start + tail_duration)
        if tail_duration <= 0:
            if cue_client is not None:
                head.cue_diagnostics.append(dict(start_s=tail_start, status='decode_error', results=[]))
            # Leerer/ungueltiger Tail-Decode ist dieselbe Coverage-Luecke wie
            # ein Ladefehler: den nicht analysierten Bereich sichtbar lassen,
            # statt ihn durch ein stilles fruehes Return zu verschlucken.
            mark_unanalysed_tail()
            return head, coverage, False

        tail_kwargs = {"anchor": anchor - tail_start}
        # Wenn die Head-Noveltly die Phrasenlaenge ermittelt hat, muss das
        # Tail dieselbe Einheit verwenden. Zwei unabhaengige Fenster duerfen
        # nicht verschiedene Phrasenraster in ein Track-Ergebnis mischen.
        tail_phrase_unit = phrase_unit if phrase_unit is not None else head.phrase_unit
        if tail_phrase_unit is not None:
            tail_kwargs["phrase_unit"] = tail_phrase_unit
        if head.phrase_unit_source == "genre_prior":
            tail_kwargs["phrase_unit_source"] = "genre_prior"
        if seconds_per_bar is not None:
            tail_kwargs["seconds_per_bar"] = seconds_per_bar
        if feature_cache is not None:
            tail_kwargs["feature_cache"] = FeatureCache(tail_audio, sr)
        if cue_client is not None:
            if cue_score_binding is not None and cue_score_binding.get('phrases') != _cue_phrase_identities(cue_candidates):
                cue_score_binding['valid'] = False
            tail_kwargs['cue_context'] = dict(
                candidates=cue_candidates, **{key: cue_client.config[key] for key in
                    ('samplecnn_path', 'cue_model_path', 'prefer_directml')}, window_start_s=tail_start,
                track_duration_s=duration, verified_grid=cue_verified_grid, _client=cue_client,
            )
        if native_phrase_analysis and native_phrase_analysis.get('status') == 'ok':
            tail_kwargs['native_phrase_context'] = dict(
                candidates=native_phrase_analysis['phrases'], verified_grid=True,
                window_start_s=tail_start, track_duration_s=duration)
        tail = analyze_structure(tail_audio, sr, bpm, genre, **tail_kwargs)
        head._section_audio_windows.append((
            tail_start, tail_audio, tail_kwargs.get('feature_cache'),
        ))
        if cue_client is not None:
            tail.cue_diagnostics = [dict(start_s=tail_start, status=(
                'unverified_grid' if not cue_verified_grid else
                'no_candidates' if not cue_candidates else 'evaluated'), results=tail.cue_diagnostics)]
        # AUDIT-FIX B7 (2026-07-24): Spiegelbildlich zum Head-Fenster — das
        # Tail-Fenster beginnt mitten im Track, ein "intro"-Label dort ist ein
        # Fenster-Artefakt und wuerde den Intro-Scanner in dj_brain vergiften.
        for section in tail.sections:
            if section.label == "intro":
                section.label = "main"

        shifted_tail = [
            _offset_section(
                section,
                tail_start,
                bpm,
                duration,
                seconds_per_bar=seconds_per_bar,
            )
            for section in tail.sections
        ]
        coverage.append({
            "start": min(tail_start, duration),
            "end": min(tail_end, duration),
        })

        head_sections = [section for section in head.sections if section.start_time < tail_start]
        if head_sections:
            head_sections[-1].end_time = min(head_sections[-1].end_time, tail_start)

        merged_sections = head_sections
        if tail_start > head_duration + 1.0:
            seconds_bar = seconds_per_bar or ((60.0 / bpm) * METER if bpm > 0 else 0.0)
            merged_sections.append(
                TrackSection(
                    label="unanalysed",
                    # Dieselben ungerundeten Grenzen wie die Nachbarsektionen:
                    # Aufrunden erzeugt sonst eine Überlappung im Cachevertrag.
                    start_time=min(head_duration, duration),
                    end_time=min(tail_start, duration),
                    start_bar=int(round(head_duration / seconds_bar)) if seconds_bar else 0,
                    end_bar=int(round(tail_start / seconds_bar)) if seconds_bar else 0,
                    avg_energy=0.0,
                )
            )
        merged_sections.extend(shifted_tail)
        total_bars = int(
            duration / (seconds_per_bar or ((60.0 / bpm) * METER))
        ) if bpm > 0 else 0
        merged = TrackStructure(
            sections=merged_sections,
            total_bars=total_bars,
            phrase_unit=head.phrase_unit or tail.phrase_unit,
            phrase_unit_source=head.phrase_unit_source,
            phrase_unit_candidate=head.phrase_unit_candidate,
            phrase_unit_score=head.phrase_unit_score,
            phrase_unit_margin=head.phrase_unit_margin,
            cue_diagnostics=head.cue_diagnostics + tail.cue_diagnostics,
        )
        return merged, coverage, tail_end >= duration - 1.0


def cue_in_verwerfen(
    cue_in: float | None,
    benannter_cue: bool,
    intro_ende: float,
) -> bool:
    """Verwirft jeden Cue auf oder vor der harten Intro-Sicherheitsgrenze.

    ``benannter_cue`` bleibt aus Kompatibilitaetsgruenden im Aufrufvertrag,
    gewaehrt aber ausdruecklich keine Ausnahme mehr.
    """
    if cue_in is None:
        return False
    return cue_in <= intro_ende + QUANTIZE_TOLERANCE_SEC


def _mixpoint_pair_erfuellt_harten_vertrag(
    mix_in: float,
    mix_out: float,
    *,
    bpm: float,
    duration: float,
    phrase_unit: int,
    anchor: float,
    sections: list[dict],
) -> bool:
    """Prueft das finale quantisierte Paar ohne Cue-Sonderrechte."""
    values = (mix_in, mix_out, bpm, duration, anchor)
    if not all(np.isfinite(float(value)) for value in values):
        return False
    if bpm <= 0.0 or duration <= 0.0 or not 0.0 <= mix_in < mix_out <= duration:
        return False

    intro_end = _get_intro_end_from_sections(sections)
    outro_start = _get_outro_start_from_sections(sections, duration)
    tolerance = QUANTIZE_TOLERANCE_SEC
    if mix_in <= intro_end + tolerance or mix_out >= outro_start - tolerance:
        return False

    if type(phrase_unit) is not int or phrase_unit not in {8, 16, 32}:
        return False
    unit = phrase_unit
    phrase_grid = (60.0 / bpm) * METER * unit
    if phrase_grid <= 0.0 or mix_out - mix_in + tolerance < 2.0 * phrase_grid:
        return False
    aligned_in = quantize_to_grid(mix_in, phrase_grid, anchor, "round")
    aligned_out = quantize_to_grid(mix_out, phrase_grid, anchor, "round")
    return (
        abs(aligned_in - mix_in) <= tolerance
        and abs(aligned_out - mix_out) <= tolerance
    )


def _apply_manual_mixpoint_cues(
    mix_in: float,
    mix_out: float,
    *,
    cue_points: list[dict],
    bpm: float,
    duration: float,
    phrase_unit: int,
    anchor: float,
    sections: list[dict],
) -> tuple[float, float]:
    """Uebernimmt gerichtete manuelle Cues nur nach dem harten Vertrag.

    IN und OUT werden getrennt versucht. Ein ungueltiger Cue verwirft daher
    weder den berechneten Trackpunkt noch einen gueltigen Cue der Gegenseite.
    """
    cue_in = None
    cue_out = None
    for cue in cue_points or []:
        if cue.get("provenance") != "manual":
            continue
        name = str(cue.get("name") or "").upper()
        if cue_in is None and CUE_IN_PATTERN.search(name):
            cue_in = float(cue["t"])
        elif cue_out is None and CUE_OUT_PATTERN.search(name):
            cue_out = float(cue["t"])

    intro_end = _get_intro_end_from_sections(sections)
    outro_start = _get_outro_start_from_sections(sections, duration)
    if cue_in is not None and cue_in <= intro_end + QUANTIZE_TOLERANCE_SEC:
        cue_in = None
    if cue_out is not None and cue_out >= outro_start - QUANTIZE_TOLERANCE_SEC:
        cue_out = None

    def ausrichten(candidate_in: float, candidate_out: float) -> tuple[float, float] | None:
        aligned_in, aligned_out = align_ai_mix_points(
            candidate_in,
            candidate_out,
            bpm,
            duration,
            phrase_unit,
            anchor=anchor,
        )
        if _mixpoint_pair_erfuellt_harten_vertrag(
            aligned_in,
            aligned_out,
            bpm=bpm,
            duration=duration,
            phrase_unit=phrase_unit,
            anchor=anchor,
            sections=sections,
        ):
            return aligned_in, aligned_out
        return None

    if cue_in is not None and cue_out is not None:
        gemeinsam = ausrichten(cue_in, cue_out)
        if gemeinsam is not None:
            return gemeinsam

    result_in, result_out = mix_in, mix_out
    if cue_in is not None:
        nur_in = ausrichten(cue_in, result_out)
        if nur_in is not None:
            result_in, result_out = nur_in
    if cue_out is not None:
        nur_out = ausrichten(result_in, cue_out)
        if nur_out is not None:
            result_in, result_out = nur_out
    return result_in, result_out


def _reestimate_phrase_phase_for_selected_unit(
    y: np.ndarray,
    sr: int,
    bpm: float,
    first_downbeat: float,
    prior_unit: int,
    structure: TrackStructure,
    *,
    first_phrase: float,
    phrase_confidence: float,
    phrase_anchor: float | None,
    anchor_grid_usable: bool,
    phrase_usage_blocked: bool,
) -> tuple[float, float, float | None]:
    """Rechnet Phrasenphase neu, wenn Novelty das zugrunde liegende Raster ändert."""
    if (
        not anchor_grid_usable
        or phrase_usage_blocked
        or structure.phrase_unit_source != "audio_novelty"
        or structure.phrase_unit == prior_unit
    ):
        return first_phrase, phrase_confidence, phrase_anchor

    selected_phrase, selected_confidence = estimate_first_phrase(
        y, sr, bpm, first_downbeat, structure.phrase_unit
    )
    selected_anchor = first_downbeat
    if (
        selected_phrase >= 0.0
        and selected_confidence >= PHRASE_CONFIDENCE_MIN
    ):
        selected_anchor = selected_phrase
    return selected_phrase, selected_confidence, selected_anchor


def _reanalyze_structure_for_phrase_anchor(
    file_path: str,
    y: np.ndarray,
    sr: int,
    bpm: float,
    genre: str,
    duration: float,
    phrase_anchor: float,
    phrase_unit: int,
    *,
    feature_cache,
    cue_candidates: list[dict] | None,
    cue_verified_grid: bool,
    cue_source_signature,
    cue_score_binding: dict,
    original_structure: TrackStructure,
    native_phrase_analysis: dict | None = None,
) -> tuple[TrackStructure, list[dict], bool]:
    """Quantisiert Sektionen erneut auf das final bestaetigte Phrase-Raster."""
    refined, coverage, outro_covered = analyze_structure_windows(
        file_path,
        y,
        sr,
        bpm,
        genre,
        duration,
        anchor=phrase_anchor,
        phrase_unit=phrase_unit,
        phrase_unit_source="genre_prior",
        feature_cache=feature_cache,
        cue_candidates=cue_candidates,
        cue_verified_grid=cue_verified_grid,
        cue_source_signature=cue_source_signature,
        cue_score_binding=cue_score_binding,
        native_phrase_analysis=native_phrase_analysis,
    )
    refined.phrase_unit = original_structure.phrase_unit
    refined.phrase_unit_source = original_structure.phrase_unit_source
    refined.phrase_unit_candidate = original_structure.phrase_unit_candidate
    refined.phrase_unit_score = original_structure.phrase_unit_score
    refined.phrase_unit_margin = original_structure.phrase_unit_margin
    return refined, coverage, outro_covered


def _analyze_structure_with_final_phrase_anchor(
    file_path: str,
    y: np.ndarray,
    sr: int,
    bpm: float,
    genre: str,
    duration: float,
    *,
    first_downbeat: float,
    phrase_anchor: float | None,
    first_phrase: float,
    phrase_confidence: float,
    phrase_unit: int,
    measure_phrase_unit: bool,
    preserve_phrase_anchor: bool,
    anchor_grid_usable: bool,
    phrase_usage_blocked: bool,
    feature_cache,
    cue_candidates: list[dict] | None,
    cue_verified_grid: bool,
    reanalyze_cue_verified_grid: bool,
    cue_source_signature,
    native_phrase_analysis: dict | None = None,
):
    """Teilt die finale Phrasen-/Strukturentscheidung beider Analysepfade."""
    cue_score_binding = {}
    structure, coverage, outro_covered = analyze_structure_windows(
        file_path,
        y,
        sr,
        bpm,
        genre,
        duration,
        anchor=0.0 if phrase_usage_blocked else phrase_anchor,
        phrase_unit=None if measure_phrase_unit else phrase_unit,
        phrase_unit_source=None if measure_phrase_unit else "genre_prior",
        feature_cache=feature_cache,
        cue_candidates=None if phrase_usage_blocked else cue_candidates,
        cue_verified_grid=cue_verified_grid,
        cue_source_signature=cue_source_signature,
        cue_score_binding=cue_score_binding,
        native_phrase_analysis=native_phrase_analysis,
    )
    previous_phrase_anchor = phrase_anchor
    if not preserve_phrase_anchor:
        first_phrase, phrase_confidence, phrase_anchor = (
            _reestimate_phrase_phase_for_selected_unit(
                y, sr, bpm, first_downbeat, phrase_unit, structure,
                first_phrase=first_phrase,
                phrase_confidence=phrase_confidence,
                phrase_anchor=phrase_anchor,
                anchor_grid_usable=anchor_grid_usable,
                phrase_usage_blocked=phrase_usage_blocked,
            )
        )
    if phrase_anchor != previous_phrase_anchor:
        try:
            structure, coverage, outro_covered = _reanalyze_structure_for_phrase_anchor(
                file_path, y, sr, bpm, genre, duration,
                phrase_anchor, structure.phrase_unit,
                feature_cache=feature_cache,
                cue_candidates=cue_candidates,
                cue_verified_grid=reanalyze_cue_verified_grid,
                cue_source_signature=cue_source_signature,
                cue_score_binding=cue_score_binding,
                original_structure=structure,
                native_phrase_analysis=native_phrase_analysis,
            )
        except Exception as exc:
            logger.warning("Struktur-Neuquantisierung nach Novelty-Phrase fehlgeschlagen: %s", exc)
            phrase_anchor = previous_phrase_anchor
            first_phrase = MIX_POINT_UNSET
            phrase_confidence = 0.0
    return (
        structure, coverage, outro_covered,
        first_phrase, phrase_confidence, phrase_anchor, cue_score_binding,
    )


def _persist_analysis_result(cache_key: str | None, track: Track) -> bool:
    """Meldet Analyseerfolg nur nach bestaetigter Cache-Persistenz."""
    try:
        persisted = cache_track(cache_key, track)
    except Exception as error:
        # cache_track kapselt Schreibfehler laut API selbst. Dieser Guard
        # verhindert trotzdem einen falschen Erfolg bei Vertragsverletzungen.
        logger.error("Cache-Persistenz warf unerwartet eine Exception: %s", error)
        return False
    if persisted is not True:
        logger.error("Analyse konnte nicht persistiert werden: %s", track.filePath)
        return False
    return True


def _reference_grid_attempt(file_path, duration, bpm, y, sr, grid, reference_bpm,
                            reference_path_match="unknown"):
    """Originalreferenz vor einer möglichen Tempoänderung unverfälscht prüfen."""
    if not isinstance(grid, (list, tuple)) or not grid:
        return None
    # Rekordbox verwendet 0 für ein fehlendes Tempo. Das Grid bleibt prüfbar,
    # die Diagnose darf daraus aber kein gemessenes positives Tempo machen.
    if (type(reference_bpm) not in (int, float)
            or not math.isfinite(reference_bpm) or reference_bpm <= 0):
        reference_bpm = None
    anchor = next((p['time'] for p in grid if p['beat'] == 1), None)
    if anchor is None:
        return None
    details = {}
    try:
        validation = _validate_track_beatgrid(file_path, duration, bpm, float(anchor),
            grid_points=grid, head_audio=y, head_sr=sr, diagnostics=details)
        diagnostic = dict(reason='reference_verified' if validation.status == 'verified' else 'unknown',
                          stage='reference')
    except Exception as error:
        validation = BeatgridValidation('unverifiable', 0, -1.)
        diagnostic = dict(reason='estimationerror', stage='reference', error_type=type(error).__name__)
        logger.warning('Originalreferenzprüfung fehlgeschlagen: %s', type(error).__name__)
    return dict(anchor_s=float(anchor), bpm=reference_bpm, target_bpm=float(bpm),
        path_match=reference_path_match,
        measurement=measurement_snapshot(diagnostic, validation,
            decode_failures=details.get('decode_failures', ())))


def _native_grid_rotation_candidate(grid, native_context, bpm):
    """Erkennt einen moeglichen konstanten Taktlabelsprung als Messausloeser."""
    native = native_context.get('analysis') if type(native_context) is dict else None
    rows = native.get('grid') if type(native) is dict else None
    if (not isinstance(grid, (list, tuple)) or not isinstance(rows, list)
            or type(bpm) not in (int, float) or not math.isfinite(bpm) or bpm <= 0):
        return False
    beat_period = 60.0 / float(bpm)
    match_tolerance = min(0.08, beat_period * 0.12)
    native_rows = []
    previous_native_time = -1.0
    for row in rows:
        if (type(row) is not dict or type(row.get('pos')) is not int or row['pos'] < 0
                or type(row.get('numBar')) is not int or row['numBar'] not in (1, 2, 3, 4)):
            return False
        native_time = row['pos'] / 44100.0
        if native_time <= previous_native_time:
            return False
        native_rows.append((native_time, row))
        previous_native_time = native_time
    native_times = [item[0] for item in native_rows]
    rotations = [0, 0, 0, 0]
    matched = 0
    native_positions = set()
    reference_positions = set()
    previous_reference_time = -1.0
    for point in grid:
        if (type(point) is not dict or type(point.get('time')) not in (int, float)
                or not math.isfinite(point['time']) or point['time'] < 0
                or point['time'] <= previous_reference_time
                or type(point.get('beat')) is not int or point['beat'] not in (1, 2, 3, 4)):
            return False
        previous_reference_time = point['time']
        right_index = bisect_left(native_times, point['time'])
        nearby = native_rows[max(0, right_index - 1):min(len(native_rows), right_index + 1)]
        if not nearby:
            continue
        nearest_time, nearest = min(nearby, key=lambda item: abs(item[0] - point['time']))
        if abs(nearest_time - point['time']) > match_tolerance:
            continue
        rotation = (point['beat'] - nearest['numBar']) % 4
        rotations[rotation] += 1
        matched += 1
        native_positions.add(nearest['numBar'])
        reference_positions.add(point['beat'])
    if (matched < 4 or native_positions != {1, 2, 3, 4}
            or reference_positions != {1, 2, 3, 4}):
        return False
    dominant = max(range(4), key=rotations.__getitem__)
    # Dieselben Mindestpositionen wie eine gemessene Modellfensterzeile;
    # vollständige Übereinstimmung dient nur als Trigger, nie als Übernahme.
    return dominant != 0 and rotations[dominant] == matched


def _native_reference_candidate_windows(file_path, duration, bpm, y, sr, grid,
                                        reference_bpm, reference_path_match,
                                        native_context):
    """Sammle Zusatzfenster nur für Offset-/Taktrotations-Kandidaten."""
    reference = _reference_grid_attempt(
        file_path, duration, bpm, y, sr, grid, reference_bpm,
        reference_path_match,
    )
    reference_grid = reference['measurement']['grid'] if reference else {}
    phase_center_ms = reference_grid.get('phase_center_ms')
    offset_candidate = bool(
        reference_grid.get('status') == 'mismatch'
        and reference_grid.get('phase_pattern') == 'consistent_offset'
        and type(phase_center_ms) in (int, float)
        and math.isfinite(phase_center_ms)
    )
    rotation_candidate = bool(reference and
        reference_grid.get('status') == 'verified'
        and _native_grid_rotation_candidate(grid, native_context, bpm))
    if not (offset_candidate or rotation_candidate):
        return reference, []
    # Der native Gesamtpfad überspringt die HPG-Modellfenster normalerweise.
    # Bei Offset oder stabil abweichender Taktbeschriftung braucht der Resolver
    # aber getrennte Model7/8-Kandidaten für seine Audio-Bestätigungsgates.
    return reference, _collect_beat_windows(file_path, duration, y, sr)


def _unknown_bar_position_comparison(reason="reference_not_verified", windows=()):
    """Liefert eine strikt unbekannte Modell-gegen-PQTZ-Taktpositionsdiagnose."""
    return dict(status="unknown", reason=reason, rotation_beats=None,
                windows=list(windows),
                audio_confirmation=_unknown_bar_audio_confirmation())


def _compare_rekordbox_bar_positions(
    bpm, grid, beat_windows, *, grid_time_offset_seconds=0.0,
):
    """Vergleicht PQTZ-Taktpositionen mit vorhandenen Modellausgaben.

    Das Ergebnis ist nur ein Modellkandidat. Es aendert weder Anker noch Gate.
    Die Modellausgaben werden ohne Zeit-/Positionsverschiebung gematcht.
    """
    if (type(bpm) not in (int, float) or not math.isfinite(bpm) or bpm <= 0
            or type(grid_time_offset_seconds) not in (int, float)
            or not math.isfinite(grid_time_offset_seconds)
            or not isinstance(grid, (list, tuple)) or len(grid) < 4):
        return _unknown_bar_position_comparison("invalid_reference")

    ibi = 60.0 / float(bpm)
    rb_times, rb_positions = [], []
    previous_time = None
    previous_position = None
    for point in grid:
        if type(point) is not dict or set(point) != {"beat", "time"}:
            return _unknown_bar_position_comparison("invalid_reference")
        position, timestamp = point["beat"], point["time"]
        if (type(position) is not int or position not in {1, 2, 3, 4}
                or type(timestamp) not in (int, float) or not math.isfinite(timestamp)
                or timestamp < 0 or (previous_time is not None and timestamp <= previous_time)
                or (previous_position is not None and position != previous_position % 4 + 1)):
            return _unknown_bar_position_comparison("invalid_reference")
        if (previous_time is not None
                and abs((timestamp - previous_time) / ibi - 1.0) > BEATGRID_MAX_INTERVAL_DEVIATION):
            return _unknown_bar_position_comparison("invalid_reference")
        # Bei einem separat gemessenen konstanten Audio-minus-Grid-Versatz
        # werden Ticks nur fuer diesen Positionsvergleich in die Audiophase
        # projiziert. Der importierte Grid-Rohwert bleibt unberuehrt.
        rb_times.append(float(timestamp) + float(grid_time_offset_seconds))
        rb_positions.append(position)
        previous_time, previous_position = float(timestamp), position

    if (not isinstance(beat_windows, (list, tuple))
            or len(beat_windows) != BEATGRID_MIN_WINDOWS
            or any(type(window) is not dict for window in beat_windows)):
        return _unknown_bar_position_comparison("window_count")
    for window in beat_windows:
        start, duration = window.get("start_s"), window.get("duration_s")
        if (type(start) not in (int, float) or not math.isfinite(start)
                or type(duration) not in (int, float) or not math.isfinite(duration)
                or start < 0 or duration <= 0):
            return _unknown_bar_position_comparison("window_overlap")
    ordered_windows = sorted(beat_windows, key=lambda window: window["start_s"])
    previous_end = -1.0
    window_starts = set()
    for window in ordered_windows:
        start, duration = window.get("start_s"), window.get("duration_s")
        if (type(start) not in (int, float) or not math.isfinite(start)
                or type(duration) not in (int, float) or not math.isfinite(duration)
                or start < 0 or duration <= 0 or start < previous_end):
            return _unknown_bar_position_comparison("window_overlap")
        previous_end = start + duration
        window_starts.add(start)
    if len(window_starts) != BEATGRID_MIN_WINDOWS:
        return _unknown_bar_position_comparison("window_count")

    rows = []
    valid_rotations = set()
    saw_conflict = False
    for window in ordered_windows:
        results = window.get("results")
        by_model = ({item.get("model_id"): item for item in results
                     if type(item) is dict and type(item.get("model_id")) is str}
                    if isinstance(results, list) else {})
        for model_id in ("model7", "model8"):
            base = dict(model_id=model_id, start_s=float(window["start_s"]),
                        status="unavailable", matched_beats=0,
                        max_time_error_ms=None, rotation_beats=None,
                        decoder_positions=[], rekordbox_positions=[],
                        rotation_candidates=[])
            item = by_model.get(model_id)
            decoder = item.get("decoder") if item and item.get("status") == "ok" else None
            if (type(decoder) is not dict or decoder.get("status") != "ok" or decoder.get("ambiguous")
                    or not isinstance(decoder.get("beats"), list)):
                rows.append(base)
                continue

            observed = [event for event in decoder["beats"]
                        if type(event) is dict and event.get("observed") is True]
            direct = []
            used_rb = set()
            event_invalid = False
            for event in observed:
                timestamp, position = event.get("time_s"), event.get("position")
                if (type(timestamp) not in (int, float) or not math.isfinite(timestamp)
                        or type(position) is not int or position not in {1, 2, 3, 4}):
                    event_invalid = True
                    break
                lo, hi = 0, len(rb_times)
                while lo < hi:
                    middle = (lo + hi) // 2
                    if rb_times[middle] < timestamp:
                        lo = middle + 1
                    else:
                        hi = middle
                candidates = [index for index in (lo - 1, lo) if 0 <= index < len(rb_times)]
                if not candidates:
                    continue
                nearest = min(candidates, key=lambda index: abs(rb_times[index] - timestamp))
                error = abs(rb_times[nearest] - timestamp)
                if error > EXACT_BEAT_SYNC_TOLERANCE_SECONDS:
                    continue
                if nearest in used_rb:
                    event_invalid = True
                    break
                used_rb.add(nearest)
                direct.append((position, rb_positions[nearest], error))

            rotations = {(decoder_position - rb_position) % 4
                         for decoder_position, rb_position, _ in direct}
            decoder_positions = {decoder_position for decoder_position, _, _ in direct}
            rb_matched_positions = {rb_position for _, rb_position, _ in direct}
            base["matched_beats"] = len(direct)
            base["decoder_positions"] = sorted(decoder_positions)
            base["rekordbox_positions"] = sorted(rb_matched_positions)
            base["rotation_candidates"] = sorted(rotations)
            if direct:
                base["max_time_error_ms"] = round(max(error for _, _, error in direct) * 1000.0, 3)
            if event_invalid:
                base["status"] = "invalid_events"
            elif len(rotations) > 1:
                base["status"] = "conflict"
                saw_conflict = True
            elif (len(direct) < 4 or decoder_positions != {1, 2, 3, 4}
                    or rb_matched_positions != {1, 2, 3, 4}):
                base["status"] = "insufficient_matches"
            elif observed and len(direct) != len(observed):
                base["status"] = "time_mismatch"
            else:
                rotation = next(iter(rotations))
                base.update(status="measured", rotation_beats=rotation)
                valid_rotations.add(rotation)
            rows.append(base)

    if saw_conflict or len(valid_rotations) > 1:
        status, reason, rotation = "conflict", "rotation_disagreement", None
    elif len(rows) == 2 * BEATGRID_MIN_WINDOWS and all(row["status"] == "measured" for row in rows):
        rotation = next(iter(valid_rotations))
        status, reason = ("aligned", "measured") if rotation == 0 else ("candidate_rotation", "measured")
    else:
        status, reason, rotation = "unknown", "insufficient_evidence", None
    if reason == "measured" and grid_time_offset_seconds != 0.0:
        reason = "offset_compensated"
    return dict(status=status, reason=reason, rotation_beats=rotation, windows=rows,
                audio_confirmation=_unknown_bar_audio_confirmation())


def _unknown_bar_audio_confirmation(reason="not_attempted"):
    return dict(status="unknown", reason=reason, expected_anchor_s=None,
                final_grid_status="unknown", windows=[])


def _confirm_rekordbox_bar_rotation(
    file_path, duration, bpm, y, sr, rekordbox_anchor_s, beat_windows,
    comparison, *, grid_time_offset_seconds=0.0, independent_windows=False,
):
    """Bestaetigt Taktrotation oder Zeitversatz per Audio samt Gesamtgrid."""
    offset_candidate = (
        comparison.get("reason") == "offset_compensated"
        and comparison.get("status") in {"candidate_rotation", "aligned"}
    )
    regular_rotation = (
        comparison.get("reason") == "measured"
        and comparison.get("status") == "candidate_rotation"
    )
    if not (offset_candidate or regular_rotation):
        return _unknown_bar_audio_confirmation("no_rotation_candidate")
    if independent_windows is not True:
        return _unknown_bar_audio_confirmation("independent_windows_unavailable")
    rotation = comparison.get("rotation_beats")
    allowed_rotations = {0, 1, 2, 3} if offset_candidate else {1, 2, 3}
    if (type(rotation) is not int or rotation not in allowed_rotations
            or type(bpm) not in (int, float) or not math.isfinite(bpm) or bpm <= 0
            or type(rekordbox_anchor_s) not in (int, float)
            or not math.isfinite(rekordbox_anchor_s) or rekordbox_anchor_s < 0
            or type(grid_time_offset_seconds) not in (int, float)
            or not math.isfinite(grid_time_offset_seconds)):
        return _unknown_bar_audio_confirmation("invalid_candidate")
    ibi = 60.0 / float(bpm)
    bar = 4.0 * ibi
    raw_expected_anchor = (
        float(rekordbox_anchor_s) + float(grid_time_offset_seconds)
        - rotation * ibi
    )
    if offset_candidate and rotation == 0 and not 0.0 <= raw_expected_anchor < bar:
        return _unknown_bar_audio_confirmation("invalid_candidate")
    expected_anchor = raw_expected_anchor
    while expected_anchor < 0.0:
        expected_anchor += bar
    while expected_anchor >= bar:
        expected_anchor -= bar

    windows_by_start = {
        float(window["start_s"]): window
        for window in beat_windows if type(window) is dict
        and type(window.get("start_s")) in (int, float)
    }
    records = []
    comparisons = comparison.get("windows", [])
    if (len(comparisons) != 6
            or any(row.get("status") != "measured" for row in comparisons)):
        return _unknown_bar_audio_confirmation("incomplete_model_evidence")

    if independent_windows:
        if len(windows_by_start) != BEATGRID_MIN_WINDOWS:
            return _unknown_bar_audio_confirmation("incomplete_model_evidence")
        targets = [
            (model_id, window)
            for window in beat_windows
            for model_id in ("model7", "model8")
        ]
    else:
        targets = [
            (row["model_id"], windows_by_start.get(float(row["start_s"])))
            for row in comparisons
        ]

    confirmed_audio_windows = {}
    for model_id, source_window in targets:
        start = (float(source_window["start_s"])
                 if type(source_window) is dict else -1.0)
        record = dict(model_id=model_id, start_s=start, status="unavailable",
                      reason="window_unavailable", anchor_s=None,
                      confidence=None, phase_error_ms=None)
        records.append(record)
        if (source_window is None or source_window.get("status") != "evaluated"
                or type(source_window.get("duration_s")) not in (int, float)):
            continue
        results = source_window.get("results")
        matches = [item for item in results if type(item) is dict
                   and item.get("model_id") == model_id] if isinstance(results, list) else []
        if len(matches) != 1:
            record.update(status="unavailable", reason="model_unavailable")
            continue
        item = matches[0]
        decoder = item.get("decoder")
        decoder_bpm = decoder.get("bpm") if type(decoder) is dict else None
        if (item.get("status") != "ok" or type(decoder) is not dict
                or decoder.get("status") != "ok" or decoder.get("ambiguous")
                or type(decoder_bpm) not in (int, float)
                or not math.isfinite(decoder_bpm) or decoder_bpm <= 0
                or abs(decoder_bpm / bpm - 1.0) > BEATGRID_MAX_INTERVAL_DEVIATION):
            record.update(status="unavailable", reason="model_unavailable")
            continue

        width = float(source_window["duration_s"])
        try:
            rate = int(sr)
            first = int(start * rate)
            count = int(width * rate)
            retained_audio = (source_window.get("_audio")
                              if independent_windows and type(source_window) is dict else None)
            if isinstance(retained_audio, np.ndarray):
                rate = 44100
                count = int(width * rate)
            if (isinstance(retained_audio, np.ndarray)
                    and retained_audio.ndim == 1 and len(retained_audio) == count):
                audio = retained_audio
                audio_start = start
            elif rate > 0 and y is not None and len(y) >= first + count:
                audio = np.asarray(y)[first:first + count]
                audio_start = first / rate
            else:
                rate = 44100
                audio, loaded_rate = _load_analysis_audio(
                    file_path, sr=rate, offset=start, duration=width,
                    res_type="soxr_hq",
                )
                if loaded_rate != rate:
                    raise ValueError("source_rate")
                audio = np.asarray(audio)
                audio_start = start
                count = int(width * rate)
            if (audio.ndim != 1 or len(audio) != count
                    or not np.isfinite(audio).all()):
                raise ValueError("incomplete_audio_window")
            events = [
                dict(time_s=event["time_s"] - audio_start,
                     position=event["position"], observed=event["observed"])
                for event in decoder["beats"]
            ]
            downbeat = {}
            local_anchor, confidence = estimate_first_downbeat(
                audio, rate, bpm, external_beats=events,
                diagnostics=downbeat, _allow_metric_retry=False,
            )
            if (not math.isfinite(local_anchor) or not math.isfinite(confidence)
                    or not 0 <= local_anchor < len(audio) / rate
                    or not 0 <= confidence < 1):
                raise ValueError("invalid_audio_estimate")
            absolute_anchor = float(local_anchor + audio_start)
            phase_error = abs((absolute_anchor - expected_anchor + bar / 2.0) % bar - bar / 2.0)
            record.update(anchor_s=absolute_anchor, confidence=float(confidence),
                          phase_error_ms=round(phase_error * 1000.0, 3))
            if confidence < DOWNBEAT_RELIABLE_MIN:
                record.update(status="rejected", reason="weak_audio")
            elif phase_error > EXACT_BEAT_SYNC_TOLERANCE_SECONDS:
                record.update(status="rejected", reason="audio_phase_conflict")
            else:
                record.update(status="confirmed", reason="measured")
                if independent_windows:
                    if not isinstance(retained_audio, np.ndarray):
                        raise ValueError("independent_audio_missing")
                    confirmed_audio_windows[start] = retained_audio
        except Exception as error:
            record.update(status="error", reason="audio_error")
            logger.warning("Rekordbox-Taktkandidat %.3fs: %s", start, type(error).__name__)

    if len(records) != 6 or any(row["status"] != "confirmed" for row in records):
        reason = next((row["reason"] for row in records if row["status"] != "confirmed"),
                      "incomplete_model_evidence")
        return dict(status="rejected", reason=reason, expected_anchor_s=expected_anchor,
                    final_grid_status="not_checked", windows=records)

    final_details = {}
    try:
        if independent_windows:
            final = validate_beatgrid_windows(
                sorted(confirmed_audio_windows.items()), 44100, bpm,
                anchor=expected_anchor,
                collect_diagnostics=True,
            )
        else:
            final = _validate_track_beatgrid(
                file_path, duration, bpm, expected_anchor, head_audio=y,
                head_sr=sr, diagnostics=final_details,
            )
    except Exception as error:
        logger.warning("Rekordbox-Taktkandidat-Gesamtgrid: %s", type(error).__name__)
        return dict(status="error", reason="final_grid_error",
                    expected_anchor_s=expected_anchor, final_grid_status="unknown",
                    windows=records)
    if final.status != "verified":
        return dict(status="rejected", reason="final_grid_rejected",
                    expected_anchor_s=expected_anchor,
                    final_grid_status=final.status, windows=records)
    confirmation = dict(status="audio_confirmed", reason="measured",
                        expected_anchor_s=expected_anchor,
                        final_grid_status=final.status, windows=records)
    if independent_windows:
        confirmation["_final_validation"] = final
        confirmation["_final_details"] = final_details
        confirmation["_final_downbeat"] = dict(
            reason="external_alignment", stage="external_alignment",
            beats_detected=0, beats_used=0,
        )
    return confirmation


def _resolve_track_tempo(file_path, duration, bpm, y, sr, grid, windows, *, reference_bpm=None,
                         reference_path_match="unknown"):
    """Beide Modelle und unabhängige Audioprüfung müssen das neue Tempo tragen."""
    reference = _reference_grid_attempt(file_path, duration, bpm, y, sr, grid,
        reference_bpm, reference_path_match)
    transient = bool(reference and (reference['measurement']['grid']['decode_failures']
        or reference['measurement']['downbeat']['reason'] == 'estimationerror'))
    baseline = (bpm, reference, transient)
    model_samples = []

    def baseline_result(reason, *, model_bpm=None, refined_bpm=None,
                        model_spread=None, transient_result=None):
        if len(model_samples) == 6:
            sample_tempos = [sample['bpm'] for sample in model_samples]
            if model_bpm is None:
                model_bpm = float(np.median(sample_tempos))
            if model_spread is None:
                model_spread = max(sample_tempos) / min(sample_tempos) - 1.
        diagnostic = dict(
            status='baseline', reason=reason, model_bpm=model_bpm,
            refined_bpm=refined_bpm, model_spread=model_spread,
            model_samples=[dict(sample) for sample in model_samples],
        )
        return (*baseline[:2], transient if transient_result is None else transient_result,
                diagnostic)

    if transient or (reference and reference['measurement']['grid']['status'] == 'verified'):
        return baseline_result('reference_error' if transient else 'reference_verified')
    try:
        if len(windows) != BEATGRID_MIN_WINDOWS:
            return baseline_result('window_count')
        end, tempos = -1., []
        for window in windows:
            if window['status'] != 'evaluated' or window['start_s'] < end:
                return baseline_result('window_unavailable')
            end = window['start_s'] + window['duration_s']
            models = {item['model_id']: item for item in window['results']}
            if len(window['results']) != 2 or set(models) != {'model7', 'model8'}:
                return baseline_result('model_set_invalid')
            for model in ('model7', 'model8'):
                item, decoder = models[model], models[model].get('decoder')
                if (item['status'] != 'ok' or not decoder or decoder['status'] != 'ok'
                        or decoder['ambiguous']):
                    return baseline_result('model_unavailable')
                value = decoder['bpm']
                if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                    return baseline_result('model_bpm_invalid')
                tempos.append(float(value))
                model_samples.append(dict(
                    model_id=model, start_s=float(window['start_s']),
                    bpm=float(value),
                ))
        # Bereits geltende 2%-Intervalltoleranz; kein neues Modellgewicht.
        tempo_spread = max(tempos) / min(tempos) - 1.
        candidate = float(np.median(tempos))
        if tempo_spread > BEATGRID_MAX_INTERVAL_DEVIATION:
            logger.info(
                "Neuronales Tempo verworfen: Modellfenster widersprechen sich "
                "(min=%.6f, max=%.6f BPM, spread=%.4f%%, Grenze=%.4f%%)",
                min(tempos), max(tempos), tempo_spread * 100.,
                BEATGRID_MAX_INTERVAL_DEVIATION * 100.,
            )
            return baseline_result(
                'model_disagreement', model_bpm=candidate,
                model_spread=tempo_spread,
            )
        # Alle sechs Modellwerte tragen gleichberechtigt; der Median vermeidet
        # eine Abhaengigkeit von Fenster- und Modellreihenfolge. DSP-Refinement
        # und das unabhaengige Gesamtgrid bleiben die Uebernahme-Gates.
        diagnostic_values = dict(model_bpm=candidate, model_spread=tempo_spread)
        if candidate == bpm:
            return baseline_result('candidate_matches_baseline', **diagnostic_values)
        detail = {}
        refined = _refine_audio_tempo(y, sr, candidate, file_path=file_path,
                                     duration=duration, diagnostics=detail)
        if detail.get('reason') not in {'accepted', 'prior_verified'}:
            return baseline_result(
                'audio_refinement_rejected', **diagnostic_values,
                transient_result=transient or detail.get('reason') in {'decode_error', 'estimation_error'},
            )
        if (not math.isfinite(refined) or refined <= 0
                or any(abs(refined / value - 1.) > BEATGRID_MAX_INTERVAL_DEVIATION for value in tempos)):
            return baseline_result(
                'refined_tempo_invalid', refined_bpm=float(refined)
                if math.isfinite(refined) else None, **diagnostic_values,
            )
        phase, lock = _beat_phase_from_fold(
            np.asarray(y[:int(TEMPO_TRAINING_SECONDS*sr)], dtype=np.float64), sr, 60./refined)
        if phase is None or not math.isfinite(phase) or not math.isfinite(lock) or lock < BEATGRID_MIN_FOLD_LOCK:
            return baseline_result(
                'audio_phase_unlocked', refined_bpm=float(refined), **diagnostic_values,
            )
        details = {}
        validation = _validate_track_beatgrid(file_path, duration, refined, phase,
            head_audio=y, head_sr=sr, diagnostics=details)
        if details.get('decode_failures'):
            return baseline_result(
                'final_grid_decode_error', refined_bpm=float(refined),
                transient_result=True, **diagnostic_values,
            )
        if validation.status != 'verified':
            return baseline_result(
                'final_grid_unverified', refined_bpm=float(refined), **diagnostic_values,
            )
        logger.info('Neuronales Tempo durch beide Modelle und Audio bestätigt: %.9f -> %.9f', bpm, refined)
        return float(refined), reference, transient, dict(
            status='accepted', reason='accepted', model_bpm=candidate,
            refined_bpm=float(refined), model_spread=tempo_spread,
            model_samples=[dict(sample) for sample in model_samples],
        )
    except Exception as error:
        logger.warning('Neuronale Tempoprüfung fehlgeschlagen: %s', type(error).__name__)
        return baseline_result('resolver_error', transient_result=True)


def _classify_bar_position_status(source, confidence, native_accepted, usage_blocked,
                                  comparison=None):
    """Takt-1 nur freigeben, wenn das RB-Grid nicht widersprochen bekommt."""
    if usage_blocked:
        return "blocked"
    if source == "rekordbox" and confidence == 1.0:
        if isinstance(comparison, dict) and comparison.get("status") == "aligned":
            return "reference_verified"
        return "reference_candidate"
    if confidence >= DOWNBEAT_RELIABLE_MIN:
        return "audio_estimate"
    if native_accepted:
        return "native_candidate"
    return "unknown"


def _phrase_phase_usable(source, status, usage_blocked, grid_usable):
    """Native Taktposition nach Nutzerfreigabe nutzen; Bestätigungsstatus bleibt erhalten."""
    return bool(
        grid_usable
        and not usage_blocked
        and status not in {
            "reference_candidate", "blocked", "unknown",
        }
        and not (source == "rekordbox" and status != "reference_verified")
    )


def _resolve_track_anchor(file_path, duration, bpm, y, sr, rekordbox_grid,
                          beat_windows, *, reference_bpm=None, reference_attempt=None,
                          phrase_unit=None, reference_path_match="unknown", native_context=None):
    """Importiertes Grid bevorzugen; bestätigte native Analyse als Kandidat nutzen."""
    if native_context is not None and native_context.get('accepted'):
        native = native_context['analysis']
        if bpm != native['bpm']:
            raise ValueError('Native beat tempo changed before anchor adoption')
        # Ein importiertes Rekordbox-Grid hat Vorrang, wenn es am Quellaudio
        # bestätigt wird. Der native Audioanker bleibt Fallback bei fehlender
        # oder nicht bestätigter Referenz.
        reference = reference_attempt
        if reference is None:
            reference = _reference_grid_attempt(file_path, duration, bpm, y, sr,
                rekordbox_grid, reference_bpm, reference_path_match)
        if reference and reference['measurement']['grid']['status'] == 'verified':
            native_context['accepted'] = False
            native_context['decision'] = dict(status='rejected', reason='reference_preferred')
            native_context = None
            reference_attempt = reference
        else:
            # Die native Analyse ist am Quellaudio auf getrennten Fenstern
            # bestätigt. Nutze ihre eigene Takt-Eins als Rekordbox-Kandidat;
            # sie bleibt als native_candidate gekennzeichnet und wird damit
            # nicht als unabhängig geprüfte musikalische Wahrheit ausgegeben.
            from .ai_models.native_beat_alignment import active_anchor
            anchor = active_anchor(native)
            validation = native_context['validation']
            details = native_context.get('diagnostics') or {}
            diagnostic = details.get('downbeat') or dict(
                reason='external_alignment', stage='external_alignment',
                beats_detected=0, beats_used=0,
            )
            aligned = 'audio_alignment' in native
            method = ('native_rekordbox_audio_offset' if aligned
                      else 'native_rekordbox')
            decision = dict(
                source='audio', method=method, anchor_s=anchor, confidence=0.,
                reference=reference,
                bar_position_comparison=_unknown_bar_position_comparison(),
                neural=dict(
                    reason='native_offset_adopted' if aligned else 'native_adopted',
                    transient=False, windows=[], candidate_anchor_s=anchor,
                ),
            )
            baseline = (anchor, 0., 'audio', validation, diagnostic, details, decision)
            return (*baseline, None)
    reference = reference_attempt
    if reference is None:
        reference = _reference_grid_attempt(file_path, duration, bpm, y, sr,
            rekordbox_grid, reference_bpm, reference_path_match)
    if reference and reference['measurement']['grid']['status'] == 'verified':
        bar_comparison = _compare_rekordbox_bar_positions(bpm, rekordbox_grid, beat_windows)
        grid = reference['measurement']['grid']
        validation = BeatgridValidation(**{key: value for key, value in grid.items() if key != 'decode_failures'})
        diagnostic = reference['measurement']['downbeat']
        details = dict(decode_failures=grid['decode_failures'])
        anchor = reference['anchor_s']
        decision = dict(source='rekordbox', method='rekordbox', anchor_s=anchor,
            confidence=1., reference=reference,
            bar_position_comparison=bar_comparison,
            neural=dict(reason='reference_preferred', transient=False, windows=[], candidate_anchor_s=None))
        confirmation = _unknown_bar_audio_confirmation('no_rotation_candidate')
        if bar_comparison.get('status') == 'candidate_rotation':
            span = min(_BEATGRID_WINDOW_SECONDS, float(duration))
            independent_starts = _offset_confirmation_starts(
                duration, span, grid, beat_windows,
            )
            if len(independent_starts) == BEATGRID_MIN_WINDOWS:
                confirmation_windows = _collect_beat_windows(
                    file_path, duration, y, sr,
                    window_starts=independent_starts, retain_audio=True,
                )
                confirmation = _confirm_rekordbox_bar_rotation(
                    file_path, duration, bpm, y, sr, reference['anchor_s'],
                    confirmation_windows, bar_comparison,
                    independent_windows=True,
                )
            else:
                confirmation = _unknown_bar_audio_confirmation(
                    'independent_windows_unavailable',
                )
        bar_comparison['audio_confirmation'] = confirmation
        if confirmation['status'] == 'audio_confirmed':
            # Modellkandidat und Audio-Bestaetigung nutzen disjunkte Quellfenster.
            # Der korrigierte Anker bleibt Audioherkunft; PSSI und Rekordbox-
            # Render-Sync behandeln ihn nicht als unveraenderten RB-Anker.
            final_validation = confirmation.pop('_final_validation')
            final_details = confirmation.pop('_final_details')
            downbeat_diagnostic = confirmation.pop('_final_downbeat')
            corrected_anchor = confirmation['expected_anchor_s']
            confidence = min(row['confidence'] for row in confirmation['windows'])
            decision.update(
                source='audio', method='model_audio_rotation',
                anchor_s=corrected_anchor, confidence=confidence,
                neural=dict(
                    reason='bar_rotation_adopted', transient=False,
                    windows=[], candidate_anchor_s=corrected_anchor,
                ),
            )
            return (corrected_anchor, confidence, 'audio', final_validation,
                    downbeat_diagnostic, final_details, decision, None)
        return anchor, 1., 'rekordbox', validation, diagnostic, details, decision, None

    diagnostic, details = {}, {}
    anchor, confidence = _estimate_audio_downbeat(y, sr, bpm, file_path=file_path,
                                                 duration=duration, diagnostics=diagnostic)
    validation = _validate_track_beatgrid(file_path, duration, bpm, anchor,
                                         head_audio=y, head_sr=sr, diagnostics=details)
    neural = dict(reason='no_candidates', transient=bool(details.get('decode_failures') or
        (reference and reference['measurement']['grid']['decode_failures'])), windows=[], candidate_anchor_s=None)
    phase_grid = reference['measurement']['grid'] if reference else None
    if (isinstance(phase_grid, dict)
            and phase_grid.get('status') == 'mismatch'
            and phase_grid.get('phase_pattern') == 'consistent_offset'):
        # Der gemessene konstante Zeitversatz darf Modellpositionen gegen das
        # phasenprojizierte Referenzgrid vergleichen. Erst der unten ausgefuehrte
        # disjunkte Modell-/Audiowindowsatz darf den Kandidaten bestaetigen.
        phase_center_ms = phase_grid.get('phase_center_ms')
        if (type(phase_center_ms) in (int, float) and math.isfinite(phase_center_ms)):
            bar_comparison = _compare_rekordbox_bar_positions(
                bpm, rekordbox_grid, beat_windows,
                grid_time_offset_seconds=phase_center_ms / 1000.0,
            )
        else:
            bar_comparison = _unknown_bar_position_comparison('reference_constant_offset')
    else:
        bar_comparison = _unknown_bar_position_comparison()
    decision = dict(source='audio', method='dsp', anchor_s=float(anchor), confidence=float(confidence),
                    reference=reference,
                    bar_position_comparison=bar_comparison, neural=neural)
    baseline = (anchor, confidence, 'audio', validation, diagnostic, details, decision)
    if (reference is not None
            and bar_comparison.get('status') in {'candidate_rotation', 'aligned'}
            and bar_comparison.get('reason') == 'offset_compensated'):
        span = min(_BEATGRID_WINDOW_SECONDS, float(duration))
        independent_starts = _offset_confirmation_starts(
            duration, span, phase_grid, beat_windows,
        )
        if len(independent_starts) == BEATGRID_MIN_WINDOWS:
            confirmation_windows = _collect_beat_windows(
                file_path, duration, y, sr,
                window_starts=independent_starts, retain_audio=True,
            )
            phase_offset = float(phase_grid['phase_center_ms']) / 1000.0
            confirmation = _confirm_rekordbox_bar_rotation(
                file_path, duration, bpm, y, sr, reference['anchor_s'],
                confirmation_windows, bar_comparison,
                grid_time_offset_seconds=phase_offset,
                independent_windows=True,
            )
            bar_comparison['audio_confirmation'] = confirmation
            if confirmation.get('status') == 'audio_confirmed':
                final_validation = confirmation.pop('_final_validation')
                final_details = confirmation.pop('_final_details')
                downbeat_diagnostic = confirmation.pop('_final_downbeat')
                corrected_anchor = confirmation['expected_anchor_s']
                corrected_confidence = min(
                    row['confidence'] for row in confirmation['windows']
                )
                phase_only = bar_comparison.get('rotation_beats') == 0
                decision.update(
                    source='audio',
                    method='model_audio_phase_offset' if phase_only else 'model_audio_rotation',
                    anchor_s=corrected_anchor, confidence=corrected_confidence,
                    neural=dict(
                        reason='phase_offset_adopted' if phase_only else 'bar_rotation_adopted', transient=False,
                        windows=[], candidate_anchor_s=corrected_anchor,
                    ),
                )
                return (corrected_anchor, corrected_confidence, 'audio',
                        final_validation, downbeat_diagnostic, final_details,
                        decision, None)
        else:
            bar_comparison['audio_confirmation'] = _unknown_bar_audio_confirmation(
                'independent_windows_unavailable',
            )
    baseline_phrase = None
    if confidence >= DOWNBEAT_RELIABLE_MIN and validation.status == 'verified':
        if phrase_unit is not None:
            try:
                first_phrase, phrase_confidence = estimate_first_phrase(y, sr, bpm, anchor, phrase_unit)
                baseline_phrase = (first_phrase, phrase_confidence)
            except Exception as error:
                neural['transient'] = True
                logger.warning('Baseline-Phrasenprüfung fehlgeschlagen: %s', type(error).__name__)
        model_candidates_available = any(
            window.get('status') == 'evaluated'
            and any(item.get('status') == 'ok'
                    and isinstance(item.get('decoder'), dict)
                    and item['decoder'].get('status') == 'ok'
                    for item in window.get('results', ()))
            for window in beat_windows
        )
        if not model_candidates_available and (phrase_unit is None or (
                baseline_phrase is not None and baseline_phrase[1] >= PHRASE_CONFIDENCE_MIN)):
            # Phrasenkonfidenz bestaetigt keine musikalische Takt-Eins.
            # Vorhandene Modellkandidaten immer gegen Audio pruefen, auch
            # wenn das regulaere DSP-Raster bereits technisch verifiziert ist.
            neural['reason'] = 'baseline_preferred'
            return (*baseline, baseline_phrase)

    return _resolve_model_audio_anchor(
        file_path, duration, bpm, y, sr, beat_windows, baseline, baseline_phrase)


def _resolve_model_audio_anchor(file_path, duration, bpm, y, sr, beat_windows,
                                baseline, baseline_phrase, *, phase_method='bass_fold'):
    """Gemeinsame sechs Modell-/Audiobelege für native und bisherige Anker."""
    decision = baseline[6]
    neural = decision['neural']
    supported = []
    for window in beat_windows:
        start, width = window['start_s'], window['duration_s']
        if window['status'] != 'evaluated':
            neural['windows'].append(dict(model_id=None, start_s=start, duration_s=width,
                reason='window_unavailable', input_status=window['status'], input_reason=window.get('reason'),
                anchor_s=None, confidence=None, downbeat={}))
            continue
        audio = None
        for item in window['results']:
            record = dict(model_id=item['model_id'], start_s=start, duration_s=width,
                          reason='model_unavailable', input_status=item['status'], input_reason=item.get('reason'),
                          anchor_s=None, confidence=None, downbeat={})
            neural['windows'].append(record)
            decoder = item.get('decoder')
            if item['status'] != 'ok' or not decoder or decoder['status'] != 'ok':
                continue
            if decoder['ambiguous']:
                record['reason'] = 'ambiguous'
                continue
            if abs(decoder['bpm'] / bpm - 1.) > BEATGRID_MAX_INTERVAL_DEVIATION:
                record['reason'] = 'tempo_mismatch'
                continue
            try:
                if audio is None:
                    # Das Audio-Voting darf den DSP-Head verwenden. Sein echter
                    # Sampleoffset bleibt beim Lokalisieren der Modellzeiten erhalten.
                    rate = int(sr)
                    first = int(start * rate)
                    count = int(width * rate)
                    if rate > 0 and y is not None and len(y) >= first + count:
                        audio = np.asarray(y)[first:first+count]
                        audio_start = first / rate
                    else:
                        rate = 44100
                        audio, loaded_rate = _load_analysis_audio(
                            file_path, sr=rate, offset=start, duration=width,
                            res_type='soxr_hq',
                        )
                        if loaded_rate != rate:
                            raise ValueError('source_rate')
                        audio = np.asarray(audio)
                        audio_start = start
                        count = int(width * rate)
                    if (audio.ndim != 1 or len(audio) != count or not np.isfinite(audio).all()):
                        raise ValueError('incomplete_audio_window')
                events = [dict(time_s=e['time_s']-audio_start, position=e['position'], observed=e['observed'])
                          for e in decoder['beats']]
                local = {}
                local_anchor, local_confidence = estimate_first_downbeat(audio, rate, bpm,
                    external_beats=events, diagnostics=local, _allow_metric_retry=False,
                    # Native Bestätigung darf eine vom Modell abweichende
                    # Audio-Taktphase nicht als Modellzustimmung verbuchen.
                    _allow_external_conflict_candidate=phase_method != 'native_attack_v1',
                    **({'phase_method': phase_method} if phase_method != 'bass_fold' else {}))
                record['downbeat'] = local
                if local.get('reason') == 'estimationerror':
                    neural['transient'] = True
                record['confidence'] = float(local_confidence)
                record['anchor_s'] = float(local_anchor + audio_start)
                if (not math.isfinite(local_anchor) or not math.isfinite(local_confidence)
                        or not 0 <= local_anchor < len(audio)/rate or not 0 <= local_confidence < 1):
                    raise ValueError('invalid_audio_estimate')
                if local_confidence < DOWNBEAT_RELIABLE_MIN:
                    record['reason'] = 'weak_audio'
                    continue
                record['reason'] = 'confirmed'
                supported.append(record)
            except Exception as error:
                record.update(reason='audio_error', anchor_s=None, confidence=None, downbeat={})
                neural['transient'] = True
                logger.warning('Neuronale Taktprüfung %.3fs: %s', start, type(error).__name__)

    if not supported:
        neural['reason'] = 'insufficient_evidence'
        return (*baseline, baseline_phrase)
    # Auch ein einzelner belastbarer Widerspruch des anderen Modells sperrt.
    bar = 4. * 60. / bpm
    for index, left in enumerate(supported):
        for right in supported[index+1:]:
            distance = abs((left['anchor_s']-right['anchor_s']+bar/2) % bar-bar/2)
            if distance > EXACT_BEAT_SYNC_TOLERANCE_SECONDS:
                neural['reason'] = 'bar_conflict'
                return (*baseline, baseline_phrase)
    eligible_models = set()
    for model in ('model7', 'model8'):
        distinct = sorted((r for r in supported if r['model_id'] == model), key=lambda r: r['start_s'])
        end, count = -1., 0
        for record in distinct:
            if record['start_s'] >= end:
                count += 1
                end = record['start_s'] + record['duration_s']
        if count >= BEATGRID_MIN_WINDOWS:
            eligible_models.add(model)
    if eligible_models != {'model7', 'model8'}:
        neural['reason'] = 'insufficient_windows'
        return (*baseline, baseline_phrase)
    winner = min(supported, key=lambda r: (r['anchor_s'], r['model_id']))
    selected_anchor = winner['anchor_s']
    neural['candidate_anchor_s'] = selected_anchor
    final_details = {}
    try:
        final = _validate_track_beatgrid(file_path, duration, bpm, selected_anchor,
            head_audio=y, head_sr=sr, diagnostics=final_details, phase_method=phase_method)
    except Exception as error:
        neural.update(reason='final_grid_error', transient=True)
        logger.warning('Neuronale Gesamtgridprüfung: %s', type(error).__name__)
        return (*baseline, baseline_phrase)
    if final_details.get('decode_failures'):
        neural['transient'] = True
    if final.status != 'verified':
        neural['reason'] = 'final_grid_rejected'
        return (*baseline, baseline_phrase)
    confidence = min(record['confidence'] for record in supported)
    neural['reason'] = 'adopted'
    decision.update(method='neural_audio', anchor_s=selected_anchor, confidence=confidence)
    return selected_anchor, confidence, 'audio', final, winner['downbeat'], final_details, decision, None


def _offset_confirmation_starts(duration, span, reference_grid, candidate_windows=(), *, eligible=None):
    """Waehlt drei Audiofenster ausserhalb von Referenz und Modellkandidat."""
    if (type(duration) not in (int, float) or not math.isfinite(duration)
            or type(span) not in (int, float) or not math.isfinite(span)
            or duration <= 0 or span <= 0 or duration < span):
        return ()
    diagnostics = reference_grid.get('window_diagnostics') if type(reference_grid) is dict else None
    if not isinstance(diagnostics, (list, tuple)) or len(diagnostics) != BEATGRID_MIN_WINDOWS:
        return ()
    excluded = []
    for item in diagnostics:
        if type(item) is not dict:
            return ()
        start, width = item.get('offset_seconds'), item.get('duration_seconds')
        if (type(start) not in (int, float) or not math.isfinite(start)
                or type(width) not in (int, float) or not math.isfinite(width)
                or start < 0 or width <= 0 or start + width > duration + 1e-6):
            return ()
        excluded.append((float(start), float(start + width)))
    if len(candidate_windows) != BEATGRID_MIN_WINDOWS:
        return ()
    for item in candidate_windows:
        if type(item) is not dict:
            return ()
        start, width = item.get('start_s'), item.get('duration_s')
        if (type(start) not in (int, float) or not math.isfinite(start)
                or type(width) not in (int, float) or not math.isfinite(width)
                or start < 0 or width <= 0 or start + width > duration + 1e-6):
            return ()
        excluded.append((float(start), float(start + width)))
    ordered = sorted(excluded)
    merged = []
    for start, end in ordered:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    last_start = int(math.floor(duration - span))
    candidates = [
        float(start) for start in range(max(0, last_start + 1))
        if (eligible is None or eligible(float(start), span)) and all(start + span <= left or start >= right
               for left, right in merged)
    ]
    chosen = []
    for target in (duration * 0.2, duration * 0.5, duration * 0.8):
        available = [start for start in candidates
                     if all(start + span <= other or start >= other + span
                            for other in chosen)]
        if not available:
            return ()
        selected = min(available, key=lambda start: (abs(start - target), start))
        chosen.append(selected)
    return tuple(sorted(chosen)) if len(chosen) == BEATGRID_MIN_WINDOWS else ()


def _prepare_native_beats(file_path, duration, y, sr, *, snapshot=None):
    """Native Gesamtanalyse vor alten Modellfenstern; Audio-Synchronsperre bleibt."""
    from .ai_models import native_track_beats
    if not native_track_beats.enabled():
        return dict(analysis=dict(status='disabled', reason='disabled'), accepted=False,
                    transient=False, decision=dict(status='disabled', reason='disabled'))
    # Der Native-Reader und Snapshotvertrag begrenzen lange Quellen auf zwei
    # Stunden; oberhalb davon früh zum bestehenden HPG-Pfad zurückfallen.
    from .ai_models.native_beat_selection import MAX_NATIVE_BEAT_SECONDS
    if duration < 1.0 or duration > MAX_NATIVE_BEAT_SECONDS:
        return dict(analysis=dict(status='unavailable', reason='unsupported_native_duration'),
                    accepted=False, transient=False,
                    decision=dict(status='unavailable', reason='unsupported_duration'))
    try:
        with cue_service.session() as client:
            from .ai_models.native_beat_selection import native_track_job_timeout_seconds
            native = native_track_beats.analyze(
                file_path, timeout_s=native_track_job_timeout_seconds(duration),
                **({'snapshot': snapshot} if snapshot is not None else {}),
                transport=getattr(client, 'native_beats', None))
        if type(native) is not dict:
            raise ValueError('invalid_native_result_type')
        if native.get('status') == 'ok':
            try:
                native_track_beats.validate_snapshot(native, duration=duration)
            except Exception as error:
                # Ein formal unpassender nativer Snapshot ist dauerhaft fuer
                # diesen Lauf unbrauchbar, aber kein transienter Workerfehler.
                # Die bestehende HPG-Analyse muss mit ihrem Audiofallback
                # weiterlaufen und darf den Track danach normal cachen.
                reason = f'invalid_native_snapshot:{type(error).__name__}'
                return dict(analysis=dict(status='unavailable', reason=reason),
                            accepted=False, transient=False,
                            decision=dict(status='unavailable', reason=reason))
    except Exception as error:
        # Start-, Transport- und Vertragsfehler des nativen Pfads dürfen die
        # normale HPG-Analyse nicht abbrechen.
        reason = f'native_path_unavailable:{type(error).__name__}'
        return dict(analysis=dict(status='unavailable', reason=reason),
                    accepted=False, transient=True,
                    decision=dict(status='unavailable', reason=reason))
    context = dict(analysis=native, accepted=False,
                   transient=native.get('status') == 'unavailable' and native.get('reason') != 'unsupported_source_format',
                   decision=dict(status=(native.get('status') if native.get('status') in
                       ('disabled', 'unavailable') else 'rejected'),
                       reason=('native_unavailable' if native.get('status') == 'unavailable'
                               else 'disabled' if native.get('status') == 'disabled'
                               else 'grid_unverified')))
    if native.get('status') != 'ok':
        return context
    native['phase_method'] = 'native_attack_v1'
    period = 60. / native['bpm']
    first = native['grid'][0]['pos'] / 44100
    if any(abs(row['pos']/44100 - (first + index*period)) > EXACT_BEAT_SYNC_TOLERANCE_SECONDS
           for index, row in enumerate(native['grid'])):
        # HPGs aktueller Renderer verwendet ein konstantes Raster. Ein natives
        # variables Grid bleibt erhalten, wird aber nicht still begradigt.
        context['decision']['reason'] = 'variable_grid_unsupported'
        return context
    from .ai_models.native_beat_alignment import single_window_evidence_plan
    evidence_plan = single_window_evidence_plan(native, duration, _BEATGRID_WINDOW_SECONDS)
    details = {}
    validation = _validate_track_beatgrid(file_path, duration, native['bpm'],
        native['first_downbeat'], head_audio=y, head_sr=sr, diagnostics=details,
        phase_method=native['phase_method'],
        **({'window_starts': evidence_plan[0]} if evidence_plan else {}),
        grid_points=[dict(time=row['pos']/44100, beat=row['numBar']) for row in native['grid']])
    context.update(accepted=validation.status == 'verified', validation=validation, diagnostics=details)
    if validation.status == 'verified':
        context['decision'] = dict(status='accepted', reason='verified')
    if (validation.status == 'mismatch' and validation.phase_pattern == 'consistent_offset'
            and validation.phase_center_ms is not None):
        from dataclasses import asdict
        from .ai_models.native_beat_alignment import validate_alignment, stable_model_window
        shift = validation.phase_center_ms / 1000.
        if not EXACT_BEAT_SYNC_TOLERANCE_SECONDS < abs(shift) < period / 4:
            context['decision'] = dict(status='rejected', reason='offset_out_of_range')
            return context
        records = [asdict(row) for row in validation.window_diagnostics]
        span = _BEATGRID_WINDOW_SECONDS
        starts = evidence_plan[1] if evidence_plan else _offset_confirmation_starts(duration, span,
            {'window_diagnostics': records},
            [dict(start_s=r['offset_seconds'], duration_s=r['duration_seconds']) for r in records],
            eligible=lambda start, width: stable_model_window(native, start, width))
        if len(starts) != BEATGRID_MIN_WINDOWS:
            context['decision'] = dict(status='rejected', reason='offset_confirmation_windows_missing')
            return context
        windows = []
        try:
            for start in starts:
                audio, loaded_sr = _load_analysis_audio(
                    file_path, sr=sr, offset=start, duration=span
                )
                if loaded_sr != sr:
                    context['decision'] = dict(status='rejected', reason='offset_audio_decode_failed')
                    return context
                windows.append((start, audio))
            confirmation = validate_beatgrid_windows(windows, sr, native['bpm'],
                anchor=native['first_downbeat'] + shift,
                grid_times=[r['pos']/44100 + shift for r in native['grid']],
                collect_diagnostics=True, phase_method=native['phase_method'])
            alignment = dict(offset_seconds=shift, calibration=records,
                confirmation=[asdict(r) for r in confirmation.window_diagnostics])
            if confirmation.status != 'verified':
                context['decision'] = dict(status='rejected', reason='offset_audio_confirmation_failed')
                return context
            validate_alignment(native, alignment)
        except (OSError, RuntimeError, ValueError, sf.LibsndfileError):
            context['decision'] = dict(status='rejected', reason='offset_audio_decode_failed')
            return context
        native['audio_alignment'] = alignment
        context.update(accepted=True, validation=confirmation)
        context['decision'] = dict(status='accepted', reason='audio_offset_confirmed')
    return context


def _collect_beat_windows(
    file_path, duration, head_audio, head_sr, *, window_starts=None,
    retain_audio=False,
):
    """Bis drei getrennte Quellfenster; ausschließlich unverifizierte Kandidaten.

    Ein 22050-Hz-Head hat Hochfrequenzanteile bereits verloren und wird niemals
    für diese Modelle hochgesampelt. Wiederverwendung nur bei echten 44100 Hz.
    """
    span = min(_BEATGRID_WINDOW_SECONDS, float(duration))
    if not math.isfinite(span) or span <= 0:
        return []
    requested_starts = (
        (0., max(0., duration / 2 - span / 2), max(0., duration - span))
        if window_starts is None else tuple(window_starts)
    )
    starts = tuple(dict.fromkeys(int(offset * 44100) for offset in requested_starts))
    windows = []
    for sample_start in starts:
        offset = sample_start / 44100
        count = int(min(span, duration - offset) * 44100)
        requested_duration = count / 44100
        window = dict(start_s=offset, duration_s=requested_duration,
                      status='unavailable', reason='insufficient_audio', results=[])
        if count < 44100:
            if requested_duration > 0:
                windows.append(window)
            continue
        try:
            if head_sr == 44100 and head_audio is not None and len(head_audio) >= sample_start + count:
                audio = np.asarray(head_audio)[sample_start:sample_start+count]
                sample_rate = 44100
            else:
                audio, sample_rate = _load_analysis_audio(
                    file_path, sr=44100, offset=offset,
                    duration=requested_duration, res_type='soxr_hq',
                )
                audio = np.asarray(audio)[:count]
            if (sample_rate != 44100 or audio.ndim != 1 or audio.dtype.kind != 'f'
                    or len(audio) < count - 1 or not np.isfinite(audio).all()):
                raise ValueError('incomplete_or_invalid_source_window')
            if retain_audio:
                window['_audio'] = np.asarray(audio[:count], dtype=np.float32)
            if len(audio) < 44100:
                windows.append(window)
                continue
            with cue_service.session() as client:
                result = client.score_beats(audio, 44100, window_start_s=offset,
                                           track_duration_s=duration)
            cue_service._validate_beat_window(result)
            if retain_audio:
                result['_audio'] = window['_audio']
            windows.append(result)
        except Exception as error:
            logger.warning('Beat-Modellfenster %.2fs nicht verfügbar: %s', offset, type(error).__name__)
            window.update(status='decode_error', reason=f'beat_window_error:{type(error).__name__}')
            windows.append(window)
    return windows


@cue_service.track_session
def analyze_track(file_path: str, *, cache_policy: str = "reuse",
                  native_snapshot=None) -> Track | None:
    """Analyzes one track; ``fresh`` bypasses both track-cache reads and writes."""
    if type(cache_policy) is not str or cache_policy not in {"reuse", "fresh"}:
        raise ValueError("cache_policy muss 'reuse' oder 'fresh' sein")
    if not file_path:
        return None

    if isinstance(file_path, os.PathLike):
        file_path = os.fspath(file_path)

    if not isinstance(file_path, str) or not file_path:
        return None

    if not os.path.exists(file_path):
        logger.error(f"Datei nicht gefunden: {file_path}")
        return None

    # Ressourcenlimits vor jedem Decoder-/LUFS-Aufruf pruefen. Der spaetere
    # Playlist-Filter bleibt als zweite Verteidigung bestehen, darf aber nicht
    # erst nach teurem Audio-Decode greifen.
    try:
        file_size = os.path.getsize(file_path)
        if file_size > SECURITY_MAX_FILE_SIZE:
            logger.warning("Datei wegen Groessenlimit uebersprungen: %s", file_path)
            return None
        file_duration = _get_file_duration(file_path)
        if not np.isfinite(file_duration) or file_duration <= 0.0:
            logger.warning("Datei hat keine gueltige Audiodauer: %s", file_path)
            return None
        if file_duration > SECURITY_MAX_TRACK_DURATION:
            logger.warning("Datei wegen Dauerlimit uebersprungen: %s", file_path)
            return None
    except OSError as error:
        logger.warning("Datei konnte vor Analyse nicht geprueft werden: %s", error)
        return None

    # Rekordbox-Metadaten koennen sich ohne Audio-Dateiaenderung aendern.
    # Die Signatur muss deshalb vor dem Cache-Lookup ermittelt werden.
    rekordbox_importer = None
    rekordbox_data = None
    rekordbox_signature = ""
    try:
        rekordbox_importer = get_rekordbox_importer()
        rekordbox_data = rekordbox_importer.get_track_data(file_path)
    except Exception as error:
        logger.warning(
            "Rekordbox-Daten nicht lesbar; Audiofallback fuer %s: %s",
            os.path.basename(file_path),
            error,
        )

    if rekordbox_importer is not None:
        signature_builder = getattr(rekordbox_importer, "get_track_signature", None)
        if callable(signature_builder):
            try:
                rekordbox_signature = signature_builder(file_path) or ""
            except Exception as error:
                logger.warning(
                    "Rekordbox-Signatur nicht lesbar; Audiofallback fuer %s: %s",
                    os.path.basename(file_path),
                    error,
                )
                rekordbox_data = None

    cue_source_signature = _cue_source_signature(file_path, rekordbox_signature)
    try:
        neural_identity = cue_service.fingerprint()
        # Bestehende Cache-/Metadatenkonsumenten verwenden dieses Signaturfeld.
        # Deshalb dieselbe erweiterte Quellidentität im Track und Lookup halten.
        rekordbox_signature = f"{rekordbox_signature}|neural:{neural_identity}"
        cache_key = generate_cache_key(file_path, rekordbox_signature)
    except Exception as error:
        logger.error("Cache-Key konnte nicht sicher erzeugt werden: %s", error)
        return None
    if not cache_key:
        logger.error("Cache-Key konnte nicht sicher erzeugt werden: %s", file_path)
        return None

    cached_track = None
    if cache_policy == "reuse":
        try:
            cached_track = get_cached_track(cache_key, file_path=file_path)
        except Exception as error:
            logger.warning("Cache-Lesefehler; Track wird neu analysiert: %s", error)
            cached_track = None

    if cached_track:
        cached_mode = getattr(cached_track, "analysis_mode", None)
        if cached_mode in VALID_ANALYSIS_MODES:
            from .ai_models.deep_features import attach as attach_deep_features
            from .ai_models.deep_features import needs_refresh as deep_features_need_refresh
            if deep_features_need_refresh(cached_track):
                # Fehlgeschlagene/veraltete Zusatzmerkmale gezielt erneuern.
                # Die erfolgreiche Basisanalyse bleibt dabei Cachetreffer.
                try:
                    attach_deep_features(cached_track)
                    if not cache_track(cache_key, cached_track):
                        logger.warning("Zusatzmerkmale nicht im Cache aktualisiert: %s",
                                       os.path.basename(file_path))
                except Exception as error:
                    logger.warning("Veraltete Zusatzmerkmale nicht erneuert: %s",
                                   type(error).__name__)
            cached_track.analysis_origin = "cache"
            logger.debug(f"Cache-Hit: {os.path.basename(file_path)}")
            return cached_track
        logger.warning(
            "Cache-Hit mit ungueltigem analysis_mode %r; Track wird neu analysiert: %s",
            cached_mode,
            os.path.basename(file_path),
        )

    logger.info(f"Analysiere: {os.path.basename(file_path)}")

    if rekordbox_data and rekordbox_data.bpm:
        # Rekordbox data available - use it!
        analysis_degraded = False  # AUDIT-FIX A-02: markiert Load-Fehlschlag
        logger.info(
            f"Rekordbox-Daten: BPM={rekordbox_data.bpm}, Key={rekordbox_data.camelot_code}"
        )

        # Still extract ID3 tags (Rekordbox might have different metadata)
        artist_id3, title_id3, genre_id3 = extract_metadata(file_path)

        # Prefer Rekordbox metadata, fallback to ID3
        artist = rekordbox_data.artist or artist_id3
        title = rekordbox_data.title or title_id3
        genre = rekordbox_data.genre or genre_id3

        # For duration and some missing data, we still need librosa (quick load only)
        # K2 Audit-Fix: Dauer begrenzen — BPM/Key kommt aus Rekordbox, nur Energy/Genre noetig
        try:
            y, sr = _load_analysis_audio(
                file_path, duration=LIBROSA_FAST_PATH_DURATION
            )
            # Fensterbreite EINMAL je Pfad. Stand sie an mehreren Stellen,
            # konnte `energy` gegen ein anderes Fenster laufen als die
            # uebrigen sieben Merkmale, ohne dass ein Test das sieht.
            fenster_samples = int(FEATURE_WINDOW_DURATION * sr)
            feature_cache = FeatureCache(y, sr)
            # D8: gemeinsames Messfenster fuer die Merkmale. Bewusst EIGENE
            # Namen -- wuerden `y` und `feature_cache` neu gebunden, wanderten
            # auch `calculate_bass_intensity`, `classify_genre`, der
            # MFCC-Fingerabdruck, die Sektionsschleife und die
            # Strukturfenster still mit. Genau EINMAL gebunden, damit kein
            # Merkmal gegen ein anderes Fenster laufen kann.
            y_fenster = y[:fenster_samples]
            cache_fenster = feature_cache.fenster(fenster_samples)
            # Echte Datei-Dauer, nicht die abgeschnittene aus y (max FAST_PATH_DURATION)
            duration = file_duration

            # Calculate energy and bass (not in Rekordbox)
            energy = calculate_energy(y_fenster)
            bass_intensity = calculate_bass_intensity(y, sr)

            lufs, lufs_status, lufs_coverage, lufs_channels, lufs_sample_rate = (
                calculate_file_lufs(file_path)
            )
            # Key aus der Rekordbox-DB = verlaesslich analysiert
            key_confidence = 1.0 if rekordbox_data.camelot_code else 0.0

            grid_reader = getattr(rekordbox_importer, "get_beatgrid", None)
            rekordbox_grid = grid_reader(file_path) if callable(grid_reader) else []
            native_context = _prepare_native_beats(file_path, duration, y, sr,
                **({'snapshot': native_snapshot} if native_snapshot is not None else {}))
            if native_context['accepted']:
                bpm = native_context['analysis']['bpm']
                reference_attempt, beat_windows = _native_reference_candidate_windows(
                    file_path, duration, bpm, y, sr, rekordbox_grid,
                    rekordbox_data.bpm,
                    getattr(rekordbox_data, "path_match", "unknown"),
                    native_context,
                )
                tempo_transient, tempo_diagnostic = False, None
            else:
                beat_windows = _collect_beat_windows(file_path, duration, y, sr)
                bpm, reference_attempt, tempo_transient, tempo_diagnostic = _resolve_track_tempo(
                    file_path, duration, rekordbox_data.bpm, y, sr, rekordbox_grid, beat_windows,
                    reference_bpm=rekordbox_data.bpm,
                    reference_path_match=getattr(rekordbox_data, "path_match", "unknown"))

            # DJ Brain: Genre-Klassifikation
            genre_result = classify_genre(
                y, sr, bpm, bass_intensity, genre
            )
            logger.info(
                f"Genre: {genre_result.genre} (confidence: {genre_result.confidence:.2f}, source: {genre_result.source})"
            )

            # Downbeat-Anker (2026-07-17): zuerst der exakte Rekordbox-Beatgrid
            # (ANLZ/PQTZ, Konfidenz 1.0), sonst eigene Schaetzung (Phase-Voting)
            # Rekordbox-Phrasen (PSSI) und Cues mit Provenienz — Rohmaterial
            # fuer die Mixpunkt-Kandidaten (Spec 2026-08-21)
            cue_points = normalize_cues(
                rekordbox_data.cue_points,
                duration=file_duration,
                source=file_path,
            )
            phrase_unit = GENRE_PHRASE_UNITS.get(genre_result.genre, 8)
            (first_downbeat, downbeat_confidence, beatgrid_source, beatgrid_validation,
             downbeat_diagnostics, grid_diagnostics, anchor_decision, phrase_estimate) = _resolve_track_anchor(
                file_path, duration, bpm, y, sr, rekordbox_grid, beat_windows,
                reference_bpm=rekordbox_data.bpm, reference_attempt=reference_attempt,
                phrase_unit=phrase_unit, native_context=native_context,
                reference_path_match=getattr(rekordbox_data, "path_match", "unknown"))
            anchor_decision["neural"]["transient"] |= tempo_transient or native_context.get('transient', False)
            phrase_usage_blocked = bar_position_usage_blocked(anchor_decision)
            bar_position_status = _classify_bar_position_status(
                beatgrid_source, downbeat_confidence, native_context['accepted'],
                phrase_usage_blocked, anchor_decision.get("bar_position_comparison"))
            # Das prueft stabile Beatphase, nicht unabhaengige Takt-1-Genauigkeit.
            anchor_grid_usable = (
                beatgrid_validation.status == "verified"
                and (downbeat_confidence >= DOWNBEAT_RELIABLE_MIN
                     or native_context['accepted'])
            )
            phrase_phase_usable = _phrase_phase_usable(
                beatgrid_source, bar_position_status, phrase_usage_blocked,
                anchor_grid_usable,
            )
            pssi_grid_usable = bool(
                beatgrid_source == "rekordbox"
                and beatgrid_validation.status == "verified"
                and not phrase_usage_blocked
            )
            phrases = (
                rekordbox_importer.get_phrases(file_path, duration=file_duration)
                if pssi_grid_usable
                and hasattr(rekordbox_importer, "get_phrases")
                else []
            )
            mix_phase_usable = bool(
                anchor_grid_usable and not phrase_usage_blocked
                and (phrase_phase_usable or (pssi_grid_usable and phrases))
            )

            if anchor_grid_usable and not phrase_usage_blocked:
                if phrase_estimate is not None:
                    first_phrase, phrase_confidence = phrase_estimate
                else:
                    first_phrase, phrase_confidence = estimate_first_phrase(
                        y, sr, bpm, first_downbeat, phrase_unit
                    )
            else:
                first_phrase, phrase_confidence = MIX_POINT_UNSET, 0.0
            phrase_anchor = None if phrase_usage_blocked else (
                first_phrase
                if anchor_grid_usable
                and first_phrase >= 0.0
                and phrase_confidence >= PHRASE_CONFIDENCE_MIN
                else first_downbeat if anchor_grid_usable else 0.0
            )
            if phrases and pssi_grid_usable:
                phrase_anchor = float(phrases[0]["start_s"])

            # Wenn Audio kein belastbares erstes Phrasenereignis findet,
            # darf die Novelty-Messung im Strukturpfad die Genre-Prior-
            # Phrasenlaenge bestimmen. Das Raster bleibt am bestaetigten
            # Downbeat verankert; gesperrte oder unbestaetigte Raster behalten
            # unveraendert den Genre-Prior.
            measure_phrase_unit = (
                anchor_grid_usable
                and not phrase_usage_blocked
                and (first_phrase < 0.0 or phrase_confidence < PHRASE_CONFIDENCE_MIN)
            )

            # Native Erzeugung ist getrennt von importierten PSSI-Phrasen.
            from .ai_models.native_phrase_adapter import analyze_track_phrases
            native_key_note, native_key_mode = REVERSE_CAMELOT_MAP.get(
                rekordbox_data.camelot_code, ('', ''))
            native_phrase_analysis = analyze_track_phrases(
                file_path, bpm=bpm, duration=file_duration, first_downbeat=first_downbeat,
                grid_usable=anchor_grid_usable and phrase_phase_usable,
                usage_blocked=phrase_usage_blocked,
                imported_phrases=phrases, reference_grid=rekordbox_grid,
                grid_source=beatgrid_source,
                native_beat_analysis=(native_context['analysis'] if native_context['accepted'] else None),
                key_note=native_key_note, key_mode=native_key_mode)
            cue_model_candidates, cue_model_grid_verified = _cue_candidates_for_structure(
                phrases=phrases, pssi_grid_usable=pssi_grid_usable,
                native_phrase_analysis=native_phrase_analysis,
                phrase_phase_usable=phrase_phase_usable,
                pssi_grid_verified=(phrase_phase_usable and beatgrid_source == "rekordbox"
                                    and beatgrid_validation.status == "verified"),
            )
            # DJ Brain: gemeinsamer Strukturabschluss für beide Analysepfade.
            (
                structure, analysis_coverage, outro_covered,
                first_phrase, phrase_confidence, phrase_anchor, cue_score_binding,
            ) = _analyze_structure_with_final_phrase_anchor(
                file_path, y, sr, bpm, genre_result.genre, duration,
                first_downbeat=first_downbeat,
                phrase_anchor=phrase_anchor,
                first_phrase=first_phrase,
                phrase_confidence=phrase_confidence,
                phrase_unit=phrase_unit,
                measure_phrase_unit=measure_phrase_unit,
                preserve_phrase_anchor=bool(phrases and pssi_grid_usable),
                anchor_grid_usable=anchor_grid_usable,
                phrase_usage_blocked=phrase_usage_blocked,
                feature_cache=feature_cache,
                cue_candidates=cue_model_candidates,
                cue_verified_grid=cue_model_grid_verified,
                reanalyze_cue_verified_grid=cue_model_grid_verified,
                cue_source_signature=cue_source_signature,
                native_phrase_analysis=native_phrase_analysis,
            )
            section_dicts = [s.to_dict() for s in structure.sections]
            for section in section_dicts:
                section["analysis_status"] = (
                    "unanalysed" if section.get("label") == "unanalysed" else "analyzed"
                )
            section_labels = [s.label for s in structure.sections]
            logger.info(
                f"Struktur: {len(structure.sections)} Sektionen: {section_labels} (Phrase: {structure.phrase_unit} Bars)"
            )

            # AUDIT-FEATURE A1 (2026-07-26): Phrasen-Phase schaetzen und als
            # Anker fuers PHRASEN-Gitter verwenden (Konfidenz-Gate; Fallback
            # bleibt der Takt-Anker first_downbeat).
            # AUDIT-FIX R2 (2026-07-26): NUR bei belastbarem Downbeat-Raster —
            # ein gescheitertes Downbeat-Estimate (Konfidenz 0.0) wuerde sonst
            # ein erfundenes Bar-Raster ab t=0 abstimmen.
            # AUDIT-FIX R4 (2026-07-26): Sentinel -1.0 statt 0.0 — first_phrase
            # 0.0 ist eine GUELTIGE Phase (Track startet auf der Phrasengrenze).
            # DJ Brain: Genre-spezifische Mix-Punkte (RMS-Fallback ohne Sections
            # delegiert intern ebenfalls an calculate_genre_aware_mix_points)
            if not mix_phase_usable:
                mix_in_point = mix_out_point = MIX_POINT_UNSET
                mix_in_bars = mix_out_bars = 0
            elif section_dicts:
                mix_in_point, mix_out_point, mix_in_bars, mix_out_bars = (
                    calculate_genre_aware_mix_points(
                        section_dicts, bpm, duration,
                        genre_result.genre, anchor=phrase_anchor,
                        first_downbeat=first_downbeat,  # R3: Untergrenze am Takt-Anker
                        phrase_unit=structure.phrase_unit,
                    )
                )
                logger.info(
                    f"DJ Brain Mix-Punkte: in={mix_in_bars} bars, out={mix_out_bars} bars ({genre_result.genre})"
                )
            else:
                mix_in_point, mix_out_point, mix_in_bars, mix_out_bars = (
                    analyze_structure_and_mix_points(
                        y, sr, duration, energy, bpm,
                        genre=genre_result.genre,
                        anchor=phrase_anchor,
                        first_downbeat=first_downbeat,  # R3
                        phrase_unit=structure.phrase_unit,
                    )
                )

            # Gerichtete manuelle Cues behalten ihre Prioritaet, muessen aber
            # denselben quantisierten Intro-/Outro-Vertrag wie Analyzerpunkte
            # erfuellen. Der gemeinsame Helfer wird auch im Vollpfad benutzt.
            if mix_phase_usable:
                mix_in_point, mix_out_point = _apply_manual_mixpoint_cues(
                    mix_in_point,
                    mix_out_point,
                    cue_points=cue_points,
                    bpm=bpm,
                    duration=duration,
                    phrase_unit=structure.phrase_unit,
                    anchor=phrase_anchor,
                    sections=section_dicts,
                )
            # Nach den manuellen Cues neu rechnen -- sie koennen die Punkte
            # verschoben haben. Dieselbe Rundung wie `dj_brain` und die
            # Anzeige: `int()` trunkierte, wodurch Cache und Anzeige um einen
            # Takt auseinanderliefen. Der Sentinel MIX_POINT_UNSET (-1.0)
            # ergaebe gerundet ab 174 BPM einen negativen Takt, den
            # `caching.validate_track_dict` zurueckweist.
            mix_in_bars = (
                seconds_to_bars(mix_in_point, bpm)
                if mix_in_point >= 0 else 0
            )
            mix_out_bars = (
                seconds_to_bars(mix_out_point, bpm)
                if mix_out_point >= 0 else 0
            )
            if not anchor_grid_usable:
                # Kein Track-Mixpunkt darf auf dem unzuverlaessigen
                # Fallback-Anker als Takt- oder Phrasenraster ausgegeben werden.
                mix_in_point = mix_out_point = MIX_POINT_UNSET
                mix_in_bars = mix_out_bars = 0

            # Audio Feature Extensions
            brightness = calculate_brightness(y_fenster, sr, cache_fenster)
            vocal_instrumental = detect_vocal_instrumental(y_fenster, sr, cache_fenster)
            danceability = calculate_danceability(
                y_fenster, sr, bpm, cache_fenster
            )
            # M1 Audit-Fix: MFCC kommt aus classify_genre() (spart doppelte Berechnung)
            mfcc_fingerprint = genre_result.mfcc_fingerprint or calculate_mfcc_fingerprint(
                y, sr, feature_cache=feature_cache
            )
            logger.debug(
                f"Features: brightness={brightness}, vocal={vocal_instrumental}, dance={danceability}"
            )

        except (sf.LibsndfileError, RuntimeError, OSError, ValueError) as e:
            # AUDIT-FIX A-02 (2026-07-24): Nur die tatsaechlich erwarteten
            # Lade-/Decode-Fehlerklassen fangen (vorher `except Exception`, was
            # auch echte Programmierfehler als "Load fehlgeschlagen" tarnte).
            # Ohne decodiertes Audio existiert kein belastbarer Analyseerfolg.
            # Insbesondere duerfen keine Default-Mixpunkte nach außen gelangen.
            logger.warning("Schneller Librosa-Load fehlgeschlagen: %s", e)
            return None

        # Extract key note and mode from Camelot code (for backward compatibility)
        key_note = ""
        key_mode = ""
        if rekordbox_data.camelot_code:
            # Use reverse mapping to get correct Note and Mode from Camelot code
            key_tuple = REVERSE_CAMELOT_MAP.get(rekordbox_data.camelot_code)
            if key_tuple:
                key_note, key_mode = key_tuple

        # --- Advanced Audio Analysis (Phase 2) ---
        # C1-Fix: Block darf NICHT im camelot_code-Zweig haengen, sonst wird
        # `track` bei Tracks ohne Key nie erzeugt (UnboundLocalError).
        # C2-Fix: bereits geladenes Fast-Path-Audio (y) wiederverwenden statt
        # die Datei erneut in voller Laenge zu laden.
        try:
            # Timbre-Fingerprint fuer den Fast-Path-Ausschnitt
            timbre_fp = generate_timbre_fingerprint(y_fenster, sr, cache_fenster)

            # Overall Track Averages for Advanced Features (VOR dem Sektions-Loop,
            # damit Sektionen ausserhalb des geladenen Audiofensters darauf
            # zurueckfallen koennen).
            avg_b, avg_m, avg_h = analyze_frequency_bands(y_fenster, sr, cache_fenster)
            track_pr, track_sf = analyze_rhythm_complexity(y_fenster, sr, cache_fenster)

            # Groove-Features (nur auf belastbarem Downbeat-Raster, siehe
            # compute_groove_fields). y/sr sind hier das Fast-Path-Audio.
            groove = compute_groove_fields(
                y_fenster, sr, bpm, first_downbeat,
                downbeat_confidence if anchor_grid_usable else 0.0,
                feature_cache=cache_fenster, sections=section_dicts,
            )

            # Update each section with detailed frequency and rhythm data
            updated_sections = []
            section_audio_windows = getattr(
                structure, '_section_audio_windows', [(0.0, y, feature_cache)]
            )
            for sec_dict in section_dicts:
                y_seg, section_cache, sample_range = _section_audio_slice(
                    sec_dict, section_audio_windows, sr, feature_cache,
                )

                if len(y_seg) > sr: # At least 1 second
                    # Frequency Bands
                    b, m, h = analyze_frequency_bands(y_seg, sr)
                    sec_dict['avg_bass'] = b
                    sec_dict['avg_mids'] = m
                    sec_dict['avg_highs'] = h

                    # Rhythm & Texture
                    percussive_ratio, spectral_flatness = analyze_rhythm_complexity(
                        y_seg, sr, section_cache,
                        sample_range=sample_range,
                    )
                    sec_dict['percussive_ratio'] = percussive_ratio
                    sec_dict['spectral_flatness'] = spectral_flatness

                    # Bassdruck der Sektion fuer den Nahtstellen-Vergleich
                    # (Spec 5.3). Zu kurze Sektionen bekommen die Schluessel
                    # NICHT — transition_features faellt dann auf das
                    # Trackmittel zurueck, statt einen aus wenigen Frames
                    # geschaetzten Wert vorzutaeuschen.
                    if len(y_seg) >= BASS_KENNWERTE_MIN_SEC * sr:
                        sec_sub, sec_punch = bass_kennwerte(y_seg, sr)
                        sec_dict['sub_energy'] = sec_sub
                        sec_dict['bass_punch'] = sec_punch
                else:
                    # Audit-Fix 2026-07-21: Sektion liegt ausserhalb des geladenen
                    # Audiofensters (Fast-Path 360s / Full 600s) oder ist zu kurz.
                    # Vorher wurden hier harte 0.0-Platzhalter geschrieben, die den
                    # sinnvollen Track-Level-Fallback in dj_brain
                    # (out_sec_data.get('avg_bass', track_a.avg_bass)) UEBERSCHRIEBEN —
                    # genau am kritischen Mix-Out langer Tracks. Jetzt erben diese
                    # Sektionen die Track-weiten Kennwerte statt Bass=0 vorzutaeuschen.
                    sec_dict['avg_bass'] = sec_dict.get('avg_bass', avg_b)
                    sec_dict['avg_mids'] = avg_m
                    sec_dict['avg_highs'] = avg_h
                    sec_dict['percussive_ratio'] = track_pr
                    sec_dict['spectral_flatness'] = track_sf

                updated_sections.append(sec_dict)

            section_dicts = updated_sections

        except Exception as e:
            logger.warning(f"Erweiterte Analyse fehlgeschlagen: {e}")
            timbre_fp = []
            avg_b = avg_m = avg_h = 0.0
            track_pr = track_sf = 0.0
            groove = GrooveFeatures()

        # Mixpunkt-Kandidaten (Spec 2026-08-21). Guard: im degradierten Zweig
        # sind die Listen bereits leer gesetzt und duerfen nicht ueberschrieben
        # werden (section_dicts/structure waeren dort Platzhalter).
        if not analysis_degraded:
            if phrase_usage_blocked:
                mix_in_candidates, mix_out_candidates = [], []
                phrase_grid = []
                kandidaten = None
            else:
                kandidaten = _kandidaten_berechnen(
                    file_path, pfad="fast", bpm=bpm, duration=duration,
                    first_downbeat=first_downbeat,
                    downbeat_confidence=downbeat_confidence,
                    phrase_confidence=phrase_confidence,
                    phrase_anchor=phrase_anchor,
                    anchor_grid_usable=anchor_grid_usable,
                    phrase_phase_usable=phrase_phase_usable,
                    pssi_grid_usable=pssi_grid_usable and bool(phrases),
                    phrase_unit=structure.phrase_unit, sections=section_dicts,
                    phrases=phrases, cues=cue_points,
                    native_phrases=native_phrase_analysis.get('phrases', []),
                    analyzer_in=mix_in_point, analyzer_out=mix_out_point,
                    outro_covered=outro_covered,
                    cue_scores=_bound_cue_scores(cue_model_candidates, cue_source_signature, cue_score_binding, structure.cue_diagnostics),
                )
            if not phrase_usage_blocked and kandidaten is None:
                return None
            if not phrase_usage_blocked:
                mix_in_candidates, mix_out_candidates = kandidaten
                phrase_grid = phrase_grid_from_phrases(phrases or native_phrase_analysis.get('phrases', []))

        # Create Track object with Rekordbox data
        track = Track(
            avg_bass=avg_b,
            avg_mids=avg_m,
            avg_highs=avg_h,
            spectral_flatness=track_sf,
            percussive_ratio=track_pr,
            timbre_fingerprint=timbre_fp,
            groove_pattern=groove.groove_pattern,
            bass_pattern=groove.bass_pattern,
            syncopation=groove.syncopation,
            sub_energy=groove.sub_energy,
            bass_punch=groove.bass_punch,
            filePath=file_path,
            fileName=os.path.basename(file_path),
            artist=artist,
            title=title,
            genre=genre,
            duration=duration,
            bpm=bpm,
            keyNote=key_note,
            keyMode=key_mode,
            camelotCode=rekordbox_data.camelot_code,
            energy=energy,
            bass_intensity=bass_intensity,
            mix_in_point=mix_in_point,
            mix_out_point=mix_out_point,
            mix_in_bars=mix_in_bars,
            mix_out_bars=mix_out_bars,
            detected_genre=genre_result.genre,
            genre_confidence=genre_result.confidence,
            genre_source=genre_result.source,
            sections=section_dicts,
            phrase_unit=structure.phrase_unit,
            phrase_unit_source=structure.phrase_unit_source,
            phrase_unit_candidate=structure.phrase_unit_candidate,
            phrase_unit_score=structure.phrase_unit_score,
            phrase_unit_margin=structure.phrase_unit_margin,
            brightness=brightness,
            vocal_instrumental=vocal_instrumental,
            danceability=danceability,
            mfcc_fingerprint=mfcc_fingerprint,
            first_downbeat=first_downbeat,
            downbeat_confidence=downbeat_confidence,
            bar_position_status=bar_position_status,
            beatgrid_source=beatgrid_source,
            beatgrid_status=beatgrid_validation.status,
            beatgrid_windows_checked=beatgrid_validation.windows_checked,
            beatgrid_max_phase_error_ms=beatgrid_validation.max_phase_error_ms,
            neural_analysis=cue_service.neural_snapshot(structure, neural_identity, beat_windows),
            native_phrase_analysis=native_phrase_analysis,
            native_beat_analysis=native_context['analysis'],
            measurement_diagnostics=measurement_snapshot(
                downbeat_diagnostics, beatgrid_validation,
                decode_failures=grid_diagnostics.get("decode_failures", ()),
                anchor_decision=anchor_decision,
                phrase_unit_diagnostic=dict(
                    unit=structure.phrase_unit,
                    source=structure.phrase_unit_source,
                    candidate=structure.phrase_unit_candidate,
                    raw_score=structure.phrase_unit_score,
                    ranking_margin=structure.phrase_unit_margin,
                ),
                tempo_diagnostic=tempo_diagnostic,
                native_grid_diagnostic=native_context.get('decision'),
            ),
            first_phrase=first_phrase,
            phrase_confidence=phrase_confidence,
            key_confidence=key_confidence,
            lufs=lufs,
            rekordbox_signature=rekordbox_signature,
            analysis_mode=(
                "rekordbox_degraded"
                if analysis_degraded
                else "rekordbox_fast_tail"
            ),
            analysis_coverage=analysis_coverage,
            outro_covered=outro_covered,
            lufs_status=lufs_status,
            lufs_coverage_seconds=lufs_coverage,
            lufs_channels=lufs_channels,
            lufs_sample_rate=lufs_sample_rate,
            phrases=phrases,
            cue_points=cue_points,
            phrase_grid=phrase_grid,
            mix_in_candidates=mix_in_candidates,
            mix_out_candidates=mix_out_candidates,
        )

        # Laufzeit-Provenienz fuer Kohorten/Hoertests; kein persistiertes Feld.
        track.analysis_origin = "fresh"
        from .ai_models import deep_features
        deep_features.attach(track)

        # Degradierte Kernanalysen nicht persistieren. Optionale Stems/Embeddings
        # duerfen dagegen als unavailable gespeichert werden: der Cache-Hit kann
        # sie spaeter gezielt erneuern, ohne die Basisanalyse neu zu rechnen.
        if cache_policy == "reuse":
            if not analysis_degraded and not cue_service.transient_failure(track.neural_analysis) and track.native_phrase_analysis.get("status") != "unavailable" and not anchor_decision["neural"]["transient"]:
                if not _persist_analysis_result(cache_key, track):
                    return None
            else:
                logger.warning(
                    f"Degradierte Kernanalyse NICHT gecacht: {os.path.basename(file_path)}"
                )
        return track

    # Kein Rekordbox-Tempo: BPM kommt aus dem Audio. Ein vorhandener, aber in
    # Rekordbox noch nicht analysierter Datensatz bleibt fuer unabhaengige
    # Metadaten (Artist/Title/Genre, validierter Key, Cues/ANLZ) nutzbar.
    logger.info("Volle Librosa-Analyse (kein nutzbares Rekordbox-Tempo)")
    artist_id3, title_id3, genre_id3 = extract_metadata(file_path)
    if rekordbox_data is not None:
        artist = rekordbox_data.artist or artist_id3
        title = rekordbox_data.title or title_id3
        genre = rekordbox_data.genre or genre_id3
    else:
        artist, title, genre = artist_id3, title_id3, genre_id3

    try:
        # K2 Audit-Fix: Safety-Net gegen extrem lange Dateien (>10 Min)
        # Echte Datei-Dauer zuerst bestimmen (sehr schnell), dann nur max. 10 Min laden
        duration = file_duration
        y, sr = _load_analysis_audio(file_path, duration=LIBROSA_MAX_DURATION)
        # Siehe Fast-Path: Fensterbreite einmal je Pfad.
        fenster_samples = int(FEATURE_WINDOW_DURATION * sr)
        feature_cache = FeatureCache(y, sr)
        # D8: siehe Fast-Path. Eigene Namen, genau einmal gebunden.
        y_fenster = y[:fenster_samples]
        cache_fenster = feature_cache.fenster(fenster_samples)

        # --- BPM-Erkennung: ID3-Tag liefert den Wert, Audio prueft den Faktor ---
        # AUDIT-FIX 2026-08-14: Frueher stand hier "Beatport-Exporte enthalten
        # immer korrekte BPM-Werte" und der Tag wurde ungeprueft uebernommen,
        # abgesichert nur durch 20 < bpm < 300. Gemessen an der Produktiv-
        # bibliothek widersprach der Tag bei 23 von 52 Tracks der Rekordbox-
        # Analyse; bei "Bellatrix - Modern Music" stand 69 BPM im Tag, waehrend
        # librosa am selben Track 143.6 misst — exakt Halftime. Der Fehler
        # pflanzt sich fort: falsche BPM -> Genre "Unknown" -> phrase_unit 8
        # statt 16 -> verdoppeltes Phrasengitter -> Mixpoints auf falschem
        # Raster, und im Renderer reisst die Stretch-Klemme (+-8 %).
        # Die Halftime-Korrektur weiter unten galt nur fuer den Librosa-Zweig.
        #
        # Neue Logik: Die PRAEZISION des Tags bleibt massgeblich (er ist auf
        # Nachkommastellen genau), aber der FAKTOR wird gegen das Audio
        # geprueft. Nur wenn ein einfaches Vielfaches des Tags das gemessene
        # Tempo deutlich besser trifft, wird korrigiert.
        tag_bpm = extract_bpm_from_tags(file_path)
        if tag_bpm is not None:
            bpm = tag_bpm
            beat_frames = np.array([])  # Bleibt leer, falls die Gegenprobe scheitert
            measured = 0.0
            try:
                measured_raw, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
                measured_arr = np.atleast_1d(measured_raw)
                measured = float(measured_arr[0]) if measured_arr.size else 0.0
            except Exception as error:
                logger.debug(f"Tempo-Gegenprobe nicht moeglich: {error}")

            # Das ID3-Genre ist der Schiedsrichter. Ohne ihn wird NICHT
            # korrigiert — Begruendung: librosa liefert Tempo-Fehler um den
            # Faktor 2/3 vollkommen stabil (an einem echten 140-BPM-Track
            # ueber vier Fenster konstant 92.3, Streuung 0.0). Die Messung
            # allein kann "Tag falsch" und "Messung falsch" also nicht
            # unterscheiden. Der kanonische BPM-Bereich des Genres kann es:
            # 92 BPM sind fuer Psytrance (135-150) unmoeglich, 138 nicht.
            # Ist das ID3-Genre bekannt, gilt dessen kanonischer Bereich.
            # Fehlendes oder unbekanntes ID3-Genre darf keinen Audiowert zum
            # Schiedsrichter machen; insbesondere gibt es keinen Union-Fallback.
            if np.isfinite(measured) and measured > 0.0:
                corrected = _correct_id3_bpm_factor(
                    tag_bpm,
                    measured,
                    genre_id3,
                )
                direct = abs(tag_bpm - measured) / measured
                if corrected != tag_bpm:
                    factor = corrected / tag_bpm
                    logger.warning(
                        "ID3-BPM %.2f widerspricht dem Audio (%.1f gemessen) — "
                        "als Faktor %.3f erkannt, korrigiert auf %.2f: %s",
                        tag_bpm, measured, factor, corrected,
                        os.path.basename(file_path),
                    )
                    bpm = corrected
                elif direct > ID3_BPM_DIRECT_DEVIATION_MIN:
                    logger.warning(
                        "ID3-BPM %.2f weicht um %.0f%% vom gemessenen Tempo "
                        "%.1f ab, wird aber uebernommen (kein plausibles "
                        "Vielfaches im Genre-Bereich): %s",
                        tag_bpm, direct * 100.0, measured,
                        os.path.basename(file_path),
                    )
            logger.info(f"BPM aus ID3-Tag: {bpm:.2f}")
        else:
            # Librosa-Fallback: wenn keine BPM-Tags vorhanden
            tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
            tempo_array = np.atleast_1d(tempo)
            bpm_value = float(tempo_array[0]) if tempo_array.size else 0.0
            if bpm_value <= 0:
                alt_tempo = librosa.feature.rhythm.tempo(y=y, sr=sr)
                alt_array = np.atleast_1d(alt_tempo)
                bpm_value = float(alt_array[0]) if alt_array.size else 0.0
            if bpm_value <= 0 and beat_frames.size > 1:
                beat_times = librosa.frames_to_time(beat_frames, sr=sr)
                intervals = np.diff(beat_times)
                if intervals.size:
                    bpm_value = 60.0 / np.mean(intervals)
            bpm = round(float(bpm_value if bpm_value > 0 else DEFAULT_BPM), 2)

            # Halftime-Korrektur: Librosa erkennt manchmal die halbe BPM
            # bei elektronischer Musik (Psytrance ~145, Techno ~130, House ~125).
            # Schwellwert 95 statt 100: verhindert 80 BPM -> 160 BPM (wuerde DnB ausloesen).
            # Zusaetzliche Obergrenze: Verdoppelung nur wenn Ergebnis <= BPM_HALFTIME_MAX_RESULT
            # (verhindert ~92 BPM -> 184 BPM -> falsche DnB-Klassifikation)
            if 40 < bpm < 95:
                doubled = round(bpm * 2, 2)
                if doubled <= BPM_HALFTIME_MAX_RESULT:
                    bpm = doubled
            # M8-Fix: Doubletime-Korrektur als Gegenstueck — Librosa liefert bei
            # schnellen Genres (Psytrance ~145) manchmal die doppelte BPM (~290).
            # Elektronische Musik liegt praktisch nie ueber 200 BPM.
            elif bpm > 200:
                bpm = round(bpm / 2, 2)
            logger.info(f"BPM via Librosa: {bpm:.2f} (keine BPM-Tags gefunden)")

        # Vorhandenes Audio-Feintempo bildet die Baseline des Vollpfads.
        # Die anschließende gemeinsame Entscheidung schützt bestätigte Referenzen.
        bpm = _refine_audio_tempo(y, sr, bpm, file_path=file_path, duration=duration)

        rekordbox_grid: list[dict] = []
        if rekordbox_data is not None:
            grid_reader = getattr(rekordbox_importer, "get_beatgrid", None)
            rekordbox_grid = (
                grid_reader(file_path) if callable(grid_reader) else []
            )
        native_context = _prepare_native_beats(file_path, duration, y, sr,
            **({'snapshot': native_snapshot} if native_snapshot is not None else {}))
        if native_context['accepted']:
            bpm = native_context['analysis']['bpm']
            reference_attempt, beat_windows = _native_reference_candidate_windows(
                file_path, duration, bpm, y, sr, rekordbox_grid,
                rekordbox_data.bpm if rekordbox_data is not None else None,
                getattr(rekordbox_data, "path_match", "unknown"),
                native_context,
            )
            tempo_transient, tempo_diagnostic = False, None
        else:
            beat_windows = _collect_beat_windows(file_path, duration, y, sr)
            bpm, reference_attempt, tempo_transient, tempo_diagnostic = _resolve_track_tempo(
                file_path, duration, bpm, y, sr, rekordbox_grid, beat_windows,
                reference_bpm=rekordbox_data.bpm if rekordbox_data is not None else None,
                reference_path_match=getattr(rekordbox_data, "path_match", "unknown"))

        rekordbox_key = (
            REVERSE_CAMELOT_MAP.get(rekordbox_data.camelot_code)
            if rekordbox_data is not None and rekordbox_data.camelot_code
            else None
        )
        if rekordbox_key is not None:
            # Camelot-Codes werden nur nach erfolgreicher Reverse-Map als
            # sicher uebernommen; unbekannte Werte fallen auf Audio zurueck.
            key_note, key_mode = rekordbox_key
            camelot_code = rekordbox_data.camelot_code
            key_confidence = 1.0
            logger.info("Key aus Rekordbox trotz fehlendem RB-Tempo: %s", camelot_code)
        else:
            chroma = feature_cache.get_chroma()
            chroma_vector = np.mean(chroma, axis=1)
            # Key-Confidence-Feature 2026-07-17: Essentia-Muster (strength + margin)
            key_note, key_mode, key_strength, key_margin, second_note, second_mode = (
                get_key_with_confidence(chroma_vector)
            )
            key_confidence = key_confidence_score(
                key_strength, key_margin, key_note, key_mode, second_note, second_mode
            )
            logger.info(
                f"Key: {key_note} {key_mode} (Konfidenz {key_confidence:.2f}, "
                f"strength={key_strength:.2f}, margin={key_margin:.3f})"
            )

            # AUDIT-FIX F15: Bei flacher/stiller/mehrdeutiger Chroma keinen
            # erfundenen Key setzen; leerer Code nutzt den neutralen Score.
            if key_strength <= 0.05 and key_margin <= 1e-4:
                key_note = ""
                key_mode = ""
                camelot_code = ""
                key_confidence = 0.0
                logger.info(
                    "Key-Detection nicht eindeutig (flache Chroma) -> kein Camelot-Code"
                )
            else:
                camelot_code = CAMELOT_MAP.get((key_note, key_mode), "")

        energy = calculate_energy(y_fenster)
        bass_intensity = calculate_bass_intensity(y, sr)

        lufs, lufs_status, lufs_coverage, lufs_channels, lufs_sample_rate = (
            calculate_file_lufs(file_path)
        )

        # DJ Brain: Genre-Klassifikation
        genre_result = classify_genre(y, sr, bpm, bass_intensity, genre)
        logger.info(
            f"Genre: {genre_result.genre} (confidence: {genre_result.confidence:.2f}, source: {genre_result.source})"
        )

        phrase_unit = GENRE_PHRASE_UNITS.get(genre_result.genre, 8)
        (first_downbeat, downbeat_confidence, beatgrid_source, beatgrid_validation,
         downbeat_diagnostics, grid_diagnostics, anchor_decision, phrase_estimate) = _resolve_track_anchor(
            file_path, duration, bpm, y, sr, rekordbox_grid, beat_windows,
            reference_bpm=rekordbox_data.bpm if rekordbox_data is not None else None,
                reference_attempt=reference_attempt, phrase_unit=phrase_unit, native_context=native_context,
                reference_path_match=getattr(rekordbox_data, "path_match", "unknown"))
        anchor_decision["neural"]["transient"] |= tempo_transient or native_context.get('transient', False)
        phrase_usage_blocked = bar_position_usage_blocked(anchor_decision)
        bar_position_status = _classify_bar_position_status(
            beatgrid_source, downbeat_confidence, native_context['accepted'],
            phrase_usage_blocked, anchor_decision.get("bar_position_comparison"))
        # Das prueft stabile Beatphase, nicht unabhaengige Takt-1-Genauigkeit.
        anchor_grid_usable = (
            beatgrid_validation.status == "verified"
            and (downbeat_confidence >= DOWNBEAT_RELIABLE_MIN
                 or native_context['accepted'])
        )
        phrase_phase_usable = _phrase_phase_usable(
            beatgrid_source, bar_position_status, phrase_usage_blocked,
            anchor_grid_usable,
        )
        pssi_grid_usable = bool(
            beatgrid_source == "rekordbox"
            and beatgrid_validation.status == "verified"
            and not phrase_usage_blocked
        )
        phrases = (
            rekordbox_importer.get_phrases(file_path, duration=file_duration)
            if pssi_grid_usable
            and rekordbox_data is not None
            and hasattr(rekordbox_importer, "get_phrases")
            else []
        )
        mix_phase_usable = bool(
            anchor_grid_usable and not phrase_usage_blocked
            and (phrase_phase_usable or (pssi_grid_usable and phrases))
        )
        cue_points = (
            normalize_cues(
                rekordbox_data.cue_points,
                duration=file_duration,
                source=file_path,
            )
            if rekordbox_data is not None else []
        )

        if anchor_grid_usable and not phrase_usage_blocked:
            if phrase_estimate is not None:
                first_phrase, phrase_confidence = phrase_estimate
            else:
                first_phrase, phrase_confidence = estimate_first_phrase(
                    y, sr, bpm, first_downbeat, phrase_unit
                )
        else:
            first_phrase, phrase_confidence = MIX_POINT_UNSET, 0.0
        phrase_anchor = None if phrase_usage_blocked else (
            first_phrase
            if anchor_grid_usable
            and first_phrase >= 0.0
            and phrase_confidence >= PHRASE_CONFIDENCE_MIN
            else first_downbeat if anchor_grid_usable else 0.0
        )
        if phrases and pssi_grid_usable:
            phrase_anchor = float(phrases[0]["start_s"])
        # Wie im Fast-Path kann die Novelty-Messung den Genre-Prior nur bei
        # bestaetigtem Beatgrid und schwacher Phrasenphase ersetzen.
        measure_phrase_unit = (
            anchor_grid_usable
            and not phrase_usage_blocked
            and (first_phrase < 0.0 or phrase_confidence < PHRASE_CONFIDENCE_MIN)
        )
        # Wie im Fast-Path bleibt die Struktur auf dem BPM-Raster von
        # Downbeat, Phrasen und Mixpunkten. Der Median hopgerasterter
        # Trackerintervalle erzeugte hier einen abweichenden Taktabstand.
        # Native Erzeugung ist getrennt von importierten PSSI-Phrasen.
        from .ai_models.native_phrase_adapter import analyze_track_phrases
        native_phrase_analysis = analyze_track_phrases(
            file_path, bpm=bpm, duration=file_duration, first_downbeat=first_downbeat,
            grid_usable=anchor_grid_usable and phrase_phase_usable,
            usage_blocked=phrase_usage_blocked,
            imported_phrases=phrases, reference_grid=rekordbox_grid,
            grid_source=beatgrid_source,
            native_beat_analysis=(native_context['analysis'] if native_context['accepted'] else None),
            key_note=key_note, key_mode=key_mode)
        cue_model_candidates, cue_model_grid_verified = _cue_candidates_for_structure(
            phrases=phrases, pssi_grid_usable=pssi_grid_usable,
            native_phrase_analysis=native_phrase_analysis,
            phrase_phase_usable=phrase_phase_usable,
            pssi_grid_verified=(phrase_phase_usable and beatgrid_source == "rekordbox"
                                and beatgrid_validation.status == "verified"),
        )
        # DJ Brain: gemeinsamer Strukturabschluss für beide Analysepfade.
        (
            structure, analysis_coverage, outro_covered,
            first_phrase, phrase_confidence, phrase_anchor, cue_score_binding,
        ) = _analyze_structure_with_final_phrase_anchor(
            file_path, y, sr, bpm, genre_result.genre, duration,
            first_downbeat=first_downbeat,
            phrase_anchor=phrase_anchor,
            first_phrase=first_phrase,
            phrase_confidence=phrase_confidence,
            phrase_unit=phrase_unit,
            measure_phrase_unit=measure_phrase_unit,
            preserve_phrase_anchor=bool(phrases and pssi_grid_usable),
            anchor_grid_usable=anchor_grid_usable,
            phrase_usage_blocked=phrase_usage_blocked,
            feature_cache=feature_cache,
            cue_candidates=cue_model_candidates,
            cue_verified_grid=cue_model_grid_verified,
            reanalyze_cue_verified_grid=cue_model_grid_verified,
            cue_source_signature=cue_source_signature,
            native_phrase_analysis=native_phrase_analysis,
        )
        section_dicts = [s.to_dict() for s in structure.sections]
        for section in section_dicts:
            section["analysis_status"] = (
                "unanalysed" if section.get("label") == "unanalysed" else "analyzed"
            )
        section_labels = [s.label for s in structure.sections]
        logger.info(
            f"Struktur: {len(structure.sections)} Sektionen: {section_labels} (Phrase: {structure.phrase_unit} Bars)"
        )

        # AUDIT-FEATURE A1 (2026-07-26): Phrasen-Phase schaetzen (Konfidenz-Gate,
        # Fallback: Takt-Anker) und als Anker fuers Phrasen-Gitter verwenden.
        # AUDIT-FIX R2 (2026-07-26): NUR bei belastbarem Downbeat-Raster —
        # ein gescheitertes Downbeat-Estimate (Konfidenz 0.0) wuerde sonst
        # ein erfundenes Bar-Raster ab t=0 abstimmen.
        # AUDIT-FIX R4 (2026-07-26): Sentinel -1.0 statt 0.0 — first_phrase
        # 0.0 ist eine GUELTIGE Phase (Track startet auf der Phrasengrenze).
        # DJ Brain: Genre-spezifische Mix-Punkte (RMS-Fallback ohne Sections
        # delegiert intern ebenfalls an calculate_genre_aware_mix_points)
        if not mix_phase_usable:
            mix_in_point = mix_out_point = MIX_POINT_UNSET
            mix_in_bars = mix_out_bars = 0
        elif section_dicts:
            mix_in_point, mix_out_point, mix_in_bars, mix_out_bars = (
                calculate_genre_aware_mix_points(
                    section_dicts, bpm, duration, genre_result.genre,
                    anchor=phrase_anchor,
                    first_downbeat=first_downbeat,  # R3: Untergrenze am Takt-Anker
                    phrase_unit=structure.phrase_unit,
                )
            )
            logger.info(
                f"DJ Brain Mix-Punkte: in={mix_in_bars} bars, out={mix_out_bars} bars ({genre_result.genre})"
            )
        else:
            mix_in_point, mix_out_point, mix_in_bars, mix_out_bars = (
                analyze_structure_and_mix_points(
                    y, sr, duration, energy, bpm,
                    genre=genre_result.genre,
                    anchor=phrase_anchor,
                    first_downbeat=first_downbeat,  # R3
                    phrase_unit=structure.phrase_unit,
                )
            )

        if mix_phase_usable:
            mix_in_point, mix_out_point = _apply_manual_mixpoint_cues(
                mix_in_point,
                mix_out_point,
                cue_points=cue_points,
                bpm=bpm,
                duration=duration,
                phrase_unit=structure.phrase_unit,
                anchor=phrase_anchor,
                sections=section_dicts,
            )
        # Siehe Fast-Path: gleiche Rundung, gleicher Sentinel-Guard.
        mix_in_bars = seconds_to_bars(mix_in_point, bpm) if mix_in_point >= 0 else 0
        mix_out_bars = seconds_to_bars(mix_out_point, bpm) if mix_out_point >= 0 else 0
        if not anchor_grid_usable or phrase_usage_blocked:
            # Fast-Path gleich: ohne belastbare Taktphase keine Mix-Ausgabe.
            mix_in_point = mix_out_point = MIX_POINT_UNSET
            mix_in_bars = mix_out_bars = 0

        # Audio Feature Extensions
        brightness = calculate_brightness(y_fenster, sr, cache_fenster)
        vocal_instrumental = detect_vocal_instrumental(y_fenster, sr, cache_fenster)
        # `calculate_danceability` erkennt die Beats selbst, auf dem Fenster.
        # Die Beat-Frames aus dem BPM-Block gehoeren zum VOLLEN Signal und
        # waeren hier das falsche Fenster; der Parameter dafuer ist mit D14
        # entfallen. Preis ist ein `beat_track`-Aufruf zusaetzlich zu dem im
        # BPM-Block; der Vollpfad rechnet ausserdem einen in
        # `estimate_first_downbeat`, eine Gesamtzahl behauptet das hier nicht.
        #
        # ACHTUNG, gemessen 2026-09-04: dass beide Pfade dieselbe Funktion auf
        # demselben Fenster rechnen, gleicht `danceability` zwischen den
        # Pfaden NICHT an. Die verbleibende Differenz (97 gegen 92 an einer
        # 90-s-Synthetik) stammt aus der BPM, nicht aus den Beats: `bpm_bonus`
        # ist 0.15 im Band 118-152 und 0.08 im Band 100-170 und geht als
        # `(bpm_bonus / 0.15) * 0.10` ein -- 10.0 gegen 5.33 Punkte. Fast-Path
        # 128.0 aus Rekordbox, Vollpfad 107.67 aus librosas Schaetzung. Bei
        # gleicher BPM liefern beide 97. Das ist GEWOLLT: die BPM aus der
        # Datenbank zu nehmen ist der Zweck des Fast-Path.
        danceability = calculate_danceability(
            y_fenster, sr, bpm, cache_fenster
        )
        # M1 Audit-Fix: MFCC kommt aus classify_genre() (spart doppelte Berechnung)
        mfcc_fingerprint = genre_result.mfcc_fingerprint or calculate_mfcc_fingerprint(
            y, sr, feature_cache=feature_cache
        )
        logger.debug(
            f"Features: brightness={brightness}, vocal={vocal_instrumental}, dance={danceability}"
        )

        
        # --- Advanced Audio Analysis (Phase 2) ---
        try:
            # Signal und Samplerate liegen vor; der Fingerabdruck kommt aus
            # dem Merkmalsfenster, nicht aus dem vollen Signal (D8).
            timbre_fp = generate_timbre_fingerprint(y_fenster, sr, cache_fenster)
            
            updated_sections = []
            section_audio_windows = getattr(
                structure, '_section_audio_windows', [(0.0, y, feature_cache)]
            )
            for sec_dict in section_dicts:
                y_seg, section_cache, sample_range = _section_audio_slice(
                    sec_dict, section_audio_windows, sr, feature_cache,
                )
                
                if len(y_seg) > sr:
                    b, m, h = analyze_frequency_bands(y_seg, sr)
                    percussive_ratio, spectral_flatness = analyze_rhythm_complexity(
                        y_seg, sr, section_cache,
                        sample_range=sample_range,
                    )
                    sec_dict.update({
                        'avg_bass': b,
                        'avg_mids': m,
                        'avg_highs': h,
                        'percussive_ratio': percussive_ratio,
                        'spectral_flatness': spectral_flatness,
                    })

                    # Bassdruck der Sektion fuer den Nahtstellen-Vergleich
                    # (Spec 5.3), gleiche Regel wie im Rekordbox-Fast-Path.
                    if len(y_seg) >= BASS_KENNWERTE_MIN_SEC * sr:
                        sec_sub, sec_punch = bass_kennwerte(y_seg, sr)
                        sec_dict['sub_energy'] = sec_sub
                        sec_dict['bass_punch'] = sec_punch
                updated_sections.append(sec_dict)
            section_dicts = updated_sections
            
            avg_b, avg_m, avg_h = analyze_frequency_bands(y_fenster, sr, cache_fenster)
            track_pr, track_sf = analyze_rhythm_complexity(y_fenster, sr, cache_fenster)

            # Groove-Features (nur auf belastbarem Downbeat-Raster, siehe
            # compute_groove_fields).
            groove = compute_groove_fields(
                y_fenster, sr, bpm, first_downbeat,
                downbeat_confidence if anchor_grid_usable else 0.0,
                feature_cache=cache_fenster, sections=section_dicts,
            )
        except Exception as e:
            logger.warning(f"Librosa-Phase-2 fehlgeschlagen: {e}")
            timbre_fp = []
            avg_b = avg_m = avg_h = 0.0
            track_pr = track_sf = 0.0
            groove = GrooveFeatures()

        # Mixpunkt-Kandidaten (Spec 2026-08-21), Spiegel des Rekordbox-Pfads.
        # Ohne validiertes Rekordbox-Raster bleiben Phrasen leer; benannte und
        # unbenannte Cues sind davon unabhaengige, sichere Nutzerdaten.
        phrase_grid = [] if phrase_usage_blocked else phrase_grid_from_phrases(
            phrases or native_phrase_analysis.get('phrases', []))
        kandidaten = None if phrase_usage_blocked else _kandidaten_berechnen(
            file_path, pfad="voll", bpm=bpm, duration=duration,
            first_downbeat=first_downbeat,
            downbeat_confidence=downbeat_confidence,
            phrase_confidence=phrase_confidence,
            phrase_anchor=phrase_anchor,
            anchor_grid_usable=anchor_grid_usable,
            phrase_phase_usable=phrase_phase_usable,
            pssi_grid_usable=pssi_grid_usable and bool(phrases),
            phrase_unit=structure.phrase_unit, sections=section_dicts,
            phrases=phrases, cues=cue_points,
            native_phrases=native_phrase_analysis.get('phrases', []),
            analyzer_in=mix_in_point, analyzer_out=mix_out_point,
            outro_covered=outro_covered,
            cue_scores=_bound_cue_scores(cue_model_candidates, cue_source_signature, cue_score_binding, structure.cue_diagnostics),
        )
        if phrase_usage_blocked:
            mix_in_candidates, mix_out_candidates = [], []
        elif kandidaten is None:
            return None
        else:
            mix_in_candidates, mix_out_candidates = kandidaten

        track = Track(
            groove_pattern=groove.groove_pattern,
            bass_pattern=groove.bass_pattern,
            syncopation=groove.syncopation,
            sub_energy=groove.sub_energy,
            bass_punch=groove.bass_punch,
            filePath=file_path,
            fileName=os.path.basename(file_path),
            artist=artist,
            title=title,
            genre=genre,
            duration=duration,
            bpm=bpm,
            keyNote=key_note,
            keyMode=key_mode,
            camelotCode=camelot_code,
            energy=energy,
            bass_intensity=bass_intensity,
            avg_bass=avg_b,
            avg_mids=avg_m,
            avg_highs=avg_h,
            spectral_flatness=track_sf,
            percussive_ratio=track_pr,
            timbre_fingerprint=timbre_fp,
            mix_in_point=mix_in_point,
            mix_out_point=mix_out_point,
            mix_in_bars=mix_in_bars,
            mix_out_bars=mix_out_bars,
            detected_genre=genre_result.genre,
            genre_confidence=genre_result.confidence,
            genre_source=genre_result.source,
            sections=section_dicts,
            phrase_unit=structure.phrase_unit,
            phrase_unit_source=structure.phrase_unit_source,
            phrase_unit_candidate=structure.phrase_unit_candidate,
            phrase_unit_score=structure.phrase_unit_score,
            phrase_unit_margin=structure.phrase_unit_margin,
            brightness=brightness,
            vocal_instrumental=vocal_instrumental,
            danceability=danceability,
            mfcc_fingerprint=mfcc_fingerprint,
            first_downbeat=first_downbeat,
            downbeat_confidence=downbeat_confidence,
            bar_position_status=bar_position_status,
            beatgrid_source=beatgrid_source,
            beatgrid_status=beatgrid_validation.status,
            beatgrid_windows_checked=beatgrid_validation.windows_checked,
            beatgrid_max_phase_error_ms=beatgrid_validation.max_phase_error_ms,
            neural_analysis=cue_service.neural_snapshot(structure, neural_identity, beat_windows),
            native_phrase_analysis=native_phrase_analysis,
            native_beat_analysis=native_context['analysis'],
            measurement_diagnostics=measurement_snapshot(
                downbeat_diagnostics, beatgrid_validation,
                decode_failures=grid_diagnostics.get("decode_failures", ()),
                anchor_decision=anchor_decision,
                phrase_unit_diagnostic=dict(
                    unit=structure.phrase_unit,
                    source=structure.phrase_unit_source,
                    candidate=structure.phrase_unit_candidate,
                    raw_score=structure.phrase_unit_score,
                    ranking_margin=structure.phrase_unit_margin,
                ),
                tempo_diagnostic=tempo_diagnostic,
                native_grid_diagnostic=native_context.get('decision'),
            ),
            first_phrase=first_phrase,
            phrase_confidence=phrase_confidence,
            key_confidence=key_confidence,
            lufs=lufs,
            rekordbox_signature=rekordbox_signature,
            analysis_mode="librosa_full_or_tail",
            analysis_coverage=analysis_coverage,
            outro_covered=outro_covered,
            lufs_status=lufs_status,
            lufs_coverage_seconds=lufs_coverage,
            lufs_channels=lufs_channels,
            lufs_sample_rate=lufs_sample_rate,
            phrases=phrases,
            cue_points=cue_points,
            phrase_grid=phrase_grid,
            mix_in_candidates=mix_in_candidates,
            mix_out_candidates=mix_out_candidates,
        )

        # Laufzeit-Provenienz fuer Kohorten/Hoertests; kein persistiertes Feld.
        track.analysis_origin = "fresh"

        from .ai_models import deep_features
        deep_features.attach(track)
        if cache_policy == "reuse":
            if not cue_service.transient_failure(track.neural_analysis) and track.native_phrase_analysis.get("status") != "unavailable" and not anchor_decision["neural"]["transient"]:
                if not _persist_analysis_result(cache_key, track):
                    return None
        return track

    except Exception as e:
        logger.error(f"Fehler bei der Librosa-Analyse von {file_path}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None
