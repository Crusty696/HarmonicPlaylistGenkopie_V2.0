"""
Profiling-Utilities fuer HPG.

Bietet Dekoratoren und Kontext-Manager fuer Performance-Messung:
- @profile_function: Misst Ausfuehrungszeit einer Funktion
- @profile_memory: Misst Speicherverbrauch (optional, braucht psutil)
- TimerContext: Kontext-Manager fuer Block-Timing

Verwendung:
    from hpg_core.profiling import profile_function, TimerContext

    @profile_function
    def slow_function():
        ...

    with TimerContext("Librosa Load"):
        y, sr = librosa.load(file)
"""

import logging
import time
import functools
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)


def profile_function(func=None, *, threshold_ms: float = 0.0):
  """
  Dekorator: Misst und loggt die Ausfuehrungszeit einer Funktion.

  Args:
      threshold_ms: Nur loggen wenn laenger als X Millisekunden (0 = immer)

  Verwendung:
      @profile_function
      def analyze_track(path): ...

      @profile_function(threshold_ms=100)
      def slow_function(): ...
  """
  def decorator(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
      start = time.perf_counter()
      try:
        result = fn(*args, **kwargs)
        return result
      finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        if elapsed_ms >= threshold_ms:
          logger.info(f"⏱ {fn.__qualname__}: {elapsed_ms:.1f}ms")
    return wrapper

  # Erlaubt @profile_function und @profile_function(threshold_ms=100)
  if func is not None:
    return decorator(func)
  return decorator


@contextmanager
def TimerContext(label: str, log_level: str = "INFO"):
  """
  Kontext-Manager fuer Block-Timing.

  Verwendung:
      with TimerContext("Librosa Load"):
          y, sr = librosa.load(file)

      with TimerContext("Cache Check", log_level="DEBUG"):
          track = get_cached_track(key)
  """
  start = time.perf_counter()
  try:
    yield
  finally:
    elapsed_ms = (time.perf_counter() - start) * 1000
    level = getattr(logging, log_level.upper(), logging.INFO)
    logger.log(level, f"⏱ {label}: {elapsed_ms:.1f}ms")


class AnalysisProfiler:
  """
  Sammelt Timing-Daten fuer die gesamte Analyse-Pipeline.

  Verwendung:
      profiler = AnalysisProfiler()
      profiler.start("bpm_detection")
      # ... BPM erkennen ...
      profiler.stop("bpm_detection")
      profiler.report()
  """

  def __init__(self):
    self._timings = {}
    self._starts = {}

  def start(self, label: str):
    """Startet einen Timer."""
    self._starts[label] = time.perf_counter()

  def stop(self, label: str):
    """Stoppt einen Timer und speichert das Ergebnis."""
    if label in self._starts:
      elapsed = (time.perf_counter() - self._starts[label]) * 1000
      self._timings[label] = elapsed
      del self._starts[label]

  @contextmanager
  def measure(self, label: str):
    """Kontext-Manager fuer Inline-Messung."""
    self.start(label)
    try:
      yield
    finally:
      self.stop(label)

  def report(self) -> dict:
    """
    Gibt alle gesammelten Timings als Dict zurueck und loggt sie.

    Returns:
        Dict mit {label: ms}
    """
    if not self._timings:
      logger.info("Profiler: Keine Messungen vorhanden")
      return {}

    total = sum(self._timings.values())
    logger.info(f"=== Analyse-Profil (Gesamt: {total:.1f}ms) ===")
    for label, ms in sorted(self._timings.items(), key=lambda x: -x[1]):
      pct = (ms / total * 100) if total > 0 else 0
      logger.info(f"  {label:30s} {ms:8.1f}ms ({pct:5.1f}%)")
    return dict(self._timings)

  def reset(self):
    """Setzt alle Messungen zurueck."""
    self._timings.clear()
    self._starts.clear()


def get_memory_usage_mb() -> Optional[float]:
  """
  Gibt den aktuellen Speicherverbrauch in MB zurueck.
  Braucht psutil (optional).

  Returns:
      Speicherverbrauch in MB oder None wenn psutil nicht verfuegbar
  """
  try:
    import psutil
    process = psutil.Process()
    return process.memory_info().rss / (1024 * 1024)
  except ImportError:
    return None


@contextmanager
def track_memory(label: str):
  """
  Kontext-Manager: Misst Speicherverbrauch eines Code-Blocks.
  Braucht psutil (optional, loggt Warnung wenn nicht installiert).

  Verwendung:
      with track_memory("Librosa Load"):
          y, sr = librosa.load(file)
  """
  before = get_memory_usage_mb()
  if before is None:
    logger.debug(f"Speicher-Tracking fuer '{label}' nicht moeglich (psutil fehlt)")
    yield
    return

  try:
    yield
  finally:
    after = get_memory_usage_mb()
    if after is not None:
      diff = after - before
      logger.info(f"💾 {label}: {diff:+.1f}MB (vorher: {before:.0f}MB, nachher: {after:.0f}MB)")
