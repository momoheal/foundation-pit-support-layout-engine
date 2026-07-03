"""Tkinter entry point and DXF export helpers for internal strut layouts."""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

import ezdxf

from strut_engine import StrutEngine


LAYER_COLORS = {
    "WALL_REF": 1,
    "WALING": 6,
    "STRUT": 4,
    "CORNER": 2,
    "TIE": 8,
    "TRUSS_WEB": 30,
    "RING_STRUT": 140,
    "RADIAL_STRUT": 5,
    "PILLAR": 7,
    "STRUT_OUTLINE": 9,
    "WALING_OUTLINE": 213,
    "TRUSS_CHORD": 3,
    "DEBUG_NODE": 1,
    "DEBUG_ISSUE": 1,
    "CORE_PROTECTION": 1,
}

MEMBER_LAYERS = {
    "waling": "WALING",
    "main_strut": "STRUT",
    "corner": "CORNER",
    "haunch": "CORNER",
    "tie": "TIE",
    "truss_web": "TRUSS_WEB",
    "truss_chord": "TRUSS_CHORD",
    "ring_strut": "RING_STRUT",
    "radial_strut": "RADIAL_STRUT",
}


def export_strut_dxf(
    path: str | Path,
    boundary: list[tuple[float, float]],
    layout: dict[str, Any],
) -> None:
    """Write a strut layout to DXF with the documented layer set."""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    _ensure_layers(doc)

    msp.add_lwpolyline(boundary, close=True, dxfattribs={"layer": "WALL_REF"})

    members = layout.get("members") or []
    if members:
        for member in members:
            layer = MEMBER_LAYERS.get(member.get("kind"), "DEBUG_NODE")
            geometry = member.get("geometry", [])
            if len(geometry) >= 2:
                msp.add_lwpolyline(
                    geometry,
                    close=member.get("kind") in {"waling", "ring_strut"},
                    dxfattribs={"layer": layer},
                )
    else:
        _draw_legacy_layout(msp, layout)

    for outline in layout.get("outlines", []):
        geometry = outline.get("geometry", [])
        if len(geometry) >= 2:
            msp.add_lwpolyline(
                geometry,
                close=bool(outline.get("closed", True)),
                dxfattribs={"layer": outline.get("layer", "STRUT_OUTLINE")},
            )

    for point in layout.get("pillars", []):
        size = 0.4
        x, y = point
        msp.add_lwpolyline(
            [(x - size, y - size), (x + size, y - size),
             (x + size, y + size), (x - size, y + size)],
            close=True,
            dxfattribs={"layer": "PILLAR"},
        )

    for node in layout.get("nodes", []):
        x, y = node["pos"]
        msp.add_circle((x, y), radius=0.12, dxfattribs={"layer": "DEBUG_NODE"})

    for issue in layout.get("issues", []):
        point = issue.get("point")
        if point:
            x, y = point
            msp.add_circle((x, y), radius=0.25, dxfattribs={"layer": "DEBUG_ISSUE"})

    doc.saveas(str(path))


def _ensure_layers(doc: Any) -> None:
    for name, color in LAYER_COLORS.items():
        if name not in doc.layers:
            doc.layers.new(name, dxfattribs={"color": color})


def _draw_legacy_layout(msp: Any, layout: dict[str, Any]) -> None:
    if layout.get("waling"):
        msp.add_lwpolyline(layout["waling"], close=True, dxfattribs={"layer": "WALING"})
    for key, layer in (("struts", "STRUT"), ("corners", "CORNER"), ("ties", "TIE")):
        for segment in layout.get(key, []):
            if len(segment) >= 2:
                msp.add_lwpolyline(segment[:2], dxfattribs={"layer": layer})


