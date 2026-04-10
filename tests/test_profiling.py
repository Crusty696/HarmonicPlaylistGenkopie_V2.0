import pytest
import logging
import math
from unittest.mock import patch, MagicMock
from hpg_core.profiling import (
    profile_function,
    TimerContext,
    AnalysisProfiler,
    get_memory_usage_mb,
    track_memory
)

def test_profile_function_no_args(caplog):
    caplog.set_level(logging.INFO)

    @profile_function
    def dummy_func():
        return "success"

    with patch('hpg_core.profiling.time.perf_counter', side_effect=[0.0, 0.1]):
        result = dummy_func()

    assert result == "success"
    assert "⏱ test_profile_function_no_args.<locals>.dummy_func: 100.0ms" in caplog.text

def test_profile_function_with_args_below_threshold(caplog):
    caplog.set_level(logging.INFO)

    @profile_function(threshold_ms=200.0)
    def dummy_func():
        return "success"

    with patch('hpg_core.profiling.time.perf_counter', side_effect=[0.0, 0.1]):
        result = dummy_func()

    assert result == "success"
    assert "dummy_func: 100.0ms" not in caplog.text

def test_profile_function_with_args_above_threshold(caplog):
    caplog.set_level(logging.INFO)

    @profile_function(threshold_ms=50.0)
    def dummy_func():
        return "success"

    with patch('hpg_core.profiling.time.perf_counter', side_effect=[0.0, 0.1]):
        result = dummy_func()

    assert result == "success"
    assert "⏱ test_profile_function_with_args_above_threshold.<locals>.dummy_func: 100.0ms" in caplog.text

def test_profile_function_exception(caplog):
    caplog.set_level(logging.INFO)

    @profile_function
    def failing_func():
        raise ValueError("test error")

    with patch('hpg_core.profiling.time.perf_counter', side_effect=[0.0, 0.1]):
        with pytest.raises(ValueError, match="test error"):
            failing_func()

    assert "⏱ test_profile_function_exception.<locals>.failing_func: 100.0ms" in caplog.text

def test_timer_context_default_log(caplog):
    caplog.set_level(logging.INFO)

    with patch('hpg_core.profiling.time.perf_counter', side_effect=[0.0, 0.15]):
        with TimerContext("Test Block"):
            pass

    assert "⏱ Test Block: 150.0ms" in caplog.text

def test_timer_context_custom_log(caplog):
    caplog.set_level(logging.DEBUG)

    with patch('hpg_core.profiling.time.perf_counter', side_effect=[0.0, 0.05]):
        with TimerContext("Debug Block", log_level="DEBUG"):
            pass

    record = next((r for r in caplog.records if "Debug Block" in r.message), None)
    assert record is not None
    assert record.levelname == "DEBUG"
    assert "⏱ Debug Block: 50.0ms" in record.message

def test_analysis_profiler():
    profiler = AnalysisProfiler()

    with patch('hpg_core.profiling.time.perf_counter', side_effect=[0.0, 0.2, 0.3, 0.4]):
        profiler.start("task1")
        profiler.stop("task1")  # elapsed 200ms

        with profiler.measure("task2"):
            pass  # start at 0.3, stop at 0.4 -> elapsed 100ms

    report = profiler.report()
    assert "task1" in report
    assert "task2" in report
    assert math.isclose(report["task1"], 200.0, rel_tol=1e-9)
    assert math.isclose(report["task2"], 100.0, rel_tol=1e-9)

def test_analysis_profiler_reset():
    profiler = AnalysisProfiler()
    with patch('hpg_core.profiling.time.perf_counter', side_effect=[0.0, 0.1]):
        profiler.start("task1")
        profiler.stop("task1")

    assert "task1" in profiler._timings
    profiler.reset()
    assert not profiler._timings
    assert not profiler._starts

def test_analysis_profiler_empty_report(caplog):
    profiler = AnalysisProfiler()
    report = profiler.report()
    assert report == {}
    assert "Profiler: Keine Messungen vorhanden" in caplog.text

def test_get_memory_usage_mb_with_psutil():
    with patch.dict('sys.modules', {'psutil': MagicMock()}):
        import psutil
        mock_process = MagicMock()
        mock_process.memory_info.return_value.rss = 1048576 * 10  # 10 MB
        psutil.Process.return_value = mock_process

        mem = get_memory_usage_mb()
        assert mem == 10.0

def test_get_memory_usage_mb_no_psutil():
    with patch.dict('sys.modules', {'psutil': None}):
        mem = get_memory_usage_mb()
        assert mem is None

def test_track_memory_with_psutil(caplog):
    caplog.set_level(logging.INFO)

    with patch('hpg_core.profiling.get_memory_usage_mb', side_effect=[10.0, 15.5]):
        with track_memory("Memory Block"):
            pass

    assert "💾 Memory Block: +5.5MB (vorher: 10MB, nachher: 16MB)" in caplog.text

def test_track_memory_no_psutil(caplog):
    caplog.set_level(logging.DEBUG)

    with patch('hpg_core.profiling.get_memory_usage_mb', return_value=None):
        with track_memory("Memory Block"):
            pass

    assert "Speicher-Tracking fuer 'Memory Block' nicht moeglich (psutil fehlt)" in caplog.text
