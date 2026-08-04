# L-Shaped Boundary-Driven Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate buildable, boundary-driven bracing for an L-shaped excavation by separating its two visible support fields and joining them only through explicit waling/truss conversion nodes.

**Architecture:** Keep `solve_brace()` as orchestration. Add reusable visibility-segment and perimeter-edge models inside `StrutEngine`; use Shapely intersections to derive first-visible opposite waling spans and polygon coverage to select inward edge normals. Extend validation with excavation-boundary and re-entrant-notch red lines, then lock the behavior with unit, engineering, DXF, and PNG evidence attached to GitHub Issue #2.

**Tech Stack:** Python 3.10+, Shapely, pytest, ezdxf, Matplotlib, GitHub CLI.

---

## File map

- Modify `strut_engine.py`: visible-zone main-strut generation, boundary-edge truss panels, concave conversion-node topology.
- Modify `strut_validation.py`: reject boundary-overlap, notch-crossing, and unanchored conversion members.
- Modify `test_strut_minimal.py`: exact L-shaped topology and regression assertions.
- Modify `run_engineering_strut_checks.py`: add the L-shaped engineering case and hard checks.
- Modify `docs/issues/INDEX.md`: generated GitHub Issue mirror only; never edit by hand.
- Generate `engineering_check_outputs/l_shape_brace_60x40.{dxf,png}`: visual/CAD evidence; stage only if repository policy tracks generated evidence.

### Task 1: Lock the L-shaped failure as regression tests

**Files:**
- Modify: `test_strut_minimal.py`

- [ ] **Step 1: Add shared L-shaped test helpers**

Add these helpers near the existing geometry helpers:

```python
L_SHAPE_COORDS = [(0, 0), (60, 0), (60, 20), (30, 20), (30, 40), (0, 40)]


def _l_shape_layout() -> dict[str, Any]:
    params = {
        "support_system": "brace",
        "spacing": 9.0,
        "waling_offset": 2.0,
        "safe_dist": 1.5,
    }
    return StrutEngine(L_SHAPE_COORDS, params).solve()


def _member_line(member: dict[str, Any]) -> LineString:
    return LineString(member["geometry"])
```

- [ ] **Step 2: Write failing visibility and boundary tests**

```python
def test_l_shape_main_struts_use_visible_opposite_waling_only() -> None:
    layout = _l_shape_layout()
    excavation_boundary = Polygon(L_SHAPE_COORDS).boundary
    main = [member for member in layout["members"] if member["kind"] == "main_strut"]

    assert main
    assert all(_member_line(member).intersection(excavation_boundary).length <= 1e-6 for member in main)
    assert not any(
        abs(member["geometry"][0][0] - 30.0) <= 1e-6
        and abs(member["geometry"][-1][0] - 30.0) <= 1e-6
        for member in main
    )
    assert not any(
        abs(member["geometry"][0][1] - 20.0) <= 1e-6
        and abs(member["geometry"][-1][1] - 20.0) <= 1e-6
        for member in main
    )


def test_l_shape_has_separate_long_and_short_arm_strut_fields() -> None:
    layout = _l_shape_layout()
    main = [member for member in layout["members"] if member["kind"] == "main_strut"]
    vertical_spans = [member for member in main if abs(member["geometry"][0][0] - member["geometry"][-1][0]) <= 1e-6]
    horizontal_spans = [member for member in main if abs(member["geometry"][0][1] - member["geometry"][-1][1]) <= 1e-6]

    assert any(max(point[1] for point in member["geometry"]) > 20.0 for member in vertical_spans)
    assert any(max(point[0] for point in member["geometry"]) > 30.0 for member in horizontal_spans)
    assert all(Polygon(layout["waling"]).buffer(1e-6).covers(_member_line(member)) for member in main)
```

- [ ] **Step 3: Write failing perimeter and concave-node tests**

