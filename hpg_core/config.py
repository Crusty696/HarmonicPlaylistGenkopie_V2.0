"""
Configuration constants for audio analysis.
Centralizes all magic numbers and configurable parameters.
"""

# === Audio Processing Parameters ===
HOP_LENGTH = 1024  # Frame hop for feature extraction
METER = 4  # 4/4 time signature (beats per bar)

# === Intro/Outro Detection Thresholds ===
INTRO_MAX_PERCENTAGE = 0.25  # Intro can't be longer than 25%
OUTRO_MIN_PERCENTAGE = 0.75  # Outro can't start before 75%

RMS_THRESHOLD = 0.4  # Segment RMS must be < 40% of average (intro/outro detection)

# === Phrase Detection ===
BARS_PER_PHRASE = 8  # Standard phrase length (8 bars)

# === Performance Optimization ===
# Default BPM for fallback when BPM detection fails
DEFAULT_BPM = 120.0

# === DJ Brain Configuration ===
DJ_BRAIN_ENABLED = True  # Master-Schalter: genre-aware Mix-Punkte (dj_brain) vs. generischer RMS-Fallback

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
BPM_HALFTIME_MAX_RESULT = 185.0

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
LIBROSA_FAST_PATH_DURATION = 360  # Sekunden (fuer Rekordbox-Pfad)
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
LOG_LEVEL = "INFO"  # Standard-Level: DEBUG, INFO, WARNING, ERROR (INFO fuer Produktion)
LOG_TO_FILE = True  # Logdatei unter logs/hpg.log (mit Rotation)
LOG_TO_CONSOLE = True  # Konsolenausgabe auf stderr

# === Security & Safety ===
# 500 MB: Lossless-AIFF/WAV ueberschreitet 100 MB schon ab ~10 Minuten
# (Beatport-AIFF 44.1k/16bit ~ 10.6 MB/min); Dauer-Limit + LIBROSA_MAX_DURATION
# schuetzen weiterhin vor Ressourcen-Erschoepfung
SECURITY_MAX_FILE_SIZE = 1024 * 1024 * 500
SECURITY_MAX_TRACK_DURATION = 7200  # 2 Stunden max Track-Länge (sicherheitsbedingt)
SECURITY_MAX_PLAYLIST_SIZE = 1000  # 1000 Tracks max pro Playlist

# === AI Intelligence Layer ===
AI_ENABLED = True
AI_PROVIDER = "Ollama"  # "Ollama" or "LM Studio"
AI_API_URL_OLLAMA = "http://localhost:11434/v1/chat/completions"
AI_API_URL_LMSTUDIO = "http://localhost:1234/v1/chat/completions" # Default Ollama
AI_MODEL = "gemma4:12b" # Oder mistral, etc.
AI_TIMEOUT = 120.0  # Hoch genug fuer Cold-Start (Modell-Load in VRAM beim ersten Call); danach schnell
AI_SYSTEM_PROMPT = (
    "You are a professional electronic music curator and DJ. Analyze tracks with focus on "
    "sub-genres (like Forest Psy, Peak-time Techno, Deep Progressive), atmosphere, and precise mixing points. "
    "Based on the track information and the detected audio sections, suggest the ideal mix-in time "
    "and mix-out time (in seconds) that allow for a smooth transition. "
    "Respond ONLY with a JSON object using EXACTLY these keys: "
    '"sub_genre" (string, precise sub-genre), '
    '"moods" (array of 2-3 short mood tag strings, e.g. ["mystic","industrial"]), '
    '"description" (string, one-sentence mixing tip explaining why the mix-in and mix-out points were chosen), '
    '"mix_in_time" (float, ideal mix-in point in seconds), '
    '"mix_out_time" (float, ideal mix-out point in seconds). '
    'Example: {"sub_genre":"Peak-time Techno","moods":["driving","dark"],"description":"Blend the intro after the first drop fades out.","mix_in_time":32.5,"mix_out_time":240.0}'
)
AI_MODELS_AVAILABLE = ["gemma4:12b", "gemma2:9b", "gemma:7b", "llama3:8b", "llama3.1:8b", "qwen2.5:7b", "mistral:7b", "phi3:medium", "llama3", "mistral", "gemma"]
