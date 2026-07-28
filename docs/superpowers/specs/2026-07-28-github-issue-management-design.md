# GitHub Issue Management Design

## Goal

Manage geometry defects and engineering regressions as traceable issues so the
same failure mode is not fixed repeatedly without a durable regression guard.
GitHub Issues is the only editable source of issue state. The repository keeps
an automatically generated Markdown mirror for offline review and audit.

## Scope

This change adds issue-management documentation, GitHub issue forms, an Issue
Agent operating guide, and a deterministic index synchronization tool. It does
not alter support-layout geometry, DXF export, or existing diagnostic output.

## Source Of Truth And Data Flow

1. GitHub Issues stores the title, body, labels, assignee, comments, and open
   or closed state.
2. The Issue Agent searches GitHub before creating a defect issue. It updates
   an existing issue when the failure has the same root cause and affected
   behavior; otherwise it creates a new issue and links related issues.
3. `tools/sync_issue_index.py` reads GitHub Issues through `gh` and writes
   `docs/issues/INDEX.md`. The index is never edited by hand.
4. The generated index groups issues by `Open`, `In Progress`, `Blocked`, and
   `Closed`, and shows number, priority, type, title, owner, modules, required
   acceptance commands, and GitHub URL.

The script writes to a temporary sibling file and replaces the index only after
a successful GitHub query and output validation. A missing `gh` executable,
unauthenticated session, network failure, or incomplete required metadata
causes a non-zero exit and preserves the prior index.

## Issue Taxonomy

Every new issue receives exactly one work type:

- `bug`: incorrect behavior that does not necessarily affect engineering
  plausibility.
- `engineering`: a support layout that violates a structural or drawing
  plausibility rule.
- `regression`: a previously accepted behavior that has failed again.

Every issue also has one priority label (`P0`, `P1`, or `P2`) and starts with
`needs-triage` until the Issue Agent has checked scope, duplicates, severity,
and acceptance criteria. The issue form requires:

- deterministic reproduction command and named sample/case;
- expected and actual behavior;
- affected modules and risk;
- initial root-cause hypothesis;
- explicit acceptance criteria, including a named regression test;
- DXF/PNG evidence path when geometry is affected.

`engineering` and `regression` issues require `python run_engineering_strut_checks.py`
and a diagnostic PNG review unless the issue explicitly documents why they do
not apply.

## Issue Agent Contract

The Issue Agent must:

1. Search open and closed issues by symptom, module, case name, and labels
   before creating a new one.
2. Create the issue or append reproduction and new evidence to its duplicate
   or parent issue. It must not create anonymous duplicate issues.
3. Keep a fix associated with an issue number in the branch, commit, and issue
   comment. A repair without an issue is returned to triage.
4. Add or update the named regression test before claiming the fix is ready.
5. Run the issue acceptance commands. For geometry changes, regenerate and
   review the relevant diagnostic PNG/DXF outputs.
6. Post the commands, results, changed files, and evidence paths to GitHub.
7. Close only when all acceptance criteria pass, then regenerate the Markdown
   index. Failed verification reopens the issue or creates a linked
   `regression` issue when the original issue is already historical.

## Repository Components

| Path | Responsibility |
| --- | --- |
| `.github/ISSUE_TEMPLATE/bug.yml` | General defect intake form. |
| `.github/ISSUE_TEMPLATE/engineering.yml` | Engineering-layout defect intake form. |
| `.github/ISSUE_TEMPLATE/regression.yml` | Reintroduced accepted behavior intake form. |
| `.github/ISSUE_TEMPLATE/config.yml` | Issue-template chooser configuration. |
| `.agents/issue-agent.md` | Mandatory Issue Agent workflow and closure gate. |
| `docs/issue-management.md` | Human-facing workflow and ownership rules. |
| `tools/sync_issue_index.py` | One-way GitHub-to-Markdown index generator. |
| `docs/issues/INDEX.md` | Generated local issue mirror. |
| `test_issue_management.py` | Script behavior and generated-index regression tests. |

## Index Format

The index begins with a generated-file warning and the UTC synchronization
time. The four status sections use stable ordering: priority (`P0`, `P1`,
`P2`), then issue number descending. Each row links to the GitHub issue and
contains only summary metadata; full history remains on GitHub.

## Validation

Automated tests will use saved `gh issue list --json` fixtures and assert:

- all four status groups render, including empty groups;
- statuses, labels, owner, modules, commands, and links render correctly;
- priority and number ordering are deterministic;
- malformed or missing required metadata fails without replacing the index;
- `gh` failures produce actionable errors and preserve the previous index.

The project change also runs `python -m pytest test_issue_management.py -v`.
No geometry validation command is required for this documentation/tooling-only
change; future geometry issue closure remains governed by `AGENTS.md`.

## Non-Goals

- No bidirectional synchronization or manual edits to the generated index.
- No external issue tracker besides GitHub Issues.
- No automatic issue closure from a test result alone.
- No changes to current support-system generation behavior.
