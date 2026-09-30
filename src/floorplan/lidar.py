"""LiDAR-tier geometry pipeline: capture -> rooms, walls, openings, heights."""
from dataclasses import dataclass

import numpy as np

from floorplan.io.stray import StrayCapture
from floorplan.geometry.drift import DriftReport, correct_drift, wall_sharpness
from floorplan.geometry.floormap import FloorMap, build_floormap, find_doorways, segment_rooms
from floorplan.geometry.openings import Opening, detect_openings, wall_evidence
from floorplan.geometry.polygon import RoomPolygon, room_polygon
from floorplan.geometry.structure import Level, floor_and_ceiling, fuse, manhattan_yaw

DEFAULT_CEILING = 2.6  # sizes wall images only, when no ceiling was captured


@dataclass
class LidarResult:
    floor: Level
    ceiling: Level | None
    yaw: float
    fm: FloorMap
    rooms: np.ndarray
    polys: list[RoomPolygon]
    openings: list[Opening]
    sharpness: float
    drift: DriftReport | None
    drift_applied: bool


def _fused(cap: StrayCapture):
    pcd = fuse(cap)
    P, N = np.asarray(pcd.points), np.asarray(pcd.normals)
    return P, N, manhattan_yaw(N)


def run_lidar(cap: StrayCapture, drift: str = "auto") -> LidarResult:
    """drift: "off" = poses as recorded, "on" = always correct, "auto" = correct only
    if it makes the walls measurably crisper (guards against correcting noise)."""
    P, N, yaw = _fused(cap)
    sharp = wall_sharpness(P, N, yaw)
    rep, applied = None, False
    if drift in ("on", "auto"):
        cc, rep = correct_drift(cap, yaw)
        P2, N2, yaw2 = _fused(cc)
        sharp2 = wall_sharpness(P2, N2, yaw2)
        if drift == "on" or sharp2 > sharp + 0.005:
            cap, P, N, yaw, sharp, applied = cc, P2, N2, yaw2, sharp2, True

    floor, ceil = floor_and_ceiling(P, N)
    fm = build_floormap(cap, P, N, floor.y, yaw)
    rooms = segment_rooms(fm, find_doorways(fm))
    polys = [room_polygon(rooms == k, fm, P, N, floor.y) for k in range(1, rooms.max() + 1)]
    top = ceil.y - floor.y if ceil else DEFAULT_CEILING
    openings = detect_openings(wall_evidence(cap, fm, floor.y, polys, top), top)
    return LidarResult(floor, ceil, yaw, fm, rooms, polys, openings, sharp, rep, applied)