"""
Configuration constants for audio analysis.
Centralizes all magic numbers and configurable parameters.
"""

# === Audio Processing Parameters ===
HOP_LENGTH = 1024  # Frame hop for feature extraction
METER = 4  # 4/4 time signature (beats per bar)

# === Intro/Outro Detection Thresholds ===
INTRO_PERCENTAGE = 0.15  # Default: first 15% is intro
OUTRO_PERCENTAGE = 0.85  # Default: last 85% starts outro

INTRO_MAX_PERCENTAGE = 0.25  # Intro can't be longer than 25%
OUTRO_MIN_PERCENTAGE = 0.75  # Outro can't start before 75%

MIN_SEGMENT_DURATION = 5.0  # Minimum segment length in seconds

# Heuristic multipliers for intro/outro detection
RMS_THRESHOLD = 0.4  # Segment RMS must be < 40% of average (intro/outro detection)
ONSET_THRESHOLD = 0.5  # Segment onset must be < 50% of average
CENTROID_THRESHOLD = 0.7  # Segment centroid must be < 70% of average

# === Mix Point Selection ===
MIX_POINT_BUFFER = 5.0  # Seconds buffer from intro/outro
MIN_MIX_DURATION = 10.0  # Minimum seconds between mix-in and mix-out
MIX_IN_MAX_PERCENTAGE = 0.5  # Mix-in must be in first half
MIX_OUT_MIN_PERCENTAGE = 0.5  # Mix-out must be in second half

# Fallback percentages when no suitable points found
FALLBACK_MIX_IN = 0.25  # 25% for mix-in
FALLBACK_MIX_OUT = 0.75  # 75% for mix-out

# === Structural Segmentation (ruptures) ===
RUPTURES_JUMP = 5  # Jump parameter for Pelt algorithm (higher = faster)
RUPTURES_MIN_SIZE_SECONDS = 5.0  # Minimum segment size in seconds
RUPTURES_PENALTY_MULTIPLIER = 2.0  # Penalty multiplier for change point detection

# === Phrase Detection ===
BARS_PER_PHRASE = 8  # Standard phrase length (8 bars)

# === Performance Optimization ===
# Default BPM for fallback when BPM detection fails
DEFAULT_BPM = 120.0
DEFAULT_SECONDS_PER_BAR = 2.0  # Approximate seconds per bar at 120 BPM

# === Error Handling Fallbacks ===
FALLBACK_INTRO_END = 0.2  # 20% fallback
FALLBACK_OUTRO_START = 0.8  # 80% fallback
