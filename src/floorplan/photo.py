"""Photo tier: one folder of 2-8 stills per room -> stitched, dimensioned plan.

1. Per room: MapAnything on that room's photos (EXIF focal length as known
   intrinsics), then the same geometry back end as LiDAR: free-space ray
   casting from the photo positions, room polygon, walls refined on 3D points,
   openings, heights.
2. Stitch: one joint reconstruction of *all* photos gives a coarse placement
   of the rooms (doorway photos overlap between rooms). Each room's polygon is
   moved into that frame, snapped to the property's shared Manhattan axes,
   and neighbouring rooms are pushed so facing walls are one wall-thickness
   apart, never overlapping.
3. Intervals: every length gets an extra relative term for metric-scale
   error, which dominates on photos (calibrated against tape, see report).
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import ExifTags, Image, ImageOps
from scipy import ndimage as ndi
from scipy.ndimage import gaussian_filter1d, maximum_filter1d

from floorplan.geometry.floormap import RES, build_floormap, find_doorways
from floorplan.geometry.openings import detect_openings, wall_evidence
from floorplan.geometry.polygon import RoomPolygon, Wall, _vertices, room_polygon
from floorplan.geometry.stitch import RoomHeights, SharedOpening, room_heights
from floorplan.geometry.structure import floor_and_ceiling, fuse, manhattan_yaw
from floorplan.io.recon import ReconCapture, run_mapanything
from floorplan.uncertainty import widen_for_scale

MAX_SIDE = 1024
DEFAULT_HFOV_DEG = 70.0     # used only when a photo has no EXIF focal length
# Relative 1-sigma metric-scale error, with / without EXIF focal length. Calibrated on the
# benchmark flat: per-room photo-tier wall errors had RMS ~9.5% (see benchmark report).
SCALE_SIGMA = {True: 0.10, False: 0.15}
WALL_T = 0.12               # interior wall thickness assumed when snapping rooms together
_TAGS = {v: k for k, v in ExifTags.TAGS.items()}
IMG_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif"}


@dataclass
class PhotoRoom:
    name: str
    images: list[np.ndarray]
    K: np.ndarray
    has_exif: bool


def _load(path: Path) -> tuple[np.ndarray, np.ndarray, bool]:
    if path.suffix.lower() in {".heic", ".heif"}:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    im = Image.open(path)
    f35 = im.getexif().get_ifd(0x8769).get(_TAGS["FocalLengthIn35mmFilm"])
    im = ImageOps.exif_transpose(im).convert("RGB")
    W, H = im.size
    s = MAX_SIDE / max(W, H)
    im = im.resize((round(W * s), round(H * s)), Image.LANCZOS)
    w, h = im.size
    if f35:
        fx = float(f35) * np.hypot(w, h) / 43.27      # 35 mm-equivalent focal is defined on the diagonal
    else:
        fx = (w / 2) / np.tan(np.radians(DEFAULT_HFOV_DEG / 2))
    K = np.array([[fx, 0, (w - 1) / 2], [0, fx, (h - 1) / 2], [0, 0, 1]])
    return np.asarray(im), K, bool(f35)


def load_rooms(root: Path) -> list[PhotoRoom]:
    rooms = []
    for d in sorted(p for p in Path(root).iterdir() if p.is_dir()):
        files = sorted(f for f in d.iterdir() if f.suffix.lower() in IMG_EXT)   # closeups/ subfolder is skipped
        if not files:
            continue
        loaded = [_load(f) for f in files]
        shapes = {im.shape for im, _, _ in loaded}
        if len(shapes) > 1:   # mixed portrait/landscape: keep the majority orientation
            major = max(shapes, key=lambda s: sum(im.shape == s for im, _, _ in loaded))
            loaded = [x for x in loaded if x[0].shape == major]
        rooms.append(PhotoRoom(d.name, [x[0] for x in loaded], loaded[0][1], all(x[2] for x in loaded)))
    return rooms


def _pick_room_region(fm, doors) -> np.ndarray:
    """The free-space component the photos were taken from (most cells near a camera)."""
    cut = np.zeros_like(fm.free)
    for d in doors:
        cut |= d["mask"]
    lab, n = ndi.label(fm.free & ~cut)
    near_cam = ndi.distance_transform_edt(~fm.visited) * RES < 1.0
    best = max(range(1, n + 1), key=lambda k: ((lab == k) & near_cam).sum())
    mask = lab == best
    grown = ndi.binary_dilation(mask, iterations=12) & cut & fm.free     # give doorway cuts back
    return mask | grown


@dataclass
class RoomResult:
    name: str
    poly: object            # RoomPolygon, in this room's own Manhattan frame
    heights: RoomHeights
    openings: list
    cap: ReconCapture
    yaw: float
    R2: np.ndarray          # 2x2 world(x,z) -> room Manhattan frame
    scale_sigma: float


def _wall_planes_rect(P, N, R, floor_y, top, cams) -> list[Wall] | None:
    """Rectangle from the walls that reach the ceiling.

    With only a handful of photos, free-space ray casting does not fill a room
    out to its walls. Walls are instead found directly: in a band just below
    the ceiling, furniture is absent and nothing is visible *through* doors or
    windows (they end ~2.1 m), so the outermost strong vertical plane on each
    side of the cameras is the wall.
    """
    XZ, N2 = P[:, [0, 2]] @ R.T, N[:, [0, 2]] @ R.T
    h = P[:, 1] - floor_y
    band = (h > top - 0.45) & (h < top - 0.08)
    cc = cams.mean(0)
    walls = {}
    for ax in (0, 1):
        sel = band & (np.abs(N2[:, ax]) > 0.9)
        v = XZ[sel, ax]
        if len(v) < 200:
            return None
        hist, e = np.histogram(v, bins=np.arange(v.min() - 0.05, v.max() + 0.05, 0.01))
        hs = gaussian_filter1d(hist.astype(float), 1.5)
        pk = np.nonzero((hs == maximum_filter1d(hs, 15)) & (hs > 0.15 * hs.max()))[0]
        pos = e[pk] + 0.005
        lo, hi = pos[pos < cc[ax]], pos[pos > cc[ax]]
        if not len(lo) or not len(hi):
            return None
        for side, c0 in (("lo", lo.min()), ("hi", hi.max())):
            # Refine on all wall heights within +-3 cm of the band's estimate.
            on = (np.abs(XZ[:, ax] - c0) < 0.03) & (np.abs(N2[:, ax]) > 0.9) & (h > 0.3) & (h < top - 0.05)
            vals = XZ[on, ax]
            c = float(np.median(vals)) if len(vals) > 50 else float(c0)
            mad = 1.4826 * np.median(np.abs(vals - c)) if len(vals) > 50 else RES
            walls[(ax, side)] = Wall(ax, c, float(np.hypot(mad / np.sqrt(max(len(vals), 1)), 0.005)),
                                     int(len(vals)), len(vals) > 50)
    # Counter-clockwise cycle, alternating axes: x=lo, z=lo, x=hi, z=hi.
    return [walls[(0, "lo")], walls[(1, "lo")], walls[(0, "hi")], walls[(1, "hi")]]


def _poly_from_walls(walls: list[Wall]) -> RoomPolygon:
    V = _vertices(walls)
    rp = RoomPolygon(walls, V)
    K = len(walls)
    for k in range(K):
        prev, nxt = walls[k - 1], walls[(k + 1) % K]
        rp.lengths.append(float(np.linalg.norm(V[(k + 1) % K] - V[k])))
        rp.length_sigmas.append(float(np.hypot(prev.sigma, nxt.sigma)))
    x, z = V[:, 0], V[:, 1]
    rp.area = float(abs(np.dot(x, np.roll(z, -1)) - np.dot(z, np.roll(x, -1))) / 2)
    rp.area_sigma = float(np.sqrt(sum((L * w.sigma) ** 2 for L, w in zip(rp.lengths, walls))))
    return rp


def reconstruct_room(room: PhotoRoom) -> RoomResult:
    views = run_mapanything(room.images, room.K)
    cap = ReconCapture(views, fps=1.0)
    pcd = fuse(cap, stride=1)
    P, N = np.asarray(pcd.points), np.asarray(pcd.normals)
    floor, ceil = floor_and_ceiling(P, N, min_support=300)
    yaw = manhattan_yaw(N)
    fm = build_floormap(cap, P, N, floor.y, yaw, stride=1, rays_per_frame=20000)
    cams = np.array([f.T_wc[:3, 3][[0, 2]] for f in cap.frames]) @ fm.R.T
    walls = _wall_planes_rect(P, N, fm.R, floor.y, ceil.y - floor.y if ceil else 2.5, cams)
    doors = find_doorways(fm)
    mask = _pick_room_region(fm, doors)
    if walls is not None:
        poly = _poly_from_walls(walls)
    else:   # fall back to the free-space outline (narrow or poorly covered rooms)
        poly = room_polygon(mask, fm, P, N, floor.y)
    rooms = mask.astype(np.int32)
    heights = room_heights(P, N, fm, rooms)[0]
    top = ceil.y - floor.y if ceil else 2.6
    openings = detect_openings(wall_evidence(cap, fm, floor.y, [poly], top, stride=1, max_pts=40000), top)
    s = SCALE_SIGMA[room.has_exif]
    widen_for_scale([poly], [heights], openings, s)
    return RoomResult(room.name, poly, heights, openings, cap, yaw, fm.R, s)


# ---------------------------------------------------------------- stitching

@dataclass
class PhotoPlan:
    """Duck-types LidarResult for output.plan.build_plan."""
    names: list[str]
    polys: list[RoomPolygon]
    heights: list[RoomHeights]
    shared: list
    edges: list[dict]
    sharpness: float = float("nan")
    drift: object = None
    drift_applied: bool = False


def _rot2(theta: float) -> np.ndarray:
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[c, -s], [s, c]])


def _kabsch2d(A: np.ndarray, B: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Rigid 2D transform (R, t) with B ~ A @ R.T + t."""
    ma, mb = A.mean(0), B.mean(0)
    U, _, Vt = np.linalg.svd((B - mb).T @ (A - ma))
    D = np.diag([1.0, np.sign(np.linalg.det(U @ Vt))])
    R = U @ D @ Vt
    return R, mb - ma @ R.T


