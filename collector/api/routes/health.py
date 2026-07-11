"""Liveness/readiness endpoint. Deliberately unauthenticated — orchestrators
and load balancers polling this shouldn't need a bearer token.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from collector.api.deps import get_db_session
from shared.exceptions import PersistenceError

router = APIRouter()


@router.get("/healthz")
def healthz(session: Session = Depends(get_db_session)) -> dict[str, str]:
    """Report whether the Collector can reach its database."""
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise PersistenceError("database health check failed") from exc
    return {"status": "ok"}
