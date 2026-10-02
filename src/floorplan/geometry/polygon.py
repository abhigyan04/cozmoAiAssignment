"""Room outline: grid region -> rectilinear polygon -> walls refined on raw 3D points.

The 5 cm grid only locates a wall to within a cell. For cm accuracy we go back
to the full-resolution point cloud: each wall's position is the robust median
of the 3D points on its room-facing surface.
"""
from dataclasses import dataclass, field

import cv2
import numpy as np
from scipy import ndimage as ndi

from floorplan.geometry.floormap import RES, FloorMap

# Systematic error per wall plane (not reduced by averaging): LiDAR range bias, pose
# error, plaster/skirting vs tape-at-1m. Calibrated on the benchmark flat: on correctly
# segmented walls the length errors had RMS ~5.8 cm, i.e. ~4 cm per plane; 3 cm keeps
# the 95% interval honest without hiding the bias (reported separately).
SYS_SIGMA = 0.03


@dataclass
class Wall:
    axis: int            # 0: wall is a line x = c (normal along x); 1: line z = c
    c: float             # wall plane coordinate in the Manhattan frame, metres
    sigma: float         # 1-sigma uncertainty of c
    support: int         # number of 3D points that located it
    refined: bool        # False if too few points: position comes from the grid only


@dataclass
class RoomPolygon:
    walls: list[Wall]
    vertices: np.ndarray                # (K, 2) corners in the Manhattan frame, metres
    lengths: list[float] = field(default_factory=list)
    length_sigmas: list[float] = field(default_factory=list)
    area: float = 0.0
    area_sigma: float = 0.0


def _grid_outline(mask: np.ndarray, fm: FloorMap) -> list[tuple[int, float]]:
    """Rectilinear outline of a room mask as a cyclic list of (axis, coordinate)."""
    # No dilation towards the walls: the outline only has to land within the
    # refinement window (15 cm), and growing it risks snapping to a wall's far face.
    m = ndi.binary_closing(mask, iterations=3)
    m = ndi.binary_fill_holes(m).astype(np.uint8)
    cnts, _ = cv2.findContours(m.T.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cnts, key=cv2.contourArea).reshape(-1, 2).astype(float)  # (x=i, y=j) in cells
    poly = cv2.approxPolyDP(c.astype(np.float32), 3.0, True).reshape(-1, 2)
    edges = []
    for a, b in zip(poly, np.roll(poly, -1, axis=0)):
        d = b - a
        axis = 0 if abs(d[0]) < abs(d[1]) else 1       # nearly constant x -> wall is x = c
        coord = (a[axis] + b[axis]) / 2
        length = abs(d[1 - axis])
        edges.append([axis, coord * RES + fm.origin[axis], length * RES])
    # Merge consecutive edges with the same orientation (Manhattan snapping).
    merged = []
    for e in edges:
        if merged and merged[-1][0] == e[0]:
            L = merged[-1][2] + e[2]
            merged[-1][1] = (merged[-1][1] * merged[-1][2] + e[1] * e[2]) / max(L, 1e-9)
            merged[-1][2] = L
        else:
            merged.append(e)
    if len(merged) > 1 and merged[0][0] == merged[-1][0]:
        e = merged.pop()
        L = merged[0][2] + e[2]
        merged[0][1] = (merged[0][1] * merged[0][2] + e[1] * e[2]) / L
        merged[0][2] = L
    return [(int(a), float(c)) for a, c, _ in merged]


def _vertices(walls: list[Wall]) -> np.ndarray:
    """Corner k is where wall k-1 meets wall k (they alternate axis)."""
    V = []
    for prev, cur in zip(np.roll(walls, 1), walls):
        v = np.zeros(2)
        v[prev.axis] = prev.c
        v[cur.axis] = cur.c
        V.append(v)
    return np.array(V)


