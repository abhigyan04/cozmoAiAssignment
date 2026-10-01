"""Video tier: handheld walkthrough clip -> stitched, dimensioned plan.

Fix-loop version (see docs/FIX_LOOP.md). One reconstruction of a whole
multi-room walk is not geometrically consistent, so the walk is first split
into room visits and each room is reconstructed on its own:

1. Keyframes: sharpest frame per second.
2. Room grouping: each keyframe gets a DINOv2 image embedding. Contiguous
   visits come from agglomerative clustering constrained to time-adjacent
   frames; visits that look alike (re-entering a room) are merged.
3. Each room's keyframes go through the photo tier's per-room pipeline
   (MapAnything with known intrinsics, near-ceiling wall planes), then the
   photo tier's layout stitch.

The baseline (one chunked reconstruction through the LiDAR back end) is kept
as run_video_single() for the before/after comparison.
"""
from pathlib import Path

import av
import numpy as np

from floorplan.io.recon import ReconCapture, ReconView, run_mapanything
from floorplan.io.video import extract_keyframes

CHUNK = 48          # views per MapAnything call (fits 8 GB at 16:9)
OVERLAP = 12        # shared views between consecutive chunks
SCALE_SIGMA = 0.05  # relative 1-sigma metric-scale error for video (calibrated, see report)


def video_intrinsics(path: Path, w: int, h: int) -> np.ndarray | None:
    """Intrinsics from the container's 35 mm-equivalent focal length, if the phone wrote it.

    Phones record video as a crop of the photo sensor that keeps its full width,
    so the focal is converted on the width of the 4:3 photo frame, not on the
    16:9 video diagonal.
    """
    with av.open(str(path)) as c:
        meta = {**c.metadata, **c.streams.video[0].metadata}
    f35 = None
    for k, v in meta.items():
        if "focal_length" in k.lower():
            try:
                f35 = float(str(v).lower().replace("mm", ""))
            except ValueError:
                pass
    if not f35:
        return None
    long_side = max(w, h)
    diag_43 = np.hypot(long_side, long_side * 3 / 4)          # the 4:3 frame this video is cropped from
    fx = f35 * diag_43 / 43.27
    return np.array([[fx, 0, (w - 1) / 2], [0, fx, (h - 1) / 2], [0, 0, 1]])


