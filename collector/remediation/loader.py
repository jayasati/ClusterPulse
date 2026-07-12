"""Loads and validates the Collector's remediation policy from a JSON file."""

import json
from pathlib import Path

from pydantic import ValidationError

from collector.remediation.definitions import RemediationPolicy
from shared.exceptions import ConfigurationError


def load_remediation_policy(path: str | Path) -> RemediationPolicy:
    """Load and validate a ``RemediationPolicy`` from the JSON file at ``path``.

    Fails fast with ``ConfigurationError`` on a missing file, invalid JSON,
    or a config that fails schema validation (including the
    one-playbook-per-rule_key constraint and the ``restart_service``
    reservation) — mirrors ``collector/rules/loader.py``.
    """
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigurationError(
            f"failed to read remediation policy file: {path}"
        ) from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            f"remediation policy file is not valid JSON: {path}"
        ) from exc

    try:
        return RemediationPolicy.model_validate(data)
    except ValidationError as exc:
        raise ConfigurationError(
            f"remediation policy file failed validation: {path}"
        ) from exc