```python
def test_l_shape_edge_truss_covers_every_waling_edge() -> None:
    layout = _l_shape_layout()
    waling_edges = [
        LineString([start, end])
        for start, end in zip(layout["waling"][:-1], layout["waling"][1:])
    ]
    outer_chords = [
        _member_line(member)
        for member in layout["members"]
        if member["kind"] == "truss_chord" and member.get("truss_role") == "outer_chord"
    ]

    assert len(waling_edges) == 6
    assert outer_chords
    assert all(unary_union(outer_chords).buffer(1e-6).covers(edge) for edge in waling_edges)


def test_l_shape_reentrant_corner_uses_one_registered_conversion_group() -> None:
    layout = _l_shape_layout()
    conversion = [
        member for member in layout["members"]
        if member.get("conversion_group") == "reentrant_1"
    ]
    node_positions = [Point(node["pos"]) for node in layout["nodes"]]

    assert conversion
    assert all(member.get("corner_class") == "concave" for member in conversion)
    assert all(
        any(point.distance(Point(endpoint)) <= 1e-6 for point in node_positions)
        for member in conversion
        for endpoint in (member["geometry"][0], member["geometry"][-1])
    )
    assert not any(
        member["kind"] == "corner"
        and _member_line(member).distance(Point(30.0, 20.0)) <= 2.0
        for member in layout["members"]
    )
```

Add `unary_union` to the existing Shapely imports.

- [ ] **Step 4: Run the focused tests and confirm the current defect**

Run:

```powershell
$env:TMP = "$PWD\.tmp_runtime"
$env:TEMP = "$PWD\.tmp_runtime"
$env:MPLCONFIGDIR = "$PWD\.mplconfig"
python -m pytest test_strut_minimal.py -k "l_shape" -v
```

Expected: the new tests fail because `x=30`/`y=20` members overlap the excavation boundary and perimeter-truss coverage/conversion metadata are absent.

- [ ] **Step 5: Commit only the failing tests**

```powershell
git add -- test_strut_minimal.py
git commit -m "test(#2): lock L-shaped support topology red lines"
```

### Task 2: Generate first-visible opposite-waling strut spans

**Files:**
- Modify: `strut_engine.py`
- Test: `test_strut_minimal.py`

- [ ] **Step 1: Add a candidate-span helper**

Place this beside `_place_main_struts()`:

```python
def _visible_support_segments(
    self,
    waling_poly: Polygon,
    line: LineString,
) -> list[LineString]:
    excavation_boundary = self.poly.boundary
    return [
        segment
        for segment in _unwrap_lines(
            waling_poly.intersection(line),
            float(self.params["min_strut_len"]),
        )
        if segment.intersection(excavation_boundary).length <= 1e-6
        and not _line_is_collinear_with_boundary(segment, excavation_boundary)
    ]
```

Add the low-level helper near the other Shapely helpers:

```python
def _line_is_collinear_with_boundary(line: LineString, boundary: Any) -> bool:
    overlap = line.intersection(boundary)
    return not overlap.is_empty and overlap.length > 1e-6
```

- [ ] **Step 2: Route both main-strut generators through the helper**

In `_place_main_struts()` and `_place_main_struts_avoiding_corner_coverage()`, replace each direct `_unwrap_lines(waling_poly.intersection(line), min_len)` loop with:

```python
for seg in self._visible_support_segments(waling_poly, line):
    member = self._add_linear_member(
        layout,
        "main_strut",
        list(seg.coords),
        old_key="struts",
        node_kind="strut_end",
        attributes={"support_zone": _support_zone_key(seg)},
    )
```

Define the deterministic zone key at low level:

```python
def _support_zone_key(line: LineString) -> str:
    midpoint = line.interpolate(0.5, normalized=True)
    start = line.coords[0]
    end = line.coords[-1]
    axis = "x" if abs(start[0] - end[0]) <= abs(start[1] - end[1]) else "y"
    return f"{axis}:{float(midpoint.x):.3f}:{float(midpoint.y):.3f}"
```

