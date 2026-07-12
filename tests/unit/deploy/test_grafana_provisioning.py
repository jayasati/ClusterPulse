"""Sanity checks for the Grafana provisioning artifacts.

Dashboards are data, not code — but broken data ships just as easily.
These tests catch the failure modes a JSON edit can introduce: invalid
syntax, a dashboard pointing at a datasource UID that isn't provisioned,
and panels with no queries.
"""

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
DASHBOARD_DIR = REPO_ROOT / "deploy" / "grafana" / "dashboards"
DATASOURCE_FILE = (
    REPO_ROOT
    / "deploy"
    / "grafana"
    / "provisioning"
    / "datasources"
    / "clusterpulse.yaml"
)

PROVISIONED_DATASOURCE_UID = "clusterpulse-postgres"

dashboard_files = sorted(DASHBOARD_DIR.glob("*.json"))


def test_dashboards_exist() -> None:
    assert len(dashboard_files) == 3


def test_datasource_provisioning_declares_the_expected_uid() -> None:
    # Cheap containment check instead of a YAML parser: PyYAML is not a
    # project dependency, and the UID contract is what actually matters.
    content = DATASOURCE_FILE.read_text(encoding="utf-8")
    assert f"uid: {PROVISIONED_DATASOURCE_UID}" in content
    assert "password: $CLUSTERPULSE_GRAFANA_DB_PASSWORD" in content


@pytest.mark.parametrize("path", dashboard_files, ids=lambda p: p.name)
def test_dashboard_is_valid_json_with_unique_uid_and_title(path: Path) -> None:
    dashboard = json.loads(path.read_text(encoding="utf-8"))
    assert dashboard["uid"].startswith("clusterpulse-")
    assert dashboard["title"].startswith("ClusterPulse")
    assert dashboard["panels"], "dashboard has no panels"


@pytest.mark.parametrize("path", dashboard_files, ids=lambda p: p.name)
def test_every_panel_queries_the_provisioned_datasource(path: Path) -> None:
    dashboard = json.loads(path.read_text(encoding="utf-8"))
    for panel in dashboard["panels"]:
        assert panel["datasource"]["uid"] == PROVISIONED_DATASOURCE_UID
        assert panel["targets"], f"panel {panel['title']!r} has no queries"
        for target in panel["targets"]:
            assert target["rawSql"].strip(), f"panel {panel['title']!r} has empty SQL"


def test_dashboard_uids_are_unique() -> None:
    uids = [
        json.loads(path.read_text(encoding="utf-8"))["uid"] for path in dashboard_files
    ]
    assert len(uids) == len(set(uids))
