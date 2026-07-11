"""Unit tests for AlertEvaluationService, using fakes for RuleEngine/AlertRepository."""

from datetime import datetime, timedelta, timezone

import pytest

from collector.enums import AlertStatus, RuleKind
from collector.exceptions import AlertAlreadyResolvedError, AlertNotFoundError
from collector.repositories.protocols import AlertRecord
from collector.rules.engine import RuleEvaluationResult
from collector.services.alerting import AlertEvaluationService
from shared.constants import Severity


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _FakeRuleEngine:
    def __init__(self, results: list[RuleEvaluationResult]) -> None:
        self._results = results

    def evaluate(self, node_id, samples, collected_at):
        return self._results


class _FakeAlertRepository:
    def __init__(self) -> None:
        self._alerts: dict[int, AlertRecord] = {}
        self._next_id = 1

    def find_open_alert(self, node_id, rule_key):
        for record in self._alerts.values():
            if (
                record.node_id == node_id
                and record.rule_key == rule_key
                and record.status == AlertStatus.FIRING
            ):
                return record
        return None

    def create_alert(
        self,
        node_id,
        rule_key,
        rule_kind,
        severity,
        description,
        triggering_value,
        bound,
        fired_at,
    ):
        record = AlertRecord(
            id=self._next_id,
            node_id=node_id,
            rule_key=rule_key,
            rule_kind=rule_kind,
            severity=severity,
            status=AlertStatus.FIRING,
            description=description,
            triggering_value=triggering_value,
            bound=bound,
            first_fired_at=fired_at,
            last_fired_at=fired_at,
            resolved_at=None,
        )
        self._alerts[self._next_id] = record
        self._next_id += 1
        return record

    def update_last_fired(self, alert_id, triggering_value, fired_at):
        record = self._alerts[alert_id]
        updated = AlertRecord(
            **{
                **record.__dict__,
                "triggering_value": triggering_value,
                "last_fired_at": fired_at,
            }
        )
        self._alerts[alert_id] = updated
        return updated

    def resolve_alert(self, alert_id, resolved_at):
        record = self._alerts[alert_id]
        updated = AlertRecord(
            **{
                **record.__dict__,
                "status": AlertStatus.RESOLVED,
                "resolved_at": resolved_at,
            }
        )
        self._alerts[alert_id] = updated
        return updated

    def acknowledge_alert(self, alert_id, acknowledged_by, acknowledged_at):
        record = self._alerts[alert_id]
        updated = AlertRecord(
            **{
                **record.__dict__,
                "acknowledged_by": acknowledged_by,
                "acknowledged_at": acknowledged_at,
            }
        )
        self._alerts[alert_id] = updated
        return updated

    def escalate_alert(self, alert_id, escalated_at):
        record = self._alerts[alert_id]
        updated = AlertRecord(**{**record.__dict__, "escalated_at": escalated_at})
        self._alerts[alert_id] = updated
        return updated

    def get(self, alert_id):
        return self._alerts.get(alert_id)

    def list_alerts(self, status=None):
        values = list(self._alerts.values())
        if status is None:
            return values
        return [a for a in values if a.status == status]


class _FakeNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def notify(self, message: str) -> bool:
        self.messages.append(message)
        return True


def _result(
    breached: bool, rule_key: str = "threshold:cpu.usage_percent"
) -> RuleEvaluationResult:
    return RuleEvaluationResult(
        rule_key=rule_key,
        rule_kind=RuleKind.THRESHOLD,
        severity=Severity.CRITICAL,
        description="CPU too high",
        breached=breached,
        value=95.0,
        bound=90.0,
    )


def test_breach_with_no_open_alert_opens_one() -> None:
    service = AlertEvaluationService(
        _FakeRuleEngine([_result(True)]), _FakeAlertRepository()
    )

    transitions = service.evaluate_and_apply("node-1", [], _now())

    assert len(transitions) == 1
    assert transitions[0].status == AlertStatus.FIRING


