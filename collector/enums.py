"""Collector-wide enums shared across the rules, repository, and API layers.

Kept in their own module so ``collector/rules/`` (rule evaluation) and
``collector/repositories/`` (persistence) — two peer packages, neither of
which should depend on the other — can both reference these without an
artificial coupling between them.
"""

from enum import Enum


class RuleKind(str, Enum):
    """Which category of rule produced an evaluation result or alert."""

    THRESHOLD = "threshold"
    RATE_OF_CHANGE = "rate_of_change"


class AlertStatus(str, Enum):
    """An alert's position in its lifecycle. See ``docs/adr/006-alert-lifecycle.md``."""

    FIRING = "firing"
    RESOLVED = "resolved"
