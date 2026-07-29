# Structural Topology Red Lines

## Authority

This specification records the current engineering decision for the
`large_brace_corner_truss_120x80` sample. It supersedes every earlier rule that
requires a corner-brace member to start at a true waling corner or terminate at
an arbitrary main-strut midspan. In particular, the R39/R40/R47 corner-vertex
requirements in `docs/iteration11-corner-brace-as-diagonal-truss-leg.md` are
retired.

The two real drawing references supplied on 2026-07-29 are the visual authority:

- `codex-clipboard-d5a958e8-3da7-4766-b1b6-ad86c9e535f0.png`
- `codex-clipboard-f71afbce-f2aa-48ff-ad2f-02e560d90d67.png`

## Structural Model

The large rectangular brace case has one horizontal paired main-strut group and
two vertical paired main-strut groups. The nominal spacing between the two
members in a pair is 6 m. Coupling stations along a pair target 14 m maximum
unbraced length.

Each convex corner is supported by a local triangular lattice assembly:

1. Its two exterior anchors are distinct legal nodes on the two adjacent waling
   edges, set back from the true polygon vertex.
2. No corner-lattice member endpoint is the true waling corner.
3. No corner-lattice member terminates at an unsplit main-strut midspan.
4. The assembly is triangulated locally and hands load into the continuous
   waling/perimeter system through shared graph nodes.
5. Edge-truss webs stop at the corner-assembly handoff stations. They do not
   overlap or continue through the corner assembly.
6. Adjacent members of a multi-member corner assembly are linked; no parallel,
   structurally independent corner legs are permitted.

## Graph Contract

Visual intersection is not structural connectivity. Every intended joint must
be represented by one shared node id and every intersected member must be split
at that node. After excluding non-structural drawing artifacts, every support
member must be reachable from the waling through the member-node graph.

Nodes within `node_snap_tolerance` merge. Important distinct nodes must not be
closer than 3 m; 6 m is preferred for the representative large-brace case.
Nearby parallel regular members must have at least 3 m clear centerline spacing,
with 6 m preferred unless they are the explicitly identified members of a pair.

## Non-bypassable Acceptance

A defect can be marked fixed only when all of the following exist:

- an open GitHub Issue (or an explicitly marked pending issue draft while GitHub
  authentication is unavailable);
- a named regression test that first failed for the reproduced defect;
- `python -m pytest test_strut_minimal.py test_issue_management.py -v` passes;
- `python run_engineering_strut_checks.py` reports all checks passed;
- the affected DXF and PNG are regenerated and visually compared with the real
  references;
- the Issue receives the commands, results, changed files and evidence paths.

Failed or incomplete verification leaves the Issue open. A test or validator
must not be weakened merely to clear an Issue.
