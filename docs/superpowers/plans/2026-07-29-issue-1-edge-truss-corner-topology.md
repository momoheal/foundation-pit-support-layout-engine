# Issue #1 Edge-Truss and Corner-Brace Topology Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the rejected continuous perimeter band with four discrete edge trusses and modular corner assemblies whose outer chord is the waling and whose three-tier brace/web topology matches the approved real references.

**Architecture:** Keep `solve_brace()` and `solve_straight_truss()` as orchestrators. Add one shared waling-polygon helper, one discrete edge-truss generator, and one modular corner-assembly generator; let the existing planarization pass split every structural crossing into shared graph nodes. Enforce the member-identity and tier formulas in tests, validation, and engineering checks before accepting regenerated PNG/DXF evidence.

**Tech Stack:** Python 3.10+, Shapely, pytest, ezdxf, Matplotlib, Ruff, Mypy, GitHub CLI.

---

## File Map

- Modify `strut_engine.py`: outward waling geometry, outer-chord role reuse, discrete edge panels, modular corner tiers, and orchestration.
- Modify `test_strut_minimal.py`: remove assertions that require the rejected perimeter band and add the Issue #1 RED/GREEN topology tests.
- Modify `strut_validation.py`: reject duplicated waling/chords, closed chamfer bands, invalid tier anchors, and corner clutter.
- Modify `run_engineering_strut_checks.py`: assert the approved topology and regenerate the two affected engineering cases.
- Modify `strut_diagnostics.py` only if needed to distinguish excavation edge from outward waling clearly in PNG output.
- Modify `docs/issues/INDEX.md`: generated remote Issue index after migration and verification comments.
- Delete `docs/issues/pending/P0-edge-truss-chord-and-corner-linkage.md`: remove the authenticated draft after Issue #1 exists.
- Create `docs/superpowers/plans/2026-07-29-issue-1-edge-truss-corner-topology.md`: this execution plan.

### Task 1: Migrate the P0 Draft and Lock the Execution Branch

**Files:**
- Delete: `docs/issues/pending/P0-edge-truss-chord-and-corner-linkage.md`
- Modify: `docs/issues/INDEX.md`
- Create: `docs/superpowers/plans/2026-07-29-issue-1-edge-truss-corner-topology.md`

- [x] **Step 1: Verify authentication and search for duplicate Issues**

Run:

```text
gh auth status
gh issue list --repo momoheal/foundation-pit-support-layout-engine --state all --search "edge truss corner linkage perimeter band"
```

Expected: authenticated as `momoheal`; no duplicate Issue.

- [x] **Step 2: Create required labels and Issue #1**

Run:

```text
gh label create engineering --repo momoheal/foundation-pit-support-layout-engine --color B60205 --description "Engineering plausibility or structural geometry defect"
gh label create P0 --repo momoheal/foundation-pit-support-layout-engine --color D93F0B --description "Engineering-critical priority"
gh issue create --repo momoheal/foundation-pit-support-layout-engine --title "[Engineering] Edge-truss chords and corner linkage use rejected topology" --label engineering --label P0 --body-file docs/issues/pending/P0-edge-truss-chord-and-corner-linkage.md
```

Expected: `https://github.com/momoheal/foundation-pit-support-layout-engine/issues/1`.

- [x] **Step 3: Create the Issue branch**

Run:

```text
git switch -c codex/issue-1-edge-truss-corner-topology
```

Expected: current branch is `codex/issue-1-edge-truss-corner-topology`; unrelated dirty files remain untouched.

- [ ] **Step 4: Remove the pending draft and refresh the generated index**

Run:

```text
python tools/sync_issue_index.py
python -m pytest test_issue_management.py -v
```

Expected: Issue #1 appears in `docs/issues/INDEX.md`; all three Issue-management tests pass.

- [ ] **Step 5: Commit only Issue migration and plan files**

```text
git add docs/issues/INDEX.md docs/issues/pending/P0-edge-truss-chord-and-corner-linkage.md docs/superpowers/plans/2026-07-29-issue-1-edge-truss-corner-topology.md
git commit -m "chore(#1): migrate edge-truss P0 issue"
```

