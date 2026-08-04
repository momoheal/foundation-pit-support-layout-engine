# L-Shaped Boundary-Driven Support Design

## Status

Design approved by the user on 2026-08-04. This document defines the geometry contract for Issue #2. It is not an implementation plan and must be reviewed before code changes begin.

## Problem

The current support generator treats an L-shaped excavation as a rectangular grid with one corner removed. That produces main struts which overlap the excavation boundary, crosses the missing notch, and leaves the re-entrant corner without a coherent load path. Validation currently does not detect all of these failures.

## Structural model

The input polygon is the complete excavation boundary. Every boundary segment participates in the support system. The waling centerline is generated from that boundary and remains continuous through the re-entrant corner. The excavation boundary is not reconstructed from a bounding rectangle.

The L shape is partitioned into two support zones at the re-entrant corner:

1. The long-arm zone receives its own boundary-normal opposite-strut groups.
2. The short-arm zone receives its own boundary-normal opposite-strut groups.
3. The two groups are allowed to share only explicit structural nodes in the conversion-node group. No main strut may cross the missing notch.

## Member topology

### Waling and edge truss

- Waling centerline follows every segment of the inward-offset boundary.
- The outer chord of an edge truss is the same structural line as the waling, not an independent parallel ribbon.
- Outer chord terminals land on actual waling corner or panel nodes.
- The inner chord is offset toward the excavation interior and is panelized between real nodes.
- At an inner-chord/web intersection, the inner chord may continue to the waling; that continuation is part of the corner brace load path and is not duplicated as a short parallel link.

### Zone struts

For each boundary segment, cast a normal into the excavation and connect it to the first visible opposite waling in the same support zone. A candidate is rejected when it overlaps the excavation boundary, runs longitudinally along a boundary segment, or crosses the notch. Horizontal and vertical arms therefore form separate strut groups.

### Re-entrant conversion-node group

The conversion group is the only interface between the two zones. It consists of existing waling nodes, edge-truss chord nodes, and their intersections. A conversion diagonal is allowed only when both endpoints are registered structural nodes and the diagonal forms a non-degenerate triangle with the adjacent chord/waling members. The concave vertex is never treated as a convex corner and never receives a convex-corner brace by fallback.

### Pillars and secondary links

Pillars are sparse and may be placed only at registered structural intersections or other approved load-bearing nodes. No pillar or tie is created at a computed centroid. When an existing strut crossing already closes the local triangle, no additional short or near-parallel link is added.

## Geometry invariants

The implementation must enforce these invariants before a layout is accepted:

- Every original boundary segment has a continuous waling and edge-truss representation.
- Every member endpoint resolves to a waling, chord, registered intersection, pillar, or ring node.
- No main strut intersects the original excavation polygon boundary except at an explicitly registered endpoint.
- No main strut crosses the re-entrant notch or runs along an excavation edge.
- The outer chord and waling are coincident within node tolerance.
- The inner chord continuation reaches a waling node and is classified as part of the corner-brace path.
- The concave vertex has no convex-corner brace.
- Duplicate, coincident, and near-parallel members are rejected where an existing triangular load path already exists.

## Validation and regression coverage

Add an L-shaped case using `[(0, 0), (60, 0), (60, 20), (30, 20), (30, 40), (0, 40)]` with the existing brace parameters. Regression checks must assert:

1. The current `x=30` and `y=20` edge-overlap members are absent.
2. All six boundary segments receive waling/edge-truss coverage.
3. Zone struts do not cross the notch and do not overlap the original excavation boundary.
4. The re-entrant vertex has no convex brace.
5. Conversion members have registered endpoints and form valid triangles.
6. No dangling centroid-anchored tie, duplicate member, invalid pillar, or unregistered endpoint is emitted.
7. Diagnostic PNG review shows two compact, symmetric-within-zone support fields and no dense local line fan.

The engineering-check script must include this case and fail on any invariant violation; validation must not be weakened to hide a generation defect.

## Out of scope

This design does not select steel sizes, jack zones, staging levels, soil parameters, or a global optimization algorithm. It also does not authorize changes to unrelated support systems.

## Implementation gate

The user must review this document. Only after approval should an implementation plan be written and code changes begin.
