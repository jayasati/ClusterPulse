"""Unit tests for RemediationPolicy/PlaybookDefinition validation."""

import pytest
from pydantic import ValidationError

from collector.remediation.definitions import PlaybookDefinition, RemediationPolicy
from shared.contracts.v1.remediation import PlaybookActionType


def _clear_directory_playbook(rule_key: str = "threshold:disk.usage_percent") -> dict:
    return {
        "rule_key": rule_key,
        "playbook_name": "clear_tmp",
        "action_type": "clear_directory",
        "parameters": {"path": "/tmp/reclaimable"},
        "description": "Clear reclaimable temp space",
    }


def test_valid_policy_with_one_playbook() -> None:
    policy = RemediationPolicy.model_validate(
        {"playbooks": [_clear_directory_playbook()]}
    )
    assert len(policy.playbooks) == 1
    assert policy.playbooks[0].action_type == PlaybookActionType.CLEAR_DIRECTORY


def test_empty_policy_is_valid() -> None:
    policy = RemediationPolicy.model_validate({})
    assert policy.playbooks == []


def test_duplicate_rule_key_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RemediationPolicy.model_validate(
            {
                "playbooks": [
                    _clear_directory_playbook(),
                    {**_clear_directory_playbook(), "playbook_name": "clear_tmp_2"},
                ]
            }
        )


def test_clear_directory_without_path_parameter_is_rejected() -> None:
    playbook = _clear_directory_playbook()
    playbook["parameters"] = {}
    with pytest.raises(ValidationError):
        RemediationPolicy.model_validate({"playbooks": [playbook]})


def test_clear_directory_with_blank_path_parameter_is_rejected() -> None:
    playbook = _clear_directory_playbook()
    playbook["parameters"] = {"path": "   "}
    with pytest.raises(ValidationError):
        RemediationPolicy.model_validate({"playbooks": [playbook]})


def test_restart_service_is_rejected_as_not_yet_implemented() -> None:
    playbook = _clear_directory_playbook()
    playbook["action_type"] = "restart_service"
    playbook["parameters"] = {}
    with pytest.raises(ValidationError):
        RemediationPolicy.model_validate({"playbooks": [playbook]})


def test_noop_requires_no_parameters() -> None:
    playbook = PlaybookDefinition(
        rule_key="threshold:cpu.usage_percent",
        playbook_name="noop_test",
        action_type=PlaybookActionType.NOOP,
        description="test only",
    )
    policy = RemediationPolicy(playbooks=[playbook])
    assert policy.playbooks[0].parameters == {}


def test_different_rule_keys_are_allowed() -> None:
    policy = RemediationPolicy.model_validate(
        {
            "playbooks": [
                _clear_directory_playbook("threshold:disk.usage_percent"),
                {
                    **_clear_directory_playbook("threshold:memory.usage_percent"),
                    "playbook_name": "clear_tmp_2",
                },
            ]
        }
    )
    assert len(policy.playbooks) == 2
