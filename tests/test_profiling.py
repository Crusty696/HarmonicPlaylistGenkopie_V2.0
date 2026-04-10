import pytest
from unittest.mock import patch, MagicMock
import logging

from hpg_core.profiling import (
    track_memory,
    get_memory_usage_mb,
    profile_function,
    TimerContext,
    AnalysisProfiler
)

class TestTrackMemory:
    @patch('hpg_core.profiling.get_memory_usage_mb')
    def test_track_memory_no_psutil(self, mock_get_memory_usage_mb, caplog):
        # Setup mock to simulate missing psutil
        mock_get_memory_usage_mb.return_value = None

        with caplog.at_level(logging.DEBUG):
            with track_memory("TestLabel"):
                pass

        assert "Speicher-Tracking fuer 'TestLabel' nicht moeglich (psutil fehlt)" in caplog.text

    @patch('hpg_core.profiling.get_memory_usage_mb')
    def test_track_memory_with_psutil(self, mock_get_memory_usage_mb, caplog):
        # Simulate memory usage growing
        mock_get_memory_usage_mb.side_effect = [100.0, 150.0]

        with caplog.at_level(logging.INFO):
            with track_memory("TestLabel"):
                pass

        assert "💾 TestLabel: +50.0MB (vorher: 100MB, nachher: 150MB)" in caplog.text

    @patch('hpg_core.profiling.get_memory_usage_mb')
    def test_track_memory_exception_raised(self, mock_get_memory_usage_mb, caplog):
        # Even if an exception occurs, it should log the after value if before was gathered
        mock_get_memory_usage_mb.side_effect = [100.0, 110.0]

        with caplog.at_level(logging.INFO):
            with pytest.raises(ValueError):
                with track_memory("ErrorLabel"):
                    raise ValueError("Simulated error")

        assert "💾 ErrorLabel: +10.0MB (vorher: 100MB, nachher: 110MB)" in caplog.text

class TestGetMemoryUsageMB:
    @patch.dict('sys.modules', {'psutil': MagicMock()})
    def test_get_memory_usage_mb_success(self):
        # Setup mock for process and memory_info
        mock_process = MagicMock()
        mock_memory_info = MagicMock()
        mock_memory_info.rss = 104857600 # 100 MB in bytes
        mock_process.memory_info.return_value = mock_memory_info
        __import__('sys').modules['psutil'].Process.return_value = mock_process

        # Test
        result = get_memory_usage_mb()

        # Assertions
        assert result == 100.0
        __import__('sys').modules['psutil'].Process.assert_called_once()

    @patch.dict('sys.modules', {'psutil': None})
    def test_get_memory_usage_mb_import_error(self):
        result = get_memory_usage_mb()
        assert result is None

class TestProfileFunction:
    def test_profile_function_decorator(self, caplog):
        @profile_function
        def dummy_func():
            return 42

        with caplog.at_level(logging.INFO):
            result = dummy_func()

        assert result == 42
        assert "dummy_func" in caplog.text

    def test_profile_function_decorator_with_threshold(self, caplog):
        @profile_function(threshold_ms=10.0)
        def dummy_func_fast():
            return 42

        with caplog.at_level(logging.INFO):
            result = dummy_func_fast()

        assert result == 42
        # Fast function should not be logged because threshold is 10.0ms
        assert "dummy_func_fast" not in caplog.text

        @profile_function(threshold_ms=0.0)
        def dummy_func_slow():
            return 42

        with caplog.at_level(logging.INFO):
            result = dummy_func_slow()

        assert result == 42
        # Function should be logged because threshold is 0.0ms
        assert "dummy_func_slow" in caplog.text

class TestTimerContext:
    def test_timer_context_info(self, caplog):
        with caplog.at_level(logging.INFO):
            with TimerContext("TestContext"):
                pass

        assert "TestContext" in caplog.text
        assert "ms" in caplog.text

    def test_timer_context_debug(self, caplog):
        with caplog.at_level(logging.DEBUG):
            with TimerContext("TestContextDebug", log_level="DEBUG"):
                pass

        assert "TestContextDebug" in caplog.text
        assert "ms" in caplog.text

class TestAnalysisProfiler:
    def test_start_stop_report(self, caplog):
        profiler = AnalysisProfiler()
        profiler.start("step1")
        profiler.stop("step1")

        with caplog.at_level(logging.INFO):
            report = profiler.report()

        assert "step1" in report
        assert isinstance(report["step1"], float)
        assert "Analyse-Profil" in caplog.text

    def test_measure_context(self):
        profiler = AnalysisProfiler()
        with profiler.measure("step2"):
            pass

        report = profiler.report()
        assert "step2" in report
        assert isinstance(report["step2"], float)

    def test_report_empty(self, caplog):
        profiler = AnalysisProfiler()
        with caplog.at_level(logging.INFO):
            report = profiler.report()

        assert report == {}
        assert "Profiler: Keine Messungen vorhanden" in caplog.text

    def test_reset(self):
        profiler = AnalysisProfiler()
        profiler.start("step3")
        profiler.stop("step3")
        assert "step3" in profiler.report()

        profiler.reset()
        assert profiler.report() == {}
