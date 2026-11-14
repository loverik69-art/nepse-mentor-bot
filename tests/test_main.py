import asyncio
import logging
from types import SimpleNamespace

from main import global_error_handler


def test_global_error_handler_logs_exception(caplog):
    error = RuntimeError("Test internal failure")
    context = SimpleNamespace(error=error)

    with caplog.at_level(logging.ERROR):
        asyncio.run(global_error_handler(None, context))

    assert "Unhandled exception" in caplog.text
    assert "RuntimeError: Test internal failure" in caplog.text


def test_global_error_handler_handles_missing_exception(caplog):
    context = SimpleNamespace(error=None)

    with caplog.at_level(logging.ERROR):
        asyncio.run(global_error_handler(None, context))

    assert "without exception details" in caplog.text
