"""CPU metric collection."""

import psutil

from shared.constants import MetricType
from shared.contracts.v1.metrics import MetricSample


class CpuCollector:
    """Collects CPU utilization for the local node.

    ``psutil.cpu_percent`` measures the delta since its *previous* call, so
    the very first call in a process is meaningless (always ``0.0``). The
    constructor makes that first, throwaway call so every subsequent
    ``collect()`` returns a real value.
    """

    def __init__(self) -> None:
        psutil.cpu_percent(interval=None)

    def collect(self) -> list[MetricSample]:
        """Return current CPU usage as a single percentage sample."""
        usage_percent = psutil.cpu_percent(interval=None)
        return [
            MetricSample(
                metric_type=MetricType.CPU_USAGE_PERCENT,
                value=usage_percent,
                unit="percent",
            )
        ]
