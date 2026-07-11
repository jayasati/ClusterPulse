"""Unit tests for CollectorSettings."""

import pytest

from collector.config import CollectorSettings
from shared.exceptions import ConfigurationError


def test_defaults_are_sane() -> None:
    settings = CollectorSettings()
    assert settings.environment == "dev"
    assert settings.port == 8000
    assert settings.token_set == frozenset()


def test_token_set_parses_comma_separated_tokens() -> None:
    settings = CollectorSettings(api_tokens="a, b ,, c")
    assert settings.token_set == {"a", "b", "c"}


def test_empty_tokens_allowed_in_dev() -> None:
    settings = CollectorSettings(environment="dev", api_tokens="")
    assert settings.token_set == frozenset()


def test_empty_tokens_rejected_outside_dev() -> None:
    with pytest.raises(ConfigurationError):
        CollectorSettings(environment="prod", api_tokens="")


def test_nonempty_tokens_allowed_outside_dev() -> None:
    settings = CollectorSettings(environment="prod", api_tokens="a-real-token")
    assert settings.token_set == {"a-real-token"}
