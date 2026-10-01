"""Surface damage on walls, tied to a named surface with a metric extent.

Geometry first, learning second:
1. Wall pixels only: a pixel belongs to wall k if its 3D point (from depth and
   pose) lies within 3 cm of wall k's plane, inside the wall's extent. Furniture,
   curtains, fans and anything in front of the wall drop out by construction.
2. Candidates: paint is near-uniform, so a water stain / damp patch / mould is a
   soft region darker than its local background, and a crack is a thin dark
   ridge (morphological black-hat).
3. Classification: each candidate crop is labelled zero-shot by CLIP against
   damage and non-damage prompts (posters, switches and shadows sit *on* the
   wall plane, so geometry alone cannot reject them).
4. Extent: candidate pixels are 3D points on a known plane, so width, height
   and area come out in metres on that surface.
Detections from different frames on the same surface are merged.
"""
from dataclasses import dataclass

import cv2
import numpy as np

CLIP_ID = "openai/clip-vit-base-patch32"
PROMPTS = {
    "crack": "a photo of a crack in a painted wall",
    "water_stain": "a photo of a brown water stain on a painted wall",
    "mould": "a photo of black mould spots on a wall",
    "peeling_paint": "a photo of peeling paint on a wall",
    "_poster": "a photo of a poster or picture hanging on a wall",
    "_fixture": "a photo of a light switch, socket or wire on a wall",
    "_shadow": "a photo of a shadow on a plain wall",
    "_clean": "a photo of a clean plain painted wall",
    "_edge": "a photo of a door frame or the corner of a room",
    "_curtain": "a photo of a patterned curtain or fabric",
    "_door": "a photo of a wooden door",
}
DAMAGE = [k for k in PROMPTS if not k.startswith("_")]
ON_PLANE = 0.03
MIN_PROB = 0.45


@dataclass
class Damage:
    room: int
    wall: int              # index of the wall in the room polygon
    cls: str
    u0: float              # extent along the wall, metres (Manhattan frame coordinate)
    u1: float
    h0: float              # height above floor, metres
    h1: float
    area_m2: float
    confidence: float
    frames: int = 1


class _Clip:
    def __init__(self):
        import torch
        from transformers import CLIPModel, CLIPProcessor
        self.torch = torch
        self.model = CLIPModel.from_pretrained(CLIP_ID).cuda().eval()
        self.proc = CLIPProcessor.from_pretrained(CLIP_ID)
        self.prompts = list(PROMPTS.values())

    def classify(self, crops: list[np.ndarray]) -> np.ndarray:
        """Softmax over the prompts for each crop (CLIP image-text similarity)."""
        if not crops:
            return np.zeros((0, len(PROMPTS)))
        with self.torch.no_grad():
            x = self.proc(text=self.prompts, images=crops, return_tensors="pt", padding=True).to("cuda")
            return self.model(**x).logits_per_image.softmax(-1).cpu().numpy()


def _wall_pixels(depth, K, T_wc, R2, floor_y, walls):
    """Per-pixel wall index (-1 = not on a wall), u (along wall) and h (height)."""
    h, w = depth.shape
    v, u = np.mgrid[0:h, 0:w]
    z = depth
    p = np.stack([(u - K[0, 2]) * z / K[0, 0], (v - K[1, 2]) * z / K[1, 1], z, np.ones_like(z)], -1)
    P = p.reshape(-1, 4) @ T_wc.T
    XZ = P[:, [0, 2]] @ R2.T
    H = P[:, 1] - floor_y
    lab = np.full(h * w, -1)
    U = np.zeros(h * w)
    for k, (axis, c, lo, hi) in enumerate(walls):
        on = (z.reshape(-1) > 0) & (np.abs(XZ[:, axis] - c) < ON_PLANE) & \
             (XZ[:, 1 - axis] > lo) & (XZ[:, 1 - axis] < hi) & (H > 0.05)
        lab[on] = k
        U[on] = XZ[on, 1 - axis]
    return lab.reshape(h, w), U.reshape(h, w), H.reshape(h, w)


