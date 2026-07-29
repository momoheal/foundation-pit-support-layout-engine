# PENDING-GITHUB: P0 engineering - validator accepts disconnected or unanchored layouts

Status: Open / Unverified

Reproduction: construct broken member fixtures and call
`validate_layout(layout, params)`.

Expected: hard errors cover member bounds, endpoint anchors, disconnected graph
components, waling reachability and representative-case topology red lines.

Regression tests:

- `test_validator_rejects_unanchored_member_endpoint`
- `test_validator_rejects_disconnected_structural_component`
- `test_validator_rejects_member_outside_waling`
