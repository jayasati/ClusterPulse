"""Agent process entrypoint: wiring and lifecycle management."""

import signal
import sys
from types import FrameType

import structlog

from agent.buffer import FileBuffer
from agent.collectors.cpu import CpuCollector
from agent.collectors.disk import DiskCollector
from agent.collectors.memory import MemoryCollector
from agent.collectors.network import NetworkCollector
from agent.config import AgentSettings
from agent.remediation.executor import PlaybookExecutor
from agent.scheduler import AgentScheduler
from agent.transport.http_client import HttpTransport
from shared.exceptions import ConfigurationError
from shared.logging.setup import configure_logging
from shared.protocols import MetricCollector

logger = structlog.get_logger(__name__)

_shutdown_requested = False


def _handle_shutdown_signal(signum: int, frame: FrameType | None) -> None:
    """Mark the process for graceful shutdown on SIGTERM/SIGINT."""
    global _shutdown_requested
    logger.info("shutdown_signal_received", signum=signum)
    _shutdown_requested = True


def _should_stop() -> bool:
    return _shutdown_requested


def build_scheduler(settings: AgentSettings) -> AgentScheduler:
    """Construct an ``AgentScheduler`` wired from validated settings."""
    transport = HttpTransport(
        base_url=settings.collector_base_url,
        timeout_seconds=settings.http_timeout_seconds,
        retry_attempts=settings.http_retry_attempts,
        retry_min_wait_seconds=settings.http_retry_min_wait_seconds,
        retry_max_wait_seconds=settings.http_retry_max_wait_seconds,
        auth_token=settings.auth_token,
    )
    buffer = FileBuffer(
        path=settings.buffer_path, max_entries=settings.buffer_max_entries
    )
    collectors: list[MetricCollector] = [
        CpuCollector(),
        MemoryCollector(),
        DiskCollector(),
        NetworkCollector(),
    ]
    executor = (
        PlaybookExecutor(settings.remediation_allowed_directory_set)
        if settings.remediation_enabled
        else None
    )
    return AgentScheduler(
        node_id=settings.node_id,
        collectors=collectors,
        transport=transport,
        buffer=buffer,
        interval_seconds=settings.collection_interval_seconds,
        executor=executor,
    )


def main() -> None:
    """Load configuration, wire the Agent, and run until a shutdown signal."""
    try:
        settings = AgentSettings()
    except Exception as exc:  # noqa: BLE001 - fail fast on any config error
        print(f"configuration error: {exc}", file=sys.stderr)
        raise ConfigurationError("failed to load agent settings") from exc

    configure_logging(settings)
    signal.signal(signal.SIGTERM, _handle_shutdown_signal)
    signal.signal(signal.SIGINT, _handle_shutdown_signal)

    scheduler = build_scheduler(settings)
    logger.info("agent_starting", node_id=settings.node_id)
    scheduler.run_forever(_should_stop)
    logger.info("agent_stopped")


if __name__ == "__main__":
    main()