def _candidates(rgb, wallmask):
    """Dark soft blobs (stains) and thin dark ridges (cracks) inside the wall mask."""
    L = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)[..., 0].astype(np.float32)
    m = wallmask.astype(np.uint8)
    if m.sum() < 500:
        return []
    # Local background: normalised blur over wall pixels only.
    k = max(31, (min(L.shape) // 8) | 1)
    num = cv2.GaussianBlur(L * m, (k, k), 0)
    den = cv2.GaussianBlur(m.astype(np.float32), (k, k), 0) + 1e-6
    bg = num / den
    resid = (L - bg) * m
    stain = ((resid < -10) & (m > 0)).astype(np.uint8)
    stain = cv2.morphologyEx(stain, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    bh = cv2.morphologyEx(L, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9)))
    crack = ((bh > 12) & (m > 0)).astype(np.uint8)
    out = []
    for kind, mask, min_px in (("blob", stain, 150), ("line", crack, 80)):
        n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        for i in range(1, n):
            x, y, w, h, a = stats[i]
            if a < min_px:
                continue
            if kind == "line" and max(w, h) < 4 * min(w, h):   # cracks are elongated
                continue
            if _busy(rgb, (x, y, w, h)):
                continue
            out.append((kind, lab == i, (x, y, w, h)))
    return out


def _busy(rgb, box, pad: int = 12) -> bool:
    """Patterned surroundings (curtains, posters, fabric) rather than painted plaster.

    Damage sits on near-uniform paint: around a real stain or crack the image is
    low in colour saturation and has few edges. Curtains hang within a few cm of
    the window wall, so geometry alone keeps them in the wall mask."""
    x, y, w, h = box
    patch = rgb[max(y - pad, 0):y + h + pad, max(x - pad, 0):x + w + pad]
    if patch.size == 0:
        return True
    hsv = cv2.cvtColor(patch, cv2.COLOR_RGB2HSV)
    edges = cv2.Canny(cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY), 60, 150)
    return float(hsv[..., 1].mean()) > 90 or float((edges > 0).mean()) > 0.12


