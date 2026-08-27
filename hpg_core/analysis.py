from __future__ import annotations  # Python 3.9 compatibility for | type hints

import logging
import math
import os
import re
import time
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
    HOP_LENGTH,
    METER,
    MIX_IN_SEARCH_WINDOW_PCT,
    MIX_OUT_SEARCH_WINDOW_PCT,
    RMS_THRESHOLD,
    DEFAULT_BPM,
    BPM_HALFTIME_MAX_RESULT,
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
    DOWNBEAT_RELIABLE_MIN,
    estimate_first_downbeat,
    estimate_first_phrase,
    validate_beatgrid_windows,
)
from .genre_classifier import classify_genre, match_id3_genre
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
    get_camelot_components,
    quantize_to_grid,
)
from .rekordbox_importer import get_rekordbox_importer
from .rekordbox_phrases import phrase_grid_from_phrases
from .structure_analyzer import (
    GENRE_PHRASE_UNITS,
    TrackSection,
    TrackStructure,
    analyze_structure,
)

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


def _validate_track_beatgrid(
    file_path: str,
    duration: float,
    bpm: float,
    anchor: float,
    *,
    grid_points: list[dict] | None = None,
    head_audio: np.ndarray | None = None,
    head_sr: int = 0,
) -> BeatgridValidation:
    """Laedt bis zu drei getrennte Fenster und prueft deren reale Kickphase."""
    span = min(_BEATGRID_WINDOW_SECONDS, max(1.0, float(duration)))
    raw_offsets = (
        0.0,
        max(0.0, float(duration) / 2.0 - span / 2.0),
        max(0.0, float(duration) - span),
    )
    offsets = tuple(dict.fromkeys(raw_offsets))
    windows: list[tuple[float, np.ndarray]] = []
    sample_rate = int(head_sr or 0)
    for index, offset in enumerate(offsets):
        try:
            if index == 0 and head_audio is not None and sample_rate > 0:
                audio = np.asarray(head_audio)[: int(span * sample_rate)]
            else:
                audio, loaded_sr = librosa.load(
                    file_path, sr=sample_rate or None, mono=True,
                    offset=offset, duration=span,
                )
                sample_rate = int(loaded_sr)
        except (OSError, RuntimeError, ValueError, sf.LibsndfileError) as error:
            logger.warning("Beatgrid-Fenster %.2fs nicht lesbar: %s", offset, error)
            continue
        windows.append((offset, np.asarray(audio)))
    grid_times = [float(point["time"]) for point in (grid_points or [])]
    return validate_beatgrid_windows(
        windows, sample_rate, bpm, anchor=anchor, grid_times=grid_times
    )

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
    Paper voll BS.1770-konform bei jeder Samplerate). Referenz fuer
    Gain-Matching ist LUFS_REFERENCE (config, -18 = ReplayGain 2.0).

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


def _integrated_loudness_from_blocks(file_path: str, info, meter) -> float:
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

    for chunk in sf.blocks(
        file_path,
        blocksize=stream_block_frames,
        dtype="float32",
        always_2d=True,
    ):
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
    """Liest die Dauer ohne Audiodaten zu dekodieren, mit Librosa-Fallback."""
    try:
        info = sf.info(file_path)
        if info.samplerate > 0:
            return float(info.frames / info.samplerate)
    except (OSError, RuntimeError, ValueError) as error:
        logger.debug(f"SoundFile-Dauer nicht verfügbar: {error}")
    return float(librosa.get_duration(path=file_path))


