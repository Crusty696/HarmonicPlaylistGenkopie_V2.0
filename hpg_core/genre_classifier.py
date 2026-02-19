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

from dataclasses import dataclass, field
import numpy as np
import librosa
from .config import GENRE_CONFIDENCE_THRESHOLD, DNB_MINIMUM_BPM


# === Genre Classification Result ===


@dataclass
class GenreClassification:
    """Result of genre classification."""

    genre: str  # "Psytrance", "Tech House", "Progressive", "Melodic Techno",
    # "Techno", "Deep House", "Trance", "Drum & Bass", "Minimal", "Unknown"
    confidence: float  # 0.0-1.0
    source: str  # "audio_analysis" or "id3_tag"
    scores: dict = field(default_factory=dict)  # Per-genre scores for transparency


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
# Based on research from Pioneer DJ, Club Ready DJ School, Native Instruments,
# Psytrance Connection, ZIPDJ, Beatportal, Samplesound


@dataclass
class GenreProfile:
    """Defines characteristic audio features for a genre."""

    name: str
    bpm_range: tuple[float, float]
    bpm_center: float  # Most common BPM
    spectral_centroid_range: tuple[float, float]  # Hz
    onset_rate_range: tuple[float, float]  # events/sec
    spectral_flatness_range: tuple[float, float]  # 0-1
    rms_variance_range: tuple[float, float]  # normalized
    bass_ratio_range: tuple[float, float]  # 0-100


