import logging
import logging.handlers
import sys
import os
from pathlib import Path

import pytest

from hpg_core.logging_config import (
    setup_logging,
    set_module_level,
    get_debug_logger,
    _CompactFormatter,
    _FileFormatter,
    LOG_DIR,
    LOG_FILE,
    DEFAULT_LEVEL,
    MODULE_LEVELS,
)

@pytest.fixture(autouse=True)
def cleanup_logging(tmp_path, monkeypatch):
    """Fixture to save and restore logging state around each test and use tmp_path."""
    # Monkeypatch LOG_DIR and LOG_FILE to use tmp_path so we don't pollute the actual logs directory
    monkeypatch.setattr("hpg_core.logging_config.LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr("hpg_core.logging_config.LOG_FILE", tmp_path / "logs" / "hpg.log")

    root = logging.getLogger()
    old_level = root.level
    old_handlers = list(root.handlers)

    # Save loggers' levels that might be modified
    saved_levels = {}
    for module in MODULE_LEVELS.keys():
        saved_levels[module] = logging.getLogger(module).level

    for lib in ["librosa", "numba", "audioread", "matplotlib", "PIL"]:
        saved_levels[lib] = logging.getLogger(lib).level

    yield

    # Restore root logger
    root.setLevel(old_level)
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()
    for handler in old_handlers:
        root.addHandler(handler)

    # Restore module levels
    for module, level in saved_levels.items():
        logging.getLogger(module).setLevel(level)


def test_setup_logging_defaults():
    root = setup_logging()

    assert root.level == logging.DEBUG

    handlers = root.handlers
    assert len(handlers) == 2

    stream_handlers = [h for h in handlers if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.handlers.RotatingFileHandler)]
    file_handlers = [h for h in handlers if isinstance(h, logging.handlers.RotatingFileHandler)]

    assert len(stream_handlers) == 1
    assert stream_handlers[0].stream == sys.stderr
    assert stream_handlers[0].level == logging.INFO
    assert isinstance(stream_handlers[0].formatter, _CompactFormatter)

    assert len(file_handlers) == 1
    # Check that it ends with hpg.log (since we monkeypatched the path it won't equal LOG_FILE statically)
    assert file_handlers[0].baseFilename.endswith("hpg.log")
    assert file_handlers[0].level == logging.DEBUG
    assert isinstance(file_handlers[0].formatter, _FileFormatter)

    # Check that module levels are applied
    for module in MODULE_LEVELS.keys():
        assert logging.getLogger(module).level == logging.INFO

    # Check that external libs are quiet
    for lib in ["librosa", "numba", "audioread", "matplotlib", "PIL"]:
        assert logging.getLogger(lib).level == logging.WARNING


def test_setup_logging_level():
    root = setup_logging(level="DEBUG")
    handlers = root.handlers
    stream_handlers = [h for h in handlers if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(stream_handlers) == 1
    assert stream_handlers[0].level == logging.DEBUG


def test_setup_logging_no_file():
    root = setup_logging(log_to_file=False)
    handlers = root.handlers
    file_handlers = [h for h in handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(file_handlers) == 0


def test_setup_logging_no_console():
    root = setup_logging(log_to_console=False)
    handlers = root.handlers
    stream_handlers = [h for h in handlers if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(stream_handlers) == 0


def test_setup_logging_replaces_handlers():
    setup_logging()
    root = logging.getLogger()
    initial_handler_count = len(root.handlers)

    # Call again to ensure old handlers are removed
    setup_logging()
    root = logging.getLogger()
    assert len(root.handlers) == initial_handler_count


def test_compact_formatter():
    formatter = _CompactFormatter()

    # Test formatting of standard message
    record = logging.LogRecord(
        name="hpg_core.analysis",
        level=logging.INFO,
        pathname="analysis.py",
        lineno=10,
        msg="Test message",
        args=(),
        exc_info=None
    )
    formatted = formatter.format(record)
    assert formatted == "[INFO] analysis: Test message"

    # Test formatting for exporters
    record_exporter = logging.LogRecord(
        name="hpg_core.exporters.m3u8_exporter",
        level=logging.ERROR,
        pathname="m3u8_exporter.py",
        lineno=20,
        msg="Export failed",
        args=(),
        exc_info=None
    )
    formatted_exporter = formatter.format(record_exporter)
    assert formatted_exporter == "[ERROR] exporters.m3u8_exporter: Export failed"

    # Coverage for the elif without replacing hpg_core first
    # This specifically tests the `elif short_name.startswith("hpg_core.exporters.")` logic
    # though it normally wouldn't be hit because "hpg_core." matches first
    # We pass it explicitly
    record_exporter_direct = logging.LogRecord(
        name="hpg_core.exporters.test",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Export msg",
        args=(),
        exc_info=None
    )
    # The current logic will hit the first if branch anyway, but we just verify it works
    formatted_exporter_direct = formatter.format(record_exporter_direct)
    assert formatted_exporter_direct == "[INFO] exporters.test: Export msg"

    # Test formatting with arbitrary logger name
    record_other = logging.LogRecord(
        name="other.module",
        level=logging.DEBUG,
        pathname="other.py",
        lineno=30,
        msg="Other message",
        args=(),
        exc_info=None
    )
    formatted_other = formatter.format(record_other)
    assert formatted_other == "[DEBUG] other.module: Other message"

    # Test fallback tags
    record_unknown = logging.LogRecord(
        name="test",
        level=45, # Custom level
        pathname="test.py",
        lineno=1,
        msg="Unknown level",
        args=(),
        exc_info=None
    )
    formatted_unknown = formatter.format(record_unknown)
    assert formatted_unknown == "[Level 45] test: Unknown level"

    # Test with exception info
    try:
        1 / 0
    except ZeroDivisionError:
        exc_info = sys.exc_info()

    record_exc = logging.LogRecord(
        name="hpg_core.test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=1,
        msg="Exception occurred",
        args=(),
        exc_info=exc_info
    )
    formatted_exc = formatter.format(record_exc)
    assert "[ERROR] test: Exception occurred" in formatted_exc
    assert "ZeroDivisionError" in formatted_exc


def test_file_formatter():
    formatter = _FileFormatter()
    record = logging.LogRecord(
        name="hpg_core.analysis",
        level=logging.INFO,
        pathname="analysis.py",
        lineno=10,
        msg="Test message",
        args=(),
        exc_info=None
    )
    formatted = formatter.format(record)
    assert "INFO" in formatted
    assert "[hpg_core.analysis]" in formatted
    assert "Test message" in formatted
    # Check that it starts with a timestamp (like "2023-10-27 10:00:00")
    assert len(formatted.split()) >= 3


def test_set_module_level():
    module_name = "hpg_core.test_module"
    logger = logging.getLogger(module_name)

    # Set to DEBUG
    set_module_level(module_name, "DEBUG")
    assert logger.level == logging.DEBUG

    # Set to WARNING
    set_module_level(module_name, "WARNING")
    assert logger.level == logging.WARNING


def test_get_debug_logger():
    name = "test_logger_name"
    logger = get_debug_logger(name)

    assert isinstance(logger, logging.Logger)
    assert logger.name == name
