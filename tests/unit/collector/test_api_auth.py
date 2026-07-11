"""Unit tests for API token authentication, exercised through a real route."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from collector.config import CollectorSettings
from collector.db.base import Base
from collector.main import create_app

from .conftest import dispose_app_engine


def test_missing_token_is_rejected(collector_client) -> None:
    response = collector_client.get("/api/v1/nodes")
    assert response.status_code == 401


def test_wrong_token_is_rejected(collector_client) -> None:
    response = collector_client.get(
        "/api/v1/nodes", headers={"Authorization": "Bearer wrong-token"}
    )
    assert response.status_code == 401


def test_correct_token_is_accepted(collector_client, auth_headers) -> None:
    response = collector_client.get("/api/v1/nodes", headers=auth_headers)
    assert response.status_code == 200


def test_malformed_authorization_header_is_rejected(collector_client) -> None:
    response = collector_client.get(
        "/api/v1/nodes", headers={"Authorization": "not-a-bearer-token"}
    )
    assert response.status_code == 401


def test_empty_token_set_disables_auth_in_dev(tmp_path) -> None:
    """environment=dev with no configured tokens is a deliberate, documented
    escape hatch for local development — see docs/adr/005-authentication.md."""
    database_url = f"sqlite:///{tmp_path / 'dev_auth_test.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    engine.dispose()
    settings = CollectorSettings(
        environment="dev", database_url=database_url, api_tokens=""
    )
    app = create_app(settings=settings)

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/nodes")
    finally:
        dispose_app_engine(app)

    assert response.status_code == 200
