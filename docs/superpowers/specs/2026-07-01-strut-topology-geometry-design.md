# Strut Topology Geometry Design

## Confirmed Engineering Decisions

- Edge truss uses option C: the waling line is the edge-truss outer chord.
- The edge truss adds an inner chord offset by `truss_depth` and triangular web members between the waling chord and inner chord.
- Large foundation pits should use trussed corner brace bands instead of only single-line corner braces.
- Single-line corner braces and trussed corner braces should not be stacked in the same large-pit corner area.
- Pillars are selected from topology candidates; they are not generated at every truss panel node.

## Geometry Rules

- `straight_truss` first generates waling, then edge truss, main struts, internal truss bands, coupling ties, structural cross nodes, and filtered pillars.
- Edge truss outer chord is coincident with waling. This prevents a visually detached edge truss and matches drawings where the perimeter beam acts as the outside chord.
- Large `brace` layouts generate local corner truss bands near each corner. Smaller brace layouts keep the existing single-line corner struts.
- Structural crossings created by intentional truss/main-strut/tie connections are written into `nodes` and then recognized by validation.

## Pillar Rules

- `pillar_min_spacing` defaults to `spacing_min`.
- Pillar candidates are scored by node type. Main strut crosses are preferred, followed by ring/radial nodes and tie-related nodes.
- Ordinary truss panel nodes do not automatically become pillars.
- Candidate points are greedily selected with minimum spacing to avoid dense pillar clusters.

## Verification Targets

- `large_rect_120x80_straight_truss` verifies the waling-as-outer-chord rule and sparse pillars.
- `large_rect_120x80_brace` verifies large-pit corner truss bands.
- Existing small and irregular cases continue to validate geometry, statistics, and DXF layers.
