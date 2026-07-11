"""Network metric collection."""

import psutil

from shared.constants import MetricType
from shared.contracts.v1.metrics import MetricSample


class NetworkCollector:
    """Collects cumulative network I/O counters for the local node."""

    def collect(self) -> list[MetricSample]:
        """Return cumulative bytes sent/received since boot.

        These are cumulative counters, not rates — computing a rate from
        successive samples is a downstream (Rule Engine) concern, not the
        collector's.
        """
        counters = psutil.net_io_counters()
        return [
            MetricSample(
                metric_type=MetricType.NETWORK_BYTES_SENT,
                value=float(counters.bytes_sent),
                unit="bytes",
            ),
            MetricSample(
                metric_type=MetricType.NETWORK_BYTES_RECV,
                value=float(counters.bytes_recv),
                unit="bytes",
            ),
        ]
