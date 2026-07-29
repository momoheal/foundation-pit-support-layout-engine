"""Regression tests for the GitHub Issue index workflow."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.sync_issue_index import IssueMetadataError, load_issues, render_index, sync_index


FIXTURE = Path(__file__).parent / "tests" / "fixtures" / "github_issues.json"


def test_issue_index_renders_all_statuses_and_required_metadata() -> None:
    issues = load_issues(json.loads(FIXTURE.read_text(encoding="utf-8")))
    rendered = render_index(issues, generated_at="2026-07-29T00:00:00Z")

    for heading in ("## Open", "## In Progress", "## Blocked", "## Closed"):
        assert heading in rendered
    assert "#12" in rendered
    assert "P0" in rendered
    assert "engineering" in rendered
    assert "engineer" in rendered
    assert "strut_engine.py, strut_validation.py" in rendered
    assert "python run_engineering_strut_checks.py" in rendered
    assert rendered.index("## Open") < rendered.index("## In Progress")


def test_issue_index_rejects_missing_required_metadata() -> None:
    broken = json.loads(FIXTURE.read_text(encoding="utf-8"))
    broken[0]["labels"] = [{"name": "P0"}]

    with pytest.raises(IssueMetadataError, match="work type"):
        load_issues(broken)


def test_sync_failure_preserves_existing_index(tmp_path: Path) -> None:
    target = tmp_path / "INDEX.md"
    target.write_text("existing\n", encoding="utf-8")

    def failing_query() -> list[dict[str, object]]:
        raise RuntimeError("gh authentication failed")

    with pytest.raises(RuntimeError, match="authentication"):
        sync_index(target, query=failing_query)
    assert target.read_text(encoding="utf-8") == "existing\n"
