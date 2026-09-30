"""Detect doors, windows and passages on every wall and save the unrolled-wall images.

Each panel is one wall seen face-on: red = LiDAR rays passed through, blue = rays
hit the wall, white = never observed. Green boxes are detected openings.
"""
import sys
import time
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from floorplan.io.stray import StrayCapture  # noqa: E402
from floorplan.geometry.structure import fuse, floor_and_ceiling, manhattan_yaw  # noqa: E402
from floorplan.geometry.floormap import build_floormap, find_doorways, segment_rooms  # noqa: E402
from floorplan.geometry.polygon import room_polygon  # noqa: E402
from floorplan.geometry.openings import wall_evidence, detect_openings  # noqa: E402

DEFAULT_CEILING = 2.6  # only used to size the wall images when no ceiling was captured

for scan in sys.argv[1:]:
    t = time.time()
    cap = StrayCapture(scan)
    pcd = fuse(cap)
    P, N = np.asarray(pcd.points), np.asarray(pcd.normals)
    floor, ceil = floor_and_ceiling(P, N)
    top = ceil.y - floor.y if ceil else DEFAULT_CEILING
    fm = build_floormap(cap, P, N, floor.y, manhattan_yaw(N))
    rooms = segment_rooms(fm, find_doorways(fm))
    polys = [room_polygon(rooms == k, fm, P, N, floor.y) for k in range(1, rooms.max() + 1)]
    walls = wall_evidence(cap, fm, floor.y, polys, top)
    openings = detect_openings(walls, top)

    print(f"{Path(scan).name}: {len(openings)} openings  ({time.time() - t:.0f}s)")
    for o in openings:
        print(f"  R{o.room + 1} wall {o.wall:2d}  {o.kind:8s} width {o.width:.3f} +/- {o.width_sigma * 100:.1f} cm"
              f"  height {o.bottom:.2f}-{o.top:.2f} m")

    cols = 5
    rows = (len(walls) + cols - 1) // cols
    fig, axs = plt.subplots(rows, cols, figsize=(4 * cols, 2.6 * rows), squeeze=False)
    for ax, w in zip(axs.flat, walls):
        tot = w["hit"] + w["pas"]
        frac = np.where(tot >= 2, w["pas"] / np.maximum(tot, 1), np.nan)
        ax.imshow(frac.T, origin="lower", extent=[w["lo"], w["hi"], 0, top], cmap="coolwarm", vmin=0, vmax=1)
        for o in openings:
            if (o.room, o.wall) == (w["room"], w["wall"]):
                ax.add_patch(plt.Rectangle((o.u0, o.bottom), o.width, o.top - o.bottom, fill=False, ec="lime", lw=2))
                ax.text(o.u0, o.top, f"{o.kind} {o.width:.2f}", color="green", fontsize=8)
        ax.set_title(f"R{w['room'] + 1} wall {w['wall']}", fontsize=8)
    for ax in axs.flat[len(walls):]:
        ax.axis("off")
    fig.tight_layout()
    out = Path("out") / f"openings_{Path(scan).name}.png"
    fig.savefig(out, dpi=60)
    print("  saved", out)