Do not add a parameter for this behavior; it is a geometric validity rule.

- [ ] **Step 3: Run focused tests**

Run:

```powershell
python -m pytest test_strut_minimal.py -k "l_shape_main_struts or l_shape_has_separate" -v
```

Expected: both main-strut tests pass; perimeter and conversion tests still fail.

- [ ] **Step 4: Run non-rectangular regression tests**

Run:

```powershell
python -m pytest test_strut_minimal.py -k "main_struts_are_clipped_inside_non_rectangular_wale or main_strut_grid_uses_edge_anchored_modular_spacing" -v
```

Expected: PASS; rectangular spacing defaults and octagonal/irregular containment remain unchanged.

- [ ] **Step 5: Commit the visibility fix**

```powershell
git add -- strut_engine.py test_strut_minimal.py
git commit -m "fix(#2): derive struts from visible opposite waling"
```

### Task 3: Build edge trusses from boundary edges and a concave conversion node

**Files:**
- Modify: `strut_engine.py`
- Test: `test_strut_minimal.py`

- [ ] **Step 1: Add boundary-vertex classification and polygon-aware inward normals**

Place these helpers in the low-level helper section:

```python
def _corner_class(
    prev_pt: Point2D,
    corner: Point2D,
    next_pt: Point2D,
    polygon: Polygon,
) -> str:
    return "convex" if _is_convex_corner(prev_pt, corner, next_pt, polygon) else "concave"


def _polygon_inward_unit_normal(
    start: Point2D,
    end: Point2D,
    polygon: Polygon,
    depth: float,
) -> Point2D:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = hypot(dx, dy)
    if length <= 1e-9:
        return (0.0, 0.0)
    candidates = [(-dy / length, dx / length), (dy / length, -dx / length)]
    midpoint = _line_midpoint((start, end))
    for normal in candidates:
        probe = _offset_point(midpoint, normal, min(depth, 0.25))
        if polygon.buffer(1e-6).covers(Point(probe)):
            return normal
    raise ValueError(f"no inward normal for waling edge {start!r}->{end!r}")
```

Add `hypot` to the existing `math` imports.

- [ ] **Step 2: Introduce a boundary-edge model**

Add a `_perimeter_edge_model()` helper beside the corner-anchor model:

```python
def _perimeter_edge_model(self, waling_poly: Polygon) -> list[dict[str, Any]]:
    coords = _open_coords(_closed_coords(list(waling_poly.exterior.coords)))
    depth = self._edge_truss_depth()
    result = []
    for index, start in enumerate(coords):
        end = coords[(index + 1) % len(coords)]
        prev_pt = coords[index - 1]
        next_after_end = coords[(index + 2) % len(coords)]
        normal = _polygon_inward_unit_normal(start, end, waling_poly, depth)
        result.append({
            "edge_index": index,
            "outer_start": start,
            "outer_end": end,
            "inner_start": _offset_point(start, normal, depth),
            "inner_end": _offset_point(end, normal, depth),
            "start_class": _corner_class(prev_pt, start, end, waling_poly),
            "end_class": _corner_class(start, end, next_after_end, waling_poly),
        })
    return result
```

- [ ] **Step 3: Replace convex-corner-to-convex-corner edge traversal**

Change `_place_large_brace_perimeter_truss()` so panel generation iterates `_perimeter_edge_model(waling_poly)`. Retain the existing station splitting at main-strut endpoints and `_truss_panel_member_specs()`, but attach explicit roles:

```python
attributes = {
    "truss_primitive": "panel",
    "truss_role": "outer_chord" if kind == "truss_chord" and geometry == [outer_a, outer_b] else "inner_chord",
    "boundary_edge": edge_model["edge_index"],
}
```

For `truss_web`, set `truss_role="web"`. Do not emit an extra outer chord offset from the waling.

- [ ] **Step 4: Add the re-entrant conversion group**

