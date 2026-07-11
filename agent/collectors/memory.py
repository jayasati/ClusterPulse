"""Memory metric collection."""

import psutil

from shared.constants import MetricType
from shared.contracts.v1.metrics import MetricSample


class MemoryCollector:
    """Collects virtual memory utilization for the local node."""

    def collect(self) -> list[MetricSample]:
        """Return current memory usage percentage, used bytes, and available bytes."""
        vm = psutil.virtual_memory()
        return [
            MetricSample(
                metric_type=MetricType.MEMORY_USAGE_PERCENT,
                value=vm.percent,
                unit="percent",
            ),
            MetricSample(
                metric_type=MetricType.MEMORY_USED_BYTES,
                value=float(vm.used),
                unit="bytes",
            ),
            MetricSample(
                metric_type=MetricType.MEMORY_AVAILABLE_BYTES,
                value=float(vm.available),
                unit="bytes",
            ),
        ]
