"""Segment a LiDAR capture into rooms and save a top-down picture of the result."""
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
from floorplan.geometry.floormap import RES, build_floormap, find_doorways, segment_rooms  # noqa: E402

for scan in sys.argv[1:]:
    t = time.time()
    cap = StrayCapture(scan)
    pcd = fuse(cap)
    P, N = np.asarray(pcd.points), np.asarray(pcd.normals)
    floor, _ = floor_and_ceiling(P, N)
    fm = build_floormap(cap, P, N, floor.y, manhattan_yaw(N))
    rooms = segment_rooms(fm, find_doorways(fm))
    areas = [(rooms == k).sum() * RES**2 for k in range(1, rooms.max() + 1)]
    print(f"{Path(scan).name}: {rooms.max()} rooms, areas m2 = {[round(float(a), 1) for a in areas]}  ({time.time() - t:.0f}s)")

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.imshow(np.ma.masked_equal(rooms, 0).T, origin="lower", cmap="tab10", interpolation="nearest")
    ax.imshow(np.ma.masked_equal(fm.wall * 1.0, 0).T, origin="lower", cmap="gray", interpolation="nearest")
    path = np.argwhere(fm.visited)
    ax.plot(path[:, 0], path[:, 1], "r.", ms=1)
    ax.set_title(f"{Path(scan).name}: rooms (colour), walls (black), camera path (red)")
    out = Path("out") / f"rooms_{Path(scan).name}.png"
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out, dpi=80)
    print("  saved", out)