import pytest
import time
import logging
import sys
from unittest.mock import patch, MagicMock

# Mock audio/heavy dependencies if needed, but we try to import directly first
from hpg_core.profiling import (
    profile_function,
    TimerContext,
    AnalysisProfiler,
    get_memory_usage_mb,
    track_memory
)

# Test profile_function decorator

def test_profile_function_no_args(caplog):
    caplog.set_level(logging.INFO)

    @profile_function
    def dummy_func():
        return "result"

    res = dummy_func()
    assert res == "result"

    # Verify logging
    assert any("dummy_func" in record.message for record in caplog.records)
    assert any("ms" in record.message for record in caplog.records)


def test_profile_function_with_args(caplog):
    caplog.set_level(logging.INFO)

    @profile_function(threshold_ms=100.0)
    def fast_func():
        return "fast"

    @profile_function(threshold_ms=0.0)
    def slow_func():
        return "slow"

    fast_func()
    assert not any("fast_func" in record.message for record in caplog.records)

    slow_func()
    assert any("slow_func" in record.message for record in caplog.records)


def test_profile_function_exception(caplog):
    caplog.set_level(logging.INFO)

    @profile_function
    def error_func():
        raise ValueError("test error")

    with pytest.raises(ValueError, match="test error"):
        error_func()

    assert any("error_func" in record.message for record in caplog.records)

# Test TimerContext
def test_timer_context(caplog):
    caplog.set_level(logging.INFO)

    with TimerContext("Test Block"):
        pass

    assert any("Test Block" in record.message for record in caplog.records)

def test_timer_context_custom_level(caplog):
    caplog.set_level(logging.DEBUG)

    with TimerContext("Debug Block", log_level="DEBUG"):
        pass

    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("Debug Block" in record.message for record in debug_records)

# Test AnalysisProfiler
def test_analysis_profiler(caplog):
    caplog.set_level(logging.INFO)
    profiler = AnalysisProfiler()

    profiler.start("step1")
    profiler.stop("step1")

    with profiler.measure("step2"):
        pass

    report = profiler.report()
    assert "step1" in report
    assert "step2" in report
    assert isinstance(report["step1"], float)
    assert isinstance(report["step2"], float)

def test_analysis_profiler_reset():
    profiler = AnalysisProfiler()
    profiler.start("step1")
    profiler.stop("step1")
    assert "step1" in profiler._timings

    profiler.reset()
    assert len(profiler._timings) == 0
    assert len(profiler._starts) == 0

def test_analysis_profiler_empty_report(caplog):
    caplog.set_level(logging.INFO)
    profiler = AnalysisProfiler()
    report = profiler.report()
    assert report == {}
    assert any("Keine Messungen vorhanden" in record.message for record in caplog.records)

# Test memory profiling
def test_get_memory_usage_mb_with_psutil():
    # If psutil is installed, it returns a float, otherwise None
    try:
        import psutil
        has_psutil = True
    except ImportError:
        has_psutil = False

    mem = get_memory_usage_mb()
    if has_psutil:
        assert isinstance(mem, float)
    else:
        assert mem is None

@patch('hpg_core.profiling.get_memory_usage_mb')
def test_track_memory_with_psutil(mock_get_memory, caplog):
    caplog.set_level(logging.INFO)
    mock_get_memory.side_effect = [100.0, 105.0]

    with track_memory("Memory Block"):
        pass

    assert any("Memory Block" in record.message and "+5.0MB" in record.message for record in caplog.records)

@patch('hpg_core.profiling.get_memory_usage_mb')
def test_track_memory_without_psutil(mock_get_memory, caplog):
    caplog.set_level(logging.DEBUG)
    mock_get_memory.return_value = None

    with track_memory("Memory Block No Psutil"):
        pass

    assert any("nicht moeglich" in record.message for record in caplog.records)

def test_get_memory_usage_mb_no_psutil(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "psutil", None)
    from hpg_core.profiling import get_memory_usage_mb
    assert get_memory_usage_mb() is None

def test_track_memory_no_psutil(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    import sys
    monkeypatch.setitem(sys.modules, "psutil", None)
    from hpg_core.profiling import track_memory
    with track_memory("Memory Block No Psutil Sys Patch"):
        pass
    assert any("nicht moeglich" in record.message for record in caplog.records)

def test_analysis_profiler_stop_non_existent(caplog):
    caplog.set_level(logging.INFO)
    from hpg_core.profiling import AnalysisProfiler
    profiler = AnalysisProfiler()
    profiler.stop("non_existent")
    assert "non_existent" not in profiler._timings

def test_analysis_profiler_pct_coverage(caplog):
    caplog.set_level(logging.INFO)
    from hpg_core.profiling import AnalysisProfiler
    profiler = AnalysisProfiler()
    profiler.start("fast_step")
    profiler.stop("fast_step")

    profiler.start("slow_step")
    # simulate some duration manually
    import time
    time.sleep(0.01)
    profiler.stop("slow_step")

    report = profiler.report()
    assert "fast_step" in report
    assert "slow_step" in report