def detect_damage(views, R2, floor_y, room_walls, clip: "_Clip | None" = None, max_frames: int = 40):
    """views: iterable of (rgb, depth, K, T_wc) at the same resolution, world frame of the room.
    room_walls: list over rooms of [(axis, c, lo, hi)] in the Manhattan frame given by R2."""
    clip = clip or _Clip()
    found: list[Damage] = []
    views = list(views)
    step = max(1, len(views) // max_frames)
    for rgb, depth, K, T in views[::step]:
        for ri, walls in enumerate(room_walls):
            lab, U, H = _wall_pixels(depth, K, T, R2, floor_y, walls)
            for wi in range(len(walls)):
                cands = _candidates(rgb, lab == wi)
                crops, keep = [], []
                for kind, mask, (x, y, w, h) in cands:
                    pad = max(w, h) // 2 + 8
                    crop = rgb[max(y - pad, 0):y + h + pad, max(x - pad, 0):x + w + pad]
                    if crop.size == 0:
                        continue
                    crops.append(crop)
                    keep.append(mask)
                probs = clip.classify(crops)
                names = list(PROMPTS)
                for mask, pr in zip(keep, probs):
                    j = int(np.argmax(pr))
                    if names[j] not in DAMAGE or pr[j] < MIN_PROB:
                        continue
                    u, hh = U[mask], H[mask]
                    z = depth[mask]
                    px_area = (z / K[0, 0]) * (z / K[1, 1])            # m2 per pixel at that depth
                    found.append(Damage(ri, wi, names[j], float(u.min()), float(u.max()),
                                        float(hh.min()), float(hh.max()), float(px_area.sum()), float(pr[j])))
    return _merge(found)


def _merge(ds: list[Damage], gap: float = 0.10) -> list[Damage]:
    """Same room, wall and class, overlapping extents (within 10 cm) -> one region."""
    out: list[Damage] = []
    for d in sorted(ds, key=lambda d: -d.confidence):
        for o in out:
            if (o.room, o.wall, o.cls) == (d.room, d.wall, d.cls) and \
               d.u0 < o.u1 + gap and o.u0 < d.u1 + gap and d.h0 < o.h1 + gap and o.h0 < d.h1 + gap:
                o.u0, o.u1 = min(o.u0, d.u0), max(o.u1, d.u1)
                o.h0, o.h1 = min(o.h0, d.h0), max(o.h1, d.h1)
                o.area_m2 = max(o.area_m2, d.area_m2)
                o.frames += 1
                break
        else:
            out.append(d)
    # A region seen in a single frame only is likely noise unless it is confident.
    return [d for d in out if d.frames >= 2 or d.confidence >= 0.7]


# ------------------------------------------------------------ rules and scope

def concealed_flags(damage: list[Damage], heights: list) -> list[dict]:
    """Rule-based flags for damage that is likely hidden behind or above a surface."""
    flags = []
    for i, d in enumerate(damage):
        top = heights[d.room].height if d.room < len(heights) and heights[d.room].height else 2.6
        if d.cls in ("water_stain", "mould") and d.h1 > top - 0.3:
            flags.append({"damage": i, "rule": "R1 stain/mould within 30 cm of ceiling",
                          "flag": "possible leak above ceiling (slab, roof or upstairs plumbing); inspect ceiling void"})
        if d.cls in ("water_stain", "mould") and d.h0 < 0.3:
            flags.append({"damage": i, "rule": "R2 stain/mould within 30 cm of floor",
                          "flag": "possible rising damp or concealed pipe leak in wall cavity; moisture-meter the wall base"})
        if d.cls == "mould":
            flags.append({"damage": i, "rule": "R3 visible mould",
                          "flag": "mould growth implies sustained moisture; likely concealed growth behind finish"})
        if d.cls == "crack" and (d.u1 - d.u0 > 1.0 or d.h1 - d.h0 > 1.0):
            flags.append({"damage": i, "rule": "R4 crack longer than 1 m",
                          "flag": "possible structural movement or failed lintel; check behind plaster and at openings"})
        if d.cls == "water_stain" and d.area_m2 > 0.25:
            flags.append({"damage": i, "rule": "R5 water stain larger than 0.25 m2",
                          "flag": "large wetting area; substrate (plaster/board) likely saturated beyond visible stain"})
    return flags


SCOPE = {
    "crack": ("Rake out, fill and sand crack; prime and repaint wall", "m"),
    "water_stain": ("Treat stain with stain-blocking primer; repaint wall", "m2"),
    "mould": ("Fungicidal wash, stain-block, anti-mould repaint", "m2"),
    "peeling_paint": ("Scrape, prepare and repaint affected area", "m2"),
}


def scope_items(damage: list[Damage], wall_ids: list[list[str]], wall_areas: list[list[float]]) -> list[dict]:
    items, repainted = [], set()
    for i, d in enumerate(damage):
        desc, unit = SCOPE[d.cls]
        surface = wall_ids[d.room][d.wall]
        qty = max(d.u1 - d.u0, d.h1 - d.h0) if unit == "m" else d.area_m2
        items.append({"surface": surface, "damage": i, "description": desc,
                      "quantity": round(qty, 2), "unit": unit})
        # Repaint is per wall, not per patch: one item per affected wall surface.
        if surface not in repainted:
            repainted.add(surface)
            items.append({"surface": surface, "damage": i, "description": "Repaint full wall for uniform finish",
                          "quantity": round(wall_areas[d.room][d.wall], 2), "unit": "m2"})
    return items


def room_walls(polys) -> list[list[tuple]]:
    """[(axis, c, lo, hi)] per room from room polygons (Manhattan frame)."""
    out = []
    for rp in polys:
        V, K = rp.vertices, len(rp.walls)
        ws = []
        for k, w in enumerate(rp.walls):
            a, b = V[k], V[(k + 1) % K]
            lo, hi = sorted([a[1 - w.axis], b[1 - w.axis]])
            ws.append((w.axis, w.c, lo, hi))
        out.append(ws)
    return out


def stray_views(cap, every: int = 15, size=(960, 720)):
    """(rgb, depth, K, T_wc) for every `every`-th Stray frame, depth upsampled to the RGB size."""
    import av
    want = set(range(0, len(cap.frames), every))
    with av.open(str(cap.root / "rgb.mp4")) as c:
        for k, f in enumerate(c.decode(c.streams.video[0])):
            if k not in want:
                continue
            rgb = cv2.resize(f.to_ndarray(format="rgb24"), size, interpolation=cv2.INTER_AREA)
            d = cv2.resize(cap.depth(k) * (cap.confidence(k) >= 1), size, interpolation=cv2.INTER_NEAREST)
            K = cap.frames[k].K_rgb.copy()
            K[0] *= size[0] / 1920
            K[1] *= size[1] / 1440
            yield rgb, d, K, cap.frames[k].T_wc


def recon_views(cap):
    """(rgb, depth, K, T_wc) for an image-only (MapAnything) capture."""
    for v, f in zip(cap.views, cap.frames):
        yield v.rgb, v.depth, v.K, f.T_wc


def damage_for(res) -> list[Damage]:
    """Run damage detection on a pipeline result of any tier (LiDAR or image-only)."""
    clip = _Clip()
    if getattr(res, "results", None):                      # photo / video: per room, own frame
        out = []
        for i, rr in enumerate(res.results):
            for d in detect_damage(recon_views(rr.cap), rr.R2, rr.floor_y, room_walls([rr.poly]), clip):
                d.room = i
                out.append(d)
        return out
    if getattr(res, "cap", None) is not None and res.polys:  # LiDAR
        return detect_damage(stray_views(res.cap, every=10), res.fm.R, res.floor.y, room_walls(res.polys), clip)
    return []
