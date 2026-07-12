"""Collector process configuration."""

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import SettingsConfigDict

from shared.config.base import BaseServiceSettings
from shared.constants import (
    DEFAULT_ESCALATION_AFTER_SECONDS,
    DEFAULT_HEARTBEAT_STALE_AFTER_SECONDS,
    DEFAULT_MAX_REMEDIATIONS_PER_NODE_PER_HOUR,
    DEFAULT_REMEDIATION_AFTER_SECONDS,
    DEFAULT_REMEDIATION_COOLDOWN_SECONDS,
)
from shared.exceptions import ConfigurationError

_DEFAULT_RULES_CONFIG_PATH = str(
    Path(__file__).resolve().parent / "rules" / "default_rules.json"
)
_DEFAULT_REMEDIATION_POLICY_PATH = str(
    Path(__file__).resolve().parent / "remediation" / "default_playbooks.json"
)


class CollectorSettings(BaseServiceSettings):
    """Configuration for the ClusterPulse Collector process.

    Loaded from environment variables prefixed ``CLUSTERPULSE_COLLECTOR_``,
    or a local ``.env`` file. ``api_tokens`` may be empty only when
    ``environment == "dev"`` — anywhere else, an empty token set means the
    Collector would accept unauthenticated pushes, so construction fails
    fast instead (see ``docs/adr/005-authentication.md``).
    """

    model_config = SettingsConfigDict(
        env_prefix="CLUSTERPULSE_COLLECTOR_", env_file=".env", extra="ignore"
    )

    database_url: str = (
        "postgresql+psycopg://clusterpulse:clusterpulse@localhost:5432/clusterpulse"
    )
    host: str = "0.0.0.0"
    port: int = 8000

    api_tokens: str = ""
    """Comma-separated bearer tokens, e.g. ``token-a,token-b``. See ``token_set``."""

    heartbeat_stale_after_seconds: float = DEFAULT_HEARTBEAT_STALE_AFTER_SECONDS

    rules_config_path: str = _DEFAULT_RULES_CONFIG_PATH
    """Path to the JSON file defining Threshold/Rate-of-change rules. See
    ``collector/rules/default_rules.json`` and ``docs/adr/006-alert-lifecycle.md``."""

    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    """Both must be set together, or neither — see ``notifications_enabled`` and
    ``docs/adr/018-telegram-notifications.md``. Unlike ``api_tokens``, leaving
    both unset is a normal, non-fail-fast configuration (notifications are
    optional, not a security control)."""

    escalation_after_seconds: float = Field(
        default=DEFAULT_ESCALATION_AFTER_SECONDS, ge=0
    )
    """Seconds a firing, unacknowledged alert waits before a single escalation
    notification. See ``docs/adr/019-alert-acknowledgement-escalation.md``."""

    remediation_enabled: bool = False
    """Global kill switch for auto-remediation — off by default. See
    ``docs/adr/007-remediation-safety.md``. Dispatching also requires the
    Agent's own independent ``remediation_enabled`` opt-in; both must be
    true for a Playbook to actually execute."""

    remediation_after_seconds: float = Field(
        default=DEFAULT_REMEDIATION_AFTER_SECONDS, ge=0
    )
    """Seconds a firing, unacknowledged alert waits before remediation is
    considered — always evaluated at the same "has this escalated" moment
    as ``escalation_after_seconds``, so this must be >= it (a human gets a
    chance to intervene before automation does)."""

    max_remediations_per_node_per_hour: int = Field(
        default=DEFAULT_MAX_REMEDIATIONS_PER_NODE_PER_HOUR, ge=1
    )
    """Safety Limit: caps how many remediation actions may be dispatched to a
    single node within a rolling hour, regardless of how many distinct
    alerts escalate on it."""

    remediation_cooldown_seconds: float = Field(
        default=DEFAULT_REMEDIATION_COOLDOWN_SECONDS, ge=0
    )
    """Safety Limit: minimum time since the last dispatched/blocked action for
    the same ``(node_id, playbook_name)`` before another may be dispatched."""

    remediation_policy_config_path: str = _DEFAULT_REMEDIATION_POLICY_PATH
    """Path to the JSON file mapping ``rule_key`` -> Playbook. See
    ``collector/remediation/default_playbooks.json``."""

    @property
    def token_set(self) -> frozenset[str]:
        """The configured tokens as a set, ignoring blanks and whitespace."""
        return frozenset(
            token.strip() for token in self.api_tokens.split(",") if token.strip()
        )

    @property
    def notifications_enabled(self) -> bool:
        """Whether both Telegram settings are configured."""
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @model_validator(mode="after")
    def _require_tokens_outside_dev(self) -> "CollectorSettings":
        if self.environment != "dev" and not self.token_set:
            raise ConfigurationError(
                "api_tokens must be set when environment is not 'dev'",
                context={"environment": self.environment},
            )
        return self

    @model_validator(mode="after")
    def _require_telegram_both_or_neither(self) -> "CollectorSettings":
        has_token = bool(self.telegram_bot_token)
        has_chat_id = bool(self.telegram_chat_id)
        if has_token != has_chat_id:
            raise ConfigurationError(
                "telegram_bot_token and telegram_chat_id must both be set, or neither"
            )
        return self

    @model_validator(mode="after")
    def _require_remediation_after_escalation(self) -> "CollectorSettings":
        if (
            self.remediation_enabled
            and self.remediation_after_seconds < self.escalation_after_seconds
        ):
            raise ConfigurationError(
                "remediation_after_seconds must be >= escalation_after_seconds "
                "— remediation must never fire before a human has had a chance "
                "to acknowledge",
                context={
                    "remediation_after_seconds": self.remediation_after_seconds,
                    "escalation_after_seconds": self.escalation_after_seconds,
                },
            )
        return self
