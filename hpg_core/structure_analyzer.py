"""
Structure Analyzer for DJ Brain

Analyzes track structure to identify sections:
- Intro, Build, Drop, Breakdown, Outro, Main

Uses self-similarity matrices (SSM) from MFCCs to find structural boundaries,
then labels sections based on energy profiles. All boundaries are quantized
to genre-specific phrase units (8, 16, or 32 bars).

No additional dependencies beyond librosa (already installed).

Algorithm:
1. Compute MFCC-based self-similarity matrix
2. Derive novelty curve (structural change points)
3. Pick peaks as section boundaries
4. Quantize boundaries to bar/phrase grid
5. Label sections by energy profile (low=intro/outro, high=drop, mid=main/build)
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
import numpy as np
import librosa

from .config import HOP_LENGTH, METER


# === Data Structures ===

@dataclass
class TrackSection:
  """A labeled section of a track."""
  label: str        # "intro", "build", "drop", "breakdown", "outro", "main"
  start_time: float # Seconds
  end_time: float   # Seconds
  start_bar: int
  end_bar: int
  avg_energy: float # 0-100

  def duration(self) -> float:
    return self.end_time - self.start_time

  def to_dict(self) -> dict:
    return asdict(self)


@dataclass
class TrackStructure:
  """Complete structural analysis of a track."""
  sections: list[TrackSection] = field(default_factory=list)
  total_bars: int = 0
  phrase_unit: int = 8  # 8, 16, or 32 bars


# === Genre-specific Phrase Units ===

GENRE_PHRASE_UNITS: dict[str, int] = {
  "Psytrance": 16,      # Psytrance uses 16-bar phrases (long builds/drops)
  "Tech House": 8,       # Tech House uses 8-bar phrases (tight groove loops)
  "Progressive": 8,      # Progressive uses 8-bar phrases (gradual layers)
  "Melodic Techno": 8,   # Melodic Techno uses 8-bar phrases
  "Techno": 8,           # Techno uses 8-bar phrases (driving, repetitive)
  "Deep House": 8,       # Deep House uses 8-bar phrases (smooth grooves)
  "Trance": 16,          # Trance uses 16-bar phrases (big builds, long breakdowns)
  "Drum & Bass": 8,      # DnB uses 8-bar phrases (fast switches)
  "Minimal": 8,          # Minimal uses 8-bar phrases (hypnotic loops)
  "Unknown": 8,          # Default to 8 bars
}

# Minimum number of sections to detect (prevents over-segmentation)
MIN_SECTIONS = 3
# Maximum number of sections (prevents over-segmentation on noisy tracks)
MAX_SECTIONS = 12

# Minimum section duration in seconds
MIN_SECTION_DURATION = 8.0

# Energy thresholds for section labeling (relative to track average)
ENERGY_HIGH_THRESHOLD = 1.2     # >120% of avg = high energy (drop)
ENERGY_LOW_THRESHOLD = 0.6      # <60% of avg = low energy (intro/outro)
ENERGY_BUILD_THRESHOLD = 0.9    # 60-90% with rising trend = build
ENERGY_BREAKDOWN_THRESHOLD = 0.8  # Sudden drop after high = breakdown


# === Core Analysis Functions ===

def _compute_novelty_curve(y: np.ndarray, sr: int, hop_length: int = HOP_LENGTH) -> tuple[np.ndarray, np.ndarray]:
  """
  Compute a novelty curve from MFCC-based self-similarity.

  The novelty curve highlights points of structural change in the audio.
  Peaks in this curve correspond to section boundaries.

  Args:
    y: Audio signal (mono)
    sr: Sample rate
    hop_length: Hop size for feature extraction

  Returns:
    (novelty_curve, times) - novelty values and their timestamps
  """
  # Extract MFCCs (13 coefficients, standard for music)
  mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=hop_length)

  # Compute self-similarity using recurrence matrix
  # This creates a matrix where similar frames have high values
  rec = librosa.segment.recurrence_matrix(
    mfcc,
    width=int(sr / hop_length * 4),  # ~4 second context window
    mode='affinity',
    sym=True,
  )

  # Compute novelty from the recurrence matrix
  # Novelty is high where the local structure changes
  novelty = np.zeros(rec.shape[0])
  kernel_size = int(sr / hop_length * 2)  # ~2 second kernel
  kernel_size = max(4, kernel_size)

  # Checkerboard kernel for novelty detection
  for i in range(kernel_size, rec.shape[0] - kernel_size):
    # Compare blocks before and after the current frame
    block_before = rec[i - kernel_size:i, i - kernel_size:i]
    block_after = rec[i:i + kernel_size, i:i + kernel_size]
    block_cross = rec[i - kernel_size:i, i:i + kernel_size]

    if block_before.size > 0 and block_after.size > 0 and block_cross.size > 0:
      self_sim = (np.mean(block_before) + np.mean(block_after)) / 2.0
      cross_sim = np.mean(block_cross)
      novelty[i] = max(0.0, self_sim - cross_sim)

  # Smooth the novelty curve
  if len(novelty) > 8:
    kernel = np.hanning(8)
    kernel /= kernel.sum()
    novelty = np.convolve(novelty, kernel, mode='same')

  times = librosa.frames_to_time(np.arange(len(novelty)), sr=sr, hop_length=hop_length)

  return novelty, times


def _pick_boundaries(
  novelty: np.ndarray,
  times: np.ndarray,
  duration: float,
  min_distance_sec: float = MIN_SECTION_DURATION,
  max_sections: int = MAX_SECTIONS,
) -> list[float]:
  """
  Pick section boundaries from the novelty curve.

  Uses peak picking with minimum distance constraint.

  Args:
    novelty: Novelty curve
    times: Timestamps for novelty values
    duration: Total track duration
    min_distance_sec: Minimum time between boundaries
    max_sections: Maximum number of sections

  Returns:
    List of boundary times (sorted), always starting with 0.0
  """
  if len(novelty) < 4:
    return [0.0]

  # Calculate minimum distance in frames
  dt = times[1] - times[0] if len(times) > 1 else 0.05
  min_distance_frames = max(1, int(min_distance_sec / dt))

  # Normalize novelty
  novelty_max = np.max(novelty)
  if novelty_max > 0:
    novelty_norm = novelty / novelty_max
  else:
    return [0.0]

  # Find peaks with minimum height and distance
  # Start with a moderate threshold, lower it if we get too few peaks
  threshold = 0.3
  boundaries = []

  while threshold >= 0.1 and len(boundaries) < MIN_SECTIONS - 1:
    peaks = []
    for i in range(1, len(novelty_norm) - 1):
      if novelty_norm[i] > novelty_norm[i - 1] and novelty_norm[i] > novelty_norm[i + 1]:
        if novelty_norm[i] >= threshold:
          peaks.append((i, novelty_norm[i]))

    # Sort by strength (descending)
    peaks.sort(key=lambda x: x[1], reverse=True)

    # Apply minimum distance constraint
    selected = []
    for idx, strength in peaks:
      too_close = False
      for sel_idx in selected:
        if abs(idx - sel_idx) < min_distance_frames:
          too_close = True
          break
      if not too_close:
        selected.append(idx)

      if len(selected) >= max_sections - 1:
        break

    boundaries = sorted([times[idx] for idx in selected])
    threshold -= 0.05

  # Always include 0.0 as the first boundary
  if not boundaries or boundaries[0] > 1.0:
    boundaries = [0.0] + boundaries
  else:
    boundaries[0] = 0.0

  return boundaries


def _quantize_to_bars(
  boundaries: list[float],
  bpm: float,
  duration: float,
  phrase_unit: int = 8,
) -> list[float]:
  """
  Quantize boundary times to the nearest bar or phrase boundary.

  Args:
    boundaries: Section boundary times
    bpm: Track BPM
    duration: Track duration
    phrase_unit: Phrase length in bars (8, 16, 32)

  Returns:
    Quantized boundary times
  """
  if bpm <= 0:
    return boundaries

  seconds_per_beat = 60.0 / bpm
  seconds_per_bar = seconds_per_beat * METER

  quantized = []
  for t in boundaries:
    # Quantize to nearest bar
    bar_index = round(t / seconds_per_bar)
    quantized_time = bar_index * seconds_per_bar

    # Clamp to track bounds
    quantized_time = max(0.0, min(quantized_time, duration))
    quantized.append(quantized_time)

  # Remove duplicates and sort
  quantized = sorted(set(quantized))

  # Ensure minimum spacing of 2 bars
  min_spacing = seconds_per_bar * 2
  filtered = [quantized[0]] if quantized else [0.0]
  for t in quantized[1:]:
    if t - filtered[-1] >= min_spacing:
      filtered.append(t)

  return filtered


def _compute_section_energy(y: np.ndarray, sr: int, start: float, end: float) -> float:
  """
  Compute average RMS energy for a section of audio.

  Args:
    y: Full audio signal
    sr: Sample rate
    start: Section start time (seconds)
    end: Section end time (seconds)

  Returns:
    Average energy scaled to 0-100
  """
  start_sample = int(start * sr)
  end_sample = int(end * sr)

  # Clamp to signal bounds
  start_sample = max(0, min(start_sample, len(y) - 1))
  end_sample = max(start_sample + 1, min(end_sample, len(y)))

  segment = y[start_sample:end_sample]
  if len(segment) == 0:
    return 0.0

  rms = float(np.sqrt(np.mean(segment ** 2)))
  # Scale to 0-100 (typical audio RMS is 0.0 to ~0.4)
  energy = float(np.interp(rms, [0.0, 0.4], [0.0, 100.0]))
  return min(max(energy, 0.0), 100.0)


def _compute_energy_trend(y: np.ndarray, sr: int, start: float, end: float) -> str:
  """
  Determine if energy is rising, falling, or stable within a section.

  Returns: "rising", "falling", or "stable"
  """
  start_sample = int(start * sr)
  end_sample = int(end * sr)
  start_sample = max(0, min(start_sample, len(y) - 1))
  end_sample = max(start_sample + 1, min(end_sample, len(y)))

  segment = y[start_sample:end_sample]
  if len(segment) < sr:  # Less than 1 second
    return "stable"

  # Split into first and second half
  mid = len(segment) // 2
  first_half_rms = float(np.sqrt(np.mean(segment[:mid] ** 2)))
  second_half_rms = float(np.sqrt(np.mean(segment[mid:] ** 2)))

  if first_half_rms == 0:
    return "rising" if second_half_rms > 0 else "stable"

  ratio = second_half_rms / first_half_rms
  if ratio > 1.3:
    return "rising"
  elif ratio < 0.7:
    return "falling"
  return "stable"


def _label_sections(
  boundaries: list[float],
  duration: float,
  energies: list[float],
  trends: list[str],
) -> list[str]:
  """
  Assign labels to sections based on energy profiles and position.

  Labeling logic:
  - First section with low energy = "intro"
  - Last section with low energy = "outro"
  - High energy sections = "drop"
  - Rising energy before a drop = "build"
  - Low energy after a drop = "breakdown"
  - Everything else = "main"

  Args:
    boundaries: Section boundary times
    duration: Total track duration
    energies: Average energy per section
    trends: Energy trend per section ("rising", "falling", "stable")

  Returns:
    List of labels for each section
  """
  n = len(energies)
  if n == 0:
    return []

  labels = ["main"] * n

  # Calculate average energy for threshold computation
  avg_energy = np.mean(energies) if energies else 50.0
  high_threshold = avg_energy * ENERGY_HIGH_THRESHOLD
  low_threshold = avg_energy * ENERGY_LOW_THRESHOLD

  # Step 1: Label intro
  # Ein Intro kann auch mit moderater Energie starten (z.B. Kick-Loop bei
  # Melodic Techno/Tech House). Entscheidend ist: Die erste Section hat
  # WENIGER Energie als spaetere Sections, oder ist "rising".
  # Vergleiche mit dem Maximum statt nur mit dem Durchschnitt.
  max_energy = max(energies) if energies else 100.0
  intro_relative_threshold = max_energy * 0.85  # Intro = unter 85% der Peak-Energie

  is_intro = (
    energies[0] < low_threshold           # Klassisch: Niedrige Energie
    or trends[0] == "rising"               # Steigende Energie = Aufbau
    or (n >= 3 and energies[0] < intro_relative_threshold
        and boundaries[0] < duration * 0.15)  # Unter Peak-Niveau UND frueh im Track
  )
  if is_intro:
    labels[0] = "intro"
    # Multi-Section-Intro: Auch zweite Section wenn noch frueh und unter Peak
    if n > 2 and boundaries[1] < duration * 0.25:
      if (energies[1] < avg_energy or trends[1] == "rising"
          or energies[1] < intro_relative_threshold):
        labels[1] = "intro"

  # Step 2: Label outro
  # Gleiche Logik: Outro hat weniger Energie als der Peak, oder ist "falling"
  outro_is_low = (
    n > 1
    and (energies[-1] < low_threshold
         or trends[-1] == "falling"
         or (energies[-1] < intro_relative_threshold
             and boundaries[-1] > duration * 0.8))
  )
  if outro_is_low:
    labels[-1] = "outro"
    # Multi-Section-Outro
    if n > 2 and boundaries[-2] > duration * 0.75:
      if (energies[-2] < avg_energy or trends[-2] == "falling"
          or energies[-2] < intro_relative_threshold):
        labels[-2] = "outro"

  # Step 3: Label drops (high energy sections)
  for i in range(n):
    if labels[i] != "main":
      continue
    if energies[i] >= high_threshold:
      labels[i] = "drop"

  # Step 4: Label builds (rising energy before a drop)
  for i in range(n - 1):
    if labels[i] != "main":
      continue
    if labels[i + 1] == "drop" and trends[i] == "rising":
      labels[i] = "build"

  # Step 5: Label breakdowns (low energy after a drop)
  for i in range(1, n):
    if labels[i] != "main":
      continue
    if labels[i - 1] == "drop" and energies[i] < avg_energy * ENERGY_BREAKDOWN_THRESHOLD:
      labels[i] = "breakdown"

  return labels


# === Main Analysis Function ===

def analyze_structure(
  y: np.ndarray,
  sr: int,
  bpm: float,
  genre: str = "Unknown",
) -> TrackStructure:
  """
  Analyze track structure to identify sections.

  Uses MFCC-based self-similarity for boundary detection,
  then labels sections by energy profile. All boundaries
  are quantized to genre-specific phrase units.

  Args:
    y: Audio signal (mono, from librosa.load)
    sr: Sample rate
    bpm: Track BPM
    genre: Detected genre (affects phrase unit)

  Returns:
    TrackStructure with labeled sections
  """
  duration = librosa.get_duration(y=y, sr=sr)
  if duration <= 0 or bpm <= 0:
    return TrackStructure()

  # Determine phrase unit based on genre
  phrase_unit = GENRE_PHRASE_UNITS.get(genre, 8)

  seconds_per_beat = 60.0 / bpm
  seconds_per_bar = seconds_per_beat * METER
  total_bars = int(duration / seconds_per_bar)

  try:
    # Step 1: Compute novelty curve
    novelty, times = _compute_novelty_curve(y, sr)

    # Step 2: Pick section boundaries
    boundaries = _pick_boundaries(
      novelty, times, duration,
      min_distance_sec=max(MIN_SECTION_DURATION, seconds_per_bar * phrase_unit * 0.5),
    )

    # Step 3: Quantize to bar grid
    boundaries = _quantize_to_bars(boundaries, bpm, duration, phrase_unit)

    # Ensure we have at least intro + main + outro
    if len(boundaries) < 2:
      # Fallback: split into 3 equal-ish sections
      third = duration / 3.0
      boundaries = [0.0, third, 2.0 * third]
      boundaries = _quantize_to_bars(boundaries, bpm, duration, phrase_unit)

  except Exception as e:
    print(f"  [STRUCTURE] Novelty analysis failed: {e}")
    # Fallback: simple 3-section split
    third = duration / 3.0
    boundaries = [0.0, third, 2.0 * third]
    boundaries = _quantize_to_bars(boundaries, bpm, duration, phrase_unit)

  # Step 4: Compute energy and trend for each section
  section_ends = boundaries[1:] + [duration]
  energies = []
  trends = []

  for i, start in enumerate(boundaries):
    end = section_ends[i]
    energy = _compute_section_energy(y, sr, start, end)
    trend = _compute_energy_trend(y, sr, start, end)
    energies.append(energy)
    trends.append(trend)

  # Step 5: Label sections
  labels = _label_sections(boundaries, duration, energies, trends)

  # Step 6: Build TrackSection objects
  sections = []
  for i, start in enumerate(boundaries):
    end = section_ends[i]
    start_bar = int(round(start / seconds_per_bar))
    end_bar = int(round(end / seconds_per_bar))

    sections.append(TrackSection(
      label=labels[i] if i < len(labels) else "main",
      start_time=round(start, 2),
      end_time=round(end, 2),
      start_bar=start_bar,
      end_bar=end_bar,
      avg_energy=round(energies[i], 1) if i < len(energies) else 50.0,
    ))

  return TrackStructure(
    sections=sections,
    total_bars=total_bars,
    phrase_unit=phrase_unit,
  )
