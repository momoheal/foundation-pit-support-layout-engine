# Issue Management

GitHub Issues is the editable source of truth. Use the repository Issue forms
and follow `.agents/issue-agent.md`. Geometry defects require a named case,
regression test, engineering-check command and PNG/DXF evidence.

Run `python tools/sync_issue_index.py` after any Issue state change. The command
validates required labels and body sections before atomically replacing
`docs/issues/INDEX.md`. Query, authentication and metadata failures preserve the
previous index and return a non-zero exit code.

Files under `docs/issues/pending/` are temporary drafts used only while GitHub
authentication is unavailable. They must say `Open / Unverified`; migrate them
to GitHub before closure and remove the draft in the same verified change.
