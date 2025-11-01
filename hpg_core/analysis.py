import numpy as np
import librosa
import mutagen
import os
import ruptures as rpt
from .models import Track
from .caching import generate_cache_key, get_cached_track, cache_track

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
    freqs = librosa.fft_frequencies(sr=sr)

    # Find frequency bins for the bass range
    bass_indices = np.where((freqs >= 20) & (freqs <= 150))[0]

    total_energy = float(np.sum(stft ** 2))
    bass_energy = float(np.sum(stft[bass_indices, :] ** 2)) if bass_indices.size else 0.0

    if total_energy == 0:
        return 0

    bass_ratio = bass_energy / total_energy
    bass_intensity = float(np.interp(bass_ratio, [0.0, 0.5], [0.0, 100.0]))
    return int(min(max(bass_intensity, 0.0), 100.0))

def get_id3_tags(file_path):
    """Extracts Artist, Title, and Genre from ID3 tags using mutagen."""
    try:
        audio = mutagen.File(file_path, easy=True)
        if audio:
            artist = audio.get('artist', ['Unknown'])[0]
            title = audio.get('title', [os.path.basename(file_path)])[0]
            genre = audio.get('genre', ['Unknown'])[0]
            return artist, title, genre
    except Exception as e:
        print(f"Error reading ID3 tags for {file_path}: {e}")
    return "Unknown", os.path.basename(file_path), "Unknown"

