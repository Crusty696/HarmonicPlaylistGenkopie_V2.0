from __future__ import annotations  # Python 3.9 compatibility for | type hints

import numpy as np
import librosa
import mutagen
import os
import re
from math import floor
from .models import Track, CAMELOT_MAP
from .config import (
    HOP_LENGTH, METER, INTRO_PERCENTAGE, OUTRO_PERCENTAGE,
    INTRO_MAX_PERCENTAGE, OUTRO_MIN_PERCENTAGE, RMS_THRESHOLD, DEFAULT_BPM
)

# Reverse mapping: Camelot code → (Note, Mode)
REVERSE_CAMELOT_MAP = {v: k for k, v in CAMELOT_MAP.items()}
from .caching import generate_cache_key, get_cached_track, cache_track
from .rekordbox_importer import get_rekordbox_importer
from .genre_classifier import classify_genre
from .structure_analyzer import analyze_structure
from .dj_brain import calculate_genre_aware_mix_points

# Krumhansl-Schmuckler key profiles (simplified)
# C, C#, D, D#, E, F, F#, G, G#, A, A#, B
MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]

NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

def get_key(chroma_vector):
    """Determines the key from a chroma vector by correlating with major/minor profiles."""
    major_correlations = []
    minor_correlations = []

    for i in range(12):
        # Correlate with major and minor profiles, rolling the chroma vector
        major_corr = np.corrcoef(np.roll(chroma_vector, -i), MAJOR_PROFILE)[0, 1]
        minor_corr = np.corrcoef(np.roll(chroma_vector, -i), MINOR_PROFILE)[0, 1]
        major_correlations.append(major_corr)
        minor_correlations.append(minor_corr)

    # Find the best match
    max_major_corr = max(major_correlations)
    max_minor_corr = max(minor_correlations)

    if max_major_corr > max_minor_corr:
        key_index = np.argmax(major_correlations)
        key_mode = "Major"
    else:
        key_index = np.argmax(minor_correlations)
        key_mode = "Minor"

    key_note = NOTES[key_index]
    return key_note, key_mode

def calculate_energy(y):
    """Calculates the overall energy of a track and scales it to 0-100."""
    if y is None or len(y) == 0:
        return 0

    y = np.asarray(y)
    if y.size == 0:
        return 0

    # Replace NaN/inf with finite values and clamp extremes to avoid overflow
    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)
    y = np.clip(y, -1.0, 1.0)

    rms_energy = float(np.sqrt(np.mean(y ** 2))) if y.size else 0.0
    if not np.isfinite(rms_energy):
        rms_energy = 0.0

    energy_scaled = float(np.interp(rms_energy, [0.0, 0.4], [0.0, 100.0]))
    return int(min(max(energy_scaled, 0.0), 100.0))

def calculate_bass_intensity(y, sr):
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

    total_energy = float(np.sum(stft ** 2))
    bass_energy = float(np.sum(stft[bass_indices, :] ** 2)) if bass_indices.size else 0.0

    if total_energy == 0:
        return 0

    bass_ratio = bass_energy / total_energy
    bass_intensity = float(np.interp(bass_ratio, [0.0, 0.5], [0.0, 100.0]))
    return int(min(max(bass_intensity, 0.0), 100.0))

def calculate_brightness(y, sr):
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
        centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        mean_centroid = float(np.mean(centroid))

        if not np.isfinite(mean_centroid):
            return 0

        # Normalisierung: typischer Bereich 500-8000 Hz → 0-100
        # Elektronische Musik liegt meist zwischen 1000-5000 Hz
        brightness = float(np.interp(mean_centroid, [500.0, 8000.0], [0.0, 100.0]))
        return int(min(max(brightness, 0.0), 100.0))
    except Exception as e:
        print(f"[BRIGHTNESS] Error: {e}")
        return 0


def detect_vocal_instrumental(y, sr):
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
        flatness = librosa.feature.spectral_flatness(y=y)[0]
        mean_flatness = float(np.mean(flatness))

        # 2. MFCC-Varianz (höher = mehr spektrale Variation = eher Vocals)
        mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        # Varianz über die Zeit für MFCCs 2-13 (MFCC 1 ist Lautstärke)
        mfcc_variance = float(np.mean(np.var(mfccs[1:], axis=1)))

        # 3. Spectral Contrast (grössere Unterschiede = eher Vocals)
        contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
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
        print(f"[VOCAL] Error: {e}")
        return "unknown"


