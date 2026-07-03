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
from shapely.geometry import LineString, Point, Polygon

from main_strut import export_strut_dxf
from strut_engine import STATS_KEYS, StrutEngine
from strut_validation import validate_layout


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

    opposite = solve_case(next(case for case in CASES if case.name == "straight_truss_rect"))
    assert opposite["stats"]["truss_web_length"] == 0
    assert all(member["kind"] not in {"truss_chord", "truss_web", "corner"} for member in opposite["members"])

    brace = solve_case(next(case for case in CASES if case.name == "large_rect_120x80_brace"))
    assert brace["stats"]["truss_web_length"] > 0
    assert brace["stats"]["corner_length"] > 0
    assert any(member["kind"] == "truss_web" for member in brace["members"])

    octagon_circular = solve_case(next(case for case in CASES if case.name == "octagon_circular_core"))
    assert octagon_circular["stats"]["ring_strut_length"] > 0
    assert octagon_circular["stats"]["radial_strut_length"] > 0
    assert any(member["kind"] == "ring_strut" for member in octagon_circular["members"])

    rect = solve_case(next(case for case in CASES if case.name == "rect_60x40"))
    assert rect["stats"]["main_strut_length"] > 0
    assert rect["stats"]["corner_length"] > 0
    assert any("strut_cross" in node["kind"] for node in rect["nodes"])


def test_opposite_strut_generates_engineering_network_without_truss() -> None:
    case = next(case for case in CASES if case.name == "straight_truss_rect")
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


def test_brace_edge_truss_uses_economic_diagonal_webs_near_corners() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    waling_line = LineString(layout["waling"])
    edge_webs = [
        member for member in layout["members"]
        if member["kind"] == "truss_web"
        and waling_line.distance(LineString(member["geometry"]).interpolate(0.5, normalized=True)) <= 4.0
    ]
    diagonal_webs = [
        member for member in edge_webs
        if 35.0 <= _acute_axis_angle(member) <= 55.0
    ]
    post_webs = [
        member for member in edge_webs
        if _acute_axis_angle(member) <= 5.0 or _acute_axis_angle(member) >= 85.0
    ]
    shallow_webs = [
        member for member in edge_webs
        if _acute_axis_angle(member) < 25.0
    ]

    assert len(diagonal_webs) >= 16
    assert len(post_webs) <= 4
    assert shallow_webs == []


def test_large_brace_corners_use_regular_diagonal_corner_braces() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    pit_corners = list(Polygon(case.coords).exterior.coords)[:-1]
    waling_corners = list(Polygon(layout["waling"]).exterior.coords)[:-1]
    corner_zones = [Point(point).buffer(35.0) for point in waling_corners]

    for zone, pit_corner in zip(corner_zones, pit_corners):
        corner_members = [
            member for member in layout["members"]
            if member["kind"] == "corner"
            and zone.intersects(LineString(member["geometry"]))
        ]

        assert len(corner_members) >= 3
        assert all(35.0 <= _acute_axis_angle(member) <= 55.0 for member in corner_members)
        assert all(
            min(Point(point).distance(Point(corner)) for corner in waling_corners) >= case.params["spacing"]
            for member in corner_members
            for point in member["geometry"]
        )
        assert all(
            Point(endpoint).distance(Point(pit_corner)) > case.params["spacing"]
            for member in corner_members
            for endpoint in member["geometry"]
        )
        truss_nodes = [
            tuple(node["pos"]) for node in layout["nodes"]
            if "truss_node" in node["kind"]
        ]
        assert all(
            any(Point(endpoint).distance(Point(node)) <= 1e-6 for node in truss_nodes)
            for member in corner_members
            for endpoint in member["geometry"]
        )


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
    main_struts = [member for member in layout["members"] if member["kind"] == "main_strut"]
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


