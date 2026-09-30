"""Room polygons with refined wall lengths, drawn as a top-down plan.

Blue wall labels were located on raw 3D points (cm-level); red ones come from
the 5 cm grid only and carry a wider interval.
"""
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from floorplan.io.stray import StrayCapture  # noqa: E402
from floorplan.geometry.structure import fuse, floor_and_ceiling, manhattan_yaw  # noqa: E402
from floorplan.geometry.floormap import RES, build_floormap, find_doorways, segment_rooms  # noqa: E402
from floorplan.geometry.polygon import room_polygon  # noqa: E402

for scan in sys.argv[1:]:
    cap = StrayCapture(scan)
    pcd = fuse(cap)
    P, N = np.asarray(pcd.points), np.asarray(pcd.normals)
    floor, _ = floor_and_ceiling(P, N)
    fm = build_floormap(cap, P, N, floor.y, manhattan_yaw(N))
    rooms = segment_rooms(fm, find_doorways(fm))

    fig, ax = plt.subplots(figsize=(10, 10))
    wall_xy = np.argwhere(fm.wall) * RES + fm.origin
    ax.plot(wall_xy[:, 0], wall_xy[:, 1], "k,", alpha=0.4)
    print(f"{Path(scan).name}:")
    for k in range(1, rooms.max() + 1):
        rp = room_polygon(rooms == k, fm, P, N, floor.y)
        V = np.vstack([rp.vertices, rp.vertices[:1]])
        ax.plot(V[:, 0], V[:, 1], "-", lw=2)
        ax.text(*rp.vertices.mean(0), f"R{k}\n{rp.area:.2f} ± {rp.area_sigma:.2f} m²", ha="center")
        for i, (L, w) in enumerate(zip(rp.lengths, rp.walls)):
            mid = (rp.vertices[i] + rp.vertices[(i + 1) % len(rp.walls)]) / 2
            ax.text(*mid, f"{L:.2f}", fontsize=8, color="b" if w.refined else "r")
        walls = ", ".join(f"{L:.2f}+/-{s * 100:.1f}cm" for L, s in zip(rp.lengths, rp.length_sigmas))
        print(f"  R{k}: area {rp.area:.2f} +/- {rp.area_sigma:.2f} m2 | walls {walls}")
    ax.set_aspect("equal")
    ax.set_title(f"{Path(scan).name}: blue = refined on 3D points, red = grid only")
    out = Path("out") / f"plan_{Path(scan).name}.png"
    fig.savefig(out, dpi=80)
    print("  saved", out)