import logging
from hpg_core.profiling import AnalysisProfiler

def test_analysis_profiler_report_empty(caplog):
    profiler = AnalysisProfiler()
    with caplog.at_level(logging.INFO):
        result = profiler.report()

    assert result == {}
    assert "Profiler: Keine Messungen vorhanden" in caplog.text

def test_analysis_profiler_report_with_data(caplog):
    profiler = AnalysisProfiler()
    # Mocking internal data to avoid real timers for deterministic tests
    profiler._timings = {
        "fast_task": 10.0,
        "slow_task": 90.0
    }

    with caplog.at_level(logging.INFO):
        result = profiler.report()

    assert result == {"fast_task": 10.0, "slow_task": 90.0}

    # Assert correct logging
    assert "=== Analyse-Profil (Gesamt: 100.0ms) ===" in caplog.text

    log_lines = caplog.text.strip().split("\n")

    # Depending on how pytest caplog works, there might be other logs.
    # We should search for our specific logs.
    slow_task_log = next((line for line in log_lines if "slow_task" in line), None)
    fast_task_log = next((line for line in log_lines if "fast_task" in line), None)

    assert slow_task_log is not None
    assert "90.0ms" in slow_task_log
    assert "90.0%" in slow_task_log

    assert fast_task_log is not None
    assert "10.0ms" in fast_task_log
    assert "10.0%" in fast_task_log

    # slow_task should be logged before fast_task
    slow_idx = log_lines.index(slow_task_log)
    fast_idx = log_lines.index(fast_task_log)
    assert slow_idx < fast_idx

def test_analysis_profiler_report_zero_total(caplog):
    profiler = AnalysisProfiler()
    profiler._timings = {
        "zero_task": 0.0,
    }

    with caplog.at_level(logging.INFO):
        result = profiler.report()

    assert result == {"zero_task": 0.0}

    # Should not raise division by zero
    assert "=== Analyse-Profil (Gesamt: 0.0ms) ===" in caplog.text

    log_lines = caplog.text.strip().split("\n")
    zero_task_log = next((line for line in log_lines if "zero_task" in line), None)
    assert zero_task_log is not None
    assert "0.0%" in zero_task_log