def test_continued_breach_advances_existing_alert_not_a_new_one() -> None:
    alert_repo = _FakeAlertRepository()
    service = AlertEvaluationService(_FakeRuleEngine([_result(True)]), alert_repo)
    service.evaluate_and_apply("node-1", [], _now())

    service.evaluate_and_apply("node-1", [], _now())

    assert len(alert_repo.list_alerts()) == 1


def test_no_longer_breaching_resolves_open_alert() -> None:
    alert_repo = _FakeAlertRepository()
    rule_engine = _FakeRuleEngine([_result(True)])
    service = AlertEvaluationService(rule_engine, alert_repo)
    service.evaluate_and_apply("node-1", [], _now())

    rule_engine._results = [_result(False)]
    transitions = service.evaluate_and_apply("node-1", [], _now())

    assert transitions[0].status == AlertStatus.RESOLVED


def test_not_breached_with_no_open_alert_produces_no_transition() -> None:
    service = AlertEvaluationService(
        _FakeRuleEngine([_result(False)]), _FakeAlertRepository()
    )

    transitions = service.evaluate_and_apply("node-1", [], _now())

    assert transitions == []


def test_get_alert_raises_not_found_for_unknown_id() -> None:
    service = AlertEvaluationService(_FakeRuleEngine([]), _FakeAlertRepository())

    with pytest.raises(AlertNotFoundError):
        service.get_alert(999)


def test_get_alert_returns_view_for_known_id() -> None:
    alert_repo = _FakeAlertRepository()
    service = AlertEvaluationService(_FakeRuleEngine([_result(True)]), alert_repo)
    service.evaluate_and_apply("node-1", [], _now())

    view = service.get_alert(1)

    assert view.id == 1


def test_list_alerts_filters_by_status() -> None:
    alert_repo = _FakeAlertRepository()
    service = AlertEvaluationService(
        _FakeRuleEngine(
            [_result(True), _result(True, rule_key="threshold:memory.usage_percent")]
        ),
        alert_repo,
    )
    service.evaluate_and_apply("node-1", [], _now())

    assert len(service.list_alerts()) == 2
    assert len(service.list_alerts(status=AlertStatus.FIRING)) == 2
    assert len(service.list_alerts(status=AlertStatus.RESOLVED)) == 0


# --- Acknowledgement ---------------------------------------------------


def test_acknowledge_sets_who_and_when() -> None:
    alert_repo = _FakeAlertRepository()
    service = AlertEvaluationService(_FakeRuleEngine([_result(True)]), alert_repo)
    service.evaluate_and_apply("node-1", [], _now())

    view = service.acknowledge(1, acknowledged_by="alice")

    assert view.acknowledged_by == "alice"
    assert view.acknowledged_at is not None
    assert view.status == AlertStatus.FIRING


def test_acknowledge_unknown_alert_raises_not_found() -> None:
    service = AlertEvaluationService(_FakeRuleEngine([]), _FakeAlertRepository())

    with pytest.raises(AlertNotFoundError):
        service.acknowledge(999, acknowledged_by="alice")


def test_acknowledge_resolved_alert_raises_already_resolved() -> None:
    alert_repo = _FakeAlertRepository()
    rule_engine = _FakeRuleEngine([_result(True)])
    service = AlertEvaluationService(rule_engine, alert_repo)
    service.evaluate_and_apply("node-1", [], _now())
    rule_engine._results = [_result(False)]
    service.evaluate_and_apply("node-1", [], _now())

    with pytest.raises(AlertAlreadyResolvedError):
        service.acknowledge(1, acknowledged_by="alice")


def test_acknowledge_is_overwritable() -> None:
    alert_repo = _FakeAlertRepository()
    service = AlertEvaluationService(_FakeRuleEngine([_result(True)]), alert_repo)
    service.evaluate_and_apply("node-1", [], _now())
    service.acknowledge(1, acknowledged_by="alice")

    view = service.acknowledge(1, acknowledged_by="bob")

    assert view.acknowledged_by == "bob"


