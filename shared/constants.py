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
