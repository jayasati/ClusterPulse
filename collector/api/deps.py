"""FastAPI dependency providers.

Each provider is a thin function `Depends`-chained by the routes — this is
the Collector's Dependency Injection mechanism (`.claude/CLAUDE.md`:
"Dependency Injection where appropriate"). Nothing here holds real state
of its own beyond what's stashed on ``app.state`` at startup.
"""

import hmac
from collections.abc import Generator

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from collector.config import CollectorSettings
from collector.repositories.alert_repository import SqlAlchemyAlertRepository
from collector.repositories.metrics_repository import SqlAlchemyMetricsRepository
from collector.repositories.node_repository import SqlAlchemyNodeRepository
from collector.repositories.protocols import (
    AlertRepository,
    MetricsRepository,
    NodeRepository,
)
from collector.rules.definitions import RulesConfig
from collector.rules.engine import RuleEngine
from collector.services.alerting import AlertEvaluationService
from collector.services.metrics_ingestion import MetricsIngestionService
from collector.services.node_registry import NodeRegistryService
from shared.exceptions import AuthenticationError

_bearer_scheme = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> CollectorSettings:
    """Return the ``CollectorSettings`` constructed once at app startup."""
    settings: CollectorSettings = request.app.state.settings
    return settings


def get_rules_config(request: Request) -> RulesConfig:
    """Return the ``RulesConfig`` loaded once at app startup."""
    rules_config: RulesConfig = request.app.state.rules_config
    return rules_config


def get_db_session(request: Request) -> Generator[Session, None, None]:
    """Yield a request-scoped SQLAlchemy session, closed after the request."""
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def verify_api_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    settings: CollectorSettings = Depends(get_settings),
) -> None:
    """Reject the request unless it carries a configured bearer token.

    A per-candidate constant-time comparison (``hmac.compare_digest``)
    avoids leaking token validity through response-timing differences. An
    empty ``token_set`` (dev-only, enforced at settings construction)
    disables auth entirely.
    """
    if not settings.token_set:
        return
    presented = credentials.credentials if credentials is not None else ""
    if not any(hmac.compare_digest(presented, token) for token in settings.token_set):
        raise AuthenticationError("missing or invalid API token")


def get_node_repository(session: Session = Depends(get_db_session)) -> NodeRepository:
    """Provide a ``NodeRepository`` bound to the request's DB session."""
    return SqlAlchemyNodeRepository(session)


def get_metrics_repository(
    session: Session = Depends(get_db_session),
) -> MetricsRepository:
    """Provide a ``MetricsRepository`` bound to the request's DB session."""
    return SqlAlchemyMetricsRepository(session)


def get_alert_repository(session: Session = Depends(get_db_session)) -> AlertRepository:
    """Provide an ``AlertRepository`` bound to the request's DB session."""
    return SqlAlchemyAlertRepository(session)


def get_node_registry_service(
    repository: NodeRepository = Depends(get_node_repository),
    settings: CollectorSettings = Depends(get_settings),
) -> NodeRegistryService:
    """Provide a ``NodeRegistryService`` wired to the request's repository."""
    return NodeRegistryService(
        repository, stale_after_seconds=settings.heartbeat_stale_after_seconds
    )


def get_rule_engine(
    rules_config: RulesConfig = Depends(get_rules_config),
    metrics_repository: MetricsRepository = Depends(get_metrics_repository),
) -> RuleEngine:
    """Provide a ``RuleEngine`` wired to the loaded rules config and repository."""
    return RuleEngine(rules_config, metrics_repository)


def get_alert_evaluation_service(
    rule_engine: RuleEngine = Depends(get_rule_engine),
    alert_repository: AlertRepository = Depends(get_alert_repository),
) -> AlertEvaluationService:
    """Provide an ``AlertEvaluationService`` wired to its dependencies."""
    return AlertEvaluationService(rule_engine, alert_repository)


def get_metrics_ingestion_service(
    metrics_repository: MetricsRepository = Depends(get_metrics_repository),
    node_registry: NodeRegistryService = Depends(get_node_registry_service),
    alert_evaluation: AlertEvaluationService = Depends(get_alert_evaluation_service),
) -> MetricsIngestionService:
    """Provide a ``MetricsIngestionService`` wired to its dependencies."""
    return MetricsIngestionService(metrics_repository, node_registry, alert_evaluation)
