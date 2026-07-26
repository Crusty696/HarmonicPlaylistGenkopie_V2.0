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

import logging
from dataclasses import dataclass, field, asdict
import numpy as np
import librosa

from .config import HOP_LENGTH, METER, SECTION_ENERGY_THRESHOLD
from .genres import DEFAULT_MIX_PROFILE, GENRE_MIX_PROFILES

logger = logging.getLogger(__name__)


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
# Audit-Fix 2026-07-17: aus den GENRE_MIX_PROFILES (genres.py, Single Source
# of Truth) abgeleitet statt als zweite Tabelle manuell synchron gepflegt.
GENRE_PHRASE_UNITS: dict[str, int] = {
  genre: profile.phrase_unit for genre, profile in GENRE_MIX_PROFILES.items()
}
GENRE_PHRASE_UNITS["Unknown"] = DEFAULT_MIX_PROFILE.phrase_unit

# Speicher-Obergrenze fuer die Self-Similarity-Matrix (dense O(n^2)):
# 3000 Frames = ~72 MB float64; laengere MFCC-Sequenzen werden dezimiert
MAX_SSM_FRAMES = 3000

# Minimum number of sections to detect (prevents over-segmentation)
MIN_SECTIONS = 3
# Maximum number of sections (prevents over-segmentation on noisy tracks)
MAX_SECTIONS = 12

# Minimum section duration in seconds
MIN_SECTION_DURATION = 8.0

# Energy thresholds for section labeling (relative to track average)
ENERGY_HIGH_THRESHOLD = 1.2     # >120% of avg = high energy (drop)
ENERGY_LOW_THRESHOLD = 0.6      # <60% of avg = low energy (intro/outro)
ENERGY_BREAKDOWN_THRESHOLD = 0.8  # Sudden drop after high = breakdown

# Phrase-Messung bleibt absichtlich auf den bereits unterstuetzten Werten.
PHRASE_UNIT_CANDIDATES = (8, 16, 32)
PHRASE_ESTIMATE_MIN_SCORE = 0.18
PHRASE_ESTIMATE_MIN_MARGIN = 0.08
PHRASE_PRIOR_BONUS = 0.03


# === Core Analysis Functions ===

