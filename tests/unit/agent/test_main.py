"""Unit tests for Agent entrypoint wiring."""

from agent.config import AgentSettings
from agent.main import build_scheduler
from agent.scheduler import AgentScheduler


def test_build_scheduler_returns_configured_scheduler(tmp_path) -> None:
    settings = AgentSettings(buffer_path=str(tmp_path / "buffer.jsonl"))

    scheduler = build_scheduler(settings)

    assert isinstance(scheduler, AgentScheduler)


def test_build_scheduler_has_no_executor_when_remediation_disabled(tmp_path) -> None:
    settings = AgentSettings(
        _env_file=None,
        buffer_path=str(tmp_path / "buffer.jsonl"),
        remediation_enabled=False,
    )

    scheduler = build_scheduler(settings)

    assert scheduler._executor is None


def test_build_scheduler_has_executor_when_remediation_enabled(tmp_path) -> None:
    settings = AgentSettings(
        _env_file=None,
        buffer_path=str(tmp_path / "buffer.jsonl"),
        remediation_enabled=True,
        remediation_allowed_directories="/tmp/allowed",
    )

    scheduler = build_scheduler(settings)

    assert scheduler._executor is not None
    assert scheduler._executor._allowed_directories == {"/tmp/allowed"}
