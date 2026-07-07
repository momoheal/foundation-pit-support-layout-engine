# Brace Large Rectangle Edge Truss Technical Spec

## Scope

Implement the minimal B option for `support_system="brace"` when `_uses_large_corner_truss(waling_poly)` is true. The target file is `strut_engine.py`, with focused regression coverage in `test_strut_minimal.py`. Only update `run_engineering_strut_checks.py` if existing engineering assertions must be synchronized with the corrected geometry.

## Current Flow

Current large rectangle `brace` flow:

```text
waling
-> main_struts_avoiding_corner_coverage
-> edge_truss
-> truss_coupling_ties
-> secondary_perimeter_supports
-> structural_cross_nodes
-> pillars
```

Problems in the current flow:

- `_place_edge_truss()` only merges main strut edge anchors.
- `_place_edge_truss()` does not accept corner semantic anchors.
- `_place_edge_truss()` does not check `truss_web` candidates against main struts, ties, or corner semantic lines before adding members.
- `_add_structural_cross_nodes()` can create nodes after the fact, and validation may treat explicit nodes as legal connections. Therefore invalid web crossings must be prevented during generation, not cleaned up later.

## Proposed Flow

New large rectangle `brace` flow:

```text
waling
-> main_struts_avoiding_corner_coverage
-> large_brace_corner_anchor_model
-> edge_truss(extra_anchor_points=anchors, avoid_lines=semantic_lines)
-> truss_coupling_ties
-> secondary_perimeter_supports
-> structural_cross_nodes
-> pillars
```

All other support-system flows remain unchanged.

## Internal Data Model

Use an internal dict, not a public layout field:

```python
{
    "anchors": list[Point2D],
    "semantic_lines": list[Geometry],
}
```

`anchors` are waling-edge points used for edge truss snapping.

`semantic_lines` are not output members. They represent:

- corner triangular support lines: `left_i -> right_i`
- same-side layer coupling lines: `left_i -> left_{i+1}` and `right_i -> right_{i+1}`

## Engine Changes

### `_large_brace_corner_anchor_model(layout, waling_poly)`

Add a private helper in `strut_engine.py`.

Requirements:

- Only used by the large rectangle `brace` branch.
- Use open waling coordinates from `layout["waling"]`.
- Only generate anchors for convex corners.
- For each convex corner, take points along the two adjacent waling edges.
- Use existing parameters only: `spacing`, `spacing_min`, `truss_panel_max`, and `corner_layers`.
- Do not add public parameters.
- Do not output `corner` members.
- Candidate semantic lines must be covered by `waling_poly.buffer(tol)`.
- Anchor endpoints must lie near `waling_poly.exterior`.

Recommended return shape:

```python
return {
    "anchors": anchors,
    "semantic_lines": semantic_lines,
}
```

### `_place_edge_truss(...)`

Extend the signature compatibly:

```python
def _place_edge_truss(
    self,
    layout: dict[str, Any],
    waling_poly: Polygon,
    *,
    extra_anchor_points: Geometry | None = None,
    avoid_lines: list[Geometry] | None = None,
) -> None:
```

Requirements:

- Existing calls without keyword arguments keep the same behavior.
- Large rectangle `brace` passes corner anchors through `extra_anchor_points`.
- Large rectangle `brace` passes corner semantic lines through `avoid_lines`.
- Outer edge truss nodes merge main strut anchors and extra anchors before chord/web generation.
- Inner nodes remain derived from merged outer nodes and inward edge normal.

### Anchor Merge

Either extend `_merge_edge_main_strut_anchors(...)` or introduce `_merge_edge_anchor_points(...)`.

Required behavior:

- Keep current main strut endpoint merging.
- Add `extra_anchor_points`.
- Only keep anchors that lie on or near the current edge.
- Project nearby anchors to the current edge where needed.
- Sort and deduplicate along the edge.
- Preserve the existing horizontal/vertical edge behavior.

### Web Avoidance

Add a small helper if useful:

```python
def _candidate_avoids_lines(candidate: Geometry, avoid_lines: list[Geometry]) -> bool:
    ...
```

Rules for each `truss_web` candidate:

- Must remain inside `waling_poly`.
- Must not start at a waling corner.
- Must pass existing close-parallel checks.
- Must not create non-endpoint crossings with `main_strut` or `tie`.
- Must not create non-endpoint crossings with `avoid_lines`.

Use existing helpers where possible:

- `_intersection_points(...)`
- `_is_connection_point(...)`
- `_candidate_clear(...)`
- `_candidate_parallel_clear(...)`

## Test Plan

Add focused tests for `large_rect_120x80_brace`.

### Corner Anchor Geometry

Verify the internal corner anchor model:

- Each semantic corner brace line has endpoints on two adjacent waling edges.
- No corner semantic line starts at the exact waling corner.
- Anchors are not centroid/radial-only points.

### Edge Truss Snapping

Verify edge truss outer chord nodes include:

- main strut endpoints on waling
- corner anchors on the matching edge

### Web Avoidance

Verify `truss_web` members do not non-endpoint-cross:

- `main_strut`
- `tie`
- internal corner semantic lines

### Compatibility

Retain current public behavior:

- no `corner` members in `large_rect_120x80_brace`
- `layout["corners"] == []`
- `stats["corner_length"] == 0.0`
- existing perimeter truss continuity tests pass
- existing main strut grouping and coupling tie tests pass
- existing pillar sparsity tests pass

## Verification

Run:

```bash
python -m pytest test_strut_minimal.py -v
python run_engineering_strut_checks.py
```

Regenerate and inspect:

```text
engineering_check_outputs/large_brace_corner_truss_120x80.png
```

Visual review should confirm:

- corner zones no longer look radial
- edge truss nodes align with primary anchors
- truss webs do not visibly pass through main struts without a designed connection

## Implementation Boundaries

- Do not modify `straight_truss`.
- Do not modify public layout schema.
- Do not add public parameters.
- Do not add member kinds.
- Do not add stats keys.
- Do not modify DXF layer mapping.
- Do not relax `strut_validation.py`.
- Do not hand-build member dictionaries.

## Open Questions For Implementation

Ask before proceeding if any of these occur:

1. Web avoidance removes too many webs to satisfy current corner triangulation tests.
2. Tests need direct access to the internal corner anchor model but the helper shape becomes awkward.
3. Existing engineering checks conflict with the corrected geometry.
4. A public field or parameter seems necessary.
5. Validation changes seem necessary to prove the new behavior.

