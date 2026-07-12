"""Collector-wide enums shared across the rules, repository, and API layers.

Kept in their own module so ``collector/rules/`` (rule evaluation) and
``collector/repositories/`` (persistence) — two peer packages, neither of
which should depend on the other — can both reference these without an
artificial coupling between them.
"""

from enum import Enum


class RuleKind(str, Enum):
    """Which category of rule produced an evaluation result or alert.

    ``STALENESS`` alerts are not produced by the config-file rule engine —
    they come from the background ``StalenessJob`` (the dead-man switch of
    ``docs/adr/003-heartbeat-deadman-switch.md``, finally acted upon), and
    use the reserved ``staleness:`` rule_key namespace.
    """

    THRESHOLD = "threshold"
    RATE_OF_CHANGE = "rate_of_change"
    STALENESS = "staleness"


class AlertStatus(str, Enum):
    """An alert's position in its lifecycle. See ``docs/adr/006-alert-lifecycle.md``."""

    FIRING = "firing"
    RESOLVED = "resolved"


class RemediationActionStatus(str, Enum):
    """A remediation action's position in its dispatch/execution lifecycle.

    ``BLOCKED_BY_SAFETY_LIMIT`` is a terminal, expected outcome (rate limit
    or cooldown said not yet) — not an error. ``DISPATCHED`` means the
    Collector sent it to the Agent via the next ``Ack`` and is awaiting a
    result; ``EXECUTED``/``FAILED`` are terminal states the Agent reports
    back via ``POST /api/v1/remediation-actions/{id}/result``.
    """

    BLOCKED_BY_SAFETY_LIMIT = "blocked_by_safety_limit"
    DISPATCHED = "dispatched"
    EXECUTED = "executed"
    FAILED = "failed"
