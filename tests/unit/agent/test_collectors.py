"""Unit tests for psutil-based Agent collectors."""

from agent.collectors.cpu import CpuCollector
from agent.collectors.disk import DiskCollector
from agent.collectors.memory import MemoryCollector
from agent.collectors.network import NetworkCollector
from shared.constants import MetricType


def test_cpu_collector_returns_usage_percent() -> None:
    samples = CpuCollector().collect()
    assert len(samples) == 1
    assert samples[0].metric_type == MetricType.CPU_USAGE_PERCENT
    assert 0.0 <= samples[0].value <= 100.0


def test_memory_collector_returns_expected_metric_types() -> None:
    samples = MemoryCollector().collect()
    metric_types = {s.metric_type for s in samples}
    assert metric_types == {
        MetricType.MEMORY_USAGE_PERCENT,
        MetricType.MEMORY_USED_BYTES,
        MetricType.MEMORY_AVAILABLE_BYTES,
    }


def test_disk_collector_labels_samples_with_mount_point(tmp_path) -> None:
    samples = DiskCollector(mount_path=str(tmp_path)).collect()
    assert len(samples) == 3
    assert all(s.labels["mount_point"] == str(tmp_path) for s in samples)


def test_disk_collector_defaults_to_root_mount() -> None:
    collector = DiskCollector()
    assert collector.mount_path == "/"


def test_network_collector_returns_expected_metric_types() -> None:
    samples = NetworkCollector().collect()
    metric_types = {s.metric_type for s in samples}
    assert metric_types == {
        MetricType.NETWORK_BYTES_SENT,
        MetricType.NETWORK_BYTES_RECV,
    }
