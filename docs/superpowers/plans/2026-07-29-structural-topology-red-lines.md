# Structural Topology Red Lines Implementation Plan

1. Implement the repository Issue forms, Issue Agent contract and deterministic
   GitHub-to-Markdown index synchronizer described by the approved Issue design.
2. Create four P0 engineering Issue drafts for corner load path, graph
   planarization, structural validators and contradictory tests. Keep them
   explicitly unverified until remote Issues can be created.
3. Replace contradictory acceptance assertions with named red-line tests and
   confirm that the current engine fails them.
4. Planarize intended structural intersections: split all participating linear
   members, merge colocated endpoints and rebuild legacy buckets/outlines.
5. Replace true-corner diagonal legs with waling-setback triangular corner
   assemblies and trim edge-web coverage at their handoff stations.
6. Add endpoint-anchor, graph-connectivity, waling-reachability, member-bounds,
   node-spacing and parallel-clearance validators.
7. Regenerate engineering outputs and inspect the large-brace PNG against the
   supplied references before any Issue is eligible for closure.
8. Run pytest, engineering checks, mypy and Ruff. Commit and push from the
   `codex/p0-geometry-issue-hardening` branch only after the verified set is
   known. Authentication failure is reported, never treated as success.
