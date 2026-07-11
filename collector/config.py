"""Collector process configuration."""

from pathlib import Path

from pydantic import model_validator
from pydantic_settings import SettingsConfigDict

from shared.config.base import BaseServiceSettings
from shared.constants import DEFAULT_HEARTBEAT_STALE_AFTER_SECONDS
from shared.exceptions import ConfigurationError

_DEFAULT_RULES_CONFIG_PATH = str(
    Path(__file__).resolve().parent / "rules" / "default_rules.json"
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

    @property
    def token_set(self) -> frozenset[str]:
        """The configured tokens as a set, ignoring blanks and whitespace."""
        return frozenset(
            token.strip() for token in self.api_tokens.split(",") if token.strip()
        )

    @model_validator(mode="after")
    def _require_tokens_outside_dev(self) -> "CollectorSettings":
        if self.environment != "dev" and not self.token_set:
            raise ConfigurationError(
                "api_tokens must be set when environment is not 'dev'",
                context={"environment": self.environment},
            )
        return self
