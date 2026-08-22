"""
Configuration constants for audio analysis.
Centralizes all magic numbers and configurable parameters.
"""

# === Audio Processing Parameters ===
HOP_LENGTH = 1024  # Frame hop for feature extraction
METER = 4  # 4/4 time signature (beats per bar)
MAX_TRANSITION_OVERLAP_SECONDS = 64.0
# Kuerzeste Blende in Takten. Unter diese Laenge wird nie gekuerzt — lieber
# eine Blende, die ein Stueck ins Outro laeuft, als ein Uebergang, der zum
# harten Schnitt zusammenfaellt. Gleiche Untergrenze wie in dj_brain
# (`_dynamic_transition_bars`, `calculate_paired_mix_points`).
MIN_TRANSITION_BARS = 8

# === Intro/Outro Detection (RMS-Fallback, research-basiert 2026-07-17) ===
# Suchfenster-Pruning nach Bittner et al. (ISMIR 2017, Spotify):
# Mix-In-Kandidaten liegen in den ersten 20%, Mix-Out in den letzten 25%
MIX_IN_SEARCH_WINDOW_PCT = 0.20
MIX_OUT_SEARCH_WINDOW_PCT = 0.75

# Aktivitaets-Schwelle nach Zehren et al. (arXiv 2007.08411 / CMJ 2022):
# Abschnitt gilt als "aktiv/tragfaehig", wenn die ueber ein 4-Takt-Fenster
# geglaettete RMS >= 0.4 x Track-Maximum liegt
RMS_THRESHOLD = 0.4
MIX_POINT_UNSET = -1.0  # Expliziter Sentinel; 0.0 ist ein gueltiger Zeitpunkt

# === Phrase Detection ===
BARS_PER_PHRASE = 8  # Standard phrase length (8 bars)

# AUDIT-FEATURE A1 (2026-07-26): Mindest-Konfidenz des Bar-Votings, damit
# first_phrase als Phrasen-Anker verwendet wird (darunter: first_downbeat).
# Konservativ gewaehlt — ein falscher Phrasen-Anker waere schlimmer als keiner.
PHRASE_CONFIDENCE_MIN = 0.25

# Anchor-Vertrag: first_downbeat ist der erste Takt-1-Anker (in Sekunden), den
# der Rekordbox-Importer liefert. phrase_anchor ist der nachgelagerte
# Phrasen-Anker und darf bei belastbarer Phrasen-Konfidenz davon abweichen;
# andernfalls faellt er auf first_downbeat zurueck.

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

# === Mixpunkt-Kandidaten (Spec 2026-08-21, Abschnitt 1) ===
# Anzahl Kandidaten je Seite (Mix-In / Mix-Out) nach Dedupe und Kappung.
KANDIDATEN_MIN_JE_SEITE = 3
KANDIDATEN_MAX_JE_SEITE = 8
# Messfenster fuer lokale Werte: +-1 Phrase um den Kandidaten.
KANDIDATEN_FENSTER_PHRASEN = 1
# Audio fuer lokale Merkmale (wie alle uebrigen librosa-Merkmale, mono).
# LUFS wird davon getrennt in nativer Samplerate/Kanalzahl gemessen.
KANDIDATEN_AUDIO_SR = 22050
# Cues naeher als 2 s gelten als Duplikat (bisher inline in analysis.py).
CUE_DEDUPE_SEC = 2.0
# kick_aktiv: Bass-RMS (<=160 Hz) ueber dieser Schwelle UND On-Beat-Anteil
# des lokalen Bassmusters ueber KICK_AKTIV_ONBEAT_MIN. STARTWERTE, nicht
# gemessen — der Hoertest (Teil 3) prueft sie.
KICK_AKTIV_MIN_DBFS = -35.0
KICK_AKTIV_ONBEAT_MIN = 0.40
# energy_trend: |Energie nach - Energie vor| >= Schwelle → rising/falling.
ENERGIE_TREND_SCHWELLE = 10
# Schema "energie_neuheit": Sektionsgrenze zaehlt, wenn der Energiesprung
# zwischen den Nachbarsektionen mindestens so gross ist (0-100-Skala).
ENERGIE_NEUHEIT_MIN = 20

