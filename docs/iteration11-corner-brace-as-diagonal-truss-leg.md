# Iteration 11 Feedback: Corner Brace Is a Diagonal Truss Leg, Not a Separate Zone

> **SUPERSEDED ON 2026-07-29.** The corner-vertex requirements R39, R40,
> R45 and R47 in this historical document are rejected by the current real
> drawing review. Do not implement them. The current authority is
> `docs/superpowers/specs/2026-07-29-structural-topology-red-lines-design.md`:
> large-brace corner lattices use two setback anchors on adjacent waling edges
> and never connect a truss leg directly to the true corner vertex or an
> unsplit main-strut midspan.

> Follow-up to `docs/iteration10-explicit-corner-truss-algorithm.md`.
> Based on a real reference drawing (3D axonometric CAD view of an actual
> foundation-pit support structure) plus `large_brace_corner_truss_120x80`
> and `straight_truss_60x40`.

## This supersedes R26, R32, and R35

Iterations 8-10 tried to solve the corner by giving it its own bounded
"zone" - first a fan of long diagonals, then a boxed zone with crosshatch,
then an explicit fan-of-tiers-plus-rungs recipe. **All of these were the
wrong shape of solution.** The reference drawing shows the real answer is
much simpler: the corner brace is not a distinct construction at all - it's
the same edge-truss primitive (two parallel chords + zigzag web, at the same
`truss_depth` and `truss_panel_length` used everywhere else), just built
along a diagonal direction instead of along an edge. R26, R32, and R35 are
retired; this document replaces them.

## What the reference drawing shows

1. **Edge-truss chords run continuously all the way to the ring-beam corner
   vertex.** Both the outer chord (along the waling/ring beam) and the inner
   chord turn every corner - including the curved/chamfered corners visible
   in the reference - as one uninterrupted line. There is no separate
   "corner zone" with a different chord offset or a box shape; the standard
   edge-truss construction simply continues around the bend.
