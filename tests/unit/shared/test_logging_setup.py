"""Unit tests for configure_logging."""

import structlog

from shared.config.base import BaseServiceSettings
from shared.logging.setup import configure_logging


def test_configure_logging_dev_uses_console_renderer() -> None:
    configure_logging(BaseServiceSettings(environment="dev"))
    renderer = structlog.get_config()["processors"][-1]
    assert isinstance(renderer, structlog.dev.ConsoleRenderer)


def test_configure_logging_prod_uses_json_renderer() -> None:
    configure_logging(BaseServiceSettings(environment="prod"))
    renderer = structlog.get_config()["processors"][-1]
    assert isinstance(renderer, structlog.processors.JSONRenderer)


def test_configure_logging_falls_back_on_invalid_level() -> None:
    # Must not raise even though "NOT_A_LEVEL" isn't a real log level.
    configure_logging(BaseServiceSettings(log_level="NOT_A_LEVEL"))