# === Paarung und Bewertung von Kandidaten (Spec 2026-08-21, Abschnitt 2) ===
# Harte Gates auf Paar-Ebene (Spec-Werte).
PAAR_BPM_MAX = 2.0                 # |BPM_A - BPM_B| effektiv (Half/Double erkannt)
# Pitch-Bedarf diff / BPM_A. Spec-Gate; unter PAAR_BPM_MAX ab 50 BPM rechnerisch
# nie aktiv (2/50 = 4 %) — bleibt als eigenstaendiges Gate, wie die Spec es nennt.
PAAR_PITCH_MAX = 0.04
PAAR_HALF_DOUBLE_MAX_BARS = 16     # kurzer Cut bei Half/Double
PAAR_MAX_KOMBINATIONEN = 6         # Zeitpunkt-Kombinationen je Paar (x 2 Blenden)
# Teilwerte. Spec-Werte: PAAR_BPM_SKALA, LUFS_DELTA_MAX_DB, PERCUSSIVE_HOCH/NIEDRIG.
# BASS_RMS/SYNCOPATION/MIDS_HIGHS sind an den 231 Tracks gemessene p90-Spannen
# (Normierung, keine Gewichte). Alle uebrigen sind STARTWERTE, nicht gemessen —
# der Hoertest (Teil 3) ersetzt sie.
PAAR_BPM_SKALA = 1.0               # exp(-diff / Skala), Spec-Wert
# Lautheit: 0 dB -> 1.0, >= 3 dB -> 0 (Spec-Wert). Dieselbe 3-dB-Toleranz wie
# GAIN_DIFF_WARN_DB oben (Gain-Hinweis in dj_brain) — bei Aenderung beide pruefen.
LUFS_DELTA_MAX_DB = 3.0
# |delta bass_rms_dbfs| auf [0,1]. Gemessen 2026-08-22 an 231 Tracks / 3664
# Kandidaten: paarweise Differenz (BPM <= 2) Median 1.9 dB, p90 7.2 dB -> p90.
BASS_RMS_DELTA_MAX_DB = 7.0
# |delta syncopation_lokal| auf [0,1]. Gemessen 2026-08-22: paarweise Differenz
# Median 0.09, p90 0.28 -> p90.
SYNCOPATION_DELTA_MAX = 0.3
PERCUSSIVE_HOCH = 0.7              # beide darueber -> Abzug (Spec-Schwelle)
PERCUSSIVE_NIEDRIG = 0.3           # beide darunter -> lange Blende erlaubt (Spec)
PERCUSSIVE_ABZUG = 0.10            # STARTWERT
KICK_KONFLIKT_ABZUG = 0.15         # STARTWERT: beide kick_aktiv -> Bass-Swap-Pflicht, Abzug
# Mittel aus |delta avg_mids_lokal| und |delta avg_highs_lokal| in Prozentpunkten
# (analyze_frequency_bands). Gemessen 2026-08-22: Mids-Differenz Median 2.3 /
# p90 8.1, Hoehen Median 0.8 / p90 2.0 -> Mittel p90 ~ 5.
MIDS_HIGHS_DELTA_MAX = 5.0
PSSI_MOOD_ABZUG = 0.10             # STARTWERT: PSSI-mood beidseitig vorhanden und verschieden
ENERGIE_TREND_WIDERSPRUCH = 0.8    # STARTWERT: energy_trend von B widerspricht der Richtung
STRUKTUR_LABEL_BONUS = 0.10        # STARTWERT: Outro/Down -> Chorus/Drop

# === DJ Brain Configuration ===
# DJ_BRAIN_ENABLED entfernt (Konsolidierung 2026-07-17): der RMS-Fallback
# delegiert jetzt selbst an calculate_genre_aware_mix_points — es gibt nur
# noch eine Mixpoint-Logik, der Master-Schalter schaltete nichts mehr.

# Genre Classification
GENRE_CONFIDENCE_THRESHOLD = (
    0.4  # Minimum Confidence fuer Genre-Akzeptanz (war 0.3 - zu niedrig)
)
# Drum & Bass: BPM-Schwelle fuer den DnB-Score-Malus (kanonischer DnB-Bereich
# 160-180, genres.py GENRE_PROFILES). Tracks unter dieser BPM werden NICHT hart
# ausgeschlossen — ihr DnB-Score wird nur gedaempft (DNB_LOW_BPM_PENALTY), damit
# starke DnB-Merkmale (Breakbeat/Sub-Bass/Rhythmus) weiter mitzaehlen und nur
# BPM-Halftime-Fehler abgewehrt werden. Genre-Einteilung bleibt multi-feature.
DNB_MINIMUM_BPM = 160.0
# Daempfungsfaktor fuer den DnB-Score bei BPM unter DNB_MINIMUM_BPM
# (0.0 = harter Ausschluss, 1.0 = kein Effekt). 0.5 = halbieren.
DNB_LOW_BPM_PENALTY = 0.5

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
# === Parallel Analysis ===
PARALLEL_ANALYSIS_TIMEOUT = 60  # Sekunden pro Track (schuetzt gegen korrupte Dateien)
PARALLEL_MAX_WORKERS = None  # None = automatisch (cpu_count basiert), oder feste Zahl
# Native Audio-Decoder und Librosa benoetigen pro Worker deutlich RAM. Auf
# Windows fuehren mehr als vier parallele Decoder bei grossen AIFF/WAV-Dateien
# zu C-Level-Abstuerzen des ProcessPools; explizite Nutzerlimits bleiben moeglich.
PARALLEL_AUTO_MAX_WORKERS = 4
# AUDIT-FIX N-04 (2026-07-26): Obergrenze fuer die Haenger-Deadline im
# Parallel-Analyzer. Die Deadline ist eine INAKTIVITAETS-Deadline pro
# Wartezyklus (TIMEOUT * worker_count + 30) und wird hier auf ~15 Minuten
# gedeckelt — sie waechst NICHT mehr mit der Batch-Groesse.
PARALLEL_HANG_DEADLINE_MAX = 900  # Sekunden (15 Minuten)