### Task 2: Make the Waling Offset Direction an Explicit Global Contract

**Files:**
- Modify: `test_strut_minimal.py`
- Modify: `strut_engine.py`

- [ ] **Step 1: Add the failing boundary-direction regression test**

Add this test near the existing waling tests:

```python
def test_p0_waling_is_outside_excavation_edge_by_pile_radius() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    excavation = Polygon(case.coords)
    waling = Polygon(layout["waling"])

    assert waling.contains(excavation)
    assert waling.exterior.distance(excavation.exterior) == pytest.approx(
        case.params["waling_offset"],
        abs=1e-6,
    )
```

- [ ] **Step 2: Run the test and record RED**

Run:

```text
python -m pytest test_strut_minimal.py::test_p0_waling_is_outside_excavation_edge_by_pile_radius -v
```

Expected: FAIL because the current waling uses `self.poly.buffer(-waling_offset)` and lies inside the excavation edge.

- [ ] **Step 3: Add a dedicated waling helper and use it everywhere waling geometry is required**

Implement in the low-level helper section:

```python
def _waling_poly(self) -> Polygon:
    offset = float(self.params["waling_offset"])
    result = self.poly.buffer(offset, join_style="mitre")
    if isinstance(result, MultiPolygon):
        result = max(result.geoms, key=lambda geom: geom.area)
    if not isinstance(result, Polygon) or result.is_empty:
        return self.poly
    return result
```

Change `_place_waling()` to call `self._waling_poly()`. Keep `_offset_poly()` for callers that explicitly need an inward polygon; do not reverse its established generic meaning.

- [ ] **Step 4: Run boundary and representative non-truss tests**

Run:

```text
python -m pytest test_strut_minimal.py::test_p0_waling_is_outside_excavation_edge_by_pile_radius test_strut_minimal.py::test_layout_contract_all_systems -v
```

Expected: PASS. Any exact-offset assertions that encoded inward waling must be updated to the approved global contract, not weakened.

- [ ] **Step 5: Commit the boundary contract**

```text
git add strut_engine.py test_strut_minimal.py
git commit -m "fix(#1): place waling outside excavation edge"
```

### Task 3: Replace Rejected Band Assertions with Issue #1 RED Tests

**Files:**
- Modify: `test_strut_minimal.py`

- [ ] **Step 1: Remove or rewrite tests that require duplicated outer chords, setback chamfers, or the closed perimeter band**

Rewrite the current tests named `test_edge_truss_uses_waling_as_outer_chord`,
`test_edge_and_corner_trusses_handoff_at_setback_nodes`,
`test_corner_leg_uses_shared_truss_primitive`,
`test_corner_lattice_tiles_between_setback_anchors`,
`test_separate_corner_tier_fan_is_removed`, and
`test_large_brace_perimeter_truss_wraps_all_four_edges`. Do not preserve any
assertion requiring a coincident outer `truss_chord` or `corner_role == "leg"`.

- [ ] **Step 2: Add member-identity and discrete-edge failing tests**

```python
def test_p0_edge_truss_outer_chord_reuses_waling_member() -> None:
    layout = solve_case(next(case for case in CASES if case.name == "large_rect_120x80_brace"))
    waling = next(member for member in layout["members"] if member["kind"] == "waling")
    waling_line = LineString(waling["geometry"])
    duplicates = [
        member for member in layout["members"]
        if member["kind"] == "truss_chord"
        and waling_line.buffer(1e-6).covers(LineString(member["geometry"]))
    ]

    assert "edge_truss_outer_chord" in waling.get("structural_roles", [])
    assert duplicates == []


def test_p0_edge_trusses_are_discrete_straight_systems() -> None:
    layout = solve_case(next(case for case in CASES if case.name == "large_rect_120x80_brace"))
    edge_ids = {
        member["edge_truss_id"] for member in layout["members"]
        if member.get("edge_truss_id")
    }
    assert edge_ids == {"edge_truss_1", "edge_truss_2", "edge_truss_3", "edge_truss_4"}
    for edge_id in edge_ids:
        inner = [
            member for member in layout["members"]
            if member.get("edge_truss_id") == edge_id
            and member.get("edge_role") == "inner_chord"
        ]
        assert inner
        assert len({_segment_angle_180(member) for member in inner}) == 1
```

