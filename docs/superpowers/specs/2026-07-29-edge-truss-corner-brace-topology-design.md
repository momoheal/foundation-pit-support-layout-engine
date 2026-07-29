# Edge-Truss and Corner-Brace Topology Redesign

## Status and Authority

This design records the geometry approved by the user on 2026-07-29 for
`large_brace_corner_truss_120x80`, with `straight_truss_60x40` as the secondary
regression case. It supersedes the continuous perimeter-band model in
`2026-07-29-structural-topology-red-lines-design.md` and every earlier rule that
models the edge truss and corner zone as one closed double-chord belt.

The visual authority is the two real drawing references supplied in this task:

- `codex-clipboard-d5a958e8-3da7-4766-b1b6-ad86c9e535f0.png`
- `codex-clipboard-f71afbce-f2aa-48ff-ad2f-02e560d90d67.png`

The approved interpretation was reviewed through the local visual companion.
Tests and validators may enforce this design but may not redefine it.

## Problem and Root Cause

The rejected output is
`engineering_check_outputs/large_brace_corner_truss_120x80.png`. It shows a
nearly continuous octagonal double-chord band. Its corner chamfers absorb the
corner braces, its outer truss chord is separate from the waling, and its
corner webs do not follow the modular load path in the references.

The root cause is architectural:

- `_place_large_brace_perimeter_truss()` explicitly builds edge panels and
  corner lattices as one connected band.
- `_truss_panel_member_specs()` creates a `truss_chord` for the outer edge even
  where that physical member is already the waling.
- `_large_brace_corner_anchor_model()` creates setback corner handoffs that
  chamfer the edge-truss chords instead of keeping four discrete straight edge
  trusses.

The old band generator must be replaced for the affected support systems. It
must not be trimmed, patched, or hidden by validation changes.

## Boundary and Member Identity

`coords` represents the excavation edge. The waling centerline lies outside
the excavation edge by `waling_offset`; for this engineering model,
`waling_offset` is the retaining-pile radius. Diagnostic rendering must show
the excavation edge on the pit-interior side of the waling centerline.

This boundary-direction rule is global because `_place_waling()` is shared by
all support systems. The implementation must not give `waling_offset` opposite
meanings in different `support_system` branches. The discrete edge-truss and
modular corner rules below apply only where an edge truss is generated.

The edge-truss outer chord and the waling are the same physical member:

- generation creates one `waling` member, not a coincident `truss_chord`;
- the waling member carries the additional structural role
  `edge_truss_outer_chord` in member attributes;
- outlines, statistics, BOM quantities, graph connectivity, and DXF export
  count and draw this physical member once;
- four discrete straight edge-truss systems reference the adjacent waling
  edges; they do not form a closed inner/outer chord band around corners.

Each edge truss has one inner chord parallel to its waling edge. At a convex
orthogonal corner, the two adjacent inner chords cross at a registered shared
node and continue beyond that node until they reach the opposite adjacent
waling edges. These continuation segments are both inner-chord segments and
part of the corner-brace assembly. They are one geometry split into role-tagged
segments, not coincident members.

## Modular Corner Geometry

Use a local orthogonal coordinate system at each convex corner:

- `V` is the waling corner;
- `e1` and `e2` are unit vectors from `V` along the two adjacent waling edges;
- `d` is `corner_truss_tier_spacing` when explicitly supplied, otherwise the
  effective edge-truss depth;
- `N` is the integer `corner_truss_tier_count`, with default `N = 3`.

The adjacent inner chords are the lines parallel to `e1` and `e2`, each offset
inward by `d`. Their common node is:

```text
Q = V + d * e1 + d * e2
```

For corner tier `k`, define two real waling anchors:

```text
A_k = V + k * d * e1
B_k = V + k * d * e2
```

The tier member `C_k` connects `A_k` to `B_k`. Every tier is a `truss_web`
within the same corner assembly; it is not duplicated as a separate `corner`
member.

### Tier 1

`C_1` is both the first corner brace and the first local edge-truss web. It is
generated once. No additional panel web may overlap it.

### Tier 2

`C_2` passes through `Q`. `Q` is a shared graph node, and `C_2` plus both inner
chords are split at that node. No near-coincident substitute node is allowed.

### Tier 3

