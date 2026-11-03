"""Render enlarged Issue #2 joints directly from the generated geometry."""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strut_diagnostics import _member_style  # noqa: E402
from strut_engine import StrutEngine  # noqa: E402


def main() -> None:
    coords = [(0, 0), (60, 0), (60, 20), (30, 20), (30, 40), (0, 40)]
    layout = StrutEngine(coords, {'support_system': 'brace', 'spacing': 9,
                                 'waling_offset': 2, 'safe_dist': 1.5}).solve()
    panels = [
        ('Top edge: two diagonal rods meet each support node', (6, 24, 35, 43)),
        ('Right edge: no web crosses a main strut', (55, 63, 5, 15)),
        ('Reserved corner axes and continuous inner chords', (24, 35, 14, 25)),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(16, 6))
    for ax, (title, bounds) in zip(axes, panels):
        for member in layout['members']:
            xy = member['geometry']
            style = _member_style(member)
            ax.plot([p[0] for p in xy], [p[1] for p in xy], **style)
        nodes = [node['pos'] for node in layout['nodes']]
        ax.scatter([p[0] for p in nodes], [p[1] for p in nodes], s=18,
                   facecolors='white', edgecolors='black', zorder=10)
        boundary = coords + [coords[0]]
        ax.plot([p[0] for p in boundary], [p[1] for p in boundary], 'k--', linewidth=1)
        ax.set_xlim(bounds[:2])
        ax.set_ylim(bounds[2:])
        ax.set_aspect('equal')
        ax.grid(alpha=.2)
        ax.set_title(title, fontsize=10)
    fig.suptitle('Issue #2: actual geometry and registered nodes (metres)')
    fig.tight_layout()
    output = ROOT / 'engineering_check_outputs/review_issue2/joints.png'
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=170)
    plt.close(fig)
    print(output)


if __name__ == '__main__':
    main()
