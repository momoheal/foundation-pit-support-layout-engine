# Foundation Pit Support Layout Engine

Geometry automation for generating internal bracing layouts for foundation pit
excavations. The engine turns a 2D pit boundary polygon and engineering
parameters into waling beams, main struts, ties, truss chords and webs, corner
braces, circular ring/radial supports, pillar candidates, DXF output, and
diagnostic PNG previews.

This project is aimed at geotechnical and structural CAD workflows. Its output
is intended to be inspectable by engineers and usable as the basis for support
layout review, not just as a generic geometry demo.

## What It Does

- Generates perimeter waling inside a pit boundary.
- Supports orthogonal struts, corner braces, straight truss systems, and
  circular core support systems.
- Builds a graph-style node/member model alongside legacy output buckets.
- Produces DXF files with support members on typed CAD layers.
- Exports diagnostic PNG previews for engineering review.
- Runs pytest checks and representative engineering plausibility checks.

## Repository Structure

| Path | Purpose |
| --- | --- |
| `strut_engine.py` | Core `StrutEngine` layout generator. |
| `strut_validation.py` | Layout validation and engineering sanity checks. |
| `main_strut.py` | DXF export for support layouts. |
| `strut_diagnostics.py` | Diagnostic PNG rendering. |
| `test_strut_minimal.py` | Minimal pytest-compatible regression suite. |
| `run_engineering_strut_checks.py` | Representative engineering check runner. |
| `docs/` | Requirements, design notes, improvement plans, and task history. |
| `engineering_check_outputs/` | Generated DXF/PNG check artifacts. |

## Installation

Python 3.10+ is recommended.

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

## Usage

Run the regression suite:

```bash
python -m pytest test_strut_minimal.py -v
```

Run the engineering plausibility checks and regenerate diagnostics:

```bash
python run_engineering_strut_checks.py
```

Use the engine from Python:

```python
from strut_engine import StrutEngine

coords = [(0, 0), (60, 0), (60, 40), (0, 40)]
params = {
    "support_system": "orthogonal",
    "spacing": 9.0,
    "waling_offset": 1.0,
}

layout = StrutEngine(coords, params).solve()
print(layout["stats"])
print(layout["issues"])
```

## Versioning

The project uses semantic versioning. See `VERSION` for the current version and
`CHANGELOG.md` for release notes.

## Development Notes

Before considering changes to `strut_engine.py` complete, run both:

```bash
python -m pytest test_strut_minimal.py -v
python run_engineering_strut_checks.py
```

Generated layouts should also be visually reviewed from the PNG files in
`engineering_check_outputs/` because geometric output can pass numeric checks
while still looking unsuitable for engineering drawings.