def _compute_novelty_curve(
  y: np.ndarray,
  sr: int,
  hop_length: int = HOP_LENGTH,
  feature_cache=None,
) -> tuple[np.ndarray, np.ndarray]:
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
  # Extract MFCCs (13 coefficients, standard for music). A shared cache is
  # optional, damit die öffentliche Hilfsfunktion rückwärtskompatibel bleibt.
  if feature_cache is not None:
    mfcc = feature_cache.get_mfcc(n_mfcc=13, hop_length=hop_length)
  else:
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=hop_length)

  # Check for minimum MFCC length (needs at least 10 frames for recurrence matrix)
  num_frames = mfcc.shape[1]
  if num_frames < 10:
    # Audio too short for novelty analysis
    novelty = np.zeros(num_frames)
    times = librosa.frames_to_time(np.arange(num_frames), sr=sr, hop_length=hop_length)
    return novelty, times

  # Speicher-Guard (Audit 2026-07-17): recurrence_matrix ist DENSE O(n^2) —
  # 10 Min Audio ergaben ~12.900 Frames = ~1,3 GB pro Track. MFCC-Sequenz
  # wird auf max. MAX_SSM_FRAMES dezimiert (Zeitaufloesung bleibt fuer
  # Sektions-Grenzen mehr als ausreichend, Grenzen werden ohnehin auf Bars
  # quantisiert).
  step = 1
  if num_frames > MAX_SSM_FRAMES:
    step = -(-num_frames // MAX_SSM_FRAMES)
    mfcc = mfcc[:, ::step]
    num_frames = mfcc.shape[1]
  effective_hop = hop_length * step

  # Compute self-similarity using recurrence matrix
  # This creates a matrix where similar frames have high values
  # Width must be strictly less than (num_frames - 1) // 2 (safety margin for edge cases)
  max_width = max(4, (num_frames - 1) // 2 - 1)  # Strict limit with safety margin
  width = min(int(sr / effective_hop * 4), max_width)  # ~4 second context window, but capped
  width = max(1, width)
  try:
    rec = librosa.segment.recurrence_matrix(
      mfcc,
      width=width,
      mode='affinity',
      sym=True,
    )
  except Exception:
    # Audio signal is empty or too quiet for recurrence matrix (sparse/empty graph)
    # This can happen with silent or very short audio files
    novelty = np.zeros(num_frames)
    times = librosa.frames_to_time(np.arange(num_frames), sr=sr, hop_length=effective_hop)
    return novelty, times

  # Compute novelty from the recurrence matrix
  # Novelty is high where the local structure changes
  novelty = np.zeros(rec.shape[0])
  kernel_size = int(sr / effective_hop * 2)  # ~2 second kernel
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

  # MFCC-Novelty bleibt die Hauptquelle. Bass und Percussion liefern nur einen
  # kleinen, robust normalisierten Zusatz, damit reine Klangfarbenwechsel die
  # Sektionsgrenzen nicht dominieren.
  signal_novelty = _compute_bass_percussion_novelty(
    y, sr, effective_hop, len(novelty)
  )
  if signal_novelty is not None:
    mfcc_novelty = _normalize_novelty(novelty)
    bass_novelty = _normalize_novelty(signal_novelty[0])
    percussion_novelty = _normalize_novelty(signal_novelty[1])
    novelty = (
      0.65 * mfcc_novelty
      + 0.20 * bass_novelty
      + 0.15 * percussion_novelty
    )

  times = librosa.frames_to_time(np.arange(len(novelty)), sr=sr, hop_length=effective_hop)

  return novelty, times


def _normalize_novelty(values: np.ndarray) -> np.ndarray:
  """Normalisiert eine Novelty-Kurve robust auf den Bereich 0..1."""
  values = np.nan_to_num(np.asarray(values, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
  if values.size == 0:
    return values

  values = np.maximum(values - np.percentile(values, 10), 0.0)
  scale = np.percentile(values, 95)
  if scale <= np.finfo(float).eps:
    scale = np.max(values)
  if scale <= np.finfo(float).eps:
    return np.zeros_like(values)
  return np.clip(values / scale, 0.0, 1.0)


def _compute_bass_percussion_novelty(
  y: np.ndarray,
  sr: int,
  hop_length: int,
  num_frames: int,
) -> tuple[np.ndarray, np.ndarray] | None:
  """Erzeugt Bass- und Percussion-Onset-Novelty mit gleicher Frame-Anzahl."""
  if num_frames < 4 or len(y) == 0 or sr <= 0:
    return None

  try:
    # Tiefe Mel-Baender bilden Kick/Bass ab; positive Spektral-Aenderungen
    # reagieren weniger empfindlich auf die absolute Master-Lautheit.
    bass_mel = librosa.feature.melspectrogram(
      y=y,
      sr=sr,
      n_fft=max(1024, hop_length * 4),
      hop_length=hop_length,
      n_mels=16,
      fmin=20.0,
      fmax=min(250.0, sr / 2.0),
    )
    bass_flux = np.maximum(np.diff(np.log1p(bass_mel), axis=1), 0.0)
    bass_flux = np.mean(bass_flux, axis=0)
    bass_flux = np.pad(bass_flux, (1, 0))

    _, percussive = librosa.effects.hpss(y)
    percussion_flux = librosa.onset.onset_strength(
      y=percussive,
      sr=sr,
      hop_length=hop_length,
    )

    target_times = librosa.frames_to_time(
      np.arange(num_frames), sr=sr, hop_length=hop_length
    )
    bass_times = librosa.frames_to_time(
      np.arange(len(bass_flux)), sr=sr, hop_length=hop_length
    )
    percussion_times = librosa.frames_to_time(
      np.arange(len(percussion_flux)), sr=sr, hop_length=hop_length
    )
    bass = np.interp(target_times, bass_times, bass_flux, left=0.0, right=0.0)
    percussion = np.interp(
      target_times,
      percussion_times,
      percussion_flux,
      left=0.0,
      right=0.0,
    )
    return bass, percussion
  except Exception as signal_err:
    logger.debug("Bass-/Percussion-Novelty nicht verfuegbar: %s", signal_err)
    return None


def _bar_novelty(
  novelty: np.ndarray,
  times: np.ndarray,
  seconds_per_bar: float,
  anchor: float = 0.0,
) -> np.ndarray:
  """Aggregiert Frame-Novelty auf ein barweises Raster."""
  if seconds_per_bar <= 0 or len(novelty) == 0 or len(times) != len(novelty):
    return np.array([], dtype=float)

  values = np.nan_to_num(np.asarray(novelty, dtype=float))
  frame_times = np.asarray(times, dtype=float)
  bar_indices = np.floor((frame_times - anchor) / seconds_per_bar).astype(int)
  valid = (bar_indices >= 0) & np.isfinite(values)
  if not np.any(valid):
    return np.array([], dtype=float)

  bars = np.zeros(int(np.max(bar_indices[valid])) + 1, dtype=float)
  counts = np.zeros_like(bars)
  np.add.at(bars, bar_indices[valid], values[valid])
  np.add.at(counts, bar_indices[valid], 1.0)
  nonempty = counts > 0
  bars[nonempty] /= counts[nonempty]
  return bars


def _estimate_phrase_unit_from_novelty(
  novelty: np.ndarray,
  times: np.ndarray,
  bpm: float,
  genre: str = "Unknown",
  anchor: float = 0.0,
) -> int | None:
  """Misst eine Phrase aus Bar-Novelty/Autokorrelation, sonst ``None``.

  Die Rueckgabe ``None`` ist bewusst der Unsicherheitskanal: Der Aufrufer
  verwendet dann unveraendert den Genre-Prior.
  """
  prior = GENRE_PHRASE_UNITS.get(genre, 8)
  if bpm <= 0:
    return None

  seconds_per_bar = (60.0 / bpm) * METER
  bars = _bar_novelty(novelty, times, seconds_per_bar, anchor)
  if len(bars) < 16:
    return None

  bars = _normalize_novelty(bars)
  centered = bars - np.mean(bars)
  variance = float(np.dot(centered, centered))
  if variance <= np.finfo(float).eps:
    return None

  candidates = [
    unit for unit in PHRASE_UNIT_CANDIDATES
    if len(bars) >= (2 * unit + 8)
  ]
  if not candidates:
    return None

  scores: dict[int, float] = {}
  for unit in candidates:
    lag = centered[unit:]
    reference = centered[:-unit]
    score = float(np.dot(lag, reference) / variance)
    # Ein ganzzahliges Vielfaches kann dieselbe Wiederholung sehen. Die
    # kleinere Haelfte wird deshalb als Fundamentalperiode bevorzugt.
    if unit >= 16:
      half_score = scores.get(unit // 2)
      if half_score is None and len(bars) >= (2 * (unit // 2) + 8):
        half = centered[unit // 2:]
        half_reference = centered[:-(unit // 2)]
        half_score = float(np.dot(half, half_reference) / variance)
      if half_score is not None:
        score -= 0.5 * max(0.0, half_score)
    scores[unit] = score

  posterior_scores = {
    unit: score + (PHRASE_PRIOR_BONUS if unit == prior else 0.0)
    for unit, score in scores.items()
  }
  ranked = sorted(
    posterior_scores.items(), key=lambda item: item[1], reverse=True
  )
  if len(ranked) < 2:
    return None
  best_unit, best_score = ranked[0]
  second_score = ranked[1][1] if len(ranked) > 1 else -1.0
  if scores[best_unit] < PHRASE_ESTIMATE_MIN_SCORE:
    return None
  if len(ranked) > 1 and best_score - second_score < PHRASE_ESTIMATE_MIN_MARGIN:
    return None
  return best_unit


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

  # Peaks mit Mindest-Hoehe und Abstand finden
  # M2 Audit-Fix: Threshold aus config.py statt Magic Number
  threshold = SECTION_ENERGY_THRESHOLD
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
  anchor: float = 0.0,
  seconds_per_bar: float | None = None,
  whole_phrase: bool = True,
) -> list[float]:
  """
  Quantize boundary times to the whole-phrase grid by default.

  Audit-Fix 2026-07-17: vorher wurde phrase_unit ignoriert und nur auf
  einzelne Bars quantisiert — Sektionsgrenzen (und damit Mix-Punkte) lagen
  nicht auf musikalischen Phrasenanfaengen. Halbe Phrase als Gitter
  (Psytrance/Trance: 8 Bars, sonst 4) balanciert Musikalitaet gegen
  Aufloesung der Sektions-Erkennung.

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

  bar_length = seconds_per_bar or ((60.0 / bpm) * METER)
  # Phase 1.1: Sections und Mix-Punkte verwenden dasselbe GANZE
  # Phrasengitter. Die frühere Halbphrasen-Quantisierung ließ Grenzen bis zu
  # einer ganzen Phrase vom Mix-Gitter abweichen.
  grid_seconds = bar_length * phrase_unit if whole_phrase else bar_length

  quantized = []
  for t in boundaries:
    # Auf die naechste ganze Phrase relativ zum gemeinsamen Anker quantisieren.
    grid_index = round((t - anchor) / grid_seconds)
    quantized_time = grid_index * grid_seconds + anchor

    # Clamp to track bounds
    quantized_time = max(0.0, min(quantized_time, duration))
    quantized.append(quantized_time)

  # Remove duplicates and sort
  quantized = sorted(set(quantized))

  # Ensure minimum spacing of 2 bars
  min_spacing = bar_length * 2
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

  # HIGH-Fix: NaN/Inf im Audio (korrupte Datei/Decode-Fehler) wuerde sonst als
  # avg_energy=nan still bis in Cache/Scoring leaken (NaN-Vergleiche sind immer
  # False -> Energie-Schwellen brechen lautlos). Konsistent mit den nan_to_num-
  # Guards in analysis.py.
  segment = np.nan_to_num(y[start_sample:end_sample])
  if len(segment) == 0:
    return 0.0

  rms = float(np.sqrt(np.mean(segment ** 2)))
  # Skala am Track selbst kalibrieren — die fixe 0.4-Obergrenze liess laut
  # gemasterte Tracks (RMS > 0.4) alle Sektionen auf 100 saettigen und
  # zerstoerte die Drop-vs-Main-Unterscheidung (Audit-Fix 2026-07-17).
  # np.dot statt y**2 vermeidet ein grosses temporaeres Array.
  track_rms = float(np.sqrt(np.nan_to_num(np.dot(y, y)) / len(y))) if len(y) else 0.0
  # Faktor 1.6: durchschnittliche Sektion landet bei ~62, Drops (1.2-1.5x
  # Track-RMS) behalten Headroom bis 100 statt zu saettigen
  scale = max(0.4, track_rms * 1.6)
  energy = float(np.interp(rms, [0.0, scale], [0.0, 100.0]))
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

  segment = np.nan_to_num(y[start_sample:end_sample])
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
    # "rising" allein reicht nicht — fast jeder Track-Anfang steigt; ein Track,
    # der "hot" (nahe Peak-Energie) startet, hat kein Intro (Audit-Fix 2026-07-17)
    or (trends[0] == "rising" and energies[0] < intro_relative_threshold)
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
  # MED-Fix: energies[i] > 0 erzwingen — bei reiner Stille ist avg_energy=0 und
  # damit high_threshold=0, sonst wuerde ein stiller Abschnitt (0 >= 0) faelsch-
  # lich als energiereichster "drop" gelabelt und die Mixpoint-Logik fehlgeleitet.
  for i in range(n):
    if labels[i] != "main":
      continue
    if energies[i] >= high_threshold and energies[i] > 0.0:
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

def _calculate_rms_and_phrase_boundaries(
  y: np.ndarray,
  sr: int,
  bpm: float,
  duration: float,
  phrase_unit: int,
  anchor: float = 0.0,
  seconds_per_bar: float | None = None,
  feature_cache=None,
) -> list[float]:
  """
  Echtes, dummyloses Fallback-System fuer Strukturgrenzen basierend auf RMS-Energieverlauf
  und musikalischem BPM-Taktgitter (Phrase-Einheiten).
  """
  bar_length = seconds_per_bar or ((60.0 / bpm) * METER)
  
  # Standard-Phrasen-Laengen in Sekunden (z. B. 16 Bars)
  intro_len_sec = bar_length * phrase_unit * 2.0
  outro_len_sec = bar_length * phrase_unit * 2.0
  
  try:
    # 1. RMS-Pegel ueber Zeit extrahieren
    if feature_cache is not None:
      rms = feature_cache.get_rms(hop_length=HOP_LENGTH)[0]
    else:
      rms = librosa.feature.rms(y=y, hop_length=HOP_LENGTH)[0]
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=HOP_LENGTH)
    
    mean_rms = np.mean(rms)
    # Erster Punkt mit >40% RMS-Durchschnitt (Beat-Einstieg)
    intro_idx = np.where(rms > mean_rms * 0.40)[0]
    # Letzter Punkt mit >40% RMS-Durchschnitt (Outro-Start)
    outro_idx = np.where(rms > mean_rms * 0.40)[0]
    
    rms_intro_end = times[intro_idx[0]] if intro_idx.size > 0 else intro_len_sec
    rms_outro_start = times[outro_idx[-1]] if outro_idx.size > 0 else (duration - outro_len_sec)
    
    # Plausibilitaetssicherung
    if rms_intro_end > duration * 0.35:
      rms_intro_end = intro_len_sec
    if rms_outro_start < duration * 0.65:
      rms_outro_start = duration - outro_len_sec
      
    boundaries = [0.0, rms_intro_end, rms_outro_start]
    logger.info(f"Struktur-Fallback: RMS-basierte Grenzen gefunden (intro={rms_intro_end:.2f}s, outro={rms_outro_start:.2f}s)")
    
  except Exception as rms_err:
    logger.warning(f"Fallback-RMS-Analyse fehlgeschlagen: {rms_err}")
    # Musiktheoretisches BPM-Taktgitter-Fallback (kein starrer Dummy!)
    intro_time = min(intro_len_sec, duration * 0.25)
    outro_time = max(duration - outro_len_sec, duration * 0.75)
    boundaries = [0.0, intro_time, outro_time]

  # Quantisiere die Grenzen auf das Phrasengitter
  return _quantize_to_bars(
    boundaries,
    bpm,
    duration,
    phrase_unit,
    anchor,
    seconds_per_bar=bar_length,
    whole_phrase=True,
  )


# === Main Analysis Function ===

def analyze_structure(
  y: np.ndarray,
  sr: int,
  bpm: float,
  genre: str = "Unknown",
  anchor: float = 0.0,
  phrase_unit: int | None = None,
  seconds_per_bar: float | None = None,
  feature_cache=None,
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
  # MED-Fix: sr vor get_duration pruefen — librosa.get_duration rechnet
  # n_samples/sr und wuerfe bei sr<=0 einen ungefangenen ZeroDivisionError, der
  # im Non-Rekordbox-Volllauf die komplette Track-Auswertung reisst.
  if sr is None or sr <= 0:
    return TrackStructure()
  duration = librosa.get_duration(y=y, sr=sr)
  if duration <= 0 or bpm <= 0:
    return TrackStructure()

  # Determine phrase unit before any boundary work so all downstream users
  # share one explicit phrase definition.
  genre_phrase_unit = GENRE_PHRASE_UNITS.get(genre, 8)
  phrase_unit_was_explicit = phrase_unit is not None
  phrase_unit = phrase_unit or genre_phrase_unit

  bar_length = seconds_per_bar or ((60.0 / bpm) * METER)
  total_bars = int(duration / bar_length)

  try:
    # Step 1: Compute novelty curve
    novelty, times = _compute_novelty_curve(
      y, sr, feature_cache=feature_cache
    )

    # Die Messung darf den expliziten API-Wert nie ueberschreiben. Ohne
    # Messwert bleibt exakt der bisherige Genre-Prior erhalten.
    if not phrase_unit_was_explicit:
      measured_phrase_unit = _estimate_phrase_unit_from_novelty(
        novelty,
        times,
        bpm,
        genre=genre,
        anchor=anchor,
      )
      if measured_phrase_unit is not None:
        phrase_unit = measured_phrase_unit

    # Step 2: Pick section boundaries
    boundaries = _pick_boundaries(
      novelty, times, duration,
      min_distance_sec=max(MIN_SECTION_DURATION, bar_length * phrase_unit),
    )

    # Step 3: Auf das gemeinsame Ganze-Phrasen-Gitter quantisieren.
    boundaries = _quantize_to_bars(
      boundaries,
      bpm,
      duration,
      phrase_unit,
      anchor,
      seconds_per_bar=bar_length,
      whole_phrase=True,
    )

    # Ensure we have at least intro + main + outro
    if len(boundaries) < 2:
      boundaries = _calculate_rms_and_phrase_boundaries(
        y, sr, bpm, duration, phrase_unit, anchor,
        seconds_per_bar=bar_length,
        feature_cache=feature_cache,
      )

  except Exception as e:
    logger.warning(f"Novelty-Analyse fehlgeschlagen: {e}")
    boundaries = _calculate_rms_and_phrase_boundaries(
      y, sr, bpm, duration, phrase_unit, anchor,
      seconds_per_bar=bar_length,
      feature_cache=feature_cache,
    )

  # Step 4: Compute energy and trend for each section
  # Audit-Fix 2026-07-21: Grenzen, die (nach Quantisierung/Clamp) auf oder hinter
  # der Track-Dauer liegen, verwerfen — sonst entsteht eine sinnlose 0s-Sektion
  # (start == end == duration) am Ende.
  boundaries = [b for b in boundaries if b < duration - 1e-3]
  if not boundaries:
    boundaries = [0.0]
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
    start_bar = int(round(start / bar_length))
    end_bar = int(round(end / bar_length))

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
