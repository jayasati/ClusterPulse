"""Unit tests for the generic (non-ClusterPulseError) exception handler.

Uses its own ``TestClient(..., raise_server_exceptions=False)`` rather than
the shared ``collector_client`` fixture: Starlette's ``ServerErrorMiddleware``
always re-raises the original exception after building the custom-handler
response, and the default (strict) test client surfaces that re-raise for
debugging — exactly what every *other* test wants, but not this one, which
specifically exercises what a real client receives over the wire.
"""

from fastapi.testclient import TestClient

from collector.api.deps import get_node_registry_service
from collector.main import create_app


def _raise_unexpected_error():
    raise RuntimeError("something not in the ClusterPulseError hierarchy")


def test_unexpected_exception_returns_500(collector_settings, auth_headers) -> None:
    app = create_app(settings=collector_settings)
    app.dependency_overrides[get_node_registry_service] = _raise_unexpected_error
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/v1/nodes", headers=auth_headers)

    assert response.status_code == 500
    assert response.json()["error"] == "InternalServerError"
