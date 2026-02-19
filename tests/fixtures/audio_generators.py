"""
Synthetische Audio-Generatoren für deterministische Tests.
Erzeugt Signale mit bekanntem BPM, Key, Energy und Struktur.
"""
import numpy as np


DEFAULT_SR = 22050  # librosa default


def generate_click_track(bpm: float, duration: float, sr: int = DEFAULT_SR) -> np.ndarray:
  """Erzeugt einen Click-Track mit exaktem BPM.

  Jeder Beat ist ein kurzer Impuls (5ms) - ideal für BPM-Detection Tests.

  Args:
    bpm: Beats per minute (z.B. 128.0)
    duration: Dauer in Sekunden
    sr: Sample Rate

  Returns:
    numpy array mit dem Click-Signal
  """
  total_samples = int(duration * sr)
  y = np.zeros(total_samples, dtype=np.float32)

  if bpm <= 0:
    return y

  samples_per_beat = int(60.0 / bpm * sr)
  click_duration = int(0.005 * sr)  # 5ms Click

  pos = 0
  while pos < total_samples:
    end = min(pos + click_duration, total_samples)
    # Kurzer Sinus-Burst bei 1000Hz als Click
    t = np.arange(end - pos) / sr
    y[pos:end] = 0.8 * np.sin(2 * np.pi * 1000 * t)
    pos += samples_per_beat

  return y


def generate_tone(frequency: float, duration: float, sr: int = DEFAULT_SR,
                   amplitude: float = 0.5) -> np.ndarray:
  """Erzeugt einen reinen Sinuston - ideal für Key-Detection Tests.

  Args:
    frequency: Frequenz in Hz (z.B. 440.0 fuer A4)
    duration: Dauer in Sekunden
    sr: Sample Rate
    amplitude: Lautstaerke 0.0-1.0

  Returns:
    numpy array mit dem Ton-Signal
  """
  t = np.arange(int(duration * sr)) / sr
  return (amplitude * np.sin(2 * np.pi * frequency * t)).astype(np.float32)


def generate_silence(duration: float, sr: int = DEFAULT_SR) -> np.ndarray:
  """Erzeugt Stille - fuer Edge-Case Tests."""
  return np.zeros(int(duration * sr), dtype=np.float32)


def generate_noise(duration: float, sr: int = DEFAULT_SR,
                   amplitude: float = 0.3) -> np.ndarray:
  """Erzeugt weisses Rauschen - fuer Energy Tests."""
  rng = np.random.default_rng(42)  # Deterministisch
  samples = int(duration * sr)
  return (amplitude * rng.standard_normal(samples)).astype(np.float32)


def generate_bass_tone(duration: float, sr: int = DEFAULT_SR,
                       frequency: float = 80.0, amplitude: float = 0.7) -> np.ndarray:
  """Erzeugt einen tiefen Bass-Ton fuer Bass-Intensity Tests."""
  return generate_tone(frequency, duration, sr, amplitude)


