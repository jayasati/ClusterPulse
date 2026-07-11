"""Loads and validates the Collector's rule configuration from a JSON file."""

import json
from pathlib import Path

from pydantic import ValidationError

from collector.rules.definitions import RulesConfig
from shared.exceptions import ConfigurationError


def load_rules_config(path: str | Path) -> RulesConfig:
    """Load and validate a ``RulesConfig`` from the JSON file at ``path``.

    Fails fast with ``ConfigurationError`` on a missing file, invalid JSON,
    or a config that fails schema validation (including the
    one-rule-per-metric-type-per-kind constraint) — mirrors how
    ``CollectorSettings`` fails startup on bad configuration.
    """
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigurationError(f"failed to read rules config file: {path}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            f"rules config file is not valid JSON: {path}"
        ) from exc

    try:
        return RulesConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigurationError(
            f"rules config file failed validation: {path}"
        ) from exc
