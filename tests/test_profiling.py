import sys
import pytest
from unittest.mock import MagicMock, patch
from hpg_core.profiling import get_memory_usage_mb

def test_get_memory_usage_mb_success():
    """Test get_memory_usage_mb when psutil is installed and works."""
    mock_psutil = MagicMock()
    mock_process = MagicMock()
    mock_memory_info = MagicMock()
    # 100 MB
    mock_memory_info.rss = 100 * 1024 * 1024
    mock_process.memory_info.return_value = mock_memory_info
    mock_psutil.Process.return_value = mock_process

    with patch.dict('sys.modules', {'psutil': mock_psutil}):
        result = get_memory_usage_mb()
        assert result == 100.0
        mock_psutil.Process.assert_called_once()
        mock_process.memory_info.assert_called_once()

def test_get_memory_usage_mb_import_error():
    """Test get_memory_usage_mb when psutil is not installed."""
    original_import = __import__

    def mock_import(name, *args, **kwargs):
        if name == 'psutil':
            raise ImportError("No module named 'psutil'")
        return original_import(name, *args, **kwargs)

    with patch('builtins.__import__', side_effect=mock_import):
        with patch.dict('sys.modules'):
            if 'psutil' in sys.modules:
                del sys.modules['psutil']
            result = get_memory_usage_mb()
            assert result is None
