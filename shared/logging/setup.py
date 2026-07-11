"""Structured logging configuration shared by every ClusterPulse service.

Uses ``structlog`` bound to stdlib ``logging`` so third-party library log
records are captured uniformly. See
``docs/architecture/00-project-initialization.md`` §6 for the full design.
"""

import logging
import sys

import structlog

from shared.config.base import BaseServiceSettings

_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def configure_logging(settings: BaseServiceSettings) -> None:
    """Configure stdlib logging + structlog for the current process.

    Renders JSON in staging/prod (machine-parseable) and a colored console
    format in dev. Never raises: an invalid log level falls back to INFO
    with a single warning, since logging setup must not be able to crash
    process startup.
    """
    configured_level = settings.log_level.upper()
    level_name = configured_level if configured_level in _VALID_LEVELS else "INFO"
    level = getattr(logging, level_name)

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    renderer = (
        structlog.dev.ConsoleRenderer()
        if settings.environment == "dev"
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    if configured_level != level_name:
        structlog.get_logger(__name__).warning(
            "invalid_log_level_fallback",
            configured=settings.log_level,
            fallback=level_name,
        )
