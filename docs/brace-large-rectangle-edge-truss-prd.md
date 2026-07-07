# Brace Large Rectangle Edge Truss PRD

## Background

This project generates internal bracing layouts for foundation pit excavations. For a generated layout to be useful, each line must represent a plausible structural member: waling, main strut, tie, corner bracing, truss chord, truss web, ring, radial strut, or pillar.

The current high-risk case is `support_system="brace"` when `_uses_large_corner_truss(waling_poly)` is true, represented by the `large_rect_120x80_brace` sample. The current output uses perimeter truss chords and webs to cover the corner zones, but the generation order allows edge truss nodes to be created before the primary bracing topology is known.

The user confirmed the first implementation should be the B option: only fix the large rectangle `brace` edge-truss path with a minimal, incremental change.

## Problem

The large rectangle `brace` path currently has three engineering risks:

1. Edge truss chord nodes may be generated separately from later main strut or corner-zone anchors.
2. Truss webs may cross main struts, ties, or intended corner-zone support lines without being a designed connection.
3. Corner-zone behavior is visually and semantically easy to misunderstand as radial bracing, while actual corner bracing should be based on points taken along the two adjacent walings to form triangular bracing lines.

Current tests also require the large rectangle `brace` scenario to keep `corner` members empty. Therefore the first implementation must improve internal topology without changing the public output into explicit `corner` members.

## Goals

- Limit implementation to `support_system="brace"` and the `_uses_large_corner_truss(waling_poly)` branch.
- Preserve behavior for `straight_truss`, normal-size `brace`, `orthogonal`, `opposite_strut`, and `circular`.
- Generate primary main struts first, then compute internal corner triangle anchors, then generate edge truss chords and webs.
- Treat corner-zone anchors as points on adjacent waling edges, not radial points from a corner or centroid.
- Snap edge truss chord nodes to main strut endpoints and corner triangle anchors.
- Skip truss webs that would create non-endpoint crossings with primary support members or corner semantic lines.
- Keep the public layout contract unchanged.

## Non-Goals

- Do not modify `straight_truss`.
- Do not add a new `support_system`.
- Do not add public parameters.
- Do not add public layout fields.
- Do not output large rectangle corner zones as `corner` members.
- Do not relax validation to hide generation errors.
- Do not implement section design, capacity checks, stability checks, prestress design, or construction-stage analysis.
- Do not solve haunches, material-aware waling support spacing, jack zones, or body-structure avoidance in this iteration.

## Users

- Structural engineers reviewing generated diagnostic PNGs and DXF output.
- CAD automation users relying on stable `layout` fields and member kinds.
- Developers extending `strut_engine.py` without reintroducing dangling nodes or illegal crossings.

## User Stories

- As a structural reviewer, I want large rectangle corner-zone bracing to follow adjacent waling geometry so the drawing does not look like radial bracing.
- As a CAD output user, I want main strut endpoints and edge truss chord nodes to share anchors so there are no close-but-separate connection points.
- As a validation user, I want truss webs to avoid non-designed crossings with main struts, ties, and corner semantic lines.
- As a downstream consumer, I want `layout["corners"] == []` and `stats["corner_length"] == 0.0` to remain true for the current large rectangle `brace` case.

## Functional Requirements

1. In the large rectangle `brace` branch, solve order must become:

   ```text
   waling
   -> main_struts_avoiding_corner_coverage
   -> internal corner triangle anchors
   -> edge_truss snapped to main and corner anchors
   -> truss_coupling_ties
   -> secondary_perimeter_supports
   -> structural_cross_nodes
   -> pillars
   ```

2. The corner anchor model must be internal only and include:

   - `anchors`: points on adjacent waling edges.
   - `semantic_lines`: triangular corner support lines and same-side layer coupling lines used for avoidance.

3. Edge truss generation must accept optional extra anchors and optional avoid lines.
4. Existing edge truss callers must remain compatible when those optional arguments are omitted.
5. Large rectangle `brace` output must still contain `truss_chord` and `truss_web` members.
6. Large rectangle `brace` output must not contain `corner` members.
7. Truss web candidates must be rejected if they create non-endpoint crossings with main struts, ties, or corner semantic lines.

## Acceptance Criteria

- `python -m pytest test_strut_minimal.py -v` passes.
- `python run_engineering_strut_checks.py` passes and reports all engineering checks passed.
- `large_rect_120x80_brace` still has no `corner` members.
- `large_rect_120x80_brace` keeps continuous perimeter truss coverage within `truss_panel_max`.
- Edge truss nodes include main strut edge anchors and corner triangle anchors where they lie on the same waling edge.
- Truss webs do not create non-endpoint crossings with `main_strut`, `tie`, or the internal corner semantic lines.
- The diagnostic PNG for `large_brace_corner_truss_120x80` no longer suggests radial corner bracing.

## Risks

- Skipping invalid truss webs may reduce local triangulation density.
- Internal-only corner anchors improve generation but remain invisible to downstream diagnostics unless later promoted to public members or debug output.
- Keeping `corner` members empty preserves compatibility but delays a cleaner explicit `corner_truss` data model.
- `_uses_large_corner_truss` is size-based, so any future non-rectangular large pit may need additional shape gating before sharing this path.

## References

- [Brace large rectangle edge truss minimal design](superpowers/specs/2026-07-07-brace-large-rectangle-edge-truss-minimal-design.md)
- [Foundation pit support geometry constraints](superpowers/specs/2026-07-07-foundation-pit-support-geometry-constraints-design.md)
- [AGENTS.md](../AGENTS.md)

