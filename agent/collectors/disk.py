"""Disk metric collection."""

import psutil

from shared.constants import DEFAULT_DISK_MOUNT_PATH, MetricType
from shared.contracts.v1.metrics import MetricSample


class DiskCollector:
    """Collects disk usage for a single configured mount point.

    Phase 1 monitors one mount point per Agent (default: ``/``); monitoring
    multiple mount points is a future extension, not implemented here.
    """

    def __init__(self, mount_path: str = DEFAULT_DISK_MOUNT_PATH) -> None:
        self._mount_path = mount_path

    @property
    def mount_path(self) -> str:
        """The mount point this collector reports usage for."""
        return self._mount_path

    def collect(self) -> list[MetricSample]:
        """Return usage percentage, used bytes, and free bytes for the mount point."""
        usage = psutil.disk_usage(self._mount_path)
        labels = {"mount_point": self._mount_path}
        return [
            MetricSample(
                metric_type=MetricType.DISK_USAGE_PERCENT,
                value=usage.percent,
                unit="percent",
                labels=labels,
            ),
            MetricSample(
                metric_type=MetricType.DISK_USED_BYTES,
                value=float(usage.used),
                unit="bytes",
                labels=labels,
            ),
            MetricSample(
                metric_type=MetricType.DISK_FREE_BYTES,
                value=float(usage.free),
                unit="bytes",
                labels=labels,
            ),
        ]
