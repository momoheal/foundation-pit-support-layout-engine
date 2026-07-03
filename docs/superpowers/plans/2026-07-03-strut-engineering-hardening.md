# Strut Engineering Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the current foundation-pit internal strut generator engineering-usable by tightening the existing sample outputs, validation, and diagnostics without adding broad new features.

**Architecture:** `StrutEngine` remains the source of generated geometry and the node/member model. `strut_validation.py` validates that model, `main_strut.py` exports it to DXF layers, and `strut_diagnostics.py` exports a PNG for visual inspection. Legacy layout buckets stay as compatibility outputs only.

**Tech Stack:** Python, shapely, ezdxf, matplotlib, pytest, mypy, ruff.

---

## Agent Lanes

- Requirements agent: confirms scope, acceptance criteria, and any ambiguity against the user and docs.
- Code agent: edits only implementation and focused tests needed to make current samples engineering-usable.
- Verification agent: runs baseline and final checks, inspects outputs, and reports failures with exact commands and evidence.

## File Map

- Modify: `strut_engine.py` for parameter normalization, member generation, node snapping, pillars, and stats.
- Modify: `strut_validation.py` for strict validation behavior aligned to intentional nodes.
- Modify: `main_strut.py` only if DXF layer output no longer matches member kinds.
- Modify: `strut_diagnostics.py` only if the sample image needs clearer engineering inspection.
- Modify: `test_strut_minimal.py` for regression assertions around current samples.
- Modify: `docs/improve-progress.md` for current improvement progress.
- Reference: `docs/superpowers/specs/2026-07-02-strut-engineering-hardening-design.md`.

## Task 1: Requirements Gate

**Files:**
- Read: `docs/superpowers/specs/2026-07-02-strut-engineering-hardening-design.md`
- Read: `docs/improve-prompt.md`
- Read: `docs/improve-progress.md`
- Read: `docs/high-level-design.md`
- Output: a short checklist in the agent final answer

- [ ] **Step 1: Extract acceptance criteria**

Create a checklist with these exact headings:

```text
Must preserve
Must improve
Must not do
Verification commands
Open questions for user
```

- [ ] **Step 2: Confirm no scope creep**

Ensure the checklist explicitly says:

```text
No new support systems.
No broad UI rewrite.
No loose validation to hide geometry errors.
Current sample outputs are the priority.
```

- [ ] **Step 3: Return requirements verdict**

Return a final answer that states whether implementation can proceed without additional user input. If anything blocks implementation, name the exact blocking question.

## Task 2: Code Hardening

**Files:**
- Modify: `strut_engine.py`
- Modify: `strut_validation.py`
- Modify: `test_strut_minimal.py`
- Optional modify: `main_strut.py`
- Optional modify: `strut_diagnostics.py`

- [ ] **Step 1: Run focused baseline**

Run:

```bash
python -m pytest test_strut_minimal.py -q
python test_strut_minimal.py
```

Expected: either pass or reveal current sample weaknesses. Record the output.

- [ ] **Step 2: Inspect generated sample layouts**

Use `StrutEngine` directly to inspect at least:

```python
from test_strut_minimal import CASES, solve_case

for name in ("rect_60x40", "straight_truss_rect", "large_rect_120x80_straight_truss", "large_rect_120x80_brace"):
    case = next(c for c in CASES if c.name == name)
    layout = solve_case(case)
    print(name, len(layout["members"]), len(layout["nodes"]), len(layout["pillars"]), layout["stats"], layout["issues"][:3])
```

- [ ] **Step 3: Add or adjust regression assertions before implementation**

Add focused tests in `test_strut_minimal.py` only for current engineering usability. Prefer assertions like:

```python
assert report["ok"], (case.name, report["issues"])
assert layout["members"]
assert layout["stats"]["total_support_length"] > 0
assert len(layout["pillars"]) <= len(layout["nodes"])
```

For sample image readiness, keep:

```python
assert png_path.exists()
assert png_path.stat().st_size > 10_000
```

- [ ] **Step 4: Implement minimal corrections**

Make the smallest changes needed so the current samples produce legal, coherent member models. Follow these rules:

```text
Do not add new support systems.
Do not make validation looser to pass tests.
Do not move core algorithm logic into Tkinter.
Do not output members that are outside the waling/support polygon.
Do not create pillars from every truss node.
```

- [ ] **Step 5: Run focused checks**

Run:

```bash
python -m pytest test_strut_minimal.py -q
python test_strut_minimal.py
```

Expected: both pass.

- [ ] **Step 6: Return code change summary**

Return:

```text
Changed files
Root cause fixed
Tests added or changed
Commands run and results
Risks or follow-ups
```

## Task 3: Verification and Output

**Files:**
- Read: `test_strut_minimal.py`
- Read: `strut_diagnostics.py`
- Create output image under: `engineering_check_outputs/`
- Modify: `docs/improve-progress.md` only after verification evidence exists

- [ ] **Step 1: Run full verification**

Run:

```bash
python -m pytest
python test_strut_minimal.py
python -m mypy .
python -m ruff check .
```

Expected: all pass. If any fail, report exact command and first useful failure.

- [ ] **Step 2: Generate sample diagnostic image**

Run a Python snippet equivalent to:

```python
from pathlib import Path
from test_strut_minimal import CASES, solve_case
from strut_diagnostics import export_strut_diagnostic_png

case = next(c for c in CASES if c.name == "large_rect_120x80_straight_truss")
layout = solve_case(case)
path = Path("engineering_check_outputs/large_rect_120x80_straight_truss.png")
export_strut_diagnostic_png(path, case.coords, layout, title=case.name)
print(path, path.exists(), path.stat().st_size)
```

Expected: PNG exists and is larger than 10 KB.

- [ ] **Step 3: Inspect output evidence**

Report:

```text
PNG path
File size
Case name
Member count
Node count
Pillar count
Validation issue count
```

- [ ] **Step 4: Update progress**

Only after verification, update `docs/improve-progress.md` to reflect the current pass. Do not mark the whole project complete unless all commands pass.

## Main Agent Integration

- [ ] Review requirements agent checklist.
- [ ] Review code agent changed files and patch.
- [ ] Review verification agent command output.
- [ ] Re-run any failed or suspect command locally.
- [ ] Produce final user summary with sample image path and remaining risks.
