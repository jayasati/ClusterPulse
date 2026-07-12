"""The CLEAR_DIRECTORY action — deletes a directory's contents, not itself."""

import os
import shutil

from shared.contracts.v1.remediation import ActionResult, ActionResultStatus
from shared.exceptions import RemediationSafetyError


def execute_clear_directory(
    parameters: dict[str, str], allowed_directories: frozenset[str]
) -> ActionResult:
    """Delete every entry directly inside ``parameters["path"]``.

    Refuses (``RemediationSafetyError``) unless ``path`` is present and
    exactly matches an entry in ``allowed_directories`` — this Agent's own
    local allowlist, checked independently of whatever the Collector's
    Playbook config said to dispatch. Any ``OSError`` while clearing
    (missing directory, permission denied) propagates uncaught; the caller
    (``PlaybookExecutor``) turns it into a ``FAILED`` result.
    """
    path = parameters.get("path", "")
    if not path or path not in allowed_directories:
        raise RemediationSafetyError(
            f"path {path!r} is not in this Agent's "
            "remediation_allowed_directories allowlist",
            context={"path": path},
        )
    removed = _clear_directory_contents(path)
    return ActionResult(
        status=ActionResultStatus.EXECUTED,
        message=f"removed {removed} entries from {path}",
    )


def _clear_directory_contents(path: str) -> int:
    entries = os.listdir(path)
    for entry in entries:
        entry_path = os.path.join(path, entry)
        if os.path.isdir(entry_path) and not os.path.islink(entry_path):
            shutil.rmtree(entry_path)
        else:
            os.remove(entry_path)
    return len(entries)