def _sim3(A: np.ndarray, B: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    """Umeyama: B ~ s * A @ R.T + t."""
    ma, mb = A.mean(0), B.mean(0)
    A0, B0 = A - ma, B - mb
    U, S, Vt = np.linalg.svd(B0.T @ A0)
    D = np.eye(3)
    D[2, 2] = np.sign(np.linalg.det(U @ Vt))
    R = U @ D @ Vt
    s = float((S * np.diag(D)).sum() / max((A0 ** 2).sum(), 1e-9))
    return s, R, mb - s * ma @ R.T


def _pixel_correspondences(new: list[ReconView], old: list[ReconView], step: int = 4):
    """3D-3D pairs from frames reconstructed in both chunks: the same pixel of the
    same image, back-projected with each chunk's depth and pose. Thousands of pairs
    per overlap, spread over the whole scene, instead of a dozen camera centres
    on a short stretch of path (which leaves rotation badly constrained)."""
    A, B = [], []
    for a, b in zip(new, old):
        h, w = a.depth.shape
        v, u = np.mgrid[0:h:step, 0:w:step]
        da, db = a.depth[v, u], b.depth[v, u]
        ok = (da > 0) & (db > 0)
        A.append(_cam_to_world(u[ok], v[ok], da[ok], a.K, a.T_wc))
        B.append(_cam_to_world(u[ok], v[ok], db[ok], b.K, b.T_wc))
    return np.concatenate(A), np.concatenate(B)


def _cam_to_world(u, v, z, K, T):
    p = np.stack([(u - K[0, 2]) * z / K[0, 0], (v - K[1, 2]) * z / K[1, 1], z, np.ones_like(z)], 1)
    return (p @ T.T)[:, :3]


def _robust_sim3(A: np.ndarray, B: np.ndarray, iters: int = 5, keep: float = 0.8):
    """Umeyama, re-fitted on the best 80% of pairs a few times (trims bad depth)."""
    idx = np.arange(len(A))
    for _ in range(iters):
        s, R, t = _sim3(A[idx], B[idx])
        r = np.linalg.norm(B - (s * A @ R.T + t), axis=1)
        idx = np.argsort(r)[: int(keep * len(A))]
    return s, R, t


def reconstruct_chunked(frames: list[np.ndarray], K: np.ndarray | None) -> list[ReconView]:
    views: list[ReconView] = [None] * len(frames)
    start = 0
    while start < len(frames):
        end = min(start + CHUNK, len(frames))
        chunk = run_mapanything(frames[start:end], K)
        if start == 0:
            for i, v in enumerate(chunk):
                views[i] = v
        else:
            shared = list(range(start, min(start + OVERLAP, end)))
            A, B = _pixel_correspondences([chunk[i - start] for i in shared], [views[i] for i in shared])
            s, R, t = _robust_sim3(A, B)
            # Metric model: chunks should agree on scale; correct the residual anyway
            # (applied to depth too, so geometry stays consistent).
            for i, v in enumerate(chunk):
                gi = start + i
                if gi < start + OVERLAP and views[gi] is not None:
                    continue
                T = v.T_wc.copy()
                T[:3, :3] = R @ T[:3, :3]
                T[:3, 3] = s * R @ T[:3, 3] + t
                views[gi] = ReconView(v.rgb, v.depth * s, v.conf, v.K, T)
        if end == len(frames):
            break
        start = end - OVERLAP
    return views


SEC_PER_SEGMENT = 12.0   # initial visit granularity: ~one segment per 12 s of walking
MERGE_SIM = 0.72         # cosine similarity above which two visits are the same room
MIN_SEGMENT = 4          # keyframes; shorter segments are doorway transitions
ROOM_FRAMES = 16         # keyframes per room for the per-room reconstruction


def embed_frames(frames: list[np.ndarray]) -> np.ndarray:
    """L2-normalised DINOv2-S global descriptors (weights fetched by torch.hub on first use)."""
    import cv2
    import torch
    model = torch.hub.load("facebookresearch/dinov2", "dinov2_vits14", verbose=False).cuda().eval()
    mean, std = np.array([0.485, 0.456, 0.406]), np.array([0.229, 0.224, 0.225])
    out = []
    with torch.no_grad():
        for f in frames:
            x = (cv2.resize(f, (448, 252)) / 255.0 - mean) / std
            out.append(model(torch.tensor(x.transpose(2, 0, 1)[None], dtype=torch.float32).cuda()).cpu().numpy()[0])
    E = np.array(out)
    return E / np.linalg.norm(E, axis=1, keepdims=True)


def group_rooms(E: np.ndarray, duration_s: float) -> list[list[int]]:
    from scipy.sparse import diags
    from sklearn.cluster import AgglomerativeClustering

    n = len(E)
    k = int(np.clip(round(duration_s / SEC_PER_SEGMENT), 2, n // MIN_SEGMENT))
    conn = diags([1, 1], [-1, 1], shape=(n, n))
    lab = AgglomerativeClustering(n_clusters=k, connectivity=conn, linkage="ward").fit_predict(E)
    segs, start = [], 0
    for i in range(1, n + 1):
        if i == n or lab[i] != lab[i - 1]:
            segs.append(list(range(start, i)))
            start = i
    segs = [sg for sg in segs if len(sg) >= MIN_SEGMENT]
    # Merge visits of the same room (union-find on segment-mean similarity).
    M = np.array([E[sg].mean(0) for sg in segs])
    M /= np.linalg.norm(M, axis=1, keepdims=True)
    parent = list(range(len(segs)))
    def find(a):
        while parent[a] != a:
            a = parent[a]
        return a
    S = M @ M.T
    for a, b in sorted(((a, b) for a in range(len(segs)) for b in range(a + 1, len(segs))), key=lambda ab: -S[ab]):
        if S[a, b] >= MERGE_SIM:
            parent[find(b)] = find(a)
    rooms = {}
    for i, sg in enumerate(segs):
        rooms.setdefault(find(i), []).extend(sg)
    return [sorted(v) for v in rooms.values()]


def run_video(path: Path, per_second: float = 1.0, drift: str = "auto", use_focal: bool = True):
    from floorplan.photo import PhotoRoom, reconstruct_room, stitch

    frames, times = extract_keyframes(path, per_second=per_second)
    h, w = frames[0].shape[:2]
    K = video_intrinsics(path, w, h) if use_focal else None
    has_focal = K is not None
    if K is None:   # fall back to a typical phone main-camera field of view
        fx = (w / 2) / np.tan(np.radians(70.0 / 2))
        K = np.array([[fx, 0, (w - 1) / 2], [0, fx, (h - 1) / 2], [0, 0, 1]])
    groups = group_rooms(embed_frames(frames), times[-1] - times[0])
    rooms, results = [], []
    for g in groups:
        pick = [g[i] for i in np.linspace(0, len(g) - 1, min(ROOM_FRAMES, len(g))).round().astype(int)]
        room = PhotoRoom(f"R{len(rooms) + 1}", [frames[i] for i in pick], K, has_focal)
        try:
            res = reconstruct_room(room)
        except Exception:      # a visit with no usable geometry (e.g. only a doorway) is skipped
            continue
        rooms.append(room)
        results.append(res)
    return stitch(rooms, results)


def run_video_single(path: Path, per_second: float = 1.0, drift: str = "auto", use_focal: bool = True):
    """Baseline (before the fix loop): one chunked reconstruction through the LiDAR back end."""
    from floorplan.lidar import run_lidar

    frames, _ = extract_keyframes(path, per_second=per_second)
    h, w = frames[0].shape[:2]
    K = video_intrinsics(path, w, h) if use_focal else None
    views = reconstruct_chunked(frames, K)
    cap = ReconCapture(views, fps=per_second)
    return run_lidar(cap, drift=drift, stride=1, rays_per_frame=8000, scale_sigma=SCALE_SIGMA)