def _median_seconds_per_bar(
    beat_frames: np.ndarray,
    sr: int,
    bpm: float,
    hop_length: int = 512,
) -> float | None:
    """Leitet eine robuste Taktlänge aus vorhandenen Beat-Intervallen ab."""
    frames = np.asarray(beat_frames).reshape(-1)
    if sr <= 0 or bpm <= 0 or frames.size < 8:
        return None
    intervals = np.diff(frames.astype(float))
    intervals = intervals[intervals > 0]
    if intervals.size == 0:
        return None
    ibi = float(np.median(intervals) * hop_length / sr)
    expected_ibi = 60.0 / bpm
    if ibi > expected_ibi * 1.5:
        ibi /= 2.0
    elif ibi < expected_ibi * 0.75:
        ibi *= 2.0
    if not np.isfinite(ibi) or ibi <= 0:
        return None
    return 4.0 * ibi


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
    beat_frames: np.ndarray | None = None,
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
        beat_frames: Optional, bereits erkannte Beat-Frames

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
        if beat_frames is None:
            tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
        else:
            tempo = np.asarray([bpm or 0.0])
            beats = np.asarray(beat_frames).reshape(-1)
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


def analyze_structure_and_mix_points(y: np.ndarray, sr: int, duration: float, energy_level: int, bpm: float, genre: str = "Unknown", anchor: float = 0.0, first_downbeat: float | None = None) -> tuple[float, float, int, int]:
    """
    RMS-Fallback fuer Mix-Punkte, wenn keine Struktur-Analyse (Sections) vorliegt.

    Konsolidierung 2026-07-17 (docs/plans/2026-07-17-mixpoint-pfad-b-konsolidierung.md):
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
        start_time=_round_time_within_duration(start, duration),
        end_time=_round_time_within_duration(end, duration),
        start_bar=int(round(start / seconds_bar)) if seconds_bar else 0,
        end_bar=int(round(end / seconds_bar)) if seconds_bar else 0,
        avg_energy=section.avg_energy,
    )


def _round_time_within_duration(value: float, duration: float) -> float:
    """Rundet Zeitwerte, ohne sie hinter die rohe Trackdauer zu schieben."""
    return min(round(value, 2), duration)


def _kandidaten_berechnen(
    file_path: str, *, pfad: str, bpm: float, duration: float, first_downbeat: float,
    downbeat_confidence: float, phrase_confidence: float, phrase_anchor: float,
    phrase_unit: int, sections: list, phrases: list, cues: list,
    analyzer_in: float, analyzer_out: float, outro_covered: bool,
) -> tuple[list, list] | None:
    """Mix-Kandidaten beider Seiten berechnen; Fehler kippen die Analyse nie.
    `pfad` ("fast"/"voll") erscheint im Log, damit tools/kandidaten_messen.py die
    Laufzeit je Analysepfad trennen kann."""
    t0 = time.perf_counter()
    try:
        mix_in, mix_out = build_track_candidates(
            file_path, bpm=bpm, duration=duration, first_downbeat=first_downbeat,
            downbeat_confidence=downbeat_confidence, phrase_confidence=phrase_confidence,
            phrase_anchor=phrase_anchor, phrase_unit=phrase_unit, sections=sections,
            phrases=phrases, cues=cues, analyzer_in=analyzer_in, analyzer_out=analyzer_out,
            outro_covered=outro_covered,
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
) -> tuple[TrackStructure, list[dict], bool]:
    """Kombiniert Anfang und echtes Track-Ende mit expliziter Coverage-Luecke."""
    head_duration = min(float(librosa.get_duration(y=head_audio, sr=sr)), duration)
    structure_kwargs = {"anchor": anchor}
    if phrase_unit is not None:
        structure_kwargs["phrase_unit"] = phrase_unit
    if seconds_per_bar is not None:
        structure_kwargs["seconds_per_bar"] = seconds_per_bar
    if feature_cache is not None:
        structure_kwargs["feature_cache"] = feature_cache
    head = analyze_structure(head_audio, sr, bpm, genre, **structure_kwargs)
    for section in head.sections:
        section.end_time = min(section.end_time, head_duration)

    coverage = [{
        "start": 0.0,
        "end": _round_time_within_duration(head_duration, duration),
    }]
    if duration <= head_duration + 1.0:
        return head, coverage, True

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
        tail_audio, _ = librosa.load(
            file_path,
            sr=sr,
            mono=True,
            offset=tail_start,
            duration=max(0.0, duration - tail_start),
        )
    except (sf.LibsndfileError, RuntimeError, OSError, ValueError) as error:
        logger.warning("Track-Ende konnte nicht analysiert werden: %s", error)
        seconds_bar = seconds_per_bar or (
            (60.0 / bpm) * METER if bpm > 0 else 0.0
        )
        if duration > head_duration + 1.0:
            head.sections.append(
                TrackSection(
                    label="unanalysed",
                    start_time=_round_time_within_duration(head_duration, duration),
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
        return head, coverage, False
    tail_duration = float(librosa.get_duration(y=tail_audio, sr=sr))
    tail_end = min(duration, tail_start + tail_duration)
    if tail_duration <= 0:
        return head, coverage, False

    tail_kwargs = {"anchor": anchor - tail_start}
    if phrase_unit is not None:
        tail_kwargs["phrase_unit"] = phrase_unit
    if seconds_per_bar is not None:
        tail_kwargs["seconds_per_bar"] = seconds_per_bar
    if feature_cache is not None:
        tail_kwargs["feature_cache"] = FeatureCache(tail_audio, sr)
    tail = analyze_structure(tail_audio, sr, bpm, genre, **tail_kwargs)
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
        "start": _round_time_within_duration(tail_start, duration),
        "end": _round_time_within_duration(tail_end, duration),
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
                start_time=_round_time_within_duration(head_duration, duration),
                end_time=_round_time_within_duration(tail_start, duration),
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

    unit = int(phrase_unit) if phrase_unit and phrase_unit > 0 else 8
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


def analyze_track(file_path: str) -> Track | None:
    """Analyzes a single audio file for all v3.0 metadata, using a cache."""
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

    try:
        cache_key = generate_cache_key(file_path, rekordbox_signature)
    except Exception as error:
        logger.error("Cache-Key konnte nicht sicher erzeugt werden: %s", error)
        return None
    if not cache_key:
        logger.error("Cache-Key konnte nicht sicher erzeugt werden: %s", file_path)
        return None

    try:
        cached_track = get_cached_track(cache_key, file_path=file_path)
    except Exception as error:
        logger.warning("Cache-Lesefehler; Track wird neu analysiert: %s", error)
        cached_track = None

    if cached_track:
        cached_mode = getattr(cached_track, "analysis_mode", None)
        if cached_mode in VALID_ANALYSIS_MODES:
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
            y, sr = librosa.load(file_path, duration=LIBROSA_FAST_PATH_DURATION)
            feature_cache = FeatureCache(y, sr)
            # Echte Datei-Dauer, nicht die abgeschnittene aus y (max FAST_PATH_DURATION)
            duration = file_duration

            # Calculate energy and bass (not in Rekordbox)
            energy = calculate_energy(y)
            bass_intensity = calculate_bass_intensity(y, sr)

            lufs, lufs_status, lufs_coverage, lufs_channels, lufs_sample_rate = (
                calculate_file_lufs(file_path)
            )
            # Key aus der Rekordbox-DB = verlaesslich analysiert
            key_confidence = 1.0 if rekordbox_data.camelot_code else 0.0

            # DJ Brain: Genre-Klassifikation
            genre_result = classify_genre(
                y, sr, rekordbox_data.bpm, bass_intensity, genre
            )
            logger.info(
                f"Genre: {genre_result.genre} (confidence: {genre_result.confidence:.2f}, source: {genre_result.source})"
            )

            # Downbeat-Anker (2026-07-17): zuerst der exakte Rekordbox-Beatgrid
            # (ANLZ/PQTZ, Konfidenz 1.0), sonst eigene Schaetzung (Phase-Voting)
            grid_reader = getattr(rekordbox_importer, "get_beatgrid", None)
            rekordbox_grid = grid_reader(file_path) if callable(grid_reader) else []
            anlz_downbeat = next(
                (point["time"] for point in rekordbox_grid if point["beat"] == 1),
                None,
            )
            # Rekordbox-Phrasen (PSSI) und Cues mit Provenienz — Rohmaterial
            # fuer die Mixpunkt-Kandidaten (Spec 2026-08-21)
            cue_points = normalize_cues(
                rekordbox_data.cue_points,
                duration=file_duration,
                source=file_path,
            )
            if anlz_downbeat is not None:
                beatgrid_source = "rekordbox"
                beatgrid_validation = _validate_track_beatgrid(
                    file_path, duration, rekordbox_data.bpm, float(anlz_downbeat),
                    grid_points=rekordbox_grid, head_audio=y, head_sr=sr,
                )
                if beatgrid_validation.status == "verified":
                    first_downbeat, downbeat_confidence = float(anlz_downbeat), 1.0
                else:
                    # Das Rekordbox-Grid bleibt als Diagnose sichtbar, darf die
                    # musikalische Analyse aber nicht sperren. Fuer Mixpunkte
                    # wird in diesem Fall der Audio-Anker verwendet.
                    first_downbeat, downbeat_confidence = estimate_first_downbeat(
                        y, sr, rekordbox_data.bpm
                    )
            else:
                first_downbeat, downbeat_confidence = estimate_first_downbeat(
                    y, sr, rekordbox_data.bpm
                )
                beatgrid_source = "audio"
                beatgrid_validation = _validate_track_beatgrid(
                    file_path, duration, rekordbox_data.bpm, first_downbeat,
                    head_audio=y, head_sr=sr,
                )
            phrases = (
                rekordbox_importer.get_phrases(file_path, duration=file_duration)
                if beatgrid_source == "rekordbox"
                and beatgrid_validation.status == "verified"
                and hasattr(rekordbox_importer, "get_phrases")
                else []
            )

            phrase_unit = GENRE_PHRASE_UNITS.get(genre_result.genre, 8)
            if downbeat_confidence > 0.0:
                first_phrase, phrase_confidence = estimate_first_phrase(
                    y, sr, rekordbox_data.bpm, first_downbeat, phrase_unit
                )
            else:
                first_phrase, phrase_confidence = -1.0, 0.0
            phrase_anchor = (
                first_phrase
                if first_phrase >= 0.0
                and phrase_confidence >= PHRASE_CONFIDENCE_MIN
                else first_downbeat
            )

            # DJ Brain: Struktur-Analyse (phrase-verankert)
            structure, analysis_coverage, outro_covered = analyze_structure_windows(
                file_path,
                y,
                sr,
                rekordbox_data.bpm,
                genre_result.genre,
                duration,
                anchor=phrase_anchor,
                phrase_unit=phrase_unit,
                feature_cache=feature_cache,
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
            if section_dicts:
                mix_in_point, mix_out_point, mix_in_bars, mix_out_bars = (
                    calculate_genre_aware_mix_points(
                        section_dicts, rekordbox_data.bpm, duration,
                        genre_result.genre, anchor=phrase_anchor,
                        first_downbeat=first_downbeat,  # R3: Untergrenze am Takt-Anker
                    )
                )
                logger.info(
                    f"DJ Brain Mix-Punkte: in={mix_in_bars} bars, out={mix_out_bars} bars ({genre_result.genre})"
                )
            else:
                mix_in_point, mix_out_point, mix_in_bars, mix_out_bars = (
                    analyze_structure_and_mix_points(
                        y, sr, duration, energy, rekordbox_data.bpm,
                        genre=genre_result.genre,
                        anchor=phrase_anchor,
                        first_downbeat=first_downbeat,  # R3
                    )
                )

            # Gerichtete manuelle Cues behalten ihre Prioritaet, muessen aber
            # denselben quantisierten Intro-/Outro-Vertrag wie Analyzerpunkte
            # erfuellen. Der gemeinsame Helfer wird auch im Vollpfad benutzt.
            mix_in_point, mix_out_point = _apply_manual_mixpoint_cues(
                mix_in_point,
                mix_out_point,
                cue_points=cue_points,
                bpm=rekordbox_data.bpm,
                duration=duration,
                phrase_unit=structure.phrase_unit,
                anchor=phrase_anchor,
                sections=section_dicts,
            )
            seconds_per_bar = (60.0 / rekordbox_data.bpm) * METER
            mix_in_bars = int(mix_in_point / seconds_per_bar)
            mix_out_bars = int(mix_out_point / seconds_per_bar)

            # Audio Feature Extensions
            brightness = calculate_brightness(y, sr, feature_cache)
            vocal_instrumental = detect_vocal_instrumental(y, sr, feature_cache)
            danceability = calculate_danceability(
                y, sr, rekordbox_data.bpm, feature_cache
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
            timbre_fp = generate_timbre_fingerprint(y, sr, feature_cache)

            # Overall Track Averages for Advanced Features (VOR dem Sektions-Loop,
            # damit Sektionen ausserhalb des geladenen Audiofensters darauf
            # zurueckfallen koennen).
            avg_b, avg_m, avg_h = analyze_frequency_bands(y, sr, feature_cache)
            track_pr, track_sf = analyze_rhythm_complexity(y, sr, feature_cache)

            # Groove-Features (nur auf belastbarem Downbeat-Raster, siehe
            # compute_groove_fields). y/sr sind hier das Fast-Path-Audio.
            groove = compute_groove_fields(
                y, sr, rekordbox_data.bpm, first_downbeat, downbeat_confidence,
                feature_cache=feature_cache, sections=section_dicts,
            )

            # Update each section with detailed frequency and rhythm data
            updated_sections = []
            for sec_dict in section_dicts:
                start_s = sec_dict['start_time']
                end_s = sec_dict['end_time']

                # Extract segment
                start_sample = int(start_s * sr)
                end_sample = int(end_s * sr)
                y_seg = y[start_sample:end_sample]

                if len(y_seg) > sr: # At least 1 second
                    # Frequency Bands
                    b, m, h = analyze_frequency_bands(y_seg, sr)
                    sec_dict['avg_bass'] = b
                    sec_dict['avg_mids'] = m
                    sec_dict['avg_highs'] = h

                    # Rhythm & Texture
                    percussive_ratio, spectral_flatness = analyze_rhythm_complexity(
                        y_seg, sr, feature_cache,
                        sample_range=(start_sample, end_sample),
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
            kandidaten = _kandidaten_berechnen(
                file_path, pfad="fast", bpm=rekordbox_data.bpm, duration=duration,
                first_downbeat=first_downbeat,
                downbeat_confidence=downbeat_confidence,
                phrase_confidence=phrase_confidence,
                phrase_anchor=phrase_anchor,
                phrase_unit=structure.phrase_unit, sections=section_dicts,
                phrases=phrases, cues=cue_points,
                analyzer_in=mix_in_point, analyzer_out=mix_out_point,
                outro_covered=outro_covered,
            )
            if kandidaten is None:
                return None
            mix_in_candidates, mix_out_candidates = kandidaten
            phrase_grid = phrase_grid_from_phrases(phrases)

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
            bpm=rekordbox_data.bpm,
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
            brightness=brightness,
            vocal_instrumental=vocal_instrumental,
            danceability=danceability,
            mfcc_fingerprint=mfcc_fingerprint,
            first_downbeat=first_downbeat,
            downbeat_confidence=downbeat_confidence,
            beatgrid_source=beatgrid_source,
            beatgrid_status=beatgrid_validation.status,
            beatgrid_windows_checked=beatgrid_validation.windows_checked,
            beatgrid_max_phase_error_ms=beatgrid_validation.max_phase_error_ms,
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

        # AUDIT-FIX A-02 (2026-07-24): Degradierte Analysen NICHT persistieren —
        # sonst liefert der mtime-basierte Cache die erfundenen Default-Werte
        # (energy=50, mix_in=0.0) fuer immer zurueck, ohne sichtbaren Fehler.
        if not analysis_degraded:
            if not _persist_analysis_result(cache_key, track):
                return None
        else:
            logger.warning(
                f"Degradierte Analyse NICHT gecacht: {os.path.basename(file_path)}"
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
        y, sr = librosa.load(file_path, duration=LIBROSA_MAX_DURATION)
        feature_cache = FeatureCache(y, sr)

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
                alt_tempo = librosa.beat.tempo(y=y, sr=sr)
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

        energy = calculate_energy(y)
        bass_intensity = calculate_bass_intensity(y, sr)

        lufs, lufs_status, lufs_coverage, lufs_channels, lufs_sample_rate = (
            calculate_file_lufs(file_path)
        )

        # DJ Brain: Genre-Klassifikation
        genre_result = classify_genre(y, sr, bpm, bass_intensity, genre)
        logger.info(
            f"Genre: {genre_result.genre} (confidence: {genre_result.confidence:.2f}, source: {genre_result.source})"
        )

        # Ein BPM-loser Rekordbox-Datensatz kann dennoch ein PQTZ/PSSI-Paket
        # besitzen. Es wird erst gegen das jetzt gemessene Tempo validiert;
        # bei Mismatch bleibt nur die Diagnose, der Anker kommt aus dem Audio.
        rekordbox_grid: list[dict] = []
        if rekordbox_data is not None:
            grid_reader = getattr(rekordbox_importer, "get_beatgrid", None)
            rekordbox_grid = (
                grid_reader(file_path) if callable(grid_reader) else []
            )
        anlz_downbeat = next(
            (point["time"] for point in rekordbox_grid if point["beat"] == 1),
            None,
        )
        if anlz_downbeat is not None:
            beatgrid_source = "rekordbox"
            beatgrid_validation = _validate_track_beatgrid(
                file_path, duration, bpm, float(anlz_downbeat),
                grid_points=rekordbox_grid, head_audio=y, head_sr=sr,
            )
            if beatgrid_validation.status == "verified":
                first_downbeat = float(anlz_downbeat)
                downbeat_confidence = 1.0
            else:
                first_downbeat, downbeat_confidence = estimate_first_downbeat(
                    y, sr, bpm
                )
        else:
            first_downbeat, downbeat_confidence = estimate_first_downbeat(y, sr, bpm)
            beatgrid_source = "audio"
            beatgrid_validation = _validate_track_beatgrid(
                file_path, duration, bpm, first_downbeat, head_audio=y, head_sr=sr
            )
        phrases = (
            rekordbox_importer.get_phrases(file_path, duration=file_duration)
            if rekordbox_data is not None
            and beatgrid_source == "rekordbox"
            and beatgrid_validation.status == "verified"
            and hasattr(rekordbox_importer, "get_phrases")
            else []
        )
        cue_points = (
            normalize_cues(
                rekordbox_data.cue_points,
                duration=file_duration,
                source=file_path,
            )
            if rekordbox_data is not None else []
        )

        phrase_unit = GENRE_PHRASE_UNITS.get(genre_result.genre, 8)
        if downbeat_confidence > 0.0:
            first_phrase, phrase_confidence = estimate_first_phrase(
                y, sr, bpm, first_downbeat, phrase_unit
            )
        else:
            first_phrase, phrase_confidence = -1.0, 0.0
        phrase_anchor = (
            first_phrase
            if first_phrase >= 0.0
            and phrase_confidence >= PHRASE_CONFIDENCE_MIN
            else first_downbeat
        )
        median_bar_length = _median_seconds_per_bar(beat_frames, sr, bpm)

        # DJ Brain: Struktur-Analyse (phrase-verankert)
        structure, analysis_coverage, outro_covered = analyze_structure_windows(
            file_path,
            y,
            sr,
            bpm,
            genre_result.genre,
            duration,
            anchor=phrase_anchor,
            phrase_unit=phrase_unit,
            seconds_per_bar=median_bar_length,
            feature_cache=feature_cache,
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
        if section_dicts:
            mix_in_point, mix_out_point, mix_in_bars, mix_out_bars = (
                calculate_genre_aware_mix_points(
                    section_dicts, bpm, duration, genre_result.genre,
                    anchor=phrase_anchor,
                    first_downbeat=first_downbeat,  # R3: Untergrenze am Takt-Anker
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
                )
            )

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
        seconds_per_bar = (60.0 / bpm) * METER
        mix_in_bars = int(mix_in_point / seconds_per_bar)
        mix_out_bars = int(mix_out_point / seconds_per_bar)

        # Audio Feature Extensions
        brightness = calculate_brightness(y, sr, feature_cache)
        vocal_instrumental = detect_vocal_instrumental(y, sr, feature_cache)
        danceability = calculate_danceability(
            y, sr, bpm, feature_cache, beat_frames=beat_frames
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
            # We already have y and sr loaded. For detailed analysis, use full signal.
            timbre_fp = generate_timbre_fingerprint(y, sr, feature_cache)
            
            updated_sections = []
            for sec_dict in section_dicts:
                start_s = sec_dict['start_time']
                end_s = sec_dict['end_time']
                start_sample = int(start_s * sr)
                end_sample = int(end_s * sr)
                y_seg = y[start_sample:end_sample]
                
                if len(y_seg) > sr:
                    b, m, h = analyze_frequency_bands(y_seg, sr)
                    percussive_ratio, spectral_flatness = analyze_rhythm_complexity(
                        y_seg, sr, feature_cache,
                        sample_range=(start_sample, end_sample),
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
            
            avg_b, avg_m, avg_h = analyze_frequency_bands(y, sr, feature_cache)
            track_pr, track_sf = analyze_rhythm_complexity(y, sr, feature_cache)

            # Groove-Features (nur auf belastbarem Downbeat-Raster, siehe
            # compute_groove_fields).
            groove = compute_groove_fields(
                y, sr, bpm, first_downbeat, downbeat_confidence,
                feature_cache=feature_cache, sections=section_dicts,
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
        phrase_grid = phrase_grid_from_phrases(phrases)
        kandidaten = _kandidaten_berechnen(
            file_path, pfad="voll", bpm=bpm, duration=duration,
            first_downbeat=first_downbeat,
            downbeat_confidence=downbeat_confidence,
            phrase_confidence=phrase_confidence,
            phrase_anchor=phrase_anchor,
            phrase_unit=structure.phrase_unit, sections=section_dicts,
            phrases=phrases, cues=cue_points,
            analyzer_in=mix_in_point, analyzer_out=mix_out_point,
            outro_covered=outro_covered,
        )
        if kandidaten is None:
            return None
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
            brightness=brightness,
            vocal_instrumental=vocal_instrumental,
            danceability=danceability,
            mfcc_fingerprint=mfcc_fingerprint,
            first_downbeat=first_downbeat,
            downbeat_confidence=downbeat_confidence,
            beatgrid_source=beatgrid_source,
            beatgrid_status=beatgrid_validation.status,
            beatgrid_windows_checked=beatgrid_validation.windows_checked,
            beatgrid_max_phase_error_ms=beatgrid_validation.max_phase_error_ms,
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

        if not _persist_analysis_result(cache_key, track):
            return None
        return track

    except Exception as e:
        logger.error(f"Fehler bei der Librosa-Analyse von {file_path}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None
