"""Unit tests for the Collector app factory wiring."""

from fastapi import FastAPI

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
