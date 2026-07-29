# Foundation Pit Support Geometry Constraints

This document defines the geometry contract for `StrutEngine` outputs and for
`strut_validation.py`. It is the reference for deciding whether a generated
layout is geometrically invalid, engineering-suspicious, or merely different
from the preferred drawing style.

The goal is to stop spreading validation rules across generation code,
pytest helpers, engineering-check helpers, and visual review notes. New
geometry checks should be added here first, then implemented in
`strut_validation.py`, then reused by `test_strut_minimal.py` and
`run_engineering_strut_checks.py`.

## Severity Levels

### Error

An error means the layout is not a valid support layout. `validate_layout()`
must return `ok=False`.

Use errors for geometry that would produce an impossible, dangling, or unsafe
load path:

- A support member lies outside the waling polygon, except for documented
  rendering outlines.
- A member endpoint is not anchored to waling, an existing node, a pillar, a
  ring, or another accepted structural anchor.
- Two members intersect at a non-endpoint location without an explicit shared
  node, unless the pair is listed as an allowed crossing.
- A member intrudes into the circular core protection zone.
- A required support-system topology is missing, for example a `circular`
  layout without a ring strut.
- A member kind appears in `members` but is not part of the supported member
  vocabulary.

### Warning

A warning means the layout can still be exported, but should be treated as
engineering-suspicious. `validate_layout()` may return `ok=True` while
reporting warnings.

Use warnings for geometry that may be acceptable in small or constrained pits
but should be visible to the user or test harness:

- Main strut spacing is outside the recommended range.
- Waling connection spacing is uneven or exceeds the recommended range.
- Important structural nodes or pillars are too dense.
- Regular parallel members are closer than the recommended clearance.
- Perimeter truss coverage has a gap larger than the target panel length but
  below a hard project-specific failure threshold.
- A truss web angle is too shallow to work as an effective web.

### Generation Preference

A generation preference should guide algorithms and visual review, but should
not be a validation issue unless a later section promotes it to an error or
warning.

Examples:

- Prefer fewer total support length after hard constraints are satisfied.
- Prefer symmetric grids in rectangular pits.
- Prefer reusing existing truss nodes instead of adding nearby new nodes.
- Prefer Warren or K web rhythm that matches the selected support system.

## Shared Geometry Contract

These constraints apply to every `support_system`.

### Layout Envelope

- `waling` must be a closed, valid polygonal loop.
- Every linear support member must be covered by the waling polygon with a
  small tolerance, except where a member kind is explicitly defined as an
  external reference or outline.
- `outlines` are drawing artifacts; validation should check the member
  centerline and structural intent, not fail because a buffered outline
  slightly crosses a boundary.

Recommended validator:

- `validate_member_bounds(layout, params) -> list[ValidationIssue]`

### Anchors And Nodes

Every member endpoint must land on a real structural anchor:

- waling boundary point;
- node in `layout["nodes"]`;
- endpoint or interior point of another member with an explicit node;
- ring point for radial struts;
- pillar point when the member is explicitly supported by a pillar.

Bare computed points, such as a centroid-to-edge radial that does not connect
to another member or ring, are invalid.

Recommended validator:

- `validate_member_endpoint_anchors(layout, params)`

### Legal Intersections

The default rule is strict: member intersections are legal only at endpoints or
at explicit shared nodes.

Allowed crossings:

- `main_strut` with `main_strut`, if the intersection is recorded as a
  `strut_cross` node.
- `ring_strut` with `radial_strut`, if the intersection is recorded as a
  `ring_radial` node.
- `truss_chord` with `truss_web`, if the intersection is a truss endpoint or
  an explicit `truss_node`.

The validator may keep a small whitelist for legacy behavior, but a whitelist
must not hide non-node intersections that should be modeled as real nodes.

Current implementation:

- `find_illegal_intersections()`
- `has_explicit_connection_node()`

Required improvement:

- Allowed crossing rules should check explicit nodes wherever the crossing is
  intended to be structural, not only the member-kind pair.

### Member Vocabulary

Supported member kinds are:

- `waling`
- `main_strut`
- `corner`
- `haunch`
- `tie`
- `truss_chord`
- `truss_web`
- `ring_strut`
- `radial_strut`

