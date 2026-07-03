"""Engineering geometry checks for internal strut layouts.

Run from the project root:
    python run_engineering_strut_checks.py

The script prints numeric checks and exports DXF files to
``engineering_check_outputs/`` for manual inspection.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import atan2, degrees
from pathlib import Path
from typing import Any

from shapely.geometry import LineString, Point, Polygon

from main_strut import export_strut_dxf
from strut_diagnostics import export_strut_diagnostic_png
from strut_engine import StrutEngine
from strut_validation import validate_layout


@dataclass(frozen=True)
class Case:
    name: str
    coords: list[tuple[float, float]]
    params: dict[str, Any]


CASES = [
    Case(
        "opposite_strut_60x40",
        [(0, 0), (60, 0), (60, 40), (0, 40)],
        {
            "support_system": "opposite_strut",
            "spacing": 9.0,
            "spacing_min": 6.0,
            "spacing_max": 9.0,
            "waling_offset": 5.0,
            "safe_dist": 2.5,
            "truss_depth": 0.8,
            "truss_panel_min": 6.0,
            "truss_panel_max": 9.0,
        },
    ),
    Case(
        "large_opposite_strut_120x80",
        [(0, 0), (120, 0), (120, 80), (0, 80)],
        {
            "support_system": "opposite_strut",
            "spacing": 12.0,
            "spacing_min": 8.0,
            "spacing_max": 14.0,
            "waling_offset": 5.0,
            "safe_dist": 2.5,
            "truss_depth": 1.2,
            "truss_panel_min": 8.0,
            "truss_panel_max": 12.0,
        },
    ),
    Case(
        "large_brace_corner_truss_120x80",
        [(0, 0), (120, 0), (120, 80), (0, 80)],
        {
            "support_system": "brace",
            "spacing": 12.0,
            "spacing_min": 8.0,
            "spacing_max": 14.0,
            "waling_offset": 5.0,
            "safe_dist": 2.5,
            "truss_depth": 1.2,
            "truss_panel_min": 8.0,
            "truss_panel_max": 12.0,
        },
    ),
    Case(
        "octagon_circular_core",
        [(10, 0), (50, 0), (60, 10), (60, 30), (50, 40), (10, 40), (0, 30), (0, 10)],
        {
            "support_system": "circular",
            "spacing": 8.0,
            "waling_offset": 2.0,
            "safe_dist": 1.5,
            "core_center": (30.0, 20.0),
            "core_diameter": 8.0,
            "core_clearance": 2.0,
            "ring_edge_clearance": 5.0,
        },
    ),
]


def main() -> int:
    output_dir = Path("engineering_check_outputs")
    output_dir.mkdir(exist_ok=True)

    failed = 0
    for case in CASES:
        print(f"\n=== {case.name} ===")
        engine = StrutEngine(case.coords, case.params)
        layout = engine.solve()
        report = validate_layout(layout, engine.params)
        dxf_path = output_dir / f"{case.name}.dxf"
        png_path = output_dir / f"{case.name}.png"
        export_strut_dxf(dxf_path, case.coords, layout)
        export_strut_diagnostic_png(png_path, case.coords, layout, title=case.name)

        failed += _print_summary_and_check(case, layout, report, dxf_path, png_path)

    print("\n=== Result ===")
    if failed:
        print(f"FAILED: {failed} check(s) failed")
        return 1
    print("PASSED: all engineering checks passed")
    return 0


def _print_summary_and_check(
    case: Case,
    layout: dict[str, Any],
    report: dict[str, Any],
    dxf_path: Path,
    png_path: Path,
) -> int:
    failures = 0
    members = layout["members"]
    counts = Counter(member["kind"] for member in members)
    stats = layout["stats"]

    print(f"DXF: {dxf_path}")
    print(f"PNG: {png_path}")
    print(f"members: {dict(sorted(counts.items()))}")
    print(
        "stats: "
        f"main={stats['main_strut_length']:.2f}, "
        f"corner={stats['corner_length']:.2f}, "
        f"web={stats['truss_web_length']:.2f}, "
        f"tie={stats['tie_length']:.2f}, "
        f"ring={stats['ring_strut_length']:.2f}, "
        f"radial={stats['radial_strut_length']:.2f}, "
        f"pillars={stats['pillar_count']}"
    )

    failures += _check(report["ok"], f"geometry validation OK; issues={report['issues'][:5]}")

    if case.params["support_system"] == "opposite_strut":
        failures += _check_opposite_strut(case, layout)
        failures += _check_grouped_coupling_ties(case, layout)
        failures += _check_required_pillars(case, layout)

    if case.name.startswith("large_brace"):
        failures += _check_edge_truss(case, layout)
        failures += _check_large_corner_truss(case, layout)

    if case.params["support_system"] == "circular":
        failures += _check(stats["ring_strut_length"] > 0, "circular support has ring strut length")
        failures += _check(stats["radial_strut_length"] > 0, "circular support has radial strut length")

    return failures


def _check_opposite_strut(case: Case, layout: dict[str, Any]) -> int:
    counts = Counter(member["kind"] for member in layout["members"])
    failures = _check(counts["corner"] == 0, "opposite strut has no corner braces")
    failures += _check(counts["truss_chord"] == 0, "opposite strut has no edge truss chords")
    failures += _check(counts["truss_web"] == 0, "opposite strut has no edge truss webs")
    main = [member for member in layout["members"] if member["kind"] == "main_strut"]
    vertical = [member for member in main if _is_vertical(member)]
    horizontal = [member for member in main if _is_horizontal(member)]
    failures += _check(len(vertical) >= 3, f"opposite strut has distributed vertical struts; actual={len(vertical)}")
    failures += _check(len(horizontal) >= 3, f"opposite strut has distributed horizontal struts; actual={len(horizontal)}")
    min_required_spacing = min(10.0, float(case.params["spacing_min"]))
    failures += _check(
        _minimum_axis_spacing(vertical, "x") >= min_required_spacing,
        "vertical opposite strut spacing is not too close",
    )
    failures += _check(
        _minimum_axis_spacing(horizontal, "y") >= min_required_spacing,
        "horizontal opposite strut spacing is not too close",
    )
    return failures


def _check_edge_truss(case: Case, layout: dict[str, Any]) -> int:
    waling_line = LineString(layout["waling"])
    outer_chord_length = sum(
        LineString(member["geometry"]).length
        for member in layout["members"]
        if member["kind"] == "truss_chord"
        and waling_line.distance(LineString(member["geometry"]).interpolate(0.5, normalized=True)) < 1e-6
    )
    coverage = outer_chord_length / waling_line.length if waling_line.length else 0.0
    print(f"edge truss outer chord coverage: {coverage:.3f}")
    failures = _check(coverage >= 0.98, "edge truss uses waling as outer chord")

    web_count = sum(1 for member in layout["members"] if member["kind"] == "truss_web")
    min_web_count = 24
    failures += _check(web_count >= min_web_count, f"truss web count >= {min_web_count}; actual={web_count}")
    shallow_web_count = sum(
        1
        for member in layout["members"]
        if member["kind"] == "truss_web"
        and waling_line.distance(LineString(member["geometry"]).interpolate(0.5, normalized=True)) <= 4.0
        and _acute_axis_angle(member) < 25.0
    )
    failures += _check(shallow_web_count == 0, f"edge truss has no shallow ineffective webs; actual={shallow_web_count}")

    waling_poly = Polygon(layout["waling"])
    min_x, min_y, max_x, max_y = waling_poly.bounds
    failures += _check(_edge_has_main_group_centers(layout, min_y, axis="x"), "bottom edge reuses main-strut group centers")
    failures += _check(_edge_has_main_group_centers(layout, max_y, axis="x"), "top edge reuses main-strut group centers")
    failures += _check(_edge_has_main_group_centers(layout, min_x, axis="y"), "left edge reuses main-strut group centers")
    failures += _check(_edge_has_main_group_centers(layout, max_x, axis="y"), "right edge reuses main-strut group centers")
    return failures


def _check_large_corner_truss(case: Case, layout: dict[str, Any]) -> int:
    waling = Polygon(layout["waling"])
    corner_zones = [Point(point).buffer(30.0) for point in list(waling.exterior.coords)[:-1]]
    failures = 0
    for index, corner in enumerate(list(waling.exterior.coords)[:-1]):
        corner_members = [
            member
            for member in layout["members"]
            if member["kind"] == "corner"
            and corner_zones[index].intersects(LineString(member["geometry"]))
        ]
        failures += _check(len(corner_members) == int(case.params.get("corner_layers", 3)), f"corner {index} has three brace layers")
        failures += _check(
            all(
                not any(Point(endpoint).distance(Point(corner)) <= 1e-6 for endpoint in member["geometry"])
                for member in corner_members
            ),
            f"corner {index} braces do not start from the pit corner",
        )
        failures += _check(
            all(35.0 <= _acute_axis_angle(member) <= 55.0 for member in corner_members),
            f"corner {index} braces are regular diagonal members",
        )
    return failures


def _check_grouped_coupling_ties(case: Case, layout: dict[str, Any]) -> int:
    ties = [member for member in layout["members"] if member["kind"] == "tie"]
    horizontal_ties = [member for member in ties if _is_horizontal(member)]
    vertical_ties = [member for member in ties if _is_vertical(member)]
    bounds = Polygon(layout["waling"]).bounds
    tie_interval = float(case.params.get("tie_interval", 14.0))
    min_required_spacing = min(10.0, float(case.params["spacing_min"]))
    expected_horizontal = max(2, int((bounds[3] - bounds[1]) / tie_interval) - 1)
    expected_vertical = max(2, int((bounds[2] - bounds[0]) / tie_interval) - 1)
    failures = _check(
        len(horizontal_ties) >= expected_horizontal,
        f"horizontal paired-strut ties present; actual={len(horizontal_ties)}, expected>={expected_horizontal}",
    )
    failures += _check(
        len(vertical_ties) >= expected_vertical,
        f"vertical paired-strut ties present; actual={len(vertical_ties)}, expected>={expected_vertical}",
    )
    failures += _check(
        all(min_required_spacing <= LineString(member["geometry"]).length <= float(case.params["spacing_max"]) + 1.0 for member in ties),
        "ties connect adjacent opposite struts without dense spacing",
    )
    return failures


def _check_required_pillars(case: Case, layout: dict[str, Any]) -> int:
    required_points = _main_and_tie_intersection_points(layout)
    pillar_points = [Point(point) for point in layout["pillars"]]
    print(f"pillars: count={len(pillar_points)}, required_main_tie_or_main_cross={len(required_points)}")
    return _check(
        all(any(Point(point).distance(pillar) <= 0.1 for pillar in pillar_points) for point in required_points),
        "all main-strut/tie and main-strut cross nodes have pillars",
    )


def _edge_has_main_group_centers(layout: dict[str, Any], edge_value: float, *, axis: str) -> bool:
    value_index = 1 if axis == "x" else 0
    axis_index = 0 if axis == "x" else 1
    main_values = sorted({
        round(point[axis_index], 6)
        for member in layout["members"]
        if member["kind"] == "main_strut"
        for point in member["geometry"]
        if abs(point[value_index] - edge_value) <= 1e-6
    })
    if not main_values:
        return True
    groups = _axis_groups(main_values, max_pair_gap=8.0)
    centers = {round(sum(group) / len(group), 6) for group in groups}
    truss_values = {
        round(point[axis_index], 6)
        for member in layout["members"]
        if member["kind"] in {"truss_chord", "truss_web"}
        for point in (member["geometry"][0], member["geometry"][-1])
        if abs(point[value_index] - edge_value) <= 1e-6
    }
    return centers <= truss_values


def _main_and_tie_intersection_points(layout: dict[str, Any]) -> list[tuple[float, float]]:
    structural = [
        member
        for member in layout["members"]
        if member["kind"] in {"main_strut", "tie"}
    ]
    points: list[tuple[float, float]] = []
    for index, left in enumerate(structural):
        left_line = LineString(left["geometry"])
        for right in structural[index + 1:]:
            if left["kind"] == right["kind"] == "tie":
                continue
            inter = left_line.intersection(LineString(right["geometry"]))
            if inter.geom_type != "Point":
                continue
            point = (float(inter.x), float(inter.y))
            if not any(Point(point).distance(Point(existing)) <= 1e-6 for existing in points):
                points.append(point)
    return points


def _is_vertical(member: dict[str, Any]) -> bool:
    start, end = member["geometry"][0], member["geometry"][-1]
    return abs(start[0] - end[0]) < 1e-6 and abs(start[1] - end[1]) > 1e-6


def _is_horizontal(member: dict[str, Any]) -> bool:
    start, end = member["geometry"][0], member["geometry"][-1]
    return abs(start[1] - end[1]) < 1e-6 and abs(start[0] - end[0]) > 1e-6


def _axis_groups(values: list[float], max_pair_gap: float) -> list[list[float]]:
    groups: list[list[float]] = []
    for value in values:
        if groups and value - groups[-1][-1] <= max_pair_gap:
            groups[-1].append(value)
        else:
            groups.append([value])
    return groups


def _minimum_axis_spacing(members: list[dict[str, Any]], axis: str) -> float:
    if len(members) < 2:
        return float("inf")
    index = 0 if axis == "x" else 1
    values = sorted({round(member["geometry"][0][index], 6) for member in members})
    if len(values) < 2:
        return float("inf")
    return min(right - left for left, right in zip(values, values[1:]))


def _acute_axis_angle(member: dict[str, Any]) -> float:
    start, end = member["geometry"][0], member["geometry"][-1]
    dx = abs(end[0] - start[0])
    dy = abs(end[1] - start[1])
    angle = abs(degrees(atan2(dy, dx)))
    return min(angle, 180.0 - angle)


def _check(condition: bool, message: str) -> int:
    marker = "OK" if condition else "FAIL"
    print(f"[{marker}] {message}")
    return 0 if condition else 1


if __name__ == "__main__":
    raise SystemExit(main())
