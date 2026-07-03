"""Geometry engine for foundation pit internal strut layouts.

The engine keeps the legacy drawing fields (``waling``, ``corners``,
``struts``, ``ties`` and ``pillars``) while also producing a node/member model
that validation, statistics and DXF output can use without guessing a member's
meaning from the old bucket names.
"""

from __future__ import annotations

from math import ceil, cos, pi, sin
from typing import Any

from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon


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
            "tie_ratio": [1.0 / 3.0, 2.0 / 3.0],
            "tie_interval": 14.0,
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
            "truss_web_with_main": "warren",
            "truss_web_without_main": "k",
            "node_snap_tolerance": 1e-3,
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
            "tie_interval",
            "min_strut_len",
            "core_clearance",
            "ring_edge_clearance",
            "radial_spacing_min",
            "radial_spacing_max",
            "truss_depth",
            "truss_panel_min",
            "truss_panel_max",
            "node_snap_tolerance",
        ):
            if params[key] is not None:
                params[key] = float(params[key])
        if params["pillar_min_spacing"] is None:
            params["pillar_min_spacing"] = params["spacing_min"]

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
        elif system in {"opposite_strut", "straight_truss"}:
            self.solve_opposite_strut(layout)
        elif system == "circular":
            self.solve_circular(layout)
        else:  # pragma: no cover - guarded by parameter normalization.
            raise ValueError(f"unsupported support_system {system!r}")

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
        struts = self._place_main_struts(layout, waling_poly, include_x=True, include_y=True)
        self._place_single_direction_ties(layout, struts, waling_poly)
        self._place_secondary_perimeter_supports(layout, waling_poly)
        if self._uses_large_corner_truss(waling_poly):
            self._place_edge_truss(layout, waling_poly)
            self._place_corner_trusses(layout, waling_poly)
        else:
            self._place_corner_struts(layout, waling_poly)
        self._add_structural_cross_nodes(layout)
        self._place_pillars_from_nodes(layout, waling_poly)

    def solve_opposite_strut(self, layout: dict[str, Any]) -> None:
        waling_poly = self._place_waling(layout)
        struts = self._place_main_struts(layout, waling_poly, include_x=True, include_y=True)
        self._place_single_direction_ties(layout, struts, waling_poly)
        self._place_opposite_strut_y_ties(layout, struts, waling_poly)
        self._add_structural_cross_nodes(layout)
        self._place_pillars_from_nodes(layout, waling_poly)

    def solve_straight_truss(self, layout: dict[str, Any]) -> None:
        self.solve_opposite_strut(layout)

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
        waling_poly = self._offset_poly(self.params["waling_offset"]) or self.poly
        coords = _closed_coords(list(waling_poly.exterior.coords))
        layout["waling"] = coords
        self._add_member(
            layout,
            kind="waling",
            geometry=coords,
            width=self.params["waling_width"],
            node_kind="waling_point",
            closed=True,
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
            if y_high - y_low < panel:
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
                    webs = [(left_low, right_high)] if i % 2 == 0 else [(right_low, left_high)]
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

    def _place_edge_truss(self, layout: dict[str, Any], waling_poly: Polygon) -> None:
        coords = _open_coords(_closed_coords(list(waling_poly.exterior.coords)))
        centroid = (float(waling_poly.centroid.x), float(waling_poly.centroid.y))
        depth = self.params["truss_depth"]
        bounds = waling_poly.bounds
        x_grid = self._support_grid_positions(bounds[0], bounds[2])
        y_grid = self._support_grid_positions(bounds[1], bounds[3])

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

            edge_depth = max(depth, float(self.params["spacing_min"]) * 0.75)
            outer_nodes = self._edge_truss_nodes(
                start,
                end,
                x_grid=x_grid,
                y_grid=y_grid,
                target_panel=edge_depth,
            )
            outer_nodes = self._merge_edge_main_strut_anchors(layout, outer_nodes, start, end)
            if len(outer_nodes) < 2:
                continue
            inner_nodes = [
                (outer[0] + inward[0] * edge_depth, outer[1] + inward[1] * edge_depth)
                for outer in outer_nodes
            ]

            for index in range(len(outer_nodes) - 1):
                members = [
                    ("truss_chord", [outer_nodes[index], outer_nodes[index + 1]]),
                    ("truss_chord", [inner_nodes[index], inner_nodes[index + 1]]),
                ]
                if index % 2 == 0:
                    members.append(("truss_web", [outer_nodes[index], inner_nodes[index + 1]]))
                else:
                    members.append(("truss_web", [inner_nodes[index], outer_nodes[index + 1]]))
                for kind, member in members:
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
            for layer in range(layers):
                target = first_offset + layer_step * layer
                left = self._edge_truss_node_near(layout, corner, prev_pt, target)
                right = self._edge_truss_node_near(layout, corner, next_pt, target)
                if left is None or right is None:
                    continue
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

        for left, right in self._paired_group_struts(by_axis["x"], axis="x"):
            left_geom = left["member"]["geometry"]
            right_geom = right["member"]["geometry"]
            y_min = max(min(left_geom[0][1], left_geom[-1][1]), min(right_geom[0][1], right_geom[-1][1]))
            y_max = min(max(left_geom[0][1], left_geom[-1][1]), max(right_geom[0][1], right_geom[-1][1]))
            if y_max - y_min < self.params["spacing_min"]:
                continue

            for y in self._coupling_positions(y_min, y_max):
                candidate = [(left_geom[0][0], y), (right_geom[0][0], y)]
                line = LineString(candidate)
                if not waling_poly.buffer(1e-6).covers(line):
                    continue
                if not self._candidate_clear(layout, candidate, {"corner", "tie"}):
                    continue
                self._add_linear_member(
                    layout,
                    "tie",
                    candidate,
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

            for x in self._coupling_positions(x_min, x_max):
                y_bottom = bottom_geom[0][1]
                y_top = top_geom[0][1]
                candidate = [(x, y_bottom), (x, y_top)]
                line = LineString(candidate)
                if not waling_poly.buffer(1e-6).covers(line):
                    continue
                if not self._candidate_clear(layout, candidate, {"corner", "tie"}):
                    continue
                self._add_linear_member(
                    layout,
                    "tie",
                    candidate,
                    old_key="ties",
                    node_kind="truss_node",
                )

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
        if abs(start[1] - end[1]) <= 1e-6:
            for group in _group_axis_points(edge_points, axis="x", max_gap=float(self.params["spacing_min"])):
                anchors.append((round(sum(point[0] for point in group) / len(group), 6), round(start[1], 6)))
        elif abs(start[0] - end[0]) <= 1e-6:
            for group in _group_axis_points(edge_points, axis="y", max_gap=float(self.params["spacing_min"])):
                anchors.append((round(start[0], 6), round(sum(point[1] for point in group) / len(group), 6)))
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
                if not any(abs(point[0] - anchor_x) <= merge_tol for anchor_x in anchor_xs)
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
                if not any(abs(point[1] - anchor_y) <= merge_tol for anchor_y in anchor_ys)
            ]
            for anchor in anchors:
                if not lo - 1e-6 <= anchor[1] <= hi + 1e-6:
                    continue
                ys.append(anchor[1])
            return [(x, y) for y in sorted(set(ys))]

        return nodes

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
                    elif _is_endpoint(point, left["geometry"]) or _is_endpoint(point, right["geometry"]):
                        node_kind = "truss_node"
                    else:
                        node_kind = "truss_node|strut_cross"
                    self._add_node(
                        layout,
                        point,
                        node_kind,
                        [left["id"], right["id"]],
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

    def _add_node(
        self,
        layout: dict[str, Any],
        pos: Point2D,
        kind: str,
        source: list[str] | None = None,
    ) -> str:
        snap_tol = float(self.params["node_snap_tolerance"])
        for node in layout["nodes"]:
            if Point(node["pos"]).distance(Point(pos)) <= snap_tol:
                node_id = node["id"]
                node["kind"] = _merge_node_kind(node["kind"], kind)
                if source:
                    node["source"] = sorted(set(node["source"]) | set(source))
                key = (round(float(pos[0]) * 1000), round(float(pos[1]) * 1000))
                self._node_index[key] = node_id
                return str(node_id)

        key = (round(float(pos[0]) * 1000), round(float(pos[1]) * 1000))
        node_id = f"N{self._node_seq:03d}"
        self._node_seq += 1
        self._node_index[key] = node_id
        layout["nodes"].append({
            "id": node_id,
            "pos": (float(pos[0]), float(pos[1])),
            "kind": kind,
            "source": list(source or []),
            "system": self.params["support_system"],
        })
        return node_id

    def _add_member(
        self,
        layout: dict[str, Any],
        kind: str,
        geometry: list[tuple[float, float]],
        width: float,
        *,
        node_kind: str,
        closed: bool = False,
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
    ) -> dict[str, Any] | None:
        width = self.params["tie_width"] if kind == "tie" else self.params["main_width"]
        if kind == "waling":
            width = self.params["waling_width"]
        member = self._add_member(layout, kind, geometry, width, node_kind=node_kind)
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
        for score, point in candidates:
            if score < 90 and any(Point(point).distance(Point(existing)) < min_spacing for existing in selected):
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
        layout["issues"] = report["issues"]

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

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
