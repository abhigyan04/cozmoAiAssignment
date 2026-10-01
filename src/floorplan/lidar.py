"""LiDAR-tier geometry pipeline: capture -> rooms, walls, openings, heights."""
from dataclasses import dataclass

import numpy as np

from floorplan.io.stray import StrayCapture
from floorplan.geometry.drift import DriftReport, correct_drift, wall_sharpness
from floorplan.geometry.floormap import BAND, FloorMap, build_floormap, find_doorways, segment_rooms, wall_band
from floorplan.geometry.openings import Opening, detect_openings, wall_evidence
from floorplan.geometry.polygon import RoomPolygon, room_polygon
from floorplan.geometry.stitch import RoomHeights, SharedOpening, adjacency, pair_openings, room_heights
from floorplan.geometry.structure import Level, floor_and_ceiling, fuse, manhattan_yaw
from floorplan.uncertainty import widen_for_scale

DEFAULT_CEILING = 2.6  # sizes wall images only, when no ceiling was captured


@dataclass
class LidarResult:
    floor: Level
    ceiling: Level | None
    yaw: float
    fm: FloorMap
    rooms: np.ndarray
    polys: list[RoomPolygon]
    heights: list[RoomHeights]
    openings: list[Opening]
    shared: list[SharedOpening]
    edges: list[dict]
    sharpness: float
    drift: DriftReport | None
    drift_applied: bool


def _fused(cap: StrayCapture, stride: int = 10):
    pcd = fuse(cap, stride=stride)
    P, N = np.asarray(pcd.points), np.asarray(pcd.normals)
    return P, N, manhattan_yaw(N)


def run_lidar(cap: StrayCapture, drift: str = "auto", stride: int = 10,
              rays_per_frame: int = 3000, scale_sigma: float = 0.0) -> LidarResult:
    """drift: "off" = poses as recorded, "on" = always correct, "auto" = correct only
    if it makes the walls measurably crisper (guards against correcting noise).

    stride / rays_per_frame: LiDAR has ~45 frames/s and needs subsampling; image-only
    tiers have ~1 keyframe/s and use every frame. scale_sigma: relative scale
    uncertainty added to every measurement (0 for LiDAR, whose depth is metric)."""
    fps = getattr(cap, "fps", 45.0)
    P, N, yaw = _fused(cap, stride)
    sharp = wall_sharpness(P, N, yaw)
    rep, applied = None, False
    if drift in ("on", "auto"):
        cc, rep = correct_drift(cap, yaw, fps_hint=fps, window_s=max(2.0, 8.0 / fps))
        P2, N2, yaw2 = _fused(cc, stride)
        sharp2 = wall_sharpness(P2, N2, yaw2)
        if drift == "on" or sharp2 > sharp + 0.005:
            cap, P, N, yaw, sharp, applied = cc, P2, N2, yaw2, sharp2, True

    floor, ceil = floor_and_ceiling(P, N)
    band = wall_band(ceil.y - floor.y if ceil else None)
    fm = build_floormap(cap, P, N, floor.y, yaw, stride=stride, rays_per_frame=rays_per_frame)
    doors = find_doorways(fm)
    rooms = segment_rooms(fm, doors)
    refine = band if band != BAND else (0.3, 2.4)   # no ceiling: refine on full wall height as before
    polys = [room_polygon(rooms == k, fm, P, N, floor.y, refine) for k in range(1, rooms.max() + 1)]
    heights = room_heights(P, N, fm, rooms)
    top = ceil.y - floor.y if ceil else DEFAULT_CEILING
    openings = detect_openings(wall_evidence(cap, fm, floor.y, polys, top, stride=max(stride // 2, 1),
                                              max_pts=2 * rays_per_frame), top)
    if scale_sigma:
        widen_for_scale(polys, heights, openings, scale_sigma)
    shared = pair_openings(openings, polys)
    edges = adjacency(doors, rooms, shared, fm)
    return LidarResult(floor, ceil, yaw, fm, rooms, polys, heights, openings, shared, edges,
                       sharp, rep, applied)