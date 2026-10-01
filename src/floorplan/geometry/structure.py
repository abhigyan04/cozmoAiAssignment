"""Room structure from a fused, gravity-aligned point cloud (world +y is up).

Floor and ceiling are horizontal planes, so we find them as peaks in the
height histogram of upward/downward-facing points, then refine each with a
robust mean of the inliers. Walls are vertical, and indoor walls are
overwhelmingly Manhattan (at 90 degrees to each other), so one dominant
yaw angle describes them all.
"""
from dataclasses import dataclass

import numpy as np
import open3d as o3d

from floorplan.io.stray import StrayCapture

@dataclass
class Level:
    y: float           # height in world frame, metres
    sigma: float       # 1-sigma uncertainty of y, metres
    support: int       # number of inlier points


def fuse(cap: StrayCapture, stride: int = 10, voxel: float = 0.02) -> o3d.geometry.PointCloud:
    """Fuse every `stride`-th depth frame and estimate normals."""
    pts = np.concatenate([cap.points_world(i) for i in range(0, len(cap.frames), stride)])
    pcd = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(pts)).voxel_down_sample(voxel)
    pcd.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=4 * voxel, max_nn=30))
    return pcd


def _refine_level(y: np.ndarray, y0: float, band: float = 0.03) -> Level:
    inl = y[np.abs(y - y0) < band]
    med = np.median(inl)
    mad = 1.4826 * np.median(np.abs(inl - med))  # robust std of the plane's thickness
    # Surface noise averages out over many points, so the statistical term is tiny;
    # the floor (0.5 cm) keeps us honest about LiDAR bias that averaging cannot remove.
    sigma = float(np.hypot(mad / np.sqrt(len(inl)), 0.005))
    return Level(float(med), sigma, int(len(inl)))


def floor_and_ceiling(P: np.ndarray, N: np.ndarray, min_room_h: float = 1.8,
                      min_support: int = 2000, cam_y: float | None = None) -> tuple[Level, Level | None]:
    """Floor = lowest strong horizontal plane; ceiling = highest one >= 1.8 m above it.

    cam_y (median camera height, if known): the floor must lie below the cameras.
    A scan that looks up a lot (as the protocol asks, for the ceiling) can see far
    more ceiling than floor, especially with a bed covering it, so only peaks below
    the cameras are floor candidates, with a lower support threshold (5 %)."""
    horiz = np.abs(N[:, 1]) > 0.9
    y = P[horiz, 1]
    hist, edges = np.histogram(y, bins=np.arange(y.min(), y.max() + 0.01, 0.01))
    if cam_y is not None and (edges[:-1] < cam_y - 0.5).any():
        below = edges[:-1] < cam_y - 0.5
        hb = np.where(below, hist, 0)
        strong = np.nonzero(hb >= max(hb.max() * 0.05, 200))[0]
        if not len(strong):
            strong = np.nonzero(hist >= max(hist.max() * 0.2, 200))[0]
    else:
        strong = np.nonzero(hist >= max(hist.max() * 0.2, 200))[0]
    floor = _refine_level(y, edges[strong.min()] + 0.005)

    up = y[y > floor.y + min_room_h]
    if len(up) < min_support:
        return floor, None  # ceiling not captured: report it rather than guess
    h2, e2 = np.histogram(up, bins=np.arange(up.min(), up.max() + 0.01, 0.01))
    ceil = _refine_level(up, e2[np.argmax(h2)] + 0.005)
    return floor, (ceil if ceil.support >= min_support else None)


def manhattan_yaw(N: np.ndarray) -> float:
    """Dominant wall direction in degrees, in [0, 90), from vertical-surface normals."""
    vert = np.abs(N[:, 1]) < 0.2
    ang = np.degrees(np.arctan2(N[vert, 2], N[vert, 0])) % 90.0
    # Circular mean on the 90-degree circle (angle*4 maps it onto a full circle).
    hist, edges = np.histogram(ang, bins=180, range=(0, 90))
    peak = edges[np.argmax(hist)] + 0.25
    near = ang[np.abs(((ang - peak + 45) % 90) - 45) < 3]
    z = np.exp(1j * np.radians(near) * 4).mean()
    return float(np.degrees(np.angle(z)) / 4 % 90)