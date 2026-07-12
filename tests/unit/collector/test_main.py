"""Unit tests for the Collector app factory wiring."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from collector.config import CollectorSettings
from collector.main import create_app


def test_create_app_returns_a_fastapi_app(collector_settings) -> None:
    app = create_app(settings=collector_settings)
    assert isinstance(app, FastAPI)


def test_create_app_registers_expected_routes(collector_settings) -> None:
    app = create_app(settings=collector_settings)
    paths = set(app.openapi()["paths"].keys())
    assert "/api/v1/metrics" in paths
    assert "/api/v1/heartbeat" in paths
    assert "/api/v1/nodes" in paths
    assert "/api/v1/nodes/{node_id}" in paths
    assert "/healthz" in paths


def test_create_app_stashes_settings_on_state(collector_settings) -> None:
    app = create_app(settings=collector_settings)
    assert app.state.settings is collector_settings


def test_no_job_scheduler_when_retention_disabled(collector_settings) -> None:
    """Default behavior is exactly pre-Phase-6: no background thread at all."""
    app = create_app(settings=collector_settings)
    assert app.state.job_scheduler is None


def test_lifespan_starts_and_stops_scheduler_when_retention_enabled(tmp_path) -> None:
    settings = CollectorSettings(
        _env_file=None,
        api_tokens="t",
        database_url=f"sqlite:///{tmp_path / 'retention_lifespan.db'}",
        retention_enabled=True,
        # One hour: the scheduler thread must exist but never actually
        # sweep during this test.
        retention_interval_seconds=3600,
    )
    app = create_app(settings=settings)
    try:
        scheduler = app.state.job_scheduler
        assert scheduler is not None
        assert scheduler.is_running is False

        with TestClient(app):
            assert scheduler.is_running is True

        assert scheduler.is_running is False
    finally:
        app.state.session_factory.kw["bind"].dispose()
