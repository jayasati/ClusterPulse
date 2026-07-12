"""Unit tests for CollectorSettings.

Every construction here passes ``_env_file=None`` to disable
pydantic-settings' automatic ``.env`` loading — without it, a real
``.env`` in the repo root (e.g. real Telegram credentials set up for
manual verification) silently leaks into these "defaults" assertions.
"""

import pytest
from pydantic import ValidationError

from collector.config import CollectorSettings
from shared.exceptions import ConfigurationError


def test_defaults_are_sane() -> None:
    settings = CollectorSettings(_env_file=None)
    assert settings.environment == "dev"
    assert settings.port == 8000
    assert settings.token_set == frozenset()
    assert settings.notifications_enabled is False
    assert settings.escalation_after_seconds > 0


def test_token_set_parses_comma_separated_tokens() -> None:
    settings = CollectorSettings(_env_file=None, api_tokens="a, b ,, c")
    assert settings.token_set == {"a", "b", "c"}


def test_empty_tokens_allowed_in_dev() -> None:
    settings = CollectorSettings(_env_file=None, environment="dev", api_tokens="")
    assert settings.token_set == frozenset()


def test_empty_tokens_rejected_outside_dev() -> None:
    with pytest.raises(ConfigurationError):
        CollectorSettings(_env_file=None, environment="prod", api_tokens="")


def test_nonempty_tokens_allowed_outside_dev() -> None:
    settings = CollectorSettings(
        _env_file=None, environment="prod", api_tokens="a-real-token"
    )
    assert settings.token_set == {"a-real-token"}


def test_notifications_enabled_when_both_telegram_settings_set() -> None:
    settings = CollectorSettings(
        _env_file=None,
        api_tokens="t",
        telegram_bot_token="bot-token",
        telegram_chat_id="chat-id",
    )
    assert settings.notifications_enabled is True


def test_notifications_disabled_when_neither_telegram_setting_set() -> None:
    settings = CollectorSettings(_env_file=None, api_tokens="t")
    assert settings.notifications_enabled is False


def test_telegram_bot_token_without_chat_id_raises_configuration_error() -> None:
    with pytest.raises(ConfigurationError):
        CollectorSettings(
            _env_file=None, api_tokens="t", telegram_bot_token="bot-token"
        )


def test_telegram_chat_id_without_bot_token_raises_configuration_error() -> None:
    with pytest.raises(ConfigurationError):
        CollectorSettings(_env_file=None, api_tokens="t", telegram_chat_id="chat-id")


def test_negative_escalation_after_seconds_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CollectorSettings(_env_file=None, api_tokens="t", escalation_after_seconds=-1)


def test_remediation_disabled_by_default() -> None:
    settings = CollectorSettings(_env_file=None, api_tokens="t")
    assert settings.remediation_enabled is False


def test_remediation_after_seconds_below_escalation_rejected_when_enabled() -> None:
    with pytest.raises(ConfigurationError):
        CollectorSettings(
            _env_file=None,
            api_tokens="t",
            remediation_enabled=True,
            escalation_after_seconds=900,
            remediation_after_seconds=100,
        )


def test_remediation_after_seconds_below_escalation_allowed_when_disabled() -> None:
    """The ordering only matters once remediation can actually fire."""
    settings = CollectorSettings(
        _env_file=None,
        api_tokens="t",
        remediation_enabled=False,
        escalation_after_seconds=900,
        remediation_after_seconds=100,
    )
    assert settings.remediation_after_seconds == 100


def test_remediation_after_seconds_equal_to_escalation_is_allowed() -> None:
    settings = CollectorSettings(
        _env_file=None,
        api_tokens="t",
        remediation_enabled=True,
        escalation_after_seconds=900,
        remediation_after_seconds=900,
    )
    assert settings.remediation_after_seconds == 900


def test_negative_max_remediations_per_node_per_hour_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CollectorSettings(
            _env_file=None, api_tokens="t", max_remediations_per_node_per_hour=0
        )


def test_retention_disabled_by_default() -> None:
    settings = CollectorSettings(_env_file=None, api_tokens="t")
    assert settings.retention_enabled is False
    assert settings.metrics_retention_days >= 1
    assert settings.resolved_alerts_retention_days >= 1
    assert settings.remediation_actions_retention_days >= 1
    assert settings.retention_interval_seconds > 0
    assert settings.retention_batch_size >= 1


def test_zero_retention_days_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CollectorSettings(_env_file=None, api_tokens="t", metrics_retention_days=0)


def test_zero_retention_batch_size_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CollectorSettings(_env_file=None, api_tokens="t", retention_batch_size=0)


def test_zero_retention_interval_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CollectorSettings(_env_file=None, api_tokens="t", retention_interval_seconds=0)


def test_alert_retention_longer_than_remediation_rejected_when_enabled() -> None:
    """An alert pruned while audit rows still reference it would violate the
    remediation_actions.alert_id foreign key — refused at startup."""
    with pytest.raises(ConfigurationError):
        CollectorSettings(
            _env_file=None,
            api_tokens="t",
            retention_enabled=True,
            resolved_alerts_retention_days=90,
            remediation_actions_retention_days=30,
        )


def test_alert_retention_longer_than_remediation_allowed_when_disabled() -> None:
    """The window ordering only matters once retention can actually delete."""
    settings = CollectorSettings(
        _env_file=None,
        api_tokens="t",
        retention_enabled=False,
        resolved_alerts_retention_days=90,
        remediation_actions_retention_days=30,
    )
    assert settings.resolved_alerts_retention_days == 90


def test_alert_retention_equal_to_remediation_is_allowed() -> None:
    settings = CollectorSettings(
        _env_file=None,
        api_tokens="t",
        retention_enabled=True,
        resolved_alerts_retention_days=30,
        remediation_actions_retention_days=30,
    )
    assert settings.retention_enabled is True


def test_staleness_and_reconciliation_disabled_by_default() -> None:
    settings = CollectorSettings(_env_file=None, api_tokens="t")
    assert settings.staleness_alerting_enabled is False
    assert settings.remediation_reconciliation_enabled is False
    assert settings.staleness_check_interval_seconds > 0
    assert settings.reconciliation_interval_seconds > 0
    assert settings.remediation_dispatch_timeout_seconds > 0


def test_zero_staleness_interval_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CollectorSettings(
            _env_file=None, api_tokens="t", staleness_check_interval_seconds=0
        )


def test_zero_dispatch_timeout_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CollectorSettings(
            _env_file=None, api_tokens="t", remediation_dispatch_timeout_seconds=0
        )
