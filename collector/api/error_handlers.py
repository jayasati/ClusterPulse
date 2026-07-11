"""Maps ``ClusterPulseError`` subclasses to HTTP responses.

Every response body shares one shape (``error``, ``message``, ``context``)
so API consumers have one error format to parse regardless of which
subclass was raised. See ``docs/architecture/00-project-initialization.md`` §7.2.
"""

import structlog
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from collector.exceptions import NodeNotFoundError
from shared.constants import HTTP_SERVER_ERROR_THRESHOLD
from shared.exceptions import AuthenticationError, ClusterPulseError, PersistenceError

logger = structlog.get_logger(__name__)


def _status_for(exc: ClusterPulseError) -> int:
    """Map an exception instance to its HTTP status code, by hierarchy."""
    if isinstance(exc, AuthenticationError):
        return status.HTTP_401_UNAUTHORIZED
    if isinstance(exc, NodeNotFoundError):
        return status.HTTP_404_NOT_FOUND
    if isinstance(exc, PersistenceError):
        return status.HTTP_503_SERVICE_UNAVAILABLE
    return status.HTTP_500_INTERNAL_SERVER_ERROR


def register_exception_handlers(app: FastAPI) -> None:
    """Register handlers translating exceptions into JSON responses."""

    @app.exception_handler(ClusterPulseError)
    async def handle_cluster_pulse_error(
        request: Request, exc: ClusterPulseError
    ) -> JSONResponse:
        status_code = _status_for(exc)
        if status_code >= HTTP_SERVER_ERROR_THRESHOLD:
            logger.error(
                "unhandled_cluster_pulse_error", error=str(exc), path=request.url.path
            )
        return JSONResponse(
            status_code=status_code,
            content={
                "error": type(exc).__name__,
                "message": exc.message,
                "context": exc.context,
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled_exception", error=str(exc), path=request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "InternalServerError",
                "message": "an unexpected error occurred",
            },
        )
