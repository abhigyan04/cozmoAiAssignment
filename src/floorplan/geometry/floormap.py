"""Top-down 2D maps and room segmentation.

Everything happens on a 5 cm grid in the Manhattan frame (walls axis-aligned).
We only use geometry between 1.1 m and 2.1 m above the floor: tables, sofas,
beds and counters sit below 1.1 m, while walls and the gaps doors make in
them extend above it. So in this band "vertical surface" means "wall" and
rays pass over furniture instead of stopping at it.
"""
from dataclasses import dataclass

import numpy as np
from scipy import ndimage as ndi

from floorplan.io.stray import StrayCapture

RES = 0.05            # grid cell size, metres
BAND = (1.1, 2.1)     # height band above floor used for walls and free space


@dataclass
class FloorMap:
    wall: np.ndarray      # bool grid: structural wall evidence
    free: np.ndarray      # bool grid: observed empty space (from ray casting)
    visited: np.ndarray   # bool grid: cells the camera passed over
    origin: np.ndarray    # world (x, z) of cell [0, 0], in the Manhattan frame
    R: np.ndarray         # 2x2 rotation, world (x, z) -> Manhattan frame

    def to_cell(self, xz_world: np.ndarray) -> np.ndarray:
        ij = ((xz_world @ self.R.T - self.origin) / RES).astype(int)
        return np.clip(ij, 0, np.array(self.wall.shape) - 1)


def build_floormap(cap: StrayCapture, P: np.ndarray, N: np.ndarray, floor_y: float,
                   yaw_deg: float, stride: int = 10, rays_per_frame: int = 3000) -> FloorMap:
    t = np.radians(yaw_deg)
    R = np.array([[np.cos(t), np.sin(t)], [-np.sin(t), np.cos(t)]])
    XZ = P[:, [0, 2]] @ R.T
    h = P[:, 1] - floor_y
    origin = XZ.min(0) - 0.5
    shape = tuple(((XZ.max(0) + 0.5 - origin) / RES).astype(int) + 1)
    fm = FloorMap(np.zeros(shape, bool), np.zeros(shape, bool), np.zeros(shape, bool), origin, R)

    # Walls: vertical surfaces inside the band, seen at least twice.
    wall = np.zeros(shape, np.int32)
    ij = fm.to_cell(P[(np.abs(N[:, 1]) < 0.3) & (h > BAND[0]) & (h < BAND[1])][:, [0, 2]])
    np.add.at(wall, (ij[:, 0], ij[:, 1]), 1)
    fm.wall = wall >= 2

    # Free space: 2D ray casting. Every LiDAR ray from the camera to a surface
    # crossed empty space, which fills in the floor hidden under furniture.
    free = np.zeros(shape, np.int32)
    s = np.linspace(0, 1, 60)[:-3]  # stop just short of the hit point
    rng = np.random.default_rng(0)
    for i in range(0, len(cap.frames), stride):
        p = cap.points_world(i, max_depth=6.0)
        p = p[(p[:, 1] - floor_y > BAND[0]) & (p[:, 1] - floor_y < BAND[1])]
        if len(p) > rays_per_frame:
            p = p[rng.choice(len(p), rays_per_frame, replace=False)]
        o = cap.frames[i].T_wc[:3, 3][[0, 2]]
        rays = o + (p[:, [0, 2]] - o)[:, None, :] * s[None, :, None]
        ij = fm.to_cell(rays.reshape(-1, 2))
        np.add.at(free, (ij[:, 0], ij[:, 1]), 1)
    fm.free = ndi.binary_opening((free >= 2) & ~fm.wall)

    cam = np.array([f.T_wc[:3, 3][[0, 2]] for f in cap.frames])
    ij = fm.to_cell(cam)
    fm.visited[ij[:, 0], ij[:, 1]] = True
    return fm


def _span_width(free: np.ndarray, wall: np.ndarray) -> np.ndarray:
    """Width of each free cell's run along axis 0, if both ends of the run hit a wall."""
    W = np.zeros(free.shape)
    for j in range(free.shape[1]):
        col, n, i = free[:, j], free.shape[0], 0
        while i < n:
            if not col[i]:
                i += 1
                continue
            k = i
            while k < n and col[k]:
                k += 1
            if wall[max(i - 3, 0):i, j].any() and wall[k:k + 3, j].any():
                W[i:k, j] = (k - i) * RES
            i = k
    return W


def find_doorways(fm: FloorMap, wmin=0.55, wmax=1.25, max_depth=0.5) -> list[dict]:
    """Doorway = short, narrow gap between two walls.

    A gap 0.55-1.25 m wide whose extent in the walking direction is under
    0.5 m (roughly a wall's thickness plus frame). A hallway is also narrow,
    but it is long, so it is not cut.
    """
    doors = []
    for axis in (0, 1):
        f, w = (fm.free, fm.wall) if axis == 0 else (fm.free.T, fm.wall.T)
        W = _span_width(f, w)
        if axis == 1:
            W = W.T
        lab, n = ndi.label((W >= wmin) & (W <= wmax))
        for k, sl in enumerate(ndi.find_objects(lab), start=1):
            comp = lab[sl] == k
            depth = (sl[1 - axis].stop - sl[1 - axis].start) * RES
            if depth <= max_depth:
                mask = np.zeros_like(fm.free)
                mask[sl] = comp
                doors.append({"axis": axis, "mask": mask, "width": float(np.median(W[sl][comp]))})
    return doors


def segment_rooms(fm: FloorMap, doors: list[dict], min_area=1.5) -> np.ndarray:
    """Label grid: 0 = not a room, 1..K = room id."""
    cut = np.zeros_like(fm.free)
    for d in doors:
        cut |= d["mask"]
    lab, n = ndi.label(fm.free & ~cut)
    dist_to_path = ndi.distance_transform_edt(~fm.visited) * RES
    rooms = np.zeros(lab.shape, np.int32)
    k = 0
    for r in range(1, n + 1):
        m = lab == r
        # A room must be big enough, and the operator must have walked through it:
        # >= 70% of its cells within 2 m of the camera path. This drops "fans" of
        # rays that shot through a doorway into a space only looked at from outside.
        if m.sum() * RES**2 >= min_area and (dist_to_path[m] < 2.0).mean() >= 0.7:
            k += 1
            rooms[m] = k
    # Give cut cells (doorways, false cuts at shelves) back to the nearest room.
    idx = ndi.distance_transform_edt(rooms == 0, return_distances=False, return_indices=True)
    grown = rooms[idx[0], idx[1]]
    back = cut & fm.free & (ndi.distance_transform_edt(rooms == 0) <= 12)
    rooms[back] = grown[back]
    return rooms