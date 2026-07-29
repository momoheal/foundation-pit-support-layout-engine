# PENDING-GITHUB: P0 regression - acceptance tests encode rejected geometry

Status: Open / Unverified

Reproduction: inspect tests that require corner-vertex direct connection and
tests named as requiring diagonal lacing while asserting that lacing is absent.

Expected: test names, assertions, engineering-check messages and the current
authority specification all express the same structural contract.

Acceptance: the rejected assertions are removed, replacement red-line tests fail
against the old implementation, and the full suite passes only after the engine
meets the new contract.
