"""Unit tests for load_rules_config."""

import pytest

from collector.rules.loader import load_rules_config
from shared.exceptions import ConfigurationError


def test_load_rules_config_missing_file_raises_configuration_error(tmp_path) -> None:
    with pytest.raises(ConfigurationError):
        load_rules_config(tmp_path / "does-not-exist.json")


def test_load_rules_config_invalid_json_raises_configuration_error(tmp_path) -> None:
    path = tmp_path / "rules.json"
    path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ConfigurationError):
        load_rules_config(path)


def test_load_rules_config_schema_violation_raises_configuration_error(
    tmp_path,
) -> None:
    path = tmp_path / "rules.json"
    path.write_text(
        '{"threshold_rules": [{"metric_type": "not-a-real-metric"}]}', encoding="utf-8"
    )

    with pytest.raises(ConfigurationError):
        load_rules_config(path)


def test_load_rules_config_valid_file_parses(tmp_path) -> None:
    path = tmp_path / "rules.json"
    path.write_text(
        """
        {
          "threshold_rules": [
            {
              "metric_type": "cpu.usage_percent",
              "comparison": "gt",
              "threshold": 90.0,
              "severity": "critical",
              "description": "CPU too high"
            }
          ],
          "rate_of_change_rules": []
        }
        """,
        encoding="utf-8",
    )

    config = load_rules_config(path)

    assert len(config.threshold_rules) == 1
    assert config.threshold_rules[0].threshold == 90.0


def test_default_rules_config_loads_successfully() -> None:
    """Guards the file collector/main.py loads at import time / app startup."""
    from pathlib import Path

    default_path = (
        Path(__file__).resolve().parents[3]
        / "collector"
        / "rules"
        / "default_rules.json"
    )

    config = load_rules_config(default_path)

    assert len(config.threshold_rules) > 0
