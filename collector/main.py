"""Collector process entrypoint: FastAPI app factory."""

import structlog
from fastapi import FastAPI

from collector.api.error_handlers import register_exception_handlers
from collector.api.routes import alerts, health, heartbeat, metrics, nodes
from collector.config import CollectorSettings
from collector.db.session import create_session_factory
from collector.rules.loader import load_rules_config
from shared.logging.setup import configure_logging

logger = structlog.get_logger(__name__)


def create_app(settings: CollectorSettings | None = None) -> FastAPI:
    """Build a fully-wired Collector FastAPI application.

    Accepts an optional ``settings`` override so tests can construct an
    isolated app instance (pointed at a test database) without depending
    on process environment variables.
    """
    settings = settings or CollectorSettings()
    configure_logging(settings)

    app = FastAPI(title="ClusterPulse Collector")
    app.state.settings = settings
    app.state.session_factory = create_session_factory(settings.database_url)
    app.state.rules_config = load_rules_config(settings.rules_config_path)

    register_exception_handlers(app)
    app.include_router(metrics.router)
    app.include_router(heartbeat.router)
    app.include_router(nodes.router)
    app.include_router(alerts.router)
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