def _simplify(walls: list[Wall], min_len: float = 0.25) -> list[Wall]:
    """Remove jogs shorter than min_len: drop the short wall, merge its two neighbours.

    Neighbours of a wall share an axis (walls alternate x/z), so dropping wall k
    makes k-1 and k+1 collinear-ish; the merged wall takes the position of the
    better-supported one. Repeats until every wall is long enough.
    """
    walls = list(walls)
    while len(walls) > 4:
        V = _vertices(walls)
        L = [np.linalg.norm(V[(k + 1) % len(walls)] - V[k]) for k in range(len(walls))]
        k = int(np.argmin(L))
        if L[k] >= min_len:
            break
        # Rotate the cyclic list so the short wall sits at index 1, between 0 and 2.
        walls = walls[k - 1:] + walls[:k - 1] if k >= 1 else walls[-1:] + walls[:-1]
        V = _vertices(walls)
        a, b = walls[0], walls[2]
        la = np.linalg.norm(V[1] - V[0])      # wall 0 runs corner 0 -> corner 1
        lb = np.linalg.norm(V[3 % len(walls)] - V[2])
        keep = a if (a.support, la) >= (b.support, lb) else b
        walls = [Wall(keep.axis, keep.c, keep.sigma, keep.support, keep.refined)] + walls[3:]
    return walls


def _refine(walls: list[Wall], verts: np.ndarray, XZ: np.ndarray, N2: np.ndarray,
            band: float = 0.15, min_pts: int = 200) -> None:
    """Move each wall onto the median of 3D points lying on its surface."""
    K = len(walls)
    for k, w in enumerate(walls):
        a, b = verts[k], verts[(k + 1) % K]               # wall k runs from corner k to corner k+1
        lo, hi = sorted([a[1 - w.axis], b[1 - w.axis]])
        inset = min(0.15, (hi - lo) / 4)                  # stay away from corners
        sel = ((np.abs(XZ[:, w.axis] - w.c) < band)
               & (XZ[:, 1 - w.axis] > lo + inset) & (XZ[:, 1 - w.axis] < hi - inset)
               & (np.abs(N2[:, w.axis]) > 0.9))
        v = XZ[sel, w.axis]
        if len(v) < min_pts:
            w.sigma = RES  # grid-only: half a cell either way, honestly wide
            continue
        med = np.median(v)
        # Two faces (e.g. a thin partition seen from both sides): keep the peak nearest the grid estimate.
        v = v[np.abs(v - med) < 0.05]
        med = float(np.median(v))
        mad = 1.4826 * np.median(np.abs(v - med))
        w.c, w.support, w.refined = med, len(v), True
        w.sigma = float(np.hypot(mad / np.sqrt(len(v)), SYS_SIGMA))


def room_polygon(mask: np.ndarray, fm: FloorMap, P: np.ndarray, N: np.ndarray,
                 floor_y: float, band: tuple[float, float] = (0.3, 2.4)) -> RoomPolygon:
    outline = _grid_outline(mask, fm)
    walls = [Wall(a, c, RES, 0, False) for a, c in outline]
    h = P[:, 1] - floor_y
    keep = (np.abs(N[:, 1]) < 0.3) & (h > band[0]) & (h < band[1])   # wall surfaces in the band
    XZ = P[keep][:, [0, 2]] @ fm.R.T
    N2 = N[keep][:, [0, 2]] @ fm.R.T
    walls = _simplify(walls)
    _refine(walls, _vertices(walls), XZ, N2)
    walls = _simplify(walls)
    V = _vertices(walls)
    rp = RoomPolygon(walls, V)
    K = len(walls)
    for k, w in enumerate(walls):
        # Wall k is bounded by walls k-1 and k+1: its length error comes from their positions.
        prev, nxt = walls[k - 1], walls[(k + 1) % K]
        rp.lengths.append(float(np.linalg.norm(V[(k + 1) % K] - V[k])))
        rp.length_sigmas.append(float(np.hypot(prev.sigma, nxt.sigma)))
    x, z = V[:, 0], V[:, 1]
    rp.area = float(abs(np.dot(x, np.roll(z, -1)) - np.dot(z, np.roll(x, -1))) / 2)
    # Area uncertainty: moving wall k by dc changes area by (its length) * dc.
    rp.area_sigma = float(np.sqrt(sum((L * w.sigma) ** 2 for L, w in zip(rp.lengths, walls))))
    return rp

