# PENDING-GITHUB: P0 engineering - incorrect corner-brace load path

Status: Open / Unverified

Reproduction: `python run_engineering_strut_checks.py`

Case: `large_brace_corner_truss_120x80`

Actual: diagonal corner truss legs start at true waling vertices and terminate
at main-strut midspans.

Expected: each corner assembly uses two setback anchors on adjacent waling
edges, local triangular lattice members, and shared structural nodes. No member
endpoint may use the true corner or an unsplit main-strut midspan.

Regression tests:

- `test_p0_corner_assemblies_use_setback_waling_anchors`
- `test_p0_corner_lattice_does_not_overlap_edge_web_zone`
- `test_p0_corner_lattice_members_are_mutually_connected`

Evidence: `engineering_check_outputs/large_brace_corner_truss_120x80.{png,dxf}`