After adjacent edge panels are built, pair the two edge models meeting at each concave vertex. Use extended inner-chord lines to obtain the shared inner node, require polygon coverage, and connect the actual waling corner to that node:

```python
def _place_reentrant_conversion_groups(
    self,
    layout: dict[str, Any],
    waling_poly: Polygon,
    edges: list[dict[str, Any]],
) -> None:
    group_index = 0
    min_x, min_y, max_x, max_y = waling_poly.bounds
    extension = hypot(max_x - min_x, max_y - min_y) * 2.0
    for previous, following in zip(edges, edges[1:] + edges[:1]):
        corner = previous["outer_end"]
        if previous["end_class"] != "concave":
            continue
        inner_a = _extended_line(previous["inner_start"], previous["inner_end"], extension)
        inner_b = _extended_line(following["inner_start"], following["inner_end"], extension)
        intersection = inner_a.intersection(inner_b)
        if intersection.geom_type != "Point":
            continue
        shared = (float(intersection.x), float(intersection.y))
        diagonal = LineString([corner, shared])
        if not waling_poly.buffer(1e-6).covers(diagonal):
            continue
        group_index += 1
        attributes = {
            "conversion_group": f"reentrant_{group_index}",
            "corner_class": "concave",
            "truss_role": "conversion_web",
        }
        self._add_linear_member(
            layout,
            "truss_web",
            [corner, shared],
            old_key=None,
            node_kind="truss_node",
            attributes=attributes,
        )
```

Add the extension helper in the low-level section:

```python
def _extended_line(start: Point2D, end: Point2D, extension: float) -> LineString:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = hypot(dx, dy)
    if length <= 1e-9:
        return LineString([start, end])
    unit = (dx / length, dy / length)
    return LineString([
        (start[0] - unit[0] * extension, start[1] - unit[1] * extension),
        (end[0] + unit[0] * extension, end[1] + unit[1] * extension),
    ])
```

Call this helper from `_place_large_brace_perimeter_truss()` after all edge panels exist. Ensure the two inner chords terminate at the same `shared` coordinate instead of creating two close parallel endpoints.

- [ ] **Step 5: Run topology tests**

Run:

```powershell
python -m pytest test_strut_minimal.py -k "l_shape_edge_truss or l_shape_reentrant" -v
```

Expected: PASS with six covered waling edges, one concave conversion group, and no convex brace at `(30, 20)`.

- [ ] **Step 6: Run existing corner-truss regressions**

Run:

```powershell
python -m pytest test_strut_minimal.py -k "corner_vertices_have_direct_truss_leg_connection or large_brace_edge_truss or perimeter_truss" -v
```

Expected: PASS; rectangular convex-corner assemblies retain direct waling-corner connectivity and panel length limits.

- [ ] **Step 7: Commit the perimeter topology change**

```powershell
git add -- strut_engine.py test_strut_minimal.py
git commit -m "fix(#2): connect L-shaped perimeter truss at concave node"
```

### Task 4: Add validation red lines for non-convex excavations

**Files:**
- Modify: `strut_validation.py`
- Modify: `test_strut_minimal.py`

- [ ] **Step 1: Write a failing validation mutation test**

```python
def test_validation_rejects_main_strut_overlapping_excavation_boundary() -> None:
    case = next(case for case in CASES if case.name == "l_shape")
    layout = solve_case(case)
    layout["members"].append({
        "id": "M_BAD_EDGE",
        "kind": "main_strut",
        "system": "brace",
        "start": "N_BAD_1",
        "end": "N_BAD_2",
        "geometry": [(30.0, 20.0), (30.0, 40.0)],
        "width": 0.8,
        "material": "steel",
    })

    report = validate_layout(layout, {**case.params, "excavation_coords": case.coords})
    assert not report["ok"]
    assert any(issue["reason"] == "member_overlaps_excavation_boundary" for issue in report["issues"])
```

