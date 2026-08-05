# GitHub Issue Index

> GENERATED FILE. Do not edit by hand.
> Synchronized at 2026-08-05T01:51:17Z.

## Open

| Issue | Priority | Type | Title | Owner | Modules | Acceptance commands |
| --- | --- | --- | --- | --- | --- | --- |
| [#2](https://github.com/momoheal/foundation-pit-support-layout-engine/issues/2) | P0 | engineering | [Engineering] L-shaped pit places main struts on excavation edges | Unassigned | - `strut_engine.py`<br>- `strut_validation.py`<br>- `test_strut_minimal.py`<br>- `run_engineering_strut_checks.py` | ```text<br>python -m pytest test_strut_minimal.py -q<br>python run_engineering_strut_checks.py<br>python test_issue_management.py<br>python -m ruff check strut_engine.py strut_validation.py test_strut_minimal.py run_engineering_strut_checks.py<br>``` |
| [#1](https://github.com/momoheal/foundation-pit-support-layout-engine/issues/1) | P0 | engineering | [Engineering] Edge-truss chords and corner linkage use rejected topology | Unassigned | - `strut_engine.py`<br>- `strut_validation.py`<br>- `test_strut_minimal.py`<br>- `run_engineering_strut_checks.py`<br>- `strut_diagnostics.py` if boundary labels or layer presentation require<br>correction | ```text<br>python -m pytest test_strut_minimal.py test_issue_management.py -v<br>python run_engineering_strut_checks.py<br>``` |

## In Progress

| Issue | Priority | Type | Title | Owner | Modules | Acceptance commands |
| --- | --- | --- | --- | --- | --- | --- |
| - | - | - | None | - | - | - |

## Blocked

| Issue | Priority | Type | Title | Owner | Modules | Acceptance commands |
| --- | --- | --- | --- | --- | --- | --- |
| - | - | - | None | - | - | - |

## Closed

| Issue | Priority | Type | Title | Owner | Modules | Acceptance commands |
| --- | --- | --- | --- | --- | --- | --- |
| - | - | - | None | - | - | - |
