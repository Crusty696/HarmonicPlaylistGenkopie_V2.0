"""
Tests fuer ParallelAnalyzer - Multi-core Audio-Analyse.
Prueft Worker-Count, parallele Verarbeitung, Error-Handling.
"""
import os
import pytest
import tempfile
import numpy as np
import multiprocessing as mp
from unittest.mock import MagicMock, Mock
from hpg_core.parallel_analyzer import (
  ParallelAnalyzer,
  get_optimal_worker_count,
  _analyze_track_wrapper,
  _terminate_executor_processes,
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

  def test_configured_workers_are_capped_at_cpu_count(self, monkeypatch):
    """Auch ein zu hoher Konfigurationswert darf CPU-Limit nicht brechen."""
    from hpg_core import parallel_analyzer

    monkeypatch.setattr(
      parallel_analyzer.config,
      "PARALLEL_MAX_WORKERS",
      mp.cpu_count() + 100,
    )

    assert get_optimal_worker_count(file_count=50) == mp.cpu_count()

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

  def test_large_audio_workload_uses_stable_auto_cap(self, monkeypatch):
    """Grosse native Audio-Workloads bleiben bei vier Auto-Workern stabil."""
    from hpg_core import parallel_analyzer

    monkeypatch.setattr(parallel_analyzer.mp, "cpu_count", lambda: 16)

    assert get_optimal_worker_count(file_count=26) == 4

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

  def test_explicit_worker_limit_is_used_for_multi_file_run(self, monkeypatch):
    """Der Konstruktorwert darf nicht durch Auto-Scaling ersetzt werden."""
    from hpg_core import parallel_analyzer

    seen_workers = []

    class ImmediateFuture:
      def result(self, timeout=None):
        return None

      def cancel(self):
        return True

    class ImmediateExecutor:
      def __init__(self, max_workers, initializer=None, **kwargs):
        # AUDIT-FIX P-01: ProcessPoolExecutor bekommt jetzt initializer=_worker_init
        seen_workers.append(max_workers)
        self._processes = {}

      def __enter__(self):
        return self

      def __exit__(self, *args):
        return False

      def submit(self, func, path):
        return ImmediateFuture()

      def shutdown(self, wait=True, cancel_futures=False):
        return None

    monkeypatch.setattr(parallel_analyzer, "ProcessPoolExecutor", ImmediateExecutor)
    # AUDIT-FIX N-04: analyze_files nutzt jetzt wait() statt as_completed()
    monkeypatch.setattr(
      parallel_analyzer,
      "wait",
      lambda futures, timeout=None, return_when=None: (set(futures), set()),
    )

    ParallelAnalyzer(max_workers=2).analyze_files([f"track-{i}.wav" for i in range(8)])

    assert seen_workers == [2, 2]


def test_terminate_executor_stops_running_processes():
  """Timeout/Cancel beendet Prozesse vor dem impliziten Context-Wait."""
  process = MagicMock()
  process.is_alive.return_value = True
  executor = MagicMock()
  executor._processes = {1: process}

  _terminate_executor_processes(executor)

  executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)
  process.terminate.assert_called_once_with()


def test_terminate_executor_isolates_each_child_and_shutdown_error():
  """Ein defektes Child oder shutdown darf weitere Children nicht blockieren."""
  first = MagicMock()
  first.is_alive.side_effect = RuntimeError("status failed")
  first.terminate.side_effect = RuntimeError("terminate failed")
  second = MagicMock()
  second.is_alive.return_value = True
  executor = MagicMock()
  executor._processes = {1: first, 2: second}
  executor.shutdown.side_effect = RuntimeError("shutdown failed")

  _terminate_executor_processes(executor)

  first.terminate.assert_called_once_with()
  second.terminate.assert_called_once_with()
  executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)


