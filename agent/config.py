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

    auth_token: str | None = None
    """Bearer token sent to the Collector, if configured. See
    ``docs/adr/005-authentication.md``. ``None`` sends no Authorization
    header at all — the pre-Phase-2 default behavior, unchanged."""

    http_timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS
    http_retry_attempts: int = DEFAULT_HTTP_RETRY_ATTEMPTS
    http_retry_min_wait_seconds: float = DEFAULT_HTTP_RETRY_MIN_WAIT_SECONDS
    http_retry_max_wait_seconds: float = DEFAULT_HTTP_RETRY_MAX_WAIT_SECONDS

    buffer_path: str = "./agent_buffer.jsonl"
    buffer_max_entries: int = DEFAULT_BUFFER_MAX_ENTRIES

    remediation_enabled: bool = False
    """Independent opt-in for actually executing dispatched remediation
    actions — off by default. Even if the Collector dispatches a Playbook
    (its own ``remediation_enabled`` opt-in), this Agent refuses to execute
    it until this is also explicitly enabled. See
    ``docs/adr/007-remediation-safety.md``."""

    remediation_allowed_directories: str = ""
    """Comma-separated absolute directory paths this Agent may clear for a
    ``CLEAR_DIRECTORY`` action. Defense in depth: checked independently of
    whatever the Collector's Playbook config says — a dispatched path
    outside this allowlist is refused locally, never executed blindly."""

    @property
    def remediation_allowed_directory_set(self) -> frozenset[str]:
        """The configured allowlist as a set, ignoring blanks and whitespace."""
        return frozenset(
            path.strip()
            for path in self.remediation_allowed_directories.split(",")
            if path.strip()
        )
