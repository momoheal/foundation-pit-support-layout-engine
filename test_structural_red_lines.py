"""P0 regression tests for the current structural-topology contract."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from shapely.geometry import LineString, Point, Polygon

from strut_engine import StrutEngine
from strut_validation import validate_layout


COORDS = [(0.0, 0.0), (120.0, 0.0), (120.0, 80.0), (0.0, 80.0)]
PARAMS: dict[str, Any] = {
    "support_system": "brace",
    "spacing": 12.0,
    "spacing_min": 8.0,
    "spacing_max": 14.0,
    "waling_offset": 5.0,
    "safe_dist": 2.5,
    "truss_depth": 1.2,
    "truss_panel_min": 8.0,
    "truss_panel_max": 12.0,
}


def _layout() -> dict[str, Any]:
    return StrutEngine(COORDS, PARAMS).solve()


def _endpoint(member: dict[str, Any], key: str) -> tuple[float, float]:
    return tuple(member["geometry"][0 if key == "start" else -1])


def _is_shared_node(layout: dict[str, Any], left: dict[str, Any], right: dict[str, Any], point: tuple[float, float]) -> bool:
    ids = {left["id"], right["id"]}
    return any(
        ids <= set(node.get("source", []))
        and Point(node["pos"]).distance(Point(point)) <= 1e-6
        and _endpoint(left, "start") == tuple(node["pos"])
        or ids <= set(node.get("source", []))
        and Point(node["pos"]).distance(Point(point)) <= 1e-6
        for node in layout["nodes"]
    )


def test_p0_corner_assemblies_use_setback_waling_anchors() -> None:
    layout = _layout()
    waling = Polygon(layout["waling"])
    corners = list(waling.exterior.coords)[:-1]
    corner_members = [
        member for member in layout["members"]
        if member.get("corner_role") in {"leg", "corner_lattice"}
    ]
    assert corner_members
    groups = {member["belongs_to_corner_bracket"] for member in corner_members}
    assert len(groups) == 4
    for group in groups:
        points = {
            tuple(endpoint)
            for member in corner_members
            if member["belongs_to_corner_bracket"] == group
            for endpoint in (member["geometry"][0], member["geometry"][-1])
        }
        assert all(
            not any(Point(point).distance(Point(corner)) <= 1e-6 for corner in corners)
            for point in points
        )
        boundary_anchors = [point for point in points if waling.exterior.distance(Point(point)) <= 1e-6]
        assert len(boundary_anchors) == 2


def test_p0_intended_intersections_are_planarized() -> None:
    layout = _layout()
    main = [member for member in layout["members"] if member["kind"] == "main_strut"]
    ties = [member for member in layout["members"] if member["kind"] == "tie"]
    intersections = 0
    for left in main:
        for right in ties:
            inter = LineString(left["geometry"]).intersection(LineString(right["geometry"]))
            if inter.geom_type != "Point":
                continue
            intersections += 1
            point = (float(inter.x), float(inter.y))
            assert any(Point(point).distance(Point(endpoint)) <= 1e-6 for endpoint in left["geometry"])
            assert any(Point(point).distance(Point(endpoint)) <= 1e-6 for endpoint in right["geometry"])
            node_ids = {
                node["id"]
                for node in layout["nodes"]
                if Point(node["pos"]).distance(Point(point)) <= 1e-6
            }
            assert node_ids & {left["start"], left["end"]}
            assert node_ids & {right["start"], right["end"]}
    assert intersections > 0


def test_p0_structural_graph_is_waling_reachable() -> None:
    layout = _layout()
    adjacency: dict[str, set[str]] = defaultdict(set)
    waling_nodes: set[str] = set()
    for member in layout["members"]:
        start, end = str(member["start"]), str(member["end"])
        adjacency[start].add(end)
        adjacency[end].add(start)
        if member["kind"] == "waling":
            waling_nodes.update((start, end))
    reachable = set(waling_nodes)
    pending = list(waling_nodes)
    while pending:
        node = pending.pop()
        for neighbour in adjacency[node]:
            if neighbour not in reachable:
                reachable.add(neighbour)
                pending.append(neighbour)
    unreachable = [member["id"] for member in layout["members"] if member["start"] not in reachable or member["end"] not in reachable]
    assert not unreachable, unreachable


def test_p0_large_brace_has_required_paired_main_groups() -> None:
    layout = _layout()
    logical: dict[str, list[tuple[float, float]]] = {}
    for member in layout["members"]:
        if member["kind"] != "main_strut":
            continue
        logical.setdefault(
            str(member.get("parent_member_id", member["id"])),
            list(member.get("logical_geometry", member["geometry"])),
        )
    vertical = sorted({round(points[0][0], 6) for points in logical.values() if abs(points[0][0] - points[-1][0]) <= 1e-6})
    horizontal = sorted({round(points[0][1], 6) for points in logical.values() if abs(points[0][1] - points[-1][1]) <= 1e-6})

    assert len(vertical) == 4
    assert len(horizontal) == 2
    assert 6.0 <= vertical[1] - vertical[0] <= 8.0
    assert 6.0 <= vertical[3] - vertical[2] <= 8.0
    assert 6.0 <= horizontal[1] - horizontal[0] <= 8.0


def test_p0_corner_lattice_does_not_overlap_edge_web_zone() -> None:
    engine = StrutEngine(COORDS, PARAMS)
    layout = engine.solve()
    model = engine._large_brace_corner_anchor_model(layout, Polygon(layout["waling"]))
    for corner in model["corners"]:
        zone = Polygon([corner["corner"], corner["prev_anchor"], corner["next_anchor"]])
        edge_webs = [
            member for member in layout["members"]
            if member["kind"] == "truss_web"
            and member.get("belongs_to_corner_bracket") == corner["assembly_id"]
            and member.get("corner_role") == "edge_panel"
        ]
        assert edge_webs
        assert all(LineString(member["geometry"]).intersection(zone).length <= 1e-6 for member in edge_webs)


def test_p0_corner_lattice_members_are_mutually_connected() -> None:
    layout = _layout()
    groups = {
        member["belongs_to_corner_bracket"]
        for member in layout["members"]
        if member.get("corner_role") == "leg"
    }
    for group in groups:
        members = [
            member for member in layout["members"]
            if member.get("belongs_to_corner_bracket") == group
            and member.get("corner_role") == "leg"
        ]
        adjacency: dict[str, set[str]] = defaultdict(set)
        for member in members:
            adjacency[member["start"]].add(member["end"])
            adjacency[member["end"]].add(member["start"])
        reached = {members[0]["start"]}
        pending = list(reached)
        while pending:
            node = pending.pop()
            for neighbour in adjacency[node]:
                if neighbour not in reached:
                    reached.add(neighbour)
                    pending.append(neighbour)
        assert all(member["start"] in reached and member["end"] in reached for member in members)


def test_validator_rejects_unanchored_member_endpoint() -> None:
    layout = _layout()
    layout["members"].append({
        "id": "BROKEN-ENDPOINT",
        "kind": "tie",
        "system": "brace",
        "start": "MISSING",
        "end": "MISSING-2",
        "geometry": [(50.0, 50.0), (55.0, 55.0)],
        "width": 0.2,
        "material": "steel",
    })
    report = validate_layout(layout, PARAMS)
    assert not report["ok"]
    assert any(issue["reason"] == "member_endpoint_unanchored" for issue in report["issues"])


def test_validator_rejects_member_outside_waling() -> None:
    layout = _layout()
    layout["members"].append({
        "id": "BROKEN-BOUNDS",
        "kind": "tie",
        "system": "brace",
        "start": layout["members"][0]["start"],
        "end": layout["members"][0]["end"],
        "geometry": [(200.0, 200.0), (210.0, 210.0)],
        "width": 0.2,
        "material": "steel",
    })
    report = validate_layout(layout, PARAMS)
    assert not report["ok"]
    assert any(issue["reason"] == "member_outside_waling" for issue in report["issues"])


def test_validator_rejects_wrong_large_brace_main_group_count() -> None:
    layout = _layout()
    first_parent = next(
        str(member.get("parent_member_id", member["id"]))
        for member in layout["members"]
        if member["kind"] == "main_strut"
    )
    layout["members"] = [
        member for member in layout["members"]
        if str(member.get("parent_member_id", member["id"])) != first_parent
    ]
    report = validate_layout(layout, PARAMS)
    assert not report["ok"]
    assert any(issue["reason"].startswith("large_brace_main_group_topology") for issue in report["issues"])