2. **The corner brace is an additional diagonal truss leg, built from the
   same primitive, meeting at the ring-beam corner node.** At each corner,
   besides the two edges' chords meeting at the corner vertex, there's a
   short diagonal truss segment (same double-chord + zigzag-web
   construction, oriented along the corner's bisector) running from that
   same shared corner vertex inward, terminating either on the edge
   trusses' inner chord or on the internal main-strut grid.
3. **The "nested similar triangles" look comes from the diagonal leg's own
   web zigzag, not from multiple parallel diagonal lines.** A short
   diagonal truss segment built with the normal chord+web module naturally
   shows 2-3 repeating triangles along its length - this is what should have
   been built all along, instead of the R35 fan-of-tiers construction.
4. **Local triangulated stiffening appears wherever the internal strut grid
   crosses the perimeter truss**, not just a bare node - small
   square/diagonal reinforcement cells sit right at those crossings in the
   reference.
5. **The internal main-strut grid is not perfectly uniform** - spacing
   visibly tightens in some regions, consistent with local load/opening
   conditions rather than one fixed modulus applied everywhere.

## Requirements for the agent

**R39 - Edge-truss chords terminate exactly at the ring-beam corner vertex.**
Remove the separate "corner zone" boundary entirely. The standard edge-truss
generator (the unified loop from R14/R15) should run each chord all the way
to the actual corner point of the outer waling/ring beam - the same point
where the adjacent edge's chord also terminates. Both edges' outer chords
(and both inner chords) should end at literally the same corner-vertex node.

**R40 - Corner brace = one diagonal truss leg built from the shared truss
primitive (finalizes R25).**
At each corner, generate a diagonal truss segment using the exact same
function used for straight edges - same `truss_depth`, same
`truss_panel_length` - but oriented along the corner's bisector direction.
Its outer end starts at the shared corner-vertex node from R39 (where both
edges' outer chords meet). Its inner end terminates at whichever is nearer:
a natural point on the edge trusses' inner chord, or a node on the internal
main-strut grid. Length is whatever it takes to reach that termination point
- no artificial tier count or reach cap is needed, since the leg is just an
ordinary truss segment of natural length, not a special bounded construction.

**R41 - Add local triangulated stiffening at every main-strut/truss-chord
crossing (extends R31).**
Wherever an internal main strut crosses the perimeter truss (already
required to be a real shared node per R31), add a small stiffening
triangulation at that crossing - consistent with the reference drawing's
small square/diagonal reinforcement cells - rather than leaving it as a bare
node.

**R42 - Allow non-uniform internal strut/tie spacing where justified.**
Don't assume the internal main-strut grid must use one constant spacing
across the whole pit. Once exclusion zones, load concentration, or opening
data exist (see the original improvement design doc's P1 backlog on
structural exclusion zones), the grid should be able to densify locally -
this is a lower-priority, forward-looking note rather than an immediate fix,
since the current codebase has no such input data yet.

**R43 - Tag corner-adjacent edge-truss panels as part of the corner-brace
assembly for scheduling purposes.**
Even though the edge-truss panels nearest a corner are built with the
standard edge-truss primitive (per R39, no geometric difference), they
should carry a grouping tag (e.g. `belongs_to_corner_bracket: <corner_id>`)
alongside the corner leg itself, so BOM/schedule exports can report the
corner brace as one coherent assembly rather than splitting it arbitrarily
between "edge truss" and "corner truss" categories.

## Acceptance criteria

- No separate corner-zone geometry (box, crosshatch, or tiered fan) remains
  anywhere in the output - corners are produced entirely by R39 (continuous
  edge chords) + R40 (one diagonal leg).
- Both edges' outer chords, and both inner chords, share the same node at
  each corner vertex.
- The diagonal corner leg is built from the same function as straight-edge
  trusses (verifiable by comparing panel construction, not just visual
  similarity).
- Main-strut/truss-chord crossings show local stiffening triangulation, not
  a bare crossing.
- Corner-adjacent edge-truss members and the corner leg carry a shared
  grouping tag.

## Suggested test cases

| Test | Purpose |
|---|---|
| `edge_truss_chords_meet_at_corner_vertex` | Both adjacent edges' outer (and inner) chords share the exact corner-vertex node |
| `corner_leg_uses_shared_truss_primitive` | The diagonal corner leg is generated by the same function/parameters as straight-edge truss panels |
| `corner_leg_terminates_on_inner_chord_or_strut_grid` | Corner leg's inner end lands on a real node (inner chord or internal grid), not open space |
| `strut_truss_crossing_has_local_stiffening` | Every main-strut/truss-chord crossing includes a small stiffening triangulation, not just a bare node |
| `corner_assembly_members_share_grouping_tag` | Corner leg + adjacent edge-truss panels carry a matching `belongs_to_corner_bracket` tag |

## Out of scope for this iteration

- R42 (non-uniform internal grid spacing) - depends on exclusion-zone data
  that doesn't exist yet; track under the original P1 backlog, not this fix.
- Anything already resolved in iterations 5-9 that isn't touched by removing
  the corner-zone concept (perimeter continuity outside corners, tie style,
  truss-min-span gating).

## Note on this document's relationship to prior iterations

This is the second time a corner-truss approach has needed a significant
course correction (iteration 7's initial fan idea, then this iteration's
full replacement of the zone concept). Once R39/R40 are implemented and
confirmed against both test cases, treat the corner-truss construction as
closed and rely on the test suite (not further visual iteration) to catch
regressions - further hand-tuning the corner shape from screenshots has
reached diminishing returns compared to locking in this simpler, unified
model.

## Iteration 12 revised decision

R45 uses the full double-chord truss-leg option described by R40. The leg's
outer anchor is always the exact waling corner vertex (R47), never a clipped
chamfer between offset edge points. Its inner terminal is the nearest main-grid
intersection at least `truss_panel_min` from the corner, with the perimeter
inner corner retained only as a fallback when no such structural intersection
exists. The leg is tiled into repeated shared-primitive panels so no panel axis
length exceeds `truss_panel_max`; large pits therefore show multiple triangular
modules while short legs may collapse to one module.