# --- Notifications (dedup: only on open/escalate/resolve) --------------


def test_notifier_called_on_open() -> None:
    notifier = _FakeNotifier()
    service = AlertEvaluationService(
        _FakeRuleEngine([_result(True)]), _FakeAlertRepository(), notifier=notifier
    )

    service.evaluate_and_apply("node-1", [], _now())

    assert len(notifier.messages) == 1
    assert "#1" in notifier.messages[0]


def test_notifier_not_called_again_on_continued_breach() -> None:
    notifier = _FakeNotifier()
    service = AlertEvaluationService(
        _FakeRuleEngine([_result(True)]), _FakeAlertRepository(), notifier=notifier
    )
    service.evaluate_and_apply("node-1", [], _now())

    service.evaluate_and_apply("node-1", [], _now())

    assert len(notifier.messages) == 1


def test_notifier_called_on_resolve() -> None:
    notifier = _FakeNotifier()
    rule_engine = _FakeRuleEngine([_result(True)])
    service = AlertEvaluationService(
        rule_engine, _FakeAlertRepository(), notifier=notifier
    )
    service.evaluate_and_apply("node-1", [], _now())

    rule_engine._results = [_result(False)]
    service.evaluate_and_apply("node-1", [], _now())

    assert len(notifier.messages) == 2
    assert "RESOLVED" in notifier.messages[1]


def test_works_without_a_notifier() -> None:
    """Backward compatible: notifier defaults to None."""
    service = AlertEvaluationService(
        _FakeRuleEngine([_result(True)]), _FakeAlertRepository()
    )

    transitions = service.evaluate_and_apply("node-1", [], _now())  # must not raise

    assert len(transitions) == 1


# --- Escalation ----------------------------------------------------------


def test_escalation_triggers_after_threshold_and_notifies() -> None:
    notifier = _FakeNotifier()
    service = AlertEvaluationService(
        _FakeRuleEngine([_result(True)]),
        _FakeAlertRepository(),
        notifier=notifier,
        escalation_after_seconds=60,
    )
    start = _now()
    service.evaluate_and_apply("node-1", [], start)

    later = start + timedelta(seconds=61)
    view = service.evaluate_and_apply("node-1", [], later)[0]

    assert view.escalated_at is not None
    assert len(notifier.messages) == 2
    assert "ESCALATED" in notifier.messages[1]


def test_escalation_does_not_trigger_before_threshold() -> None:
    notifier = _FakeNotifier()
    service = AlertEvaluationService(
        _FakeRuleEngine([_result(True)]),
        _FakeAlertRepository(),
        notifier=notifier,
        escalation_after_seconds=600,
    )
    start = _now()
    service.evaluate_and_apply("node-1", [], start)

    soon = start + timedelta(seconds=10)
    view = service.evaluate_and_apply("node-1", [], soon)[0]

    assert view.escalated_at is None
    assert len(notifier.messages) == 1


def test_escalation_skipped_when_acknowledged() -> None:
    service = AlertEvaluationService(
        _FakeRuleEngine([_result(True)]),
        _FakeAlertRepository(),
        escalation_after_seconds=60,
    )
    start = _now()
    service.evaluate_and_apply("node-1", [], start)
    service.acknowledge(1, acknowledged_by="alice")

    later = start + timedelta(seconds=61)
    view = service.evaluate_and_apply("node-1", [], later)[0]

    assert view.escalated_at is None


def test_escalation_happens_only_once() -> None:
    service = AlertEvaluationService(
        _FakeRuleEngine([_result(True)]),
        _FakeAlertRepository(),
        escalation_after_seconds=60,
    )
    start = _now()
    service.evaluate_and_apply("node-1", [], start)
    first_escalation = start + timedelta(seconds=61)
    first_view = service.evaluate_and_apply("node-1", [], first_escalation)[0]

    much_later = start + timedelta(seconds=1000)
    second_view = service.evaluate_and_apply("node-1", [], much_later)[0]

    assert first_view.escalated_at == second_view.escalated_at
