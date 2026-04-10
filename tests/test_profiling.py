import pytest
import time
import logging
from unittest.mock import patch

from hpg_core.profiling import (
    profile_function,
    TimerContext,
    AnalysisProfiler,
    get_memory_usage_mb,
    track_memory,
)

def test_profile_function_without_args(caplog):
    caplog.set_level(logging.INFO)

    @profile_function
    def dummy_func():
        return 42

    with patch('hpg_core.profiling.time.perf_counter', side_effect=[0.0, 0.1]):
        result = dummy_func()

    assert result == 42
    assert "dummy_func" in caplog.text
    assert "100.0ms" in caplog.text

def test_profile_function_with_args_below_threshold(caplog):
    caplog.set_level(logging.INFO)

    @profile_function(threshold_ms=150.0)
    def fast_func():
        return 1

    with patch('hpg_core.profiling.time.perf_counter', side_effect=[0.0, 0.1]):
        result = fast_func()

    assert result == 1
    assert "fast_func" not in caplog.text

def test_profile_function_with_args_above_threshold(caplog):
    caplog.set_level(logging.INFO)

    @profile_function(threshold_ms=50.0)
    def slow_func():
        return 2

    with patch('hpg_core.profiling.time.perf_counter', side_effect=[0.0, 0.1]):
        result = slow_func()

    assert result == 2
    assert "slow_func" in caplog.text
    assert "100.0ms" in caplog.text

def test_timer_context(caplog):
    caplog.set_level(logging.INFO)

    with patch('hpg_core.profiling.time.perf_counter', side_effect=[0.0, 0.25]):
        with TimerContext("Test Block"):
            pass

    assert "⏱ Test Block: 250.0ms" in caplog.text

def test_timer_context_custom_level(caplog):
    caplog.set_level(logging.DEBUG)

    with patch('hpg_core.profiling.time.perf_counter', side_effect=[0.0, 0.5]):
        with TimerContext("Debug Block", log_level="DEBUG"):
            pass

    assert "⏱ Debug Block: 500.0ms" in caplog.text

def test_analysis_profiler(caplog):
    caplog.set_level(logging.INFO)
    profiler = AnalysisProfiler()

    with patch('hpg_core.profiling.time.perf_counter', side_effect=[0.0, 0.1, 0.2, 0.4]):
        profiler.start("task1")
        profiler.stop("task1") # takes 100ms

        with profiler.measure("task2"): # takes 200ms
            pass

    report = profiler.report()
    assert report["task1"] == pytest.approx(100.0)
    assert report["task2"] == pytest.approx(200.0)
    assert "Analyse-Profil" in caplog.text
    assert "task1" in caplog.text
    assert "task2" in caplog.text

def test_analysis_profiler_empty(caplog):
    caplog.set_level(logging.INFO)
    profiler = AnalysisProfiler()
    report = profiler.report()
    assert report == {}
    assert "Profiler: Keine Messungen vorhanden" in caplog.text

def test_analysis_profiler_reset():
    profiler = AnalysisProfiler()
    with patch('hpg_core.profiling.time.perf_counter', side_effect=[0.0, 0.1]):
        profiler.start("task1")
        profiler.stop("task1")

    assert "task1" in profiler._timings
    profiler.reset()
    assert profiler._timings == {}
    assert profiler._starts == {}

def test_get_memory_usage_mb():
    # Will work if psutil is installed, otherwise returns None
    mem = get_memory_usage_mb()
    if mem is not None:
        assert isinstance(mem, float)
        assert mem > 0

@patch('hpg_core.profiling.get_memory_usage_mb', side_effect=[100.0, 150.0])
def test_track_memory(mock_mem, caplog):
    caplog.set_level(logging.INFO)
    with track_memory("Memory Intensive Task"):
        pass

    assert "💾 Memory Intensive Task: +50.0MB (vorher: 100MB, nachher: 150MB)" in caplog.text

@patch('hpg_core.profiling.get_memory_usage_mb', return_value=None)
def test_track_memory_no_psutil(mock_mem, caplog):
    caplog.set_level(logging.DEBUG)
    with track_memory("No Psutil Task"):
        pass

    assert "Speicher-Tracking fuer 'No Psutil Task' nicht moeglich (psutil fehlt)" in caplog.text


@patch('hpg_core.profiling.get_memory_usage_mb', return_value=None)
def test_track_memory_after_is_none(mock_mem, caplog):
    caplog.set_level(logging.INFO)

    with patch('hpg_core.profiling.get_memory_usage_mb', side_effect=[100.0, None]):
        with track_memory("Memory Intensive Task (Failed After)"):
            pass

    assert "💾 Memory Intensive Task (Failed After):" not in caplog.text

@patch('builtins.__import__', side_effect=ImportError)
def test_get_memory_usage_mb_import_error(mock_import):
    assert get_memory_usage_mb() is None