- [ ] **Step 3: Add inner-chord and tier-formula failing tests**

Add helpers that group split members by logical geometry and assembly, then add
the four named tests from the design:

```python
def _issue1_logical_lines(
    layout: dict[str, Any],
    *,
    role: str | None = None,
    edge_role: str | None = None,
    assembly_id: str | None = None,
) -> list[LineString]:
    lines: dict[str, LineString] = {}
    for member in layout["members"]:
        if role is not None and member.get("corner_role") != role:
            continue
        if edge_role is not None and member.get("edge_role") != edge_role:
            continue
        if assembly_id is not None and member.get("belongs_to_corner_bracket") != assembly_id:
            continue
        logical_id = str(member.get("parent_member_id", member["id"]))
        geometry = member.get("logical_geometry", member["geometry"])
        lines[logical_id] = LineString(geometry)
    return list(lines.values())


def test_p0_inner_chords_cross_then_reach_opposite_waling() -> None:
    layout = solve_case(next(case for case in CASES if case.name == "large_rect_120x80_brace"))
    waling = LineString(layout["waling"])
    chords = _issue1_logical_lines(layout, edge_role="inner_chord")
    crossings = [
        left.intersection(right)
        for index, left in enumerate(chords)
        for right in chords[index + 1:]
        if left.intersection(right).geom_type == "Point"
    ]

    assert len(chords) == 4
    assert all(waling.distance(Point(line.coords[0])) <= 1e-6 for line in chords)
    assert all(waling.distance(Point(line.coords[-1])) <= 1e-6 for line in chords)
    assert len(crossings) == 4


def test_p0_corner_tier_one_is_the_first_web_once() -> None:
    layout = solve_case(next(case for case in CASES if case.name == "large_rect_120x80_brace"))
    for assembly_id in _corner_assembly_ids(layout):
        tier_one = _issue1_logical_lines(layout, role="tier_1", assembly_id=assembly_id)
        assert len(tier_one) == 1


def test_p0_corner_tier_two_passes_inner_chord_common_node() -> None:
    layout = solve_case(next(case for case in CASES if case.name == "large_rect_120x80_brace"))
    for assembly_id in _corner_assembly_ids(layout):
        tier_two = _issue1_logical_lines(layout, role="tier_2", assembly_id=assembly_id)
        inner = _issue1_logical_lines(layout, edge_role="inner_chord")
        common = [
            left.intersection(right)
            for index, left in enumerate(inner)
            for right in inner[index + 1:]
            if left.intersection(right).geom_type == "Point"
            and any(
                member.get("belongs_to_corner_bracket") == assembly_id
                and LineString(member.get("logical_geometry", member["geometry"])).distance(left.intersection(right)) <= 1e-6
                for member in layout["members"]
            )
        ]
        assert len(tier_two) == 1
        assert len(common) == 1
        assert tier_two[0].distance(common[0]) <= 1e-6


def test_p0_corner_tier_three_webs_reach_tier_two_waling_anchors() -> None:
    layout = solve_case(next(case for case in CASES if case.name == "large_rect_120x80_brace"))
    waling = LineString(layout["waling"])
    for assembly_id in _corner_assembly_ids(layout):
        tier_two = _issue1_logical_lines(layout, role="tier_2", assembly_id=assembly_id)[0]
        tier_three = _issue1_logical_lines(layout, role="tier_3", assembly_id=assembly_id)[0]
        webs = _issue1_logical_lines(
            layout,
            role="tier_3_perpendicular_web",
            assembly_id=assembly_id,
        )
        tier_two_anchors = [Point(point) for point in (tier_two.coords[0], tier_two.coords[-1])]
        crossings = [
            tier_three.intersection(chord)
            for chord in _issue1_logical_lines(layout, edge_role="inner_chord")
            if tier_three.intersection(chord).geom_type == "Point"
        ]
        assert len(webs) == 2
        assert all(
            any(web.distance(point) <= 1e-6 for point in tier_two_anchors)
            and any(web.distance(point) <= 1e-6 for point in crossings)
            and any(waling.distance(Point(endpoint)) <= 1e-6 for endpoint in (web.coords[0], web.coords[-1]))
            for web in webs
        )
```