def _finalize(rp: RoomPolygon) -> RoomPolygon:
    """Recompute corners, lengths, sigmas and area after walls moved."""
    walls = rp.walls
    V = _vertices(walls)
    K = len(walls)
    rp.vertices = V
    rp.lengths = [float(np.linalg.norm(V[(k + 1) % K] - V[k])) for k in range(K)]
    rp.length_sigmas = [float(np.hypot(walls[k - 1].sigma, walls[(k + 1) % K].sigma)) for k in range(K)]
    x, z = V[:, 0], V[:, 1]
    rp.area = float(abs(np.dot(x, np.roll(z, -1)) - np.dot(z, np.roll(x, -1))) / 2)
    rp.area_sigma = float(np.sqrt(sum((L * w.sigma) ** 2 for L, w in zip(rp.lengths, walls))))
    return rp


def extend_to_ceiling(polys: list[RoomPolygon], ceilings: list[float | None], P: np.ndarray, N: np.ndarray,
                      R2: np.ndarray, floor_y: float, max_out: float = 1.5) -> list[dict]:
    """Push walls that are really furniture faces (wardrobes) out to the true wall.

    The ceiling is never hidden by furniture: seen from below it runs to the real
    wall. A wall is moved only if (1) almost nothing vertical exists just below the
    ceiling at its position (real walls reach the ceiling; wardrobe fronts stop at
    ~2.1 m), (2) the room's own ceiling continues >= 0.2 m beyond it, and (3) the
    move does not cross into another room. Target: the first ceiling-reaching
    vertical plane beyond it that is still under the ceiling, else the ceiling edge.
    """
    from shapely.geometry import Polygon

    XZ, N2 = P[:, [0, 2]] @ R2.T, N[:, [0, 2]] @ R2.T
    H = P[:, 1] - floor_y
    vert = np.abs(N[:, 1]) < 0.3
    horiz = np.abs(N[:, 1]) > 0.9
    log = []
    for ri, (rp, top) in enumerate(zip(polys, ceilings)):
        if top is None:
            continue
        others = [Polygon(o.vertices) for j, o in enumerate(polys) if j != ri]
        ceil = horiz & (np.abs(H - top) < 0.05)
        high = vert & (H > top - 0.35) & (H < top - 0.05)
        moved = False
        ctr = rp.vertices.mean(0)
        for k, w in enumerate(rp.walls):
            V = rp.vertices
            a, b = V[k], V[(k + 1) % len(V)]
            lo, hi = sorted([a[1 - w.axis], b[1 - w.axis]])
            if hi - lo < 0.8:
                continue
            out = np.sign(w.c - ctr[w.axis]) or 1.0
            span = (XZ[:, 1 - w.axis] > lo + 0.15) & (XZ[:, 1 - w.axis] < hi - 0.15)
            d_all = (XZ[:, w.axis] - w.c) * out
            # (1) does this wall reach the ceiling?
            reach = (high & span & (np.abs(N2[:, w.axis]) > 0.9) & (np.abs(d_all) < 0.05)).sum()
            if reach >= 150:
                continue
            # (2) does the room's ceiling continue beyond it?
            beyond = d_all[ceil & span & (d_all > 0) & (d_all < max_out)]
            if len(beyond) < 300 or np.percentile(beyond, 98) < 0.2:
                continue
            edge = float(np.percentile(beyond, 98))
            # (3) first ceiling-reaching plane further out, still under the ceiling
            cand = d_all[high & span & (np.abs(N2[:, w.axis]) > 0.9) & (d_all > 0.2) & (d_all < edge + 0.15)]
            target = edge
            if len(cand) >= 100:
                hist, e = np.histogram(cand, bins=np.arange(0.2, edge + 0.16, 0.02))
                pk = np.nonzero(hist >= max(0.3 * hist.max(), 30))[0]
                if len(pk):
                    t0 = e[pk.min()] + 0.01
                    target = float(np.median(cand[np.abs(cand - t0) < 0.03]))
            old_c = w.c
            w.c = old_c + out * target
            trial = _finalize(rp)
            if trial.area <= 0 or any(Polygon(trial.vertices).intersection(o).area > 0.3 for o in others):
                w.c = old_c                       # would cross into another room: keep
                _finalize(rp)
                continue
            w.sigma = float(np.hypot(w.sigma, 0.03))   # placed from ceiling evidence: a bit less certain
            moved = True
            log.append({"room": ri, "wall": k, "moved_m": round(target, 3), "wall_ceiling_support": int(reach)})
        if moved:
            _finalize(rp)
    return log
