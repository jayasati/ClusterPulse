"""Agent process configuration."""

import socket

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from shared.config.base import BaseServiceSettings
from shared.constants import (
    DEFAULT_BUFFER_MAX_ENTRIES,
    DEFAULT_COLLECTION_INTERVAL_SECONDS,
    DEFAULT_HTTP_RETRY_ATTEMPTS,
    DEFAULT_HTTP_RETRY_MAX_WAIT_SECONDS,
    DEFAULT_HTTP_RETRY_MIN_WAIT_SECONDS,
    DEFAULT_HTTP_TIMEOUT_SECONDS,
)


def _default_node_id() -> str:
    """Fall back to the local hostname when no explicit node id is configured.

    Not collision-proof across cloned VM images — see ``docs/adr/003-heartbeat-deadman-switch.md``
    and the Phase 2 node registry for a stronger identity mechanism.
    """
    return socket.gethostname()


class AgentSettings(BaseServiceSettings):
    """Configuration for the ClusterPulse Agent process.

    Loaded from environment variables prefixed ``CLUSTERPULSE_AGENT_``, or a
    local ``.env`` file. Validated eagerly on construction — an invalid or
    missing required value raises immediately, before any collector,
    transport, or buffer is constructed.
    """

    model_config = SettingsConfigDict(
        env_prefix="CLUSTERPULSE_AGENT_", env_file=".env", extra="ignore"
    )

    node_id: str = Field(default_factory=_default_node_id)
    collector_base_url: str = "http://localhost:8000"
    collection_interval_seconds: float = DEFAULT_COLLECTION_INTERVAL_SECONDS

    http_timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS
    http_retry_attempts: int = DEFAULT_HTTP_RETRY_ATTEMPTS
    http_retry_min_wait_seconds: float = DEFAULT_HTTP_RETRY_MIN_WAIT_SECONDS
    http_retry_max_wait_seconds: float = DEFAULT_HTTP_RETRY_MAX_WAIT_SECONDS

    buffer_path: str = "./agent_buffer.jsonl"
    buffer_max_entries: int = DEFAULT_BUFFER_MAX_ENTRIES
