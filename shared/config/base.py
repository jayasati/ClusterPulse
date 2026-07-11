"""Common settings shape shared by every ClusterPulse service.

Each service (Agent, Collector) subclasses this with its own ``env_prefix``
and additional fields — see ``docs/architecture/00-project-initialization.md``
§4 for the full layered-configuration design.
"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    """Fields every ClusterPulse service configures, regardless of its role."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["dev", "staging", "prod"] = "dev"
    service_name: str = "clusterpulse"
    log_level: str = "INFO"
