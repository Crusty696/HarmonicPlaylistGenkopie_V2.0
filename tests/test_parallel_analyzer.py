"""
Tests fuer ParallelAnalyzer - Multi-core Audio-Analyse.
Prueft Worker-Count, parallele Verarbeitung, Error-Handling.
"""
import os
import pytest
import tempfile
import numpy as np
import multiprocessing as mp
from unittest.mock import MagicMock
from hpg_core.parallel_analyzer import (
  ParallelAnalyzer,
  get_optimal_worker_count,
  _analyze_track_wrapper,
)
from hpg_core.models import Track


# ============================================================
# Hilfsfunktionen
# ============================================================

def _create_minimal_wav(path: str, duration: float = 3.0, sr: int = 22050):
  """Erstellt eine minimale WAV-Datei."""
  import wave

  n_samples = int(duration * sr)
  t = np.linspace(0, duration, n_samples, endpoint=False)
  signal = (np.sin(2 * np.pi * 440 * t) * 32767 * 0.3).astype(np.int16)

  with wave.open(path, "w") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(sr)
    wav.writeframes(signal.tobytes())


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def wav_files():
  """Erstellt 3 minimale WAV-Dateien fuer Parallel-Tests."""
  paths = []
  for i in range(3):
    path = tempfile.mktemp(suffix=f"_test_{i}.wav")
    _create_minimal_wav(path, duration=3.0)
    paths.append(path)
  yield paths
  for p in paths:
    if os.path.exists(p):
      os.unlink(p)


@pytest.fixture
def single_wav():
  """Einzelne WAV-Datei."""
  path = tempfile.mktemp(suffix="_single.wav")
  _create_minimal_wav(path, duration=3.0)
  yield path
  if os.path.exists(path):
    os.unlink(path)


# ============================================================
# get_optimal_worker_count Tests
# ============================================================

class TestOptimalWorkerCount:
  """Worker-Count Berechnung."""

  def test_returns_positive_integer(self):
    """Gibt positive Ganzzahl zurueck."""
    count = get_optimal_worker_count()
    assert isinstance(count, int)
    assert count > 0

  def test_does_not_exceed_cpu_count(self):
    """Ueberschreitet nicht die CPU-Anzahl."""
    count = get_optimal_worker_count()
    assert count <= mp.cpu_count()

  def test_small_file_count(self):
    """Wenige Dateien = weniger Workers."""
    count_small = get_optimal_worker_count(file_count=3)
    assert count_small == 1, "< 5 Dateien sollte 1 Worker nutzen"

  def test_very_small_file_count(self):
    """Einzelne Datei = 1 Worker."""
    count = get_optimal_worker_count(file_count=1)
    assert count == 1

  def test_medium_file_count(self):
    """Mittlere Dateianzahl = mittlere Worker-Anzahl."""
    count = get_optimal_worker_count(file_count=8)
    assert count == 2, "8 Dateien (< 10) = 2 Worker"

  def test_large_file_count(self):
    """Viele Dateien = mehr Workers."""
    count_large = get_optimal_worker_count(file_count=50)
    assert count_large >= 2

  def test_none_file_count(self):
    """None File-Count = Auto-Detect."""
    count = get_optimal_worker_count(file_count=None)
    assert count > 0

  def test_scaling_logic(self):
    """Workers skalieren mit Dateianzahl."""
    count_5 = get_optimal_worker_count(file_count=5)
    count_50 = get_optimal_worker_count(file_count=50)
    # Mehr Dateien sollten mindestens gleich viele Workers haben
    assert count_50 >= count_5


# ============================================================
# ParallelAnalyzer Init Tests
# ============================================================

class TestParallelAnalyzerInit:
  """ParallelAnalyzer Initialisierung."""

  def test_default_init(self):
    """Default Initialisierung ohne Parameter."""
    analyzer = ParallelAnalyzer()
    assert analyzer.max_workers > 0
    assert analyzer.max_workers <= mp.cpu_count()

  def test_custom_workers(self):
    """Benutzerdefinierte Worker-Anzahl."""
    analyzer = ParallelAnalyzer(max_workers=2)
    assert analyzer.max_workers == 2

  def test_max_workers_capped_at_cpu(self):
    """Workers werden auf CPU-Anzahl begrenzt."""
    analyzer = ParallelAnalyzer(max_workers=999)
    assert analyzer.max_workers <= mp.cpu_count()

  def test_single_worker(self):
    """Einzelner Worker funktioniert."""
    analyzer = ParallelAnalyzer(max_workers=1)
    assert analyzer.max_workers == 1


# ============================================================
# analyze_files Tests
# ============================================================