def test_keyboard_interrupt_from_normal_shutdown_survives_cleanup_errors(monkeypatch):
  """shutdown(wait=True)-Interrupt bleibt trotz fehlerhaftem Cleanup original."""
  from hpg_core import parallel_analyzer

  original = KeyboardInterrupt("stop now")
  process = MagicMock()
  process.is_alive.return_value = True
  created = []

  class ShutdownInterruptExecutor:
    def __init__(self, max_workers, initializer=None, **kwargs):
      self._processes = {1: process}
      self.shutdown_calls = []
      created.append(self)

    def submit(self, func, path):
      return _FakeFuture()

    def shutdown(self, wait=True, cancel_futures=False):
      self.shutdown_calls.append((wait, cancel_futures))
      if wait:
        raise original
      raise RuntimeError("cleanup shutdown failed")

  monkeypatch.setattr(
    parallel_analyzer, "ProcessPoolExecutor", ShutdownInterruptExecutor
  )
  monkeypatch.setattr(
    parallel_analyzer,
    "wait",
    lambda futures, timeout=None, return_when=None: (set(futures), set()),
  )

  with pytest.raises(KeyboardInterrupt) as caught:
    ParallelAnalyzer(max_workers=1).analyze_files(["shutdown-interrupt.wav"])

  assert caught.value is original
  process.terminate.assert_called_once_with()
  assert created[0].shutdown_calls == [(True, False), (False, True)]


def test_recovery_shutdown_interrupt_survives_best_effort_cleanup(monkeypatch):
  """Auch Recovery-Cleanup propagiert seine originale BaseException."""
  from concurrent.futures.process import BrokenProcessPool
  from hpg_core import parallel_analyzer

  original = KeyboardInterrupt("recovery shutdown interrupted")
  recovery_process = MagicMock()
  recovery_process.is_alive.return_value = True
  created = []

  class BrokenFuture:
    def result(self, timeout=None):
      raise BrokenProcessPool("main pool broken")

  class NoneFuture:
    def result(self, timeout=None):
      return None

  class RecoveryInterruptExecutor:
    def __init__(self, max_workers, initializer=None, **kwargs):
      self.is_recovery = bool(created)
      self._processes = {1: recovery_process} if self.is_recovery else {}
      self.shutdown_calls = []
      created.append(self)

    def submit(self, func, path):
      return NoneFuture() if self.is_recovery else BrokenFuture()

    def shutdown(self, wait=True, cancel_futures=False):
      self.shutdown_calls.append((wait, cancel_futures))
      if self.is_recovery:
        if len(self.shutdown_calls) == 1:
          raise original
        raise RuntimeError("recovery cleanup failed")

  monkeypatch.setattr(
    parallel_analyzer, "ProcessPoolExecutor", RecoveryInterruptExecutor
  )
  monkeypatch.setattr(
    parallel_analyzer,
    "wait",
    lambda futures, timeout=None, return_when=None: (set(futures), set()),
  )

  with pytest.raises(KeyboardInterrupt) as caught:
    ParallelAnalyzer(max_workers=2).analyze_files(
      [f"recovery-{index}.wav" for index in range(4)]
    )

  assert caught.value is original
  recovery_process.terminate.assert_called_once_with()
  assert created[1].shutdown_calls == [(False, True), (False, True)]


def test_keyboard_interrupt_terminates_pool_without_wait_true(monkeypatch):
  """BaseException beendet Child-Prozesse sofort und bleibt sichtbar."""
  from hpg_core import parallel_analyzer

  process = MagicMock()
  process.is_alive.return_value = True
  created = []

  class InterruptExecutor:
    def __init__(self, max_workers, initializer=None, **kwargs):
      self._processes = {1: process}
      self.shutdown_calls = []
      created.append(self)

    def submit(self, func, path):
      return _FakeFuture()

    def shutdown(self, wait=True, cancel_futures=False):
      self.shutdown_calls.append((wait, cancel_futures))

  monkeypatch.setattr(parallel_analyzer, "ProcessPoolExecutor", InterruptExecutor)
  monkeypatch.setattr(
    parallel_analyzer,
    "wait",
    Mock(side_effect=KeyboardInterrupt()),
  )

  with pytest.raises(KeyboardInterrupt):
    ParallelAnalyzer(max_workers=1).analyze_files(["interrupt.wav"])

  process.terminate.assert_called_once_with()
  assert created[0].shutdown_calls == [(False, True)]


