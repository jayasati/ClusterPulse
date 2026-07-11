"""Unit tests for RuleEngine, using a fake MetricsRepository."""

from datetime import datetime, timezone

from collector.enums import RuleKind
from collector.repositories.protocols import MetricSampleRecord
from collector.rules.definitions import (
    RateOfChangeRuleDefinition,
    RulesConfig,
    ThresholdRuleDefinition,
)
from collector.rules.engine import RuleEngine
from shared.constants import MetricType, Severity
from shared.contracts.v1.metrics import MetricSample


class _FakeMetricsRepository:
    def __init__(self, previous: MetricSampleRecord | None = None) -> None:
        self._previous = previous
        self.calls: list[tuple] = []

    def bulk_insert(self, *args, **kwargs) -> None:
        raise NotImplementedError

    def find_previous_sample(self, node_id, metric_type, before, window_seconds):
        self.calls.append((node_id, metric_type, before, window_seconds))
        return self._previous


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sample(metric_type: MetricType, value: float) -> MetricSample:
    return MetricSample(metric_type=metric_type, value=value, unit="percent")


def _threshold_config() -> RulesConfig:
    return RulesConfig(
        threshold_rules=[
            ThresholdRuleDefinition(
                metric_type=MetricType.CPU_USAGE_PERCENT,
                comparison="gt",
                threshold=90.0,
                severity=Severity.CRITICAL,
                description="CPU too high",
            )
        ]
    )


def test_threshold_rule_breached() -> None:
    engine = RuleEngine(_threshold_config(), _FakeMetricsRepository())

    results = engine.evaluate(
        "node-1", [_sample(MetricType.CPU_USAGE_PERCENT, 95.0)], _now()
    )

    assert len(results) == 1
    assert results[0].breached is True
    assert results[0].rule_kind == RuleKind.THRESHOLD
    assert results[0].rule_key == "threshold:cpu.usage_percent"


def test_threshold_rule_not_breached() -> None:
    engine = RuleEngine(_threshold_config(), _FakeMetricsRepository())

    results = engine.evaluate(
        "node-1", [_sample(MetricType.CPU_USAGE_PERCENT, 10.0)], _now()
    )

    assert len(results) == 1
    assert results[0].breached is False


def test_no_rule_configured_for_metric_type_produces_no_result() -> None:
    engine = RuleEngine(RulesConfig(), _FakeMetricsRepository())

    results = engine.evaluate(
        "node-1", [_sample(MetricType.CPU_USAGE_PERCENT, 95.0)], _now()
    )

    assert results == []


def _rate_config() -> RulesConfig:
    return RulesConfig(
        rate_of_change_rules=[
            RateOfChangeRuleDefinition(
                metric_type=MetricType.MEMORY_USAGE_PERCENT,
                comparison="gt",
                max_delta=20.0,
                window_seconds=300.0,
                severity=Severity.WARNING,
                description="Memory jumped",
            )
        ]
    )


def test_rate_of_change_breached_with_prior_sample() -> None:
    previous = MetricSampleRecord(
        node_id="node-1",
        metric_type=MetricType.MEMORY_USAGE_PERCENT,
        value=50.0,
        unit="percent",
        labels={},
        collected_at=_now(),
        received_at=_now(),
    )
    repo = _FakeMetricsRepository(previous=previous)
    engine = RuleEngine(_rate_config(), repo)

    results = engine.evaluate(
        "node-1", [_sample(MetricType.MEMORY_USAGE_PERCENT, 80.0)], _now()
    )

    assert len(results) == 1
    assert results[0].breached is True
    assert results[0].value == 30.0  # delta
    assert results[0].rule_kind == RuleKind.RATE_OF_CHANGE
    assert repo.calls[0][0] == "node-1"


def test_rate_of_change_not_breached_below_max_delta() -> None:
    previous = MetricSampleRecord(
        node_id="node-1",
        metric_type=MetricType.MEMORY_USAGE_PERCENT,
        value=50.0,
        unit="percent",
        labels={},
        collected_at=_now(),
        received_at=_now(),
    )
    repo = _FakeMetricsRepository(previous=previous)
    engine = RuleEngine(_rate_config(), repo)

    results = engine.evaluate(
        "node-1", [_sample(MetricType.MEMORY_USAGE_PERCENT, 55.0)], _now()
    )

    assert results[0].breached is False


def test_rate_of_change_with_no_prior_sample_produces_no_result() -> None:
    repo = _FakeMetricsRepository(previous=None)
    engine = RuleEngine(_rate_config(), repo)

    results = engine.evaluate(
        "node-1", [_sample(MetricType.MEMORY_USAGE_PERCENT, 80.0)], _now()
    )

    assert results == []


def test_both_threshold_and_rate_of_change_can_apply_to_same_metric_type() -> None:
    previous = MetricSampleRecord(
        node_id="node-1",
        metric_type=MetricType.CPU_USAGE_PERCENT,
        value=10.0,
        unit="percent",
        labels={},
        collected_at=_now(),
        received_at=_now(),
    )
    config = RulesConfig(
        threshold_rules=_threshold_config().threshold_rules,
        rate_of_change_rules=[
            RateOfChangeRuleDefinition(
                metric_type=MetricType.CPU_USAGE_PERCENT,
                comparison="gt",
                max_delta=20.0,
                window_seconds=300.0,
                severity=Severity.WARNING,
                description="CPU jumped",
            )
        ],
    )
    engine = RuleEngine(config, _FakeMetricsRepository(previous=previous))

    results = engine.evaluate(
        "node-1", [_sample(MetricType.CPU_USAGE_PERCENT, 95.0)], _now()
    )

    assert len(results) == 2
    kinds = {r.rule_kind for r in results}
    assert kinds == {RuleKind.THRESHOLD, RuleKind.RATE_OF_CHANGE}
