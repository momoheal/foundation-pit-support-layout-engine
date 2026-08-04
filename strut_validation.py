"""Validation helpers for internal strut layouts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree


LEGACY_SEGMENT_KEYS = ("struts", "corners", "ties")
ALLOWED_CROSSINGS = {
    frozenset(("main_strut", "main_strut")),
    frozenset(("ring_strut", "radial_strut")),
    frozenset(("truss_chord", "truss_web")),
}


@dataclass(frozen=True)
class SegmentRef:
    kind: str
    index: int
    points: tuple[tuple[float, float], ...]
    member_id: str | None = None

    @property
    def line(self) -> LineString:
        return LineString(self.points)


@dataclass(frozen=True)
class ValidationIssue:
    kind: str
    member_id: str | None
    other_member_id: str | None
    point: tuple[float, float] | None
    reason: str
    severity: str = "error"


def collect_segments(layout: dict[str, Any]) -> list[SegmentRef]:
    """Collect member centerlines, falling back to legacy layout fields."""
    refs: list[SegmentRef] = []
    members = layout.get("members") or []
    if members:
        for index, member in enumerate(members):
            kind = member.get("kind", "unknown")
            if kind == "waling":
                continue
            points = tuple((float(x), float(y)) for x, y in member.get("geometry", []))
            if len(points) >= 2 and LineString(points).length > 1e-9:
                refs.append(SegmentRef(kind, index, points, member.get("id")))
        return refs

    legacy_kind = {"struts": "main_strut", "corners": "corner", "ties": "tie"}
    for key in LEGACY_SEGMENT_KEYS:
        for index, segment in enumerate(layout.get(key, [])):
            if len(segment) < 2:
                continue
            points = tuple((float(x), float(y)) for x, y in segment[:2])
            refs.append(SegmentRef(legacy_kind[key], index, points, None))
    return refs


def points_close(a: tuple[float, float], b: tuple[float, float], tol: float = 1e-6) -> bool:
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def is_endpoint(
    point: tuple[float, float],
    segment: tuple[tuple[float, float], ...],
    tol: float = 1e-6,
) -> bool:
    return points_close(point, segment[0], tol) or points_close(point, segment[-1], tol)


def is_connection_point(
    point: tuple[float, float],
    seg_a: tuple[tuple[float, float], ...],
    seg_b: tuple[tuple[float, float], ...],
    tol: float = 1e-6,
) -> bool:
    """Return True when an intersection is a legal node connection."""
    if is_endpoint(point, seg_a, tol) and is_endpoint(point, seg_b, tol):
        return True
    if is_endpoint(point, seg_a, tol) and LineString(seg_b).distance(Point(point)) <= tol:
        return True
    if is_endpoint(point, seg_b, tol) and LineString(seg_a).distance(Point(point)) <= tol:
        return True
    return False


def find_illegal_intersections(
    layout: dict[str, Any],
    allowed_crossings: set[frozenset[str]] | None = None,
    tol: float = 1e-6,
) -> list[ValidationIssue]:
    allowed = allowed_crossings or ALLOWED_CROSSINGS
    refs = collect_segments(layout)
    lines = [ref.line for ref in refs]
    tree = STRtree(lines) if lines else None
    issues: list[ValidationIssue] = []

    for i, left in enumerate(refs):
        assert tree is not None
        for right_index in tree.query(lines[i]):
            right_index = int(right_index)
            if right_index <= i:
                continue
            right = refs[right_index]
            if frozenset((left.kind, right.kind)) in allowed:
                continue
            inter = lines[i].intersection(lines[right_index])
            if inter.is_empty:
                continue
            points = _points_from_intersection(inter)
            if not points and inter.length > tol:
                point = inter.interpolate(0.5, normalized=True)
                points = [(float(point.x), float(point.y))]
            for point in points:
                if is_connection_point(point, left.points, right.points, tol):
                    continue
                if has_explicit_connection_node(layout, point, left, right, tol):
                    continue
                issues.append(ValidationIssue(
                    left.kind,
                    left.member_id,
                    right.member_id,
                    point,
                    "non_endpoint_intersection",
                ))
    return issues


def has_explicit_connection_node(
    layout: dict[str, Any],
    point: tuple[float, float],
    left: SegmentRef,
    right: SegmentRef,
    tol: float,
) -> bool:
    if left.member_id is None or right.member_id is None:
        return False
    member_ids = {left.member_id, right.member_id}
    for node in layout.get("nodes", []):
        pos = node.get("pos")
        if pos is None or not points_close((float(pos[0]), float(pos[1])), point, tol):
            continue
        if not any(kind in node.get("kind", "") for kind in ("truss_node", "strut_cross", "ring_radial", "tie_end")):
            continue
        if member_ids <= set(node.get("source", [])):
            return True
    return False


def validate_core_protection(
    layout: dict[str, Any],
    params: dict[str, Any] | None,
) -> list[ValidationIssue]:
    if not params or params.get("support_system") != "circular":
        return []
    center = params.get("core_center")
    diameter = params.get("core_diameter")
    if center is None or diameter is None:
        return []

    core = Point(center).buffer(float(diameter) / 2.0)
    issues: list[ValidationIssue] = []
    for ref in collect_segments(layout):
        if ref.kind in {"ring_strut", "waling"}:
            continue
        line = ref.line
        if line.crosses(core) or line.within(core) or line.overlaps(core) or core.contains(line):
            point = line.interpolate(0.5, normalized=True)
            issues.append(ValidationIssue(
                ref.kind,
                ref.member_id,
                None,
                (float(point.x), float(point.y)),
                "core_protection_intrusion",
            ))
    return issues


def validate_connection_spacing(
    layout: dict[str, Any],
    params: dict[str, Any] | None,
) -> list[ValidationIssue]:
    """Warn when same-axis main strut spacing is outside the recommended range."""
    if not params:
        return []
    if _is_large_brace_layout(layout, params):
        return []
    min_spacing = float(params.get("spacing_min", 6.0))
    max_spacing = float(params.get("spacing_max", 9.0))
    logical_main: dict[str, SegmentRef] = {}
    for ref in collect_segments(layout):
        if ref.kind != "main_strut":
            continue
        member = next(
            (item for item in layout.get("members", []) if item.get("id") == ref.member_id),
            None,
        )
        logical_id = str((member or {}).get("parent_member_id", ref.member_id))
        geometry = (member or {}).get("logical_geometry")
        logical_main.setdefault(
            logical_id,
            SegmentRef(
                "main_strut",
                ref.index,
                tuple((float(x), float(y)) for x, y in geometry) if geometry else ref.points,
                logical_id,
            ),
        )
    main = list(logical_main.values())
    vertical = []
    horizontal = []
    for ref in main:
        p1, p2 = ref.points[0], ref.points[-1]
        if abs(p1[0] - p2[0]) <= abs(p1[1] - p2[1]):
            vertical.append((p1[0], ref))
        else:
            horizontal.append((p1[1], ref))

    issues: list[ValidationIssue] = []
    for values in (vertical, horizontal):
        values.sort(key=lambda item: item[0])
        for (left_value, left), (right_value, right) in zip(values, values[1:]):
            spacing = abs(right_value - left_value)
            if spacing < min_spacing * 0.75 or spacing > max_spacing * 1.35:
                issues.append(ValidationIssue(
                    left.kind,
                    left.member_id,
                    right.member_id,
                    None,
                    f"connection_spacing_out_of_range:{spacing:.3f}",
                    "warning",
                ))
    return issues


def validate_member_bounds(
    layout: dict[str, Any],
    params: dict[str, Any] | None,
) -> list[ValidationIssue]:
    _ = params
    if not layout.get("waling"):
        return []
    boundary = Polygon(layout["waling"])
    if boundary.is_empty or not boundary.is_valid:
        return [ValidationIssue("waling", None, None, None, "invalid_waling")]
    issues: list[ValidationIssue] = []
    for ref in collect_segments(layout):
        if not boundary.buffer(1e-6).covers(ref.line):
            midpoint = ref.line.interpolate(0.5, normalized=True)
            issues.append(ValidationIssue(
                ref.kind,
                ref.member_id,
                None,
                (float(midpoint.x), float(midpoint.y)),
                "member_outside_waling",
            ))
    return issues


def validate_member_endpoint_anchors(
    layout: dict[str, Any],
    params: dict[str, Any] | None,
) -> list[ValidationIssue]:
    tol = float((params or {}).get("node_snap_tolerance", 1e-3))
    nodes = {str(node.get("id")): node for node in layout.get("nodes", [])}
    issues: list[ValidationIssue] = []
    for member in layout.get("members", []):
        geometry = member.get("geometry", [])
        if len(geometry) < 2:
            continue
        invalid = False
        for key, point in (("start", geometry[0]), ("end", geometry[-1])):
            node = nodes.get(str(member.get(key)))
            if node is None or Point(node["pos"]).distance(Point(point)) > tol:
                invalid = True
                break
            if str(member.get("id")) not in {str(source) for source in node.get("source", [])}:
                invalid = True
                break
        if invalid:
            issues.append(ValidationIssue(
                str(member.get("kind", "unknown")),
                str(member.get("id")),
                None,
                (float(geometry[0][0]), float(geometry[0][1])),
                "member_endpoint_unanchored",
            ))
    return issues


def validate_structural_connectivity(
    layout: dict[str, Any],
    params: dict[str, Any] | None,
) -> list[ValidationIssue]:
    _ = params
    members = layout.get("members", [])
    adjacency: dict[str, set[str]] = {}
    seeds: set[str] = set()
    for member in members:
        start, end = str(member.get("start")), str(member.get("end"))
        adjacency.setdefault(start, set()).add(end)
        adjacency.setdefault(end, set()).add(start)
        if member.get("kind") == "waling":
            seeds.update((start, end))
    if not seeds:
        return [ValidationIssue("waling", None, None, None, "waling_graph_missing")]
    reachable = set(seeds)
    pending = list(seeds)
    while pending:
        node = pending.pop()
        for neighbour in adjacency.get(node, set()):
            if neighbour not in reachable:
                reachable.add(neighbour)
                pending.append(neighbour)
    return [
        ValidationIssue(
            str(member.get("kind", "unknown")),
            str(member.get("id")),
            None,
            None,
            "structural_component_not_waling_reachable",
        )
        for member in members
        if str(member.get("start")) not in reachable or str(member.get("end")) not in reachable
    ]


def validate_large_brace_topology(
    layout: dict[str, Any],
    params: dict[str, Any] | None,
) -> list[ValidationIssue]:
    if not params or params.get("support_system") != "brace" or not layout.get("waling"):
        return []
    min_x, min_y, max_x, max_y = Polygon(layout["waling"]).bounds
    if max_x - min_x < 100.0 or max_y - min_y < 60.0:
        return []
    logical: dict[str, list[tuple[float, float]]] = {}
    for member in layout.get("members", []):
        if member.get("kind") != "main_strut":
            continue
        logical.setdefault(
            str(member.get("parent_member_id", member.get("id"))),
            [(float(x), float(y)) for x, y in member.get("logical_geometry", member["geometry"])],
        )
    vertical = sorted({round(points[0][0], 6) for points in logical.values() if abs(points[0][0] - points[-1][0]) <= 1e-6})
    horizontal = sorted({round(points[0][1], 6) for points in logical.values() if abs(points[0][1] - points[-1][1]) <= 1e-6})
    pair_gaps: list[float] = []
    if len(vertical) == 4:
        pair_gaps.extend((vertical[1] - vertical[0], vertical[3] - vertical[2]))
    if len(horizontal) == 2:
        pair_gaps.append(horizontal[1] - horizontal[0])
    if len(vertical) == 4 and len(horizontal) == 2 and all(6.0 - 1e-6 <= gap <= 8.0 + 1e-6 for gap in pair_gaps):
        return []
    return [ValidationIssue(
        "main_strut",
        None,
        None,
        None,
        f"large_brace_main_group_topology:vertical={len(vertical)},horizontal={len(horizontal)}",
    )]


def validate_large_brace_clearance(
    layout: dict[str, Any],
    params: dict[str, Any] | None,
) -> list[ValidationIssue]:
    if not params or params.get("support_system") != "brace" or not layout.get("waling"):
        return []
    min_x, min_y, max_x, max_y = Polygon(layout["waling"]).bounds
    if max_x - min_x < 100.0 or max_y - min_y < 60.0:
        return []

    important = [
        node for node in layout.get("nodes", [])
        if "strut_cross" in str(node.get("kind", ""))
        and "tie_end" not in str(node.get("kind", ""))
    ]
    issues: list[ValidationIssue] = []
    for index, left in enumerate(important):
        for right in important[index + 1:]:
            distance = Point(left["pos"]).distance(Point(right["pos"]))
            if distance < 3.0 - 1e-6:
                issues.append(ValidationIssue(
                    "node",
                    None,
                    None,
                    (float(left["pos"][0]), float(left["pos"][1])),
                    f"important_node_clearance_below_3m:{distance:.3f}",
                ))

    logical: dict[str, tuple[str, LineString]] = {}
    for member in layout.get("members", []):
        if member.get("kind") not in {"main_strut", "tie", "corner"}:
            continue
        logical_id = str(member.get("parent_member_id", member.get("id")))
        geometry = member.get("logical_geometry", member.get("geometry", []))
        if len(geometry) >= 2:
            logical.setdefault(logical_id, (str(member["kind"]), LineString(geometry)))
    items = list(logical.items())
    for index, (left_id, (left_kind, left)) in enumerate(items):
        left_dx = left.coords[-1][0] - left.coords[0][0]
        left_dy = left.coords[-1][1] - left.coords[0][1]
        for right_id, (right_kind, right) in items[index + 1:]:
            if left_kind != right_kind:
                continue
            right_dx = right.coords[-1][0] - right.coords[0][0]
            right_dy = right.coords[-1][1] - right.coords[0][1]
            scale = max(left.length * right.length, 1e-9)
            if abs(left_dx * right_dy - left_dy * right_dx) / scale > 1e-6:
                continue
            distance = left.distance(right)
            if distance < 3.0 - 1e-6:
                issues.append(ValidationIssue(
                    left_kind,
                    left_id,
                    right_id,
                    None,
                    f"parallel_member_clearance_below_3m:{distance:.3f}",
                ))
    return issues


def validate_perimeter_truss_continuity(
    layout: dict[str, Any],
    params: dict[str, Any] | None,
) -> list[ValidationIssue]:
    if not params or params.get("support_system") not in {"brace", "straight_truss"}:
        return []
    if not layout.get("waling"):
        return []

    waling_line = LineString(layout["waling"])
    if waling_line.length <= 1e-9:
        return []

    truss_refs = [
        ref for ref in collect_segments(layout)
        if ref.kind in {"truss_chord", "truss_web"}
    ]
    if not truss_refs:
        if params.get("support_system") == "brace":
            return []
        return [ValidationIssue(
            "truss_chord",
            None,
            None,
            None,
            "perimeter_truss_missing",
            "error",
        )]

    if _is_large_brace_layout(layout, params):
        panel_max = float(params.get("truss_panel_max", params.get("spacing_max", 9.0)))
        max_gap = _max_discrete_edge_truss_station_gap(layout)
        if max_gap <= panel_max + 1e-6:
            return []
        return [ValidationIssue(
            "truss_web",
            None,
            None,
            None,
            f"edge_truss_panel_gap:{max_gap:.3f}",
            "warning",
        )]

    max_gap = _max_perimeter_truss_gap(layout, params)
    panel_max = float(params.get("truss_panel_max", params.get("spacing_max", 9.0)))
    if max_gap > panel_max + 1e-6:
        point = waling_line.interpolate(min(max_gap / 2.0, waling_line.length), normalized=False)
        return [ValidationIssue(
            "truss_chord",
            None,
            None,
            (float(point.x), float(point.y)),
            f"perimeter_truss_gap:{max_gap:.3f}",
            "warning",
        )]
    return []


def validate_edge_truss_corner_topology(
    layout: dict[str, Any],
    params: dict[str, Any] | None,
) -> list[ValidationIssue]:
    if not params or params.get("support_system") not in {"brace", "straight_truss"}:
        return []
    if not layout.get("waling"):
        return []

    tolerance = 1e-6
    waling = LineString(layout["waling"])
    logical: dict[str, dict[str, Any]] = {}
    for member in layout.get("members", []):
        logical_id = str(member.get("parent_member_id", member.get("id")))
        if logical_id in logical:
            continue
        record = dict(member)
        record["id"] = logical_id
        record["geometry"] = member.get("logical_geometry", member.get("geometry", []))
        logical[logical_id] = record

    issues: list[ValidationIssue] = []
    for member in logical.values():
        geometry = member.get("geometry", [])
        if len(geometry) < 2:
            continue
        line = LineString(geometry)
        if (
            member.get("kind") == "truss_chord"
            and waling.buffer(tolerance).covers(line)
        ):
            issues.append(ValidationIssue(
                "truss_chord",
                str(member["id"]),
                None,
                None,
                "edge_truss_outer_chord_duplicates_waling",
            ))

        role = str(member.get("corner_role", ""))
        if role == "tier_2" and member.get("corner_inner_common") is not None:
            common = Point(member["corner_inner_common"])
            if line.distance(common) > tolerance:
                issues.append(ValidationIssue(
                    str(member.get("kind", "truss_web")),
                    str(member["id"]),
                    None,
                    (float(common.x), float(common.y)),
                    "corner_tier_2_misses_inner_common",
                ))
        if role.endswith("_perpendicular_web") and member.get("previous_waling_anchor") is not None:
            anchor = Point(member["previous_waling_anchor"])
            if line.distance(anchor) > tolerance or waling.distance(anchor) > tolerance:
                issues.append(ValidationIssue(
                    str(member.get("kind", "truss_web")),
                    str(member["id"]),
                    None,
                    (float(anchor.x), float(anchor.y)),
                    "corner_tier_web_misses_previous_waling_anchor",
                ))

    assemblies: dict[str, list[dict[str, Any]]] = {}
    for member in logical.values():
        assembly = member.get("belongs_to_corner_bracket")
        if assembly is not None:
            assemblies.setdefault(str(assembly), []).append(member)
    for assembly, members in assemblies.items():
        for index, left in enumerate(members):
            left_geometry = left.get("geometry", [])
            if len(left_geometry) < 2:
                continue
            left_line = LineString(left_geometry)
            left_dx = left_line.coords[-1][0] - left_line.coords[0][0]
            left_dy = left_line.coords[-1][1] - left_line.coords[0][1]
            for right in members[index + 1:]:
                right_geometry = right.get("geometry", [])
                if len(right_geometry) < 2:
                    continue
                right_line = LineString(right_geometry)
                if left_line.equals(right_line):
                    issues.append(ValidationIssue(
                        str(left.get("kind", "truss_web")),
                        str(left["id"]),
                        str(right["id"]),
                        None,
                        f"corner_member_clutter:duplicate:{assembly}",
                    ))
                    continue
                right_dx = right_line.coords[-1][0] - right_line.coords[0][0]
                right_dy = right_line.coords[-1][1] - right_line.coords[0][1]
                scale = max(left_line.length * right_line.length, tolerance)
                if abs(left_dx * right_dy - left_dy * right_dx) / scale > tolerance:
                    continue
                distance = left_line.distance(right_line)
                if tolerance < distance < 3.0 - tolerance:
                    issues.append(ValidationIssue(
                        str(left.get("kind", "truss_web")),
                        str(left["id"]),
                        str(right["id"]),
                        None,
                        f"corner_member_clutter:close_parallel:{assembly}:{distance:.3f}",
                    ))
    return issues


def validate_excavation_boundary_clearance(
    layout: dict[str, Any],
    params: dict[str, Any] | None,
) -> list[ValidationIssue]:
    if not params or not params.get("excavation_coords"):
        return []
    boundary = Polygon(params["excavation_coords"]).boundary
    issues: list[ValidationIssue] = []
    for ref in collect_segments(layout):
        if ref.kind != "main_strut":
            continue
        overlap = ref.line.intersection(boundary)
        if overlap.is_empty or overlap.length <= 1e-6:
            continue
        point = ref.line.interpolate(0.5, normalized=True)
        issues.append(ValidationIssue(
            ref.kind,
            ref.member_id,
            None,
            (float(point.x), float(point.y)),
            "member_overlaps_excavation_boundary",
            "error",
        ))
    return issues


def validate_conversion_endpoints(layout: dict[str, Any]) -> list[ValidationIssue]:
    nodes = [tuple(node["pos"]) for node in layout.get("nodes", [])]
    issues: list[ValidationIssue] = []
    for member in layout.get("members", []):
        if not member.get("conversion_group"):
            continue
        for endpoint in (member["geometry"][0], member["geometry"][-1]):
            if any(points_close(endpoint, node) for node in nodes):
                continue
            issues.append(ValidationIssue(
                str(member.get("kind", "unknown")),
                str(member.get("id")),
                None,
                (float(endpoint[0]), float(endpoint[1])),
                "conversion_endpoint_unregistered",
                "error",
            ))
    return issues


def validate_layout(layout: dict[str, Any], params: dict[str, Any] | None = None) -> dict[str, Any]:
    issues = []
    issues.extend(validate_member_bounds(layout, params))
    issues.extend(validate_member_endpoint_anchors(layout, params))
    issues.extend(validate_conversion_endpoints(layout))
    issues.extend(validate_excavation_boundary_clearance(layout, params))
    issues.extend(validate_structural_connectivity(layout, params))
    issues.extend(validate_large_brace_topology(layout, params))
    issues.extend(validate_large_brace_clearance(layout, params))
    issues.extend(find_illegal_intersections(layout))
    issues.extend(validate_core_protection(layout, params))
    issues.extend(validate_connection_spacing(layout, params))
    issues.extend(validate_perimeter_truss_continuity(layout, params))
    issues.extend(validate_edge_truss_corner_topology(layout, params))

    issue_dicts = [asdict(issue) for issue in issues]
    return {
        "ok": not any(issue["severity"] == "error" for issue in issue_dicts),
        "issues": issue_dicts,
        "counts": {key: len(layout.get(key, [])) for key in (
            "waling",
            "corners",
            "struts",
            "ties",
            "pillars",
            "nodes",
            "members",
            "outlines",
        )},
        "stats": layout.get("stats", {}),
    }


def _max_discrete_edge_truss_station_gap(layout: dict[str, Any]) -> float:
    logical: dict[str, dict[str, Any]] = {}
    for member in layout.get("members", []):
        logical_id = str(member.get("parent_member_id", member.get("id")))
        if logical_id in logical:
            continue
        record = dict(member)
        record["geometry"] = member.get("logical_geometry", member.get("geometry", []))
        logical[logical_id] = record

    gaps: list[float] = []
    for edge_index, (start, end) in enumerate(
        zip(layout["waling"], layout["waling"][1:]),
        start=1,
    ):
        edge = LineString([start, end])
        positions = [0.0, edge.length]
        for member in logical.values():
            geometry = member.get("geometry", [])
            if len(geometry) < 2:
                continue
            if (
                member.get("edge_truss_id") == f"edge_truss_{edge_index}"
                and member.get("edge_role") == "web"
            ):
                positions.extend(
                    float(edge.project(Point(point)))
                    for point in (geometry[0], geometry[-1])
                )
            if str(member.get("corner_role", "")).startswith("tier_"):
                positions.extend(
                    float(edge.project(Point(point)))
                    for point in (geometry[0], geometry[-1])
                    if edge.distance(Point(point)) <= 1e-6
                )
        unique = sorted({round(position, 6) for position in positions})
        gaps.extend(right - left for left, right in zip(unique, unique[1:]))
    return max(gaps, default=float("inf"))


def _points_from_intersection(geom: Any) -> list[tuple[float, float]]:
    if geom.is_empty:
        return []
    if geom.geom_type == "Point":
        return [(float(geom.x), float(geom.y))]
    if geom.geom_type == "MultiPoint":
        return [(float(point.x), float(point.y)) for point in geom.geoms]
    if geom.geom_type == "GeometryCollection":
        points = []
        for part in geom.geoms:
            points.extend(_points_from_intersection(part))
        return points
    return []


def _max_perimeter_truss_gap(layout: dict[str, Any], params: dict[str, Any]) -> float:
    waling_line = LineString(layout["waling"])
    if waling_line.length <= 1e-9:
        return float("inf")

    search_band = max(
        float(params.get("truss_depth", 0.8)) * 4.0,
        float(params.get("truss_panel_max", params.get("spacing_max", 9.0))) * 1.5,
    )
    positions = [0.0, waling_line.length]
    for ref in collect_segments(layout):
        if ref.kind not in {"truss_chord", "truss_web"}:
            continue
        if waling_line.distance(ref.line) > search_band:
            continue
        for point in ref.points:
            point_geom = Point(point)
            if waling_line.distance(point_geom) <= search_band:
                positions.append(float(waling_line.project(point_geom)))
        midpoint = ref.line.interpolate(0.5, normalized=True)
        if waling_line.distance(midpoint) <= search_band:
            positions.append(float(waling_line.project(midpoint)))

    unique = sorted({round(value, 6) for value in positions})
    if len(unique) < 2:
        return float("inf")
    return max(right - left for left, right in zip(unique, unique[1:]))


def _is_large_brace_layout(layout: dict[str, Any], params: dict[str, Any]) -> bool:
    if params.get("support_system") != "brace" or not layout.get("waling"):
        return False
    min_x, min_y, max_x, max_y = Polygon(layout["waling"]).bounds
    return max_x - min_x >= 100.0 and max_y - min_y >= 60.0