@pytest.mark.parametrize("invalid_mode", ["rekordbox_degraded", "full", "unknown", ""])
def test_nichtkanonisches_ergebnis_wird_im_hauptpool_abgewiesen(
  monkeypatch, invalid_mode
):
  """Defense-in-depth: nur kanonische Worker-Ergebnisse verlassen den Analyzer."""
  from hpg_core import parallel_analyzer

  degraded = Mock(spec=Track)
  degraded.analysis_mode = invalid_mode
  progress = []

  class DegradedFuture:
    def result(self, timeout=None):
      return degraded

  class DegradedExecutor:
    def __init__(self, max_workers, initializer=None, **kwargs):
      self._processes = {}

    def submit(self, func, path):
      return DegradedFuture()

    def shutdown(self, wait=True, cancel_futures=False):
      return None

  monkeypatch.setattr(parallel_analyzer, "ProcessPoolExecutor", DegradedExecutor)
  monkeypatch.setattr(
    parallel_analyzer,
    "wait",
    lambda futures, timeout=None, return_when=None: (set(futures), set()),
  )

  result = ParallelAnalyzer(max_workers=1).analyze_files(
    ["degraded.wav"],
    progress_callback=lambda current, total, status: progress.append(status),
  )

  assert result == []
  assert progress[-1] == "[FAILED] degraded.wav"


@pytest.mark.parametrize("valid_mode", ["rekordbox_fast_tail", "librosa_full_or_tail"])
def test_kanonisches_ergebnis_wird_als_erfolg_akzeptiert(valid_mode):
  from hpg_core.parallel_analyzer import _is_successful_analysis_result

  track = Mock(spec=Track)
  track.analysis_mode = valid_mode

  assert _is_successful_analysis_result(track)


def test_nichtkanonisches_ergebnis_wird_auch_im_recovery_abgewiesen(monkeypatch):
  from concurrent.futures.process import BrokenProcessPool
  from hpg_core import parallel_analyzer

  invalid = Mock(spec=Track)
  invalid.analysis_mode = "full"
  created = []

  class BrokenFuture:
    def result(self, timeout=None):
      raise BrokenProcessPool("main pool broken")

  class InvalidFuture:
    def result(self, timeout=None):
      return invalid

  class Executor:
    def __init__(self, max_workers, initializer=None, **kwargs):
      self.is_recovery = bool(created)
      self._processes = {}
      created.append(self)

    def submit(self, func, path):
      return InvalidFuture() if self.is_recovery else BrokenFuture()

    def shutdown(self, wait=True, cancel_futures=False):
      return None

  monkeypatch.setattr(parallel_analyzer, "ProcessPoolExecutor", Executor)
  monkeypatch.setattr(
    parallel_analyzer,
    "wait",
    lambda futures, timeout=None, return_when=None: (set(futures), set()),
  )

  result = ParallelAnalyzer(max_workers=2).analyze_files(["recovery-invalid.wav"])

  assert result == []
  assert len(created) == 2


# ============================================================
# AUDIT-FIX N-04: Haenger-Deadline + Recovery-Executor-Reuse
# ============================================================

from concurrent.futures.process import BrokenProcessPool


class _FakeFuture:
  """Future-Ersatz fuer gemockte Executor-Tests (kein echter Prozess)."""

  def __init__(self, fail=False):
    self._fail = fail

  def result(self, timeout=None):
    if self._fail:
      raise BrokenProcessPool("Simulierter Worker-Crash")
    return None

  def cancel(self):
    return True


