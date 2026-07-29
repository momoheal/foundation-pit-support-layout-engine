"""Geometry engine for foundation pit internal strut layouts.

The engine keeps the legacy drawing fields (``waling``, ``corners``,
``struts``, ``ties`` and ``pillars``) while also producing a node/member model
that validation, statistics and DXF output can use without guessing a member's
meaning from the old bucket names.
"""

from __future__ import annotations

from math import atan2, ceil, cos, degrees, pi, sin
from typing import Any

from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon
from shapely.ops import substring, unary_union
from shapely.strtree import STRtree


Point2D = tuple[float, float]
Geometry = list[Point2D]

SUPPORT_SYSTEMS = {"orthogonal", "brace", "opposite_strut", "straight_truss", "circular"}
STATS_KEYS = (
    "main_strut_length",
    "corner_length",
    "truss_web_length",
    "tie_length",
    "ring_strut_length",
    "radial_strut_length",
    "total_support_length",
    "pillar_count",
)


class StrutEngine:
    """Generate internal support layouts for a closed foundation pit boundary."""

    def __init__(self, coords: list[tuple[float, float]], params: dict[str, Any] | None):
        if len(coords) < 3:
            raise ValueError("pit boundary requires at least 3 points")
        self.coords = [(float(x), float(y)) for x, y in coords]
        if _points_close(self.coords[0], self.coords[-1]):
            self.coords = self.coords[:-1]

        self.poly = Polygon(self.coords)
        if not self.poly.is_valid:
            self.poly = self.poly.buffer(0)
        if self.poly.is_empty:
            raise ValueError("pit boundary is invalid")

        self.params = self._normalize_params(params or {})
        self._node_index: dict[tuple[int, int], str] = {}
        self._node_by_id: dict[str, dict[str, Any]] = {}
        self._node_seq = 1
        self._member_seq = 1
        self._outline_seq = 1

    # ------------------------------------------------------------------
    # Parameter governance
    # ------------------------------------------------------------------

    @staticmethod
    def _defaults() -> dict[str, Any]:
        return {
            "support_system": "orthogonal",
            "spacing_min": 6.0,
            "spacing_max": 9.0,
            "spacing": 9.0,
            "waling_offset": 1.0,
            "safe_dist": 2.5,
            "strut_material": "steel",
            "main_width": 0.8,
            "tie_width": 0.3,
            "waling_width": 0.8,
            "pillar_min_spacing": None,
            "enable_haunch": False,
            "haunch_angle": 35.0,
            "corner_arm": 0.25,
            "corner_layers": 3,
            "corner_truss_tier_count": 3,
            "corner_truss_tier_spacing": None,
            "corner_truss_scale": 1.5,
            "corner_truss_add_rungs": True,
            "corner_truss_max_reach": None,
            "corner_zone_panel_multiplier": 2.5,
            "corner_zone_edge_fraction": 0.3,
            "tie_ratio": [1.0 / 3.0, 2.0 / 3.0],
            "tie_interval": 14.0,
            "max_unbraced_pair_length": None,
            "min_tie_to_strut_clearance": 3.0,
            "min_strut_len": 4.0,
            "core_center": None,
            "core_diameter": None,
            "core_clearance": 2.0,
            "ring_edge_clearance": 8.0,
            "radial_spacing_min": 6.0,
            "radial_spacing_max": 9.0,
            "radial_count": None,
            "truss_depth": 0.8,
            "truss_panel_min": 6.0,
            "truss_panel_max": 9.0,
            "truss_min_span": 40.0,
            "truss_web_with_main": "warren",
            "truss_web_without_main": "k",
            "node_snap_tolerance": 1e-3,
            "min_node_separation": 0.75,
        }

    def _normalize_params(self, raw: dict[str, Any]) -> dict[str, Any]:
        params = self._defaults()
        params.update(raw)

        if "margin" in raw and "waling_offset" not in raw:
            params["waling_offset"] = raw["margin"]
        if "strut_type" in raw and "strut_material" not in raw:
            params["strut_material"] = raw["strut_type"]

        for key in (
            "spacing_min",
            "spacing_max",
            "spacing",
            "waling_offset",
            "safe_dist",
            "main_width",
            "tie_width",
            "waling_width",
            "corner_arm",
            "corner_layers",
            "corner_truss_tier_count",
            "corner_truss_tier_spacing",
            "corner_truss_scale",
            "corner_truss_max_reach",
            "corner_zone_panel_multiplier",
            "corner_zone_edge_fraction",
            "tie_interval",
            "max_unbraced_pair_length",
            "min_tie_to_strut_clearance",
            "min_strut_len",
            "core_clearance",
            "ring_edge_clearance",
            "radial_spacing_min",
            "radial_spacing_max",
            "truss_depth",
            "truss_panel_min",
            "truss_panel_max",
            "truss_min_span",
            "node_snap_tolerance",
            "min_node_separation",
        ):
            if params[key] is not None:
                params[key] = float(params[key])
        if params["pillar_min_spacing"] is None:
            params["pillar_min_spacing"] = params["spacing_min"]
        if params["max_unbraced_pair_length"] is None:
            params["max_unbraced_pair_length"] = max(
                params["truss_panel_max"],
                params["spacing_min"] * 1.5,
            )
        min_corner_reach = params["truss_depth"] * 2.0
        max_corner_reach = params["truss_depth"] * 3.0
        if params["corner_truss_max_reach"] is None:
            params["corner_truss_max_reach"] = max_corner_reach
        else:
            params["corner_truss_max_reach"] = max(
                min_corner_reach,
                min(params["corner_truss_max_reach"], max_corner_reach),
            )
        params["corner_zone_panel_multiplier"] = max(
            1.0,
            min(params["corner_zone_panel_multiplier"], 3.0),
        )
        params["corner_zone_edge_fraction"] = max(
            0.05,
            min(params["corner_zone_edge_fraction"], 0.35),
        )
        params["min_tie_to_strut_clearance"] = max(
            0.0,
            params["min_tie_to_strut_clearance"],
        )
        params["min_node_separation"] = max(
            params["node_snap_tolerance"],
            params["min_node_separation"],
        )
        params["corner_truss_tier_count"] = max(
            1,
            int(round(params["corner_truss_tier_count"])),
        )

        system = str(params["support_system"]).strip()
        if system not in SUPPORT_SYSTEMS:
            allowed = ", ".join(sorted(SUPPORT_SYSTEMS))
            raise ValueError(f"unsupported support_system {system!r}; expected one of {allowed}")
        params["support_system"] = system

        if params["spacing_min"] > params["spacing_max"]:
            raise ValueError("spacing_min must be <= spacing_max")
        if params["spacing"] < params["spacing_min"] or params["spacing"] > params["spacing_max"]:
            params["spacing"] = max(
                params["spacing_min"],
                min(params["spacing"], params["spacing_max"]),
            )

        params["core_clearance"] = max(2.0, params["core_clearance"])
        if system == "circular":
            if params["core_center"] is None:
                raise ValueError("support_system='circular' requires core_center")
            if params["core_diameter"] is None:
                raise ValueError("support_system='circular' requires core_diameter")
            cx, cy = params["core_center"]
            params["core_center"] = (float(cx), float(cy))
            params["core_diameter"] = float(params["core_diameter"])
            if params["core_diameter"] <= 0:
                raise ValueError("core_diameter must be > 0")

        return params

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------

    def solve(self) -> dict[str, Any]:
        layout = self._empty_layout()
        system = self.params["support_system"]

        if system == "orthogonal":
            self.solve_orthogonal(layout)
        elif system == "brace":
            self.solve_brace(layout)
        elif system == "opposite_strut":
            self.solve_opposite_strut(layout)
        elif system == "straight_truss":
            self.solve_straight_truss(layout)
        elif system == "circular":
            self.solve_circular(layout)
        else:  # pragma: no cover - guarded by parameter normalization.
            raise ValueError(f"unsupported support_system {system!r}")

        self._merge_nearby_nodes(layout)
        self._planarize_structural_members(layout)
        self._merge_nearby_nodes(layout)
        self._attach_stats(layout)
        self._attach_validation(layout)
        return layout

    def _empty_layout(self) -> dict[str, Any]:
        return {
            "waling": [],
            "corners": [],
            "struts": [],
            "ties": [],
            "pillars": [],
            "nodes": [],
            "members": [],
            "outlines": [],
            "stats": {key: 0.0 for key in STATS_KEYS},
            "issues": [],
        }

    # ------------------------------------------------------------------
    # Strategy entry points
    # ------------------------------------------------------------------

    def solve_orthogonal(self, layout: dict[str, Any]) -> None:
        waling_poly = self._place_waling(layout)
        struts = self._place_main_struts(layout, waling_poly, include_x=True, include_y=True)
        self._place_single_direction_ties(layout, struts, waling_poly)
        self._place_secondary_perimeter_supports(layout, waling_poly)
        self._place_pillars_from_nodes(layout, waling_poly)

    def solve_brace(self, layout: dict[str, Any]) -> None:
        waling_poly = self._place_waling(layout)
        if self._uses_large_corner_truss(waling_poly):
            struts = self._place_main_struts_avoiding_corner_coverage(layout, waling_poly)
            corner_model = self._place_discrete_edge_trusses(layout, waling_poly)
            self._place_modular_corner_assemblies(layout, waling_poly, corner_model)
            self._place_perimeter_truss_stiffening(layout, waling_poly)
            self._place_truss_coupling_ties(layout, struts, waling_poly)
        else:
            struts = self._place_main_struts(layout, waling_poly, include_x=True, include_y=True)
            self._place_single_direction_ties(layout, struts, waling_poly)
        self._place_secondary_perimeter_supports(layout, waling_poly)
        if self._uses_large_corner_truss(waling_poly):
            pass
        else:
            self._place_corner_struts(layout, waling_poly)
        self._split_truss_members_at_main_crossings(layout)
        self._add_structural_cross_nodes(layout)
        self._place_pillars_from_nodes(layout, waling_poly)

    def solve_opposite_strut(self, layout: dict[str, Any]) -> None:
        waling_poly = self._place_waling(layout)
        struts = self._place_main_struts(layout, waling_poly, include_x=True, include_y=True)
        self._place_single_direction_ties(layout, struts, waling_poly)
        self._place_opposite_strut_y_ties(layout, struts, waling_poly)
        self._split_truss_members_at_main_crossings(layout)
        self._add_structural_cross_nodes(layout)
        self._place_pillars_from_nodes(layout, waling_poly)

    def solve_straight_truss(self, layout: dict[str, Any]) -> None:
        waling_poly = self._place_waling(layout)
        struts = self._place_main_struts(layout, waling_poly, include_x=True, include_y=True)
        corner_model = self._place_discrete_edge_trusses(layout, waling_poly)
        replaced_ids = set(corner_model.get("replaced_main_strut_ids", []))
        struts = [
            item for item in struts
            if str(item["member"]["id"]) not in replaced_ids
        ]
        self._place_modular_corner_assemblies(layout, waling_poly, corner_model)
        self._place_perimeter_truss_stiffening(layout, waling_poly)
        self._place_straight_truss(layout, struts, waling_poly)
        self._place_single_direction_ties(layout, struts, waling_poly)
        self._place_opposite_strut_y_ties(layout, struts, waling_poly)
        self._add_structural_cross_nodes(layout)
        self._place_pillars_from_nodes(layout, waling_poly)

    def solve_circular(self, layout: dict[str, Any]) -> None:
        waling_poly = self._place_waling(layout)
        self._place_inner_ring_system(layout, waling_poly)
        self._place_pillars_from_nodes(layout, waling_poly)

    def _recommend_system(self) -> str:
        """Return a hint only; this value never overrides ``support_system``."""
        area = self.poly.area
        perimeter = self.poly.length
        if perimeter <= 0:
            return "orthogonal"
        circularity = 4.0 * pi * area / (perimeter * perimeter)
        return "circular" if circularity > 0.88 else "orthogonal"

    # ------------------------------------------------------------------
    # Common geometry generation
    # ------------------------------------------------------------------

    def _place_waling(self, layout: dict[str, Any]) -> Polygon:
        waling_poly = self._waling_poly()
        coords = _closed_coords(list(waling_poly.exterior.coords))
        layout["waling"] = coords
        roles = ["waling"]
        if self.params["support_system"] in {"brace", "straight_truss"}:
            roles.append("edge_truss_outer_chord")
        self._add_member(
            layout,
            kind="waling",
            geometry=coords,
            width=self.params["waling_width"],
            node_kind="waling_point",
            closed=True,
            attributes={"structural_roles": roles},
        )
        return waling_poly

    def _place_main_struts(
        self,
        layout: dict[str, Any],
        waling_poly: Polygon,
        *,
        include_x: bool,
        include_y: bool,
    ) -> list[dict[str, Any]]:
        bounds = waling_poly.bounds
        min_len = self.params["min_strut_len"]
        struts: list[dict[str, Any]] = []
        x_grid = self._support_grid_positions(bounds[0], bounds[2])
        y_grid = self._support_grid_positions(bounds[1], bounds[3])

        if include_x:
            for x_val in x_grid:
                line = LineString([(x_val, bounds[1] - self.params["spacing"]), (x_val, bounds[3] + self.params["spacing"])])
                for seg in _unwrap_lines(waling_poly.intersection(line), min_len):
                    member = self._add_linear_member(
                        layout,
                        "main_strut",
                        list(seg.coords),
                        old_key="struts",
                        node_kind="strut_end",
                        )
                    if member is not None:
                        struts.append({"member": member, "axis": "x"})

        if include_y:
            for y_val in y_grid:
                line = LineString([(bounds[0] - self.params["spacing"], y_val), (bounds[2] + self.params["spacing"], y_val)])
                for seg in _unwrap_lines(waling_poly.intersection(line), min_len):
                    member = self._add_linear_member(
                        layout,
                        "main_strut",
                        list(seg.coords),
                        old_key="struts",
                        node_kind="strut_end",
                    )
                    if member is not None:
                        struts.append({"member": member, "axis": "y"})

        self._add_main_strut_cross_nodes(layout)
        return struts

    def _place_main_struts_avoiding_corner_coverage(
        self,
        layout: dict[str, Any],
        waling_poly: Polygon,
    ) -> list[dict[str, Any]]:
        bounds = waling_poly.bounds
        min_len = self.params["min_strut_len"]
        struts: list[dict[str, Any]] = []
        x_grid = self._support_grid_positions(bounds[0], bounds[2])
        y_grid = self._support_grid_positions(bounds[1], bounds[3])
        corner_zone = unary_union(self._corner_coverage_zones(waling_poly, coverage=float(self.params["spacing"]) * 2.5))

        if self._uses_large_corner_truss(waling_poly):
            x_grid, y_grid = self._large_brace_main_strut_axes(bounds, x_grid, y_grid)

        for x_val in x_grid:
            line = LineString([
                (x_val, bounds[1] - self.params["spacing"]),
                (x_val, bounds[3] + self.params["spacing"]),
            ])
            clipped = waling_poly.intersection(line)
            if clipped.intersection(corner_zone).length > 1e-6:
                continue
            for seg in _unwrap_lines(clipped, min_len):
                member = self._add_linear_member(
                    layout,
                    "main_strut",
                    list(seg.coords),
                    old_key="struts",
                    node_kind="strut_end",
                )
                if member is not None:
                    struts.append({"member": member, "axis": "x"})

        for y_val in y_grid:
            line = LineString([
                (bounds[0] - self.params["spacing"], y_val),
                (bounds[2] + self.params["spacing"], y_val),
            ])
            clipped = waling_poly.intersection(line)
            if clipped.intersection(corner_zone).length > 1e-6:
                continue
            for seg in _unwrap_lines(clipped, min_len):
                member = self._add_linear_member(
                    layout,
                    "main_strut",
                    list(seg.coords),
                    old_key="struts",
                    node_kind="strut_end",
                )
                if member is not None:
                    struts.append({"member": member, "axis": "y"})

        self._add_main_strut_cross_nodes(layout)
        return struts

    def _large_brace_main_strut_axes(
        self,
        bounds: tuple[float, float, float, float],
        x_grid: list[float],
        y_grid: list[float],
    ) -> tuple[list[float], list[float]]:
        min_x, min_y, max_x, max_y = bounds
        _ = (x_grid, y_grid)
        pair_gap = max(6.0, min(8.0, float(self.params["spacing_min"])))
        y_center = (min_y + max_y) / 2.0
        spacing = float(self.params["spacing"])

        vertical_centers = [
            min_x + (max_x - min_x) / 3.0,
            min_x + 2.0 * (max_x - min_x) / 3.0,
        ]
        vertical = [
            round(center + offset, 6)
            for center in vertical_centers
            for offset in (-pair_gap / 2.0, pair_gap / 2.0)
        ]
        vertical = [
            value for value in vertical
            if min_x + spacing < value < max_x - spacing
        ]

        horizontal = [
            round(y_center - pair_gap / 2.0, 6),
            round(y_center + pair_gap / 2.0, 6),
        ]
        horizontal = [
            value for value in horizontal
            if min_y + spacing < value < max_y - spacing
        ]
        return vertical, horizontal

    def _corner_coverage_zones(self, waling_poly: Polygon, *, coverage: float) -> list[Polygon]:
        coords = _open_coords(_closed_coords(list(waling_poly.exterior.coords)))
        zones: list[Polygon] = []
        for index, corner in enumerate(coords):
            prev_pt = coords[index - 1]
            next_pt = coords[(index + 1) % len(coords)]
            zone = Polygon([
                corner,
                _point_along(corner, prev_pt, coverage),
                _point_along(corner, next_pt, coverage),
            ])
            if zone.is_valid and not zone.is_empty:
                zones.append(zone)
        return zones

    def _place_discrete_edge_trusses(
        self,
        layout: dict[str, Any],
        waling_poly: Polygon,
    ) -> dict[str, Any]:
        """Build one straight inner chord and middle web field per waling edge."""
        corners = _open_coords(_closed_coords(list(waling_poly.exterior.coords)))
        if len(corners) < 3:
            return {"corners": [], "inner_lines": []}
        centroid = (float(waling_poly.centroid.x), float(waling_poly.centroid.y))
        panel_max = float(self.params["truss_panel_max"])
        configured_spacing = self.params.get("corner_truss_tier_spacing")
        depth = (
            float(configured_spacing)
            if configured_spacing is not None
            else max(
                self._edge_truss_depth(),
                float(self.params["spacing_min"]) * 0.75,
                float(self.params["min_tie_to_strut_clearance"]) * (2.0 ** 0.5),
            )
        )
        requested_tiers = int(self.params["corner_truss_tier_count"])
        inner_lines: list[Geometry] = []

        for index, outer_start in enumerate(corners):
            outer_end = corners[(index + 1) % len(corners)]
            edge_id = f"edge_truss_{index + 1}"
            edge = LineString([outer_start, outer_end])
            if edge.length <= 1e-9:
                inner_lines.append([])
                continue
            inward = _inward_unit_normal(outer_start, outer_end, centroid)
            inner_start = _offset_point(outer_start, inward, depth)
            inner_end = _offset_point(outer_end, inward, depth)
            inner_geometry = [inner_start, inner_end]
            inner_lines.append(inner_geometry)

        replaced_main_strut_ids = {
            str(member["id"])
            for member in layout["members"]
            if member["kind"] == "main_strut"
            and (
                any(
                    _segments_nearly_parallel(member["geometry"], inner_geometry)
                    and LineString(member["geometry"]).distance(LineString(inner_geometry))
                    < float(self.params["min_node_separation"]) - 1e-9
                    for inner_geometry in inner_lines
                    if len(inner_geometry) >= 2
                )
                or any(
                    waling_poly.exterior.distance(Point(endpoint)) <= 1e-6
                    and min(Point(endpoint).distance(Point(corner)) for corner in corners)
                    < requested_tiers * depth - 1e-6
                    for endpoint in (member["geometry"][0], member["geometry"][-1])
                )
            )
        }
        self._remove_layout_members(layout, replaced_main_strut_ids)

        for index, inner_geometry in enumerate(inner_lines):
            if len(inner_geometry) < 2:
                continue
            outer_start = corners[index]
            outer_end = corners[(index + 1) % len(corners)]
            edge_id = f"edge_truss_{index + 1}"
            edge = LineString([outer_start, outer_end])
            inward = _unit_vector(outer_start, inner_geometry[0])
            adjacent_assemblies = [
                f"corner_bracket_{index + 1}",
                f"corner_bracket_{(index + 1) % len(corners) + 1}",
            ]
            self._add_linear_member(
                layout,
                "truss_chord",
                inner_geometry,
                old_key=None,
                node_kind="truss_node",
                attributes={
                    "edge_truss_id": edge_id,
                    "edge_role": "inner_chord",
                    "corner_assemblies": adjacent_assemblies,
                },
            )

            corner_reach = min(requested_tiers * depth, edge.length / 2.0)
            stations = [corner_reach, edge.length - corner_reach]
            for member in layout["members"]:
                if member["kind"] != "main_strut":
                    continue
                for point in (member["geometry"][0], member["geometry"][-1]):
                    if edge.distance(Point(point)) <= 1e-6:
                        distance = edge.project(Point(point))
                        if corner_reach < distance < edge.length - corner_reach:
                            stations.append(distance)
            outer_nodes: list[Point2D] = []
            unique_stations = sorted({round(float(value), 6) for value in stations})
            for left, right in zip(unique_stations, unique_stations[1:]):
                count = max(1, int(ceil((right - left) / panel_max)))
                for step in range(count):
                    distance = left + (right - left) * step / count
                    point = edge.interpolate(distance)
                    candidate = (round(float(point.x), 6), round(float(point.y), 6))
                    if not outer_nodes or not _points_close(outer_nodes[-1], candidate):
                        outer_nodes.append(candidate)
            end_point = edge.interpolate(edge.length - corner_reach)
            outer_nodes.append((round(float(end_point.x), 6), round(float(end_point.y), 6)))
            outer_nodes = self._align_edge_main_anchor_parity(
                layout,
                outer_nodes,
                outer_start,
                outer_end,
            )
            inner_nodes = [_offset_point(point, inward, depth) for point in outer_nodes]
            for panel_index, (outer_a, outer_b, inner_a, inner_b) in enumerate(zip(
                outer_nodes,
                outer_nodes[1:],
                inner_nodes,
                inner_nodes[1:],
            )):
                web = [outer_a, inner_b] if panel_index % 2 == 0 else [inner_a, outer_b]
                covering_main = next((
                    member for member in layout["members"]
                    if member["kind"] == "main_strut"
                    and LineString(member["geometry"]).buffer(1e-6).covers(LineString(web))
                ), None)
                if covering_main is not None:
                    roles = set(covering_main.get("structural_roles", []))
                    roles.add("edge_truss_web")
                    covering_main["structural_roles"] = sorted(roles)
                    covering_main.setdefault("edge_truss_web_segments", []).append(web)
                    covering_main.setdefault("edge_truss_ids", []).append(edge_id)
                    continue
                self._add_linear_member(
                    layout,
                    "truss_web",
                    web,
                    old_key=None,
                    node_kind="truss_node",
                    attributes={
                        "edge_truss_id": edge_id,
                        "edge_role": "web",
                        "truss_primitive": "panel",
                    },
                )

        corner_models: list[dict[str, Any]] = []
        for index, corner in enumerate(corners):
            prev_pt = corners[index - 1]
            next_pt = corners[(index + 1) % len(corners)]
            if not _is_convex_corner(prev_pt, corner, next_pt, waling_poly):
                continue
            prev_inner = inner_lines[index - 1]
            next_inner = inner_lines[index]
            if len(prev_inner) < 2 or len(next_inner) < 2:
                continue
            intersection = LineString(prev_inner).intersection(LineString(next_inner))
            if not isinstance(intersection, Point):
                continue
            corner_models.append({
                "assembly_id": f"corner_bracket_{index + 1}",
                "corner": corner,
                "prev_direction": _unit_vector(corner, prev_pt),
                "next_direction": _unit_vector(corner, next_pt),
                "prev_length": Point(corner).distance(Point(prev_pt)),
                "next_length": Point(corner).distance(Point(next_pt)),
                "prev_inner": prev_inner,
                "next_inner": next_inner,
                "inner_common": (float(intersection.x), float(intersection.y)),
            })
        return {
            "corners": corner_models,
            "inner_lines": inner_lines,
            "depth": depth,
            "replaced_main_strut_ids": sorted(replaced_main_strut_ids),
        }

    def _place_modular_corner_assemblies(
        self,
        layout: dict[str, Any],
        waling_poly: Polygon,
        corner_model: dict[str, Any],
    ) -> None:
        """Place modular waling-to-waling tiers and recurrence webs."""
        _ = waling_poly
        default_spacing = float(corner_model.get("depth", self._edge_truss_depth()))
        configured_spacing = self.params.get("corner_truss_tier_spacing")
        spacing = float(configured_spacing) if configured_spacing is not None else default_spacing
        requested = int(self.params["corner_truss_tier_count"])

        for corner in corner_model.get("corners", []):
            legal_count = int(min(corner["prev_length"], corner["next_length"]) // spacing)
            tier_count = min(requested, legal_count)
            if tier_count < 1:
                continue
            assembly_id = str(corner["assembly_id"])
            vertex = corner["corner"]
            prev_direction = corner["prev_direction"]
            next_direction = corner["next_direction"]
            prev_anchors = [
                _offset_point(vertex, prev_direction, spacing * tier)
                for tier in range(1, tier_count + 1)
            ]
            next_anchors = [
                _offset_point(vertex, next_direction, spacing * tier)
                for tier in range(1, tier_count + 1)
            ]
            for tier, (prev_anchor, next_anchor) in enumerate(
                zip(prev_anchors, next_anchors),
                start=1,
            ):
                tier_geometry = [prev_anchor, next_anchor]
                common_attributes = {
                    "belongs_to_corner_bracket": assembly_id,
                    "corner_role": f"tier_{tier}",
                    "corner_inner_common": corner["inner_common"],
                    "truss_primitive": "corner_tier",
                    "tier_index": tier,
                }
                self._add_linear_member(
                    layout,
                    "truss_web",
                    tier_geometry,
                    old_key=None,
                    node_kind="truss_node",
                    attributes=common_attributes,
                )
                if tier < 3:
                    continue
                tier_line = LineString(tier_geometry)
                for inner_geometry, previous_anchor in (
                    (corner["prev_inner"], prev_anchors[tier - 2]),
                    (corner["next_inner"], next_anchors[tier - 2]),
                ):
                    crossing = tier_line.intersection(LineString(inner_geometry))
                    if not isinstance(crossing, Point):
                        continue
                    crossing_point = (float(crossing.x), float(crossing.y))
                    self._add_linear_member(
                        layout,
                        "truss_web",
                        [crossing_point, previous_anchor],
                        old_key=None,
                        node_kind="truss_node",
                        attributes={
                            "belongs_to_corner_bracket": assembly_id,
                            "corner_role": f"tier_{tier}_perpendicular_web",
                            "truss_primitive": "corner_recurrence_web",
                            "tier_index": tier,
                            "tier_crossing": crossing_point,
                            "previous_waling_anchor": previous_anchor,
                        },
                    )

    def _place_grouped_main_struts(
        self,
        layout: dict[str, Any],
        waling_poly: Polygon,
    ) -> list[dict[str, Any]]:
        bounds = waling_poly.bounds
        min_len = self.params["min_strut_len"]
        pair_gap = max(4.0, min(6.0, float(self.params["spacing_min"]) * 0.6))
        struts: list[dict[str, Any]] = []

        x_span = bounds[2] - bounds[0]
        y_span = bounds[3] - bounds[1]
        x_centers = [bounds[0] + x_span / 3.0, bounds[0] + 2.0 * x_span / 3.0]
        y_centers = [bounds[1] + y_span / 2.0]

        for x_center in x_centers:
            for x_val in (x_center - pair_gap / 2.0, x_center + pair_gap / 2.0):
                line = LineString([
                    (x_val, bounds[1] - self.params["spacing"]),
                    (x_val, bounds[3] + self.params["spacing"]),
                ])
                for seg in _unwrap_lines(waling_poly.intersection(line), min_len):
                    member = self._add_linear_member(
                        layout,
                        "main_strut",
                        list(seg.coords),
                        old_key="struts",
                        node_kind="strut_end",
                    )
                    if member is not None:
                        struts.append({"member": member, "axis": "x"})

        for y_center in y_centers:
            for y_val in (y_center - pair_gap / 2.0, y_center + pair_gap / 2.0):
                line = LineString([
                    (bounds[0] - self.params["spacing"], y_val),
                    (bounds[2] + self.params["spacing"], y_val),
                ])
                for seg in _unwrap_lines(waling_poly.intersection(line), min_len):
                    member = self._add_linear_member(
                        layout,
                        "main_strut",
                        list(seg.coords),
                        old_key="struts",
                        node_kind="strut_end",
                    )
                    if member is not None:
                        struts.append({"member": member, "axis": "y"})

        self._add_main_strut_cross_nodes(layout)
        return struts

    def _place_corner_struts(self, layout: dict[str, Any], waling_poly: Polygon) -> None:
        coords = _open_coords(layout["waling"])
        spacing = self.params["spacing"]
        arm = max(self.params["spacing_min"] * 0.65, spacing * self.params["corner_arm"])

        for index, corner in enumerate(coords):
            prev_pt = coords[index - 1]
            next_pt = coords[(index + 1) % len(coords)]
            left = _point_along(corner, prev_pt, arm)
            right = _point_along(corner, next_pt, arm)
            candidate = [left, right]
            line = LineString(candidate)
            if line.length < 1.0:
                continue
            if not waling_poly.buffer(1e-6).covers(line):
                continue
            if not self._candidate_clear(layout, candidate, {"main_strut", "corner", "tie"}):
                continue
            self._add_linear_member(
                layout,
                "corner",
                candidate,
                old_key="corners",
                node_kind="corner_end",
            )

    def _truss_panel_member_specs(
        self,
        outer_start: Point2D,
        outer_end: Point2D,
        inner_start: Point2D,
        inner_end: Point2D,
        *,
        start_on_outer: bool,
        end_on_outer: bool,
    ) -> list[tuple[str, Geometry]]:
        web_start = outer_start if start_on_outer else inner_start
        web_end = outer_end if end_on_outer else inner_end
        return [
            ("truss_chord", [outer_start, outer_end]),
            ("truss_chord", [inner_start, inner_end]),
            ("truss_web", [web_start, web_end]),
        ]

    def _place_straight_truss(
        self,
        layout: dict[str, Any],
        struts: list[dict[str, Any]],
        waling_poly: Polygon,
    ) -> None:
        vertical = [item for item in struts if item["axis"] == "x"]
        vertical.sort(key=lambda item: _member_midpoint(item["member"])[0])
        if len(vertical) < 2:
            return

        panel = max(
            self.params["truss_panel_min"],
            min(self.params["spacing"], self.params["truss_panel_max"]),
        )
        depth = self.params["truss_depth"]
        for bay_index, (left, right) in enumerate(zip(vertical, vertical[1:])):
            p1, p2 = left["member"]["geometry"][0], left["member"]["geometry"][-1]
            q1, q2 = right["member"]["geometry"][0], right["member"]["geometry"][-1]
            y_low = max(min(p1[1], p2[1]), min(q1[1], q2[1]))
            y_high = min(max(p1[1], p2[1]), max(q1[1], q2[1]))
            unsupported_span = y_high - y_low - 2.0 * float(self.params["waling_offset"])
            if unsupported_span <= max(panel, float(self.params["truss_min_span"])):
                continue
            x_left = p1[0]
            x_right = q1[0]
            x_mid = (x_left + x_right) / 2.0

            for x in (x_mid - depth / 2.0, x_mid + depth / 2.0):
                chord = [(x, y_low), (x, y_high)]
                if waling_poly.buffer(1e-6).covers(LineString(chord)):
                    self._add_linear_member(
                        layout,
                        "truss_chord",
                        chord,
                        old_key=None,
                        node_kind="truss_node",
                    )

            steps = max(1, int(ceil((y_high - y_low) / panel)))
            ys = [y_low + (y_high - y_low) * i / steps for i in range(steps + 1)]
            web_style = (
                self.params["truss_web_with_main"]
                if bay_index == 0
                else self.params["truss_web_without_main"]
            )
            for i in range(steps):
                left_low = (x_mid - depth / 2.0, ys[i])
                left_high = (x_mid - depth / 2.0, ys[i + 1])
                right_low = (x_mid + depth / 2.0, ys[i])
                right_high = (x_mid + depth / 2.0, ys[i + 1])
                webs: list[tuple[Point2D, Point2D]]
                if web_style == "k":
                    mid_y = (ys[i] + ys[i + 1]) / 2.0
                    if i % 2 == 0:
                        mid = (x_mid - depth / 2.0, mid_y)
                        webs = [(mid, right_low), (mid, right_high)]
                    else:
                        mid = (x_mid + depth / 2.0, mid_y)
                        webs = [(mid, left_low), (mid, left_high)]
                else:
                    panel_specs = self._truss_panel_member_specs(
                        left_low,
                        left_high,
                        right_low,
                        right_high,
                        start_on_outer=i % 2 == 0,
                        end_on_outer=i % 2 != 0,
                    )
                    webs = [
                        (spec[1][0], spec[1][-1])
                        for spec in panel_specs
                        if spec[0] == "truss_web"
                    ]
                for truss_web in webs:
                    if waling_poly.buffer(1e-6).covers(LineString(truss_web)):
                        self._add_linear_member(
                            layout,
                            "truss_web",
                            list(truss_web),
                            old_key=None,
                            node_kind="truss_node",
                        )
                if web_style == "k":
                    mid_web = [(x_mid - depth / 2.0, mid_y), (x_mid + depth / 2.0, mid_y)]
                    if waling_poly.buffer(1e-6).covers(LineString(mid_web)):
                        if not self._candidate_clear(layout, mid_web, {"main_strut", "tie"}):
                            continue
                        self._add_linear_member(
                            layout,
                            "truss_web",
                            mid_web,
                            old_key=None,
                            node_kind="truss_node",
                        )
            for y in ys:
                cross_web = [(x_mid - depth / 2.0, y), (x_mid + depth / 2.0, y)]
                if waling_poly.buffer(1e-6).covers(LineString(cross_web)):
                    if not self._candidate_clear(layout, cross_web, {"main_strut", "tie"}):
                        continue
                    self._add_linear_member(
                        layout,
                        "truss_web",
                        cross_web,
                        old_key=None,
                        node_kind="truss_node",
                    )

    def _place_edge_truss(
        self,
        layout: dict[str, Any],
        waling_poly: Polygon,
        *,
        extra_anchor_points: Geometry | None = None,
        avoid_lines: list[Geometry] | None = None,
    ) -> None:
        coords = _open_coords(_closed_coords(list(waling_poly.exterior.coords)))
        centroid = (float(waling_poly.centroid.x), float(waling_poly.centroid.y))
        bounds = waling_poly.bounds
        x_grid = self._support_grid_positions(bounds[0], bounds[2])
        y_grid = self._support_grid_positions(bounds[1], bounds[3])
        _ = (extra_anchor_points, avoid_lines)
        has_corner_handoff = False
        edge_depth = self._edge_truss_depth()
        target_panel = max(
            float(self.params["truss_panel_min"]),
            min(float(self.params["spacing"]), float(self.params["truss_panel_max"])),
        )

        inward_by_edge: list[Point2D] = []
        edge_nodes: list[list[Point2D]] = []

        for start, end in zip(coords, coords[1:] + coords[:1]):
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            length = (dx * dx + dy * dy) ** 0.5
            if length <= 1e-9:
                continue

            normal_a = (-dy / length, dx / length)
            normal_b = (dy / length, -dx / length)
            mid = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
            toward_center = (centroid[0] - mid[0], centroid[1] - mid[1])
            inward = (
                normal_a
                if normal_a[0] * toward_center[0] + normal_a[1] * toward_center[1] >= 0
                else normal_b
            )
            inward_by_edge.append(inward)

            raw_outer_nodes = self._edge_truss_nodes(
                start,
                end,
                x_grid=x_grid,
                y_grid=y_grid,
                target_panel=target_panel,
            )
            outer_nodes = raw_outer_nodes
            outer_nodes = self._merge_edge_main_strut_anchors(
                layout,
                outer_nodes,
                start,
                end,
                extra_anchor_points=extra_anchor_points,
            )
            outer_nodes = self._orient_edge_truss_nodes(outer_nodes, start, end)
            if self._uses_large_corner_truss(waling_poly) and not extra_anchor_points:
                outer_nodes = self._stabilize_corner_adjacent_edge_nodes(outer_nodes, start, end, edge_depth)
            outer_nodes = self._force_even_edge_panel_count(outer_nodes)
            outer_nodes = self._subdivide_edge_truss_panels(outer_nodes, float(self.params["truss_panel_max"]))
            outer_nodes = self._align_edge_main_anchor_parity(layout, outer_nodes, start, end)
            if len(outer_nodes) < 2:
                continue
            edge_nodes.append(outer_nodes)

        if not edge_nodes:
            return

        outer_loop: list[tuple[Point2D, int]] = []
        for edge_index, nodes in enumerate(edge_nodes):
            for node_index, point in enumerate(nodes):
                if not has_corner_handoff and edge_index > 0 and node_index == 0:
                    continue
                if not has_corner_handoff and edge_index == len(edge_nodes) - 1 and node_index == len(nodes) - 1:
                    continue
                outer_loop.append((point, edge_index))
        if len(outer_loop) < 3:
            return

        corner_lookup = {
            (round(point[0], 6), round(point[1], 6)): index
            for index, point in enumerate(coords)
        }
        inner_loop = self._perimeter_truss_inner_nodes(
            outer_loop,
            edge_depth,
            corner_lookup,
            inward_by_edge,
        )
        main_edge_points = [
            endpoint
            for member in layout["members"]
            if member["kind"] == "main_strut"
            for endpoint in (member["geometry"][0], member["geometry"][-1])
            if waling_poly.exterior.distance(Point(endpoint)) <= 1e-6
        ]
        side_is_outer: list[bool] = []
        edge_local_indices: dict[int, int] = {}
        edge_outer_parity: dict[int, int] = {}
        for point, edge_index in outer_loop:
            local_index = edge_local_indices.get(edge_index, 0)
            edge_local_indices[edge_index] = local_index + 1
            if edge_index not in edge_outer_parity and any(
                _points_close(point, main_point, tol=1e-6)
                for main_point in main_edge_points
            ):
                edge_outer_parity[edge_index] = local_index % 2
            side_is_outer.append(False)
        edge_local_indices.clear()
        for index, (_, edge_index) in enumerate(outer_loop):
            local_index = edge_local_indices.get(edge_index, 0)
            edge_local_indices[edge_index] = local_index + 1
            outer_parity = edge_outer_parity.get(edge_index, 0)
            side_is_outer[index] = local_index % 2 == outer_parity

        # Perimeter truss panels are generated from one closed waling loop.
        # Internal main struts/ties may share exact boundary nodes, but they
        # must not clear neighboring edge panels or reset the zigzag pattern.
        for index, (outer_start, _) in enumerate(outer_loop):
            next_index = (index + 1) % len(outer_loop)
            outer_end = outer_loop[next_index][0]
            if has_corner_handoff and outer_loop[index][1] != outer_loop[next_index][1]:
                continue
            start_corner_index = next((
                corner_index
                for corner_index, corner in enumerate(coords)
                if _points_close(outer_start, corner, tol=1e-6)
            ), None)
            end_corner_index = next((
                corner_index
                for corner_index, corner in enumerate(coords)
                if _points_close(outer_end, corner, tol=1e-6)
            ), None)
            start_on_outer = side_is_outer[index]
            end_on_outer = side_is_outer[next_index]
            if start_corner_index is not None:
                start_on_outer = False
                end_on_outer = True
            elif end_corner_index is not None:
                start_on_outer = True
                end_on_outer = False
            member_specs = self._truss_panel_member_specs(
                outer_start,
                outer_end,
                inner_loop[index],
                inner_loop[next_index],
                start_on_outer=start_on_outer,
                end_on_outer=end_on_outer,
            )
            corner_index = start_corner_index if start_corner_index is not None else end_corner_index
            attributes: dict[str, Any] = {"truss_primitive": "panel"}
            if corner_index is not None:
                attributes.update({
                    "belongs_to_corner_bracket": f"corner_bracket_{corner_index + 1}",
                    "corner_role": "edge_panel",
                })
            for kind, member in member_specs:
                line = LineString(member)
                if line.length <= 1e-9:
                    continue
                if not waling_poly.buffer(1e-6).covers(line):
                    continue
                self._add_linear_member(
                    layout,
                    kind,
                    member,
                    old_key=None,
                    node_kind="truss_node",
                    attributes=attributes,
                )

    def _place_perimeter_truss_stiffening(
        self,
        layout: dict[str, Any],
        waling_poly: Polygon,
    ) -> None:
        for main in [member for member in layout["members"] if member["kind"] == "main_strut"]:
            for outer_point in main["geometry"]:
                if waling_poly.exterior.distance(Point(outer_point)) > 1e-6:
                    continue
                adjacent_webs = [
                    member for member in layout["members"]
                    if member["kind"] == "truss_web"
                    and member.get("edge_role") == "web"
                    and any(
                        _points_close(point, outer_point, tol=1e-6)
                        for point in (member["geometry"][0], member["geometry"][-1])
                    )
                ]
                for web in adjacent_webs:
                    web["stiffening_for"] = sorted({
                        *web.get("stiffening_for", []),
                        str(main["id"]),
                    })
                    web["stiffening_points"] = _dedup_points(
                        [*web.get("stiffening_points", []), tuple(outer_point)],
                        1e-6,
                    )

    def _candidate_touches_corner(self, candidate: Geometry, corners: Geometry) -> bool:
        return any(
            _points_close(endpoint, corner, tol=1e-6)
            for endpoint in candidate
            for corner in corners
        )

    def _force_even_edge_panel_count(self, nodes: list[Point2D]) -> list[Point2D]:
        if len(nodes) < 2 or (len(nodes) - 1) % 2 == 0:
            return nodes
        candidate_indices = list(range(1, len(nodes) - 2)) or list(range(len(nodes) - 1))
        longest_index = max(
            candidate_indices,
            key=lambda index: LineString([nodes[index], nodes[index + 1]]).length,
        )
        start = nodes[longest_index]
        end = nodes[longest_index + 1]
        midpoint = (
            round((start[0] + end[0]) / 2.0, 6),
            round((start[1] + end[1]) / 2.0, 6),
        )
        return nodes[:longest_index + 1] + [midpoint] + nodes[longest_index + 1:]

    def _subdivide_edge_truss_panels(
        self,
        nodes: list[Point2D],
        max_panel: float,
    ) -> list[Point2D]:
        if len(nodes) < 2:
            return nodes
        subdivided = [nodes[0]]
        for start, end in zip(nodes, nodes[1:]):
            line = LineString([start, end])
            steps = max(1, int(ceil(line.length / max(max_panel, 1e-6))))
            subdivided.extend([
                (
                    round(start[0] + (end[0] - start[0]) * index / steps, 6),
                    round(start[1] + (end[1] - start[1]) * index / steps, 6),
                )
                for index in range(1, steps + 1)
            ])
        return subdivided

    def _align_edge_main_anchor_parity(
        self,
        layout: dict[str, Any],
        nodes: list[Point2D],
        start: Point2D,
        end: Point2D,
    ) -> list[Point2D]:
        edge = LineString([start, end])
        main_points = [
            endpoint
            for member in layout["members"]
            if member["kind"] == "main_strut"
            for endpoint in (member["geometry"][0], member["geometry"][-1])
            if edge.distance(Point(endpoint)) <= 1e-6
        ]
        if not main_points:
            return nodes

        adjusted = list(nodes)
        target_parity = 0
        index = 0
        while index < len(adjusted):
            point = adjusted[index]
            if not any(_points_close(point, main_point, tol=1e-6) for main_point in main_points):
                index += 1
                continue
            if index % 2 != target_parity and index > 0:
                previous = adjusted[index - 1]
                midpoint = (
                    round((previous[0] + point[0]) / 2.0, 6),
                    round((previous[1] + point[1]) / 2.0, 6),
                )
                adjusted.insert(index, midpoint)
                index += 1
            index += 1
        return adjusted

    def _orient_edge_truss_nodes(
        self,
        nodes: list[Point2D],
        start: Point2D,
        end: Point2D,
    ) -> list[Point2D]:
        edge = LineString([start, end])
        return sorted(nodes, key=lambda point: edge.project(Point(point)))

    def _stabilize_corner_adjacent_edge_nodes(
        self,
        nodes: list[Point2D],
        start: Point2D,
        end: Point2D,
        edge_depth: float,
    ) -> list[Point2D]:
        if len(nodes) < 3:
            return nodes

        edge = LineString([start, end])
        projections = [edge.project(Point(point)) for point in nodes]
        adjusted = list(nodes)

        first_target = min(edge_depth, edge.length)
        if 1e-6 < projections[1] < first_target and (len(projections) < 3 or projections[2] > first_target + 1e-6):
            point = edge.interpolate(first_target)
            adjusted[1] = (round(float(point.x), 6), round(float(point.y), 6))

        tail_offset = min(
            float(self.params["truss_panel_max"]),
            edge_depth + float(self.params["spacing_min"]) * 0.375,
        )
        last_target = max(0.0, edge.length - tail_offset)
        if (
            last_target < projections[-2] < edge.length - 1e-6
            and (len(projections) < 3 or projections[-3] < last_target - 1e-6)
        ):
            point = edge.interpolate(last_target)
            adjusted[-2] = (round(float(point.x), 6), round(float(point.y), 6))

        return adjusted

    def _perimeter_truss_inner_nodes(
        self,
        outer_loop: list[tuple[Point2D, int]],
        edge_depth: float,
        corner_lookup: dict[Point2D, int],
        inward_by_edge: list[Point2D],
    ) -> list[Point2D]:
        inner_nodes: list[Point2D] = []
        for index, (point, edge_index) in enumerate(outer_loop):
            corner_index = corner_lookup.get((round(point[0], 6), round(point[1], 6)))
            if corner_index is None:
                inward = inward_by_edge[edge_index]
                inner_nodes.append((
                    round(point[0] + inward[0] * edge_depth, 6),
                    round(point[1] + inward[1] * edge_depth, 6),
                ))
                continue

            prev_inward = inward_by_edge[corner_index - 1]
            next_inward = inward_by_edge[corner_index % len(inward_by_edge)]
            inner_nodes.append((
                round(point[0] + (prev_inward[0] + next_inward[0]) * edge_depth, 6),
                round(point[1] + (prev_inward[1] + next_inward[1]) * edge_depth, 6),
            ))
        return inner_nodes

    def _edge_truss_depth(self) -> float:
        depth = float(self.params["truss_depth"])
        edge_depth = max(depth, float(self.params["spacing_min"]) * 0.75)
        if self.params["support_system"] == "straight_truss":
            edge_depth = max(depth, min(edge_depth, float(self.params["spacing_min"]) * 0.5))
        return min(edge_depth, float(self.params["corner_truss_max_reach"]))

    def _corner_truss_anchor_model(
        self,
        layout: dict[str, Any],
        waling_poly: Polygon,
    ) -> dict[str, Any]:
        coords = _open_coords(layout["waling"])
        corner_models: list[dict[str, Any]] = []
        if len(coords) < 3:
            return {
                "anchors": [],
                "semantic_lines": [],
                "bracket_diagonals": [],
                "bracket_rungs": [],
                "bracket_chords": [],
                "corners": corner_models,
            }

        edge_depth = self._edge_truss_depth()
        centroid = (float(waling_poly.centroid.x), float(waling_poly.centroid.y))

        for index, corner in enumerate(coords):
            prev_pt = coords[index - 1]
            next_pt = coords[(index + 1) % len(coords)]
            if not _is_convex_corner(prev_pt, corner, next_pt, waling_poly):
                continue

            prev_inward = _inward_unit_normal(corner, prev_pt, centroid)
            next_inward = _inward_unit_normal(corner, next_pt, centroid)
            inner_corner = (
                round(corner[0] + (prev_inward[0] + next_inward[0]) * edge_depth, 6),
                round(corner[1] + (prev_inward[1] + next_inward[1]) * edge_depth, 6),
            )
            leg_end = self._corner_leg_terminal(
                layout,
                corner,
                inner_corner,
                waling_poly,
            )
            leg_specs = self._corner_leg_member_specs(
                corner,
                leg_end,
                edge_depth,
                inner_anchor=inner_corner,
            )
            corner_models.append({
                "assembly_id": f"corner_bracket_{index + 1}",
                "corner": corner,
                "outer_edges": [[corner, prev_pt], [corner, next_pt]],
                "inner_corner": inner_corner,
                "leg_start": corner,
                "leg_end": leg_end,
                "leg_members": leg_specs,
                "members": [geometry for _, geometry in leg_specs],
            })

        return {
            "anchors": [],
            "semantic_lines": [],
            "bracket_diagonals": [],
            "bracket_rungs": [],
            "bracket_chords": [],
            "corners": corner_models,
        }

    def _corner_leg_terminal(
        self,
        layout: dict[str, Any],
        corner: Point2D,
        inner_corner: Point2D,
        waling_poly: Polygon,
    ) -> Point2D:
        direction = _unit_vector(corner, inner_corner)
        ray_length = max(
            waling_poly.bounds[2] - waling_poly.bounds[0],
            waling_poly.bounds[3] - waling_poly.bounds[1],
        )
        ray = LineString([
            corner,
            (
                corner[0] + direction[0] * ray_length,
                corner[1] + direction[1] * ray_length,
            ),
        ])
        min_leg_length = float(self.params["truss_panel_min"])
        candidates: list[Point2D] = []
        for member in layout["members"]:
            if member["kind"] != "main_strut":
                continue
            for point in _intersection_points(ray.intersection(LineString(member["geometry"]))):
                distance = Point(point).distance(Point(corner))
                if distance < min_leg_length - 1e-6:
                    continue
                candidates.append((round(point[0], 6), round(point[1], 6)))
        if candidates:
            return min(candidates, key=lambda point: Point(point).distance(Point(corner)))
        return inner_corner

    def _corner_leg_member_specs(
        self,
        start: Point2D,
        end: Point2D,
        depth: float,
        *,
        inner_anchor: Point2D | None = None,
    ) -> list[tuple[str, Geometry]]:
        line = LineString([start, end])
        max_panel = max(float(self.params["truss_panel_max"]), 1e-6)
        breakpoints = [start]
        if (
            inner_anchor is not None
            and line.length >= max_panel * 2.0 - 1e-6
            and line.distance(Point(inner_anchor)) <= 1e-6
        ):
            projection = line.project(Point(inner_anchor))
            if 1e-6 < projection < line.length - 1e-6:
                breakpoints.append(inner_anchor)
        breakpoints.append(end)

        panel_points = [breakpoints[0]]
        for segment_start, segment_end in zip(breakpoints, breakpoints[1:]):
            segment = LineString([segment_start, segment_end])
            segment_count = max(1, int(ceil(segment.length / max_panel)))
            panel_points.extend([
                (
                    round(
                        segment_start[0]
                        + (segment_end[0] - segment_start[0]) * index / segment_count,
                        6,
                    ),
                    round(
                        segment_start[1]
                        + (segment_end[1] - segment_start[1]) * index / segment_count,
                        6,
                    ),
                )
                for index in range(1, segment_count + 1)
            ])

        direction = _unit_vector(start, end)
        normal = (-direction[1], direction[0])
        half_depth = depth / 2.0
        panel_specs: list[tuple[str, Geometry]] = []
        for panel_start, panel_end in zip(panel_points, panel_points[1:]):
            midpoint = (
                round((panel_start[0] + panel_end[0]) / 2.0, 6),
                round((panel_start[1] + panel_end[1]) / 2.0, 6),
            )
            outer_mid = (
                round(midpoint[0] + normal[0] * half_depth, 6),
                round(midpoint[1] + normal[1] * half_depth, 6),
            )
            inner_mid = (
                round(midpoint[0] - normal[0] * half_depth, 6),
                round(midpoint[1] - normal[1] * half_depth, 6),
            )
            panel_specs.extend(self._truss_panel_member_specs(
                panel_start,
                outer_mid,
                panel_start,
                inner_mid,
                start_on_outer=True,
                end_on_outer=False,
            ))
            panel_specs.extend(self._truss_panel_member_specs(
                outer_mid,
                panel_end,
                inner_mid,
                panel_end,
                start_on_outer=False,
                end_on_outer=True,
            ))
            panel_specs.append(("truss_web", [outer_mid, inner_mid]))

        unique: list[tuple[str, Geometry]] = []
        for kind, geometry in panel_specs:
            if any(
                LineString(geometry).equals(LineString(existing))
                for _, existing in unique
            ):
                continue
            unique.append((kind, geometry))
        return unique

    def _corner_handoff_offset(
        self,
        layout: dict[str, Any],
        corner: Point2D,
        edge_end: Point2D,
        max_offset: float,
    ) -> float:
        edge = LineString([corner, edge_end])
        candidates = [
            Point(corner).distance(Point(point))
            for member in layout["members"]
            if member["kind"] == "main_strut"
            for point in (member["geometry"][0], member["geometry"][-1])
            if edge.distance(Point(point)) <= 1e-6
            and max_offset * 0.5 <= Point(corner).distance(Point(point)) <= max_offset + 1e-6
        ]
        if not candidates:
            return max_offset
        return min(candidates, key=lambda distance: abs(max_offset - distance))

    def _large_brace_corner_anchor_model(
        self,
        layout: dict[str, Any],
        waling_poly: Polygon,
    ) -> dict[str, Any]:
        coords = _open_coords(layout["waling"])
        centroid = (float(waling_poly.centroid.x), float(waling_poly.centroid.y))
        depth = self._edge_truss_depth()
        models: list[dict[str, Any]] = []
        for index, corner in enumerate(coords):
            prev_pt = coords[index - 1]
            next_pt = coords[(index + 1) % len(coords)]
            if not _is_convex_corner(prev_pt, corner, next_pt, waling_poly):
                continue
            prev_length = Point(corner).distance(Point(prev_pt))
            next_length = Point(corner).distance(Point(next_pt))
            setback = min(
                float(self.params["spacing"]) * 2.0,
                min(prev_length, next_length) * float(self.params["corner_zone_edge_fraction"]),
            )
            adjacent_main_offsets: list[float] = []
            for edge_end in (prev_pt, next_pt):
                edge = LineString([corner, edge_end])
                candidates = [
                    Point(corner).distance(Point(endpoint))
                    for member in layout["members"]
                    if member["kind"] == "main_strut"
                    for endpoint in (member["geometry"][0], member["geometry"][-1])
                    if edge.distance(Point(endpoint)) <= 1e-6
                    and Point(corner).distance(Point(endpoint)) > 1e-6
                ]
                if candidates:
                    adjacent_main_offsets.append(min(candidates))
            if len(adjacent_main_offsets) == 2:
                setback = min(setback, *adjacent_main_offsets)
            setback = max(float(self.params["node_snap_tolerance"]) * 2.0, setback)
            prev_anchor = _point_along(corner, prev_pt, setback)
            next_anchor = _point_along(corner, next_pt, setback)
            prev_inward = _inward_unit_normal(corner, prev_pt, centroid)
            next_inward = _inward_unit_normal(corner, next_pt, centroid)
            prev_inner = _offset_point(prev_anchor, prev_inward, depth)
            next_inner = _offset_point(next_anchor, next_inward, depth)
            models.append({
                "assembly_id": f"corner_bracket_{index + 1}",
                "corner": corner,
                "prev_anchor": prev_anchor,
                "next_anchor": next_anchor,
                "prev_inner_anchor": prev_inner,
                "next_inner_anchor": next_inner,
                "leg_start": prev_anchor,
                "leg_end": next_anchor,
                "leg_members": [],
                "members": [],
            })
        return {
            "anchors": [
                anchor
                for model in models
                for anchor in (model["prev_anchor"], model["next_anchor"])
            ],
            "semantic_lines": [],
            "bracket_diagonals": [],
            "bracket_rungs": [],
            "bracket_chords": [],
            "corners": models,
        }

    def _place_corner_truss_legs(
        self,
        layout: dict[str, Any],
        waling_poly: Polygon,
        corner_model: dict[str, Any],
    ) -> None:
        for corner in corner_model.get("corners", []):
            attributes = {
                "belongs_to_corner_bracket": corner["assembly_id"],
                "corner_role": "leg",
                "truss_primitive": "panel",
            }
            for kind, geometry in corner["leg_members"]:
                line = LineString(geometry)
                if line.length <= 1e-9 or not waling_poly.buffer(1e-6).covers(line):
                    continue
                member = self._add_linear_member(
                    layout,
                    kind,
                    list(geometry),
                    old_key=None,
                    node_kind="truss_node",
                    attributes=attributes,
                )
                if member is None:
                    continue
                if any(_points_close(endpoint, corner["leg_end"], tol=1e-6) for endpoint in geometry):
                    self._add_node(
                        layout,
                        corner["leg_end"],
                        "corner_leg_terminal",
                        [member["id"]],
                    )

    def _trim_edge_truss_corner_nodes(
        self,
        nodes: list[Point2D],
        start: Point2D,
        end: Point2D,
        corner_clearance: float,
        end_corner_clearance: float | None = None,
    ) -> list[Point2D]:
        if end_corner_clearance is None:
            end_corner_clearance = corner_clearance
        if corner_clearance <= 1e-9 and end_corner_clearance <= 1e-9:
            return nodes
        edge = LineString([start, end])
        trimmed = [
            point for point in nodes
            if edge.project(Point(point)) >= corner_clearance - 1e-6
            and edge.length - edge.project(Point(point)) >= end_corner_clearance - 1e-6
        ]
        if len(trimmed) < 2:
            return []
        return trimmed

    def _diagonal_starts_at_waling_corner(
        self,
        member: Geometry,
        waling_corners: Geometry,
    ) -> bool:
        angle = _segment_acute_axis_angle(member)
        if not 20.0 <= angle <= 70.0:
            return False
        return any(
            _points_close(endpoint, corner, tol=1e-6)
            for endpoint in (member[0], member[-1])
            for corner in waling_corners
        )

    def _place_secondary_perimeter_supports(
        self,
        layout: dict[str, Any],
        waling_poly: Polygon,
    ) -> None:
        coords = _open_coords(layout["waling"])
        if len(coords) < 8:
            return
        if waling_poly.convex_hull.area - waling_poly.area > max(waling_poly.area * 0.02, 1e-6):
            return
        support_lines = [
            LineString(member["geometry"])
            for member in layout["members"]
            if member["kind"] in {"main_strut", "tie"}
        ]
        if not support_lines:
            return

        max_unbraced = float(self.params.get("max_unbraced_perimeter", 8.0))
        edge_midpoints = [
            _line_midpoint((start, end))
            for start, end in zip(coords, coords[1:] + coords[:1])
        ]
        needs_support = any(
            min(line.distance(Point(point)) for line in support_lines) > max_unbraced
            for point in edge_midpoints
        )
        if not needs_support:
            return

        centroid = (float(waling_poly.centroid.x), float(waling_poly.centroid.y))
        for point in edge_midpoints:
            if min(line.distance(Point(point)) for line in support_lines) <= max_unbraced:
                continue
            line = LineString([centroid, point])
            segment = waling_poly.intersection(line)
            for radial in _unwrap_lines(segment, self.params["spacing_min"] * 0.25):
                coords_on_line = list(radial.coords)
                if len(coords_on_line) < 2:
                    continue
                candidate: Geometry = [
                    (float(coords_on_line[0][0]), float(coords_on_line[0][1])),
                    (float(coords_on_line[-1][0]), float(coords_on_line[-1][1])),
                ]
                if Point(candidate[0]).distance(Point(point)) < Point(candidate[-1]).distance(Point(point)):
                    candidate = [candidate[-1], candidate[0]]
                if not waling_poly.buffer(1e-6).covers(LineString(candidate)):
                    continue
                self._add_linear_member(
                    layout,
                    "radial_strut",
                    candidate,
                    old_key="struts",
                    node_kind="ring_radial",
                )

    def _place_corner_trusses(self, layout: dict[str, Any], waling_poly: Polygon) -> None:
        if not self._uses_large_corner_truss(waling_poly):
            return

        coords = _open_coords(layout["waling"])
        panel = max(
            self.params["truss_panel_min"],
            min(self.params["spacing"], self.params["truss_panel_max"]),
        )
        for index, corner in enumerate(coords):
            prev_pt = coords[index - 1]
            next_pt = coords[(index + 1) % len(coords)]
            layers = max(1, int(round(float(self.params["corner_layers"]))))
            first_offset = float(self.params["spacing"])
            layer_step = max(float(self.params["spacing_min"]) * 0.75, panel * 0.5)
            edge_points: list[tuple[Point2D, Point2D]] = []
            for layer in range(layers):
                target = first_offset + layer_step * layer
                left = _point_along(corner, prev_pt, target)
                right = _point_along(corner, next_pt, target)
                candidate = [left, right]
                line = LineString(candidate)
                if line.length <= 1e-9:
                    continue
                if not waling_poly.buffer(1e-6).covers(line):
                    continue
                self._add_linear_member(
                    layout,
                    "corner",
                    candidate,
                    old_key="corners",
                    node_kind="corner_end",
                )
                edge_points.append((left, right))
            self._place_corner_layer_coupling_ties(layout, waling_poly, edge_points)

    def _place_corner_layer_coupling_ties(
        self,
        layout: dict[str, Any],
        waling_poly: Polygon,
        edge_points: list[tuple[Point2D, Point2D]],
    ) -> None:
        if len(edge_points) < 2:
            return
        for side_index in range(2):
            points = [pair[side_index] for pair in edge_points]
            for start, end in zip(points, points[1:]):
                candidate = [start, end]
                line = LineString(candidate)
                if line.length < 6.0 - 1e-6:
                    continue
                if not waling_poly.exterior.buffer(1e-6).covers(line):
                    continue
                if not self._candidate_clear(layout, candidate, {"corner", "tie", "main_strut"}):
                    continue
                self._add_linear_member(
                    layout,
                    "tie",
                    candidate,
                    old_key="ties",
                    node_kind="corner_end|tie_end",
                )

    def _edge_truss_node_near(
        self,
        layout: dict[str, Any],
        corner: Point2D,
        edge_end: Point2D,
        min_distance: float,
    ) -> Point2D | None:
        edge = LineString([corner, edge_end])
        candidates: list[tuple[float, Point2D]] = []
        for node in layout["nodes"]:
            if "truss_node" not in node["kind"]:
                continue
            point = (float(node["pos"][0]), float(node["pos"][1]))
            distance = Point(point).distance(Point(corner))
            if distance + 1e-6 < min_distance:
                continue
            if edge.distance(Point(point)) > 1e-6:
                continue
            candidates.append((distance, point))
        if not candidates:
            return None
        _, point = min(candidates, key=lambda item: (abs(item[0] - min_distance), item[0]))
        return point

    def _uses_large_corner_truss(self, waling_poly: Polygon) -> bool:
        return max(
            waling_poly.bounds[2] - waling_poly.bounds[0],
            waling_poly.bounds[3] - waling_poly.bounds[1],
        ) >= 80.0

    def _place_truss_coupling_ties(
        self,
        layout: dict[str, Any],
        struts: list[dict[str, Any]],
        waling_poly: Polygon,
    ) -> None:
        by_axis = {
            "x": sorted(
                [item for item in struts if item["axis"] == "x"],
                key=lambda item: _member_midpoint(item["member"])[0],
            ),
            "y": sorted(
                [item for item in struts if item["axis"] == "y"],
                key=lambda item: _member_midpoint(item["member"])[1],
            ),
        }

        vertical_pairs = self._paired_group_struts(by_axis["x"], axis="x")
        for left, right in vertical_pairs:
            left_geom = left["member"]["geometry"]
            right_geom = right["member"]["geometry"]
            y_min = max(min(left_geom[0][1], left_geom[-1][1]), min(right_geom[0][1], right_geom[-1][1]))
            y_max = min(max(left_geom[0][1], left_geom[-1][1]), max(right_geom[0][1], right_geom[-1][1]))
            if y_max - y_min < self.params["spacing_min"]:
                continue

            y_positions = self._pair_lacing_positions(
                y_min,
                y_max,
                avoid=self._existing_long_tie_axes(layout, vertical_pair=True),
            )
            for y in y_positions:
                y_tie = [(left_geom[0][0], y), (right_geom[0][0], y)]
                line = LineString(y_tie)
                if not waling_poly.buffer(1e-6).covers(line):
                    continue
                if not self._candidate_clear(layout, y_tie, {"corner"}):
                    continue
                if not self._candidate_parallel_clear(
                    layout,
                    y_tie,
                    {"main_strut"},
                    min_distance=float(self.params["min_tie_to_strut_clearance"]),
                ):
                    continue
                self._add_linear_member(
                    layout,
                    "tie",
                    y_tie,
                    old_key="ties",
                    node_kind="truss_node",
                )

        for bottom, top in self._paired_group_struts(by_axis["y"], axis="y"):
            bottom_geom = bottom["member"]["geometry"]
            top_geom = top["member"]["geometry"]
            x_min = max(min(bottom_geom[0][0], bottom_geom[-1][0]), min(top_geom[0][0], top_geom[-1][0]))
            x_max = min(max(bottom_geom[0][0], bottom_geom[-1][0]), max(top_geom[0][0], top_geom[-1][0]))
            if x_max - x_min < self.params["spacing_min"]:
                continue

            x_positions = self._pair_lacing_positions(
                x_min,
                x_max,
                avoid=self._perpendicular_main_axes(layout, vertical_pair=False),
            )
            for x in x_positions:
                y_bottom = bottom_geom[0][1]
                y_top = top_geom[0][1]
                candidate = [(x, y_bottom), (x, y_top)]
                line = LineString(candidate)
                if not waling_poly.buffer(1e-6).covers(line):
                    continue
                if not self._candidate_clear(layout, candidate, {"corner"}):
                    continue
                if (
                    self.params["support_system"] in {"brace", "straight_truss"}
                    and not self._candidate_parallel_clear(
                        layout,
                        candidate,
                        {"main_strut"},
                        min_distance=float(self.params["min_tie_to_strut_clearance"]),
                    )
                ):
                    continue
                self._add_linear_member(
                    layout,
                    "tie",
                    candidate,
                    old_key="ties",
                    node_kind="truss_node",
                )

    def _pair_lacing_positions(
        self,
        lo: float,
        hi: float,
        *,
        anchors: list[float] | None = None,
        avoid: list[float] | None = None,
    ) -> list[float]:
        span = hi - lo
        if span <= 1e-9:
            return []
        max_unbraced = max(float(self.params["max_unbraced_pair_length"]), 1e-6)
        control_points = sorted({
            round(value, 6)
            for value in [*(anchors or []), *(avoid or [])]
            if lo < value < hi
        })
        positions: list[float] = []
        segment_start = lo
        for control in [*control_points, hi]:
            segment_end = control
            segment_span = segment_end - segment_start
            if segment_span > 1e-9:
                segments = max(1, int(ceil(segment_span / max_unbraced)))
                positions.extend(
                    segment_start + segment_span * index / segments
                    for index in range(1, segments)
                )
            if any(abs(control - anchor) <= 1e-6 for anchor in anchors or []):
                positions.append(control)
            segment_start = segment_end
        return sorted({round(value, 6) for value in positions})

    def _existing_long_tie_axes(self, layout: dict[str, Any], *, vertical_pair: bool) -> list[float]:
        bounds = self.poly.bounds
        span_threshold = (bounds[2] - bounds[0] if vertical_pair else bounds[3] - bounds[1]) * 0.5
        axes: list[float] = []
        for member in layout["members"]:
            if member["kind"] != "tie":
                continue
            start, end = member["geometry"][0], member["geometry"][-1]
            line = LineString(member["geometry"])
            if vertical_pair and abs(start[1] - end[1]) <= 1e-6 and line.length >= span_threshold:
                axes.append(float(start[1]))
            if not vertical_pair and abs(start[0] - end[0]) <= 1e-6 and line.length >= span_threshold:
                axes.append(float(start[0]))
        return sorted(set(round(value, 6) for value in axes))

    def _place_horizontal_distribution_ties(
        self,
        layout: dict[str, Any],
        waling_poly: Polygon,
        y_positions: list[float],
    ) -> None:
        if not y_positions:
            return
        min_x, _, max_x, _ = waling_poly.bounds
        edge_depth = max(float(self.params["truss_depth"]), float(self.params["spacing_min"]) * 0.75)
        x_start = min_x + edge_depth
        x_end = max_x - edge_depth
        for y in sorted({round(value, 6) for value in y_positions}):
            candidate = [(x_start, y), (x_end, y)]
            line = LineString(candidate)
            if line.length < (max_x - min_x) * 0.5:
                continue
            if not waling_poly.buffer(1e-6).covers(line):
                continue
            if not self._candidate_clear(layout, candidate, {"corner", "tie"}):
                continue
            self._add_linear_member(
                layout,
                "tie",
                candidate,
                old_key="ties",
                node_kind="truss_node|tie_end",
            )

    def _place_pair_diagonal_lacing(
        self,
        layout: dict[str, Any],
        waling_poly: Polygon,
        first_axis: float,
        second_axis: float,
        positions: list[float],
        *,
        vertical_pair: bool,
    ) -> None:
        if len(positions) < 2:
            return
        placed = False
        for index, (start_pos, end_pos) in enumerate(zip(positions, positions[1:])):
            if vertical_pair:
                candidate = (
                    [(first_axis, start_pos), (second_axis, end_pos)]
                    if index % 2 == 0
                    else [(second_axis, start_pos), (first_axis, end_pos)]
                )
            else:
                candidate = (
                    [(start_pos, first_axis), (end_pos, second_axis)]
                    if index % 2 == 0
                    else [(start_pos, second_axis), (end_pos, first_axis)]
                )
            if not 20.0 <= _segment_acute_axis_angle(candidate) <= 70.0:
                continue
            line = LineString(candidate)
            if line.length <= 1e-9:
                continue
            if not waling_poly.buffer(1e-6).covers(line):
                continue
            if not self._candidate_clear(layout, candidate, {"corner"}):
                continue
            self._add_linear_member(
                layout,
                "tie",
                candidate,
                old_key="ties",
                node_kind="truss_node",
            )
            placed = True
        if not placed:
            self._place_pair_clear_bay_lacing(
                layout,
                waling_poly,
                first_axis,
                second_axis,
                min(positions),
                max(positions),
                vertical_pair=vertical_pair,
            )

    def _place_pair_clear_bay_lacing(
        self,
        layout: dict[str, Any],
        waling_poly: Polygon,
        first_axis: float,
        second_axis: float,
        lo: float,
        hi: float,
        *,
        vertical_pair: bool,
    ) -> None:
        pair_gap = abs(second_axis - first_axis)
        if pair_gap <= 1e-9 or hi - lo <= pair_gap:
            return

        blocked = self._perpendicular_main_axes(layout, vertical_pair=vertical_pair)
        clear_intervals = [(lo, hi)]
        clearance = 6.0
        for axis_value in blocked:
            next_intervals: list[tuple[float, float]] = []
            for start, end in clear_intervals:
                left = min(end, axis_value - clearance)
                right = max(start, axis_value + clearance)
                if left - start >= pair_gap:
                    next_intervals.append((start, left))
                if end - right >= pair_gap:
                    next_intervals.append((right, end))
            clear_intervals = next_intervals

        target_bay = pair_gap * 2.0
        for start, end in sorted(clear_intervals, key=lambda item: -(item[1] - item[0])):
            bay = min(target_bay, end - start)
            if bay < pair_gap:
                continue
            mid = (start + end) / 2.0
            lace_start = mid - bay / 2.0
            lace_end = mid + bay / 2.0
            if vertical_pair:
                candidates = [
                    [_rounded_point((first_axis, lace_start)), _rounded_point((second_axis, lace_end))],
                    [_rounded_point((second_axis, lace_start)), _rounded_point((first_axis, lace_end))],
                ]
            else:
                candidates = [
                    [_rounded_point((lace_start, first_axis)), _rounded_point((lace_end, second_axis))],
                    [_rounded_point((lace_start, second_axis)), _rounded_point((lace_end, first_axis))],
                ]
            if not all(20.0 <= _segment_acute_axis_angle(candidate) <= 70.0 for candidate in candidates):
                continue
            placed = False
            for candidate in candidates:
                line = LineString(candidate)
                if not waling_poly.buffer(1e-6).covers(line):
                    continue
                if not self._candidate_clear(layout, candidate, {"corner"}):
                    continue
                self._add_linear_member(
                    layout,
                    "tie",
                    candidate,
                    old_key="ties",
                    node_kind="truss_node",
                )
                placed = True
            if placed:
                return

    def _perpendicular_main_axes(
        self,
        layout: dict[str, Any],
        *,
        vertical_pair: bool,
    ) -> list[float]:
        axes: list[float] = []
        for member in layout["members"]:
            if member["kind"] != "main_strut":
                continue
            start, end = member["geometry"][0], member["geometry"][-1]
            if vertical_pair and abs(start[1] - end[1]) <= 1e-6:
                axes.append(float(start[1]))
            if not vertical_pair and abs(start[0] - end[0]) <= 1e-6:
                axes.append(float(start[0]))
        return sorted(set(round(value, 6) for value in axes))

    def _near_perpendicular_main_strut_axis(
        self,
        layout: dict[str, Any],
        value: float,
        *,
        axis: str,
        min_distance: float,
    ) -> bool:
        index = 0 if axis == "x" else 1
        for member in layout["members"]:
            if member["kind"] != "main_strut":
                continue
            start, end = member["geometry"][0], member["geometry"][-1]
            if axis == "x" and abs(start[0] - end[0]) > 1e-6:
                continue
            if axis == "y" and abs(start[1] - end[1]) > 1e-6:
                continue
            if abs(float(value) - float(start[index])) < min_distance:
                return True
        return False

    def _paired_group_struts(self, struts: list[dict[str, Any]], *, axis: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        if len(struts) < 2:
            return []

        index = 0 if axis == "x" else 1
        pair_gap = max(4.0, min(8.0, float(self.params["spacing_min"])))
        pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
        cursor = 0
        while cursor < len(struts) - 1:
            left = struts[cursor]
            right = struts[cursor + 1]
            gap = abs(_member_midpoint(right["member"])[index] - _member_midpoint(left["member"])[index])
            if gap <= pair_gap + 1e-6:
                pairs.append((left, right))
                cursor += 2
            else:
                cursor += 1
        return pairs

    def _coupling_positions(self, lo: float, hi: float) -> list[float]:
        span = hi - lo
        if span <= self.params["spacing_min"]:
            return []
        target = max(10.0, float(self.params["tie_interval"]))
        steps = max(1, int(round(span / target)))
        spacing = span / steps
        if spacing < 10.0 and steps > 1:
            steps -= 1
        return [
            lo + span * index / steps
            for index in range(1, steps)
        ]

    def _merge_edge_main_strut_anchors(
        self,
        layout: dict[str, Any],
        nodes: list[Point2D],
        start: Point2D,
        end: Point2D,
        *,
        extra_anchor_points: Geometry | None = None,
    ) -> list[Point2D]:
        if len(nodes) < 2:
            return nodes

        anchors: list[Point2D] = []
        edge = LineString([start, end])
        edge_points = [
            (round(point[0], 6), round(point[1], 6))
            for member in layout["members"]
            if member["kind"] == "main_strut"
            for point in member["geometry"]
            if edge.distance(Point(point)) <= 1e-6
        ]
        preserve_individual = self.params["support_system"] in {"brace", "straight_truss"}
        if preserve_individual:
            anchors.extend(edge_points)
        elif abs(start[1] - end[1]) <= 1e-6:
            for group in _group_axis_points(edge_points, axis="x", max_gap=float(self.params["spacing_min"])):
                anchors.append((round(sum(point[0] for point in group) / len(group), 6), round(start[1], 6)))
        elif abs(start[0] - end[0]) <= 1e-6:
            for group in _group_axis_points(edge_points, axis="y", max_gap=float(self.params["spacing_min"])):
                anchors.append((round(start[0], 6), round(sum(point[1] for point in group) / len(group), 6)))
        for point in extra_anchor_points or []:
            projected = edge.interpolate(edge.project(Point(point)))
            projected_point = (round(float(projected.x), 6), round(float(projected.y), 6))
            if edge.distance(Point(point)) <= float(self.params["spacing_min"]) * 0.25:
                anchors.append(projected_point)
        if not anchors:
            return nodes

        target_panel = max(1e-6, LineString([start, end]).length / max(len(nodes) - 1, 1))
        merge_tol = target_panel * 0.55

        if abs(start[1] - end[1]) <= 1e-6:
            y = round(start[1], 6)
            lo, hi = sorted((start[0], end[0]))
            anchor_xs = sorted({point[0] for point in anchors if lo - 1e-6 <= point[0] <= hi + 1e-6})
            xs = [
                round(point[0], 6)
                for point in nodes
                if abs(point[0] - lo) <= 1e-6
                or abs(point[0] - hi) <= 1e-6
                or not any(abs(point[0] - anchor_x) <= merge_tol for anchor_x in anchor_xs)
            ]
            for anchor in anchors:
                if not lo - 1e-6 <= anchor[0] <= hi + 1e-6:
                    continue
                xs.append(anchor[0])
            return [(x, y) for x in sorted(set(xs))]

        if abs(start[0] - end[0]) <= 1e-6:
            x = round(start[0], 6)
            lo, hi = sorted((start[1], end[1]))
            anchor_ys = sorted({point[1] for point in anchors if lo - 1e-6 <= point[1] <= hi + 1e-6})
            ys = [
                round(point[1], 6)
                for point in nodes
                if abs(point[1] - lo) <= 1e-6
                or abs(point[1] - hi) <= 1e-6
                or not any(abs(point[1] - anchor_y) <= merge_tol for anchor_y in anchor_ys)
            ]
            for anchor in anchors:
                if not lo - 1e-6 <= anchor[1] <= hi + 1e-6:
                    continue
                ys.append(anchor[1])
            return [(x, y) for y in sorted(set(ys))]

        return nodes

    def _candidate_avoids_lines(
        self,
        candidate: Geometry,
        avoid_lines: list[Geometry],
    ) -> bool:
        line = LineString(candidate)
        for avoid in avoid_lines:
            other = LineString(avoid)
            inter = line.intersection(other)
            if inter.is_empty:
                continue
            points = _intersection_points(inter)
            if not points and inter.length > 1e-6:
                return False
            for point in points:
                if not _is_connection_point(point, candidate, avoid):
                    return False
        return True

    def _add_structural_cross_nodes(self, layout: dict[str, Any]) -> None:
        node_kinds = {"main_strut", "corner", "tie", "truss_chord", "truss_web"}
        members = [member for member in layout["members"] if member["kind"] in node_kinds]
        for index, left in enumerate(members):
            left_line = LineString(left["geometry"])
            for right in members[index + 1:]:
                inter = left_line.intersection(LineString(right["geometry"]))
                if inter.is_empty:
                    continue
                for point in _intersection_points(inter):
                    if _is_endpoint(point, left["geometry"]) and _is_endpoint(point, right["geometry"]):
                        continue
                    kinds = {left["kind"], right["kind"]}
                    if kinds == {"main_strut", "tie"}:
                        node_kind = "strut_cross|tie_end"
                    elif kinds == {"main_strut"}:
                        node_kind = "strut_cross"
                    elif kinds == {"tie"}:
                        node_kind = "tie_end"
                    elif _is_endpoint(point, left["geometry"]) or _is_endpoint(point, right["geometry"]):
                        node_kind = "truss_node"
                    else:
                        node_kind = "truss_node"
                    self._add_node(
                        layout,
                        point,
                        node_kind,
                        [left["id"], right["id"]],
                    )

    def _split_truss_members_at_main_crossings(self, layout: dict[str, Any]) -> None:
        main_struts = [
            member for member in layout["members"]
            if member["kind"] == "main_strut"
        ]
        targets = [
            member for member in layout["members"]
            if member["kind"] in {"truss_chord", "truss_web"}
        ]
        for target in targets:
            line = LineString(target["geometry"])
            split_distances: list[float] = []
            for main in main_struts:
                intersection = line.intersection(LineString(main["geometry"]))
                for point in _intersection_points(intersection):
                    distance = line.project(Point(point))
                    if 1e-6 < distance < line.length - 1e-6:
                        split_distances.append(distance)
            distances = sorted({round(distance, 6) for distance in split_distances})
            if not distances:
                continue

            layout["members"].remove(target)
            layout["outlines"] = [
                outline for outline in layout["outlines"]
                if outline.get("member_id") != target["id"]
            ]
            for node in layout["nodes"]:
                if target["id"] in node.get("source", []):
                    node["source"] = [
                        member_id for member_id in node["source"]
                        if member_id != target["id"]
                    ]

            for start_distance, end_distance in zip(
                [0.0, *distances],
                [*distances, line.length],
            ):
                segment = substring(line, start_distance, end_distance)
                if not isinstance(segment, LineString) or segment.length <= 1e-9:
                    continue
                attributes = {
                    key: value
                    for key, value in target.items()
                    if key not in {
                        "id",
                        "kind",
                        "system",
                        "start",
                        "end",
                        "geometry",
                        "width",
                        "material",
                    }
                }
                attributes["parent_member_id"] = str(
                    target.get("parent_member_id", target["id"])
                )
                attributes["logical_geometry"] = list(
                    target.get("logical_geometry", target["geometry"])
                )
                self._add_member(
                    layout,
                    target["kind"],
                    [(float(x), float(y)) for x, y in segment.coords],
                    float(target["width"]),
                    node_kind="truss_node",
                    attributes=attributes,
                )

    def _place_single_direction_ties(
        self,
        layout: dict[str, Any],
        struts: list[dict[str, Any]],
        waling_poly: Polygon,
    ) -> None:
        vertical = [item for item in struts if item["axis"] == "x"]
        vertical.sort(key=lambda item: _member_midpoint(item["member"])[0])
        if len(vertical) < 2:
            return

        for left, right in zip(vertical, vertical[1:]):
            left_geom = left["member"]["geometry"]
            right_geom = right["member"]["geometry"]
            y_min = max(min(left_geom[0][1], left_geom[-1][1]), min(right_geom[0][1], right_geom[-1][1]))
            y_max = min(max(left_geom[0][1], left_geom[-1][1]), max(right_geom[0][1], right_geom[-1][1]))
            if y_max - y_min < self.params["spacing_min"]:
                continue

            for ratio in self.params["tie_ratio"]:
                y = y_min + (y_max - y_min) * float(ratio)
                candidate = [(left_geom[0][0], y), (right_geom[0][0], y)]
                line = LineString(candidate)
                if line.length < self.params["spacing_min"] * 0.25:
                    continue
                if not waling_poly.buffer(1e-6).covers(line):
                    continue
                if not self._candidate_clear(layout, candidate, {"main_strut", "corner", "tie"}):
                    continue
                if (
                    self.params["support_system"] in {"brace", "straight_truss"}
                    and not self._candidate_parallel_clear(
                        layout,
                        candidate,
                        {"main_strut"},
                        min_distance=float(self.params["min_tie_to_strut_clearance"]),
                    )
                ):
                    continue
                self._add_linear_member(
                    layout,
                    "tie",
                    candidate,
                    old_key="ties",
                    node_kind="tie_end",
                )

    def _place_opposite_strut_y_ties(
        self,
        layout: dict[str, Any],
        struts: list[dict[str, Any]],
        waling_poly: Polygon,
    ) -> None:
        horizontal = [item for item in struts if item["axis"] == "y"]
        horizontal.sort(key=lambda item: _member_midpoint(item["member"])[1])
        if len(horizontal) < 2:
            return

        for bottom, top in zip(horizontal, horizontal[1:]):
            bottom_geom = bottom["member"]["geometry"]
            top_geom = top["member"]["geometry"]
            x_min = max(min(bottom_geom[0][0], bottom_geom[-1][0]), min(top_geom[0][0], top_geom[-1][0]))
            x_max = min(max(bottom_geom[0][0], bottom_geom[-1][0]), max(top_geom[0][0], top_geom[-1][0]))
            if x_max - x_min < self.params["spacing_min"]:
                continue

            for ratio in self.params["tie_ratio"]:
                x = x_min + (x_max - x_min) * float(ratio)
                candidate = [(x, bottom_geom[0][1]), (x, top_geom[0][1])]
                line = LineString(candidate)
                if line.length < self.params["spacing_min"] * 0.25:
                    continue
                if not waling_poly.buffer(1e-6).covers(line):
                    continue
                if not self._candidate_clear(layout, candidate, {"main_strut", "corner", "tie"}):
                    continue
                if (
                    self.params["support_system"] in {"brace", "straight_truss"}
                    and not self._candidate_parallel_clear(
                        layout,
                        candidate,
                        {"main_strut"},
                        min_distance=float(self.params["min_tie_to_strut_clearance"]),
                    )
                ):
                    continue
                self._add_linear_member(
                    layout,
                    "tie",
                    candidate,
                    old_key="ties",
                    node_kind="tie_end",
                )

    def _place_inner_ring_system(self, layout: dict[str, Any], waling_poly: Polygon) -> None:
        core_center = self.params["core_center"]
        assert core_center is not None
        cx, cy = core_center
        core_radius = self.params["core_diameter"] / 2.0
        min_ring_radius = core_radius + self.params["core_clearance"]
        edge_room = (
            Point(cx, cy).distance(waling_poly.exterior)
            - self.params["ring_edge_clearance"]
        )
        ring_radius = max(min_ring_radius, edge_room)

        if ring_radius <= min_ring_radius - 1e-6:
            raise ValueError("not enough room for circular support outside the core clearance")
        if not waling_poly.contains(Point(cx, cy).buffer(ring_radius)):
            ring_radius = min_ring_radius
            if not waling_poly.contains(Point(cx, cy).buffer(ring_radius)):
                raise ValueError("core and required ring clearance do not fit inside the pit")

        segments = max(32, int(ceil(2.0 * pi * ring_radius / 2.0)))
        ring = [
            (cx + ring_radius * cos(2.0 * pi * i / segments),
             cy + ring_radius * sin(2.0 * pi * i / segments))
            for i in range(segments)
        ]
        ring.append(ring[0])
        self._add_member(
            layout,
            "ring_strut",
            ring,
            self.params["main_width"],
            node_kind="ring_radial",
            closed=True,
        )

        radial_count = self.params["radial_count"]
        if radial_count is None:
            radial_count = max(
                8,
                int(round(2.0 * pi * ring_radius / self.params["radial_spacing_max"])),
            )
        radial_count = int(radial_count)

        for i in range(radial_count):
            angle = 2.0 * pi * i / radial_count
            direction = (cos(angle), sin(angle))
            start = (cx + ring_radius * direction[0], cy + ring_radius * direction[1])
            end = self._ray_hit_boundary((cx, cy), direction, waling_poly)
            if end is None:
                continue
            if LineString([start, end]).length <= self.params["spacing_min"] * 0.25:
                continue
            self._add_linear_member(
                layout,
                "radial_strut",
                [start, end],
                old_key="struts",
                node_kind="ring_radial",
            )

        protection = [
            (cx + core_radius * cos(2.0 * pi * i / segments),
             cy + core_radius * sin(2.0 * pi * i / segments))
            for i in range(segments)
        ]
        protection.append(protection[0])
        layout["outlines"].append({
            "id": self._next_outline_id(),
            "member_id": None,
            "layer": "CORE_PROTECTION",
            "geometry": protection,
            "closed": True,
        })

    # ------------------------------------------------------------------
    # Node/member model
    # ------------------------------------------------------------------

    def _planarize_structural_members(self, layout: dict[str, Any]) -> None:
        """Split every geometric joint so the member graph matches the drawing."""
        originals = list(layout["members"])
        if len(originals) < 2:
            return
        distances: dict[str, set[float]] = {
            str(member["id"]): {0.0, LineString(member["geometry"]).length}
            for member in originals
        }
        lines = [LineString(member["geometry"]) for member in originals]
        tree = STRtree(lines)
        snap_tol = float(self.params["node_snap_tolerance"])
        for index, (left, left_line) in enumerate(zip(originals, lines)):
            for right_index in tree.query(left_line.buffer(snap_tol)):
                right_index = int(right_index)
                if right_index <= index:
                    continue
                right = originals[right_index]
                right_line = lines[right_index]
                intersection = left_line.intersection(right_line)
                joint_points = _joint_points(intersection)
                if not joint_points and left_line.distance(right_line) <= snap_tol:
                    for point in (left_line.coords[0], left_line.coords[-1]):
                        if right_line.distance(Point(point)) <= snap_tol:
                            projected = right_line.interpolate(right_line.project(Point(point)))
                            joint_points.append((float(projected.x), float(projected.y)))
                    for point in (right_line.coords[0], right_line.coords[-1]):
                        if left_line.distance(Point(point)) <= snap_tol:
                            projected = left_line.interpolate(left_line.project(Point(point)))
                            joint_points.append((float(projected.x), float(projected.y)))
                for point in joint_points:
                    distances[str(left["id"])].add(round(left_line.project(Point(point)), 6))
                    distances[str(right["id"])].add(round(right_line.project(Point(point)), 6))

        targets = [
            member for member in originals
            if len(distances[str(member["id"])]) > 2
        ]
        if not targets:
            return
        target_ids = {str(member["id"]) for member in targets}
        layout["members"] = [
            member for member in layout["members"]
            if str(member["id"]) not in target_ids
        ]
        layout["outlines"] = [
            outline for outline in layout["outlines"]
            if str(outline.get("member_id")) not in target_ids
        ]
        for node in layout["nodes"]:
            node["source"] = [
                member_id for member_id in node.get("source", [])
                if str(member_id) not in target_ids
            ]

        excluded = {"id", "kind", "system", "start", "end", "geometry", "width", "material"}
        for target in targets:
            line = LineString(target["geometry"])
            cuts = sorted(distances[str(target["id"])])
            attributes = {key: value for key, value in target.items() if key not in excluded}
            attributes["parent_member_id"] = str(target.get("parent_member_id", target["id"]))
            attributes["logical_geometry"] = list(target.get("logical_geometry", target["geometry"]))
            for start_distance, end_distance in zip(cuts, cuts[1:]):
                if end_distance - start_distance <= 1e-6:
                    continue
                segment = substring(line, start_distance, end_distance)
                if not isinstance(segment, LineString) or segment.length <= 1e-9:
                    continue
                self._add_member(
                    layout,
                    str(target["kind"]),
                    [(float(x), float(y)) for x, y in segment.coords],
                    float(target["width"]),
                    node_kind=_planar_node_kind(str(target["kind"])),
                    attributes=attributes,
                )

        node_by_id = {str(node["id"]): node for node in layout["nodes"]}
        for node in layout["nodes"]:
            node["source"] = []
        for member in layout["members"]:
            for key in ("start", "end"):
                node = node_by_id.get(str(member[key]))
                if node is not None:
                    node["source"].append(str(member["id"]))
        layout["nodes"] = [node for node in layout["nodes"] if node["source"]]
        self._node_by_id = {str(node["id"]): node for node in layout["nodes"]}
        self._rebuild_node_index(layout)
        self._refresh_legacy_buckets(layout)

    def _refresh_legacy_buckets(self, layout: dict[str, Any]) -> None:
        layout["struts"] = [
            member["geometry"][:2]
            for member in layout["members"]
            if member["kind"] in {"main_strut", "radial_strut"}
        ]
        layout["ties"] = [
            member["geometry"][:2]
            for member in layout["members"]
            if member["kind"] == "tie"
        ]
        layout["corners"] = [
            member["geometry"][:2]
            for member in layout["members"]
            if member["kind"] == "corner"
        ]

    def _remove_layout_members(
        self,
        layout: dict[str, Any],
        member_ids: set[str],
    ) -> None:
        if not member_ids:
            return
        layout["members"] = [
            member for member in layout["members"]
            if str(member["id"]) not in member_ids
        ]
        layout["outlines"] = [
            outline for outline in layout["outlines"]
            if str(outline.get("member_id")) not in member_ids
        ]
        for node in layout["nodes"]:
            node["source"] = [
                member_id for member_id in node.get("source", [])
                if str(member_id) not in member_ids
            ]
        layout["nodes"] = [node for node in layout["nodes"] if node["source"]]
        self._node_by_id = {str(node["id"]): node for node in layout["nodes"]}
        self._rebuild_node_index(layout)
        self._refresh_legacy_buckets(layout)

    def _merge_nearby_nodes(self, layout: dict[str, Any]) -> None:
        min_separation = float(self.params["min_node_separation"])
        nodes = layout["nodes"]
        if min_separation <= 0.0 or len(nodes) < 2:
            return

        parent = list(range(len(nodes)))

        def find(index: int) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def union(left: int, right: int) -> None:
            left_root = find(left)
            right_root = find(right)
            if left_root != right_root:
                parent[right_root] = left_root

        for left_index, left in enumerate(nodes):
            left_point = Point(left["pos"])
            for right_index in range(left_index + 1, len(nodes)):
                right = nodes[right_index]
                if "truss_node" not in left["kind"] and "truss_node" not in right["kind"]:
                    continue
                if left_point.distance(Point(right["pos"])) < min_separation - 1e-9:
                    union(left_index, right_index)

        clusters: dict[int, list[int]] = {}
        for index in range(len(nodes)):
            clusters.setdefault(find(index), []).append(index)
        if all(len(cluster) == 1 for cluster in clusters.values()):
            return

        def node_priority(node: dict[str, Any]) -> tuple[int, str]:
            kind = str(node["kind"])
            if "strut_cross" in kind:
                priority = 0
            elif "strut_end" in kind:
                priority = 1
            elif "waling_point" in kind:
                priority = 2
            elif "truss_node" in kind:
                priority = 3
            else:
                priority = 4
            return priority, str(node["id"])

        replacements: dict[str, str] = {}
        canonical_nodes: list[dict[str, Any]] = []
        for cluster in clusters.values():
            canonical_index = min(cluster, key=lambda index: node_priority(nodes[index]))
            canonical = nodes[canonical_index]
            for index in cluster:
                node = nodes[index]
                replacements[str(node["id"])] = str(canonical["id"])
                if index == canonical_index:
                    continue
                canonical["kind"] = _merge_node_kind(canonical["kind"], node["kind"])
                canonical["source"] = sorted(set(canonical["source"]) | set(node["source"]))
            canonical_nodes.append(canonical)

        node_by_id = {str(node["id"]): node for node in canonical_nodes}
        changed_members: list[dict[str, Any]] = []
        for member in layout["members"]:
            changed = False
            for endpoint_key, geometry_index in (("start", 0), ("end", -1)):
                old_id = str(member[endpoint_key])
                new_id = replacements.get(old_id, old_id)
                if new_id == old_id:
                    continue
                member[endpoint_key] = new_id
                canonical_pos = node_by_id[new_id]["pos"]
                member["geometry"][geometry_index] = (
                    float(canonical_pos[0]),
                    float(canonical_pos[1]),
                )
                changed = True
            if changed:
                changed_members.append(member)

        layout["nodes"] = sorted(canonical_nodes, key=lambda node: str(node["id"]))
        self._node_by_id = {str(node["id"]): node for node in layout["nodes"]}
        self._rebuild_node_index(layout)
        changed_ids = {member["id"] for member in changed_members}
        if changed_ids:
            layout["outlines"] = [
                outline
                for outline in layout["outlines"]
                if outline.get("member_id") not in changed_ids
            ]
            for member in changed_members:
                self._add_outline(layout, member, closed=member["kind"] == "waling")

        layout["struts"] = [
            member["geometry"][:2]
            for member in layout["members"]
            if member["kind"] in {"main_strut", "radial_strut"}
        ]
        layout["ties"] = [
            member["geometry"][:2]
            for member in layout["members"]
            if member["kind"] == "tie"
        ]
        layout["corners"] = [
            member["geometry"][:2]
            for member in layout["members"]
            if member["kind"] == "corner"
        ]

    def _add_node(
        self,
        layout: dict[str, Any],
        pos: Point2D,
        kind: str,
        source: list[str] | None = None,
    ) -> str:
        snap_tol = float(self.params["node_snap_tolerance"])
        scale = 1.0 / max(snap_tol, 1e-9)
        key = (round(float(pos[0]) * scale), round(float(pos[1]) * scale))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                node_id = self._node_index.get((key[0] + dx, key[1] + dy))
                node = self._node_by_id.get(str(node_id)) if node_id is not None else None
                if node is None or _point_distance(node["pos"], pos) > snap_tol:
                    continue
                node_id = node["id"]
                node["kind"] = _merge_node_kind(node["kind"], kind)
                if source:
                    node["source"] = sorted(set(node["source"]) | set(source))
                self._node_index[key] = node_id
                return str(node_id)

        node_id = f"N{self._node_seq:03d}"
        self._node_seq += 1
        self._node_index[key] = node_id
        node = {
            "id": node_id,
            "pos": (float(pos[0]), float(pos[1])),
            "kind": kind,
            "source": list(source or []),
            "system": self.params["support_system"],
        }
        layout["nodes"].append(node)
        self._node_by_id[node_id] = node
        return node_id

    def _rebuild_node_index(self, layout: dict[str, Any]) -> None:
        snap_tol = float(self.params["node_snap_tolerance"])
        scale = 1.0 / max(snap_tol, 1e-9)
        self._node_index = {
            (round(float(node["pos"][0]) * scale), round(float(node["pos"][1]) * scale)): str(node["id"])
            for node in layout["nodes"]
        }

    def _add_member(
        self,
        layout: dict[str, Any],
        kind: str,
        geometry: list[tuple[float, float]],
        width: float,
        *,
        node_kind: str,
        closed: bool = False,
        attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        geom = [(float(x), float(y)) for x, y in geometry]
        if len(geom) < 2 or LineString(geom).length <= 1e-9:
            return None

        member_id = f"M{self._member_seq:03d}"
        self._member_seq += 1
        start = self._add_node(layout, geom[0], node_kind, [member_id])
        end = self._add_node(layout, geom[-1], node_kind, [member_id])
        member = {
            "id": member_id,
            "kind": kind,
            "system": self.params["support_system"],
            "start": start,
            "end": end,
            "geometry": geom,
            "width": float(width),
            "material": self.params["strut_material"],
        }
        if attributes:
            member.update(attributes)
        layout["members"].append(member)
        self._add_outline(layout, member, closed)
        return member

    def _add_linear_member(
        self,
        layout: dict[str, Any],
        kind: str,
        geometry: list[tuple[float, float]],
        *,
        old_key: str | None,
        node_kind: str,
        attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        width = self.params["tie_width"] if kind == "tie" else self.params["main_width"]
        if kind == "waling":
            width = self.params["waling_width"]
        member = self._add_member(
            layout,
            kind,
            geometry,
            width,
            node_kind=node_kind,
            attributes=attributes,
        )
        if member is not None and old_key:
            layout[old_key].append(member["geometry"][:2])
        return member

    def _add_outline(self, layout: dict[str, Any], member: dict[str, Any], closed: bool) -> None:
        line = LineString(member["geometry"])
        if line.length <= 1e-9 or member["width"] <= 0:
            return
        try:
            poly = line.buffer(member["width"] / 2.0, cap_style=2, join_style=2)
        except Exception:
            return
        if poly.is_empty or not hasattr(poly, "exterior"):
            return
        layout["outlines"].append({
            "id": self._next_outline_id(),
            "member_id": member["id"],
            "layer": _outline_layer(member["kind"]),
            "geometry": [(float(x), float(y)) for x, y in poly.exterior.coords],
            "closed": closed or True,
        })

    def _next_outline_id(self) -> str:
        outline_id = f"O{self._outline_seq:03d}"
        self._outline_seq += 1
        return outline_id

    def _add_main_strut_cross_nodes(self, layout: dict[str, Any]) -> None:
        members = [m for m in layout["members"] if m["kind"] == "main_strut"]
        for i, left in enumerate(members):
            left_line = LineString(left["geometry"])
            for right in members[i + 1:]:
                inter = left_line.intersection(LineString(right["geometry"]))
                if inter.geom_type != "Point":
                    continue
                point = (float(inter.x), float(inter.y))
                if _is_endpoint(point, left["geometry"]) or _is_endpoint(point, right["geometry"]):
                    continue
                self._add_node(layout, point, "strut_cross", [left["id"], right["id"]])

    def _place_pillars_from_nodes(self, layout: dict[str, Any], waling_poly: Polygon) -> None:
        candidates = []
        for node in layout["nodes"]:
            kind = node["kind"]
            score = _pillar_candidate_score(kind)
            if score <= 0:
                continue
            point = Point(node["pos"])
            if not waling_poly.buffer(1e-6).covers(point):
                continue
            if point.distance(self.poly.exterior) < self.params["safe_dist"]:
                continue
            candidates.append((score, node["pos"]))
        candidates.sort(key=lambda item: (-item[0], item[1][0], item[1][1]))
        selected: list[Point2D] = []
        min_spacing = float(self.params["pillar_min_spacing"])
        strict_spacing = self.params["support_system"] == "brace" and self._uses_large_corner_truss(waling_poly)
        for score, point in candidates:
            if (strict_spacing or score < 90) and any(
                Point(point).distance(Point(existing)) < min_spacing
                for existing in selected
            ):
                continue
            selected.append(point)
        layout["pillars"] = selected

    # ------------------------------------------------------------------
    # Validation and statistics
    # ------------------------------------------------------------------

    def _attach_stats(self, layout: dict[str, Any]) -> None:
        stats = {key: 0.0 for key in STATS_KEYS}
        for member in layout["members"]:
            kind = member["kind"]
            length = LineString(member["geometry"]).length
            if kind == "main_strut":
                stats["main_strut_length"] += length
            elif kind in {"corner", "haunch"}:
                stats["corner_length"] += length
            elif kind == "truss_web":
                stats["truss_web_length"] += length
            elif kind == "tie":
                stats["tie_length"] += length
            elif kind == "ring_strut":
                stats["ring_strut_length"] += length
            elif kind == "radial_strut":
                stats["radial_strut_length"] += length
            elif kind == "truss_chord":
                stats["main_strut_length"] += length
        stats["pillar_count"] = len(layout["pillars"])
        stats["total_support_length"] = sum(
            stats[key] for key in (
                "main_strut_length",
                "corner_length",
                "truss_web_length",
                "tie_length",
                "ring_strut_length",
                "radial_strut_length",
            )
        )
        layout["stats"] = stats

    def _attach_validation(self, layout: dict[str, Any]) -> None:
        generation_issues = list(layout["issues"])
        try:
            from strut_validation import validate_layout

            report = validate_layout(layout, self.params)
        except Exception as exc:  # pragma: no cover - validation must not hide layout generation.
            layout["issues"] = [{
                "kind": "validation_error",
                "reason": str(exc),
                "severity": "error",
            }]
            return
        layout["issues"] = generation_issues + report["issues"]

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    def _waling_poly(self) -> Polygon:
        offset = float(self.params["waling_offset"])
        try:
            result = self.poly.buffer(offset, join_style="mitre")
        except Exception:
            return self.poly
        if isinstance(result, MultiPolygon):
            result = max(result.geoms, key=lambda geom: geom.area)
        if not isinstance(result, Polygon) or result.is_empty:
            return self.poly
        return result

    def _offset_poly(self, dist: float) -> Polygon | None:
        try:
            result = self.poly.buffer(-dist)
        except Exception:
            return None
        if result.is_empty:
            return None
        if isinstance(result, MultiPolygon):
            result = max(result.geoms, key=lambda geom: geom.area)
        return result if isinstance(result, Polygon) else None

    def _ray_hit_boundary(
        self,
        origin: Point2D,
        direction: Point2D,
        poly: Polygon,
        max_dist: float = 10000.0,
    ) -> Point2D | None:
        far = (origin[0] + direction[0] * max_dist, origin[1] + direction[1] * max_dist)
        ray = LineString([origin, far])
        inter = poly.exterior.intersection(ray)
        points: list[Point2D] = []
        if inter.geom_type == "Point":
            points.append((float(inter.x), float(inter.y)))
        elif inter.geom_type == "MultiPoint":
            points.extend((float(pt.x), float(pt.y)) for pt in inter.geoms)
        elif inter.geom_type == "GeometryCollection":
            for geom in inter.geoms:
                if geom.geom_type == "Point":
                    points.append((float(geom.x), float(geom.y)))
        points = [pt for pt in points if Point(pt).distance(Point(origin)) > 1e-6]
        if not points:
            return None
        points.sort(key=lambda pt: (pt[0] - origin[0]) ** 2 + (pt[1] - origin[1]) ** 2)
        return points[0]

    def _candidate_clear(
        self,
        layout: dict[str, Any],
        candidate: Geometry,
        existing_kinds: set[str],
    ) -> bool:
        line = LineString(candidate)
        for member in layout["members"]:
            if member["kind"] not in existing_kinds:
                continue
            inter = line.intersection(LineString(member["geometry"]))
            if inter.is_empty:
                continue
            points = _intersection_points(inter)
            if not points and inter.length > 1e-6:
                return False
            for point in points:
                if not _is_connection_point(point, candidate, member["geometry"]):
                    return False
        return True

    def _candidate_parallel_clear(
        self,
        layout: dict[str, Any],
        candidate: Geometry,
        existing_kinds: set[str],
        *,
        min_distance: float,
    ) -> bool:
        candidate_line = LineString(candidate)
        for member in layout["members"]:
            if member["kind"] not in existing_kinds:
                continue
            if not _segments_nearly_parallel(candidate, member["geometry"]):
                continue
            distance = candidate_line.distance(LineString(member["geometry"]))
            if distance < min_distance - 1e-6:
                return False
        return True

    def _support_grid_positions(self, lo: float, hi: float) -> list[float]:
        span = hi - lo
        if span <= 1e-9:
            return []

        target = float(self.params["spacing"])
        preferred_edge = min(5.0, max(3.0, target * 0.55))
        min_edge = min(5.0, max(3.0, target * 0.5))
        max_edge = min(5.0, max(3.0, target * 0.6))
        if span <= 2.0 * min_edge:
            return [round((lo + hi) / 2.0, 6)]

        best: tuple[float, float, int, int, float, float] | None = None
        max_supports = max(2, int((span - 2.0 * min_edge) / max(self.params["spacing_min"], 1e-6)) + 1)
        edge_values = [
            round(min_edge + step * 0.1, 6)
            for step in range(int(round((max_edge - min_edge) / 0.1)) + 1)
        ]
        if preferred_edge not in edge_values:
            edge_values.append(round(preferred_edge, 6))
        edge_values = sorted({value for value in edge_values if min_edge - 1e-6 <= value <= max_edge + 1e-6})

        for edge in edge_values:
            effective = span - 2.0 * edge
            if effective <= 1e-9:
                continue
            for support_count in range(2, max_supports + 1):
                interval_count = support_count - 1
                spacing = effective / interval_count
                if spacing < self.params["spacing_min"] - 1e-6:
                    continue
                if spacing > self.params["spacing_max"] + 1e-6:
                    continue
                score = (
                    abs(spacing - target),
                    abs(edge - preferred_edge),
                    abs(interval_count - max(1, round(effective / max(target, 1e-6)))),
                    -support_count,
                )
                candidate = (score[0], score[1], score[2], score[3], edge, spacing)
                if best is None or candidate < best:
                    best = candidate

        if best is None:
            grid = _symmetric_grid((lo + hi) / 2.0, lo, hi, target)
            return [round(value, 6) for value in grid]

        _, _, _, neg_support_count, edge, spacing = best
        support_count = -neg_support_count
        return [round(lo + edge + spacing * index, 6) for index in range(support_count)]

    def _edge_axis_nodes(
        self,
        start: Point2D,
        end: Point2D,
        *,
        x_grid: list[float],
        y_grid: list[float],
    ) -> list[Point2D]:
        if abs(start[1] - end[1]) <= 1e-6:
            y = round(start[1], 6)
            lo, hi = sorted((start[0], end[0]))
            axis = [round(lo, 6)] + [x for x in x_grid if lo < x < hi] + [round(hi, 6)]
            return [(x, y) for x in axis]
        if abs(start[0] - end[0]) <= 1e-6:
            x = round(start[0], 6)
            lo, hi = sorted((start[1], end[1]))
            axis = [round(lo, 6)] + [y for y in y_grid if lo < y < hi] + [round(hi, 6)]
            return [(x, y) for y in axis]

        panel = max(
            self.params["truss_panel_min"],
            min(self.params["spacing"], self.params["truss_panel_max"]),
        )
        edge = LineString([start, end])
        steps = max(1, int(ceil(edge.length / panel)))
        return [
            (
                round(start[0] + (end[0] - start[0]) * index / steps, 6),
                round(start[1] + (end[1] - start[1]) * index / steps, 6),
            )
            for index in range(steps + 1)
        ]

    def _edge_truss_nodes(
        self,
        start: Point2D,
        end: Point2D,
        *,
        x_grid: list[float],
        y_grid: list[float],
        target_panel: float,
    ) -> list[Point2D]:
        edge = LineString([start, end])
        _ = (x_grid, y_grid)
        steps = max(1, int(ceil(edge.length / max(target_panel, 1e-6))))
        return [
            (
                round(start[0] + (end[0] - start[0]) * index / steps, 6),
                round(start[1] + (end[1] - start[1]) * index / steps, 6),
            )
            for index in range(steps + 1)
        ]


def _symmetric_grid(center: float, lo: float, hi: float, spacing: float) -> list[float]:
    half = (hi - lo) / 2.0
    count = max(0, int((half - spacing * 0.3) / spacing))
    values = [center + idx * spacing for idx in range(-count, count + 1)]
    margin = spacing * 0.15
    return [value for value in values if lo + margin < value < hi - margin]


def _unwrap_lines(geom: Any, min_len: float) -> list[LineString]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, LineString):
        return [geom] if geom.length >= min_len else []
    if isinstance(geom, MultiLineString):
        return [line for line in geom.geoms if line.length >= min_len]
    return []


def _horizontal_span_across_polygon(
    poly: Polygon,
    y: float,
    left_x: float,
    right_x: float,
    extension: float,
) -> Geometry | None:
    bounds = poly.bounds
    probe = LineString([(bounds[0] - extension, y), (bounds[2] + extension, y)])
    segments = _unwrap_lines(poly.intersection(probe), 1e-6)
    if not segments:
        return None

    midpoint = (left_x + right_x) / 2.0
    containing = [
        segment for segment in segments
        if segment.bounds[0] <= midpoint <= segment.bounds[2]
    ]
    segment = max(containing or segments, key=lambda item: item.length)
    coords = list(segment.coords)
    if len(coords) < 2:
        return None
    start = (float(coords[0][0]), float(coords[0][1]))
    end = (float(coords[-1][0]), float(coords[-1][1]))
    return [start, end] if start[0] <= end[0] else [end, start]


def _closed_coords(coords: list[tuple[float, float]]) -> Geometry:
    result = [(float(x), float(y)) for x, y in coords]
    if result and not _points_close(result[0], result[-1]):
        result.append(result[0])
    return result


def _open_coords(coords: Geometry) -> Geometry:
    if len(coords) > 1 and _points_close(coords[0], coords[-1]):
        return coords[:-1]
    return coords


def _inward_unit_normal(
    start: Point2D,
    end: Point2D,
    interior_point: Point2D,
) -> Point2D:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = (dx * dx + dy * dy) ** 0.5
    if length <= 1e-9:
        return (0.0, 0.0)
    normal_a = (-dy / length, dx / length)
    normal_b = (dy / length, -dx / length)
    midpoint = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
    toward_interior = (interior_point[0] - midpoint[0], interior_point[1] - midpoint[1])
    if normal_a[0] * toward_interior[0] + normal_a[1] * toward_interior[1] >= 0:
        return normal_a
    return normal_b


def _unit_vector(start: Point2D, end: Point2D) -> Point2D:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = (dx * dx + dy * dy) ** 0.5
    if length <= 1e-9:
        return (0.0, 0.0)
    return (dx / length, dy / length)


def _point_along(start: Point2D, target: Point2D, distance: float) -> Point2D:
    dx = target[0] - start[0]
    dy = target[1] - start[1]
    length = (dx * dx + dy * dy) ** 0.5
    if length <= 1e-9:
        return start
    scale = min(distance, length * 0.45) / length
    return (start[0] + dx * scale, start[1] + dy * scale)


def _point_toward(start: Point2D, target: Point2D, distance: float) -> Point2D:
    dx = target[0] - start[0]
    dy = target[1] - start[1]
    length = (dx * dx + dy * dy) ** 0.5
    if length <= 1e-9:
        return start
    scale = distance / length
    return (start[0] + dx * scale, start[1] + dy * scale)


def _offset_point(point: Point2D, direction: Point2D, distance: float) -> Point2D:
    return (
        round(point[0] + direction[0] * distance, 6),
        round(point[1] + direction[1] * distance, 6),
    )


def _point_distance(left: Point2D, right: Point2D) -> float:
    return ((left[0] - right[0]) ** 2 + (left[1] - right[1]) ** 2) ** 0.5


def _interpolate_point(start: Point2D, end: Point2D, ratio: float) -> Point2D:
    return (
        round(start[0] + (end[0] - start[0]) * ratio, 6),
        round(start[1] + (end[1] - start[1]) * ratio, 6),
    )


def _joint_points(geom: Any) -> list[Point2D]:
    points = _intersection_points(geom)
    if geom.geom_type == "LineString":
        coords = list(geom.coords)
        if coords:
            points.extend([
                (float(coords[0][0]), float(coords[0][1])),
                (float(coords[-1][0]), float(coords[-1][1])),
            ])
    elif geom.geom_type == "MultiLineString":
        for part in geom.geoms:
            points.extend(_joint_points(part))
    elif geom.geom_type == "GeometryCollection":
        for part in geom.geoms:
            points.extend(_joint_points(part))
    return list({(round(point[0], 6), round(point[1], 6)) for point in points})


def _planar_node_kind(kind: str) -> str:
    return {
        "waling": "waling_point",
        "main_strut": "strut_end",
        "tie": "tie_end",
        "ring_strut": "ring_radial",
        "radial_strut": "ring_radial|strut_end",
    }.get(kind, "truss_node")


def _is_convex_corner(
    prev_pt: Point2D,
    corner: Point2D,
    next_pt: Point2D,
    poly: Polygon,
) -> bool:
    arm = min(
        LineString([corner, prev_pt]).length,
        LineString([corner, next_pt]).length,
        1.0,
    )
    if arm <= 1e-9:
        return False
    left = _point_toward(corner, prev_pt, arm)
    right = _point_toward(corner, next_pt, arm)
    probe = LineString([left, right]).interpolate(0.5, normalized=True)
    return poly.buffer(1e-6).covers(probe)


def _line_midpoint(segment: tuple[Point2D, Point2D]) -> Point2D:
    point = LineString(segment).interpolate(0.5, normalized=True)
    return (float(point.x), float(point.y))


def _pillar_candidate_score(kind: str) -> int:
    if "strut_cross" in kind:
        return 100
    if "ring_radial" in kind:
        return 80
    if "tie_end" in kind:
        return 60
    if "truss_node" in kind and "tie" in kind:
        return 50
    return 0


def _merge_node_kind(existing: str, added: str) -> str:
    tokens = [token for token in existing.split("|") if token]
    for token in added.split("|"):
        if token and token not in tokens:
            tokens.append(token)
    return "|".join(tokens)


def _dedup_points(points: list[Point2D], tol: float) -> list[Point2D]:
    result: list[Point2D] = []
    for point in points:
        if not any(Point(point).distance(Point(existing)) <= tol for existing in result):
            result.append(point)
    return result


def _group_axis_points(points: list[Point2D], *, axis: str, max_gap: float) -> list[list[Point2D]]:
    if not points:
        return []
    index = 0 if axis == "x" else 1
    groups: list[list[Point2D]] = []
    for point in sorted(points, key=lambda item: item[index]):
        if groups and point[index] - groups[-1][-1][index] <= max_gap + 1e-6:
            groups[-1].append(point)
        else:
            groups.append([point])
    return groups


def _points_close(left: Point2D, right: Point2D, tol: float = 1e-6) -> bool:
    return abs(left[0] - right[0]) <= tol and abs(left[1] - right[1]) <= tol


def _rounded_point(point: Point2D) -> Point2D:
    return (round(float(point[0]), 6), round(float(point[1]), 6))


def _is_endpoint(point: Point2D, geometry: Geometry, tol: float = 1e-6) -> bool:
    return any(_points_close(point, endpoint, tol) for endpoint in (geometry[0], geometry[-1]))


def _is_connection_point(
    point: Point2D,
    left: Geometry,
    right: Geometry,
    tol: float = 1e-6,
) -> bool:
    if _is_endpoint(point, left, tol) and _is_endpoint(point, right, tol):
        return True
    if _is_endpoint(point, left, tol) and LineString(right).distance(Point(point)) <= tol:
        return True
    if _is_endpoint(point, right, tol) and LineString(left).distance(Point(point)) <= tol:
        return True
    return False


def _segments_nearly_parallel(left: Geometry, right: Geometry, tolerance_degrees: float = 5.0) -> bool:
    left_angle = _segment_angle_180(left)
    right_angle = _segment_angle_180(right)
    diff = abs(left_angle - right_angle)
    return min(diff, 180.0 - diff) <= tolerance_degrees


def _segment_angle_180(segment: Geometry) -> float:
    start, end = segment[0], segment[-1]
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    if abs(dx) <= 1e-9 and abs(dy) <= 1e-9:
        return 0.0
    return degrees(atan2(dy, dx)) % 180.0


def _segment_acute_axis_angle(segment: Geometry) -> float:
    angle = _segment_angle_180(segment)
    return min(angle, 180.0 - angle)


def _intersection_points(geom: Any) -> list[Point2D]:
    if geom.is_empty:
        return []
    if geom.geom_type == "Point":
        return [(float(geom.x), float(geom.y))]
    if geom.geom_type == "MultiPoint":
        return [(float(pt.x), float(pt.y)) for pt in geom.geoms]
    if geom.geom_type == "GeometryCollection":
        points = []
        for part in geom.geoms:
            points.extend(_intersection_points(part))
        return points
    return []


def _member_midpoint(member: dict[str, Any]) -> Point2D:
    line = LineString(member["geometry"])
    point = line.interpolate(0.5, normalized=True)
    return (float(point.x), float(point.y))


def _outline_layer(kind: str) -> str:
    if kind == "waling":
        return "WALING_OUTLINE"
    if kind in {"truss_chord", "truss_web"}:
        return "TRUSS_CHORD" if kind == "truss_chord" else "STRUT_OUTLINE"
    return "STRUT_OUTLINE"