class StrutApp:
    """Small GUI wrapper; the algorithm remains fully usable without Tkinter."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Internal Strut Layout")
        self.root.geometry("520x660")
        self.root.resizable(False, False)

        frame = ttk.Frame(root, padding=18)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Internal Strut Layout", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 14)
        )

        self.support_system = tk.StringVar(value="orthogonal")
        self.strut_material = tk.StringVar(value="steel")
        self.spacing_min = tk.DoubleVar(value=6.0)
        self.spacing_max = tk.DoubleVar(value=9.0)
        self.spacing = tk.DoubleVar(value=9.0)
        self.waling_offset = tk.DoubleVar(value=5.0)
        self.safe_dist = tk.DoubleVar(value=2.5)
        self.main_width = tk.DoubleVar(value=0.8)
        self.tie_width = tk.DoubleVar(value=0.3)
        self.waling_width = tk.DoubleVar(value=0.8)
        self.pillar_min_spacing = tk.DoubleVar(value=6.0)
        self.enable_haunch = tk.BooleanVar(value=False)
        self.core_x = tk.DoubleVar(value=30.0)
        self.core_y = tk.DoubleVar(value=20.0)
        self.core_diameter = tk.DoubleVar(value=8.0)
        self.core_clearance = tk.DoubleVar(value=2.0)
        self.ring_edge_clearance = tk.DoubleVar(value=5.0)
        self.radial_spacing_min = tk.DoubleVar(value=6.0)
        self.radial_spacing_max = tk.DoubleVar(value=9.0)
        self.radial_count = tk.IntVar(value=0)
        self.truss_depth = tk.DoubleVar(value=0.8)
        self.truss_panel_min = tk.DoubleVar(value=6.0)
        self.truss_panel_max = tk.DoubleVar(value=9.0)
        self.truss_web_with_main = tk.StringVar(value="warren")
        self.truss_web_without_main = tk.StringVar(value="k")

        row = 1
        row = self._combo(frame, row, "Support system", self.support_system,
                          ("orthogonal", "brace", "straight_truss", "circular"))
        row = self._combo(frame, row, "Material", self.strut_material, ("steel", "concrete"))
        for label, var in (
            ("Spacing min", self.spacing_min),
            ("Spacing max", self.spacing_max),
            ("Spacing", self.spacing),
            ("Waling offset", self.waling_offset),
            ("Safe distance", self.safe_dist),
            ("Main width", self.main_width),
            ("Tie width", self.tie_width),
            ("Waling width", self.waling_width),
            ("Pillar min spacing", self.pillar_min_spacing),
            ("Core center X", self.core_x),
            ("Core center Y", self.core_y),
            ("Core diameter", self.core_diameter),
            ("Core clearance", self.core_clearance),
            ("Ring edge clearance", self.ring_edge_clearance),
            ("Radial spacing min", self.radial_spacing_min),
            ("Radial spacing max", self.radial_spacing_max),
            ("Radial count (0=auto)", self.radial_count),
            ("Truss depth", self.truss_depth),
            ("Truss panel min", self.truss_panel_min),
            ("Truss panel max", self.truss_panel_max),
        ):
            row = self._entry(frame, row, label, var)

        row = self._combo(frame, row, "Truss web with main", self.truss_web_with_main, ("warren", "k"))
        row = self._combo(frame, row, "Truss web without main", self.truss_web_without_main, ("k", "warren"))

        ttk.Checkbutton(frame, text="Enable haunch", variable=self.enable_haunch).grid(
            row=row, column=1, sticky="w", pady=4
        )
        row += 1

        ttk.Button(frame, text="Load DXF and Export Struts", command=self.run).grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=(18, 6)
        )
        row += 1
        ttk.Button(
            frame,
            text="Export 60 x 40 Test Boundary",
            command=self._use_test_boundary,
        ).grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=6
        )
        row += 1

        self.status = ttk.Label(frame, text="Ready")
        self.status.grid(row=row, column=0, columnspan=2, sticky="w", pady=(18, 0))

    def _entry(self, parent: ttk.Frame, row: int, label: str, variable: tk.Variable) -> int:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=variable, width=18).grid(
            row=row, column=1, sticky="w", pady=4
        )
        return row + 1

    def _combo(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        values: tuple[str, ...],
    ) -> int:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(parent, textvariable=variable, values=values, state="readonly", width=18).grid(
            row=row, column=1, sticky="w", pady=4
        )
        return row + 1

    def _params(self) -> dict[str, Any]:
        params = {
            "support_system": self.support_system.get(),
            "strut_material": self.strut_material.get(),
            "spacing_min": self.spacing_min.get(),
            "spacing_max": self.spacing_max.get(),
            "spacing": self.spacing.get(),
            "waling_offset": self.waling_offset.get(),
            "safe_dist": self.safe_dist.get(),
            "main_width": self.main_width.get(),
            "tie_width": self.tie_width.get(),
            "waling_width": self.waling_width.get(),
            "pillar_min_spacing": self.pillar_min_spacing.get(),
            "enable_haunch": self.enable_haunch.get(),
            "truss_depth": self.truss_depth.get(),
            "truss_panel_min": self.truss_panel_min.get(),
            "truss_panel_max": self.truss_panel_max.get(),
            "truss_web_with_main": self.truss_web_with_main.get(),
            "truss_web_without_main": self.truss_web_without_main.get(),
        }
        if params["support_system"] == "circular":
            radial_count = self.radial_count.get()
            params.update({
                "core_center": (self.core_x.get(), self.core_y.get()),
                "core_diameter": self.core_diameter.get(),
                "core_clearance": self.core_clearance.get(),
                "ring_edge_clearance": self.ring_edge_clearance.get(),
                "radial_spacing_min": self.radial_spacing_min.get(),
                "radial_spacing_max": self.radial_spacing_max.get(),
                "radial_count": radial_count if radial_count > 0 else None,
            })
        return params

    def _load_coords(self, doc: Any) -> list[tuple[float, float]]:
        msp = doc.modelspace()
        polylines = list(msp.query("LWPOLYLINE")) or list(msp.query("POLYLINE"))
        if polylines:
            coords = [(float(x), float(y)) for x, y in polylines[0].get_points(format="xy")]
        else:
            lines = [entity for entity in msp if entity.dxftype() == "LINE"]
            if not lines:
                raise ValueError("DXF does not contain a usable boundary")
            points = set()
            for line in lines:
                points.add((float(line.dxf.start.x), float(line.dxf.start.y)))
                points.add((float(line.dxf.end.x), float(line.dxf.end.y)))
            cx = sum(point[0] for point in points) / len(points)
            cy = sum(point[1] for point in points) / len(points)
            from math import atan2

            coords = sorted(points, key=lambda point: atan2(point[1] - cy, point[0] - cx))
        if len(coords) >= 3 and coords[0] != coords[-1]:
            coords.append(coords[0])
        return coords

    def _load_core_center(self, doc: Any) -> tuple[float, float] | None:
        points = list(doc.modelspace().query("POINT"))
        if not points:
            return None
        point = points[0].dxf.location
        return (float(point.x), float(point.y))

    def run(self) -> None:
        source = filedialog.askopenfilename(
            title="Choose pit boundary DXF",
            filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")],
        )
        if not source:
            return
        try:
            doc_in = ezdxf.readfile(source)
            coords = self._load_coords(doc_in)
            params = self._params()
            if params["support_system"] == "circular":
                selected_center = self._load_core_center(doc_in)
                if selected_center is not None:
                    params["core_center"] = selected_center
            layout = StrutEngine(coords, params).solve()
            output = str(Path(source).with_name(Path(source).stem + "_strut.dxf"))
            export_strut_dxf(output, coords, layout)
            self.status.config(text=f"Exported {output}")
            messagebox.showinfo("Export complete", self._summary(layout, output))
        except Exception as exc:
            self.status.config(text=f"Failed: {exc}")
            messagebox.showerror("Strut layout failed", str(exc))

    def _use_test_boundary(self) -> None:
        output = filedialog.asksaveasfilename(
            title="Save test strut DXF",
            defaultextension=".dxf",
            filetypes=[("DXF files", "*.dxf")],
        )
        if not output:
            return
        try:
            coords = [(0.0, 0.0), (60.0, 0.0), (60.0, 40.0), (0.0, 40.0)]
            layout = StrutEngine(coords, self._params()).solve()
            export_strut_dxf(output, coords, layout)
            self.status.config(text=f"Exported {output}")
            messagebox.showinfo("Export complete", self._summary(layout, output))
        except Exception as exc:
            self.status.config(text=f"Failed: {exc}")
            messagebox.showerror("Strut layout failed", str(exc))

    def _summary(self, layout: dict[str, Any], output: str) -> str:
        stats = layout.get("stats", {})
        return (
            f"Members: {len(layout.get('members', []))}\n"
            f"Nodes: {len(layout.get('nodes', []))}\n"
            f"Pillars: {len(layout.get('pillars', []))}\n"
            f"Total support length: {stats.get('total_support_length', 0.0):.2f}\n"
            f"Output: {output}"
        )


if __name__ == "__main__":
    root = tk.Tk()
    StrutApp(root)
    root.mainloop()
