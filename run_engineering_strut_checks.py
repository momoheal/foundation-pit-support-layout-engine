"""Engineering geometry checks for internal strut layouts.

Run from the project root:
    python run_engineering_strut_checks.py

The script prints numeric checks and exports DXF files to
``engineering_check_outputs/`` for manual inspection.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import atan2, ceil, degrees
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
        "straight_truss_60x40",
        [(0, 0), (60, 0), (60, 40), (0, 40)],
        {
            "support_system": "straight_truss",
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

    if case.params["support_system"] in {"brace", "straight_truss"}:
        failures += _check_corner_bracket_geometry(case, layout)
        failures += _check_main_truss_crossing_vertices(layout)
        failures += _check_pair_scoped_ties(case, layout)
        failures += _check_edge_panel_symmetry(case, layout)

    if case.params["support_system"] == "opposite_strut":
        failures += _check_opposite_strut(case, layout)
        failures += _check_grouped_coupling_ties(case, layout)
        failures += _check_required_pillars(case, layout)

    if case.params["support_system"] == "straight_truss":
        failures += _check_straight_truss(case, layout)
        failures += _check_straight_truss_pair_groups(layout)

    if case.name.startswith("large_brace"):
        failures += _check_edge_truss(case, layout)
        failures += _check_continuous_perimeter_truss(case, layout)
        failures += _check_horizontal_pair_spacing(layout)
        failures += _check_internal_tie_nodes_and_no_lacing(layout)

    if case.params["support_system"] == "circular":
        failures += _check(stats["ring_strut_length"] > 0, "circular support has ring strut length")
        failures += _check(stats["radial_strut_length"] > 0, "circular support has radial strut length")

    return failures


def _check_straight_truss(case: Case, layout: dict[str, Any]) -> int:
    waling_line = LineString(layout["waling"])
    counts = Counter(member["kind"] for member in layout["members"])
    failures = _check(counts["corner"] == 0, "straight truss has no separate corner members")
    failures += _check(counts["truss_chord"] > 0, "straight truss has perimeter chord members")
    failures += _check(counts["truss_web"] > 0, "straight truss has perimeter triangular web members")
    internal_truss = _internal_truss_members(layout)
    failures += _check(
        internal_truss == [],
        f"short-span straight truss has no internal truss cage; actual={len(internal_truss)}",
    )
    failures += _check(
        _max_perimeter_truss_gap(layout) <= float(case.params["truss_panel_max"]) + 1e-6,
        "straight truss perimeter has no coverage gap larger than truss_panel_max",
    )

    truss_endpoints = [
        point
        for member in layout["members"]
        if member["kind"] in {"truss_chord", "truss_web"}
        and waling_line.distance(LineString(member["geometry"]).interpolate(0.5, normalized=True)) <= 8.0
        for point in (member["geometry"][0], member["geometry"][-1])
    ]
    main_edge_endpoints = [
        point
        for member in layout["members"]
        if member["kind"] == "main_strut"
        for point in member["geometry"]
        if waling_line.distance(Point(point)) <= 1e-6
    ]
    failures += _check(
        bool(main_edge_endpoints)
        and all(
            any(Point(point).distance(Point(anchor)) <= 1e-6 for anchor in truss_endpoints)
            for point in main_edge_endpoints
        ),
        "straight truss perimeter nodes snap to main strut edge anchors",
    )
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
    walings = _logical_members([
        member for member in layout["members"] if member["kind"] == "waling"
    ])
    duplicate_outer_chords = [
        member for member in _logical_members(layout["members"])
        if member["kind"] == "truss_chord"
        and waling_line.buffer(1e-6).covers(LineString(member["geometry"]))
    ]
    failures = _check(
        len(walings) == 1
        and "edge_truss_outer_chord" in walings[0].get("structural_roles", [])
        and duplicate_outer_chords == [],
        "waling is the only physical edge-truss outer chord",
    )

    web_count = sum(
        1
        for member in layout["members"]
        if member["kind"] == "truss_web"
    )
    failures += _check(web_count >= 16, f"perimeter truss web count >= 16; actual={web_count}")
    standard_web_count = sum(
        1
        for member in layout["members"]
        if member["kind"] == "truss_web"
        and member.get("truss_primitive") == "panel"
        and member.get("corner_role") != "leg"
        and not member.get("stiffening_for", member.get("stiffening_at"))
        and waling_line.distance(LineString(member["geometry"]).interpolate(0.5, normalized=True)) <= 4.0
    )
    failures += _check(
        standard_web_count >= 8,
        f"edge truss uses shared standard panel webs; actual={standard_web_count}",
    )

    vertical_groups = _double_strut_groups(layout, axis="x")
    horizontal_groups = _double_strut_groups(layout, axis="y")
    failures += _check(len(vertical_groups) >= 2, f"two vertical double opposite strut groups exist; actual={len(vertical_groups)}")
    failures += _check(len(horizontal_groups) == 1, f"one horizontal double opposite strut group exists; actual={len(horizontal_groups)}")
    failures += _check(_minimum_group_spacing(vertical_groups) >= 10.0, "vertical double strut groups keep 10m spacing")
    failures += _check(_important_node_spacing(layout) >= 6.0, "important structural nodes keep 6m spacing")
    return failures


def _check_edge_panel_symmetry(case: Case, layout: dict[str, Any]) -> int:
    sequences = [
        _edge_truss_projected_panel_lengths(layout, edge_index)
        for edge_index in range(1, 5)
    ]
    opposite_edges_match = all(
        len(left) == len(right)
        and all(abs(a - b) <= 2e-6 for a, b in zip(left, right))
        for left, right in ((sequences[0], sequences[2]), (sequences[1], sequences[3]))
    )
    mirrored = all(
        sequence
        and all(abs(left - right) <= 2e-6 for left, right in zip(sequence, reversed(sequence)))
        for sequence in sequences
    )
    within_limit = all(
        max(sequence, default=float("inf")) <= float(case.params["truss_panel_max"]) + 1e-6
        for sequence in sequences
    )
    failures = _check(opposite_edges_match, "opposite edge-truss panel sequences match")
    failures += _check(mirrored, "each edge-truss panel sequence mirrors about its midpoint")
    failures += _check(within_limit, "edge-truss panels remain within truss_panel_max")
    return failures


def _check_continuous_perimeter_truss(case: Case, layout: dict[str, Any]) -> int:
    corner_members = [member for member in layout["members"] if member["kind"] == "corner"]
    failures = _check(
        len(corner_members) == 0,
        f"large brace has no separate corner members; actual={len(corner_members)}",
    )
    max_gap = _max_edge_truss_station_gap(layout)
    print(f"discrete edge-truss maximum panel station gap: {max_gap:.3f}")
    failures += _check(
        max_gap <= float(case.params["truss_panel_max"]) + 1e-6,
        "discrete edge-truss panels do not exceed truss_panel_max",
    )
    groups = {
        member["belongs_to_corner_bracket"]
        for member in layout["members"]
        if member.get("belongs_to_corner_bracket")
    }
    failures += _check(len(groups) == 4, f"four corner assemblies are tagged; actual={len(groups)}")
    for group in sorted(groups):
        roles = {
            member.get("corner_role")
            for member in layout["members"]
            if member.get("belongs_to_corner_bracket") == group
        }
        failures += _check(
            {"tier_1", "tier_2", "tier_3", "tier_3_perpendicular_web"} <= roles,
            f"{group} contains the approved three tiers and recurrence webs",
        )
    failures += _check(not _has_diagonal_lacing(layout), "paired internal strut ties are perpendicular-only by default")
    return failures


def _check_corner_bracket_geometry_legacy(case: Case, layout: dict[str, Any]) -> int:
    raise RuntimeError(
        "retired corner-vertex acceptance must not be called; use setback-anchor checks"
    )  # pragma: no cover
    engine = StrutEngine(case.coords, case.params)
    model = engine._corner_truss_anchor_model(layout, Polygon(layout["waling"]))
    members_by_id = {member["id"]: member for member in layout["members"]}
    waling = Polygon(layout["waling"])
    failures = _check(len(model["corners"]) == 4, "four diagonal corner-truss legs exist")
    failures += _check(
        model.get("bracket_diagonals", []) == [] and model.get("bracket_rungs", []) == [],
        "retired corner tier-fan geometry is absent",
    )

    for index, corner_model in enumerate(model["corners"]):
        assembly_id = corner_model["assembly_id"]
        leg_members = [
            member for member in layout["members"]
            if member.get("belongs_to_corner_bracket") == assembly_id
            and member.get("corner_role") == "leg"
        ]
        edge_members = [
            member for member in layout["members"]
            if member.get("belongs_to_corner_bracket") == assembly_id
            and member.get("corner_role") == "edge_panel"
        ]
        leg_length = LineString([
            corner_model["leg_start"],
            corner_model["leg_end"],
        ]).length
        expected_panels = max(
            1,
            int(ceil(leg_length / float(engine.params["truss_panel_max"]))),
        )
        failures += _check(
            sum(member["kind"] == "truss_chord" for member in leg_members) >= expected_panels * 2
            and sum(member["kind"] == "truss_web" for member in leg_members) >= expected_panels
            and all(member.get("truss_primitive") == "panel" for member in leg_members),
            f"corner {index} leg uses {expected_panels} shared truss panels",
        )
        failures += _check(
            bool(edge_members),
            f"corner {index} adjacent edge panels share assembly tag",
        )

        outer_node = next((
            node for node in layout["nodes"]
            if Point(node["pos"]).distance(Point(corner_model["corner"])) <= 1e-6
        ), None)
        inner_node = next((
            node for node in layout["nodes"]
            if Point(node["pos"]).distance(Point(corner_model["inner_corner"])) <= 1e-6
        ), None)
        terminal_node = next((
            node for node in layout["nodes"]
            if Point(node["pos"]).distance(Point(corner_model["leg_end"])) <= 1e-6
        ), None)
        outer_chords = [
            members_by_id[member_id]
            for member_id in (outer_node or {}).get("source", [])
            if member_id in members_by_id
            and members_by_id[member_id]["kind"] == "truss_chord"
            and waling.exterior.distance(Point((outer_node or {})["pos"])) <= 1e-6
        ] if outer_node else []
        leg_outer_chords = [
            member for member in outer_chords
            if member.get("belongs_to_corner_bracket") == assembly_id
            and member.get("corner_role") == "leg"
        ]
        inner_chords = [
            members_by_id[member_id]
            for member_id in (inner_node or {}).get("source", [])
            if member_id in members_by_id
            and members_by_id[member_id]["kind"] == "truss_chord"
            and members_by_id[member_id].get("corner_role") == "edge_panel"
        ] if inner_node else []
        failures += _check(len(outer_chords) >= 2, f"corner {index} outer chords share corner node")
        failures += _check(
            bool(leg_outer_chords),
            f"corner {index} exact waling vertex directly anchors the truss leg",
        )
        failures += _check(len(inner_chords) >= 2, f"corner {index} inner chords share corner node")
        failures += _check(
            terminal_node is not None and "corner_leg_terminal" in terminal_node["kind"],
            f"corner {index} leg terminates on registered structural node",
        )

    min_separation = float(engine.params["min_node_separation"])
    node_distances = [
        Point(left["pos"]).distance(Point(right["pos"]))
        for node_index, left in enumerate(layout["nodes"])
        for right in layout["nodes"][node_index + 1:]
    ]
    failures += _check(
        not node_distances or min(node_distances) >= min_separation - 1e-6,
        f"distinct nodes keep minimum separation {min_separation:.3f}",
    )

    waling_line = LineString(layout["waling"])
    stiffening_ok = True
    stiffening_count = 0
    for main in [member for member in layout["members"] if member["kind"] == "main_strut"]:
        for endpoint in main["geometry"]:
            if waling_line.distance(Point(endpoint)) > 1e-6:
                continue
            stiffeners = [
                member for member in layout["members"]
                if member["kind"] == "truss_web"
                and member.get("stiffening_at") == main["id"]
                and Point(member.get("stiffening_point")).distance(Point(endpoint)) <= 1e-6
            ]
            stiffening_count += len(stiffeners)
            stiffening_ok = stiffening_ok and len(stiffeners) >= 2
    failures += _check(
        stiffening_ok and stiffening_count > 0,
        f"main-strut/perimeter crossings have local triangulation; members={stiffening_count}",
    )

    return failures


def _check_corner_bracket_geometry(case: Case, layout: dict[str, Any]) -> int:
    waling = LineString(layout["waling"])
    logical = _logical_members(layout["members"])
    groups = sorted({
        str(member["belongs_to_corner_bracket"])
        for member in logical
        if member.get("belongs_to_corner_bracket")
        and str(member.get("corner_role", "")).startswith("tier_")
    })
    failures = _check(len(groups) == 4, "four corner truss assemblies exist")

    for index, group in enumerate(groups):
        members = [
            member for member in logical
            if member.get("belongs_to_corner_bracket") == group
        ]
        by_role: dict[str, list[dict[str, Any]]] = {}
        for member in members:
            by_role.setdefault(str(member.get("corner_role")), []).append(member)
        topology_ok = (
            len(by_role.get("tier_1", [])) == 1
            and len(by_role.get("tier_2", [])) == 1
            and len(by_role.get("tier_3", [])) == 1
            and len(by_role.get("tier_3_perpendicular_web", [])) == 2
            and all(member["kind"] == "truss_web" for member in members)
        )
        failures += _check(topology_ok, f"corner {index} has three tiers and two recurrence webs")
        if not topology_ok:
            continue

        tier_two = by_role["tier_2"][0]
        common = Point(tier_two["corner_inner_common"])
        failures += _check(
            LineString(tier_two["geometry"]).distance(common) <= 1e-6,
            f"corner {index} tier 2 passes the inner-chord common node",
        )
        for web in by_role["tier_3_perpendicular_web"]:
            anchor = Point(web["previous_waling_anchor"])
            failures += _check(
                LineString(web["geometry"]).distance(anchor) <= 1e-6
                and waling.distance(anchor) <= 1e-6,
                f"corner {index} recurrence web reaches the tier-2 waling anchor",
            )

    waling_line = LineString(layout["waling"])
    stiffening_ok = True
    stiffening_count = 0
    for main in [member for member in layout["members"] if member["kind"] == "main_strut"]:
        parent_id = main.get("parent_member_id", main["id"])
        for endpoint in main["geometry"]:
            if waling_line.distance(Point(endpoint)) > 1e-6:
                continue
            stiffeners = [
                member for member in layout["members"]
                if member["kind"] == "truss_web"
                and parent_id in member.get("stiffening_for", [member.get("stiffening_at")])
                and any(
                    Point(point).distance(Point(endpoint)) <= 1e-6
                    for point in member.get("stiffening_points", [member.get("stiffening_point")])
                    if point is not None
                )
            ]
            stiffening_count += len(stiffeners)
            stiffening_ok = stiffening_ok and len(stiffeners) >= 2
    failures += _check(
        stiffening_ok and stiffening_count > 0,
        f"main-strut/perimeter crossings have local triangulation; members={stiffening_count}",
    )
    return failures


def _check_main_truss_crossing_vertices(layout: dict[str, Any]) -> int:
    nodes = layout["nodes"]
    crossings = []
    valid = True
    for main in [member for member in layout["members"] if member["kind"] == "main_strut"]:
        main_line = LineString(main["geometry"])
        for truss in [
            member for member in layout["members"]
            if member["kind"] in {"truss_chord", "truss_web"}
        ]:
            intersection = main_line.intersection(LineString(truss["geometry"]))
            points = []
            if intersection.geom_type == "Point":
                points = [(float(intersection.x), float(intersection.y))]
            elif intersection.geom_type == "MultiPoint":
                points = [(float(point.x), float(point.y)) for point in intersection.geoms]
            for point in points:
                crossings.append((main["id"], truss["id"], point))
                truss_endpoint = any(
                    Point(point).distance(Point(endpoint)) <= 1e-6
                    for endpoint in (truss["geometry"][0], truss["geometry"][-1])
                )
                shared_node = any(
                    Point(node["pos"]).distance(Point(point)) <= 1e-6
                    and {main["id"], truss["id"]} <= set(node.get("source", []))
                    for node in nodes
                )
                valid = valid and truss_endpoint and shared_node
    failures = _check(bool(crossings), "main struts intersect perimeter truss members")
    failures += _check(
        valid,
        f"all main/truss crossings are split shared vertices; actual={len(crossings)}",
    )
    return failures


def _check_pair_scoped_ties(case: Case, layout: dict[str, Any]) -> int:
    main_struts = _logical_members([
        member for member in layout["members"] if member["kind"] == "main_strut"
    ])
    ties = _logical_members([
        member for member in layout["members"] if member["kind"] == "tie"
    ])
    scoped = True
    for tie in ties:
        tie_line = LineString(tie["geometry"])
        intersecting = [
            main for main in main_struts
            if not tie_line.intersection(LineString(main["geometry"])).is_empty
        ]
        endpoints_anchored = all(
            any(LineString(main["geometry"]).distance(Point(endpoint)) <= 1e-6 for main in intersecting)
            for endpoint in (tie["geometry"][0], tie["geometry"][-1])
        )
        scoped = scoped and len(intersecting) == 2 and endpoints_anchored

    clearance = float(case.params.get("min_tie_to_strut_clearance", 3.0))
    clear = all(
        distance <= 1e-6 or distance >= clearance - 1e-6
        for tie in ties
        for main in main_struts
        if _nearly_parallel(tie, main)
        for distance in [LineString(tie["geometry"]).distance(LineString(main["geometry"]))]
    )
    failures = _check(bool(ties) and scoped, f"ties are independent pair-scoped members; actual={len(ties)}")
    failures += _check(clear, f"ties keep {clearance:.3f} clearance from parallel main struts")
    return failures


def _check_straight_truss_pair_groups(layout: dict[str, Any]) -> int:
    main_struts = _logical_members([
        member for member in layout["members"] if member["kind"] == "main_strut"
    ])
    valid = True
    details: list[tuple[str, set[tuple[float, float]], set[tuple[float, float]]]] = []
    for orientation, tie_orientation, coordinate_index in (
        ("vertical", "horizontal", 0),
        ("horizontal", "vertical", 1),
    ):
        axes = sorted({
            round(member["geometry"][0][coordinate_index], 6)
            for member in main_struts
            if (_is_vertical(member) if orientation == "vertical" else _is_horizontal(member))
        })
        expected = {
            (axes[index], axes[index + 1])
            for index in range(0, len(axes) - 1, 2)
        }
        actual = {
            tuple(sorted((
                round(member["geometry"][0][coordinate_index], 6),
                round(member["geometry"][-1][coordinate_index], 6),
            )))
            for member in layout["members"]
            if member["kind"] == "tie"
            and (
                _is_horizontal(member)
                if tie_orientation == "horizontal"
                else _is_vertical(member)
            )
        }
        valid = valid and bool(expected) and actual == expected
        details.append((orientation, expected, actual))
    return _check(valid, f"straight-truss ties use non-overlapping main-strut pairs; {details}")


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
    excavation = Polygon(case.coords)
    safe_dist = float(case.params["safe_dist"])
    required_points = [
        point for point in _main_and_tie_intersection_points(layout)
        if excavation.covers(Point(point))
        and excavation.exterior.distance(Point(point)) >= safe_dist - 1e-6
    ]
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
    geometry = member.get("logical_geometry", member["geometry"])
    start, end = geometry[0], geometry[-1]
    return abs(start[0] - end[0]) < 1e-6 and abs(start[1] - end[1]) > 1e-6


def _is_horizontal(member: dict[str, Any]) -> bool:
    geometry = member.get("logical_geometry", member["geometry"])
    start, end = geometry[0], geometry[-1]
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
    values = sorted({
        round(member.get("logical_geometry", member["geometry"])[0][index], 6)
        for member in members
    })
    if len(values) < 2:
        return float("inf")
    return min(right - left for left, right in zip(values, values[1:]))


def _double_strut_groups(layout: dict[str, Any], *, axis: str) -> list[list[float]]:
    members = [
        member
        for member in layout["members"]
        if member["kind"] == "main_strut"
        and ((_is_vertical(member) and axis == "x") or (_is_horizontal(member) and axis == "y"))
        and _main_strut_reaches_opposite_waling_sides(layout, member, axis=axis)
    ]
    index = 0 if axis == "x" else 1
    values = sorted({
        round(member.get("logical_geometry", member["geometry"])[0][index], 6)
        for member in members
    })
    return [group for group in _axis_groups(values, max_pair_gap=8.0) if len(group) >= 2]


def _minimum_group_spacing(groups: list[list[float]]) -> float:
    if len(groups) < 2:
        return float("inf")
    return min(right[0] - left[-1] for left, right in zip(groups, groups[1:]))


def _check_horizontal_pair_spacing(layout: dict[str, Any]) -> int:
    failures = 0
    for left, right in _double_strut_groups(layout, axis="y"):
        positions = _pair_lateral_support_positions(layout, left, right, vertical_pair=False)
        gaps = [right_value - left_value for left_value, right_value in zip(positions, positions[1:])]
        failures += _check(len(gaps) >= 3, "horizontal pair has enough support intervals")
        if gaps:
            failures += _check(
                max(gaps) - min(gaps) <= 4.0,
                f"horizontal pair support spacing is uniform; gap_range={max(gaps) - min(gaps):.3f}",
            )
    return failures


def _check_internal_tie_nodes_and_no_lacing(layout: dict[str, Any]) -> int:
    nodes = layout["nodes"]

    def has_node(point: tuple[float, float], kinds: tuple[str, ...]) -> bool:
        return any(
            Point(node["pos"]).distance(Point(point)) <= 1e-6
            and any(kind in node["kind"] for kind in kinds)
            for node in nodes
        )

    failures = 0
    diagonal_ties = [
        member
        for member in layout["members"]
        if member["kind"] == "tie"
        and not _is_horizontal(member)
        and not _is_vertical(member)
    ]
    internal_ties = [
        member
        for member in layout["members"]
        if member["kind"] == "tie"
        and LineString(member["geometry"]).length <= 15.0
    ]
    failures += _check(diagonal_ties == [], f"internal tie lacing is absent by default; actual={len(diagonal_ties)}")
    failures += _check(
        bool(internal_ties) and all(
            all(has_node(endpoint, ("tie_end", "truss_node", "strut_cross")) for endpoint in member["geometry"])
            for member in internal_ties
        ),
        "internal tie endpoints are real nodes",
    )

    crossings = []
    for main in [member for member in layout["members"] if member["kind"] == "main_strut"]:
        main_line = LineString(main["geometry"])
        for chord in [member for member in layout["members"] if member["kind"] == "truss_chord"]:
            inter = main_line.intersection(LineString(chord["geometry"]))
            if inter.is_empty:
                continue
            points: list[tuple[float, float]] = []
            if inter.geom_type == "Point":
                points = [(float(inter.x), float(inter.y))]
            elif inter.geom_type == "MultiPoint":
                points = [(float(point.x), float(point.y)) for point in inter.geoms]
            for point in points:
                if has_node(point, ("truss_node", "strut_cross")):
                    crossings.append((main["id"], chord["id"], point))
    failures += _check(bool(crossings), "main strut crossings with perimeter truss inner chord are real nodes")
    return failures


def _pair_lateral_support_positions(
    layout: dict[str, Any],
    first_axis: float,
    second_axis: float,
    *,
    vertical_pair: bool,
) -> list[float]:
    bounds = Polygon(layout["waling"]).bounds
    positions = [bounds[1], bounds[3]] if vertical_pair else [bounds[0], bounds[2]]
    positions.extend(_short_tie_positions_between_pair(layout, first_axis, second_axis, vertical_pair=vertical_pair))
    positions.extend(_long_tie_axes_for_pair(layout, vertical_pair=vertical_pair))
    for member in layout["members"]:
        if member["kind"] != "tie" or _is_horizontal(member) or _is_vertical(member):
            continue
        start, end = member["geometry"][0], member["geometry"][-1]
        if vertical_pair and {round(start[0], 6), round(end[0], 6)} == {round(first_axis, 6), round(second_axis, 6)}:
            positions.extend([start[1], end[1]])
        if not vertical_pair and {round(start[1], 6), round(end[1], 6)} == {round(first_axis, 6), round(second_axis, 6)}:
            positions.extend([start[0], end[0]])
    positions.extend(_perpendicular_main_axes_for_pair(layout, vertical_pair=vertical_pair))
    return sorted({round(value, 6) for value in positions})


def _short_tie_positions_between_pair(
    layout: dict[str, Any],
    first_axis: float,
    second_axis: float,
    *,
    vertical_pair: bool,
) -> list[float]:
    positions: set[float] = set()
    for member in layout["members"]:
        if member["kind"] != "tie":
            continue
        start, end = member["geometry"][0], member["geometry"][-1]
        if vertical_pair:
            if not _is_horizontal(member):
                continue
            if {round(start[0], 6), round(end[0], 6)} != {round(first_axis, 6), round(second_axis, 6)}:
                continue
            positions.add(round(start[1], 6))
        else:
            if not _is_vertical(member):
                continue
            if {round(start[1], 6), round(end[1], 6)} != {round(first_axis, 6), round(second_axis, 6)}:
                continue
            positions.add(round(start[0], 6))
    return sorted(positions)


def _perpendicular_main_axes_for_pair(layout: dict[str, Any], *, vertical_pair: bool) -> list[float]:
    axes: list[float] = []
    for member in layout["members"]:
        if member["kind"] != "main_strut":
            continue
        start = member["geometry"][0]
        if vertical_pair and _is_horizontal(member):
            axes.append(float(start[1]))
        if not vertical_pair and _is_vertical(member):
            axes.append(float(start[0]))
    return sorted({round(value, 6) for value in axes})


def _long_tie_axes_for_pair(layout: dict[str, Any], *, vertical_pair: bool) -> list[float]:
    bounds = Polygon(layout["waling"]).bounds
    span_threshold = (bounds[2] - bounds[0] if vertical_pair else bounds[3] - bounds[1]) * 0.5
    axes: list[float] = []
    for member in layout["members"]:
        if member["kind"] != "tie":
            continue
        start = member["geometry"][0]
        line = LineString(member["geometry"])
        if vertical_pair and _is_horizontal(member) and line.length >= span_threshold:
            axes.append(float(start[1]))
        if not vertical_pair and _is_vertical(member) and line.length >= span_threshold:
            axes.append(float(start[0]))
    return sorted({round(value, 6) for value in axes})


def _is_member_endpoint(point: tuple[float, float], member: dict[str, Any]) -> bool:
    return (
        Point(point).distance(Point(member["geometry"][0])) <= 1e-6
        or Point(point).distance(Point(member["geometry"][-1])) <= 1e-6
    )


def _corner_layer_coupling_ties_exist(
    layout: dict[str, Any],
    corner: tuple[float, float],
    corner_members: list[dict[str, Any]],
) -> bool:
    corners = list(Polygon(layout["waling"]).exterior.coords)[:-1]
    index = corners.index(corner)
    adjacent_edges = (
        LineString([corner, corners[index - 1]]),
        LineString([corner, corners[(index + 1) % len(corners)]]),
    )
    for edge in adjacent_edges:
        points = sorted(
            [
                endpoint
                for member in corner_members
                for endpoint in member["geometry"]
                if edge.distance(Point(endpoint)) <= 1e-6
            ],
            key=lambda point: edge.project(Point(point)),
        )
        if len(points) < 2:
            return False
        for start, end in zip(points, points[1:]):
            if LineString([start, end]).length < 6.0 - 1e-6:
                return False
            if not any(
                member["kind"] == "tie"
                and _same_segment(member["geometry"], [start, end])
                for member in layout["members"]
            ):
                return False
    return True


def _same_segment(left: list[tuple[float, float]], right: list[tuple[float, float]]) -> bool:
    return (
        Point(left[0]).distance(Point(right[0])) <= 1e-6
        and Point(left[-1]).distance(Point(right[-1])) <= 1e-6
    ) or (
        Point(left[0]).distance(Point(right[-1])) <= 1e-6
        and Point(left[-1]).distance(Point(right[0])) <= 1e-6
    )


def _internal_truss_members(layout: dict[str, Any]) -> list[dict[str, Any]]:
    waling_line = LineString(layout["waling"])
    return [
        member
        for member in layout["members"]
        if member["kind"] in {"truss_chord", "truss_web"}
        and not member.get("corner_role")
        and waling_line.distance(LineString(member["geometry"]).interpolate(0.5, normalized=True)) > 5.0
    ]


def _points_on_adjacent_waling_edges(
    left: tuple[float, float],
    right: tuple[float, float],
    corner: tuple[float, float],
    corners: list[tuple[float, float]],
) -> bool:
    index = corners.index(corner)
    prev_edge = LineString([corner, corners[index - 1]])
    next_edge = LineString([corner, corners[(index + 1) % len(corners)]])
    return (
        prev_edge.distance(Point(left)) <= 1e-6
        and next_edge.distance(Point(right)) <= 1e-6
    ) or (
        prev_edge.distance(Point(right)) <= 1e-6
        and next_edge.distance(Point(left)) <= 1e-6
    )


def _nearly_parallel(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_angle = _member_angle_180(left)
    right_angle = _member_angle_180(right)
    diff = abs(left_angle - right_angle)
    return min(diff, 180.0 - diff) <= 5.0


def _member_angle_180(member: dict[str, Any]) -> float:
    start, end = member["geometry"][0], member["geometry"][-1]
    return degrees(atan2(end[1] - start[1], end[0] - start[0])) % 180.0


def _main_strut_reaches_opposite_waling_sides(
    layout: dict[str, Any],
    member: dict[str, Any],
    *,
    axis: str,
) -> bool:
    min_x, min_y, max_x, max_y = Polygon(layout["waling"]).bounds
    geometry = member.get("logical_geometry", member["geometry"])
    endpoints = geometry[0], geometry[-1]
    if axis == "x":
        return (
            all(abs(point[0] - endpoints[0][0]) <= 1e-6 for point in endpoints)
            and {round(endpoints[0][1], 6), round(endpoints[-1][1], 6)} == {round(min_y, 6), round(max_y, 6)}
        )
    if axis == "y":
        return (
            all(abs(point[1] - endpoints[0][1]) <= 1e-6 for point in endpoints)
            and {round(endpoints[0][0], 6), round(endpoints[-1][0], 6)} == {round(min_x, 6), round(max_x, 6)}
        )
    raise ValueError(axis)


def _important_node_spacing(layout: dict[str, Any]) -> float:
    points = [
        tuple(node["pos"])
        for node in layout["nodes"]
        if "corner_end" in node["kind"]
        or ("strut_cross" in node["kind"] and "tie_end" not in node["kind"])
    ]
    if len(points) < 2:
        return float("inf")
    return min(
        Point(left).distance(Point(right))
        for index, left in enumerate(points)
        for right in points[index + 1:]
    )


def _max_perimeter_truss_gap(layout: dict[str, Any]) -> float:
    waling_line = LineString(layout["waling"])
    if waling_line.length <= 1e-9:
        return float("inf")

    positions = [0.0, waling_line.length]
    for member in layout["members"]:
        if member["kind"] not in {"truss_chord", "truss_web"}:
            continue
        line = LineString(member["geometry"])
        if waling_line.distance(line) > 18.0:
            continue
        for point in member["geometry"]:
            if waling_line.distance(Point(point)) <= 18.0:
                positions.append(float(waling_line.project(Point(point))))
        midpoint = line.interpolate(0.5, normalized=True)
        if waling_line.distance(midpoint) <= 18.0:
            positions.append(float(waling_line.project(midpoint)))

    unique = sorted({round(value, 6) for value in positions})
    if len(unique) < 2:
        return float("inf")
    return max(right - left for left, right in zip(unique, unique[1:]))


def _max_edge_panel_length(layout: dict[str, Any]) -> float:
    waling = LineString(layout["waling"])
    lengths = [
        LineString(member["geometry"]).length
        for member in layout["members"]
        if member["kind"] == "truss_chord"
        and waling.distance(LineString(member["geometry"]).interpolate(0.5, normalized=True)) <= 1e-6
    ]
    return max(lengths, default=float("inf"))


def _max_edge_truss_station_gap(layout: dict[str, Any]) -> float:
    gaps: list[float] = []
    logical = _logical_members(layout["members"])
    for edge_index, (start, end) in enumerate(
        zip(layout["waling"], layout["waling"][1:]),
        start=1,
    ):
        edge = LineString([start, end])
        positions = [0.0, edge.length]
        for member in logical:
            if (
                member.get("edge_truss_id") == f"edge_truss_{edge_index}"
                and member.get("edge_role") == "web"
            ):
                positions.extend(
                    float(edge.project(Point(point)))
                    for point in (member["geometry"][0], member["geometry"][-1])
                )
            if str(member.get("corner_role", "")).startswith("tier_"):
                positions.extend(
                    float(edge.project(Point(point)))
                    for point in (member["geometry"][0], member["geometry"][-1])
                    if edge.distance(Point(point)) <= 1e-6
                )
        unique = sorted({round(position, 6) for position in positions})
        gaps.extend(right - left for left, right in zip(unique, unique[1:]))
    return max(gaps, default=float("inf"))


def _edge_truss_projected_panel_lengths(
    layout: dict[str, Any],
    edge_index: int,
) -> list[float]:
    start = layout["waling"][edge_index - 1]
    end = layout["waling"][edge_index]
    edge = LineString([start, end])
    panels: list[tuple[float, float]] = []
    for member in _logical_members(layout["members"]):
        if (
            member.get("edge_truss_id") != f"edge_truss_{edge_index}"
            or member.get("edge_role") != "web"
        ):
            continue
        positions = sorted(
            float(edge.project(Point(point)))
            for point in (member["geometry"][0], member["geometry"][-1])
        )
        panels.append((positions[0], positions[-1]))
    panels.sort()
    return [round(end_pos - start_pos, 6) for start_pos, end_pos in panels]


def _logical_members(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for member in members:
        key = str(member.get("parent_member_id", member["id"]))
        if key in unique:
            continue
        logical = dict(member)
        logical["geometry"] = list(member.get("logical_geometry", member["geometry"]))
        unique[key] = logical
    return list(unique.values())


def _has_diagonal_lacing(layout: dict[str, Any]) -> bool:
    return any(
        member["kind"] == "tie"
        and not _is_horizontal(member)
        and not _is_vertical(member)
        and 20.0 <= _acute_axis_angle(member) <= 70.0
        for member in layout["members"]
    )


def _long_horizontal_distribution_tie_count(layout: dict[str, Any]) -> int:
    bounds = Polygon(layout["waling"]).bounds
    width = bounds[2] - bounds[0]
    return sum(
        1
        for member in layout["members"]
        if member["kind"] == "tie"
        and _is_horizontal(member)
        and LineString(member["geometry"]).length >= width * 0.75
    )


def _corner_coverage_zones(layout: dict[str, Any], coverage: float) -> list[Polygon]:
    corners = list(Polygon(layout["waling"]).exterior.coords)[:-1]
    zones = []
    for index, corner in enumerate(corners):
        prev_pt = corners[index - 1]
        next_pt = corners[(index + 1) % len(corners)]
        zones.append(Polygon([
            corner,
            _point_along(corner, prev_pt, coverage),
            _point_along(corner, next_pt, coverage),
        ]))
    return zones


def _point_along(
    start: tuple[float, float],
    target: tuple[float, float],
    distance: float,
) -> tuple[float, float]:
    dx = target[0] - start[0]
    dy = target[1] - start[1]
    length = (dx * dx + dy * dy) ** 0.5
    if length <= 1e-9:
        return start
    scale = min(distance, length) / length
    return (start[0] + dx * scale, start[1] + dy * scale)


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