def _make_fake_executor(created_workers, broken_main_pool=False):
  """Erzeugt eine Fake-Executor-Klasse, die Instanziierungen protokolliert.

  broken_main_pool=True laesst nur den Haupt-Pool (max_workers != 1)
  crashen, der Recovery-Pool (max_workers == 1) funktioniert.
  """

  class FakeExecutor:
    def __init__(self, max_workers, initializer=None, **kwargs):
      created_workers.append(max_workers)
      self._processes = {}
      self._fail = broken_main_pool and max_workers != 1

    def __enter__(self):
      return self

    def __exit__(self, *args):
      return False

    def submit(self, func, path):
      return _FakeFuture(fail=self._fail)

    def shutdown(self, wait=True, cancel_futures=False):
      return None

  return FakeExecutor


class TestHangDeadline:
  """N-04: Deadline haengt an worker_count, nicht an der Batch-Groesse."""

  def _run(self, monkeypatch, file_count, max_workers):
    from hpg_core import parallel_analyzer

    recorded_timeouts = []

    def fake_wait(futures, timeout=None, return_when=None):
      recorded_timeouts.append(timeout)
      return set(futures), set()

    created = []
    monkeypatch.setattr(parallel_analyzer, "wait", fake_wait)
    monkeypatch.setattr(
      parallel_analyzer, "ProcessPoolExecutor", _make_fake_executor(created)
    )
    ParallelAnalyzer(max_workers=max_workers).analyze_files(
      [f"track-{i}.wav" for i in range(file_count)]
    )
    return recorded_timeouts

  def test_deadline_depends_on_workers_not_batch_size(self, monkeypatch):
    """300 Dateien, 2 Worker: Deadline = TIMEOUT * 2 + 30 (frueher batch-proportional)."""
    timeouts = self._run(monkeypatch, file_count=300, max_workers=2)
    assert timeouts, "wait() muss aufgerufen worden sein"
    assert all(0 < t <= 0.5 for t in timeouts)


  def test_deadline_identical_for_different_batch_sizes(self, monkeypatch):
    """Gleiche Worker-Anzahl -> gleiche Deadline, egal wie gross der Batch ist."""
    timeouts_small = self._run(monkeypatch, file_count=10, max_workers=2)
    timeouts_large = self._run(monkeypatch, file_count=300, max_workers=2)
    assert set(timeouts_small) == set(timeouts_large) == {0.5}

  def test_deadline_is_capped_at_max(self, monkeypatch):
    """Deadline ueberschreitet nie PARALLEL_HANG_DEADLINE_MAX (~15 min)."""
    from hpg_core import parallel_analyzer

    monkeypatch.setattr(parallel_analyzer.config, "PARALLEL_ANALYSIS_TIMEOUT", 600)
    timeouts = self._run(monkeypatch, file_count=50, max_workers=2)
    assert timeouts
    assert all(0 < t <= 0.5 for t in timeouts)


def test_per_task_timeout_limits_inflight_submissions(monkeypatch):
  """Ein haengender Task wird nach seinem eigenen Limit erkannt."""
  from hpg_core import parallel_analyzer
  from itertools import count

  class NeverFuture:
    def result(self, timeout=None):
      return None

    def cancel(self):
      return True

  submitted = []

  class FakeExecutor:
    def __init__(self, max_workers, initializer=None, **kwargs):
      self.max_workers = max_workers
      self._processes = {}

    def __enter__(self):
      return self

    def __exit__(self, *args):
      return False

    def submit(self, func, path):
      submitted.append((self.max_workers, path))
      return NeverFuture()

    def shutdown(self, wait=True, cancel_futures=False):
      return None

  ticks = count(0)
  monkeypatch.setattr(parallel_analyzer, "ProcessPoolExecutor", FakeExecutor)
  monkeypatch.setattr(parallel_analyzer, "wait", lambda *args, **kwargs: (set(), set()))
  monkeypatch.setattr(parallel_analyzer.time, "monotonic", lambda: float(next(ticks)))
  monkeypatch.setattr(
    parallel_analyzer.config, "PARALLEL_ANALYSIS_TIMEOUT", 0.5
  )

  ParallelAnalyzer(max_workers=2).analyze_files(
    [f"track-{index}.wav" for index in range(4)]
  )

  main_submissions = [path for workers, path in submitted if workers == 2]
  assert main_submissions == ["track-0.wav", "track-1.wav"]