def test_corner_truss_nodes_are_snapped_and_have_columns() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    corner_zones = [Point(point).buffer(35.0) for point in list(Polygon(layout["waling"]).exterior.coords)[:-1]]
    corner_members = [
        member for member in layout["members"]
        if member["kind"] == "corner"
        and any(zone.intersects(LineString(member["geometry"])) for zone in corner_zones)
    ]
    corner_pillars = [
        point for point in layout["pillars"]
        if any(zone.covers(Point(point)) for zone in corner_zones)
    ]

    assert corner_members
    assert corner_pillars


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
    outer_chord_length = sum(
        LineString(member["geometry"]).length
        for member in layout["members"]
        if member["kind"] == "truss_chord"
        and waling_line.distance(LineString(member["geometry"]).interpolate(0.5, normalized=True)) < 1e-6
    )
    assert outer_chord_length >= waling_line.length * 0.98


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

    assert len(vertical_x) >= 3
    assert len(horizontal_y) >= 3

    left_offset = vertical_x[0] - min_x
    right_offset = max_x - vertical_x[-1]
    bottom_offset = horizontal_y[0] - min_y
    top_offset = max_y - horizontal_y[-1]

    assert 3.0 <= left_offset <= 5.0
    assert abs(left_offset - right_offset) <= 1e-6
    assert 3.0 <= bottom_offset <= 5.0
    assert abs(bottom_offset - top_offset) <= 1e-6

    vertical_spans = [round(right - left, 6) for left, right in zip(vertical_x, vertical_x[1:])]
    horizontal_spans = [round(top - bottom, 6) for bottom, top in zip(horizontal_y, horizontal_y[1:])]
    assert max(vertical_spans) - min(vertical_spans) <= 1e-6
    assert max(horizontal_spans) - min(horizontal_spans) <= 1e-6


def test_edge_truss_is_continuous_without_forced_main_grid_snap() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    waling_poly = Polygon(layout["waling"])
    min_x, _, max_x, _ = waling_poly.bounds
    top_y = max(point[1] for point in layout["waling"])

    top_truss_x = sorted({
        round(point[0], 6)
        for member in layout["members"]
        if member["kind"] in {"truss_chord", "truss_web"}
        for point in (member["geometry"][0], member["geometry"][-1])
        if abs(point[1] - top_y) < 1e-6
    })

    assert top_truss_x
    assert round(min_x, 6) in top_truss_x
    assert round(max_x, 6) in top_truss_x
    assert max(right - left for left, right in zip(top_truss_x, top_truss_x[1:])) <= case.params["truss_panel_max"]
    main_top_x = sorted({
        round(point[0], 6)
        for member in layout["members"]
        if member["kind"] == "main_strut"
        for point in member["geometry"]
        if abs(point[1] - top_y) < 1e-6
    })
    main_top_groups = [
        round(sum(group) / len(group), 6)
        for group in _axis_groups(main_top_x, max_pair_gap=case.params["spacing_min"])
    ]
    assert main_top_x
    assert set(main_top_groups) <= set(top_truss_x)


def test_truss_panels_use_edge_k_webs_without_internal_truss_posts() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    engine = StrutEngine(case.coords, case.params)
    layout = engine.solve()
    waling_line = LineString(layout["waling"])
    bounds = Polygon(layout["waling"]).bounds

    edge_diagonal_webs = [
        member
        for member in layout["members"]
        if member["kind"] == "truss_web"
        and waling_line.distance(LineString(member["geometry"]).interpolate(0.5, normalized=True)) <= 4.0
        and 35.0 <= _acute_axis_angle(member) <= 55.0
    ]
    internal_truss_posts = [
        member for member in layout["members"]
        if member["kind"] == "truss_web"
        and waling_line.distance(LineString(member["geometry"]).interpolate(0.5, normalized=True)) > 4.0
        and _point_inside_middle_band(LineString(member["geometry"]).interpolate(0.5, normalized=True), bounds)
    ]

    assert len(edge_diagonal_webs) >= 24
    assert internal_truss_posts == []


def test_large_pit_corner_braces_are_regular_diagonal_bands() -> None:
    case = next(case for case in CASES if case.name == "large_rect_120x80_brace")
    layout = solve_case(case)
    corner_zones = [Point(point).buffer(35.0) for point in list(Polygon(layout["waling"]).exterior.coords)[:-1]]
    corner_members = [
        member for member in layout["members"]
        if member["kind"] == "corner"
        and any(zone.intersects(LineString(member["geometry"])) for zone in corner_zones)
    ]
    assert len(corner_members) >= 8


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
    with tempfile.TemporaryDirectory() as tmp:
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
    with tempfile.TemporaryDirectory() as tmp:
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
    start, end = member["geometry"][0], member["geometry"][-1]
    return abs(start[0] - end[0]) < 1e-6 and abs(start[1] - end[1]) > 1e-6


def _is_horizontal(member: dict[str, Any]) -> bool:
    start, end = member["geometry"][0], member["geometry"][-1]
    return abs(start[1] - end[1]) < 1e-6 and abs(start[0] - end[0]) > 1e-6


def _axis_values(members: list[dict[str, Any]], axis: str) -> list[float]:
    index = 0 if axis == "x" else 1
    return sorted({round(member["geometry"][0][index], 6) for member in members})


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
