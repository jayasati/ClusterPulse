"""RemediationEngine: decides whether an escalated alert should dispatch a Playbook."""

from datetime import datetime, timedelta

import structlog

from collector.enums import RemediationActionStatus
from collector.remediation.definitions import PlaybookDefinition, RemediationPolicy
from collector.repositories.protocols import (
    RemediationActionRecord,
    RemediationActionRepository,
)

logger = structlog.get_logger(__name__)


class RemediationEngine:
    """Applies Safety Limits before dispatching a Playbook for an escalated alert.

    Reuses the same "the alert has escalated" moment ``AlertEvaluationService``
    already computes as the sole remediation trigger — Playbooks are never
    considered on open or on a plain still-firing advance, only once a human
    has already had a chance to intervene. See
    ``docs/adr/007-remediation-safety.md``.
    """

    def __init__(
        self,
        policy: RemediationPolicy,
        action_repository: RemediationActionRepository,
        enabled: bool,
        max_actions_per_node_per_hour: int,
        cooldown_seconds: float,
    ) -> None:
        self._by_rule_key = {p.rule_key: p for p in policy.playbooks}
        self._action_repository = action_repository
        self._enabled = enabled
        self._max_actions_per_node_per_hour = max_actions_per_node_per_hour
        self._cooldown_seconds = cooldown_seconds

    def decide(
        self, node_id: str, alert_id: int, rule_key: str, now: datetime
    ) -> RemediationActionRecord | None:
        """Return the recorded decision for this escalation.

        Returns ``None`` (no audit record at all) if remediation is
        disabled, or no Playbook is mapped to ``rule_key`` — most
        escalations have no Playbook and that is not itself notable.
        """
        if not self._enabled:
            return None
        playbook = self._by_rule_key.get(rule_key)
        if playbook is None:
            return None

        blocked_reason = self._check_safety_limits(node_id, playbook, now)
        status = (
            RemediationActionStatus.BLOCKED_BY_SAFETY_LIMIT
            if blocked_reason is not None
            else RemediationActionStatus.DISPATCHED
        )
        self._log_decision(node_id, playbook, status, blocked_reason)
        return self._action_repository.create_action(
            node_id=node_id,
            alert_id=alert_id,
            rule_key=rule_key,
            playbook_name=playbook.playbook_name,
            action_type=playbook.action_type,
            parameters=playbook.parameters,
            status=status,
            reason=blocked_reason,
            created_at=now,
        )

    def _check_safety_limits(
        self, node_id: str, playbook: PlaybookDefinition, now: datetime
    ) -> str | None:
        last = self._action_repository.find_last_action(node_id, playbook.playbook_name)
        if last is not None:
            elapsed = (now - last.created_at).total_seconds()
            if elapsed < self._cooldown_seconds:
                return (
                    f"cooldown active: {elapsed:.0f}s of "
                    f"{self._cooldown_seconds:.0f}s since last action"
                )

        since = now - timedelta(hours=1)
        recent_count = self._action_repository.count_recent_actions(node_id, since)
        if recent_count >= self._max_actions_per_node_per_hour:
            return (
                f"rate limit reached: {recent_count} actions in the last hour "
                f"(max {self._max_actions_per_node_per_hour})"
            )
        return None

    def _log_decision(
        self,
        node_id: str,
        playbook: PlaybookDefinition,
        status: RemediationActionStatus,
        reason: str | None,
    ) -> None:
        event = (
            "remediation_blocked_by_safety_limit"
            if status == RemediationActionStatus.BLOCKED_BY_SAFETY_LIMIT
            else "remediation_dispatched"
        )
        logger.warning(
            event,
            node_id=node_id,
            playbook_name=playbook.playbook_name,
            action_type=playbook.action_type.value,
            reason=reason,
        )
