"""Rule configuration models — what a "Threshold Rule" or "Rate-of-change
Rule" is. Loaded from a JSON file (``collector/rules/loader.py``), not a
database — see ``docs/adr/006-alert-lifecycle.md`` for why static,
config-file-driven rules were chosen over a dynamic rule-management API.
"""

from enum import Enum
from typing import Callable

from pydantic import BaseModel, Field, model_validator

from shared.constants import MetricType, Severity


class ComparisonOperator(str, Enum):
    """How a measured value is compared against a configured bound."""

    GREATER_THAN = "gt"
    GREATER_THAN_OR_EQUAL = "gte"
    LESS_THAN = "lt"
    LESS_THAN_OR_EQUAL = "lte"


_COMPARISON_FUNCS: dict[ComparisonOperator, Callable[[float, float], bool]] = {
    ComparisonOperator.GREATER_THAN: lambda value, bound: value > bound,
    ComparisonOperator.GREATER_THAN_OR_EQUAL: lambda value, bound: value >= bound,
    ComparisonOperator.LESS_THAN: lambda value, bound: value < bound,
    ComparisonOperator.LESS_THAN_OR_EQUAL: lambda value, bound: value <= bound,
}


def evaluate_comparison(
    operator: ComparisonOperator, value: float, bound: float
) -> bool:
    """Apply ``operator`` to ``value`` against ``bound``."""
    return _COMPARISON_FUNCS[operator](value, bound)


class ThresholdRuleDefinition(BaseModel):
    """Fires when a metric's raw value crosses a fixed bound."""

    metric_type: MetricType
    comparison: ComparisonOperator
    threshold: float
    severity: Severity
    description: str


class RateOfChangeRuleDefinition(BaseModel):
    """Fires when a metric changes by more than ``max_delta`` within ``window_seconds``."""

    metric_type: MetricType
    comparison: ComparisonOperator
    max_delta: float
    window_seconds: float
    severity: Severity
    description: str


class RulesConfig(BaseModel):
    """The full set of configured rules, loaded once at Collector startup.

    At most one threshold rule and one rate-of-change rule are allowed per
    ``metric_type`` (checked independently per list) — this keeps each
    alert's ``rule_key`` (``"{kind}:{metric_type}"``) unambiguous.
    """

    threshold_rules: list[ThresholdRuleDefinition] = Field(default_factory=list)
    rate_of_change_rules: list[RateOfChangeRuleDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def _no_duplicate_metric_types_per_kind(self) -> "RulesConfig":
        _assert_unique_metric_types(self.threshold_rules, "threshold_rules")
        _assert_unique_metric_types(self.rate_of_change_rules, "rate_of_change_rules")
        return self


def _assert_unique_metric_types(
    rules: list[ThresholdRuleDefinition] | list[RateOfChangeRuleDefinition],
    field_name: str,
) -> None:
    seen: set[MetricType] = set()
    for rule in rules:
        if rule.metric_type in seen:
            raise ValueError(
                f"duplicate rule for metric_type={rule.metric_type!r} in {field_name}"
            )
        seen.add(rule.metric_type)
