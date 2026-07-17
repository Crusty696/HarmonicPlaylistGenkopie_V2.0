"""
Genre Classifier for DJ Brain

Classifies electronic music tracks into 9 target genres:
- Psytrance (135-150 BPM, bright, tonal, high energy variance)
- Tech House (124-135 BPM, groove-heavy, percussive)
- Progressive House/Trance (120-140 BPM, smooth energy, layered)
- Melodic Techno (120-130 BPM, melodic, moderate dynamics)
- Techno (130-150 BPM, driving, industrial, hard-hitting)
- Deep House (118-128 BPM, warm, smooth, soulful)
- Trance (128-145 BPM, euphoric, uplifting, melodic builds)
- Drum & Bass (160-180 BPM, fast breakbeats, heavy bass)
- Minimal (120-132 BPM, sparse, hypnotic, repetitive)

Uses a weighted rule-based approach with audio features from librosa.
No ML training data or additional dependencies required.

Sources:
- Pioneer DJ Blog: Genre mixing techniques
- Psytrance Connection: BPM ranges
- Native Instruments: Genre definitions
- ZIPDJ: Techno BPM guide
- Beatportal: Genre guides
- Resident Advisor: Genre definitions
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
import numpy as np
import librosa
from .config import GENRE_CONFIDENCE_THRESHOLD, DNB_MINIMUM_BPM

logger = logging.getLogger(__name__)


# === Genre Classification Result ===


@dataclass
class GenreClassification:
    """Result of genre classification."""

    genre: str  # "Psytrance", "Tech House", "Progressive", "Melodic Techno",
    # "Techno", "Deep House", "Trance", "Drum & Bass", "Minimal", "Unknown"
    confidence: float  # 0.0-1.0
    source: str  # "audio_analysis" or "id3_tag"
    scores: dict = field(default_factory=dict)  # Per-genre scores for transparency
    # M1 Audit-Fix: MFCC-Mean direkt mitliefern (vermeidet doppelte Berechnung)
    mfcc_fingerprint: list = field(default_factory=list)


# === Audio Feature Extraction ===


@dataclass
class GenreFeatures:
    """Audio features used for genre classification."""

    bpm: float
    spectral_centroid_mean: float  # Brightness (Hz)
    spectral_centroid_std: float  # Brightness variance
    spectral_rolloff_mean: float  # Where high-freq energy drops off (Hz)
    spectral_flatness_mean: float  # Noise-like (1.0) vs tonal (0.0)
    onset_rate: float  # Percussive events per second
    rms_variance: float  # Energy dynamics (normalized)
    bass_ratio: float  # Bass intensity (0-100 from existing analysis)
    mfcc_means: np.ndarray  # First 13 MFCC coefficients (timbral fingerprint)


def extract_genre_features(
    y: np.ndarray, sr: int, bpm: float, bass_intensity: int
) -> GenreFeatures:
    """
    Extract audio features relevant for genre classification.

    All features computed from the already-loaded audio buffer (y, sr),
    so no additional file I/O is needed.

    Args:
        y: Audio signal (mono, from librosa.load)
        sr: Sample rate
        bpm: Already-computed BPM
        bass_intensity: Already-computed bass intensity (0-100)

    Returns:
        GenreFeatures with all extracted values
    """
    hop_length = 1024

    # Spectral Centroid - indicates brightness
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop_length)[0]
    centroid_mean = float(np.mean(centroid))
    centroid_std = float(np.std(centroid))

    # Spectral Rolloff - where high-frequency energy drops
    rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr, hop_length=hop_length)[0]
    rolloff_mean = float(np.mean(rolloff))

    # Spectral Flatness - noise-like vs tonal
    flatness = librosa.feature.spectral_flatness(y=y, hop_length=hop_length)[0]
    flatness_mean = float(np.mean(flatness))

    # Onset Rate - percussive events per second
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)
    onsets = librosa.onset.onset_detect(
        y=y, sr=sr, hop_length=hop_length, onset_envelope=onset_env, backtrack=False
    )
    duration = librosa.get_duration(y=y, sr=sr)
    onset_rate = len(onsets) / duration if duration > 0 else 0.0

    # RMS Energy Variance - dynamics over time
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    rms_mean = float(np.mean(rms))
    rms_var = float(np.var(rms)) / (rms_mean**2) if rms_mean > 0 else 0.0

    # MFCCs - timbral fingerprint (first 13 coefficients)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=hop_length)
    mfcc_means = np.mean(mfcc, axis=1)

    return GenreFeatures(
        bpm=bpm,
        spectral_centroid_mean=centroid_mean,
        spectral_centroid_std=centroid_std,
        spectral_rolloff_mean=rolloff_mean,
        spectral_flatness_mean=flatness_mean,
        onset_rate=onset_rate,
        rms_variance=rms_var,
        bass_ratio=float(bass_intensity),
        mfcc_means=mfcc_means,
    )


# === Genre Profiles ===
# GenreProfile + GENRE_PROFILES leben zentral in genres.py (Single Source of
# Truth mit Import-Validierung, Audit-Refactoring 2026-07-17)
from .genres import GenreProfile, GENRE_PROFILES, ID3_GENRE_MAP, CANONICAL_GENRES


# Feature weights for scoring
WEIGHT_BPM = 0.35  # BPM is the strongest discriminator
WEIGHT_SPECTRAL = 0.20  # Brightness + rolloff
WEIGHT_RHYTHM = 0.20  # Onset rate + flatness
WEIGHT_DYNAMICS = 0.15  # RMS variance
WEIGHT_BASS = 0.10  # Bass intensity

# Minimum confidence to accept a classification (aus config.py)
MIN_CONFIDENCE = GENRE_CONFIDENCE_THRESHOLD


# === ID3 Genre Tag Matching ===
# ID3_GENRE_MAP lebt zentral in genres.py (siehe Import oben)



def match_id3_genre(id3_genre: str) -> str | None:
    """
    Try to match an ID3 genre tag to one of our target genres.

    Uses case-insensitive fuzzy matching against known genre strings.

    Args:
        id3_genre: Genre string from ID3 tag

    Returns:
        Matched genre name or None if no match
    """
    if not id3_genre or id3_genre == "Unknown":
        return None

    genre_lower = id3_genre.strip().lower()

    # Direct match
    if genre_lower in ID3_GENRE_MAP:
        return ID3_GENRE_MAP[genre_lower]

    # Substring match (e.g., "Psytrance / Full On" contains "psytrance").
    # M13-Fix: nur noch tag-in-genre — die Rueckrichtung band generische Tags
    # ("house", "tech") greedy an das erste spezifische Genre. Laengste Tags
    # zuerst, damit "tech house" vor "house" gewinnt.
    for tag in sorted(ID3_GENRE_MAP, key=len, reverse=True):
        if tag in genre_lower:
            return ID3_GENRE_MAP[tag]

    return None


# === Scoring Functions ===


def _score_range(
    value: float, range_min: float, range_max: float, center: float = None
) -> float:
    """
    Score how well a value fits within a range.

    Scoring-Zonen (H2 Audit-Fix: Dokumentation verbessert):
    - distance <= 0.5: Innerhalb der Range → 1.0 (center) bis 0.8 (Rand)
    - distance <= 1.0: Knapp ausserhalb → 0.8 bis 0.2 (linearer Abfall)
    - distance <= 2.0: Weit ausserhalb → exponentieller Abfall bis ~0.0
    - distance > 2.0:  Hard-Cutoff → 0.0 (verhindert ueberraschende Zuweisungen)

    Args:
        value: Zu bewertender Wert (z.B. BPM)
        range_min: Untere Grenze der Genre-Range
        range_max: Obere Grenze der Genre-Range
        center: Optimaler Wert (Default: Mitte der Range)

    Returns:
        float: Score zwischen 0.0 und 1.0
    """
    if center is None:
        center = (range_min + range_max) / 2.0

    range_width = range_max - range_min
    if range_width <= 0:
        return 1.0 if value == center else 0.0

    # Distanz vom Center, normalisiert auf Range-Breite
    distance = abs(value - center) / range_width

    if distance <= 0.5:
        # Innerhalb der Range: hoher Score
        return 1.0 - (distance * 0.4)  # 1.0 at center, 0.8 at edges
    elif distance <= 1.0:
        # Knapp ausserhalb: moderater Score
        return 0.8 - (distance - 0.5) * 1.2  # 0.8 at edge, 0.2 at 1x outside
    elif distance <= 2.0:
        # Weit ausserhalb: exponentieller Abfall
        return max(0.0, 0.2 * np.exp(-(distance - 1.0)))
    else:
        # H2 Hard-Cutoff: >2x Range-Breite entfernt → definitiv kein Match
        return 0.0


def _score_genre(features: GenreFeatures, profile: GenreProfile) -> float:
    """
    Calculate how well the extracted features match a genre profile.

    Returns a weighted score between 0.0 and 1.0.
    """
    # BPM score (strongest signal)
    bpm_score = _score_range(
        features.bpm, *profile.bpm_range, center=profile.bpm_center
    )

    # Spectral score (brightness)
    centroid_score = _score_range(
        features.spectral_centroid_mean, *profile.spectral_centroid_range
    )

    # Rhythm score (onset rate + flatness)
    onset_score = _score_range(features.onset_rate, *profile.onset_rate_range)
    flatness_score = _score_range(
        features.spectral_flatness_mean, *profile.spectral_flatness_range
    )
    rhythm_score = (onset_score + flatness_score) / 2.0

    # Dynamics score (RMS variance)
    dynamics_score = _score_range(features.rms_variance, *profile.rms_variance_range)

    # Bass score
    bass_score = _score_range(features.bass_ratio, *profile.bass_ratio_range)

    # Weighted total
    total = (
        WEIGHT_BPM * bpm_score
        + WEIGHT_SPECTRAL * centroid_score
        + WEIGHT_RHYTHM * rhythm_score
        + WEIGHT_DYNAMICS * dynamics_score
        + WEIGHT_BASS * bass_score
    )

    return float(np.clip(total, 0.0, 1.0))


# === Main Classification Function ===


def classify_genre(
    y: np.ndarray,
    sr: int,
    bpm: float,
    bass_intensity: int,
    id3_genre: str = "Unknown",
) -> GenreClassification:
    """
    Classify a track into one of the target electronic music genres.

    Priority:
    1. ID3 tag match (if available and matches a target genre) -> confidence=1.0
    2. Audio-based classification using spectral/rhythmic features

    Args:
        y: Audio signal (mono, from librosa.load)
        sr: Sample rate
        bpm: Already-computed BPM value
        bass_intensity: Already-computed bass intensity (0-100)
        id3_genre: Genre string from ID3 tag

    Returns:
        GenreClassification with genre, confidence, source, and per-genre scores
    """
    # Step 1: Try ID3 tag match first
    id3_match = match_id3_genre(id3_genre)
    if id3_match:
        return GenreClassification(
            genre=id3_match,
            confidence=1.0,
            source="id3_tag",
            scores={id3_match: 1.0},
        )

    # Step 2: Audio-based classification
    try:
        features = extract_genre_features(y, sr, bpm, bass_intensity)
        # M1 Audit-Fix: MFCC-Mean fuer Fingerprint mitfuehren (spart doppelte Berechnung)
        mfcc_fp = [round(float(v), 4) for v in features.mfcc_means]
    except Exception as e:
        logger.error(f"Feature-Extraktion fehlgeschlagen: {e}")
        return GenreClassification(
            genre="Unknown", confidence=0.0, source="audio_analysis",
            scores={}, mfcc_fingerprint=[]
        )

    # Step 3: Score each genre
    scores = {}
    for genre_name, profile in GENRE_PROFILES.items():
        scores[genre_name] = _score_genre(features, profile)
        # Hard BPM-Guard: DnB braucht echte 160+ BPM (schuetzt gegen Halftime-Korrektur-Fehler)
        if genre_name == "Drum & Bass" and features.bpm < DNB_MINIMUM_BPM:
            scores[genre_name] = 0.0

    # Step 4: Pick the best match
    if not scores:
        return GenreClassification(
            genre="Unknown", confidence=0.0, source="audio_analysis", scores=scores
        )

    best_genre = max(scores, key=scores.get)
    best_score = scores[best_genre]

    # Calculate confidence from the gap between best and second-best
    sorted_scores = sorted(scores.values(), reverse=True)
    if len(sorted_scores) >= 2:
        gap = sorted_scores[0] - sorted_scores[1]
        # Confidence: combine absolute score with relative gap
        # High score + big gap = high confidence
        confidence = (best_score * 0.6) + (gap * 2.0 * 0.4)
        confidence = float(np.clip(confidence, 0.0, 1.0))
    else:
        confidence = best_score

    # If confidence is too low, mark as Unknown
    if confidence < MIN_CONFIDENCE:
        return GenreClassification(
            genre="Unknown",
            confidence=confidence,
            source="audio_analysis",
            scores=scores,
            mfcc_fingerprint=mfcc_fp,
        )

    return GenreClassification(
        genre=best_genre,
        confidence=round(confidence, 3),
        source="audio_analysis",
        scores={k: round(v, 3) for k, v in scores.items()},
        mfcc_fingerprint=mfcc_fp,
    )
