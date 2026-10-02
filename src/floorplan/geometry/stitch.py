"""Whole-property structure: per-room heights, room adjacency, shared openings.

Rooms from one continuous capture already share a coordinate frame, so
"stitching" here means working out how they connect: a doorway cut from the
segmentation step touches exactly two rooms, and the same physical door is
usually detected on both rooms' walls (two faces of one wall). We pair those
detections into one opening and average their widths.
"""
from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage as ndi

from floorplan.geometry.floormap import RES, FloorMap
from floorplan.geometry.openings import Opening
from floorplan.geometry.structure import Level, floor_and_ceiling

MAX_WALL_THICKNESS = 0.40   # two detections of one door are at most this far apart across the wall
MIN_ROOM_POINTS = 300


@dataclass
class SharedOpening:
    kind: str
    rooms: list[int]                  # 1 room = exterior or unmatched, 2 = connects them
    detections: list[Opening]
    width: float
    width_sigma: float
    center: np.ndarray                # Manhattan-frame (x, z) of the opening's middle
    axis: int                         # axis of the wall it sits in


@dataclass
class RoomHeights:
    floor: Level | None
    ceiling: Level | None                       # dominant ceiling level
    levels: list[tuple[float, float]] = field(default_factory=list)  # (height, share of ceiling points)

    @property
    def height(self) -> float | None:
        return None if self.ceiling is None or self.floor is None else self.ceiling.y - self.floor.y

    @property
    def sigma(self) -> float | None:
        return None if self.height is None else float(np.hypot(self.floor.sigma, self.ceiling.sigma))


def room_heights(P: np.ndarray, N: np.ndarray, fm: FloorMap, rooms: np.ndarray,
                 floor: Level | None = None) -> list[RoomHeights]:
    """Floor and ceiling measured separately inside each room.

    Floor: searched only within +-10 cm of the property-wide floor `floor`. Floors are
    level across a flat to a few cm, and a room's own "lowest strong plane" can be a bed
    top when the bed covers most of the floor (bedroom1: 0.6 m bed taken as floor gave a
    2.05 m ceiling). Falls back to the property floor if the room's floor is unseen.
    Ceiling: the strongest overhead plane at least 2.2 m above the floor (lofts and door
    heads sit at ~2.0-2.1 m), else the strongest above 1.8 m; none if never observed."""
    from floorplan.geometry.structure import _refine_level
    ij = fm.to_cell(P[:, [0, 2]])
    lab = rooms[ij[:, 0], ij[:, 1]]
    out = []
    for k in range(1, rooms.max() + 1):
        core = ndi.binary_erosion(rooms == k, iterations=2)      # keep away from walls
        sel = core[ij[:, 0], ij[:, 1]] & (lab == k) & (np.abs(N[:, 1]) > 0.9)
        y = P[sel, 1]
        if len(y) < MIN_ROOM_POINTS:
            out.append(RoomHeights(floor, None))
            continue
        if floor is not None:
            near = y[np.abs(y - floor.y) < 0.10]
            f = _refine_level(near, float(np.median(near))) if len(near) >= 100 else floor
        else:
            h, e = np.histogram(y, bins=np.arange(y.min(), y.max() + 0.02, 0.01))
            strong = np.nonzero(h >= max(h.max() * 0.2, 50))[0]
            f = _refine_level(y, e[strong.min()] + 0.005)
        c = None
        for min_h in (MIN_CEILING, 1.8):
            up = y[y > f.y + min_h]
            if len(up) >= MIN_ROOM_POINTS:
                h, e = np.histogram(up, bins=np.arange(up.min(), up.max() + 0.02, 0.01))
                c = _refine_level(up, e[np.argmax(h)] + 0.005)
                break
        out.append(RoomHeights(f, c, _ceiling_levels(P[sel], N[sel], f) if c else []))
    return out