Adding a kind requires updates to:

- `STATS_KEYS` aggregation in `strut_engine.py`;
- `_outline_layer(kind)`;
- DXF output layer mapping;
- validation vocabulary;
- at least one test or engineering-check case.

Recommended validator:

- `validate_member_kinds(layout, params)`

### Spacing And Density

Spacing checks are engineering warnings unless a support-system section below
defines a hard failure for a representative case.

Recommended defaults:

- Main strut and waling connection target: `spacing`, with preferred bounds
  `spacing_min` to `spacing_max`.
- Important structural node minimum spacing: normally `spacing_min`, with
  current large-brace checks using `6.0m`.
- Regular parallel member minimum clearance: `3.0m` hard visual/engineering
  floor, with `6.0m` preferred where possible.
- Pillar minimum spacing: `pillar_min_spacing` or `spacing_min`.

Recommended validators:

- `validate_connection_spacing(layout, params)`
- `validate_structural_node_density(layout, params)`
- `validate_parallel_member_clearance(layout, params)`
- `validate_pillar_spacing(layout, params)`

## Support-System Topology

### `orthogonal`

Expected:

- closed `waling`;
- orthogonal `main_strut` members clipped to the waling polygon;
- `tie` members connecting adjacent main struts where needed;
- `pillar` points at important main-strut intersections.

Allowed:

- simple `corner` braces when enabled by the selected strategy.

Not required:

- perimeter truss;
- ring/radial system.

Errors:

- main strut endpoint is not anchored to waling or a legal node;
- main strut segment crosses outside the waling polygon;
- tie endpoint is not attached to a main strut, waling, or legal node.

### `opposite_strut`

Expected:

- distributed full-span `main_strut` members in both principal directions for
  large rectangular cases;
- `tie` members between adjacent parallel struts;
- no perimeter truss and no corner brace members by default.

Current representative checks:

- no `truss_chord`, `truss_web`, or `corner` members;
- enough vertical and horizontal main struts;
- grouped ties connect adjacent opposite struts;
- required main/tie or main/main nodes receive pillars.

Errors:

- tie connects fewer or more than two adjacent main struts;
- tie endpoint is not on the adjacent strut pair;
- ring/radial or truss members appear unless a future design explicitly
  enables a hybrid system.

Warnings:

- same-axis main strut spacing outside recommended range;
- grouped tie interval is irregular.

### `brace`

`brace` has two valid modes, depending on pit size and current requirements.

Small or ordinary brace mode:

- may generate `corner` members;
- corner endpoints must land on waling or legal nodes;
- corner members must not start directly at the waling polygon corner;
- corner members must not illegally cross main struts or ties.

Large brace with perimeter truss mode:

- current `large_brace_corner_truss_120x80` requirements use this mode;
- no separate `corner` members;
- straight edge panels stop at setback handoff nodes before each true corner;
- each corner is bridged by a local double-chord triangular lattice whose two
  exterior anchors lie on the adjacent waling edges;
- corner-lattice members never start at the true waling vertex or terminate at
  an unsplit main-strut midspan;
- edge-panel webs do not continue through the corner-lattice zone;
- the representative case has two vertical paired groups and one horizontal
  paired group, coupled by perpendicular ties at no more than the configured
  unbraced interval.

Errors:

- a large-brace perimeter-truss layout contains `corner` members;
- the perimeter truss has no chord or web near a waling corner;
- paired main-strut coupling ties have dangling endpoints;
- a diagonal member starts directly at a waling corner point.

Warnings:

- large-brace perimeter truss max gap exceeds `truss_panel_max`;
- paired tie/lacing positions are not modular;
- important structural nodes or pillars are closer than the configured limit.

### `straight_truss`

Expected:

- closed `waling`;
- continuous or segmented perimeter truss band;
- waling acts as the outer chord;
- inner chord is offset inward by `truss_depth`;
- web members form triangular panels;
- main strut endpoints and perimeter truss stations should align where they
  meet the waling.

Errors:

- no `truss_chord` or no `truss_web`;
- separate `corner` members are generated;
- truss web endpoint is not on an outer chord, inner chord, or truss node;
- truss panel extends outside waling.

Warnings:

