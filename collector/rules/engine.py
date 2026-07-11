"""RuleEngine: evaluates configured rules against a node's freshly-ingested samples."""

from dataclasses import dataclass
from datetime import datetime

from collector.enums import RuleKind
from collector.repositories.protocols import MetricsRepository
from collector.rules.definitions import (
    RateOfChangeRuleDefinition,
    RulesConfig,
    ThresholdRuleDefinition,
    evaluate_comparison,
)
from shared.constants import Severity
from shared.contracts.v1.metrics import MetricSample


@dataclass(frozen=True)
class RuleEvaluationResult:
    """The outcome of evaluating one rule against one sample.

    ``value`` is the raw metric value for a threshold result, or the
    computed delta for a rate-of-change result; ``bound`` is the
    configured threshold/max_delta it was compared against.
    """

    rule_key: str
    rule_kind: RuleKind
    severity: Severity
    description: str
    breached: bool
    value: float
    bound: float


class RuleEngine:
    """Evaluates the configured Threshold and Rate-of-change rules.

    Rate-of-change rules need a prior sample for the same node/metric, so
    this depends on ``MetricsRepository`` (a Protocol) for that lookup;
    threshold rules need no such lookup.
    """

    def __init__(
        self, rules_config: RulesConfig, metrics_repository: MetricsRepository
    ) -> None:
        self._threshold_rules = {r.metric_type: r for r in rules_config.threshold_rules}
        self._rate_of_change_rules = {
            r.metric_type: r for r in rules_config.rate_of_change_rules
        }
        self._metrics_repository = metrics_repository

    def evaluate(
        self, node_id: str, samples: list[MetricSample], collected_at: datetime
    ) -> list[RuleEvaluationResult]:
        """Evaluate every applicable rule for each of ``samples``."""
        results: list[RuleEvaluationResult] = []
        for sample in samples:
            threshold_rule = self._threshold_rules.get(sample.metric_type)
            if threshold_rule is not None:
                results.append(self._evaluate_threshold(threshold_rule, sample))

            rate_rule = self._rate_of_change_rules.get(sample.metric_type)
            if rate_rule is not None:
                rate_result = self._evaluate_rate_of_change(
                    node_id, rate_rule, sample, collected_at
                )
                if rate_result is not None:
                    results.append(rate_result)
        return results

    def _evaluate_threshold(
        self, rule: ThresholdRuleDefinition, sample: MetricSample
    ) -> RuleEvaluationResult:
        breached = evaluate_comparison(rule.comparison, sample.value, rule.threshold)
        return RuleEvaluationResult(
            rule_key=f"{RuleKind.THRESHOLD.value}:{rule.metric_type.value}",
            rule_kind=RuleKind.THRESHOLD,
            severity=rule.severity,
            description=rule.description,
            breached=breached,
            value=sample.value,
            bound=rule.threshold,
        )

    def _evaluate_rate_of_change(
        self,
        node_id: str,
        rule: RateOfChangeRuleDefinition,
        sample: MetricSample,
        collected_at: datetime,
    ) -> RuleEvaluationResult | None:
        """Compare ``sample`` against the most recent prior sample in the window.

        Returns ``None`` (not a "not breached" result) when there is no
        prior sample to compare against yet — a brand-new node's first
        sample for a metric has nothing to compute a rate from.
        """
        previous = self._metrics_repository.find_previous_sample(
            node_id=node_id,
            metric_type=sample.metric_type,
            before=collected_at,
            window_seconds=rule.window_seconds,
        )
        if previous is None:
            return None
        delta = sample.value - previous.value
        breached = evaluate_comparison(rule.comparison, delta, rule.max_delta)
        return RuleEvaluationResult(
            rule_key=f"{RuleKind.RATE_OF_CHANGE.value}:{rule.metric_type.value}",
            rule_kind=RuleKind.RATE_OF_CHANGE,
            severity=rule.severity,
            description=rule.description,
            breached=breached,
            value=delta,
            bound=rule.max_delta,
        )