GENRE_PROFILES: dict[str, GenreProfile] = {
    "Psytrance": GenreProfile(
        name="Psytrance",
        bpm_range=(135, 150),
        bpm_center=142,
        # Psytrance is bright - acid synths, layered high-freq elements
        spectral_centroid_range=(2000, 4500),
        # Moderate onset rate - driving kick but less percussive variety
        onset_rate_range=(2.0, 5.0),
        # More tonal (acid bass, synth leads) = lower flatness
        spectral_flatness_range=(0.01, 0.08),
        # High energy variance (big drops and breakdowns)
        rms_variance_range=(0.15, 0.6),
        # High bass intensity (driving basslines)
        bass_ratio_range=(50, 90),
    ),
    "Tech House": GenreProfile(
        name="Tech House",
        bpm_range=(124, 135),
        bpm_center=128,
        # Mid-range brightness - groovy but not as bright as psytrance
        spectral_centroid_range=(1500, 3500),
        # High onset rate - lots of percussion, hats, shakers
        onset_rate_range=(3.5, 7.0),
        # More noise-like (percussion heavy) = higher flatness
        spectral_flatness_range=(0.04, 0.15),
        # Lower energy variance - consistent groove
        rms_variance_range=(0.05, 0.25),
        # Moderate bass - groove-focused, not bass-dominated
        bass_ratio_range=(35, 70),
    ),
    "Progressive": GenreProfile(
        name="Progressive",
        bpm_range=(120, 140),
        bpm_center=126,
        # Moderate brightness - layered pads, subtle melodies
        spectral_centroid_range=(1200, 3200),
        # Lower onset rate - less percussion, more atmosphere
        onset_rate_range=(1.5, 4.5),
        # Mixed tonal/noise content
        spectral_flatness_range=(0.03, 0.12),
        # Low-moderate variance - gradual energy changes
        rms_variance_range=(0.03, 0.20),
        # Moderate bass
        bass_ratio_range=(30, 65),
    ),
    "Melodic Techno": GenreProfile(
        name="Melodic Techno",
        bpm_range=(120, 130),
        bpm_center=125,
        # Moderate-high brightness - synth melodies, pads
        spectral_centroid_range=(1500, 3800),
        # Moderate onset rate - rhythmic but melodic
        onset_rate_range=(2.5, 5.5),
        # More tonal (melodies, chords) = lower flatness
        spectral_flatness_range=(0.02, 0.10),
        # Moderate variance - breakdowns and builds
        rms_variance_range=(0.08, 0.35),
        # Moderate bass - balanced with melodic content
        bass_ratio_range=(35, 70),
    ),
    "Techno": GenreProfile(
        name="Techno",
        bpm_range=(130, 150),
        bpm_center=138,
        # Moderate brightness - industrial, dark, raw sounds
        spectral_centroid_range=(1800, 4000),
        # High onset rate - relentless percussion, hats
        onset_rate_range=(3.5, 7.0),
        # Higher flatness - noise elements, industrial textures
        spectral_flatness_range=(0.05, 0.18),
        # Low-moderate variance - consistent driving energy
        rms_variance_range=(0.04, 0.22),
        # High bass - powerful kicks, sub bass
        bass_ratio_range=(50, 90),
    ),
    "Deep House": GenreProfile(
        name="Deep House",
        bpm_range=(118, 128),
        bpm_center=123,
        # Lower brightness - warm pads, smooth keys, filtered sounds
        spectral_centroid_range=(1000, 2800),
        # Moderate onset rate - laid-back groove
        onset_rate_range=(2.0, 4.5),
        # Mixed tonal/noise - warm chords with shuffled hats
        spectral_flatness_range=(0.03, 0.12),
        # Low variance - smooth, consistent energy
        rms_variance_range=(0.02, 0.15),
        # Moderate bass - deep but not overpowering
        bass_ratio_range=(30, 65),
    ),
    "Trance": GenreProfile(
        name="Trance",
        bpm_range=(128, 145),
        bpm_center=138,
        # High brightness - euphoric synths, supersaw leads, uplifting melodies
        spectral_centroid_range=(2200, 5000),
        # Moderate onset rate - arpeggios, plucks, but not percussion-heavy
        onset_rate_range=(2.0, 5.5),
        # Low flatness - very tonal (melodies, pads, supersaw)
        spectral_flatness_range=(0.01, 0.08),
        # High variance - big breakdowns, builds, drops
        rms_variance_range=(0.15, 0.55),
        # Moderate-high bass - solid kick, rolling bass
        bass_ratio_range=(40, 80),
    ),
    "Drum & Bass": GenreProfile(
        name="Drum & Bass",
        bpm_range=(160, 180),
        bpm_center=174,
        # Moderate-high brightness - fast snares, cymbals, reese bass harmonics
        spectral_centroid_range=(1800, 4200),
        # Very high onset rate - fast breakbeats, rapid-fire drums
        onset_rate_range=(5.0, 10.0),
        # Moderate flatness - mix of tonal bass and percussive noise
        spectral_flatness_range=(0.04, 0.15),
        # High variance - drops, breaks, switches
        rms_variance_range=(0.10, 0.50),
        # Very high bass - massive sub bass, reese bass
        bass_ratio_range=(60, 95),
    ),
    "Minimal": GenreProfile(
        name="Minimal",
        bpm_range=(120, 132),
        bpm_center=126,
        # Low brightness - sparse, filtered, subtle textures
        spectral_centroid_range=(800, 2500),
        # Low-moderate onset rate - sparse percussion, space
        onset_rate_range=(1.5, 4.0),
        # Moderate flatness - percussive clicks, subtle textures
        spectral_flatness_range=(0.03, 0.13),
        # Very low variance - hypnotic, repetitive, consistent
        rms_variance_range=(0.01, 0.12),
        # Moderate bass - subtle, deep, not overwhelming
        bass_ratio_range=(25, 60),
    ),
}

# Feature weights for scoring
WEIGHT_BPM = 0.35  # BPM is the strongest discriminator
WEIGHT_SPECTRAL = 0.20  # Brightness + rolloff
WEIGHT_RHYTHM = 0.20  # Onset rate + flatness
WEIGHT_DYNAMICS = 0.15  # RMS variance
WEIGHT_BASS = 0.10  # Bass intensity

# Minimum confidence to accept a classification (aus config.py)
MIN_CONFIDENCE = GENRE_CONFIDENCE_THRESHOLD


# === ID3 Genre Tag Matching ===

