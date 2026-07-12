"""Project-wide constants shared by the Agent and the Collector.

Named here so no module reaches for a magic number or a bare string literal
(``.claude/CODING_STANDARDS.md``: "No magic numbers").
"""

from enum import Enum


class MetricType(str, Enum):
    """Enumerates every metric sample kind an Agent collector can produce."""

    CPU_USAGE_PERCENT = "cpu.usage_percent"
    MEMORY_USAGE_PERCENT = "memory.usage_percent"
    MEMORY_USED_BYTES = "memory.used_bytes"
    MEMORY_AVAILABLE_BYTES = "memory.available_bytes"
    DISK_USAGE_PERCENT = "disk.usage_percent"
    DISK_USED_BYTES = "disk.used_bytes"
    DISK_FREE_BYTES = "disk.free_bytes"
    NETWORK_BYTES_SENT = "network.bytes_sent"
    NETWORK_BYTES_RECV = "network.bytes_recv"


class Severity(str, Enum):
    """How urgently an alert condition demands attention.

    Deferred out of this module until the Rule Engine (Phase 3) had a real
    consumer for it — see ``shared/architecture.md`` Future Extension Notes.
    """

    WARNING = "warning"
    CRITICAL = "critical"


DEFAULT_DISK_MOUNT_PATH: str = "/"

DEFAULT_COLLECTION_INTERVAL_SECONDS: float = 30.0

DEFAULT_HTTP_TIMEOUT_SECONDS: float = 10.0
DEFAULT_HTTP_RETRY_ATTEMPTS: int = 3
DEFAULT_HTTP_RETRY_MIN_WAIT_SECONDS: float = 1.0
DEFAULT_HTTP_RETRY_MAX_WAIT_SECONDS: float = 10.0

DEFAULT_BUFFER_MAX_ENTRIES: int = 1000
DEFAULT_BUFFER_DRAIN_BATCH_SIZE: int = 50

HTTP_CLIENT_ERROR_THRESHOLD: int = 400
HTTP_SERVER_ERROR_THRESHOLD: int = 500

DEFAULT_HEARTBEAT_STALE_AFTER_SECONDS: float = 90.0

DEFAULT_ESCALATION_AFTER_SECONDS: float = 900.0

DEFAULT_REMEDIATION_AFTER_SECONDS: float = 1800.0
DEFAULT_MAX_REMEDIATIONS_PER_NODE_PER_HOUR: int = 3
DEFAULT_REMEDIATION_COOLDOWN_SECONDS: float = 1800.0

DEFAULT_STALENESS_CHECK_INTERVAL_SECONDS: float = 60.0
DEFAULT_RECONCILIATION_INTERVAL_SECONDS: float = 300.0
DEFAULT_REMEDIATION_DISPATCH_TIMEOUT_SECONDS: float = 1800.0

DEFAULT_METRICS_RETENTION_DAYS: int = 7
DEFAULT_RESOLVED_ALERTS_RETENTION_DAYS: int = 30
DEFAULT_REMEDIATION_ACTIONS_RETENTION_DAYS: int = 90
DEFAULT_RETENTION_INTERVAL_SECONDS: float = 3600.0
DEFAULT_RETENTION_BATCH_SIZE: int = 10_000