# === Structure Analysis ===
SECTION_ENERGY_THRESHOLD = 0.3  # Novelty-Peak Threshold fuer Sektions-Erkennung (0.1-0.5)

# === BPM Half/Double Tolerance ===
BPM_HALF_DOUBLE_ENABLED = True  # 140 BPM ↔ 70 BPM als kompatibel erkennen
BPM_HALF_DOUBLE_PENALTY = 0.85  # Leichter Abzug fuer Half/Double Transitions (0-1)

# === Erweitertes Scoring: Groove/Bass/Timbre/Mood ===
# Groove-/Bass-/Timbre-/Mood-Scoring (Spec 2026-08-19).
# False = bit-identisches Verhalten zum Stand vor der Erweiterung.
# True seit 2026-08-21 mit Startgewichten aus genres.py (groove 0.30) —
# Begruendung und Messung dort. Bis dahin stand der Schalter aus, weil die
# Kalibrierung aus fremden DJ-Mixen gescheitert war (Gewichtsbudget 0.012).
# Im Acht-Faktoren-Pfad kommt das Genre-Gewicht aus der Toleranztabelle;
# GENRE_WEIGHT_WITH/_WITHOUT_DJ_BRAIN wirken dort nur noch als VERHAELTNIS
# (Halbierung bei unbekanntem Genre, siehe playlist.py
# calculate_enhanced_compatibility), nicht mehr als Absolutwert.
TRANSITION_FEATURES_ENABLED = True

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
# AUDIT-FIX 2026-08-14: Provider und Modell waren nicht lauffaehig.
# AI_MODEL stand auf "gemma4:12b" — dieses Modell ist weder lokal installiert,
# noch existiert die Groesse 12B in der Gemma-4-Familie (E2B/E4B/26B-A4B/31B).
# Wer die KI-Funktion einschaltete, lief ins Leere.
# Beide Werte sind nur Vorauswahl: der ai_launcher erkennt beide Provider und
# fuellt das Modell-Dropdown mit den tatsaechlich installierten Modellen.
AI_PROVIDER = "LM Studio"  # "Ollama" or "LM Studio"
AI_API_URL_OLLAMA = "http://localhost:11434/v1/chat/completions"
AI_API_URL_LMSTUDIO = "http://localhost:1234/v1/chat/completions" # Default LM Studio
# Standardmodell mit vom lokalen Ollama-Server gemeldeter Audio-Faehigkeit.
# Gemessen am 2026-08-14 gegen den echten Vertrag dieser App (System-Prompt,
# response_format=json_schema strict, Validierung inkl. Provenienz), 8 reale
# Tracks je Modell auf einer RX 7800 XT (LM Studio, Vulkan-Runtime):
#
#   granite-4.0-h-tiny        8/8 gueltig   2.7 s/Track   Laden 20 s   4.2 GB
#   llama-3.2-8x3b-dark-...   8/8 gueltig   2.8 s/Track   Laden 40 s  10.7 GB
#   ministral-3-14b-reason.   8/8 gueltig   6.7 s/Track   Laden 51 s  12.0 GB
#   qwen3.5-9b                0/8           leere Antwort bei JEDEM Token-Budget
#   ornith-1.0-9b             0/8           leere Antwort
#
# granite-4.0-h-tiny gewinnt in allen Dimensionen: hoechste Trefferquote,
# schnellste Antwort, kleinster Speicherbedarf. Bei 500 Tracks sind das rund
# 22 Minuten statt 11 Stunden mit einem 27B-Reasoning-Modell.
AI_MODEL = "granite-4.0-h-tiny"
# Obergrenze der KI-Antwortlaenge. Pflicht bei erzwungenem JSON-Schema:
# ohne Limit kann ein Modell in einer ungeschlossenen Struktur haengen
# bleiben und laeuft in AI_TIMEOUT statt in einen sauberen Fehler.
AI_MAX_TOKENS = 400
AI_TIMEOUT = 120.0  # Hoch genug fuer Cold-Start (Modell-Load in VRAM beim ersten Call); danach schnell
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
