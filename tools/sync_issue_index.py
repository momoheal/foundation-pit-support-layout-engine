"""Generate the read-only local GitHub Issue index."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable


PRIORITIES = ("P0", "P1", "P2")
WORK_TYPES = ("bug", "engineering", "regression")
STATUSES = ("Open", "In Progress", "Blocked", "Closed")


class IssueMetadataError(ValueError):
    """Raised when an Issue cannot satisfy the repository audit contract."""


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    status: str
    priority: str
    work_type: str
    owner: str
    modules: str
    commands: str
    url: str


def _label_names(raw: dict[str, Any]) -> set[str]:
    return {str(label.get("name", "")).strip() for label in raw.get("labels", [])}


def _single_label(number: int, labels: set[str], choices: tuple[str, ...], name: str) -> str:
    matches = [choice for choice in choices if choice in labels]
    if len(matches) != 1:
        raise IssueMetadataError(
            f"issue #{number} must have exactly one {name} label; found {matches}"
        )
    return matches[0]


def _body_section(body: str, heading: str) -> str:
    lines = body.splitlines()
    content: list[str] = []
    active = False
    for line in lines:
        if line.strip().lower() == f"### {heading}".lower():
            active = True
            continue
        if active and line.startswith("### "):
            break
        if active and line.strip():
            content.append(line.strip())
    return "<br>".join(content)


def load_issues(raw_issues: list[dict[str, Any]]) -> list[Issue]:
    issues: list[Issue] = []
    for raw in raw_issues:
        number = int(raw["number"])
        labels = _label_names(raw)
        priority = _single_label(number, labels, PRIORITIES, "priority")
        work_type = _single_label(number, labels, WORK_TYPES, "work type")
        body = str(raw.get("body") or "")
        modules = _body_section(body, "Affected modules")
        commands = _body_section(body, "Acceptance commands")
        if not modules:
            raise IssueMetadataError(f"issue #{number} is missing Affected modules")
        if not commands:
            raise IssueMetadataError(f"issue #{number} is missing Acceptance commands")

        state = str(raw.get("state", "OPEN")).upper()
        if state == "CLOSED":
            status = "Closed"
        elif "blocked" in labels:
            status = "Blocked"
        elif "in-progress" in labels:
            status = "In Progress"
        else:
            status = "Open"
        assignees = [str(item.get("login", "")) for item in raw.get("assignees", [])]
        issues.append(Issue(
            number=number,
            title=str(raw["title"]).replace("|", "\\|"),
            status=status,
            priority=priority,
            work_type=work_type,
            owner=", ".join(owner for owner in assignees if owner) or "Unassigned",
            modules=modules.replace("|", "\\|"),
            commands=commands.replace("|", "\\|"),
            url=str(raw["url"]),
        ))
    return issues


def render_index(issues: list[Issue], *, generated_at: str | None = None) -> str:
    stamp = generated_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    priority_order = {priority: index for index, priority in enumerate(PRIORITIES)}
    lines = [
        "# GitHub Issue Index",
        "",
        "> GENERATED FILE. Do not edit by hand.",
        f"> Synchronized at {stamp}.",
        "",
    ]
    for status in STATUSES:
        lines.extend([
            f"## {status}",
            "",
            "| Issue | Priority | Type | Title | Owner | Modules | Acceptance commands |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ])
        group = sorted(
            (issue for issue in issues if issue.status == status),
            key=lambda issue: (priority_order[issue.priority], -issue.number),
        )
        if not group:
            lines.append("| - | - | - | None | - | - | - |")
        for issue in group:
            lines.append(
                f"| [#{issue.number}]({issue.url}) | {issue.priority} | {issue.work_type} | "
                f"{issue.title} | {issue.owner} | {issue.modules} | {issue.commands} |"
            )
        lines.append("")
    return "\n".join(lines)


def query_github_issues() -> list[dict[str, Any]]:
    command = [
        "gh", "issue", "list", "--state", "all", "--limit", "1000", "--json",
        "number,title,state,url,labels,assignees,body",
    ]
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("gh executable was not found") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "unknown gh failure").strip()
        raise RuntimeError(f"GitHub Issue query failed: {detail}") from exc
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GitHub Issue query returned invalid JSON") from exc
    if not isinstance(payload, list):
        raise RuntimeError("GitHub Issue query did not return a list")
    return payload


def sync_index(
    target: Path,
    *,
    query: Callable[[], list[dict[str, Any]]] = query_github_issues,
) -> None:
    raw_issues = query()
    rendered = render_index(load_issues(raw_issues))
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent, text=True
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered)
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("docs/issues/INDEX.md"))
    args = parser.parse_args()
    try:
        sync_index(args.output)
    except (IssueMetadataError, RuntimeError, OSError) as exc:
        parser.exit(1, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