- [ ] **Step 2: Add the validator**

Add a `validate_excavation_boundary_clearance()` function before `validate_layout()`:

```python
def validate_excavation_boundary_clearance(
    layout: dict[str, Any],
    params: dict[str, Any] | None,
) -> list[ValidationIssue]:
    if not params or not params.get("excavation_coords"):
        return []
    boundary = Polygon(params["excavation_coords"]).boundary
    issues = []
    for ref in collect_segments(layout):
        if ref.kind != "main_strut":
            continue
        overlap = ref.line.intersection(boundary)
        if overlap.length > 1e-6:
            point = ref.line.interpolate(0.5, normalized=True)
            issues.append(ValidationIssue(
                ref.kind,
                ref.member_id,
                None,
                (float(point.x), float(point.y)),
                "member_overlaps_excavation_boundary",
                "error",
            ))
    return issues
```

Call it from `validate_layout()` before general intersection checks. Pass the excavation coordinates through `_attach_validation()` without adding a public default parameter:

```python
validation_params = dict(self.params)
validation_params["excavation_coords"] = list(self.coords)
report = validate_layout(layout, validation_params)
```

- [ ] **Step 3: Add conversion-node validation assertions**

Add this focused validator before `validate_layout()`:

```python
def validate_conversion_endpoints(layout: dict[str, Any]) -> list[ValidationIssue]:
    nodes = [tuple(node["pos"]) for node in layout.get("nodes", [])]
    issues = []
    for member in layout.get("members", []):
        if not member.get("conversion_group"):
            continue
        for endpoint in (member["geometry"][0], member["geometry"][-1]):
            if any(points_close(endpoint, node) for node in nodes):
                continue
            issues.append(ValidationIssue(
                member["kind"],
                member.get("id"),
                None,
                tuple(endpoint),
                "conversion_endpoint_unregistered",
                "error",
            ))
    return issues
```

Call `validate_conversion_endpoints(layout)` from `validate_layout()` immediately after `validate_member_endpoint_anchors()`. Add this mutation test:

```python
def test_validation_rejects_unregistered_conversion_endpoint() -> None:
    case = next(case for case in CASES if case.name == "l_shape")
    layout = solve_case(case)
    conversion = next(
        member for member in layout["members"]
        if member.get("conversion_group") == "reentrant_1"
    )
    missing = conversion["geometry"][-1]
    layout["nodes"] = [
        node for node in layout["nodes"]
        if Point(node["pos"]).distance(Point(missing)) > 1e-6
    ]

    report = validate_layout(layout, {**case.params, "excavation_coords": case.coords})
    assert not report["ok"]
    assert any(issue["reason"] == "conversion_endpoint_unregistered" for issue in report["issues"])
```

- [ ] **Step 4: Run validation tests**

Run:

```powershell
python -m pytest test_strut_minimal.py -k "validation_rejects_main_strut or conversion_endpoint or l_shape" -v
```

Expected: PASS; the real layout is clean and both corrupted layouts fail with explicit error codes.

- [ ] **Step 5: Commit validation red lines**

```powershell
git add -- strut_validation.py strut_engine.py test_strut_minimal.py
git commit -m "test(#2): reject excavation-edge and conversion-node defects"
```

### Task 5: Add engineering evidence, run all gates, and update Issue #2

**Files:**
- Modify: `run_engineering_strut_checks.py`
- Modify: `docs/issues/INDEX.md` by generator
- Generate: `engineering_check_outputs/l_shape_brace_60x40.png`
- Generate: `engineering_check_outputs/l_shape_brace_60x40.dxf`

- [ ] **Step 1: Add the L-shaped engineering case**

Add to `CASES`:

```python
Case(
    "l_shape_brace_60x40",
    [(0, 0), (60, 0), (60, 20), (30, 20), (30, 40), (0, 40)],
    {
        "support_system": "brace",
        "spacing": 9.0,
        "waling_offset": 2.0,
        "safe_dist": 1.5,
    },
),
```

