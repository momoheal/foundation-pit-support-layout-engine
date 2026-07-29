# PENDING-GITHUB: P0 engineering - visually connected members form disconnected graph

Status: Open / Unverified

Reproduction: solve `large_rect_120x80_brace` and count member-node graph
components. The current result has isolated tie components even where the
geometry visibly crosses main struts.

Expected: every intended joint shares one node id, intersected members are split
at the joint, and every structural member is reachable from the waling.

Regression tests:

- `test_p0_intended_intersections_are_planarized`
- `test_p0_structural_graph_is_waling_reachable`

Evidence: graph component report plus refreshed large-brace PNG/DXF.
