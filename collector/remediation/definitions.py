"""Remediation policy configuration models — what a "Playbook" is.

Loaded from a JSON file (``collector/remediation/loader.py``), not a
database — mirrors the Rule Engine's config-file-driven precedent
(``collector/rules/definitions.py``, ``docs/adr/006-alert-lifecycle.md``)
for the same reason: changes are reviewed like code, not hot-reloaded.
"""

from pydantic import BaseModel, Field, model_validator

from shared.contracts.v1.remediation import PlaybookActionType


class PlaybookDefinition(BaseModel):
    """A named remediation action mapped to the alert condition that triggers it.

    ``rule_key`` matches ``Alert.rule_key`` (``"{kind}:{metric_type}"``) —
    at most one Playbook per ``rule_key``, enforced by ``RemediationPolicy``.
    """

    rule_key: str
    playbook_name: str
    action_type: PlaybookActionType
    parameters: dict[str, str] = Field(default_factory=dict)
    description: str


class RemediationPolicy(BaseModel):
    """The full set of configured Playbooks, loaded once at Collector startup."""

    playbooks: list[PlaybookDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_playbooks(self) -> "RemediationPolicy":
        seen_rule_keys: set[str] = set()
        for playbook in self.playbooks:
            if playbook.rule_key in seen_rule_keys:
                raise ValueError(
                    f"duplicate playbook mapping for rule_key={playbook.rule_key!r}"
                )
            seen_rule_keys.add(playbook.rule_key)
            _validate_action_parameters(playbook)
        return self


def _validate_action_parameters(playbook: PlaybookDefinition) -> None:
    if playbook.action_type == PlaybookActionType.CLEAR_DIRECTORY:
        if not playbook.parameters.get("path", "").strip():
            raise ValueError(
                f"playbook {playbook.playbook_name!r} (clear_directory) "
                "requires a non-empty 'path' parameter"
            )
    if playbook.action_type == PlaybookActionType.RESTART_SERVICE:
        raise ValueError(
            f"playbook {playbook.playbook_name!r}: restart_service is reserved "
            "but not implemented as of Phase 5 (requires a privileged-execution "
            "model not yet built) — see docs/adr/007-remediation-safety.md"
        )
