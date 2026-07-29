# PENDING-GITHUB: P0 engineering - edge-truss chords and corner linkage use rejected topology

Status: Open / Unverified

GitHub status: `gh auth status` failed on 2026-07-29 because no GitHub host is
authenticated. This draft must be migrated to GitHub before closure.

Related prior draft: `P0-corner-brace-load-path.md`. That draft covers the
earlier long-leg defect. This Issue records the distinct regression introduced
by replacing it with a continuous perimeter band; it does not mark the prior
Issue fixed.

Priority: P0

Work type: engineering

## Reproduction

```text
python run_engineering_strut_checks.py
```

Case: `large_brace_corner_truss_120x80`

Rejected evidence:
`engineering_check_outputs/large_brace_corner_truss_120x80.png`

## Expected structural behavior

- The excavation edge lies on the pit-interior side of the waling centerline
  by the retaining-pile radius (`waling_offset`).
- That offset direction is global across support systems because waling
  generation is shared; branch-specific sign conventions are forbidden.
- The edge-truss outer chord is the waling itself, not a coincident second
  member.
- Four straight edge trusses remain discrete; they do not become a chamfered
  closed perimeter band.
- Adjacent inner chords cross at a shared node and continue to the opposite
  adjacent waling edges. Their continuation segments belong to the corner
  assembly.
- Tier 1 is one shared brace/web member.
- Tier 2 connects the `2d` waling anchors and passes through the inner-chord
  common node.
- Tier 3 connects the `3d` waling anchors and crosses both inner chords. Its
  perpendicular webs connect those crossing nodes to the corresponding tier-2
  waling anchors.
- Corner assemblies contain no duplicate geometry, small intersection cluster,
  or unclassified close nearly parallel members.

## Actual structural behavior

`_place_large_brace_perimeter_truss()` generates edge and corner panels as one
connected double-chord band. The output forms an octagonal belt, creates an
outer `truss_chord` separate from the waling, terminates edge-truss chords at
setback chamfers, and lacks the approved modular multi-tier corner linkage.

## Affected modules

- `strut_engine.py`
- `strut_validation.py`
- `test_strut_minimal.py`
- `run_engineering_strut_checks.py`
- `strut_diagnostics.py` if boundary labels or layer presentation require
  correction

## Engineering risk and root-cause hypothesis

The rejected geometry does not describe discrete constructible edge trusses or
a traceable corner load path. Coincident waling/chord members double-count
physical steel, while chamfered chords and generic panel webs obscure which
nodes transfer corner forces.

The root cause is the continuous-band abstraction shared by
`_place_large_brace_perimeter_truss()`, `_truss_panel_member_specs()`, and
`_large_brace_corner_anchor_model()`. Panel-size tuning cannot repair the
member-identity and topology errors.

## Acceptance criteria

The following tests must fail against commit `97d9310` for the intended reason
before production geometry is edited:

- `test_p0_waling_is_outside_excavation_edge_by_pile_radius`
- `test_p0_edge_truss_outer_chord_reuses_waling_member`
- `test_p0_edge_trusses_are_discrete_straight_systems`
- `test_p0_inner_chords_cross_then_reach_opposite_waling`
- `test_p0_corner_tier_one_is_the_first_web_once`
- `test_p0_corner_tier_two_passes_inner_chord_common_node`
- `test_p0_corner_tier_three_webs_reach_tier_two_waling_anchors`
- `test_p0_corner_zone_has_no_dense_duplicate_or_close_parallel_members`

The Issue remains Open / Unverified until all tests pass, engineering checks
pass, the affected PNG and DXF files are regenerated, and the refreshed PNGs
are explicitly reviewed against both real references.

## Acceptance commands

```text
python -m pytest test_strut_minimal.py test_issue_management.py -v
python run_engineering_strut_checks.py
```

## DXF and PNG evidence paths

- `engineering_check_outputs/large_brace_corner_truss_120x80.png`
- `engineering_check_outputs/large_brace_corner_truss_120x80.dxf`
- `engineering_check_outputs/straight_truss_60x40.png`
- `engineering_check_outputs/straight_truss_60x40.dxf`

Approved design:
`docs/superpowers/specs/2026-07-29-edge-truss-corner-brace-topology-design.md`
