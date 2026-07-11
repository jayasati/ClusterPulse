"""Engine and session-factory construction for the Collector's database.

Sync SQLAlchemy, not async — see ``docs/adr/017-collector-sync-vs-async-db.md``.
"""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_session_factory(database_url: str) -> sessionmaker[Session]:
    """Build a session factory bound to a fresh engine for ``database_url``."""
    engine: Engine = create_engine(database_url, pool_pre_ping=True)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
