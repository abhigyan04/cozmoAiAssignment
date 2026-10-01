"""Video tier: handheld walkthrough clip -> stitched, dimensioned plan.

Keyframes (sharpest frame per slot) go through MapAnything in overlapping
chunks that fit an 8 GB GPU. Consecutive chunks share frames, so each chunk is
aligned to the previous one with a similarity transform fitted on the shared
cameras. The chained result is wrapped as a LiDAR-like capture and runs
through the same back end as the LiDAR tier, including drift correction
(chunk chaining accumulates exactly the kind of heading drift it removes).
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


def run_video(path: Path, per_second: float = 1.0, drift: str = "auto", use_focal: bool = True):
    from floorplan.lidar import run_lidar

    frames, _ = extract_keyframes(path, per_second=per_second)
    h, w = frames[0].shape[:2]
    K = video_intrinsics(path, w, h) if use_focal else None
    views = reconstruct_chunked(frames, K)
    cap = ReconCapture(views, fps=per_second)
    return run_lidar(cap, drift=drift, stride=1, rays_per_frame=8000, scale_sigma=SCALE_SIGMA)
