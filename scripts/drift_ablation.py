"""Drift ablation: run the LiDAR pipeline with drift correction off and on, and
overlay the two stitched footprints.

Reported per run: wall sharpness (share of wall points within 1 cm of their
wall plane; higher = more consistent poses), number of rooms, total footprint.
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
from floorplan.lidar import run_lidar  # noqa: E402


def world_polygons(res):
    """Room polygons back in world (x, z) so both runs share one frame."""
    return [rp.vertices @ res.fm.R for rp in res.polys]   # R is orthonormal: inverse = transpose


for scan in sys.argv[1:]:
    cap = StrayCapture(scan)
    runs = {}
    for mode in ("off", "on"):
        t = time.time()
        runs[mode] = run_lidar(cap, drift=mode)
        r = runs[mode]
        area = sum(rp.area for rp in r.polys)
        extra = ""
        if r.drift:
            extra = (f"  max heading drift {r.drift.max_abs_drift_deg:.2f} deg,"
                     f" loop closure {'applied' if r.drift.loop_closed else 'skipped (not well-conditioned)'}")
        print(f"{Path(scan).name} drift={mode}: sharpness {r.sharpness:.3f}, {len(r.polys)} rooms,"
              f" footprint {area:.2f} m2{extra}  ({time.time() - t:.0f}s)")

    fig, ax = plt.subplots(figsize=(10, 10))
    for mode, colour in (("off", "tab:red"), ("on", "tab:blue")):
        for k, V in enumerate(world_polygons(runs[mode])):
            V = np.vstack([V, V[:1]])
            ax.plot(V[:, 0], V[:, 1], "-", color=colour, lw=1.5, label=f"drift {mode}" if k == 0 else None)
    ax.set_aspect("equal")
    ax.legend()
    ax.set_title(f"{Path(scan).name}: stitched footprint, drift correction off (red) vs on (blue)")
    out = Path("out") / f"drift_ablation_{Path(scan).name}.png"
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out, dpi=80)
    print("  saved", out)