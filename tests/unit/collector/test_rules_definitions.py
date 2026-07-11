"""Unit tests for rule configuration models and comparison evaluation."""

import pytest
from pydantic import ValidationError

from collector.rules.definitions import (
    ComparisonOperator,
    RateOfChangeRuleDefinition,
    RulesConfig,
    ThresholdRuleDefinition,
    evaluate_comparison,
)
from shared.constants import MetricType, Severity


@pytest.mark.parametrize(
    "operator, value, bound, expected",
    [
        (ComparisonOperator.GREATER_THAN, 10.0, 5.0, True),
        (ComparisonOperator.GREATER_THAN, 5.0, 10.0, False),
        (ComparisonOperator.GREATER_THAN_OR_EQUAL, 5.0, 5.0, True),
        (ComparisonOperator.LESS_THAN, 3.0, 5.0, True),
        (ComparisonOperator.LESS_THAN, 5.0, 5.0, False),
        (ComparisonOperator.LESS_THAN_OR_EQUAL, 5.0, 5.0, True),
    ],
)
def test_evaluate_comparison(operator, value, bound, expected) -> None:
    assert evaluate_comparison(operator, value, bound) is expected


def _threshold_rule(metric_type: MetricType = MetricType.CPU_USAGE_PERCENT) -> dict:
    return {
        "metric_type": metric_type,
        "comparison": "gt",
        "threshold": 90.0,
        "severity": "critical",
        "description": "test rule",
    }


def _rate_rule(metric_type: MetricType = MetricType.CPU_USAGE_PERCENT) -> dict:
    return {
        "metric_type": metric_type,
        "comparison": "gt",
        "max_delta": 20.0,
        "window_seconds": 300.0,
        "severity": "warning",
        "description": "test rate rule",
    }


def test_threshold_rule_definition_parses() -> None:
    rule = ThresholdRuleDefinition(**_threshold_rule())
    assert rule.metric_type == MetricType.CPU_USAGE_PERCENT
    assert rule.severity == Severity.CRITICAL


def test_rate_of_change_rule_definition_parses() -> None:
    rule = RateOfChangeRuleDefinition(**_rate_rule())
    assert rule.window_seconds == 300.0


def test_rules_config_defaults_to_empty() -> None:
    config = RulesConfig()
    assert config.threshold_rules == []
    assert config.rate_of_change_rules == []


def test_rules_config_allows_same_metric_type_across_different_kinds() -> None:
    config = RulesConfig(
        threshold_rules=[_threshold_rule()], rate_of_change_rules=[_rate_rule()]
    )
    assert len(config.threshold_rules) == 1
    assert len(config.rate_of_change_rules) == 1


def test_rules_config_rejects_duplicate_threshold_metric_type() -> None:
    with pytest.raises(ValidationError):
        RulesConfig(threshold_rules=[_threshold_rule(), _threshold_rule()])


def test_rules_config_rejects_duplicate_rate_of_change_metric_type() -> None:
    with pytest.raises(ValidationError):
        RulesConfig(rate_of_change_rules=[_rate_rule(), _rate_rule()])