def calculate_danceability(y, sr, bpm=None):
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
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
        if beats.size > 2:
            beat_times = librosa.frames_to_time(beats, sr=sr)
            intervals = np.diff(beat_times)
            if intervals.size > 0 and np.mean(intervals) > 0:
                beat_regularity = 1.0 - min(float(np.std(intervals) / np.mean(intervals)), 1.0)
            else:
                beat_regularity = 0.0
        else:
            beat_regularity = 0.0

        # 2. Onset-Regelmässigkeit (0-1)
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
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
                        if ac_norm[i] > ac_norm[i-1] and ac_norm[i] > ac_norm[i+1]:
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
            stft = np.abs(librosa.stft(y, n_fft=2048))
            freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
            bass_bins = np.where((freqs >= 20) & (freqs <= 200))[0]
            if bass_bins.size > 0:
                bass_energy_over_time = np.mean(stft[bass_bins, :], axis=0)
                if bass_energy_over_time.size > 1 and np.std(bass_energy_over_time) > 0:
                    # Periodizität des Bass-Signals
                    bass_ac = librosa.autocorrelate(bass_energy_over_time,
                                                     max_size=bass_energy_over_time.size // 2)
                    if bass_ac.size > 1 and bass_ac[0] > 0:
                        bass_ac_norm = bass_ac / bass_ac[0]
                        bass_peaks = []
                        for i in range(1, min(len(bass_ac_norm), 200)):
                            if i < len(bass_ac_norm) - 1:
                                if bass_ac_norm[i] > bass_ac_norm[i-1] and bass_ac_norm[i] > bass_ac_norm[i+1]:
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
            beat_regularity * 0.40 +
            onset_regularity * 0.30 +
            bass_periodicity * 0.20
        )
        if bpm_bonus > 0:
            raw_score = base_score + (bpm_bonus / 0.15) * 0.10
        else:
            raw_score = base_score

        danceability = raw_score * 100.0
        return int(min(max(danceability, 0.0), 100.0))

    except Exception as e:
        print(f"[DANCEABILITY] Error: {e}")
        return 0


def calculate_mfcc_fingerprint(y, sr, n_mfcc=13):
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
        mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=n_mfcc)
        # Mittelwert über die Zeit → kompakter Vektor
        mean_mfccs = np.mean(mfccs, axis=1)
        return [round(float(v), 4) for v in mean_mfccs]
    except Exception as e:
        print(f"[MFCC] Error: {e}")
        return []


def parse_filename_for_metadata(file_path):
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
    match = re.match(r'^(?:\d+[\s.-]*)?([^-]+?)\s*-\s*(.+)$', name_without_ext)
    if match:
        artist = match.group(1).strip()
        title = match.group(2).strip()

        # Validate: artist and title should have reasonable length
        if 1 <= len(artist) <= 100 and 1 <= len(title) <= 200:
            return artist, title

    # Pattern 2: "Artist_Track" (underscore separator)
    match = re.match(r'^(?:\d+[\s._-]*)?([^_]+?)_(.+)$', name_without_ext)
    if match:
        artist = match.group(1).strip()
        title = match.group(2).strip()
        if 1 <= len(artist) <= 100 and 1 <= len(title) <= 200:
            return artist, title

    # If no pattern matched, return None
    return None, None

def extract_metadata(file_path):
    """
    Extracts Artist, Title, and Genre from ID3 tags or filename.

    Tries ID3 tags first, then falls back to filename parsing if tags are missing.

    Returns:
        tuple: (artist, title, genre)
    """
    artist = None
    title = None
    genre = None

    # Try to extract from ID3 tags first
    try:
        audio = mutagen.File(file_path, easy=True)
        if audio:
            artist = audio.get('artist', [None])[0]
            title = audio.get('title', [None])[0]
            genre = audio.get('genre', [None])[0]
    except Exception as e:
        print(f"Warning: Error reading ID3 tags for {file_path}: {e}")

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

