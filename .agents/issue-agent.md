# Issue Agent Contract

1. Search open and closed GitHub Issues by symptom, module, case and labels
   before creating a new Issue. Append evidence to the same root-cause Issue;
   do not create anonymous duplicates.
2. Every Issue has exactly one work-type label (`bug`, `engineering`, or
   `regression`) and one priority label (`P0`, `P1`, or `P2`).
3. No fix starts without an Issue number. If GitHub authentication is
   unavailable, create an explicitly `PENDING-GITHUB` draft under
   `docs/issues/pending/`; it remains Open/Unverified and is not a substitute
   for the remote Issue.
4. Put the Issue number in the branch, commit and verification comment. Add the
   named regression test before claiming readiness.
5. Run all acceptance commands. Geometry changes also require regenerated DXF
   and PNG evidence and a recorded visual review.
6. Post commands, results, changed files and evidence paths before closure.
7. Close only when every criterion passes. A failure keeps the Issue open; a
   repeat after closure reopens it or creates a linked regression Issue.
8. `docs/issues/INDEX.md` is generated only by
   `python tools/sync_issue_index.py`; never edit it by hand.
