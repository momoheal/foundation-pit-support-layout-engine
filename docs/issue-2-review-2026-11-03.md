# Issue #2: corrected acceptance contract

The user rejected commit 4932b1d; d60d115 reverted it. Its passing tests and
previous Issue comment do not establish acceptance. Issue #2 stays OPEN.

## Scope

Correct the orthogonal L-shaped brace case, retaining the approved corner
tiers, continuous inner chords and reentrant transfer axes. Other support
systems and rectangular layouts retain their existing algorithm.

1. Reserve corner transfer axes and inner chords before ordinary paired struts.
2. Place ordinary struts in explicit two-member groups on visible opposing
   walings. Use the existing edge-truss depth as group spacing, matching the
   corner pair. Leave an interval empty when a complete pair cannot fit between
   corner coverage and reserved axes; never fill it with a singleton.
3. Generate edge webs after supports. Each complete web has one end on waling
   and one on its inner chord. A support/chord crossing is a mandatory inner
   anchor. Webs terminate there, rather than crossing the support and relying
   on later planarization to make the drawing appear connected.
4. Preserve triangulation across the entire middle edge field. A main strut
   relabeled as a web is not an eight-brace, and deleting adjacent bays is not
   a repair. An eight-brace consists of two diagonal waling-to-node rods.
5. Verify complete logical rods as well as the final split graph. Check web
   coverage, pair membership, common spacing, anchorage, overlaps, angles and
   overview/detail images. Passing numerical tests alone is insufficient.
6. The user chose one corner tier where a paired strut and the second tier
   leave a near-parallel web on a short boundary. Keep multiple tiers at other
   corners where they fit; update the adjacent web-field limits accordingly.
7. Draw the reentrant load-bearing inner chords in the same colour as the
   corresponding main struts while retaining the `truss_chord` physical type
   and the DXF chord layer. Ordinary inner chords retain the chord style.

Distances are in the existing model units (metres in this case); coordinate
tolerance is 1e-5 for geometry assertions. Existing 30–100 degree web-apex
limits remain regression constraints, not newly claimed engineering standards.
Pair placement is a geometric proposal, not a structural capacity calculation.
For the named short-edge regression, a 20-degree minimum angle to the main
strut is a geometric clutter guard; it is not a design-code requirement.

## Outstanding findings

The L-shaped sample retains two spacing warnings, 14.75 and 12.75 m. The
existing warning compares main-strut axes without crediting a load-bearing
inner chord, so the 14.75 m figure is not the clear distance to every support.
Do not silence either warning or treat the proposed open bays as a verified
structural design without engineering review.

At baseline d60d115, `test_structural_red_lines.py` already has two failing
rectangular corner tests: `test_p0_corner_assemblies_use_setback_waling_anchors`
and `test_p0_corner_lattice_does_not_overlap_edge_web_zone`. These failures are
independent of the L-shaped change and remain open under Issue #1.