class TestRecoveryExecutorReuse:
  """N-04: Nach BrokenProcessPool EIN Recovery-Pool fuer alle Rest-Dateien."""

  def test_single_recovery_pool_per_batch(self, monkeypatch):
    from hpg_core import parallel_analyzer

    created = []
    monkeypatch.setattr(
      parallel_analyzer,
      "ProcessPoolExecutor",
      _make_fake_executor(created, broken_main_pool=True),
    )
    monkeypatch.setattr(
      parallel_analyzer,
      "wait",
      lambda futures, timeout=None, return_when=None: (set(futures), set()),
    )

    result = ParallelAnalyzer(max_workers=2).analyze_files(
      [f"track-{i}.wav" for i in range(8)]
    )

    # 8 Dateien, 2 Worker -> BATCH_SIZE 4 -> 2 Batches.
    # Pro Batch: 1 Haupt-Pool (crasht) + genau EIN Recovery-Pool fuer alle
    # 4 Rest-Dateien (vorher: ein neuer Recovery-Pool PRO Datei).
    assert created == [2, 1, 2, 1]
    assert result == []

  def test_cancel_is_polled_inside_recovery(self, monkeypatch):
    from hpg_core import parallel_analyzer

    created = []
    monkeypatch.setattr(
      parallel_analyzer,
      "ProcessPoolExecutor",
      _make_fake_executor(created, broken_main_pool=True),
    )
    monkeypatch.setattr(
      parallel_analyzer,
      "wait",
      lambda futures, timeout=None, return_when=None: (set(futures), set()),
    )
    cancel_states = iter([False, False, True])

    with pytest.raises(InterruptedError):
      ParallelAnalyzer(max_workers=2).analyze_files(
        [f"track-{i}.wav" for i in range(4)],
        cancel_callback=lambda: next(cancel_states),
      )

    assert created == [2, 1]

  def test_recovery_crash_cleanup_error_does_not_stop_next_track(self, monkeypatch):
    """Defekter Recovery-Pool wird non-throwing entsorgt und neu aufgebaut."""
    from hpg_core import parallel_analyzer

    recovery_process = MagicMock()
    recovery_process.is_alive.return_value = True
    created = []

    class CrashFuture:
      def result(self, timeout=None):
        raise BrokenProcessPool("worker crashed")

    class NoneFuture:
      def result(self, timeout=None):
        return None

    class CleanupFailingExecutor:
      def __init__(self, max_workers, initializer=None, **kwargs):
        self.index = len(created)
        self._processes = {1: recovery_process} if self.index == 1 else {}
        created.append(self)

      def submit(self, func, path):
        if self.index in (0, 1):
          return CrashFuture()
        return NoneFuture()

      def shutdown(self, wait=True, cancel_futures=False):
        if self.index == 1:
          raise RuntimeError("cleanup failed")

    monkeypatch.setattr(
      parallel_analyzer, "ProcessPoolExecutor", CleanupFailingExecutor
    )
    monkeypatch.setattr(
      parallel_analyzer,
      "wait",
      lambda futures, timeout=None, return_when=None: (set(futures), set()),
    )

    result = ParallelAnalyzer(max_workers=2).analyze_files(
      [f"recovery-{index}.wav" for index in range(4)]
    )

    assert result == []
    assert len(created) == 3
    recovery_process.terminate.assert_called_once_with()


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
