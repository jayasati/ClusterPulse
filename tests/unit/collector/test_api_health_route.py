"""Unit tests for GET /healthz."""


def test_healthz_does_not_require_auth(collector_client) -> None:
    response = collector_client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_reports_503_when_db_is_unreachable(collector_client) -> None:
    # Point the app's session factory at a broken database to simulate an
    # outage without needing a real network-level failure.
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    broken_engine = create_engine("sqlite:////nonexistent/path/does-not-exist.db")
    collector_client.app.state.session_factory = sessionmaker(bind=broken_engine)

    response = collector_client.get("/healthz")

    assert response.status_code == 503
