"""Unit tests for BaseServiceSettings."""

from shared.config.base import BaseServiceSettings


def test_defaults() -> None:
    settings = BaseServiceSettings()
    assert settings.environment == "dev"
    assert settings.log_level == "INFO"
    assert settings.service_name == "clusterpulse"


def test_environment_override_via_env_var(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "prod")
    settings = BaseServiceSettings()
    assert settings.environment == "prod"