@pytest.mark.integration
class TestAnalyzeFiles:
  """ParallelAnalyzer.analyze_files() Tests."""

  def test_empty_list_returns_empty(self):
    """Leere Dateiliste = leere Ergebnisliste."""
    analyzer = ParallelAnalyzer(max_workers=1)
    result = analyzer.analyze_files([])
    assert result == []

  def test_single_file(self, single_wav):
    """Einzelne Datei wird korrekt analysiert."""
    analyzer = ParallelAnalyzer(max_workers=1)
    result = analyzer.analyze_files([single_wav])
    assert len(result) == 1
    assert isinstance(result[0], Track)

  def test_single_file_has_fields(self, single_wav):
    """Analysierter Track hat alle Felder."""
    analyzer = ParallelAnalyzer(max_workers=1)
    result = analyzer.analyze_files([single_wav])
    track = result[0]
    assert track.filePath == single_wav
    assert track.bpm > 0
    assert track.duration > 0

  def test_multiple_files(self, wav_files):
    """Mehrere Dateien werden parallel analysiert."""
    analyzer = ParallelAnalyzer(max_workers=2)
    result = analyzer.analyze_files(wav_files)
    assert len(result) == len(wav_files)
    for track in result:
      assert isinstance(track, Track)
      assert track.bpm > 0

  def test_progress_callback(self, single_wav):
    """Progress-Callback wird aufgerufen."""
    analyzer = ParallelAnalyzer(max_workers=1)
    callback_calls = []

    def progress_cb(current, total, msg):
      callback_calls.append((current, total, msg))

    analyzer.analyze_files([single_wav], progress_callback=progress_cb)
    assert len(callback_calls) >= 1

  def test_progress_callback_has_total(self, wav_files):
    """Progress-Callback erhaelt korrekte Gesamtanzahl."""
    analyzer = ParallelAnalyzer(max_workers=1)
    totals = []

    def progress_cb(current, total, msg):
      totals.append(total)

    analyzer.analyze_files(wav_files, progress_callback=progress_cb)
    # Alle Callbacks sollten gleiche Gesamtanzahl haben
    if totals:
      assert all(t == len(wav_files) for t in totals)

  def test_nonexistent_file_filtered(self, single_wav):
    """Nicht-existente Dateien werden gefiltert."""
    analyzer = ParallelAnalyzer(max_workers=1)
    files = [single_wav, "/nonexistent/fake.mp3"]
    result = analyzer.analyze_files(files)
    # Nur die gueltige Datei sollte erfolgreich sein
    assert len(result) >= 1
    assert any(t.filePath == single_wav for t in result)


# ============================================================
# _analyze_track_wrapper Tests
# ============================================================

@pytest.mark.integration
class TestAnalyzeTrackWrapper:
  """Wrapper-Funktion fuer Multiprocessing."""

  def test_valid_file_returns_track(self, single_wav):
    """Valide Datei gibt Track zurueck."""
    result = _analyze_track_wrapper(single_wav)
    assert isinstance(result, Track)

  def test_invalid_file_returns_none(self):
    """Ungueltige Datei gibt None zurueck."""
    result = _analyze_track_wrapper("/nonexistent/fake.mp3")
    assert result is None

  def test_wrapper_catches_exceptions(self):
    """Wrapper faengt Exceptions ab."""
    # Sollte nicht crashen, sondern None zurueckgeben
    result = _analyze_track_wrapper("")
    assert result is None


# ============================================================
# Error Handling
# ============================================================

@pytest.mark.integration
class TestParallelAnalyzerErrorHandling:
  """Error-Handling in ParallelAnalyzer."""

  def test_mixed_valid_invalid(self, single_wav):
    """Mix aus validen und invaliden Dateien."""
    analyzer = ParallelAnalyzer(max_workers=1)
    files = [
      single_wav,
      "/fake/path1.mp3",
      "/fake/path2.wav",
    ]
    result = analyzer.analyze_files(files)
    # Mindestens die valide Datei sollte durchkommen
    assert len(result) >= 1

  def test_all_invalid_returns_empty(self):
    """Nur invalide Dateien = leere Liste."""
    analyzer = ParallelAnalyzer(max_workers=1)
    files = ["/fake1.mp3", "/fake2.wav", "/fake3.flac"]
    result = analyzer.analyze_files(files)
    assert result == []

  def test_corrupted_file_handled(self):
    """Korrupte Datei wird behandelt (kein Crash)."""
    # Erstelle eine Datei die keine gueltige Audio ist
    path = tempfile.mktemp(suffix=".wav")
    with open(path, "wb") as f:
      f.write(b"This is not a valid WAV file" * 10)

    try:
      analyzer = ParallelAnalyzer(max_workers=1)
      result = analyzer.analyze_files([path])
      # Sollte leer sein oder Track mit Defaults haben
      # Hauptsache kein Crash
      assert isinstance(result, list)
    finally:
      if os.path.exists(path):
        os.unlink(path)
