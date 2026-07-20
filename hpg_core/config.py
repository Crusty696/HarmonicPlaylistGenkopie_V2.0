"""
Configuration constants for audio analysis.
Centralizes all magic numbers and configurable parameters.
"""

# === Audio Processing Parameters ===
HOP_LENGTH = 1024  # Frame hop for feature extraction
METER = 4  # 4/4 time signature (beats per bar)
MAX_TRANSITION_OVERLAP_SECONDS = 64.0

# === Intro/Outro Detection (RMS-Fallback, research-basiert 2026-07-17) ===
# Suchfenster-Pruning nach Bittner et al. (ISMIR 2017, Spotify):
# Mix-In-Kandidaten liegen in den ersten 20%, Mix-Out in den letzten 25%
MIX_IN_SEARCH_WINDOW_PCT = 0.20
MIX_OUT_SEARCH_WINDOW_PCT = 0.75

# Aktivitaets-Schwelle nach Zehren et al. (arXiv 2007.08411 / CMJ 2022):
# Abschnitt gilt als "aktiv/tragfaehig", wenn die ueber ein 4-Takt-Fenster
# geglaettete RMS >= 0.4 x Track-Maximum liegt
RMS_THRESHOLD = 0.4

# === Phrase Detection ===
BARS_PER_PHRASE = 8  # Standard phrase length (8 bars)

# === Performance Optimization ===
# Default BPM for fallback when BPM detection fails
DEFAULT_BPM = 120.0

# Fallback-Energie fuer Sektionen ohne avg_energy-Feld (Skala 0-100)
DEFAULT_SECTION_ENERGY = 50.0

# Enhanced-Harmonic-Flow: Lookahead-Rekursion nur fuer die K besten
# Kandidaten (begrenzt O(n^3) auf O(n^2 * K) bei grossen Playlists)
LOOKAHEAD_TOP_K = 8

# === Loudness / Gain-Matching (2026-07-17, EBU R128) ===
# Referenz-Loudness fuer Gain-Angleichung: -18 LUFS = ReplayGain-2.0-Standard
# (Mixxx-kompatibel, genug Headroom fuer EDM; rekordbox-Zielwert unbekannt)
LUFS_REFERENCE = -18.0
# Anzeige-Schwelle: Differenzen >= 1 dB sind hoerbar (JND)
GAIN_DIFF_SHOW_DB = 1.0
# Warn-Schwelle: >= 3 dB gilt als korrekturbeduerftig
GAIN_DIFF_WARN_DB = 3.0

# Key-Confidence: unterhalb dieser Schwelle gilt die Tonart als unsicher
# (Schwellwerte heuristisch — offiziell publiziert ist keiner, siehe
# docs/plans/2026-07-17-key-confidence-lufs.md)
KEY_CONFIDENCE_UNCERTAIN = 0.5

# === DJ Brain Configuration ===
# DJ_BRAIN_ENABLED entfernt (Konsolidierung 2026-07-17): der RMS-Fallback
# delegiert jetzt selbst an calculate_genre_aware_mix_points — es gibt nur
# noch eine Mixpoint-Logik, der Master-Schalter schaltete nichts mehr.

# Genre Classification
GENRE_CONFIDENCE_THRESHOLD = (
    0.4  # Minimum Confidence fuer Genre-Akzeptanz (war 0.3 - zu niedrig)
)
# Drum & Bass: Mindest-BPM fuer Klassifikation (schuetzt gegen BPM-Halftime-Fehler)
# Tracks unter 155 BPM koennen nicht als DnB klassifiziert werden
DNB_MINIMUM_BPM = 155.0

# Halftime-Korrektur: Maximales Ergebnis nach Verdoppelung
# Wenn bpm*2 > BPM_HALFTIME_MAX_RESULT, wird NICHT verdoppelt
# (verhindert z.B. ~92 BPM -> 184 BPM -> falsche DnB-Klassifikation)
BPM_HALFTIME_MAX_RESULT = 185.0

# Genre-BPM-Bereiche liegen zentral in genre_classifier.GENRE_PROFILES —
# die frueheren *_BPM_RANGE-Konstanten hier waren ein ungelesenes Duplikat
# und wurden entfernt (Audit 2026-07-17)

# Genre Weight in Playlist-Kompatibilitaet
GENRE_WEIGHT_WITH_DJ_BRAIN = 0.2  # Wenn DJ Brain Genre-Daten vorhanden
GENRE_WEIGHT_WITHOUT_DJ_BRAIN = 0.1  # Fallback ohne DJ Brain Daten

# === Librosa Memory Protection (K2 Audit-Fix) ===
# Maximale Lade-Dauer in Sekunden — begrenzt RAM-Verbrauch bei langen Tracks.
# Rekordbox Fast-Path: BPM/Key kommt aus DB, daher reichen 120s fuer Energy/Genre.
# Volle Analyse: 600s (10 Min) als Sicherheitsnetz gegen riesige Dateien.
LIBROSA_FAST_PATH_DURATION = 360  # Sekunden (fuer Rekordbox-Pfad)
LIBROSA_MAX_DURATION = 600  # Sekunden (fuer volle Analyse, Safety-Net)
# Separates Endfenster verhindert, dass Outro/Mix-Out aus einem reinen
# Track-Anfang extrapoliert werden. Die Zeitachse markiert eventuelle Luecken.
LIBROSA_TAIL_DURATION = 180
# Maximale dekodierte Float32-Groesse fuer eine vollstaendige Stereo-LUFS-
# Messung. Groessere Dateien werden explizit als nicht gemessen markiert.
LUFS_MAX_DECODE_BYTES = 512 * 1024 * 1024

