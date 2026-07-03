"""Visual diagnostics for internal strut layouts."""

from __future__ import annotations

from pathlib import Path
from typing import Any


MEMBER_STYLES = {
    "waling": {"color": "#d946ef", "linewidth": 2.6, "zorder": 5},
    "main_strut": {"color": "#2563eb", "linewidth": 1.8, "zorder": 4},
    "truss_chord": {"color": "#16a34a", "linewidth": 1.6, "zorder": 6},
    "truss_web": {"color": "#f97316", "linewidth": 1.0, "zorder": 7},
    "tie": {"color": "#64748b", "linewidth": 0.9, "zorder": 3},
    "corner": {"color": "#eab308", "linewidth": 1.4, "zorder": 4},
    "ring_strut": {"color": "#0d9488", "linewidth": 1.8, "zorder": 4},
    "radial_strut": {"color": "#7c3aed", "linewidth": 1.2, "zorder": 4},
}


def export_strut_diagnostic_png(
    path: str | Path,
    boundary: list[tuple[float, float]],
    layout: dict[str, Any],
    *,
    title: str | None = None,
) -> None:
    """Export a member-model diagnostic image that makes truss topology visible."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(12, 8))
    fig.patch.set_facecolor("#f8fafc")
    ax.set_facecolor("#ffffff")

    if boundary:
        closed_boundary = boundary + [boundary[0]]
        ax.plot(
            [point[0] for point in closed_boundary],
            [point[1] for point in closed_boundary],
            color="#111827",
            linewidth=1.4,
            linestyle="--",
            zorder=2,
        )

    for member in layout.get("members", []):
        geometry = member.get("geometry", [])
        if len(geometry) < 2:
            continue
        style = MEMBER_STYLES.get(member.get("kind"), {"color": "#334155", "linewidth": 0.8, "zorder": 1})
        ax.plot(
            [point[0] for point in geometry],
            [point[1] for point in geometry],
            color=style["color"],
            linewidth=style["linewidth"],
            solid_capstyle="round",
            zorder=style["zorder"],
        )

    if layout.get("pillars"):
        ax.scatter(
            [point[0] for point in layout["pillars"]],
            [point[1] for point in layout["pillars"]],
            marker="s",
            s=20,
            color="#7c3aed",
            zorder=8,
        )

    ax.set_aspect("equal", adjustable="box")
    ax.grid(color="#e5e7eb", linewidth=0.4)
    ax.set_title(title or "Strut diagnostic", fontsize=12)
    ax.margins(0.08)
    fig.tight_layout()
    fig.savefig(output, dpi=160)
    plt.close(fig)