Each test must assert real geometry and shared node ids, not only attribute
presence. For tier 3, assert that both perpendicular webs connect a
`tier_3`/inner-chord crossing to the matching tier-2 waling anchor and are
perpendicular to that waling edge.

- [ ] **Step 4: Add the corner-clutter failing test**

```python
def test_p0_corner_zone_has_no_dense_duplicate_or_close_parallel_members() -> None:
    layout = solve_case(next(case for case in CASES if case.name == "large_rect_120x80_brace"))
    for assembly_id in _corner_assembly_ids(layout):
        members = _logical_corner_members(layout, assembly_id)
        assert _duplicate_segments(members) == []
        assert _unclassified_close_parallel_pairs(members, clearance=3.0) == []
        assert _minimum_corner_joint_spacing(members) >= 3.0
```

- [ ] **Step 5: Run all eight Issue #1 tests and record RED output**

Run:

```text
python -m pytest test_strut_minimal.py -k "p0_waling or p0_edge_truss or p0_inner_chords or p0_corner_tier or p0_corner_zone" -v
```

Expected: the boundary test passes after Task 2; the remaining tests fail for missing roles, duplicated chords, or wrong corner topology.

- [ ] **Step 6: Commit only the RED tests**

```text
git add test_strut_minimal.py
git commit -m "test(#1): lock edge-truss corner topology red lines"
```

### Task 4: Generate Discrete Edge Trusses and Shared Outer-Chord Roles

**Files:**
- Modify: `strut_engine.py`
- Test: `test_strut_minimal.py`

- [ ] **Step 1: Tag the waling as the physical outer chord**

Pass this attribute from `_place_waling()` into `_add_member()`:

```python
attributes={"structural_roles": ["waling", "edge_truss_outer_chord"]}
```

- [ ] **Step 2: Replace `_place_large_brace_perimeter_truss()` with a discrete-edge helper**

Implement a helper with this interface:

```python
def _place_discrete_edge_trusses(
    self,
    layout: dict[str, Any],
    waling_poly: Polygon,
) -> dict[str, Any]:
    """Build one inner chord and ordinary web panels per straight waling edge."""
```

For each waling edge, calculate one inward normal, offset the complete edge by
`d`, extend the inner chord to both adjacent waling edges, add it once as a
logical `truss_chord`, and panelize only the middle portion not owned by corner
tiers. Ordinary webs get `edge_truss_id`, `edge_role = "web"`, and
`truss_primitive = "panel"`. Do not emit an outer `truss_chord`.

- [ ] **Step 3: Return a corner model based on true waling vertices**

The helper return value must contain, for each convex orthogonal corner:

```python
{
    "assembly_id": f"corner_bracket_{index + 1}",
    "corner": corner,
    "edge_dirs": (prev_direction, next_direction),
    "inner_common": inner_common,
    "inner_chord_ids": (prev_inner_id, next_inner_id),
}
```

- [ ] **Step 4: Use the helper from both orchestration methods**

Replace calls to `_large_brace_corner_anchor_model()` and
`_place_large_brace_perimeter_truss()` in `solve_brace()` and
`solve_straight_truss()` with `_place_discrete_edge_trusses()`. Keep stiffening,
ties, planarization, and pillars in their current relative order.

- [ ] **Step 5: Run the two edge-truss tests GREEN**

```text
python -m pytest test_strut_minimal.py::test_p0_edge_truss_outer_chord_reuses_waling_member test_strut_minimal.py::test_p0_edge_trusses_are_discrete_straight_systems -v
```

