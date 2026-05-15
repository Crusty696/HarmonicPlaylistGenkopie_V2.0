import pytest
import logging
import time
from unittest.mock import patch, MagicMock

from hpg_core.profiling import (
    profile_function,
    TimerContext,
    AnalysisProfiler,
    get_memory_usage_mb,
    track_memory,
)

class TestProfileFunction:
    def test_profile_function_no_args_logs(self, caplog):
        caplog.set_level(logging.INFO)

        @profile_function
        def dummy_func(x):
            return x * 2

        with patch('hpg_core.profiling.time.perf_counter', side_effect=[0.0, 0.05]):
            result = dummy_func(5)

        assert result == 10
        assert any("dummy_func" in record.message for record in caplog.records)
        assert any("50.0ms" in record.message for record in caplog.records)

    def test_profile_function_with_args_below_threshold(self, caplog):
        caplog.set_level(logging.INFO)

        @profile_function(threshold_ms=100.0)
        def fast_func():
            return "fast"

        with patch('hpg_core.profiling.time.perf_counter', side_effect=[0.0, 0.05]):
            result = fast_func()

        assert result == "fast"
        # Since 50ms < 100ms, it should not log
        assert not any("fast_func" in record.message for record in caplog.records)

    def test_profile_function_with_args_above_threshold(self, caplog):
        caplog.set_level(logging.INFO)

        @profile_function(threshold_ms=100.0)
        def slow_func():
            return "slow"

        with patch('hpg_core.profiling.time.perf_counter', side_effect=[0.0, 0.15]):
            result = slow_func()

        assert result == "slow"
        assert any("slow_func" in record.message for record in caplog.records)
        assert any("150.0ms" in record.message for record in caplog.records)

    def test_profile_function_exception_handling(self, caplog):
        caplog.set_level(logging.INFO)

        @profile_function
        def error_func():
            raise ValueError("Test error")

        with patch('hpg_core.profiling.time.perf_counter', side_effect=[0.0, 0.05]):
            with pytest.raises(ValueError):
                error_func()

        assert any("error_func" in record.message for record in caplog.records)
        assert any("50.0ms" in record.message for record in caplog.records)


class TestTimerContext:
    def test_timer_context_logs_info_by_default(self, caplog):
        caplog.set_level(logging.INFO)

        with patch('hpg_core.profiling.time.perf_counter', side_effect=[0.0, 0.1]):
            with TimerContext("Test Block"):
                pass

        assert any("Test Block" in record.message for record in caplog.records)
        assert any("100.0ms" in record.message for record in caplog.records)

    def test_timer_context_custom_log_level(self, caplog):
        caplog.set_level(logging.DEBUG)

        with patch('hpg_core.profiling.time.perf_counter', side_effect=[0.0, 0.1]):
            with TimerContext("Debug Block", log_level="DEBUG"):
                pass

        debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("Debug Block" in record.message for record in debug_records)

    def test_timer_context_exception(self, caplog):
        caplog.set_level(logging.INFO)

        with patch('hpg_core.profiling.time.perf_counter', side_effect=[0.0, 0.1]):
            with pytest.raises(ValueError):
                with TimerContext("Error Block"):
                    raise ValueError("Fail")

        assert any("Error Block" in record.message for record in caplog.records)


class TestAnalysisProfiler:
    def test_profiler_start_stop(self):
        profiler = AnalysisProfiler()
        with patch('hpg_core.profiling.time.perf_counter', side_effect=[0.0, 0.1]):
            profiler.start("task1")
            profiler.stop("task1")

        assert profiler._timings["task1"] == pytest.approx(100.0)

    def test_profiler_measure_context(self):
        profiler = AnalysisProfiler()
        with patch('hpg_core.profiling.time.perf_counter', side_effect=[0.0, 0.2]):
            with profiler.measure("task2"):
                pass

        assert profiler._timings["task2"] == pytest.approx(200.0)

    def test_profiler_report(self, caplog):
        caplog.set_level(logging.INFO)
        profiler = AnalysisProfiler()
        profiler._timings = {"task_a": 100.0, "task_b": 300.0}

        report = profiler.report()
        assert report == {"task_a": 100.0, "task_b": 300.0}

        assert any("Analyse-Profil" in record.message for record in caplog.records)
        assert any("task_a" in record.message for record in caplog.records)
        assert any("task_b" in record.message for record in caplog.records)

    def test_profiler_report_empty(self, caplog):
        caplog.set_level(logging.INFO)
        profiler = AnalysisProfiler()

        report = profiler.report()
        assert report == {}
        assert any("Keine Messungen vorhanden" in record.message for record in caplog.records)

    def test_profiler_reset(self):
        profiler = AnalysisProfiler()
        profiler._timings = {"task1": 100.0}
        profiler._starts = {"task2": 0.0}

        profiler.reset()
        assert profiler._timings == {}
        assert profiler._starts == {}


class TestMemoryProfiling:
    def test_get_memory_usage_mb_success(self):
        mock_psutil = MagicMock()
        mock_process = MagicMock()
        mock_process.memory_info.return_value.rss = 1048576 * 10  # 10 MB
        mock_psutil.Process.return_value = mock_process

        with patch.dict('sys.modules', {'psutil': mock_psutil}):
            usage = get_memory_usage_mb()
            assert usage == 10.0

    def test_get_memory_usage_mb_no_psutil(self):
        with patch.dict('sys.modules', {'psutil': None}):
            usage = get_memory_usage_mb()
            assert usage is None

    @patch('hpg_core.profiling.get_memory_usage_mb')
    def test_track_memory_success(self, mock_get_memory, caplog):
        caplog.set_level(logging.INFO)
        mock_get_memory.side_effect = [10.0, 15.0]  # 5MB increase

        with track_memory("MemoryTask"):
            pass

        assert any("MemoryTask" in r.message for r in caplog.records)
        assert any("+5.0MB" in r.message for r in caplog.records)

    @patch('hpg_core.profiling.get_memory_usage_mb')
    def test_track_memory_no_psutil(self, mock_get_memory, caplog):
        caplog.set_level(logging.DEBUG)
        mock_get_memory.return_value = None

        with track_memory("MissingPsutilTask"):
            pass

        assert any("nicht moeglich" in r.message for r in caplog.records)

    @patch('hpg_core.profiling.get_memory_usage_mb')
    def test_track_memory_exception(self, mock_get_memory, caplog):
        caplog.set_level(logging.INFO)
        mock_get_memory.side_effect = [10.0, 15.0]

        with pytest.raises(ValueError):
            with track_memory("FailingTask"):
                raise ValueError("Fail")

        assert any("FailingTask" in r.message for r in caplog.records)
        assert any("+5.0MB" in r.message for r in caplog.records)
