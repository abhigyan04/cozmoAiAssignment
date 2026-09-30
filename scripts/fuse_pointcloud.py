"""Sanity check: fuse every Nth LiDAR frame into one world-frame point cloud."""
import argparse
import sys
from pathlib import Path

import numpy as np
import open3d as o3d

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from floorplan.io.stray import StrayCapture  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("scan")
ap.add_argument("--stride", type=int, default=10)
ap.add_argument("--out", default="out/fused.ply")
args = ap.parse_args()

cap = StrayCapture(args.scan)
pts = np.concatenate([cap.points_world(i) for i in range(0, len(cap.frames), args.stride)])
pcd = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(pts)).voxel_down_sample(0.02)
P = np.asarray(pcd.points)
print(f"{len(cap.frames)} frames -> {len(P)} points after 2cm voxel")
print("extent min", P.min(0).round(2), "max", P.max(0).round(2))
# ARKit world is gravity-aligned with +y up: floor/ceiling should be y-histogram peaks.
hist, edges = np.histogram(P[:, 1], bins=np.arange(P[:, 1].min(), P[:, 1].max() + 0.02, 0.02))
for k in np.argsort(hist)[-4:][::-1]:
    print(f"  y={edges[k]:+.2f} m  count={hist[k]}")
Path(args.out).parent.mkdir(parents=True, exist_ok=True)
o3d.io.write_point_cloud(args.out, pcd)
print("wrote", args.out)