Expected: PASS.

- [ ] **Step 6: Commit discrete edge trusses**

```text
git add strut_engine.py test_strut_minimal.py
git commit -m "fix(#1): generate discrete edge trusses"
```

### Task 5: Generate the Modular Corner Tiers and Perpendicular Webs

**Files:**
- Modify: `strut_engine.py`
- Test: `test_strut_minimal.py`

- [ ] **Step 1: Normalize and consume the existing tier parameters**

Keep `corner_truss_tier_count` as an integer of at least one. Use
`corner_truss_tier_spacing` when supplied; otherwise use `_edge_truss_depth()`.
Do not leave either parameter declared but unused.

- [ ] **Step 2: Implement modular corner member placement**

```python
def _place_modular_corner_assemblies(
    self,
    layout: dict[str, Any],
    waling_poly: Polygon,
    corner_model: dict[str, Any],
) -> None:
    """Place C_k waling-to-waling tiers and their recurrence webs."""
```

For every corner and tier `k`, compute `A_k = V + k*d*e1` and
`B_k = V + k*d*e2`. Add `C_k = [A_k, B_k]` as `truss_web` with
`corner_role = f"tier_{k}"`. Tier 1 is generated once and replaces the first
ordinary edge-panel web. Tier 2 must contain `Q`. For every `k >= 3`, intersect
`C_k` with both inner chords and connect those points to `A_(k-1)` and
`B_(k-1)` as `corner_role = f"tier_{k}_perpendicular_web"`.

- [ ] **Step 3: Bound tier count without compressing spacing**

Compute the largest legal `k` from both adjacent edge lengths and the required
end clearance. Use `min(requested_count, legal_count)`. For
`large_brace_corner_truss_120x80`, assert `legal_count >= 3`; never reduce `d`
to force the requested count.

- [ ] **Step 4: Planarize the tier/inner-chord intersections**

Call the existing `_planarize_structural_members()` after the complete edge
and corner topology exists. Confirm that split segments retain
`belongs_to_corner_bracket`, `corner_role`, `logical_geometry`, and
`parent_member_id`.

- [ ] **Step 5: Run the inner-chord and corner-tier tests GREEN**

```text
python -m pytest test_strut_minimal.py -k "p0_inner_chords or p0_corner_tier" -v
```

Expected: all four tests pass.

- [ ] **Step 6: Run and fix the clutter test without weakening its thresholds**

```text
python -m pytest test_strut_minimal.py::test_p0_corner_zone_has_no_dense_duplicate_or_close_parallel_members -v
```

Expected: PASS with no duplicate logical geometry, no unclassified close
parallel pairs, and no important-node spacing below 3 m.

- [ ] **Step 7: Commit modular corner assemblies**

```text
git add strut_engine.py test_strut_minimal.py
git commit -m "fix(#1): add modular corner brace tiers"
```

### Task 6: Add Validator and Engineering-Check Red Lines

**Files:**
- Modify: `strut_validation.py`
- Modify: `run_engineering_strut_checks.py`
- Modify: `test_strut_minimal.py`

- [ ] **Step 1: Add validator tests using deliberately invalid layouts**

Create focused fixtures for a duplicated waling/chord, a tier-2 member that
misses `Q`, and a tier-3 recurrence web that ends at an arbitrary waling point.
Assert issue reasons beginning with:

```text
edge_truss_outer_chord_duplicates_waling
corner_tier_2_misses_inner_common
corner_tier_web_misses_previous_waling_anchor
corner_member_clutter
```

- [ ] **Step 2: Run validator tests RED**

```text
python -m pytest test_strut_minimal.py -k "validation_reports_edge_truss or validation_reports_corner_tier" -v
```

Expected: FAIL because the reasons do not exist yet.

- [ ] **Step 3: Implement validation from member geometry and roles**

Add independent validation helpers that inspect real coordinates and shared
nodes. Attributes select the assembly but never substitute for geometric
proof. Append errors to `issues`; do not suppress generation defects.

- [ ] **Step 4: Replace engineering checks that require perimeter-band coverage**