def generate_track_with_structure(
    bpm: float,
    duration: float,
    sr: int = DEFAULT_SR,
    intro_ratio: float = 0.15,
    outro_ratio: float = 0.85,
    main_amplitude: float = 0.5,
    intro_amplitude: float = 0.05,
    outro_amplitude: float = 0.05,
) -> np.ndarray:
  """Erzeugt ein Audio-Signal mit klar definierten Intro/Main/Outro Abschnitten.

  Ideal fuer Mix-Point Detection Tests. Das Signal hat:
  - Leises Intro (intro_amplitude) bis intro_ratio
  - Lauten Main-Body (main_amplitude) von intro_ratio bis outro_ratio
  - Leises Outro (outro_amplitude) ab outro_ratio

  Beats werden als Click-Impulse ueberlagert.

  Args:
    bpm: Beats per minute
    duration: Gesamtdauer in Sekunden
    sr: Sample Rate
    intro_ratio: Anteil des Intros (0.0-1.0)
    outro_ratio: Start des Outros (0.0-1.0)
    main_amplitude: Lautstaerke des Hauptteils
    intro_amplitude: Lautstaerke des Intros
    outro_amplitude: Lautstaerke des Outros

  Returns:
    numpy array mit strukturiertem Audio
  """
  total_samples = int(duration * sr)
  intro_end = int(intro_ratio * total_samples)
  outro_start = int(outro_ratio * total_samples)

  # Basis-Rauschen mit unterschiedlichen Lautstaerken pro Abschnitt
  rng = np.random.default_rng(42)
  y = np.zeros(total_samples, dtype=np.float32)

  # Intro: leises Rauschen
  y[:intro_end] = intro_amplitude * rng.standard_normal(intro_end).astype(np.float32)

  # Main Body: lautes Rauschen
  main_len = outro_start - intro_end
  y[intro_end:outro_start] = main_amplitude * rng.standard_normal(main_len).astype(np.float32)

  # Outro: leises Rauschen
  outro_len = total_samples - outro_start
  y[outro_start:] = outro_amplitude * rng.standard_normal(outro_len).astype(np.float32)

  # Beats ueberlagern (Click-Track)
  if bpm > 0:
    clicks = generate_click_track(bpm, duration, sr)
    y = y + 0.3 * clicks

  return np.clip(y, -1.0, 1.0)


# Frequenzen der Noten (mittlere Oktave) fuer Key-Detection Tests
NOTE_FREQUENCIES = {
  'C': 261.63,
  'C#': 277.18,
  'D': 293.66,
  'D#': 311.13,
  'E': 329.63,
  'F': 349.23,
  'F#': 369.99,
  'G': 392.00,
  'G#': 415.30,
  'A': 440.00,
  'A#': 466.16,
  'B': 493.88,
}


def generate_major_chord(root_note: str, duration: float = 3.0,
                         sr: int = DEFAULT_SR) -> np.ndarray:
  """Erzeugt einen Dur-Akkord basierend auf dem Grundton.

  Major = Root + Major Third (4 Halbtoene) + Perfect Fifth (7 Halbtoene)
  """
  notes = list(NOTE_FREQUENCIES.keys())
  root_idx = notes.index(root_note)

  root_freq = NOTE_FREQUENCIES[root_note]
  third_freq = NOTE_FREQUENCIES[notes[(root_idx + 4) % 12]]
  fifth_freq = NOTE_FREQUENCIES[notes[(root_idx + 7) % 12]]

  t = np.arange(int(duration * sr)) / sr
  chord = (
    0.4 * np.sin(2 * np.pi * root_freq * t) +
    0.3 * np.sin(2 * np.pi * third_freq * t) +
    0.3 * np.sin(2 * np.pi * fifth_freq * t)
  )
  return chord.astype(np.float32)


def generate_minor_chord(root_note: str, duration: float = 3.0,
                         sr: int = DEFAULT_SR) -> np.ndarray:
  """Erzeugt einen Moll-Akkord basierend auf dem Grundton.

  Minor = Root + Minor Third (3 Halbtoene) + Perfect Fifth (7 Halbtoene)
  """
  notes = list(NOTE_FREQUENCIES.keys())
  root_idx = notes.index(root_note)

  root_freq = NOTE_FREQUENCIES[root_note]
  third_freq = NOTE_FREQUENCIES[notes[(root_idx + 3) % 12]]
  fifth_freq = NOTE_FREQUENCIES[notes[(root_idx + 7) % 12]]

  t = np.arange(int(duration * sr)) / sr
  chord = (
    0.4 * np.sin(2 * np.pi * root_freq * t) +
    0.3 * np.sin(2 * np.pi * third_freq * t) +
    0.3 * np.sin(2 * np.pi * fifth_freq * t)
  )
  return chord.astype(np.float32)
