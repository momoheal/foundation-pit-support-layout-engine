"""Minimal command-line and pytest coverage for the internal strut engine.

Run:
    python test_strut_minimal.py
    python -m pytest test_strut_minimal.py
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from math import atan2, degrees, inf
from pathlib import Path
from typing import Any

import ezdxf
import strut_diagnostics
from shapely.geometry import LineString, Point, Polygon

from main_strut import export_strut_dxf
from strut_engine import STATS_KEYS, StrutEngine
from strut_validation import validate_layout


TMP_ROOT = Path(__file__).resolve().parent / ".tmp_pytest"


@dataclass(frozen=True)
class Case:
    name: str
    coords: list[tuple[float, float]]
    params: dict[str, Any]


CASES = [
    Case(
        "rect_60x40",
        [(0, 0), (60, 0), (60, 40), (0, 40)],
        {"support_system": "brace", "spacing": 9.0, "waling_offset": 5.0, "safe_dist": 2.5},
    ),
    Case(
        "l_shape",
        [(0, 0), (60, 0), (60, 20), (30, 20), (30, 40), (0, 40)],
        {"support_system": "brace", "spacing": 9.0, "waling_offset": 2.0, "safe_dist": 1.5},
    ),
    Case(
        "octagon_cut",
        [(10, 0), (50, 0), (60, 10), (60, 30), (50, 40), (10, 40), (0, 30), (0, 10)],
        {"support_system": "brace", "spacing": 8.0, "waling_offset": 2.0, "safe_dist": 1.5},
    ),
    Case(
        "irregular",
        [(0, 0), (30, -5), (65, 10), (70, 35), (55, 55), (20, 50), (-5, 30), (-10, 10)],
        {"support_system": "orthogonal", "spacing": 9.0, "waling_offset": 2.0, "safe_dist": 1.5},
    ),
    Case(
        "circle_or_ellipse_with_core",
        [(30 + 28 * __import__("math").cos(i * __import__("math").tau / 48),
          20 + 18 * __import__("math").sin(i * __import__("math").tau / 48)) for i in range(48)],
        {
            "support_system": "circular",
            "spacing": 8.0,
            "waling_offset": 1.0,
            "safe_dist": 1.5,
            "core_center": (30.0, 20.0),
            "core_diameter": 8.0,
            "core_clearance": 2.0,
            "ring_edge_clearance": 5.0,
        },
    ),
    Case(
        "straight_truss_rect",
        [(0, 0), (60, 0), (60, 40), (0, 40)],
        {
            "support_system": "straight_truss",
            "spacing": 9.0,
            "waling_offset": 5.0,
            "safe_dist": 2.5,
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
    Case(
        "large_rect_120x80_opposite_strut",
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
        "large_rect_120x80_brace",
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
]


def solve_case(case: Case) -> dict:
    return StrutEngine(case.coords, case.params).solve()


def test_parameter_governance() -> None:
    layout = StrutEngine(
        [(0, 0), (30, 0), (30, 20), (0, 20)],
        {"margin": 3.0, "support_system": "orthogonal"},
    ).solve()
    assert layout["waling"]

    for system in ("orthogonal", "brace", "opposite_strut", "straight_truss", "circular"):
        params: dict[str, Any] = {"support_system": system}
        if system == "circular":
            params.update({"core_center": (15, 10), "core_diameter": 4})
        StrutEngine([(0, 0), (30, 0), (30, 20), (0, 20)], params).solve()

    try:
        StrutEngine([(0, 0), (30, 0), (30, 20), (0, 20)], {"support_system": "bad"}).solve()
    except ValueError as exc:
        assert "support_system" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("invalid support_system should fail")

    try:
        StrutEngine([(0, 0), (30, 0), (30, 20), (0, 20)], {
            "support_system": "orthogonal",
            "spacing_min": 10,
            "spacing_max": 6,
        }).solve()
    except ValueError as exc:
        assert "spacing_min" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("spacing_min > spacing_max should fail")

    try:
        StrutEngine([(0, 0), (30, 0), (30, 20), (0, 20)], {"support_system": "circular"}).solve()
    except ValueError as exc:
        assert "core_center" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("circular without core parameters should fail")


def test_layout_contract_for_all_cases() -> None:
    for case in CASES:
        layout = solve_case(case)
        report = validate_layout(layout, StrutEngine(case.coords, case.params).params)
        assert report["ok"], (case.name, report["issues"])
        for key in ("waling", "corners", "struts", "ties", "pillars", "nodes", "members",
                    "outlines", "stats", "issues"):
            assert key in layout
        for key in STATS_KEYS:
            assert key in layout["stats"]
        assert layout["waling"]
        assert layout["members"]
        assert len({node["id"] for node in layout["nodes"]}) == len(layout["nodes"])
        assert len({member["id"] for member in layout["members"]}) == len(layout["members"])


def test_system_specific_outputs() -> None:
    circular_case = next(case for case in CASES if case.name == "circle_or_ellipse_with_core")
    circular = solve_case(circular_case)
    assert circular["stats"]["ring_strut_length"] > 0
    assert circular["stats"]["radial_strut_length"] > 0
    assert any(member["kind"] == "ring_strut" for member in circular["members"])
    assert any(outline["layer"] == "CORE_PROTECTION" for outline in circular["outlines"])

    straight_truss = solve_case(next(case for case in CASES if case.name == "straight_truss_rect"))
    assert straight_truss["stats"]["truss_web_length"] > 0
    assert any(member["kind"] == "truss_chord" for member in straight_truss["members"])
    assert any(member["kind"] == "truss_web" for member in straight_truss["members"])
    assert all(member["kind"] != "corner" for member in straight_truss["members"])

    opposite = solve_case(next(case for case in CASES if case.name == "large_rect_120x80_opposite_strut"))
    assert opposite["stats"]["truss_web_length"] == 0
    assert all(member["kind"] not in {"truss_chord", "truss_web", "corner"} for member in opposite["members"])

    brace = solve_case(next(case for case in CASES if case.name == "large_rect_120x80_brace"))
    assert brace["stats"]["truss_web_length"] > 0
    assert brace["stats"]["corner_length"] == 0
    assert any(member["kind"] == "truss_web" for member in brace["members"])
    assert all(member["kind"] != "corner" for member in brace["members"])

    octagon_circular = solve_case(next(case for case in CASES if case.name == "octagon_circular_core"))
    assert octagon_circular["stats"]["ring_strut_length"] > 0
    assert octagon_circular["stats"]["radial_strut_length"] > 0
    assert any(member["kind"] == "ring_strut" for member in octagon_circular["members"])

    rect = solve_case(next(case for case in CASES if case.name == "rect_60x40"))
    assert rect["stats"]["main_strut_length"] > 0
    assert rect["stats"]["corner_length"] > 0
    assert any("strut_cross" in node["kind"] for node in rect["nodes"])


def test_opposite_strut_generates_engineering_network_without_truss() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_opposite_strut")
    layout = solve_case(case)
    engine = StrutEngine(case.coords, case.params)
    waling_poly = engine._offset_poly(engine.params["waling_offset"])
    assert waling_poly is not None

    chords = [member for member in layout["members"] if member["kind"] == "truss_chord"]
    webs = [member for member in layout["members"] if member["kind"] == "truss_web"]
    ties = [member for member in layout["members"] if member["kind"] == "tie"]
    main = [member for member in layout["members"] if member["kind"] == "main_strut"]

    assert chords == []
    assert webs == []
    assert main
    assert ties

    legal_node_ids = {
        node["id"] for node in layout["nodes"]
        if any(kind in node["kind"] for kind in ("truss_node", "strut_end", "strut_cross"))
    }
    assert all(tie["start"] in legal_node_ids and tie["end"] in legal_node_ids for tie in ties)


def test_straight_truss_generates_perimeter_truss_snapped_to_main_grid() -> None:
    case = next(case for case in CASES if case.name == "straight_truss_rect")
    engine = StrutEngine(case.coords, case.params)
    layout = engine.solve()
    waling_line = LineString(layout["waling"])

    perimeter_truss = [
        member for member in layout["members"]
        if member["kind"] in {"truss_chord", "truss_web"}
        and waling_line.distance(LineString(member["geometry"]).interpolate(0.5, normalized=True)) <= 8.0
    ]
    assert any(member["kind"] == "truss_chord" for member in perimeter_truss)
    assert any(member["kind"] == "truss_web" for member in perimeter_truss)

    truss_endpoints = [
        point
        for member in perimeter_truss
        for point in (member["geometry"][0], member["geometry"][-1])
    ]
    main_edge_endpoints = [
        point
        for member in layout["members"]
        if member["kind"] == "main_strut"
        for point in member["geometry"]
        if waling_line.distance(Point(point)) <= 1e-6
    ]
    assert main_edge_endpoints
    assert all(
        any(Point(point).distance(Point(anchor)) <= 1e-6 for anchor in truss_endpoints)
        for point in main_edge_endpoints
    )

    for corner in list(Polygon(layout["waling"]).exterior.coords)[:-1]:
        zone = Point(corner).buffer(engine.params["truss_panel_max"] + 1.0)
        assert any(
            member["kind"] == "truss_chord" and zone.intersects(LineString(member["geometry"]))
            for member in perimeter_truss
        )
        assert any(
            member["kind"] == "truss_web" and zone.intersects(LineString(member["geometry"]))
            for member in perimeter_truss
        )


def test_straight_truss_short_span_struts_are_not_wrapped_in_internal_trusses() -> None:
    case = next(case for case in CASES if case.name == "straight_truss_rect")
    layout = solve_case(case)
    main_struts = [member for member in layout["members"] if member["kind"] == "main_strut"]
    vertical = _logical_members([member for member in main_struts if _is_vertical(member)])
    horizontal = _logical_members([member for member in main_struts if _is_horizontal(member)])

    assert len(vertical) <= 6
    assert len(horizontal) <= 4
    assert _minimum_axis_spacing(vertical, "x") >= case.params.get("spacing_min", 6.0) - 1e-6
    assert _minimum_axis_spacing(horizontal, "y") >= case.params.get("spacing_min", 6.0) - 1e-6
    assert _internal_truss_members(layout) == []


def test_truss_panel_primitive_returns_shared_chord_and_web_geometry() -> None:
    engine = StrutEngine([(0, 0), (20, 0), (20, 20), (0, 20)], {"support_system": "straight_truss"})

    specs = engine._truss_panel_member_specs(
        (0.0, 0.0),
        (10.0, 0.0),
        (0.0, 2.0),
        (10.0, 2.0),
        start_on_outer=True,
        end_on_outer=False,
    )

    assert specs == [
        ("truss_chord", [(0.0, 0.0), (10.0, 0.0)]),
        ("truss_chord", [(0.0, 2.0), (10.0, 2.0)]),
        ("truss_web", [(0.0, 0.0), (10.0, 2.0)]),
    ]


def test_opposite_strut_has_uniform_two_direction_struts_without_truss_or_corners() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_opposite_strut")
    layout = solve_case(case)
    waling_line = LineString(layout["waling"])
    bounds = Polygon(layout["waling"]).bounds
    main_struts = [member for member in layout["members"] if member["kind"] == "main_strut"]
    vertical = [member for member in main_struts if _is_vertical(member)]
    horizontal = [member for member in main_struts if _is_horizontal(member)]

    vertical_groups = _axis_groups(_axis_values(vertical, "x"), max_pair_gap=8.0)
    horizontal_groups = _axis_groups(_axis_values(horizontal, "y"), max_pair_gap=8.0)

    assert len(vertical_groups) >= 3
    assert len(horizontal_groups) >= 3
    assert all(len(group) == 1 for group in vertical_groups + horizontal_groups)
    assert _minimum_group_spacing(vertical_groups) >= 10.0
    assert _minimum_group_spacing(horizontal_groups) >= 10.0

    assert all(member["kind"] != "corner" for member in layout["members"])
    assert all(member["kind"] not in {"truss_chord", "truss_web"} for member in layout["members"])

    internal_truss = [
        member for member in layout["members"]
        if member["kind"] in {"truss_chord", "truss_web"}
        and waling_line.distance(LineString(member["geometry"]).interpolate(0.5, normalized=True)) > 2.0
        and _point_inside_middle_band(LineString(member["geometry"]).interpolate(0.5, normalized=True), bounds)
    ]
    assert internal_truss == []

    ties = [member for member in layout["members"] if member["kind"] == "tie"]
    assert any(_is_horizontal(tie) for tie in ties)
    assert any(_is_vertical(tie) for tie in ties)
    assert all(10.0 <= LineString(tie["geometry"]).length <= case.params["spacing_max"] + 1.0 for tie in ties)


def test_brace_edge_truss_uses_standard_panel_primitive_outside_corner_assemblies() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    waling_line = LineString(layout["waling"])
    coverage_zones = _corner_coverage_zones(layout, coverage=30.0)
    edge_webs = [
        member for member in layout["members"]
        if member["kind"] == "truss_web"
        and not member.get("stiffening_at")
        and waling_line.distance(LineString(member["geometry"]).interpolate(0.5, normalized=True)) <= 4.0
        and not any(
            LineString(member["geometry"]).intersection(zone).length > 1e-6
            for zone in coverage_zones
        )
    ]
    post_webs = [
        member for member in edge_webs
        if _acute_axis_angle(member) <= 5.0 or _acute_axis_angle(member) >= 85.0
    ]

    assert len(edge_webs) >= 4
    assert all(member.get("truss_primitive") == "panel" for member in edge_webs)
    assert len(post_webs) <= 4


def test_large_brace_corner_panels_use_truss_web_triangulation() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    waling_line = LineString(layout["waling"])
    groups = {
        member["belongs_to_corner_bracket"]
        for member in layout["members"]
        if member.get("corner_role") == "leg"
    }

    assert len(groups) == 4
    for group in groups:
        corner_webs = [
            member for member in layout["members"]
            if member["kind"] == "truss_web"
            and member.get("belongs_to_corner_bracket") == group
            and member.get("corner_role") == "leg"
        ]
        corner_chords = [
            member for member in layout["members"]
            if member["kind"] == "truss_chord"
            and member.get("belongs_to_corner_bracket") == group
            and member.get("corner_role") == "leg"
        ]

        assert len(corner_webs) >= 2
        assert len(corner_chords) >= 4
        assert any(
            any(waling_line.distance(Point(endpoint)) <= 1e-6 for endpoint in member["geometry"])
            and any(waling_line.distance(Point(endpoint)) > 1.0 for endpoint in member["geometry"])
            for member in corner_webs
        )


def test_large_brace_corners_have_node_based_triangular_web_pairs() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    waling = Polygon(layout["waling"])
    waling_corners = list(waling.exterior.coords)[:-1]
    truss_nodes = _truss_node_points(layout)

    for corner in waling_corners:
        zone = Point(corner).buffer(case.params["truss_panel_max"] + 8.0)
        corner_webs = [
            member for member in layout["members"]
            if member["kind"] == "truss_web"
            and zone.intersects(LineString(member["geometry"]))
            and 20.0 <= _acute_axis_angle(member) <= 70.0
        ]

        assert len(corner_webs) >= 2
        assert all(
            all(any(Point(endpoint).distance(Point(node)) <= 1e-6 for node in truss_nodes) for endpoint in member["geometry"])
            for member in corner_webs
        )


def test_main_strut_truss_crossings_are_split_into_shared_vertices() -> None:
    cases = [
        next(case for case in CASES if case.name == "large_rect_120x80_brace"),
        next(case for case in CASES if case.name == "straight_truss_rect"),
    ]

    for case in cases:
        layout = solve_case(case)
        nodes = layout["nodes"]
        crossings = []
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
                    crossings.append((main, truss, point))
                    assert any(
                        Point(point).distance(Point(endpoint)) <= 1e-6
                        for endpoint in (truss["geometry"][0], truss["geometry"][-1])
                    )
                    assert any(
                        Point(node["pos"]).distance(Point(point)) <= 1e-6
                        and {main["id"], truss["id"]} <= set(node["source"])
                        for node in nodes
                    )

        assert crossings


def test_diagnostic_connection_points_cover_main_truss_crossings() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    assert hasattr(strut_diagnostics, "_main_truss_connection_points")
    rendered_points = strut_diagnostics._main_truss_connection_points(layout)
    expected_points = [
        (float(intersection.x), float(intersection.y))
        for main in layout["members"]
        if main["kind"] == "main_strut"
        for truss in layout["members"]
        if truss["kind"] in {"truss_chord", "truss_web"}
        for intersection in [LineString(main["geometry"]).intersection(LineString(truss["geometry"]))]
        if intersection.geom_type == "Point"
    ]

    assert rendered_points
    assert all(
        any(Point(rendered).distance(Point(expected)) <= 1e-5 for rendered in rendered_points)
        for expected in expected_points
    )
    assert all(
        any(Point(rendered).distance(Point(expected)) <= 1e-5 for expected in expected_points)
        for rendered in rendered_points
    )


def test_internal_ties_are_scoped_to_their_own_strut_pair() -> None:
    cases = [
        next(case for case in CASES if case.name == "large_rect_120x80_brace"),
        next(case for case in CASES if case.name == "straight_truss_rect"),
    ]

    for case in cases:
        layout = solve_case(case)
        main_struts = _logical_members([
            member for member in layout["members"] if member["kind"] == "main_strut"
        ])
        for tie in [member for member in layout["members"] if member["kind"] == "tie"]:
            tie_line = LineString(tie["geometry"])
            intersecting = [
                main for main in main_struts
                if not tie_line.intersection(LineString(main["geometry"])).is_empty
            ]
            assert len(intersecting) == 2
            assert all(
                any(
                    LineString(main["geometry"]).distance(Point(endpoint)) <= 1e-6
                    for main in intersecting
                )
                for endpoint in (tie["geometry"][0], tie["geometry"][-1])
            )


def test_ties_respect_minimum_clearance_from_parallel_main_struts() -> None:
    cases = [
        next(case for case in CASES if case.name == "large_rect_120x80_brace"),
        next(case for case in CASES if case.name == "straight_truss_rect"),
    ]

    for case in cases:
        engine = StrutEngine(case.coords, case.params)
        layout = engine.solve()
        clearance = float(engine.params["min_tie_to_strut_clearance"])
        main_struts = [member for member in layout["members"] if member["kind"] == "main_strut"]
        for tie in [member for member in layout["members"] if member["kind"] == "tie"]:
            distances = [
                LineString(tie["geometry"]).distance(LineString(main["geometry"]))
                for main in main_struts
                if _nearly_parallel(tie, main)
            ]
            assert all(distance <= 1e-6 or distance >= clearance - 1e-6 for distance in distances)


def test_no_nodes_closer_than_min_separation() -> None:
    cases = [
        next(case for case in CASES if case.name == "large_rect_120x80_brace"),
        next(case for case in CASES if case.name == "straight_truss_rect"),
    ]

    for case in cases:
        engine = StrutEngine(case.coords, case.params)
        layout = engine.solve()
        min_separation = float(engine.params["min_node_separation"])
        distances = [
            Point(left["pos"]).distance(Point(right["pos"]))
            for index, left in enumerate(layout["nodes"])
            for right in layout["nodes"][index + 1:]
        ]
        assert distances
        assert min(distances) >= min_separation - 1e-6


def test_strut_positions_align_with_truss_panel_vertices() -> None:
    cases = [
        next(case for case in CASES if case.name == "large_rect_120x80_brace"),
        next(case for case in CASES if case.name == "straight_truss_rect"),
    ]

    for case in cases:
        engine = StrutEngine(case.coords, case.params)
        layout = engine.solve()
        waling = LineString(layout["waling"])
        web_endpoints = [
            endpoint
            for member in layout["members"]
            if member["kind"] == "truss_web"
            for endpoint in (member["geometry"][0], member["geometry"][-1])
        ]
        main_edge_endpoints = [
            endpoint
            for member in layout["members"]
            if member["kind"] == "main_strut"
            for endpoint in (member["geometry"][0], member["geometry"][-1])
            if waling.distance(Point(endpoint)) <= 1e-6
        ]

        assert main_edge_endpoints
        assert all(
            any(Point(endpoint).distance(Point(web_endpoint)) <= 1e-6 for web_endpoint in web_endpoints)
            for endpoint in main_edge_endpoints
        )


def test_edge_and_corner_trusses_handoff_at_setback_nodes() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    engine = StrutEngine(case.coords, case.params)
    layout = engine.solve()
    model = engine._large_brace_corner_anchor_model(layout, Polygon(layout["waling"]))
    members_by_id = {member["id"]: member for member in layout["members"]}

    for corner in model["corners"]:
        for anchor in (corner["prev_anchor"], corner["next_anchor"]):
            node = next(
                node for node in layout["nodes"]
                if Point(node["pos"]).distance(Point(anchor)) <= 1e-6
            )
            roles = {
                members_by_id[member_id].get("corner_role")
                for member_id in node["source"]
                if member_id in members_by_id
            }
            assert {"edge_panel", "leg"} <= roles
            assert Point(anchor).distance(Point(corner["corner"])) > 1e-6


def test_corner_leg_uses_shared_truss_primitive() -> None:
    cases = [
        next(case for case in CASES if case.name == "large_rect_120x80_brace"),
        next(case for case in CASES if case.name == "straight_truss_rect"),
    ]

    for case in cases:
        layout = solve_case(case)
        groups = {
            member["belongs_to_corner_bracket"]
            for member in layout["members"]
            if member.get("corner_role") == "leg"
        }
        assert len(groups) == 4
        for group in groups:
            leg_members = [
                member for member in layout["members"]
                if member.get("belongs_to_corner_bracket") == group
                and member.get("corner_role") == "leg"
            ]
            assert sum(member["kind"] == "truss_chord" for member in leg_members) >= 2
            assert sum(member["kind"] == "truss_web" for member in leg_members) >= 1
            assert all(member.get("truss_primitive") == "panel" for member in leg_members)


def test_corner_lattice_terminates_on_adjacent_waling_edges() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    engine = StrutEngine(case.coords, case.params)
    layout = engine.solve()
    model = engine._large_brace_corner_anchor_model(layout, Polygon(layout["waling"]))
    waling = Polygon(layout["waling"])

    assert len(model["corners"]) == 4
    for corner in model["corners"]:
        anchors = (corner["prev_anchor"], corner["next_anchor"])
        assert all(waling.exterior.distance(Point(anchor)) <= 1e-6 for anchor in anchors)
        assert all(Point(anchor).distance(Point(corner["corner"])) >= case.params["truss_panel_min"] for anchor in anchors)


def test_corner_lattice_tiles_between_setback_anchors() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    engine = StrutEngine(case.coords, case.params)
    layout = engine.solve()
    model = engine._large_brace_corner_anchor_model(layout, Polygon(layout["waling"]))

    for corner in model["corners"]:
        members = [
            member for member in layout["members"]
            if member.get("belongs_to_corner_bracket") == corner["assembly_id"]
            and member.get("corner_role") == "leg"
        ]
        assert sum(member["kind"] == "truss_chord" for member in members) >= 4
        assert sum(member["kind"] == "truss_web" for member in members) >= 2
        assert not any(
            Point(endpoint).distance(Point(corner["corner"])) <= 1e-6
            for member in members
            for endpoint in (member["geometry"][0], member["geometry"][-1])
        )


def test_strut_truss_crossing_has_local_stiffening() -> None:
    cases = [
        next(case for case in CASES if case.name == "large_rect_120x80_brace"),
        next(case for case in CASES if case.name == "straight_truss_rect"),
    ]

    for case in cases:
        layout = solve_case(case)
        waling = LineString(layout["waling"])
        for main in [member for member in layout["members"] if member["kind"] == "main_strut"]:
            for endpoint in main["geometry"]:
                if waling.distance(Point(endpoint)) > 1e-6:
                    continue
                stiffeners = [
                    member for member in layout["members"]
                    if member["kind"] == "truss_web"
                    and main.get("parent_member_id", main["id"])
                    in member.get("stiffening_for", [member.get("stiffening_at")])
                    and any(
                        Point(point).distance(Point(endpoint)) <= 1e-6
                        for point in member.get("stiffening_points", [member.get("stiffening_point")])
                        if point is not None
                    )
                ]
                assert len(stiffeners) >= 2


def test_corner_assembly_members_share_grouping_tag() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    groups = {
        member["belongs_to_corner_bracket"]
        for member in layout["members"]
        if member.get("belongs_to_corner_bracket")
    }

    assert len(groups) == 4
    for group in groups:
        roles = {
            member.get("corner_role")
            for member in layout["members"]
            if member.get("belongs_to_corner_bracket") == group
        }
        assert {"edge_panel", "leg"} <= roles


def test_separate_corner_tier_fan_is_removed() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    engine = StrutEngine(case.coords, case.params)
    layout = engine.solve()
    model = engine._corner_truss_anchor_model(layout, Polygon(layout["waling"]))

    assert model.get("bracket_diagonals", []) == []
    assert model.get("bracket_rungs", []) == []


def test_large_brace_main_struts_avoid_corner_brace_coverage() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    coverage_zones = _corner_coverage_zones(layout, coverage=30.0)
    intruding = [
        member["id"]
        for member in layout["members"]
        if member["kind"] == "main_strut"
        and any(
            LineString(member["geometry"]).intersection(zone).length > 1e-6
            for zone in coverage_zones
        )
    ]

    assert intruding == []


def test_large_brace_main_struts_must_reach_opposite_waling_edges() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    waling = Polygon(layout["waling"])
    dangling = [
        (member["id"], member["geometry"])
        for member in _logical_members([
            candidate for candidate in layout["members"] if candidate["kind"] == "main_strut"
        ])
        if any(Point(endpoint).distance(waling.exterior) > 1e-6 for endpoint in member["geometry"])
    ]

    assert dangling == []


def test_large_brace_has_at_least_one_horizontal_opposite_strut_group() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    horizontal = [
        member for member in layout["members"]
        if member["kind"] == "main_strut"
        and _is_horizontal(member)
        and _main_strut_reaches_opposite_waling_sides(layout, member, axis="y")
    ]
    y_values = _axis_values(horizontal, "y")
    groups = _axis_groups(y_values, max_pair_gap=8.0)

    assert any(len(group) >= 2 for group in groups)


def test_large_brace_horizontal_opposite_strut_group_has_regular_coupling_ties() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    horizontal = [
        member for member in layout["members"]
        if member["kind"] == "main_strut"
        and _is_horizontal(member)
        and _main_strut_reaches_opposite_waling_sides(layout, member, axis="y")
    ]
    y_values = _axis_values(horizontal, "y")
    groups = [group for group in _axis_groups(y_values, max_pair_gap=8.0) if len(group) >= 2]
    assert groups

    group = groups[0]
    y_low, y_high = min(group), max(group)
    coupling_ties = [
        member for member in layout["members"]
        if member["kind"] == "tie"
        and _is_vertical(member)
        and {round(member["geometry"][0][1], 6), round(member["geometry"][-1][1], 6)}
        == {round(y_low, 6), round(y_high, 6)}
    ]
    assert len(coupling_ties) >= 3
    positions = _pair_lateral_support_positions(layout, y_low, y_high, vertical_pair=False)
    assert _max_gap(positions) <= case.params.get("max_unbraced_pair_length", case.params["truss_panel_max"] * 1.5) + 1e-6


def test_large_brace_internal_ties_are_perpendicular_couplings() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    lacing = [
        member for member in layout["members"]
        if member["kind"] == "tie"
        and not _is_horizontal(member)
        and not _is_vertical(member)
    ]

    assert lacing == []


def test_large_brace_horizontal_main_group_uses_perpendicular_couplings() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    horizontal = [
        member for member in layout["members"]
        if member["kind"] == "main_strut"
        and _is_horizontal(member)
        and _main_strut_reaches_opposite_waling_sides(layout, member, axis="y")
    ]
    groups = [group for group in _axis_groups(_axis_values(horizontal, "y"), max_pair_gap=8.0) if len(group) >= 2]
    assert groups

    y_low, y_high = min(groups[0]), max(groups[0])
    lacing = [
        member for member in layout["members"]
        if member["kind"] == "tie"
        and not _is_horizontal(member)
        and not _is_vertical(member)
        and {round(member["geometry"][0][1], 6), round(member["geometry"][-1][1], 6)}
        == {round(y_low, 6), round(y_high, 6)}
    ]

    assert lacing == []


def test_large_brace_every_vertical_pair_tie_level_is_perpendicular() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    vertical_pairs = _paired_main_strut_axis_groups(layout, axis="x")

    assert vertical_pairs
    for x_low, x_high in vertical_pairs:
        rung_levels = _short_tie_positions_between_pair(layout, x_low, x_high, vertical_pair=True)
        assert len(rung_levels) >= 3
        assert not any(
            _pair_has_diagonal_lacing_touching_position(layout, x_low, x_high, y, vertical_pair=True)
            for y in rung_levels
        )


def test_large_brace_horizontal_pair_clear_bays_need_no_diagonal_lacing() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    horizontal_pairs = _paired_main_strut_axis_groups(layout, axis="y")

    assert horizontal_pairs
    for y_low, y_high in horizontal_pairs:
        rung_positions = _short_tie_positions_between_pair(layout, y_low, y_high, vertical_pair=False)
        assert len(rung_positions) >= 3
        for start, end in zip(rung_positions, rung_positions[1:]):
            if _bay_contains_perpendicular_main_axis(layout, start, end, vertical_pair=False):
                continue
            assert not _pair_has_diagonal_lacing_spanning_bay(layout, y_low, y_high, start, end, vertical_pair=False)


def test_large_brace_horizontal_pair_support_spacing_is_uniform() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    horizontal_pairs = _paired_main_strut_axis_groups(layout, axis="y")

    assert horizontal_pairs
    for y_low, y_high in horizontal_pairs:
        positions = _pair_lateral_support_positions(layout, y_low, y_high, vertical_pair=False)
        gaps = [right - left for left, right in zip(positions, positions[1:])]
        assert len(gaps) >= 3
        assert max(gaps) - min(gaps) <= 4.0


def test_large_brace_internal_tie_endpoints_are_real_nodes() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    nodes = layout["nodes"]

    def has_node(point: tuple[float, float], kinds: tuple[str, ...]) -> bool:
        return any(
            Point(node["pos"]).distance(Point(point)) <= 1e-6
            and any(kind in node["kind"] for kind in kinds)
            for node in nodes
        )

    def is_endpoint(point: tuple[float, float], geometry: list[tuple[float, float]]) -> bool:
        return (
            Point(point).distance(Point(geometry[0])) <= 1e-6
            or Point(point).distance(Point(geometry[-1])) <= 1e-6
        )

    internal_ties = [
        member
        for member in layout["members"]
        if member["kind"] == "tie"
        and LineString(member["geometry"]).length <= case.params["spacing_max"] + 1.0
    ]
    assert internal_ties
    assert all(
        all(has_node(endpoint, ("tie_end", "truss_node", "strut_cross")) for endpoint in member["geometry"])
        for member in internal_ties
    )

    main_struts = _logical_members([
        member for member in layout["members"] if member["kind"] == "main_strut"
    ])
    truss_chords = [member for member in layout["members"] if member["kind"] == "truss_chord"]
    crossing_nodes = []
    for main in main_struts:
        main_line = LineString(main["geometry"])
        for chord in truss_chords:
            inter = main_line.intersection(LineString(chord["geometry"]))
            if inter.is_empty:
                continue
            points: list[tuple[float, float]] = []
            if inter.geom_type == "Point":
                points = [(float(inter.x), float(inter.y))]
            elif inter.geom_type == "MultiPoint":
                points = [(float(point.x), float(point.y)) for point in inter.geoms]
            for point in points:
                if is_endpoint(point, main["geometry"]) and is_endpoint(point, chord["geometry"]):
                    continue
                if has_node(point, ("truss_node", "strut_cross")):
                    crossing_nodes.append((main["id"], chord["id"], point))

    assert crossing_nodes


def test_large_brace_pair_lacing_limits_unbraced_length() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    limit = case.params.get("max_unbraced_pair_length", case.params["truss_panel_max"] * 1.5)

    for x_low, x_high in _paired_main_strut_axis_groups(layout, axis="x"):
        positions = _pair_lateral_support_positions(layout, x_low, x_high, vertical_pair=True)
        assert max(right - left for left, right in zip(positions, positions[1:])) <= limit + 1e-6

    for y_low, y_high in _paired_main_strut_axis_groups(layout, axis="y"):
        positions = _pair_lateral_support_positions(layout, y_low, y_high, vertical_pair=False)
        assert max(right - left for left, right in zip(positions, positions[1:])) <= limit + 1e-6


def test_large_brace_internal_tie_spacing_is_modular() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    limit = case.params.get("max_unbraced_pair_length", case.params["truss_panel_max"] * 1.5)

    for x_low, x_high in _paired_main_strut_axis_groups(layout, axis="x"):
        rung_y = _short_tie_positions_between_pair(layout, x_low, x_high, vertical_pair=True)
        assert _max_gap(rung_y) <= limit + 1e-6

    for y_low, y_high in _paired_main_strut_axis_groups(layout, axis="y"):
        positions = _pair_lateral_support_positions(layout, y_low, y_high, vertical_pair=False)
        assert _max_gap(positions) <= limit + 1e-6


def test_large_brace_short_coupling_ties_connect_adjacent_main_struts() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    main_struts = _logical_members([
        member for member in layout["members"] if member["kind"] == "main_strut"
    ])
    ties = [
        member for member in layout["members"]
        if member["kind"] == "tie"
        and LineString(member["geometry"]).length <= case.params["spacing_max"] + 1.0
        and (_is_horizontal(member) or _is_vertical(member))
    ]

    assert ties
    for member in ties:
        connected_main = [
            main for main in main_struts
            if any(
                LineString(main["geometry"]).distance(Point(tie_endpoint)) <= 1e-6
                for tie_endpoint in member["geometry"]
            )
        ]
        assert len(connected_main) == 2, member
        assert 6.0 <= LineString(member["geometry"]).length <= case.params["spacing_max"] + 1.0


def test_large_brace_has_no_full_width_distribution_ties() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    min_x, _, max_x, _ = Polygon(layout["waling"]).bounds
    width = max_x - min_x
    long_horizontal = [
        member for member in layout["members"]
        if member["kind"] == "tie"
        and _is_horizontal(member)
        and LineString(member["geometry"]).length >= width * 0.75
    ]

    assert long_horizontal == []


def test_large_brace_has_at_least_one_vertical_opposite_strut_group() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    vertical = [
        member
        for member in layout["members"]
        if member["kind"] == "main_strut"
        and _is_vertical(member)
        and _main_strut_reaches_opposite_waling_sides(layout, member, axis="x")
    ]
    x_values = _axis_values(vertical, "x")
    groups = _axis_groups(x_values, max_pair_gap=8.0)

    assert any(len(group) >= 2 for group in groups)


def test_large_brace_has_two_vertical_opposite_strut_groups() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    vertical = [
        member
        for member in layout["members"]
        if member["kind"] == "main_strut"
        and _is_vertical(member)
        and _main_strut_reaches_opposite_waling_sides(layout, member, axis="x")
    ]
    groups = _axis_groups(_axis_values(vertical, "x"), max_pair_gap=8.0)

    assert sum(1 for group in groups if len(group) >= 2) >= 2
    assert _minimum_group_spacing([group for group in groups if len(group) >= 2]) >= 10.0


def test_large_brace_perimeter_truss_no_coverage_gap() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)

    outer_chords = _large_brace_outer_edge_chords(layout)
    assert outer_chords
    assert all(
        LineString(member["geometry"]).length <= case.params["truss_panel_max"] + 1e-6
        for member in outer_chords
    )


def test_large_brace_perimeter_outer_chords_cover_each_edge() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)

    outer_chords = _large_brace_outer_edge_chords(layout)
    assert all(
        any(
            LineString([start, end]).distance(LineString(member["geometry"])) <= 1e-6
            for member in outer_chords
        )
        for start, end in zip(layout["waling"], layout["waling"][1:])
    )


def test_large_brace_symmetric_instances_produce_equivalent_output() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    engine = StrutEngine(case.coords, case.params)
    layout = engine.solve()
    groups = sorted({
        member["belongs_to_corner_bracket"]
        for member in layout["members"]
        if member.get("corner_role") == "leg"
    })
    bracket_counts = [
        sum(
            1
            for member in layout["members"]
            if member.get("belongs_to_corner_bracket") == group
            and member.get("corner_role") == "leg"
        )
        for group in groups
    ]
    vertical_pairs = _paired_main_strut_axis_groups(layout, axis="x")
    vertical_supports = [
        _pair_lateral_support_positions(layout, left, right, vertical_pair=True)
        for left, right in vertical_pairs
    ]

    assert len(groups) == 4
    assert len(set(bracket_counts)) == 1
    assert len({tuple(supports) for supports in vertical_supports}) == 1
    assert all(len(_short_tie_positions_between_pair(layout, left, right, vertical_pair=True)) >= 2 for left, right in vertical_pairs)


def test_validation_reports_perimeter_truss_coverage_gap() -> None:
    layout = {
        "waling": [(0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0), (0.0, 0.0)],
        "corners": [],
        "struts": [],
        "ties": [],
        "pillars": [],
        "nodes": [],
        "members": [
            {
                "id": "M001",
                "kind": "waling",
                "geometry": [(0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0), (0.0, 0.0)],
            },
            {
                "id": "M002",
                "kind": "truss_chord",
                "geometry": [(0.0, 0.0), (8.0, 0.0)],
            },
            {
                "id": "M003",
                "kind": "truss_web",
                "geometry": [(0.0, 0.0), (4.0, 2.0)],
            },
        ],
        "outlines": [],
        "stats": {},
        "issues": [],
    }

    report = validate_layout(layout, {
        "support_system": "straight_truss",
        "truss_panel_max": 8.0,
        "truss_depth": 1.0,
    })

    assert any(
        issue["reason"].startswith("perimeter_truss_gap:")
        for issue in report["issues"]
    )


def test_large_brace_has_no_separate_corner_members() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    corner_members = [member for member in layout["members"] if member["kind"] == "corner"]

    assert corner_members == []
    assert layout["corners"] == []
    assert layout["stats"]["corner_length"] == 0.0


def test_corner_vertices_have_no_direct_truss_leg_connection() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    corners = list(Polygon(layout["waling"]).exterior.coords)[:-1]
    connected = [
        member for member in layout["members"]
        if member.get("corner_role") == "leg"
        and any(
            Point(endpoint).distance(Point(corner)) <= 1e-6
            for corner in corners
            for endpoint in (member["geometry"][0], member["geometry"][-1])
        )
    ]
    assert connected == []


def test_large_brace_columns_and_structural_nodes_are_not_dense() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)

    assert _minimum_point_spacing(layout["pillars"]) >= 6.0

    important_nodes = [
        tuple(node["pos"])
        for node in layout["nodes"]
        if "corner_end" in node["kind"]
        or ("strut_cross" in node["kind"] and "tie_end" not in node["kind"])
    ]
    assert _minimum_point_spacing(important_nodes) >= 3.0


def test_large_brace_parallel_regular_members_keep_engineering_clearance() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    regular = [
        member for member in layout["members"]
        if member["kind"] in {"main_strut", "corner", "tie"}
    ]
    close_parallel = [
        (left["id"], right["id"], distance)
        for index, left in enumerate(regular)
        for right in regular[index + 1:]
        if _nearly_parallel(left, right)
        for distance in [LineString(left["geometry"]).distance(LineString(right["geometry"]))]
        if 1e-6 < distance < 3.0
    ]

    assert close_parallel == []


def test_large_brace_edge_truss_does_not_have_close_parallel_webs() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    engine = StrutEngine(case.coords, case.params)
    layout = engine.solve()
    waling_line = LineString(layout["waling"])
    corner_model = engine._corner_truss_anchor_model(layout, Polygon(layout["waling"]))
    bracket_diagonals = corner_model["bracket_diagonals"]
    edge_truss = [
        member for member in layout["members"]
        if member["kind"] in {"truss_chord", "truss_web"}
        and member.get("corner_role") != "leg"
        and not member.get("stiffening_at")
        and waling_line.distance(LineString(member["geometry"]).interpolate(0.5, normalized=True)) <= 18.0
        and not any(_same_segment(member["geometry"], diagonal) for diagonal in bracket_diagonals)
    ]
    close_parallel = [
        (left["id"], right["id"], distance)
        for index, left in enumerate(edge_truss)
        for right in edge_truss[index + 1:]
        if left["kind"] == right["kind"] == "truss_web"
        if _nearly_parallel(left, right)
        for distance in [LineString(left["geometry"]).distance(LineString(right["geometry"]))]
        if 1e-6 < distance < 3.0
        and not _share_endpoint(left, right)
    ]

    assert close_parallel == []


def test_main_struts_are_clipped_inside_non_rectangular_wale() -> None:
    for name in ("l_shape", "octagon_cut", "irregular"):
        case = next(case for case in CASES if case.name == name)
        layout = solve_case(case)
        waling_poly = Polygon(layout["waling"])
        main_struts = [member for member in layout["members"] if member["kind"] == "main_strut"]

        assert main_struts, name
        assert all(
            waling_poly.buffer(1e-6).covers(LineString(member["geometry"]))
            for member in main_struts
        ), name


def test_octagonal_pit_gets_secondary_perimeter_supports() -> None:
    case = next(case for case in CASES if case.name == "octagon_cut")
    params = dict(case.params)
    params["max_unbraced_perimeter"] = 0.5
    layout = StrutEngine(case.coords, params).solve()
    secondary = [
        member for member in layout["members"]
        if member["kind"] in {"radial_strut", "truss_chord", "truss_web"}
    ]

    assert secondary


def test_opposite_strut_ties_connect_adjacent_main_struts() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_opposite_strut")
    layout = solve_case(case)
    main_struts = _logical_members([
        member for member in layout["members"] if member["kind"] == "main_strut"
    ])
    ties = [
        member for member in layout["members"]
        if member["kind"] == "tie"
    ]

    assert ties
    for member in ties:
        tie_line = LineString(member["geometry"])
        connected_main = [
            main for main in main_struts
            if any(
                tie_line.distance(Point(endpoint)) <= 1e-6
                and LineString(main["geometry"]).distance(Point(endpoint)) <= 1e-6
                for endpoint in member["geometry"]
            )
        ]
        assert len(connected_main) == 2, member
        assert 10.0 <= LineString(member["geometry"]).length <= case.params["spacing_max"] + 1.0


def test_large_brace_corner_uses_truss_nodes_not_corner_nodes() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    corner_zones = [Point(point).buffer(35.0) for point in list(Polygon(layout["waling"]).exterior.coords)[:-1]]
    corner_members = [member for member in layout["members"] if member["kind"] == "corner"]
    corner_nodes = [node for node in layout["nodes"] if "corner_end" in node["kind"]]
    truss_corner_members = [
        member for member in layout["members"]
        if member["kind"] in {"truss_chord", "truss_web"}
        and any(zone.intersects(LineString(member["geometry"])) for zone in corner_zones)
    ]

    assert corner_members == []
    assert corner_nodes == []
    assert truss_corner_members


def test_node_snapping_merges_close_member_endpoints() -> None:
    engine = StrutEngine(
        [(0, 0), (30, 0), (30, 20), (0, 20)],
        {"support_system": "orthogonal", "node_snap_tolerance": 0.1},
    )
    layout = engine._empty_layout()
    first = engine._add_linear_member(
        layout,
        "main_strut",
        [(5.0, 5.0), (15.0, 5.0)],
        old_key=None,
        node_kind="strut_end",
    )
    second = engine._add_linear_member(
        layout,
        "tie",
        [(15.05, 5.03), (20.0, 5.0)],
        old_key=None,
        node_kind="tie_end",
    )

    assert first is not None
    assert second is not None
    assert first["end"] == second["start"]
    snapped_node = next(node for node in layout["nodes"] if node["id"] == first["end"])
    assert Point(snapped_node["pos"]).distance(Point((15.0, 5.0))) <= 0.1


def test_node_snapping_respects_tolerance_over_rounded_index() -> None:
    engine = StrutEngine(
        [(0, 0), (30, 0), (30, 20), (0, 20)],
        {"support_system": "orthogonal", "node_snap_tolerance": 0.001},
    )
    layout = engine._empty_layout()
    first_id = engine._add_node(layout, (10.0004, 10.0004), "strut_end", ["M001"])
    second_id = engine._add_node(layout, (10.0014, 10.0014), "tie_end", ["M002"])

    assert first_id != second_id
    assert len(layout["nodes"]) == 2


def test_columns_prioritize_main_strut_intersections() -> None:
    case = next(case for case in CASES if case.name == "rect_60x40")
    layout = solve_case(case)
    strut_crosses = [
        tuple(node["pos"]) for node in layout["nodes"]
        if "strut_cross" in node["kind"]
    ]

    assert strut_crosses
    assert all(
        any(Point(pillar).distance(Point(cross)) <= 0.1 for pillar in layout["pillars"])
        for cross in strut_crosses
    )


def test_designed_member_connections_are_explicit_nodes() -> None:
    case = next(case for case in CASES if case.name == "rect_60x40")
    layout = solve_case(case)
    main = [member for member in layout["members"] if member["kind"] == "main_strut"]
    ties = [member for member in layout["members"] if member["kind"] == "tie"]

    for main_member in main:
        main_line = LineString(main_member["geometry"])
        for tie in ties:
            inter = main_line.intersection(LineString(tie["geometry"]))
            if inter.is_empty:
                continue
            assert inter.geom_type == "Point"
            point = (float(inter.x), float(inter.y))
            assert any(
                Point(node["pos"]).distance(Point(point)) <= 1e-6
                and {main_member["id"], tie["id"]} <= set(node["source"])
                for node in layout["nodes"]
            ), (main_member["id"], tie["id"], point)


def test_edge_truss_uses_waling_as_outer_chord() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    waling_line = LineString(layout["waling"])
    coverage_zones = _corner_coverage_zones(layout, coverage=30.0)
    outer_chord_length = sum(
        LineString(member["geometry"]).length
        for member in layout["members"]
        if member["kind"] == "truss_chord"
        and waling_line.distance(LineString(member["geometry"]).interpolate(0.5, normalized=True)) < 1e-6
        and not any(
            LineString(member["geometry"]).intersection(zone).length > 1e-6
            for zone in coverage_zones
        )
    )
    assert outer_chord_length > 0.0


def test_main_strut_grid_uses_edge_anchored_modular_spacing() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    waling_poly = Polygon(layout["waling"])
    min_x, min_y, max_x, max_y = waling_poly.bounds

    vertical_x = sorted({
        round(member["geometry"][0][0], 6)
        for member in layout["members"]
        if member["kind"] == "main_strut"
        and abs(member["geometry"][0][0] - member["geometry"][-1][0]) < 1e-6
    })
    horizontal_y = sorted({
        round(member["geometry"][0][1], 6)
        for member in layout["members"]
        if member["kind"] == "main_strut"
        and abs(member["geometry"][0][1] - member["geometry"][-1][1]) < 1e-6
    })

    if vertical_x:
        left_offset = vertical_x[0] - min_x
        right_offset = max_x - vertical_x[-1]

        assert left_offset >= 3.0
        assert abs(left_offset - right_offset) <= 1e-6
    if horizontal_y:
        bottom_offset = horizontal_y[0] - min_y
        top_offset = max_y - horizontal_y[-1]
        assert bottom_offset >= case.params["spacing"]
        assert abs(bottom_offset - top_offset) <= 1e-6

    vertical_groups = _axis_groups(vertical_x, max_pair_gap=8.0)
    horizontal_groups = _axis_groups(horizontal_y, max_pair_gap=8.0)
    assert sum(1 for group in vertical_groups if len(group) >= 2) >= 2
    assert sum(1 for group in horizontal_groups if len(group) >= 2) == 1
    assert _minimum_group_spacing([group for group in vertical_groups if len(group) >= 2]) >= 10.0


def test_edge_truss_is_continuous_on_straight_middle_segments() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    top_y = max(point[1] for point in layout["waling"])

    top_truss_x = sorted({
        round(point[0], 6)
        for member in layout["members"]
        if member["kind"] in {"truss_chord", "truss_web"}
        for point in (member["geometry"][0], member["geometry"][-1])
        if abs(point[1] - top_y) < 1e-6
    })

    assert top_truss_x
    assert max(right - left for left, right in zip(top_truss_x, top_truss_x[1:])) <= case.params["truss_panel_max"]
    main_top_x = sorted({
        round(point[0], 6)
        for member in layout["members"]
        if member["kind"] == "main_strut"
        for point in member["geometry"]
        if abs(point[1] - top_y) < 1e-6
    })
    if main_top_x:
        assert set(main_top_x) <= set(top_truss_x)


def test_truss_panels_use_diagonal_webs_outside_corner_zones_without_internal_truss_posts() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    engine = StrutEngine(case.coords, case.params)
    layout = engine.solve()
    waling_line = LineString(layout["waling"])
    bounds = Polygon(layout["waling"]).bounds
    coverage_zones = _corner_coverage_zones(layout, coverage=30.0)

    edge_diagonal_webs = [
        member
        for member in layout["members"]
        if member["kind"] == "truss_web"
        and waling_line.distance(LineString(member["geometry"]).interpolate(0.5, normalized=True)) <= 4.0
        and 18.0 <= _acute_axis_angle(member) <= 70.0
        and not any(
            LineString(member["geometry"]).intersection(zone).length > 1e-6
            for zone in coverage_zones
        )
    ]
    internal_truss_posts = [
        member for member in layout["members"]
        if member["kind"] == "truss_web"
        and member.get("corner_role") != "leg"
        and waling_line.distance(LineString(member["geometry"]).interpolate(0.5, normalized=True)) > 4.0
        and _point_inside_middle_band(LineString(member["geometry"]).interpolate(0.5, normalized=True), bounds)
    ]

    assert len(edge_diagonal_webs) >= 8
    assert internal_truss_posts == []


def test_large_brace_perimeter_truss_wraps_all_four_edges() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)

    assert len(_large_brace_outer_edge_chords(layout)) >= 4
    for start, end in zip(layout["waling"], layout["waling"][1:]):
        edge = LineString([start, end])
        if edge.length <= 1e-9:
            continue
        assert any(
            member["kind"] == "truss_chord"
            and edge.distance(LineString(member["geometry"]).interpolate(0.5, normalized=True)) <= 1e-6
            for member in layout["members"]
        )


def test_pillars_are_sparse_and_not_every_truss_node() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_opposite_strut")
    layout = solve_case(case)
    required = _main_and_tie_intersection_points(layout)

    assert required
    assert all(
        any(Point(pillar).distance(Point(point)) <= 0.1 for pillar in layout["pillars"])
        for point in required
    )


def test_dxf_layers() -> None:
    TMP_ROOT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=TMP_ROOT) as tmp:
        base = Path(tmp)
        circular_case = next(case for case in CASES if case.name == "circle_or_ellipse_with_core")
        circular = solve_case(circular_case)
        circular_path = base / "circular.dxf"
        export_strut_dxf(circular_path, circular_case.coords, circular)
        circular_layers = _layer_names(circular_path)
        assert {"RING_STRUT", "RADIAL_STRUT", "CORE_PROTECTION"} <= circular_layers

        truss_case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
        truss = solve_case(truss_case)
        truss_path = base / "truss.dxf"
        export_strut_dxf(truss_path, truss_case.coords, truss)
        truss_layers = _layer_names(truss_path)
        assert {"TRUSS_WEB", "TRUSS_CHORD"} <= truss_layers


def test_visual_diagnostics_export_png() -> None:
    from strut_diagnostics import export_strut_diagnostic_png

    case = next(case for case in CASES if case.name == "large_rect_120x80_opposite_strut")
    layout = solve_case(case)
    TMP_ROOT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=TMP_ROOT) as tmp:
        png_path = Path(tmp) / "large_straight_truss_diagnostic.png"
        export_strut_diagnostic_png(png_path, case.coords, layout, title=case.name)
        assert png_path.exists()
        assert png_path.stat().st_size > 10_000


def run_case(case: Case) -> bool:
    try:
        engine = StrutEngine(case.coords, case.params)
        layout = engine.solve()
        report = validate_layout(layout, engine.params)
    except Exception as exc:
        print(f"\n{case.name}\n  ERROR: {exc}")
        return False

    counts = report["counts"]
    stats = layout["stats"]
    print(f"\n{case.name}")
    print(
        "  counts: "
        f"waling={counts['waling']} corners={counts['corners']} "
        f"struts={counts['struts']} ties={counts['ties']} pillars={counts['pillars']} "
        f"nodes={counts['nodes']} members={counts['members']}"
    )
    print(
        "  stats: "
        f"main={stats['main_strut_length']:.2f} corner={stats['corner_length']:.2f} "
        f"truss_web={stats['truss_web_length']:.2f} tie={stats['tie_length']:.2f} "
        f"ring={stats['ring_strut_length']:.2f} radial={stats['radial_strut_length']:.2f} "
        f"total={stats['total_support_length']:.2f} pillars={stats['pillar_count']}"
    )

    errors = [issue for issue in report["issues"] if issue["severity"] == "error"]
    warnings = [issue for issue in report["issues"] if issue["severity"] == "warning"]
    if not errors:
        print(f"  validation: OK ({len(warnings)} warnings)")
        return True

    print(f"  validation: FAIL ({len(errors)} errors)")
    for issue in errors[:10]:
        print(
            "   - "
            f"{issue['kind']} {issue['member_id']} x {issue['other_member_id']} "
            f"at {issue['point']} reason={issue['reason']}"
        )
    return False


def _layer_names(path: Path) -> set[str]:
    return {layer.dxf.name for layer in ezdxf.readfile(path).layers}


def _minimum_point_spacing(points: list[tuple[float, float]]) -> float:
    if len(points) < 2:
        return inf
    return min(
        Point(left).distance(Point(right))
        for index, left in enumerate(points)
        for right in points[index + 1:]
    )


def _max_perimeter_truss_gap(layout: dict[str, Any]) -> float:
    waling_line = LineString(layout["waling"])
    if waling_line.length <= 1e-9:
        return inf

    positions = [0.0, waling_line.length]
    for member in layout["members"]:
        if member["kind"] not in {"truss_chord", "truss_web"}:
            continue
        line = LineString(member["geometry"])
        if waling_line.distance(line) > 18.0:
            continue
        for point in member["geometry"]:
            projected = waling_line.project(Point(point))
            if waling_line.distance(Point(point)) <= 18.0:
                positions.append(float(projected))
        midpoint = line.interpolate(0.5, normalized=True)
        if waling_line.distance(midpoint) <= 18.0:
            positions.append(float(waling_line.project(midpoint)))

    unique = sorted({round(value, 6) for value in positions})
    if len(unique) < 2:
        return inf
    gaps = [right - left for left, right in zip(unique, unique[1:])]
    return max(gaps)


def _max_outer_chord_gap_by_edge(layout: dict[str, Any]) -> list[float]:
    gaps = []
    waling = layout["waling"]
    for start, end in zip(waling, waling[1:]):
        edge = LineString([start, end])
        if edge.length <= 1e-9:
            continue
        positions = [0.0, edge.length]
        for member in layout["members"]:
            if member["kind"] != "truss_chord":
                continue
            chord = LineString(member["geometry"])
            if edge.distance(chord) > 1e-6:
                continue
            endpoints = member["geometry"][0], member["geometry"][-1]
            if not all(edge.distance(Point(point)) <= 1e-6 for point in endpoints):
                continue
            positions.extend(float(edge.project(Point(point))) for point in endpoints)
        unique = sorted({round(value, 6) for value in positions})
        gaps.append(max(right - left for left, right in zip(unique, unique[1:])))
    return gaps


def _large_brace_outer_edge_chords(layout: dict[str, Any]) -> list[dict[str, Any]]:
    waling_line = LineString(layout["waling"])
    return [
        member for member in layout["members"]
        if member["kind"] == "truss_chord"
        and waling_line.distance(LineString(member["geometry"]).interpolate(0.5, normalized=True)) <= 1e-6
    ]


def _perimeter_web_chain_breaks(layout: dict[str, Any]) -> list[tuple[str, str]]:
    waling_line = LineString(layout["waling"])
    webs = [
        member
        for member in layout["members"]
        if member["kind"] == "truss_web"
        and waling_line.distance(LineString(member["geometry"]).interpolate(0.5, normalized=True)) <= 12.0
    ]
    if len(webs) < 2:
        return []

    breaks = []
    for left, right in zip(webs, webs[1:] + webs[:1]):
        if not _share_endpoint(left, right):
            breaks.append((left["id"], right["id"]))
    return breaks


def _perimeter_web_count_by_edge(layout: dict[str, Any]) -> list[int]:
    edges = [
        LineString([start, end])
        for start, end in zip(layout["waling"], layout["waling"][1:])
        if LineString([start, end]).length > 1e-9
    ]
    counts = [0 for _ in edges]
    for member in layout["members"]:
        if member["kind"] != "truss_web":
            continue
        midpoint = LineString(member["geometry"]).interpolate(0.5, normalized=True)
        nearest = min(range(len(edges)), key=lambda index: edges[index].distance(midpoint))
        if edges[nearest].distance(midpoint) <= 12.0:
            counts[nearest] += 1
    return counts


def _regular_spacing(values: list[float], *, tolerance: float) -> bool:
    if len(values) < 3:
        return True
    gaps = [right - left for left, right in zip(values, values[1:])]
    average = sum(gaps) / len(gaps)
    return all(abs(gap - average) <= tolerance for gap in gaps)


def _max_gap(values: list[float]) -> float:
    if len(values) < 2:
        return inf
    return max(right - left for left, right in zip(values, values[1:]))


def _corner_coverage_zones(layout: dict[str, Any], coverage: float) -> list[Polygon]:
    corners = list(Polygon(layout["waling"]).exterior.coords)[:-1]
    zones = []
    for index, corner in enumerate(corners):
        prev_pt = corners[index - 1]
        next_pt = corners[(index + 1) % len(corners)]
        zones.append(Polygon([
            corner,
            _point_along_test(corner, prev_pt, coverage),
            _point_along_test(corner, next_pt, coverage),
        ]))
    return zones


def _point_along_test(
    start: tuple[float, float],
    target: tuple[float, float],
    distance: float,
) -> tuple[float, float]:
    dx = target[0] - start[0]
    dy = target[1] - start[1]
    length = (dx * dx + dy * dy) ** 0.5
    assert length > 1e-9
    scale = min(distance, length) / length
    return (start[0] + dx * scale, start[1] + dy * scale)


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


def _share_endpoint(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return any(
        Point(left_point).distance(Point(right_point)) <= 1e-6
        for left_point in (left["geometry"][0], left["geometry"][-1])
        for right_point in (right["geometry"][0], right["geometry"][-1])
    )


def _truss_node_points(layout: dict[str, Any]) -> list[tuple[float, float]]:
    return [
        tuple(node["pos"])
        for node in layout["nodes"]
        if "truss_node" in node["kind"] or "waling_point" in node["kind"]
    ]


def _corner_bracket_webs(layout: dict[str, Any], model: dict[str, Any]) -> list[dict[str, Any]]:
    semantic_diagonals = [
        line
        for line in model["semantic_lines"]
        if len(line) == 2
        and LineString(line).length > 1e-6
    ]
    return [
        member
        for member in layout["members"]
        if member["kind"] == "truss_web"
        and any(_same_segment(member["geometry"], semantic_line) for semantic_line in semantic_diagonals)
    ]


def _same_segment(left: list[tuple[float, float]], right: list[tuple[float, float]]) -> bool:
    if len(left) < 2 or len(right) < 2:
        return False
    return (
        Point(left[0]).distance(Point(right[0])) <= 1e-6
        and Point(left[-1]).distance(Point(right[-1])) <= 1e-6
    ) or (
        Point(left[0]).distance(Point(right[-1])) <= 1e-6
        and Point(left[-1]).distance(Point(right[0])) <= 1e-6
    )


def _has_non_endpoint_intersection(
    left: list[tuple[float, float]],
    right: list[tuple[float, float]],
) -> bool:
    inter = LineString(left).intersection(LineString(right))
    if inter.is_empty:
        return False
    if inter.length > 1e-6:
        return True
    points = []
    if inter.geom_type == "Point":
        points = [(float(inter.x), float(inter.y))]
    elif inter.geom_type == "MultiPoint":
        points = [(float(point.x), float(point.y)) for point in inter.geoms]
    for point in points:
        left_endpoint = any(Point(point).distance(Point(endpoint)) <= 1e-6 for endpoint in (left[0], left[-1]))
        right_endpoint = any(Point(point).distance(Point(endpoint)) <= 1e-6 for endpoint in (right[0], right[-1]))
        if not (left_endpoint or right_endpoint):
            return True
    return False


def _main_and_tie_intersection_points(layout: dict[str, Any]) -> list[tuple[float, float]]:
    structural = [
        member for member in layout["members"]
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


def _paired_main_strut_axis_groups(layout: dict[str, Any], *, axis: str) -> list[tuple[float, float]]:
    members = [
        member
        for member in layout["members"]
        if member["kind"] == "main_strut"
        and ((_is_vertical(member) and axis == "x") or (_is_horizontal(member) and axis == "y"))
        and _main_strut_reaches_opposite_waling_sides(layout, member, axis=axis)
    ]
    values = _axis_values(members, axis)
    groups = [group for group in _axis_groups(values, max_pair_gap=8.0) if len(group) >= 2]
    return [(min(group), max(group)) for group in groups]


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


def _pair_has_diagonal_lacing_touching_position(
    layout: dict[str, Any],
    first_axis: float,
    second_axis: float,
    position: float,
    *,
    vertical_pair: bool,
) -> bool:
    for member in layout["members"]:
        if member["kind"] != "tie" or _is_horizontal(member) or _is_vertical(member):
            continue
        start, end = member["geometry"][0], member["geometry"][-1]
        if vertical_pair:
            if {round(start[0], 6), round(end[0], 6)} != {round(first_axis, 6), round(second_axis, 6)}:
                continue
            if round(position, 6) in {round(start[1], 6), round(end[1], 6)}:
                return True
        else:
            if {round(start[1], 6), round(end[1], 6)} != {round(first_axis, 6), round(second_axis, 6)}:
                continue
            if round(position, 6) in {round(start[0], 6), round(end[0], 6)}:
                return True
    return False


def _pair_has_diagonal_lacing_spanning_bay(
    layout: dict[str, Any],
    first_axis: float,
    second_axis: float,
    start_pos: float,
    end_pos: float,
    *,
    vertical_pair: bool,
) -> bool:
    for member in layout["members"]:
        if member["kind"] != "tie" or _is_horizontal(member) or _is_vertical(member):
            continue
        start, end = member["geometry"][0], member["geometry"][-1]
        if vertical_pair:
            if {round(start[0], 6), round(end[0], 6)} != {round(first_axis, 6), round(second_axis, 6)}:
                continue
            if {round(start[1], 6), round(end[1], 6)} == {round(start_pos, 6), round(end_pos, 6)}:
                return True
        else:
            if {round(start[1], 6), round(end[1], 6)} != {round(first_axis, 6), round(second_axis, 6)}:
                continue
            if {round(start[0], 6), round(end[0], 6)} == {round(start_pos, 6), round(end_pos, 6)}:
                return True
    return False


def _pair_lateral_support_positions(
    layout: dict[str, Any],
    first_axis: float,
    second_axis: float,
    *,
    vertical_pair: bool,
) -> list[float]:
    bounds = Polygon(layout["waling"]).bounds
    positions = [bounds[1], bounds[3]] if vertical_pair else [bounds[0], bounds[2]]
    positions.extend(_short_tie_positions_between_pair(
        layout,
        first_axis,
        second_axis,
        vertical_pair=vertical_pair,
    ))
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


def _bay_contains_perpendicular_main_axis(
    layout: dict[str, Any],
    start: float,
    end: float,
    *,
    vertical_pair: bool,
) -> bool:
    lo, hi = sorted((start, end))
    return any(lo < axis < hi for axis in _perpendicular_main_axes_for_pair(layout, vertical_pair=vertical_pair))


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


def _internal_truss_members(layout: dict[str, Any]) -> list[dict[str, Any]]:
    waling_line = LineString(layout["waling"])
    return [
        member
        for member in layout["members"]
        if member["kind"] in {"truss_chord", "truss_web"}
        and member.get("corner_role") != "leg"
        and waling_line.distance(LineString(member["geometry"]).interpolate(0.5, normalized=True)) > 5.0
    ]


def _axis_values(members: list[dict[str, Any]], axis: str) -> list[float]:
    index = 0 if axis == "x" else 1
    return sorted({
        round(member.get("logical_geometry", member["geometry"])[0][index], 6)
        for member in members
    })


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


def _minimum_axis_spacing(members: list[dict[str, Any]], axis: str) -> float:
    values = _axis_values(members, axis)
    if len(values) < 2:
        return inf
    return min(right - left for left, right in zip(values, values[1:]))


def _axis_groups(values: list[float], max_pair_gap: float) -> list[list[float]]:
    groups: list[list[float]] = []
    for value in values:
        if groups and value - groups[-1][-1] <= max_pair_gap:
            groups[-1].append(value)
        else:
            groups.append([value])
    return groups


def _minimum_group_spacing(groups: list[list[float]]) -> float:
    if len(groups) < 2:
        return inf
    return min(right[0] - left[-1] for left, right in zip(groups, groups[1:]))


def _acute_axis_angle(member: dict[str, Any]) -> float:
    start, end = member["geometry"][0], member["geometry"][-1]
    dx = abs(end[0] - start[0])
    dy = abs(end[1] - start[1])
    angle = abs(degrees(atan2(dy, dx)))
    return min(angle, 90.0 - angle)


def _point_inside_middle_band(point: Point, bounds: tuple[float, float, float, float]) -> bool:
    min_x, min_y, max_x, max_y = bounds
    return (
        min_x + (max_x - min_x) * 0.18 < point.x < max_x - (max_x - min_x) * 0.18
        and min_y + (max_y - min_y) * 0.18 < point.y < max_y - (max_y - min_y) * 0.18
    )


def main() -> int:
    print("Internal strut minimal validation")
    passed = 0
    failed = 0
    for case in CASES:
        if run_case(case):
            passed += 1
        else:
            failed += 1
    print(f"\nResult: {passed} passed / {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