- [ ] **Step 2: Add hard engineering checks**

Call `_check_l_shape_support()` when `case.name == "l_shape_brace_60x40"`:

```python
def _check_l_shape_support(case: Case, layout: dict[str, Any]) -> int:
    excavation_boundary = Polygon(case.coords).boundary
    main = [member for member in layout["members"] if member["kind"] == "main_strut"]
    conversion = [member for member in layout["members"] if member.get("conversion_group")]
    failures = _check(bool(main), "L-shaped pit has visible opposite struts")
    failures += _check(
        all(LineString(member["geometry"]).intersection(excavation_boundary).length <= 1e-6 for member in main),
        "L-shaped main struts do not overlap excavation edges",
    )
    failures += _check(
        {member.get("conversion_group") for member in conversion} == {"reentrant_1"},
        "L-shaped pit has exactly one concave conversion group",
    )
    failures += _check(
        not any(member["kind"] == "corner" and LineString(member["geometry"]).distance(Point(30, 20)) <= 2.0 for member in layout["members"]),
        "re-entrant vertex has no convex-corner brace",
    )
    return failures
```

- [ ] **Step 3: Run the focused engineering case and inspect artifacts**

Run the full script because it has no single-case CLI:

```powershell
$env:PYTHONUTF8 = "1"
$env:TMP = "$PWD\.tmp_runtime"
$env:TEMP = "$PWD\.tmp_runtime"
$env:MPLCONFIGDIR = "$PWD\.mplconfig"
python run_engineering_strut_checks.py
```

Expected final line: `PASSED: all engineering checks passed`.

Open `engineering_check_outputs/l_shape_brace_60x40.png` and verify all of the following before continuing:

- six boundary segments have continuous waling/outer chord coverage;
- the long and short arms have distinct compact support fields;
- no member lies on `x=30, y=20..40` or `y=20, x=30..60`;
- the re-entrant conversion group contains one shared inner node and no dense fan;
- pillars occur only at visible structural intersections.

- [ ] **Step 4: Run all repository gates**

```powershell
python -m pytest test_strut_minimal.py -v
python test_issue_management.py
python run_engineering_strut_checks.py
python -m ruff check strut_engine.py strut_validation.py test_strut_minimal.py run_engineering_strut_checks.py
```

Expected: all pytest and Issue-management tests pass, engineering checks print `PASSED`, and Ruff prints `All checks passed!`.

- [ ] **Step 5: Commit engineering coverage**

```powershell
git add -- run_engineering_strut_checks.py
git add -- engineering_check_outputs/l_shape_brace_60x40.png engineering_check_outputs/l_shape_brace_60x40.dxf
git commit -m "test(#2): add L-shaped engineering verification"
```

If generated engineering artifacts are ignored by repository policy, omit the second `git add` and attach the files to the Issue comment instead.

- [ ] **Step 6: Post verification evidence without closing Issue #2**

Create a temporary comment body under `.tmp_runtime/issue-2-verification.md` containing commit ids, exact test outputs, and the PNG/DXF artifact paths. Then run:

```powershell
gh issue comment 2 --repo momoheal/foundation-pit-support-layout-engine --body-file .tmp_runtime/issue-2-verification.md
python tools/sync_issue_index.py
python test_issue_management.py
```

Expected: Issue #2 remains open with regression and artifact evidence; `docs/issues/INDEX.md` is regenerated from GitHub and Issue-management tests pass.

- [ ] **Step 7: Commit the generated Issue index only**

```powershell
git add -- docs/issues/INDEX.md
git commit -m "docs(#2): record L-shaped verification evidence"
```

- [ ] **Step 8: Push for user visual approval**

```powershell
git push origin codex/issue-1-edge-truss-corner-topology
```

Do not close Issue #2 until the user has inspected the regenerated L-shaped PNG/DXF and explicitly approved the geometry.
