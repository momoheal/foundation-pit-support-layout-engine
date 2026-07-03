"""Validation helpers for internal strut layouts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from shapely.geometry import LineString, Point


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
    issues: list[ValidationIssue] = []

    for i, left in enumerate(refs):
        for right in refs[i + 1:]:
            if frozenset((left.kind, right.kind)) in allowed:
                continue
            inter = left.line.intersection(right.line)
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
        if not any(kind in node.get("kind", "") for kind in ("truss_node", "strut_cross", "ring_radial")):
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
    min_spacing = float(params.get("spacing_min", 6.0))
    max_spacing = float(params.get("spacing_max", 9.0))
    main = [ref for ref in collect_segments(layout) if ref.kind == "main_strut"]
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


def validate_layout(layout: dict[str, Any], params: dict[str, Any] | None = None) -> dict[str, Any]:
    issues = []
    issues.extend(find_illegal_intersections(layout))
    issues.extend(validate_core_protection(layout, params))
    issues.extend(validate_connection_spacing(layout, params))

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