def analyze_structure_and_mix_points(y, sr, duration, energy_level, bpm):
    """
    Analyzes the audio structure to find intro/outro and calculates optimal mix points.
    
    Refactored to remove ruptures dependency. Uses RMS energy thresholding for
    faster and more robust intro/outro detection.
    
    Logic:
    - Intro ends when energy consistently exceeds 40% of average energy.
    - Outro starts when energy consistently drops below 40% of average energy.
    
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
        return round(mix_in_point, 2), round(mix_out_point, 2), mix_in_bars, mix_out_bars

    try:
        # Calculate RMS energy profile using configured hop length
        rms = librosa.feature.rms(y=y, hop_length=HOP_LENGTH)[0]
        times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=HOP_LENGTH)

        # Determine energy threshold using configured RMS threshold
        avg_energy = np.mean(rms)
        threshold = avg_energy * RMS_THRESHOLD
        
        # --- Intro Detection ---
        # Find first point where energy stays above threshold for a sustained period
        # Smoothing window ~2 seconds
        window_size = int(2.0 * sr / HOP_LENGTH)
        
        # Smooth the RMS curve
        rms_smooth = np.convolve(rms, np.ones(window_size)/window_size, mode='same')
        
        # Find start of main body (Intro End)
        main_body_indices = np.where(rms_smooth > threshold)[0]
        
        if main_body_indices.size > 0:
            # Intro ends at the first index where energy is significant
            intro_end_idx = main_body_indices[0]
            intro_end_time = times[intro_end_idx]
            
            # Outro starts at the last index where energy is significant
            outro_start_idx = main_body_indices[-1]
            outro_start_time = times[outro_start_idx]
        else:
            # Fallback if track is very quiet
            intro_end_time = duration * INTRO_PERCENTAGE
            outro_start_time = duration * OUTRO_PERCENTAGE

        # Sanity checks using configured thresholds
        if intro_end_time > duration * INTRO_MAX_PERCENTAGE:
            intro_end_time = duration * INTRO_PERCENTAGE  # Fallback if intro detected as too long

        if outro_start_time < duration * OUTRO_MIN_PERCENTAGE:
            outro_start_time = duration * OUTRO_PERCENTAGE  # Fallback if outro detected as too early
            
        if intro_end_time >= outro_start_time:
            intro_end_time = duration * INTRO_PERCENTAGE
            outro_start_time = duration * OUTRO_PERCENTAGE
             
        # --- Mix Point Calculation ---
        # Optimized for DJ mixing:
        # Mix-in: Usually at the end of the intro, aligned to an 8-bar phrase.
        # Mix-out: Usually at the start of the outro, aligned to an 8-bar phrase.

        seconds_per_beat = 60.0 / bpm
        seconds_per_bar = seconds_per_beat * METER
        seconds_per_phrase = seconds_per_bar * 8  # Standard 8-bar phrase

        # 1. Align Intro End to nearest phrase boundary
        # DJs rarely mix at random times; they mix at 8, 16, or 32 bar marks.
        intro_phrase_count = round(intro_end_time / seconds_per_phrase)
        # Ensure we have at least some intro, but not too much
        if intro_phrase_count < 1: intro_phrase_count = 1
        mix_in_point = intro_phrase_count * seconds_per_phrase
        
        # 2. Align Outro Start to phrase boundary
        # We want to mix out BEFORE the energy drops completely.
        # Typically 16 or 32 bars before the very end of the track.
        total_phrases = duration / seconds_per_phrase
        outro_phrase_index = floor(outro_start_time / seconds_per_phrase)
        
        # If the detected outro is too late, pull it back to a phrase boundary
        if outro_phrase_index >= floor(total_phrases) - 1:
            outro_phrase_index = max(1, floor(total_phrases) - 4) # 32 bars before end as fallback
            
        mix_out_point = outro_phrase_index * seconds_per_phrase
        
        # 3. Refinement: Ensure mix-in is after the first beat and mix-out is before the last
        # Also ensure there's enough space between them
        if mix_in_point >= mix_out_point - (seconds_per_phrase * 2):
            # If track is short, use 15% / 85% marks but still align to bars
            mix_in_point = round((duration * 0.15) / seconds_per_bar) * seconds_per_bar
            mix_out_point = round((duration * 0.85) / seconds_per_bar) * seconds_per_bar

        # Ensure points are within bounds
        mix_in_point = max(seconds_per_bar, min(mix_in_point, duration * 0.4))
        mix_out_point = min(duration - seconds_per_bar, max(mix_out_point, duration * 0.6))

        # Calculate bars
        mix_in_bars = int(round(mix_in_point / seconds_per_bar))
        mix_out_bars = int(round(mix_out_point / seconds_per_bar))

        return round(float(mix_in_point), 2), round(float(mix_out_point), 2), mix_in_bars, mix_out_bars

    except Exception as e:
        print(f"Error in analyze_structure_and_mix_points: {e}")
        # Safe fallback
        safe_in = min(max(duration * 0.2, 0.0), max(duration - 1.0, 0.0))
        safe_out = max(duration * 0.8, safe_in + 1.0)
        safe_out = min(safe_out, duration)
        safe_in = min(safe_in, max(safe_out - 1.0, 0.0))

        # Calculate bars for fallback using METER constant
        seconds_per_bar = (60.0 / bpm) * METER if bpm > 0 else (60.0 / DEFAULT_BPM) * METER
        safe_in_bars = int(safe_in / seconds_per_bar)
        safe_out_bars = int(safe_out / seconds_per_bar)

        return round(safe_in, 2), round(safe_out, 2), safe_in_bars, safe_out_bars


def analyze_track(file_path: str) -> Track | None:
    """Analyzes a single audio file for all v3.0 metadata, using a cache."""
    if not file_path:
        return None

    if isinstance(file_path, os.PathLike):
        file_path = os.fspath(file_path)

    if not isinstance(file_path, str) or not file_path:
        return None

    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}")
        return None

    cache_key = generate_cache_key(file_path)
    cached_track = get_cached_track(cache_key, file_path=file_path)

    if cached_track:
        print(f"Cache hit for: {os.path.basename(file_path)}")
        return cached_track

    print(f"Analyzing: {os.path.basename(file_path)}")

    # Try to get analysis data from Rekordbox first (MUCH faster!)
    rekordbox_importer = get_rekordbox_importer()
    rekordbox_data = rekordbox_importer.get_track_data(file_path)

    if rekordbox_data and rekordbox_data.bpm:
        # Rekordbox data available - use it!
        print(f"  [RB] Using Rekordbox data (BPM: {rekordbox_data.bpm}, Key: {rekordbox_data.camelot_code})")

        # Still extract ID3 tags (Rekordbox might have different metadata)
        artist_id3, title_id3, genre_id3 = extract_metadata(file_path)

        # Prefer Rekordbox metadata, fallback to ID3
        artist = rekordbox_data.artist or artist_id3
        title = rekordbox_data.title or title_id3
        genre = rekordbox_data.genre or genre_id3

        # For duration and some missing data, we still need librosa (quick load only)
        try:
            y, sr = librosa.load(file_path)
            duration = rekordbox_data.duration or librosa.get_duration(y=y, sr=sr)

            # Calculate energy and bass (not in Rekordbox)
            energy = calculate_energy(y)
            bass_intensity = calculate_bass_intensity(y, sr)

            # DJ Brain: Genre-Klassifikation
            genre_result = classify_genre(y, sr, rekordbox_data.bpm, bass_intensity, genre)
            print(f"  [GENRE] {genre_result.genre} (confidence: {genre_result.confidence:.2f}, source: {genre_result.source})")

            # DJ Brain: Struktur-Analyse
            structure = analyze_structure(y, sr, rekordbox_data.bpm, genre_result.genre)
            section_dicts = [s.to_dict() for s in structure.sections]
            section_labels = [s.label for s in structure.sections]
            print(f"  [STRUCTURE] {len(structure.sections)} sections: {section_labels} (phrase: {structure.phrase_unit} bars)")

            # DJ Brain: Genre-spezifische Mix-Punkte (oder Fallback auf generische Analyse)
            if genre_result.genre != "Unknown" and section_dicts:
                mix_in_point, mix_out_point, mix_in_bars, mix_out_bars = calculate_genre_aware_mix_points(
                    section_dicts, rekordbox_data.bpm, duration, genre_result.genre
                )
                print(f"  [DJ BRAIN] Mix points: in={mix_in_bars} bars, out={mix_out_bars} bars ({genre_result.genre})")
            else:
                mix_in_point, mix_out_point, mix_in_bars, mix_out_bars = analyze_structure_and_mix_points(
                    y, sr, duration, energy, rekordbox_data.bpm
                )

            # Override mix points if Rekordbox has cue points
            if rekordbox_data.cue_points:
                for cue in rekordbox_data.cue_points:
                    if cue['name'] and cue['position']:
                        if 'IN' in cue['name'].upper() or 'START' in cue['name'].upper():
                            mix_in_point = cue['position']
                        elif 'OUT' in cue['name'].upper() or 'END' in cue['name'].upper():
                            mix_out_point = cue['position']

            # Audio Feature Extensions
            brightness = calculate_brightness(y, sr)
            vocal_instrumental = detect_vocal_instrumental(y, sr)
            danceability = calculate_danceability(y, sr, rekordbox_data.bpm)
            mfcc_fingerprint = calculate_mfcc_fingerprint(y, sr)
            print(f"  [FEATURES] brightness={brightness}, vocal={vocal_instrumental}, dance={danceability}")

        except Exception as e:
            print(f"  Warning: Quick librosa load failed: {e}")
            duration = rekordbox_data.duration or 0.0
            energy = 50  # Default energy
            bass_intensity = 50
            mix_in_point, mix_out_point = 0.0, duration
            mix_in_bars, mix_out_bars = 0, 0
            brightness = 0
            vocal_instrumental = "unknown"
            danceability = 0
            mfcc_fingerprint = []
            genre_result = type('obj', (object,), {'genre': 'Unknown', 'confidence': 0.0, 'source': 'fallback'})()
            section_dicts = []
            structure = type('obj', (object,), {'phrase_unit': 8})()

        # Extract key note and mode from Camelot code (for backward compatibility)
        key_note = "C"
        key_mode = "Major"
        if rekordbox_data.camelot_code:
            # Use reverse mapping to get correct Note and Mode from Camelot code
            key_tuple = REVERSE_CAMELOT_MAP.get(rekordbox_data.camelot_code)
            if key_tuple:
                key_note, key_mode = key_tuple
            else:
                # Fallback: at least detect mode from A/B suffix
                if 'A' in rekordbox_data.camelot_code:
                    key_mode = "Minor"
                elif 'B' in rekordbox_data.camelot_code:
                    key_mode = "Major"

        # Create Track object with Rekordbox data
        track = Track(
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
        )

        cache_track(cache_key, track)
        return track

    # No Rekordbox data - fallback to full librosa analysis
    print(f"  [LIBROSA] Full analysis (no Rekordbox data)")
    artist, title, genre = extract_metadata(file_path)

    try:
        y, sr = librosa.load(file_path)
        duration = librosa.get_duration(y=y, sr=sr)

        # --- Full Analysis --- #
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
        # Wenn BPM unter 100 liegt, ist es fast sicher halftime -> verdoppeln.
        if 40 < bpm < 100:
            bpm = round(bpm * 2, 2)

        chroma = librosa.feature.chroma_stft(y=y, sr=sr)
        chroma_vector = np.mean(chroma, axis=1)
        key_note, key_mode = get_key(chroma_vector)

        # Get Camelot code from key
        camelot_code = CAMELOT_MAP.get((key_note, key_mode), "")

        energy = calculate_energy(y)
        bass_intensity = calculate_bass_intensity(y, sr)

        # DJ Brain: Genre-Klassifikation
        genre_result = classify_genre(y, sr, bpm, bass_intensity, genre)
        print(f"  [GENRE] {genre_result.genre} (confidence: {genre_result.confidence:.2f}, source: {genre_result.source})")

        # DJ Brain: Struktur-Analyse
        structure = analyze_structure(y, sr, bpm, genre_result.genre)
        section_dicts = [s.to_dict() for s in structure.sections]
        section_labels = [s.label for s in structure.sections]
        print(f"  [STRUCTURE] {len(structure.sections)} sections: {section_labels} (phrase: {structure.phrase_unit} bars)")

        # DJ Brain: Genre-spezifische Mix-Punkte (oder Fallback auf generische Analyse)
        if genre_result.genre != "Unknown" and section_dicts:
            mix_in_point, mix_out_point, mix_in_bars, mix_out_bars = calculate_genre_aware_mix_points(
                section_dicts, bpm, duration, genre_result.genre
            )
            print(f"  [DJ BRAIN] Mix points: in={mix_in_bars} bars, out={mix_out_bars} bars ({genre_result.genre})")
        else:
            mix_in_point, mix_out_point, mix_in_bars, mix_out_bars = analyze_structure_and_mix_points(
                y, sr, duration, energy, bpm
            )

        # Audio Feature Extensions
        brightness = calculate_brightness(y, sr)
        vocal_instrumental = detect_vocal_instrumental(y, sr)
        danceability = calculate_danceability(y, sr, bpm)
        mfcc_fingerprint = calculate_mfcc_fingerprint(y, sr)
        print(f"  [FEATURES] brightness={brightness}, vocal={vocal_instrumental}, dance={danceability}")

        # --- Final Track Object --- #
        track = Track(
            filePath=file_path, fileName=os.path.basename(file_path),
            artist=artist, title=title, genre=genre,
            duration=duration, bpm=bpm, keyNote=key_note, keyMode=key_mode,
            camelotCode=camelot_code,
            energy=energy, bass_intensity=bass_intensity,
            mix_in_point=mix_in_point, mix_out_point=mix_out_point,
            mix_in_bars=mix_in_bars, mix_out_bars=mix_out_bars,
            detected_genre=genre_result.genre,
            genre_confidence=genre_result.confidence,
            genre_source=genre_result.source,
            sections=section_dicts,
            phrase_unit=structure.phrase_unit,
            brightness=brightness,
            vocal_instrumental=vocal_instrumental,
            danceability=danceability,
            mfcc_fingerprint=mfcc_fingerprint,
        )

        cache_track(cache_key, track)
        return track

    except Exception as e:
        print(f"Error analyzing {file_path}: {e}")
        return Track(
            filePath=file_path, fileName=os.path.basename(file_path),
            artist=artist, title=title, genre=genre
        )
