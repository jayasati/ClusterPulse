"""Unit tests for PlaybookExecutor and its action handlers."""

from agent.remediation.executor import PlaybookExecutor
from shared.contracts.v1.remediation import (
    ActionResultStatus,
    PendingAction,
    PlaybookActionType,
)


def _action(action_type: PlaybookActionType, parameters=None, action_id=1):
    return PendingAction(
        action_id=action_id, action_type=action_type, parameters=parameters or {}
    )


def test_noop_action_executes_successfully() -> None:
    executor = PlaybookExecutor(allowed_directories=frozenset())

    result = executor.execute(_action(PlaybookActionType.NOOP))

    assert result.status == ActionResultStatus.EXECUTED


def test_clear_directory_removes_contents_not_the_directory_itself(tmp_path) -> None:
    target = tmp_path / "reclaimable"
    target.mkdir()
    (target / "file.txt").write_text("data")
    (target / "subdir").mkdir()
    (target / "subdir" / "nested.txt").write_text("data")
    executor = PlaybookExecutor(allowed_directories=frozenset({str(target)}))

    result = executor.execute(
        _action(PlaybookActionType.CLEAR_DIRECTORY, {"path": str(target)})
    )

    assert result.status == ActionResultStatus.EXECUTED
    assert target.exists()
    assert list(target.iterdir()) == []


def test_clear_directory_refuses_path_outside_allowlist(tmp_path) -> None:
    target = tmp_path / "not-allowed"
    target.mkdir()
    (target / "file.txt").write_text("data")
    executor = PlaybookExecutor(
        allowed_directories=frozenset({str(tmp_path / "other")})
    )

    result = executor.execute(
        _action(PlaybookActionType.CLEAR_DIRECTORY, {"path": str(target)})
    )

    assert result.status == ActionResultStatus.FAILED
    assert (target / "file.txt").exists()  # nothing was touched


def test_clear_directory_refuses_when_path_parameter_missing() -> None:
    executor = PlaybookExecutor(allowed_directories=frozenset({"/tmp/allowed"}))

    result = executor.execute(_action(PlaybookActionType.CLEAR_DIRECTORY, {}))

    assert result.status == ActionResultStatus.FAILED


def test_clear_directory_reports_failure_for_missing_directory(tmp_path) -> None:
    missing = tmp_path / "does-not-exist"
    executor = PlaybookExecutor(allowed_directories=frozenset({str(missing)}))

    result = executor.execute(
        _action(PlaybookActionType.CLEAR_DIRECTORY, {"path": str(missing)})
    )

    assert result.status == ActionResultStatus.FAILED


def test_restart_service_is_refused_as_unsupported() -> None:
    executor = PlaybookExecutor(allowed_directories=frozenset())

    result = executor.execute(
        _action(PlaybookActionType.RESTART_SERVICE, {"service_name": "nginx"})
    )

    assert result.status == ActionResultStatus.FAILED
    assert "restart_service" in result.message