In `run_engineering_strut_checks.py`, remove checks for duplicated outer
`truss_chord` coverage and add the same member-identity, four-edge, tier, and
clutter assertions used by the regression tests. Run them for both
`large_brace_corner_truss_120x80` and `straight_truss_60x40`.

- [ ] **Step 5: Run validator tests and Issue #1 tests GREEN**

```text
python -m pytest test_strut_minimal.py -k "p0_ or validation_reports_edge_truss or validation_reports_corner_tier" -v
```

Expected: PASS.

- [ ] **Step 6: Commit validation red lines**

```text
git add strut_validation.py run_engineering_strut_checks.py test_strut_minimal.py
git commit -m "test(#1): enforce corner topology validation"
```

### Task 7: Regenerate Evidence, Inspect Visually, and Publish

**Files:**
- Modify: `engineering_check_outputs/large_brace_corner_truss_120x80.png`
- Modify: `engineering_check_outputs/large_brace_corner_truss_120x80.dxf`
- Modify: `engineering_check_outputs/straight_truss_60x40.png`
- Modify: `engineering_check_outputs/straight_truss_60x40.dxf`
- Modify: `docs/issues/INDEX.md`

- [ ] **Step 1: Run the full required test suite**

Set Windows runtime directories under the repository, then run:

```text
$env:TMP='D:\codexprojects\ezdxf\.tmp_runtime'
$env:TEMP='D:\codexprojects\ezdxf\.tmp_runtime'
$env:MPLCONFIGDIR='D:\codexprojects\ezdxf\.mplconfig'
python -m pytest test_strut_minimal.py test_issue_management.py -v
```

Expected: zero failures.

- [ ] **Step 2: Run engineering checks and regenerate evidence**

```text
python run_engineering_strut_checks.py
```

Expected: `PASSED: all engineering checks passed` and refreshed PNG/DXF files.

- [ ] **Step 3: Run static checks**

```text
python -m mypy strut_engine.py strut_validation.py strut_diagnostics.py main_strut.py run_engineering_strut_checks.py
python -m ruff check strut_engine.py strut_validation.py strut_diagnostics.py main_strut.py test_strut_minimal.py run_engineering_strut_checks.py
```

Expected: both commands exit 0.

- [ ] **Step 4: Inspect both PNGs against both real references**

Verify visually:

- excavation edge is inside the waling by `waling_offset`;
- no separate outer chord overlays the waling;
- four edge trusses remain straight and discrete;
- inner chords cross and continue to the opposite waling;
- tier 1 is one member, tier 2 passes `Q`, tier 3 crosses both inner chords;
- tier-3 recurrence webs end at tier-2 waling anchors;
- no small dense crossing cluster or unexplained near-parallel line exists.

- [ ] **Step 5: Commit generated evidence and final implementation**

```text
git add strut_engine.py strut_validation.py strut_diagnostics.py test_strut_minimal.py run_engineering_strut_checks.py engineering_check_outputs/large_brace_corner_truss_120x80.png engineering_check_outputs/large_brace_corner_truss_120x80.dxf engineering_check_outputs/straight_truss_60x40.png engineering_check_outputs/straight_truss_60x40.dxf
git commit -m "fix(#1): complete edge-truss corner topology"
```

- [ ] **Step 6: Post verification evidence to Issue #1 without closing it before user visual approval**

```text
$commit = git rev-parse --short HEAD
gh issue comment 1 --repo momoheal/foundation-pit-support-layout-engine --body "Verification for $commit: pytest test_strut_minimal.py + test_issue_management.py passed; engineering checks passed; mypy and ruff passed. Refreshed large_brace_corner_truss_120x80 and straight_truss_60x40 PNG/DXF under engineering_check_outputs. Status remains open pending user visual approval."
python tools/sync_issue_index.py
```

- [ ] **Step 7: Push the Issue branch**

```text
git push -u origin codex/issue-1-edge-truss-corner-topology
```

Expected: remote branch updated; Issue #1 remains open until the user accepts the supplied PNG.