# === Parallel Analysis ===
PARALLEL_ANALYSIS_TIMEOUT = 60  # Sekunden pro Track (schuetzt gegen korrupte Dateien)
PARALLEL_MAX_WORKERS = None  # None = automatisch (cpu_count basiert), oder feste Zahl

# === Structure Analysis ===
SECTION_ENERGY_THRESHOLD = 0.3  # Novelty-Peak Threshold fuer Sektions-Erkennung (0.1-0.5)

# === BPM Half/Double Tolerance ===
BPM_HALF_DOUBLE_ENABLED = True  # 140 BPM ↔ 70 BPM als kompatibel erkennen
BPM_HALF_DOUBLE_PENALTY = 0.85  # Leichter Abzug fuer Half/Double Transitions (0-1)

# === Logging & Debugging ===
LOG_LEVEL = "INFO"  # Standard-Level: DEBUG, INFO, WARNING, ERROR (INFO fuer Produktion)

# === Security & Safety ===
# 500 MB: Lossless-AIFF/WAV ueberschreitet 100 MB schon ab ~10 Minuten
# (Beatport-AIFF 44.1k/16bit ~ 10.6 MB/min); Dauer-Limit + LIBROSA_MAX_DURATION
# schuetzen weiterhin vor Ressourcen-Erschoepfung
SECURITY_MAX_FILE_SIZE = 1024 * 1024 * 500
SECURITY_MAX_TRACK_DURATION = 7200  # 2 Stunden max Track-Länge (sicherheitsbedingt)
SECURITY_MAX_PLAYLIST_SIZE = 1000  # 1000 Tracks max pro Playlist

# === AI Intelligence Layer ===
AI_PROVIDER = "Ollama"  # "Ollama" or "LM Studio"
AI_API_URL_OLLAMA = "http://localhost:11434/v1/chat/completions"
AI_API_URL_LMSTUDIO = "http://localhost:1234/v1/chat/completions" # Default Ollama
# "gemma4" existiert nicht als Ollama-Modell — gemeint ist Gemma 3 12B
AI_MODEL = "gemma3:12b" # Oder mistral, etc.
AI_TIMEOUT = 120.0  # Hoch genug fuer Cold-Start (Modell-Load in VRAM beim ersten Call); danach schnell
# KI-Mixpunkte bleiben bis zu einer unabhaengigen Cue-Validierung advisory.
AI_AUTO_APPLY_MIXPOINTS = False
AI_SYSTEM_PROMPT = (
    "You are a professional electronic music curator and DJ. Analyze tracks with focus on "
    "sub-genres (like Forest Psy, Peak-time Techno, Deep Progressive), atmosphere, and precise mixing points. "
    "Mixing Guidelines:\n"
    "1. For Techno and Psy-Trance: The mix-in time should NOT be at the very start (0.0s). It must be placed where the first loud kick and bassline starts (typically after a 32, 48, or 64-bar intro phase, between 30s and 90s, aligned with the first energetic section block).\n"
    "2. The mix-out time must be placed where the outro starts or the track starts thinning out (the last or penultimate section block, avoiding the very end of the track unless it is a short transition).\n"
    "3. DJ Transition Recommendation: In your description, recommend using 'Pro EQ Swap' for Techno, Psytrance, Tech House, and Minimal. Explain how to manage the EQ bands (e.g. swap bass on downbeat, attenuate mids to prevent clashing leads, fade highs smoothly).\n"
    "Respond ONLY with a JSON object using EXACTLY these keys: "
    '"sub_genre" (string, precise sub-genre), '
    '"moods" (array of 2-3 short mood tag strings, e.g. ["mystic","industrial"]), '
    '"description" (string, one-sentence mixing tip explaining why the mix-in/mix-out points were chosen and how to execute the transition with EQ knobs, mentioning Pro EQ Swap if applicable), '
    '"mix_in_time" (float, ideal mix-in point in seconds), '
    '"mix_out_time" (float, ideal mix-out point in seconds).\n'
    'Example for Psy-Trance: {"sub_genre":"Progressive Psytrance","moods":["driving","psychedelic"],"description":"Execute a Pro EQ Swap at the second section drop: swap bass cleanly, drop mids of track A to prevent vocal clashes.","mix_in_time":55.7,"mix_out_time":328.7}'
)
AI_MODELS_AVAILABLE = ["gemma3:12b", "gemma2:9b", "gemma:7b", "llama3:8b", "llama3.1:8b", "qwen2.5:7b", "mistral:7b", "phi3:medium", "llama3", "mistral", "gemma"]
