"""Unit tests for load_remediation_policy."""

from pathlib import Path

import pytest

from collector.remediation.loader import load_remediation_policy
from shared.exceptions import ConfigurationError


def test_load_remediation_policy_missing_file_raises_configuration_error(
    tmp_path,
) -> None:
    with pytest.raises(ConfigurationError):
        load_remediation_policy(tmp_path / "does-not-exist.json")


def test_load_remediation_policy_invalid_json_raises_configuration_error(
    tmp_path,
) -> None:
    path = tmp_path / "playbooks.json"
    path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ConfigurationError):
        load_remediation_policy(path)


def test_load_remediation_policy_schema_violation_raises_configuration_error(
    tmp_path,
) -> None:
    path = tmp_path / "playbooks.json"
    path.write_text(
        '{"playbooks": [{"rule_key": "x", "playbook_name": "y", '
        '"action_type": "not-a-real-action", "description": "z"}]}',
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError):
        load_remediation_policy(path)


def test_load_remediation_policy_valid_file_parses(tmp_path) -> None:
    path = tmp_path / "playbooks.json"
    path.write_text(
        """
        {
          "playbooks": [
            {
              "rule_key": "threshold:disk.usage_percent",
              "playbook_name": "clear_tmp",
              "action_type": "clear_directory",
              "parameters": {"path": "/tmp/reclaimable"},
              "description": "Clear reclaimable temp space"
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    policy = load_remediation_policy(path)

    assert len(policy.playbooks) == 1
    assert policy.playbooks[0].playbook_name == "clear_tmp"


def test_default_playbooks_config_loads_successfully() -> None:
    """Guards the file collector/main.py loads at import time / app startup."""
    default_path = (
        Path(__file__).resolve().parents[3]
        / "collector"
        / "remediation"
        / "default_playbooks.json"
    )

    policy = load_remediation_policy(default_path)

    assert len(policy.playbooks) > 0
