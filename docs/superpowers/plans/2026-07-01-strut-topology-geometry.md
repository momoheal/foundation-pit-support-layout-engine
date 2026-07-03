# Strut Topology Geometry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make strut geometry use the waling as the edge-truss outer chord, truss large-pit corner braces, and select sparse, well-spaced pillar points.

**Architecture:** Keep the existing `StrutEngine` strategy structure, but strengthen three local responsibilities: edge truss generation, corner brace generation, and pillar candidate filtering. Validation remains in `strut_validation.py`, with tests in `test_strut_minimal.py` expressing engineering geometry and topology constraints.

**Tech Stack:** Python, Shapely, ezdxf, pytest, mypy, ruff.

---

### Task 1: Edge Truss Uses Waling As Outer Chord

**Files:**
- Modify: `D:\codexprojects\ezdxf\test_strut_minimal.py`
- Modify: `D:\codexprojects\ezdxf\strut_engine.py`

- [ ] Add a failing test asserting that straight-truss edge chord segments lie on the waling line and cover a meaningful fraction of the waling perimeter.
- [ ] Run `python -m pytest test_strut_minimal.py::test_edge_truss_uses_waling_as_outer_chord -q` and confirm it fails on current geometry.
- [ ] Update `_place_edge_truss()` so the existing waling line is the outer chord and generated members use `truss_chord`/`truss_web` topology without moving the outer chord inward.
- [ ] Re-run the targeted test.

### Task 2: Large Corner Braces Become Truss Bands

**Files:**
- Modify: `D:\codexprojects\ezdxf\test_strut_minimal.py`
- Modify: `D:\codexprojects\ezdxf\strut_engine.py`

- [ ] Add a large `brace` case and a failing test that expects truss members near the corners.
- [ ] Run the targeted test and confirm large-pit corner braces are still single-line only.
- [ ] Add `_place_corner_trusses()` and call it for large brace layouts before/alongside single corner struts.
- [ ] Keep small-pit brace behavior compatible.
- [ ] Re-run the targeted test.

### Task 3: Pillar Filtering

**Files:**
- Modify: `D:\codexprojects\ezdxf\test_strut_minimal.py`
- Modify: `D:\codexprojects\ezdxf\strut_engine.py`

- [ ] Add tests for minimum pillar spacing and reduced pillar density in large truss layouts.
- [ ] Add `pillar_min_spacing` parameter defaulting to `spacing_min`.
- [ ] Change `_place_pillars_from_nodes()` to score candidates and greedily select well-spaced pillars, preferring main strut crosses, tie endpoints in sparse zones, and ring/radial points.
- [ ] Re-run targeted tests.

### Task 4: Documentation And Full Verification

**Files:**
- Modify: `D:\codexprojects\ezdxf\docs\prompt.md`
- Modify: `D:\codexprojects\ezdxf\docs\strut_module_requirements.md`
- Modify: `D:\codexprojects\ezdxf\docs\high-level-design.md`
- Modify: `D:\codexprojects\ezdxf\docs\tasks\progress.md`

- [ ] Update docs to record the C decision: waling is the edge-truss outer chord.
- [ ] Update docs for large-pit corner truss bands and sparse pillar topology rules.
- [ ] Run `python -m pytest`.
- [ ] Run `python test_strut_minimal.py`.
- [ ] Run `python -m mypy .`.
- [ ] Run `python -m ruff check .`.
- [ ] Run `python launcher.py test`.