# Mapping of common ID3 genre tag strings to our target genres
ID3_GENRE_MAP: dict[str, str] = {
    # Psytrance variants
    "psytrance": "Psytrance",
    "psy trance": "Psytrance",
    "psy-trance": "Psytrance",
    "psychedelic trance": "Psytrance",
    "goa trance": "Psytrance",
    "goa": "Psytrance",
    "full on": "Psytrance",
    "full-on": "Psytrance",
    "dark psy": "Psytrance",
    "dark psytrance": "Psytrance",
    "forest": "Psytrance",
    "hi-tech": "Psytrance",
    "hitech": "Psytrance",
    # Tech House variants
    "tech house": "Tech House",
    "tech-house": "Tech House",
    "techhouse": "Tech House",
    "minimal tech house": "Tech House",
    "bass house": "Tech House",
    # Progressive variants
    "progressive": "Progressive",
    "progressive house": "Progressive",
    "progressive trance": "Progressive",
    "prog house": "Progressive",
    "prog trance": "Progressive",
    "prog": "Progressive",
    "deep progressive": "Progressive",
    # Melodic Techno variants
    "melodic techno": "Melodic Techno",
    "melodic house & techno": "Melodic Techno",
    "melodic house": "Melodic Techno",
    "melodic house/techno": "Melodic Techno",
    "indie dance": "Melodic Techno",
    "organic house": "Melodic Techno",
    "afro house": "Melodic Techno",
    # Techno variants
    "techno": "Techno",
    "hard techno": "Techno",
    "industrial techno": "Techno",
    "acid techno": "Techno",
    "detroit techno": "Techno",
    "peak time techno": "Techno",
    "peak time / driving": "Techno",
    "peak time / driving techno": "Techno",
    "raw techno": "Techno",
    "warehouse techno": "Techno",
    # Deep House variants
    "deep house": "Deep House",
    "deep-house": "Deep House",
    "deephouse": "Deep House",
    "soulful house": "Deep House",
    "lounge house": "Deep House",
    "deep tech": "Deep House",
    "chill house": "Deep House",
    "jazzy house": "Deep House",
    # Trance variants
    "trance": "Trance",
    "uplifting trance": "Trance",
    "vocal trance": "Trance",
    "epic trance": "Trance",
    "euphoric trance": "Trance",
    "dream trance": "Trance",
    "hard trance": "Trance",
    "classic trance": "Trance",
    "tech trance": "Trance",
    "eurotrance": "Trance",
    # Drum & Bass variants
    "drum & bass": "Drum & Bass",
    "drum and bass": "Drum & Bass",
    "drum&bass": "Drum & Bass",
    "dnb": "Drum & Bass",
    "d&b": "Drum & Bass",
    "d'n'b": "Drum & Bass",
    "jungle": "Drum & Bass",
    "liquid dnb": "Drum & Bass",
    "liquid drum & bass": "Drum & Bass",
    "neurofunk": "Drum & Bass",
    "liquid funk": "Drum & Bass",
    "jump up": "Drum & Bass",
    "breakbeat": "Drum & Bass",
    # Minimal variants
    "minimal": "Minimal",
    "minimal techno": "Minimal",
    "minimal house": "Minimal",
    "minimal tech": "Minimal",
    "micro house": "Minimal",
    "microhouse": "Minimal",
    "clicks & cuts": "Minimal",
    "glitch": "Minimal",
}


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

    # Substring match (e.g., "Psytrance / Full On" contains "psytrance")
    for tag, target_genre in ID3_GENRE_MAP.items():
        if tag in genre_lower or genre_lower in tag:
            return target_genre

    return None


# === Scoring Functions ===


def _score_range(
    value: float, range_min: float, range_max: float, center: float = None
) -> float:
    """
    Score how well a value fits within a range.

    Returns 1.0 if at the center, drops off with distance.
    Returns 0.0 if far outside the range.
    """
    if center is None:
        center = (range_min + range_max) / 2.0

    range_width = range_max - range_min
    if range_width <= 0:
        return 1.0 if value == center else 0.0

    # Distance from center, normalized by range width
    distance = abs(value - center) / range_width

    if distance <= 0.5:
        # Inside the range: high score
        return 1.0 - (distance * 0.4)  # 1.0 at center, 0.8 at edges
    elif distance <= 1.0:
        # Just outside range: moderate score
        return 0.8 - (distance - 0.5) * 1.2  # 0.8 at edge, 0.2 at 1x outside
    else:
        # Far outside: low score with exponential decay
        return max(0.0, 0.2 * np.exp(-(distance - 1.0)))


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
    except Exception as e:
        print(f"  [GENRE] Feature extraction failed: {e}")
        return GenreClassification(
            genre="Unknown", confidence=0.0, source="audio_analysis", scores={}
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
        )

    return GenreClassification(
        genre=best_genre,
        confidence=round(confidence, 3),
        source="audio_analysis",
        scores={k: round(v, 3) for k, v in scores.items()},
    )
