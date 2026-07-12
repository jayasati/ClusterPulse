"""Collector process entrypoint: FastAPI app factory."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from sqlalchemy.orm import Session, sessionmaker

from collector.api.error_handlers import register_exception_handlers
from collector.api.routes import (
    alerts,
    health,
    heartbeat,
    metrics,
    nodes,
    remediation_actions,
)
from collector.config import CollectorSettings
from collector.db.session import create_session_factory
from collector.jobs import PeriodicJobScheduler, RetentionJob
from collector.notifications.protocols import Notifier
from collector.notifications.telegram import TelegramNotifier
from collector.remediation.loader import load_remediation_policy
from collector.rules.loader import load_rules_config
from shared.logging.setup import configure_logging

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start/stop the background job scheduler with the app.

    ``app.state.job_scheduler`` is ``None`` unless retention is enabled —
    the scheduler thread only exists when there is work for it, so every
    deployment (and every existing test) that leaves retention off runs
    exactly as before Phase 6.
    """
    scheduler: PeriodicJobScheduler | None = app.state.job_scheduler
    if scheduler is not None:
        scheduler.start()
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.stop()


def _build_job_scheduler(
    settings: CollectorSettings, session_factory: sessionmaker[Session]
) -> PeriodicJobScheduler | None:
    """Build the scheduler with the retention job, or ``None`` if disabled."""
    if not settings.retention_enabled:
        return None
    retention_job = RetentionJob(session_factory, settings)
    return PeriodicJobScheduler(
        interval_seconds=settings.retention_interval_seconds, jobs=[retention_job]
    )


def _build_notifier(settings: CollectorSettings) -> Notifier | None:
    """Build the Telegram notifier, or ``None`` if not configured.

    Constructed once at startup (like the DB engine) rather than per
    request, so it reuses one HTTP connection pool.
    """
    bot_token, chat_id = settings.telegram_bot_token, settings.telegram_chat_id
    if not bot_token or not chat_id:
        return None
    return TelegramNotifier(bot_token, chat_id)


def create_app(settings: CollectorSettings | None = None) -> FastAPI:
    """Build a fully-wired Collector FastAPI application.

    Accepts an optional ``settings`` override so tests can construct an
    isolated app instance (pointed at a test database) without depending
    on process environment variables.
    """
    settings = settings or CollectorSettings()
    configure_logging(settings)

    app = FastAPI(title="ClusterPulse Collector", lifespan=_lifespan)
    app.state.settings = settings
    app.state.session_factory = create_session_factory(settings.database_url)
    app.state.job_scheduler = _build_job_scheduler(settings, app.state.session_factory)
    app.state.rules_config = load_rules_config(settings.rules_config_path)
    app.state.remediation_policy = load_remediation_policy(
        settings.remediation_policy_config_path
    )
    app.state.notifier = _build_notifier(settings)

    register_exception_handlers(app)
    app.include_router(metrics.router)
    app.include_router(heartbeat.router)
    app.include_router(nodes.router)
    app.include_router(alerts.router)
    app.include_router(remediation_actions.router)
    app.include_router(health.router)

    logger.info("collector_app_created", environment=settings.environment)
    return app


app = create_app()


def run() -> None:
    """Run the Collector with uvicorn, bound per its own settings."""
    import uvicorn

    uvicorn.run(app, host=app.state.settings.host, port=app.state.settings.port)


if __name__ == "__main__":
    run()
