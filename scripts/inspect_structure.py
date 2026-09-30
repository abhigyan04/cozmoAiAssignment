"""Print floor, ceiling height and wall orientation for one or more LiDAR scans."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from floorplan.io.stray import StrayCapture  # noqa: E402
from floorplan.geometry.structure import fuse, floor_and_ceiling, manhattan_yaw  # noqa: E402

for scan in sys.argv[1:]:
    cap = StrayCapture(scan)
    pcd = fuse(cap)
    P, N = np.asarray(pcd.points), np.asarray(pcd.normals)
    f, c = floor_and_ceiling(P, N)
    ceiling = (f"ceiling y={c.y:.3f}  height={c.y - f.y:.3f} m +/- {np.hypot(f.sigma, c.sigma) * 100:.1f} cm"
               if c else "ceiling: NOT CAPTURED")
    print(f"{Path(scan).name}: floor y={f.y:.3f} (n={f.support})  {ceiling}  yaw={manhattan_yaw(N):.2f} deg")