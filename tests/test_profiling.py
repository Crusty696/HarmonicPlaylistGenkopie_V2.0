import pytest
import time
from unittest.mock import patch, MagicMock
from hpg_core.profiling import AnalysisProfiler

class TestAnalysisProfiler:
  def test_start_and_stop(self):
    profiler = AnalysisProfiler()
    profiler.start("test_label")
    assert "test_label" in profiler._starts

    # Mocking time to ensure elapsed time > 0
    time.sleep(0.01)
    profiler.stop("test_label")

    assert "test_label" not in profiler._starts
    assert "test_label" in profiler._timings
    assert profiler._timings["test_label"] > 0

  def test_stop_unknown_label(self):
    profiler = AnalysisProfiler()
    profiler.stop("unknown_label")
    assert "unknown_label" not in profiler._timings

  def test_measure_context_manager(self):
    profiler = AnalysisProfiler()
    with profiler.measure("test_measure"):
      time.sleep(0.01)

    assert "test_measure" not in profiler._starts
    assert "test_measure" in profiler._timings
    assert profiler._timings["test_measure"] > 0

  def test_report(self):
    profiler = AnalysisProfiler()
    profiler._timings = {"test1": 100.0, "test2": 200.0}

    report = profiler.report()
    assert report == {"test1": 100.0, "test2": 200.0}

  def test_report_empty(self):
    profiler = AnalysisProfiler()
    report = profiler.report()
    assert report == {}

  def test_reset(self):
    profiler = AnalysisProfiler()
    profiler.start("test1")
    profiler._timings = {"test2": 200.0}

    profiler.reset()
    assert profiler._starts == {}
    assert profiler._timings == {}
