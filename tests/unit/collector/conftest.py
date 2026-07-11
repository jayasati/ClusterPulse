"""Fixtures for Collector unit tests.

Two separate SQLite setups are used deliberately:

- ``db_session`` (in-memory, ``StaticPool``): fast, isolated sessions for
  repository-level tests that construct a ``Session`` directly.
- ``collector_client`` (file-based, in ``tmp_path``): used for full API
  tests through ``create_app()`` + ``TestClient``, so the app's *own*
  ``create_session_factory`` code path is exercised unmodified — a plain
  in-memory URL would hand each new connection its own private empty
  database, since SQLAlchemy's default pool doesn't share one SQLite
  ``:memory:`` connection across requests.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from collector.config import CollectorSettings
from collector.db.base import Base
from collector.db.models import alert  # noqa: F401 - register model on Base
from collector.db.models import metric_sample  # noqa: F401 - register model on Base
from collector.db.models import node  # noqa: F401 - register model on Base
from collector.main import create_app

TEST_TOKEN = "test-token"


def _enable_sqlite_foreign_keys(engine):
    """SQLite ignores foreign keys unless explicitly told to enforce them.

    Without this, a test could insert a metric sample for a nonexistent
    node and SQLite would silently allow it — masking real FK-violation
    behavior that PostgreSQL always enforces.
    """

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    _enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _build_collector_settings(tmp_path, db_name: str, **overrides) -> CollectorSettings:
    """Build test ``CollectorSettings``, isolated from any real ``.env``.

    ``_env_file=None`` disables pydantic-settings' automatic ``.env``
    loading for this instance specifically — without it, a real `.env` in
    the repo root (e.g. real Telegram credentials, set up for manual
    verification) silently leaks into every test that doesn't explicitly
    override every field, which for Telegram settings means tests
    unknowingly attempting real network calls to a real chat.
    """
    database_url = f"sqlite:///{tmp_path / db_name}"
    engine = create_engine(database_url)
    _enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    engine.dispose()
    return CollectorSettings(
        _env_file=None, database_url=database_url, api_tokens=TEST_TOKEN, **overrides
    )


@pytest.fixture
def collector_settings(tmp_path):
    return _build_collector_settings(tmp_path, "collector_test.db")


TELEGRAM_BOT_TOKEN = "test-bot-token"
TELEGRAM_CHAT_ID = "test-chat-id"


@pytest.fixture
def collector_settings_with_telegram(tmp_path):
    return _build_collector_settings(
        tmp_path,
        "collector_test_telegram.db",
        telegram_bot_token=TELEGRAM_BOT_TOKEN,
        telegram_chat_id=TELEGRAM_CHAT_ID,
    )


def dispose_app_engine(app) -> None:
    """Dispose the SQLAlchemy engine ``create_app()`` built for ``app``.

    Each test-built app owns its own engine (see ``collector_settings``
    above) — nothing else disposes it, so tests that construct their own
    app via ``create_app()`` must call this in a ``finally`` block.
    """
    app.state.session_factory.kw["bind"].dispose()


@pytest.fixture
def collector_client(collector_settings):
    app = create_app(settings=collector_settings)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        dispose_app_engine(app)


@pytest.fixture
def collector_client_with_telegram(collector_settings_with_telegram):
    app = create_app(settings=collector_settings_with_telegram)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        dispose_app_engine(app)


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {TEST_TOKEN}"}
