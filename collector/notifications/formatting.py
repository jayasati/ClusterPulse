"""Formats an alert into a human-readable Telegram notification message.

Takes a structural ``_AlertLike`` rather than importing
``collector.services.alerting.AlertView`` directly — ``collector/services/``
calls into ``collector/notifications/`` (for ``Notifier``), so the reverse
import would be circular. ``AlertRecord`` (repositories) and ``AlertView``
(services) both already have every field these functions need.
"""

from typing import Protocol

from shared.constants import Severity


class _AlertLike(Protocol):
    """Read-only attribute shape — both ``AlertRecord`` (frozen dataclass)
    and ``AlertView`` satisfy this. Declared via properties, not plain
    annotations, so a frozen dataclass's read-only fields structurally
    match (a plain annotation would require a *settable* attribute)."""

    @property
    def id(self) -> int: ...
    @property
    def node_id(self) -> str: ...
    @property
    def severity(self) -> Severity: ...
    @property
    def description(self) -> str: ...
    @property
    def triggering_value(self) -> float: ...
    @property
    def bound(self) -> float: ...


_SEVERITY_ICONS = {Severity.CRITICAL: "\U0001f534", Severity.WARNING: "\U0001f7e1"}


def format_opened(alert: _AlertLike) -> str:
    """Render the message sent when an alert first starts firing."""
    icon = _SEVERITY_ICONS[alert.severity]
    return (
        f"{icon} ALERT #{alert.id} [{alert.severity.value.upper()}] {alert.node_id}: "
        f"{alert.description} (value={alert.triggering_value}, bound={alert.bound})"
    )


def format_escalated(alert: _AlertLike) -> str:
    """Render the message sent when a still-firing, unacknowledged alert escalates."""
    return (
        f"\U0001f53a ESCALATED ALERT #{alert.id} — still firing and unacknowledged "
        f"[{alert.severity.value.upper()}] {alert.node_id}: {alert.description}"
    )


def format_resolved(alert: _AlertLike) -> str:
    """Render the message sent when an alert resolves."""
    return (
        f"✅ RESOLVED ALERT #{alert.id} [{alert.severity.value.upper()}] "
        f"{alert.node_id}: {alert.description}"
    )