def analyze_structure_and_mix_points(y, sr, duration, energy_level, bpm):
    """
    Analyzes the audio structure to find intro/outro and calculates optimal mix points
    based on beats, downbeats, and musical phrases, avoiding intro/outro sections.

    Returns:
        tuple: (mix_in_point, mix_out_point, mix_in_bars, mix_out_bars)
    """
    mix_in_point = 0.0
    mix_out_point = duration
    mix_in_bars = 0
    mix_out_bars = 0

    if duration is None or duration <= 0 or bpm is None or bpm <= 0:
        return round(mix_in_point, 2), round(mix_out_point, 2), mix_in_bars, mix_out_bars

    try:
        # --- 1. Feature Extraction ---
        hop_length = 1024 # Increased hop_length for better temporal resolution in some features
        frame_rate = sr / hop_length

        # RMS energy (for overall loudness and intro/outro heuristics)
        rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
        rms_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)

        # Onset strength envelope (for beat tracking and rhythmic density)
        onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)

        # Tempogram (for structural segmentation)
        tempogram = librosa.feature.tempogram(onset_envelope=onset_env, sr=sr, hop_length=hop_length)
        tempogram_normalized = librosa.util.normalize(tempogram, axis=0)

        # Spectral Centroid (for timbral changes)
        cent = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop_length)[0]
        cent_normalized = librosa.util.normalize(cent)

        # --- 2. Beat and Downbeat Tracking ---
        tempo, beats = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, hop_length=hop_length)
        beat_times = librosa.frames_to_time(beats, sr=sr, hop_length=hop_length)

        # Downbeat detection heuristic (simplified for 4/4 time)
        # This assumes a 4/4 time signature and finds the strongest beat within each measure.
        # More robust methods exist but this is a reasonable heuristic for a prototype.
        meter = 4
        downbeat_times = []
        if len(beat_times) > meter:
            # Group beats into potential measures
            num_measures = len(beat_times) // meter
            for i in range(num_measures):
                measure_beats_indices = beats[i * meter : (i + 1) * meter]
                if len(measure_beats_indices) == meter:
                    measure_onset_strengths = onset_env[measure_beats_indices]
                    # The downbeat is often the strongest beat in a measure
                    downbeat_local_idx = np.argmax(measure_onset_strengths)
                    downbeat_times.append(librosa.frames_to_time(measure_beats_indices[downbeat_local_idx], sr=sr, hop_length=hop_length))
        downbeat_times = np.array(downbeat_times)


        # --- 3. Structural Segmentation with ruptures ---
        # Combine features for segmentation. Tempogram is a good start.
        # For more robustness, one could concatenate other features like RMS, spectral contrast.
        # Here, we use tempogram for simplicity as it's effective for rhythmic structure.
        if tempogram_normalized.shape[1] < 2: # ruptures needs at least 2 samples
            raise ValueError("Tempogram too short for ruptures segmentation.")

        # Use FASTER algorithm: Pelt instead of Dynp, and increase jump for speed
        # Pelt is much faster than Dynp while maintaining good accuracy
        algo = rpt.Pelt(model="l2", jump=5, min_size=int(frame_rate * 5)).fit(tempogram_normalized.T)
        # Estimate number of change points. A simple heuristic: 1 change point per ~60-90 seconds of music.
        # Pelt auto-detects change points, but we can still use penalty parameter for control
        segment_frames = algo.predict(pen=np.log(tempogram_normalized.shape[1]) * 2)
        segment_times = librosa.frames_to_time(segment_frames, sr=sr, hop_length=hop_length)
        segment_times = np.unique(np.concatenate(([0.0], segment_times, [duration]))) # Ensure start and end are included

        # --- 4. Robust Intro/Outro Detection using Heuristics ---
        # Set safe fallback values first (15% for intro, 85% for outro)
        intro_end_time = duration * 0.15  # Default: first 15% is intro
        outro_start_time = duration * 0.85  # Default: last 15% is outro
        main_body_segments = []

        # Heuristics for Intro: low energy, low spectral centroid, low onset density
        # Iterate through initial segments to find a likely intro
        for i in range(len(segment_times) - 1):
            start_t = segment_times[i]
            end_t = segment_times[i+1]
            if end_t - start_t < 5: # Ignore very short segments for intro/outro
                continue

            # Calculate average features for the segment
            rms_segment = rms[(rms_times >= start_t) & (rms_times < end_t)]
            onset_segment = onset_env[(rms_times >= start_t) & (rms_times < end_t)]
            cent_segment = cent_normalized[(rms_times >= start_t) & (rms_times < end_t)]

            avg_rms = np.mean(rms_segment) if rms_segment.size > 0 else 0.0
            avg_onset_strength = np.mean(onset_segment) if onset_segment.size > 0 else 0.0
            avg_cent = np.mean(cent_segment) if cent_segment.size > 0 else 0.0

            # Simple heuristic: Intro has low RMS, low onset strength, low spectral centroid
            # These thresholds are empirical and might need tuning
            is_intro_candidate = (avg_rms < np.mean(rms) * 0.5 and # significantly lower energy than average
                                  avg_onset_strength < np.mean(onset_env) * 0.5 and # less rhythmic activity
                                  avg_cent < np.mean(cent_normalized) * 0.7) # darker timbre

            if is_intro_candidate and end_t < duration * 0.25: # Intro usually in first 25% of track
                intro_end_time = max(intro_end_time, end_t)  # Keep the latest (longest) intro found
            else:
                break # First non-intro segment found

        # Heuristics for Outro: low energy, low spectral centroid, low onset density, towards the end
        # Iterate backwards from the end to find a likely outro
        for i in range(len(segment_times) - 1, 0, -1):
            start_t = segment_times[i-1]
            end_t = segment_times[i]
            if end_t - start_t < 5: # Ignore very short segments
                continue

            rms_segment = rms[(rms_times >= start_t) & (rms_times < end_t)]
            onset_segment = onset_env[(rms_times >= start_t) & (rms_times < end_t)]
            cent_segment = cent_normalized[(rms_times >= start_t) & (rms_times < end_t)]

            avg_rms = np.mean(rms_segment) if rms_segment.size > 0 else 0.0
            avg_onset_strength = np.mean(onset_segment) if onset_segment.size > 0 else 0.0
            avg_cent = np.mean(cent_segment) if cent_segment.size > 0 else 0.0

            is_outro_candidate = (avg_rms < np.mean(rms) * 0.5 and # significantly lower energy than average
                                  avg_onset_strength < np.mean(onset_env) * 0.5 and # less rhythmic activity
                                  avg_cent < np.mean(cent_normalized) * 0.7) # darker timbre

            if is_outro_candidate and start_t > duration * 0.75: # Outro usually in last 25% of track
                outro_start_time = min(outro_start_time, start_t)  # Keep the earliest (longest) outro found
            else:
                break # First non-outro segment found

        # Ensure intro_end_time is before outro_start_time
        if intro_end_time >= outro_start_time:
            # Fallback to safe percentage-based values
            intro_end_time = duration * 0.15
            outro_start_time = duration * 0.85

        # Define Main Body segments (where mixing is allowed)
        for i in range(len(segment_times) - 1):
            start_t = segment_times[i]
            end_t = segment_times[i+1]
            if start_t >= intro_end_time and end_t <= outro_start_time:
                main_body_segments.append((start_t, end_t))
        
        # If no main body segments found, default to full track minus small buffer
        if not main_body_segments:
            main_body_segments.append((intro_end_time, outro_start_time))
            if main_body_segments[0][1] - main_body_segments[0][0] < 10: # If main body is too short, expand
                main_body_segments[0] = (max(0.0, intro_end_time - 10), min(duration, outro_start_time + 10))


        # --- 5. Phrase Identification within Main Body ---
        # Find all downbeats within the main body
        main_body_downbeats = []
        for start_seg, end_seg in main_body_segments:
            for db_time in downbeat_times:
                if start_seg <= db_time < end_seg:
                    main_body_downbeats.append(db_time)
        main_body_downbeats = np.array(main_body_downbeats)

        # Filter for 8-bar phrases (or 16-bar, depending on desired granularity)
        # A phrase starts at a downbeat and is followed by 7 (for 8-bar) or 15 (for 16-bar) more downbeats
        # We'll look for downbeats that align with 8-bar boundaries
        phrase_start_candidates = []
        if len(main_body_downbeats) > 0:
            # Assuming 8-bar phrases, so we need 8 downbeats to form a phrase
            # We look for downbeats that are multiples of 8 bars from the start of the main body
            # This is a simplification; a more robust approach would look for musical changes at phrase boundaries
            
            # Let's find the first downbeat after intro_end_time
            first_valid_downbeat_idx = np.searchsorted(downbeat_times, intro_end_time)
            if first_valid_downbeat_idx < len(downbeat_times):
                first_valid_downbeat_time = downbeat_times[first_valid_downbeat_idx]
                
                # Iterate through downbeats from this point, looking for 8-bar intervals
                for i, db_time in enumerate(downbeat_times[first_valid_downbeat_idx:]):
                    # Check if this downbeat is roughly at an 8-bar interval from the first valid downbeat
                    # This is a very rough heuristic and assumes consistent tempo and 8-bar phrasing
                    # A more accurate method would involve counting actual bars
                    
                    # For now, let's just consider all downbeats within the main body as phrase start candidates
                    # and filter them later for mix points
                    if db_time >= intro_end_time and db_time <= outro_start_time:
                        phrase_start_candidates.append(db_time)
        
        # Remove duplicates and sort
        phrase_start_candidates = np.unique(phrase_start_candidates)
        
        # --- 6. Mix Point Selection ---
        # Default to safe values if no suitable phrase candidates are found
        mix_in_point = max(0.0, intro_end_time + 5.0) # 5 seconds after intro ends
        mix_out_point = min(duration, outro_start_time - 5.0) # 5 seconds before outro starts

        # Try to find a mix-in point at an 8-bar boundary
        for p_time in phrase_start_candidates:
            if p_time >= intro_end_time + 5.0 and p_time < duration * 0.5: # Mix-in in first half, after intro
                mix_in_point = p_time
                break
        
        # Try to find a mix-out point at an 8-bar boundary
        for p_time in reversed(phrase_start_candidates):
            if p_time <= outro_start_time - 5.0 and p_time > duration * 0.5 and p_time > mix_in_point + 10: # Mix-out in second half, before outro, and after mix-in
                mix_out_point = p_time
                break
        
        # Final sanity checks
        if mix_in_point >= mix_out_point - 10.0: # Ensure at least 10 seconds between in and out
            mix_in_point = max(0.0, intro_end_time + 5.0)
            mix_out_point = min(duration, outro_start_time - 5.0)
            if mix_in_point >= mix_out_point: # Fallback to simple buffer if complex logic fails
                mix_in_point = duration * 0.25
                mix_out_point = duration * 0.75

        # --- 7. Calculate Bar Numbers ---
        # Bar = 4 Beats in 4/4 time signature
        # BPM = Beats per Minute, so seconds per beat = 60 / BPM
        # Bars = (time_in_seconds / (60 / BPM)) / 4
        seconds_per_beat = 60.0 / bpm
        seconds_per_bar = seconds_per_beat * 4  # 4 beats per bar in 4/4

        mix_in_bars = int(mix_in_point / seconds_per_bar)
        mix_out_bars = int(mix_out_point / seconds_per_bar)

        return round(float(mix_in_point), 2), round(float(mix_out_point), 2), mix_in_bars, mix_out_bars

    except Exception as e:
        print(f"Error in analyze_structure_and_mix_points: {e}")
        # Fallback to safe default values
        safe_in = min(max(duration * 0.2, 0.0), max(duration - 1.0, 0.0))
        safe_out = max(duration * 0.8, safe_in + 1.0)
        safe_out = min(safe_out, duration)
        safe_in = min(safe_in, max(safe_out - 1.0, 0.0))

        # Calculate bars for fallback
        seconds_per_bar = (60.0 / bpm) * 4 if bpm > 0 else 2.0  # Default ~120 BPM
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
    cached_track = get_cached_track(cache_key)

    if cached_track:
        print(f"Cache hit for: {os.path.basename(file_path)}")
        return cached_track

    print(f"Analyzing: {os.path.basename(file_path)}")
    
    artist, title, genre = get_id3_tags(file_path)

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
        bpm = round(float(bpm_value if bpm_value > 0 else 120.0), 2)

        chroma = librosa.feature.chroma_stft(y=y, sr=sr)
        chroma_vector = np.mean(chroma, axis=1)
        key_note, key_mode = get_key(chroma_vector)

        # Assign camelotCode here directly
        from .playlist import key_to_camelot # Import locally to avoid circular dependency issues
        temp_track_for_camelot = Track(filePath=file_path, fileName=os.path.basename(file_path), keyNote=key_note, keyMode=key_mode)
        key_to_camelot(temp_track_for_camelot)
        camelot_code = temp_track_for_camelot.camelotCode

        energy = calculate_energy(y)
        bass_intensity = calculate_bass_intensity(y, sr)

        mix_in_point, mix_out_point, mix_in_bars, mix_out_bars = analyze_structure_and_mix_points(
            y, sr, duration, energy, bpm
        )

        # --- Final Track Object --- #
        track = Track(
            filePath=file_path, fileName=os.path.basename(file_path),
            artist=artist, title=title, genre=genre,
            duration=duration, bpm=bpm, keyNote=key_note, keyMode=key_mode,
            camelotCode=camelot_code, # Assign camelotCode here
            energy=energy, bass_intensity=bass_intensity,
            mix_in_point=mix_in_point, mix_out_point=mix_out_point,
            mix_in_bars=mix_in_bars, mix_out_bars=mix_out_bars
        )

        cache_track(cache_key, track)
        return track

    except Exception as e:
        print(f"Error analyzing {file_path}: {e}")
        return Track(
            filePath=file_path, fileName=os.path.basename(file_path),
            artist=artist, title=title, genre=genre
        )