- perimeter max gap exceeds `truss_panel_max`;
- truss web angle is too shallow;
- ordinary panel nodes are all converted into pillars.

### `circular`

Expected:

- one true circular `ring_strut`;
- `radial_strut` members connect from ring to exterior support anchors;
- core protection circle stays empty;
- radial struts do not pass through the ring interior/core protection area.

Errors:

- missing `core_center` or `core_diameter` for `support_system="circular"`;
- no ring strut;
- no radial struts;
- any non-ring member intrudes into the core protection zone;
- radial endpoint is not attached to the ring or legal exterior anchor.

Warnings:

- radial spacing outside `radial_spacing_min/max`;
- radial count is too low for the ring circumference.

## Perimeter Truss Continuity

This is the current highest-risk validation gap.

A perimeter truss system is valid only when the waling loop has adjacent truss
coverage along the full perimeter. The check should walk the closed waling
line, collect projected stations from nearby `truss_chord` and `truss_web`
members, and report the largest uncovered station interval.

For `brace` large-truss and `straight_truss`:

- maximum uncovered interval should be no greater than `truss_panel_max`;
- every waling edge should have at least one nearby outer chord segment;
- every waling corner should have nearby chord and web members;
- corner webs must connect outer chord to inner chord, not just draw two
  parallel lines.

Recommended validator:

- `validate_perimeter_truss_continuity(layout, params)`

Expected issue reasons:

- `perimeter_truss_missing`
- `perimeter_truss_gap:<length>`
- `corner_truss_chord_missing`
- `corner_truss_web_missing`
- `corner_web_not_connecting_outer_inner_chord`

## Internal Paired-Strut Lacing

For grouped full-span main struts, the pair must behave as a structural unit.

Expected:

- adjacent parallel main struts within the pair are connected by short
  perpendicular `tie` members;
- clear bays include diagonal `tie` lacing, either single alternating
  diagonals or X/diamond lacing;
- tie/lacing positions are generated from a modular spacing rule, not ad hoc
  coordinates;
- diagonal lacing angle should normally be between 20 and 70 degrees relative
  to the nearest axis.

Errors:

- lacing endpoint is not on the paired main strut or legal node;
- lacing crosses another member without a legal node.

Warnings:

- no diagonal lacing exists for a paired group;
- tie/lacing station spacing is irregular beyond tolerance;
- diagonal lacing angle is too shallow or too steep.

Recommended validator:

- `validate_paired_strut_lacing(layout, params)`

## Validation API Target

`validate_layout(layout, params)` should eventually compose these validators:

```python
validators = [
    validate_member_kinds,
    validate_member_bounds,
    validate_member_endpoint_anchors,
    validate_illegal_intersections,
    validate_core_protection,
    validate_connection_spacing,
    validate_structural_node_density,
    validate_parallel_member_clearance,
    validate_pillar_spacing,
    validate_support_system_topology,
    validate_perimeter_truss_continuity,
    validate_paired_strut_lacing,
]
```

The engineering check script should call the same validators and only add
case-specific acceptance thresholds or reporting. It should not maintain a
separate copy of core geometry rules.

## Migration Plan

1. Move pure helper checks from `test_strut_minimal.py` and
   `run_engineering_strut_checks.py` into `strut_validation.py`.
2. Keep case-specific assertions in tests, but make them inspect validation
   issue reasons rather than reimplementing geometry algorithms.
3. Add targeted broken-layout fixtures for each new validator.
4. Treat warnings as passing in general pytest layout-contract tests, but make
   representative engineering checks fail on selected warnings when they
   encode current acceptance criteria.
5. Keep visual PNG review as a final check because numeric validation can miss
   clutter, visual discontinuity, or misleading member rhythm.

## Current Known Gaps

- `strut_validation.py` does not yet validate member bounds.
- It does not yet validate endpoint anchoring.
- Perimeter truss continuity is implemented only in test and engineering
  helper code.
- Paired-strut lacing checks are implemented only in test and engineering
  helper code.
- Parallel clearance and important-node density checks are not centralized.
- Support-system topology checks are not centralized.
- Some active documents contain superseded corner-truss rules. For the current
  large-brace sample, the latest rule is: corners are part of the continuous
  perimeter truss loop, and separate `corner` members must not be generated.
