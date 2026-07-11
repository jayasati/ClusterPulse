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