def _layout(boxes: list[np.ndarray], iters: int = 50) -> list[np.ndarray]:
    """Resolve overlaps and close small gaps between axis-aligned room boxes.

    boxes[i] = [xmin, zmin, xmax, zmax]. Overlapping rooms are pushed apart along
    their axis of least penetration; facing walls closer than 0.8 m (with >= 0.5 m
    of shared length) are snapped to one wall thickness apart. Moves are split
    between the two rooms so no single room absorbs all the correction.
    """
    B = [b.copy() for b in boxes]
    for _ in range(iters):
        moved = False
        for i in range(len(B)):
            for j in range(i + 1, len(B)):
                a, b = B[i], B[j]
                ov = [min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])]
                for ax in (0, 1):
                    other = 1 - ax
                    if ov[other] < 0.5:
                        continue                                  # not facing along this axis
                    if a[ax] + a[ax + 2] < b[ax] + b[ax + 2]:     # a is on the low side
                        gap = b[ax] - a[ax + 2]
                    else:
                        gap = a[ax] - b[ax + 2]
                    if gap < WALL_T - 0.01 and ov[ax] > 0 and ov[ax] > ov[other]:
                        continue                                  # overlap is resolved along the other axis
                    if -2.0 < gap < 0.8 and abs(gap - WALL_T) > 0.01:
                        d = (WALL_T - gap) / 2
                        sa = -1 if a[ax] + a[ax + 2] < b[ax] + b[ax + 2] else 1
                        a[[ax, ax + 2]] += sa * d
                        b[[ax, ax + 2]] -= sa * d
                        moved = True
        if not moved:
            break
    return B