MIN_CEILING = 2.2   # habitable ceilings are higher; lofts and door heads sit at ~2.0-2.1 m


def _ceiling_levels(P: np.ndarray, N: np.ndarray, floor: Level, min_share: float = 0.15):
    """All ceiling heights covering >= 15% of the room's ceiling points.

    False ceilings (a dropped border with a higher centre, a bulkhead over a
    kitchen) mean a room has no single height; we report every level.
    """
    y = P[np.abs(N[:, 1]) > 0.9, 1] - floor.y
    y = y[y > 1.8]
    h, e = np.histogram(y, bins=np.arange(1.8, y.max() + 0.03, 0.02))
    peaks = np.nonzero((h == ndi.maximum_filter(h, size=7)) & (h > 0))[0]
    levels = []
    for i in peaks:
        share = h[max(i - 2, 0):i + 3].sum() / len(y)          # peak +- 4 cm
        if share >= min_share:
            levels.append((round(float(e[i] + 0.01), 3), round(float(share), 2)))
    return sorted(levels, key=lambda t: -t[1])


def _center(o: Opening, polys_axis_c: dict) -> tuple[np.ndarray, int]:
    axis, c = polys_axis_c[(o.room, o.wall)]
    ctr = np.zeros(2)
    ctr[axis] = c
    ctr[1 - axis] = (o.u0 + o.u1) / 2
    return ctr, axis


def pair_openings(openings: list[Opening], polys) -> list[SharedOpening]:
    """Merge the two faces of the same door/window seen from neighbouring rooms."""
    wall_of = {(ri, k): (w.axis, w.c) for ri, rp in enumerate(polys) for k, w in enumerate(rp.walls)}
    items = [(o, *_center(o, wall_of)) for o in openings]
    used, out = set(), []
    for i, (oi, ci, ai) in enumerate(items):
        if i in used:
            continue
        best, best_d = None, None
        for j, (oj, cj, aj) in enumerate(items):
            if j <= i or j in used or oj.room == oi.room or aj != ai or oj.kind != oi.kind:
                continue
            across, along = abs(ci[ai] - cj[ai]), abs(ci[1 - ai] - cj[1 - ai])
            overlap = min(oi.u1, oj.u1) - max(oi.u0, oj.u0)
            if across < MAX_WALL_THICKNESS and along < 0.3 and overlap > 0.5 * min(oi.width, oj.width):
                if best is None or along < best_d:
                    best, best_d = j, along
        dets = [oi] if best is None else [oi, items[best][0]]
        used.add(i)
        if best is not None:
            used.add(best)
        # Inverse-variance mean of the independent width measurements.
        wts = np.array([1 / d.width_sigma**2 for d in dets])
        width = float(np.sum(wts * [d.width for d in dets]) / wts.sum())
        out.append(SharedOpening(oi.kind, sorted({d.room for d in dets}), dets, width,
                                 float(1 / np.sqrt(wts.sum())), ci, ai))
    return out


def adjacency(doors: list[dict], rooms: np.ndarray, shared: list[SharedOpening],
              fm: FloorMap) -> list[dict]:
    """Room graph. Edges come from (a) segmentation doorways touching two rooms and
    (b) openings detected from both sides; each edge names its opening when known."""
    edges = {}
    for d in doors:
        touched = set(np.unique(rooms[ndi.binary_dilation(d["mask"], iterations=3)])) - {0}
        if len(touched) == 2:
            a, b = sorted(int(x) - 1 for x in touched)
            cells = np.argwhere(d["mask"])
            ctr = cells.mean(0) * RES + fm.origin
            edges.setdefault((a, b), {"rooms": [a, b], "center": ctr, "opening": None})
    for idx, s in enumerate(shared):
        if len(s.rooms) == 2:
            key = tuple(s.rooms)
            e = edges.setdefault(key, {"rooms": list(key), "center": s.center, "opening": None})
            e["opening"] = idx
    return list(edges.values())