"""Doors, windows and passages as holes in walls, found by ray casting.

For each wall we build an "unrolled" image: position along the wall x height,
2 cm pixels. Every LiDAR ray that reaches the wall plane votes:
  hit  - the ray ended on the plane (there is wall here)
  pass - the ray crossed the plane and ended >15 cm beyond it (there is a hole)
A pixel is an opening when most rays passed through it. Furniture in front of
a wall stops rays before the plane, so it can never create a phantom opening;
unobserved parts of a wall get no votes and stay "unknown", not "opening".
"""
from dataclasses import dataclass

import numpy as np
from scipy import ndimage as ndi

from floorplan.io.stray import StrayCapture
from floorplan.geometry.floormap import FloorMap
from floorplan.geometry.polygon import RoomPolygon

PIX = 0.02          # unrolled-wall pixel size, metres
ON_PLANE = 0.06     # a hit within this distance of the plane is a wall hit
BEYOND = 0.15       # a hit this far past the plane means the ray went through


@dataclass
class Opening:
    room: int            # room index
    wall: int            # wall index within the room polygon
    kind: str            # "door" | "window" | "passage"
    u0: float            # start along the wall (Manhattan-frame coordinate), metres
    u1: float            # end along the wall
    bottom: float        # height above floor, metres
    top: float
    width_sigma: float   # 1-sigma of the width, metres

    @property
    def width(self) -> float:
        return self.u1 - self.u0


def wall_evidence(cap: StrayCapture, fm: FloorMap, floor_y: float, polys: list[RoomPolygon],
                  top: float, stride: int = 5, max_pts: int = 6000) -> list[dict]:
    """Accumulate hit/pass votes for every refined wall of every room."""
    walls = []
    for ri, rp in enumerate(polys):
        V = rp.vertices
        for k, w in enumerate(rp.walls):
            if not w.refined or rp.lengths[k] < 0.5:
                continue
            a, b = V[k], V[(k + 1) % len(V)]
            lo, hi = sorted([a[1 - w.axis], b[1 - w.axis]])
            shape = (int((hi - lo) / PIX) + 1, int(top / PIX) + 1)
            walls.append(dict(room=ri, wall=k, axis=w.axis, c=w.c, lo=lo, hi=hi,
                              hit=np.zeros(shape), pas=np.zeros(shape)))
    rng = np.random.default_rng(0)
    for i in range(0, len(cap.frames), stride):
        p = cap.points_world(i, min_conf=1, max_depth=6.0)
        if len(p) > max_pts:
            p = p[rng.choice(len(p), max_pts, replace=False)]
        o = cap.frames[i].T_wc[:3, 3]
        # Manhattan frame, columns: (x', z', height above floor)
        pm = np.c_[p[:, [0, 2]] @ fm.R.T, p[:, 1] - floor_y]
        om = np.r_[o[[0, 2]] @ fm.R.T, o[1] - floor_y]
        for w in walls:
            ax = w["axis"]
            dp, dc = pm[:, ax] - om[ax], w["c"] - om[ax]
            if abs(dc) < 0.05:
                continue
            # Rays heading toward the plane that get at least to within ON_PLANE of it.
            ok = (np.sign(dp) == np.sign(dc)) & (np.abs(dp) >= abs(dc) - ON_PLANE)
            if not ok.any():
                continue
            t = np.minimum(dc / dp[ok], 1.0)
            q = om + (pm[ok] - om) * t[:, None]            # where the ray meets the plane
            u, h = q[:, 1 - ax], q[:, 2]
            past = np.abs(dp[ok]) - abs(dc)                # how far beyond the plane it ended
            inb = (u >= w["lo"]) & (u < w["hi"]) & (h >= 0) & (h < top)
            iu = ((u[inb] - w["lo"]) / PIX).astype(int)
            ih = (h[inb] / PIX).astype(int)
            hit, pas = np.abs(past[inb]) < ON_PLANE, past[inb] > BEYOND
            np.add.at(w["hit"], (iu[hit], ih[hit]), 1)
            np.add.at(w["pas"], (iu[pas], ih[pas]), 1)
    return walls


def _edges(profile: np.ndarray, j0: int, j1: int) -> tuple[float, float]:
    """Sub-pixel left/right edges (in pixels) where an opening-fraction profile crosses 0.5."""
    def cross(j, step):
        while 0 <= j + step < len(profile) and profile[j + step] >= 0.5:
            j += step
        k = j + step
        if not 0 <= k < len(profile):
            return j + 0.5 * step
        a, b = profile[j], profile[k]                    # a >= 0.5 > b
        return j + step * (a - 0.5) / max(a - b, 1e-6)
    mid = (j0 + j1) // 2
    # cross() works in pixel-centre units (centre of pixel j is j + 0.5).
    return cross(mid, -1) + 0.5, cross(mid, +1) + 0.5


def detect_openings(walls: list[dict], top: float, min_votes: int = 2) -> list[Opening]:
    out = []
    for w in walls:
        tot = w["hit"] + w["pas"]
        hole = (tot >= min_votes) & (w["pas"] > w["hit"])
        hole = ndi.binary_opening(ndi.binary_closing(hole, iterations=2), iterations=2)
        # Window mullions and door handles split one opening into pieces:
        # close along the wall by up to ~12 cm before labelling.
        hole = ndi.binary_closing(hole, structure=np.ones((7, 1)))
        lab, n = ndi.label(hole)
        for k, sl in enumerate(ndi.find_objects(lab), start=1):
            a, b, c, d = sl[0].start, sl[0].stop, sl[1].start, sl[1].stop
            h0, h1 = c * PIX, d * PIX
            if (b - a) * PIX < 0.4 or (h1 - h0) < 0.6 or (lab[sl] == k).mean() < 0.5:
                continue
            # Width from the pass fraction over the middle 60% of the opening's height,
            # which avoids the sill, the lintel and door handles.
            r0, r1 = c + int(0.2 * (d - c)), c + max(int(0.8 * (d - c)), 1)
            frac = w["pas"][:, r0:r1].sum(1) / np.maximum(tot[:, r0:r1].sum(1), 1)
            e0, e1 = _edges(frac, a, b - 1)
            u0, u1 = w["lo"] + e0 * PIX, w["lo"] + e1 * PIX
            if u1 - u0 < 0.4:
                continue
            on_floor = h0 < 0.3   # real window sills are >= 30 cm; lower means a door with a threshold
            if on_floor and (h1 > top - 0.15 or u1 - u0 > 1.4):
                kind = "passage"        # full-height or wider than a door: archway / open boundary
            elif on_floor:
                kind = "door"
            else:
                kind = "window"
            # ~1 cm per edge (a third of a pixel plus ray footprint) until the
            # benchmark calibrates it against tape measurements.
            out.append(Opening(w["room"], w["wall"], kind, u0, u1, h0, h1, float(np.hypot(0.01, 0.01))))
    return out