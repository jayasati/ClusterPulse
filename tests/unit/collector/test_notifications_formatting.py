"""Unit tests for alert notification message formatting."""

from dataclasses import dataclass

from collector.notifications.formatting import (
    format_escalated,
    format_opened,
    format_resolved,
)
from shared.constants import Severity


@dataclass
class _FakeAlert:
    id: int
    node_id: str
    severity: Severity
    description: str
    triggering_value: float
    bound: float


def _alert(severity: Severity = Severity.CRITICAL) -> _FakeAlert:
    return _FakeAlert(
        id=42,
        node_id="node-1",
        severity=severity,
        description="CPU usage above 90%",
        triggering_value=95.0,
        bound=90.0,
    )


def test_format_opened_includes_alert_id_node_and_values() -> None:
    message = format_opened(_alert())
    assert "#42" in message
    assert "node-1" in message
    assert "CRITICAL" in message
    assert "95.0" in message
    assert "90.0" in message


def test_format_opened_uses_different_icon_per_severity() -> None:
    critical_message = format_opened(_alert(Severity.CRITICAL))
    warning_message = format_opened(_alert(Severity.WARNING))
    assert critical_message != warning_message


def test_format_escalated_mentions_escalation() -> None:
    message = format_escalated(_alert())
    assert "ESCALATED" in message
    assert "#42" in message
    assert "unacknowledged" in message


def test_format_resolved_mentions_resolution() -> None:
    message = format_resolved(_alert())
    assert "RESOLVED" in message
    assert "#42" in message
    assert "node-1" in message
