"""Unit tests for AgentSettings."""

from agent.config import AgentSettings


def test_defaults_are_sane() -> None:
    settings = AgentSettings()
    assert settings.collector_base_url == "http://localhost:8000"
    assert settings.collection_interval_seconds > 0
    assert settings.node_id  # hostname fallback, must be non-empty
    assert settings.auth_token is None


def test_env_override(monkeypatch) -> None:
    monkeypatch.setenv("CLUSTERPULSE_AGENT_NODE_ID", "custom-node")
    monkeypatch.setenv("CLUSTERPULSE_AGENT_COLLECTOR_BASE_URL", "http://collector:9000")
    settings = AgentSettings()
    assert settings.node_id == "custom-node"
    assert settings.collector_base_url == "http://collector:9000"


def test_inherits_base_service_settings_fields() -> None:
    settings = AgentSettings()
    assert settings.environment == "dev"
    assert settings.log_level == "INFO"


def test_auth_token_env_override(monkeypatch) -> None:
    monkeypatch.setenv("CLUSTERPULSE_AGENT_AUTH_TOKEN", "secret-token")
    settings = AgentSettings()
    assert settings.auth_token == "secret-token"


def test_remediation_disabled_by_default() -> None:
    settings = AgentSettings(_env_file=None)
    assert settings.remediation_enabled is False
    assert settings.remediation_allowed_directory_set == frozenset()


def test_remediation_allowed_directory_set_parses_comma_separated_paths() -> None:
    settings = AgentSettings(
        _env_file=None, remediation_allowed_directories="/tmp/a, /tmp/b ,, /tmp/c"
    )
    assert settings.remediation_allowed_directory_set == {"/tmp/a", "/tmp/b", "/tmp/c"}