def stitch(rooms: list[PhotoRoom], results: list[RoomResult]) -> PhotoPlan:
    # Coarse placement: one joint reconstruction of every photo.
    allimgs = [im for r in rooms for im in r.images]
    owner = [i for i, r in enumerate(rooms) for _ in r.images]
    joint = ReconCapture(run_mapanything(allimgs, rooms[0].K), fps=1.0)
    pcd = fuse(joint, stride=1)
    gyaw = np.radians(manhattan_yaw(np.asarray(pcd.normals)))
    Rg = np.array([[np.cos(gyaw), np.sin(gyaw)], [-np.sin(gyaw), np.cos(gyaw)]])   # world -> global Manhattan
    jcam = np.array([f.T_wc[:3, 3][[0, 2]] for f in joint.frames])

    polys, boxes, rots = [], [], []
    for i, rr in enumerate(results):
        own = np.array([f.T_wc[:3, 3][[0, 2]] for f in rr.cap.frames])     # room-local world
        R, t = _kabsch2d(own, jcam[[k for k, o in enumerate(owner) if o == i]])
        # room Manhattan frame -> room world -> joint world -> global Manhattan
        M = Rg @ R @ rr.R2.T
        theta = np.arctan2(M[1, 0], M[0, 0])
        snap = np.round(theta / (np.pi / 2)) * (np.pi / 2)                  # rooms share the property's axes
        Ms = _rot2(snap)
        V_room = rr.poly.vertices
        ctr_g = (V_room.mean(0) @ M.T) + (t @ Rg.T)                          # where the room's centre lands
        V = (V_room - V_room.mean(0)) @ Ms.T + ctr_g
        polys.append(V)
        boxes.append(np.r_[V.min(0), V.max(0)])
        rots.append((Ms, V_room.mean(0), ctr_g))

    placed = _layout(boxes)
    names, out_polys, shared, edges = [], [], [], []
    for i, (rr, V, b0, b1) in enumerate(zip(results, polys, boxes, placed)):
        shift = b1[:2] - b0[:2]
        rp = rr.poly
        newV = V + shift
        new = RoomPolygon(rp.walls, newV, rp.lengths, rp.length_sigmas, rp.area, rp.area_sigma)
        out_polys.append(new)
        names.append(rr.name)
        Ms, c_room, c_g = rots[i]
        wall_of = {k: (w.axis, w.c) for k, w in enumerate(rp.walls)}
        for o in rr.openings:
            ax, c = wall_of[o.wall]
            p = np.zeros(2)
            p[ax], p[1 - ax] = c, (o.u0 + o.u1) / 2
            pg = (p - c_room) @ Ms.T + c_g + shift
            ax_g = ax if abs(Ms[0, 0]) > 0.5 else 1 - ax
            o.room = i
            shared.append(SharedOpening(o.kind, [i], [o], o.width, o.width_sigma, pg, ax_g))
    for i in range(len(placed)):
        for j in range(i + 1, len(placed)):
            a, b = placed[i], placed[j]
            ov = [min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])]
            if max(ov) > 0.5 and abs(min(ov) + WALL_T) < 0.05:
                edges.append({"rooms": [i, j], "center": None, "opening": None})
    return PhotoPlan(names, out_polys, [r.heights for r in results], shared, edges)


def run_photo(root: Path) -> PhotoPlan:
    rooms = load_rooms(root)
    results = [reconstruct_room(r) for r in rooms]
    return stitch(rooms, results)
