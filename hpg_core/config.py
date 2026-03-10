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

# === DJ Brain Configuration ===
DJ_BRAIN_ENABLED = True  # Master-Schalter fuer DJ Brain
DJ_BRAIN_FALLBACK_ON_UNKNOWN = True  # Fallback auf generische Logik bei "Unknown"

# Genre Classification
GENRE_CONFIDENCE_THRESHOLD = (
    0.4  # Minimum Confidence fuer Genre-Akzeptanz (war 0.3 - zu niedrig)
)
GENRE_ID3_OVERRIDE = True  # ID3-Tag Genre hat Vorrang wenn es matched

# Drum & Bass: Mindest-BPM fuer Klassifikation (schuetzt gegen BPM-Halftime-Fehler)
# Tracks unter 155 BPM koennen nicht als DnB klassifiziert werden
DNB_MINIMUM_BPM = 155.0

# Halftime-Korrektur: Maximales Ergebnis nach Verdoppelung
# Wenn bpm*2 > BPM_HALFTIME_MAX_RESULT, wird NICHT verdoppelt
# (verhindert z.B. ~92 BPM -> 184 BPM -> falsche DnB-Klassifikation)
BPM_HALFTIME_MAX_RESULT = 155.0

# Genre BPM Ranges (min, max)
PSYTRANCE_BPM_RANGE = (135, 150)
TECH_HOUSE_BPM_RANGE = (124, 135)
PROGRESSIVE_BPM_RANGE = (120, 140)
MELODIC_TECHNO_BPM_RANGE = (120, 130)
TECHNO_BPM_RANGE = (130, 150)
DEEP_HOUSE_BPM_RANGE = (118, 128)
TRANCE_BPM_RANGE = (128, 145)
DRUM_AND_BASS_BPM_RANGE = (160, 180)
MINIMAL_BPM_RANGE = (120, 132)

# Genre Weight in Playlist-Kompatibilitaet
GENRE_WEIGHT_WITH_DJ_BRAIN = 0.2  # Wenn DJ Brain Genre-Daten vorhanden
GENRE_WEIGHT_WITHOUT_DJ_BRAIN = 0.1  # Fallback ohne DJ Brain Daten

# === Librosa Memory Protection (K2 Audit-Fix) ===
# Maximale Lade-Dauer in Sekunden — begrenzt RAM-Verbrauch bei langen Tracks.
# Rekordbox Fast-Path: BPM/Key kommt aus DB, daher reichen 120s fuer Energy/Genre.
# Volle Analyse: 600s (10 Min) als Sicherheitsnetz gegen riesige Dateien.
LIBROSA_FAST_PATH_DURATION = 120  # Sekunden (fuer Rekordbox-Pfad)
LIBROSA_MAX_DURATION = 600  # Sekunden (fuer volle Analyse, Safety-Net)

# === Parallel Analysis ===
PARALLEL_ANALYSIS_TIMEOUT = 60  # Sekunden pro Track (schuetzt gegen korrupte Dateien)
PARALLEL_MAX_WORKERS = None  # None = automatisch (cpu_count basiert), oder feste Zahl

# === Cache Lock ===
CACHE_LOCK_TIMEOUT = 5.0  # Sekunden (vorher 2.0 — zu kurz bei langsamer Disk/SSD)

# === Structure Analysis ===
SECTION_ENERGY_THRESHOLD = 0.3  # Novelty-Peak Threshold fuer Sektions-Erkennung (0.1-0.5)

# === BPM Half/Double Tolerance ===
BPM_HALF_DOUBLE_ENABLED = True  # 140 BPM ↔ 70 BPM als kompatibel erkennen
BPM_HALF_DOUBLE_PENALTY = 0.85  # Leichter Abzug fuer Half/Double Transitions (0-1)

# === Logging & Debugging ===
LOG_LEVEL = "INFO"  # Standard-Level: DEBUG, INFO, WARNING, ERROR
LOG_TO_FILE = True  # Logdatei unter logs/hpg.log (mit Rotation)
LOG_TO_CONSOLE = True  # Konsolenausgabe auf stderr