`C_3` crosses both inner chords. Let its two registered intersection nodes be
`P1` and `P2`. The two perpendicular webs are not arbitrary projections:

- `P1` connects to the same-side tier-2 waling anchor;
- `P2` connects to the other tier-2 waling anchor.

Each resulting web is perpendicular to its corresponding waling edge. The
endpoints are existing nodes: one `C_3`/inner-chord intersection and one
`C_2`/waling anchor.

### Additional Tiers

For `k > 3`, `C_k` connects `A_k` and `B_k`. Its intersections with the two
inner chords connect back to the corresponding `A_(k-1)` and `B_(k-1)` waling
anchors. This preserves the same modular lattice without inventing new
projection points.

The requested tier count is reduced only when the adjacent waling lengths
cannot contain the anchors with required end clearance. The representative
120 m by 80 m case must produce at least three tiers at every convex corner.
The generator must not compress `d`, create near-coincident anchors, or silently
fall back to one tier.

## Data and Generation Flow

`solve_brace()` and `solve_straight_truss()` remain thin orchestration methods:

1. Build the outward waling polygon and its members.
2. Place main struts against real waling nodes.
3. Build four discrete straight edge-truss inner chords and ordinary panels.
4. Build each convex modular corner assembly from the formulas above.
5. Split all chord, brace, and web members at structural intersections.
6. Merge nodes only within `node_snap_tolerance`.
7. Add stiffening, ties, and pillars after the corner topology is complete.
8. Validate member identity, connectivity, spacing, and corner formulas.

All new linear geometry goes through `_add_linear_member()` and `_add_member()`.
Member attributes identify shared roles without duplicating geometry:

- waling: `structural_roles` includes `edge_truss_outer_chord`;
- inner-chord continuation: `corner_role = "inner_chord_extension"`;
- tier member: `corner_role = "tier_1"`, `"tier_2"`, and so on;
- perpendicular web: `corner_role = "tier_k_perpendicular_web"`;
- all corner members: `belongs_to_corner_bracket = <assembly_id>`.

## Non-Bypassable Geometry Red Lines

The layout is invalid if any of the following occurs:

- a `truss_chord` duplicates or runs coincident with a waling member;
- the edge-truss chords form a chamfered or closed perimeter band;
- an inner chord stops at its corner intersection instead of reaching the
  opposite adjacent waling;
- tier 1 is represented by separate coincident brace and web members;
- tier 2 misses the inner-chord common node;
- a tier endpoint lands on an inner chord instead of the waling;
- a tier-3 perpendicular web uses an arbitrary projected point instead of the
  matching tier-2 waling anchor;
- distinct member intersections create a node cluster below
  `min_node_separation`;
- duplicate segments or unclassified close, nearly parallel segments occur in
  a corner assembly;
- a validator, score, or rendering filter suppresses any of these defects.

The intentionally parallel tier members are permitted only when they are
classified in the same corner assembly and retain the full modular separation
implied by `d`. Classification never excuses duplicate or compressed members.

## Test-First Acceptance

The old implementation must first fail these named regression tests:

- `test_p0_waling_is_outside_excavation_edge_by_pile_radius`
- `test_p0_edge_truss_outer_chord_reuses_waling_member`
- `test_p0_edge_trusses_are_discrete_straight_systems`
- `test_p0_inner_chords_cross_then_reach_opposite_waling`
- `test_p0_corner_tier_one_is_the_first_web_once`
- `test_p0_corner_tier_two_passes_inner_chord_common_node`
- `test_p0_corner_tier_three_webs_reach_tier_two_waling_anchors`
- `test_p0_corner_zone_has_no_dense_duplicate_or_close_parallel_members`

After the failing tests are recorded, the minimal implementation must make
them pass without weakening existing engineering checks. Completion requires:

```text
python -m pytest test_strut_minimal.py test_issue_management.py -v
python run_engineering_strut_checks.py
```

The following evidence must be regenerated and visually compared with both
real references:

- `engineering_check_outputs/large_brace_corner_truss_120x80.png`
- `engineering_check_outputs/large_brace_corner_truss_120x80.dxf`
- `engineering_check_outputs/straight_truss_60x40.png`
- `engineering_check_outputs/straight_truss_60x40.dxf`

A numeric pass is insufficient. The P0 Issue remains Open / Unverified until
the red-green test record, command output, refreshed files, and explicit visual
review all exist.
