"""Unit tests for Agent entrypoint wiring."""

from agent.config import AgentSettings
from agent.main import build_scheduler
from agent.scheduler import AgentScheduler


def test_build_scheduler_returns_configured_scheduler(tmp_path) -> None:
    settings = AgentSettings(buffer_path=str(tmp_path / "buffer.jsonl"))

    scheduler = build_scheduler(settings)

    assert isinstance(scheduler, AgentScheduler)
