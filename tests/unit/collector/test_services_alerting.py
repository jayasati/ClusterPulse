"""Unit tests for AlertEvaluationService, using fakes for RuleEngine/AlertRepository."""

from datetime import datetime, timezone

import pytest

from collector.enums import AlertStatus, RuleKind
from collector.exceptions import AlertNotFoundError
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

    def get(self, alert_id):
        return self._alerts.get(alert_id)

    def list_alerts(self, status=None):
        values = list(self._alerts.values())
        if status is None:
            return values
        return [a for a in values if a.status == status]


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
