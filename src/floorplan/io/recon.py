"""Image-only captures (video keyframes, photos) -> a LiDAR-like capture.

MapAnything (Meta, Apache-2.0 weights) regresses metric depth, camera poses and
intrinsics from plain images in one feed-forward pass. We wrap its output in
the same interface as StrayCapture (frames with camera->world poses, depth maps,
confidence), so every tier runs through the identical geometry back end.

Its world frame is the first camera, not gravity. We level it: the room's
dominant plane normals give three Manhattan axes, and "up" is the one closest
to the cameras' average up direction (people hold phones roughly upright).
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from floorplan.io.stray import Frame, StrayCapture

MODEL_ID = "facebook/map-anything-apache"


@dataclass
class ReconView:
    rgb: np.ndarray        # H x W x 3 uint8, model resolution
    depth: np.ndarray      # H x W metres (z-depth), 0 = invalid
    conf: np.ndarray       # H x W, model confidence
    K: np.ndarray          # 3x3 at model resolution
    T_wc: np.ndarray       # 4x4 camera->world, OpenCV camera


_MODEL = None


def load_model(device: str = "cuda"):
    """Load MapAnything once per process."""
    global _MODEL
    if _MODEL is None:
        import torch
        from mapanything.models import MapAnything
        # The ViT-g image encoder is ~4.5 GB in fp32, too much for an 8 GB GPU; it runs
        # under bf16 autocast anyway, so store its weights in bf16. The rest stays fp32.
        model = MapAnything.from_pretrained(MODEL_ID)
        model.encoder.to(dtype=torch.bfloat16)

        def _features_to_fp32(module, inputs, output):   # downstream code expects fp32 features
            output.features = output.features.float()
            if getattr(output, "registers", None) is not None:
                output.registers = output.registers.float()
            return output
        model.encoder.register_forward_hook(_features_to_fp32)
        _MODEL = model.to(device)
    return _MODEL


def run_mapanything(images: list[np.ndarray], K: np.ndarray | None = None,
                    device: str = "cuda") -> list[ReconView]:
    """images: RGB uint8 arrays. K: intrinsics at the images' resolution, if known.

    Known intrinsics matter a lot: with them the model only has to solve depth
    and pose; without them a wrong field of view skews both depth and scale.
    """
    import torch
    from mapanything.utils.image import preprocess_inputs

    model = load_model(device)
    raw = []
    for img in images:
        v = {"img": torch.from_numpy(img)}
        if K is not None:
            v["intrinsics"] = torch.from_numpy(K.astype(np.float32))
        raw.append(v)
    views = preprocess_inputs(raw)
    with torch.no_grad():
        preds = model.infer(views, memory_efficient_inference=True, use_amp=True,
                            amp_dtype="bf16", apply_mask=True, mask_edges=True)
    out = []
    for p in preds:
        mask = p["mask"][0, ..., 0].cpu().numpy().astype(bool)
        depth = p["depth_z"][0, ..., 0].float().cpu().numpy()
        depth[~mask] = 0.0
        out.append(ReconView(
            rgb=(p["img_no_norm"][0].float().cpu().numpy() * 255).clip(0, 255).astype(np.uint8),
            depth=depth,
            conf=p["conf"][0].float().cpu().numpy(),
            K=p["intrinsics"][0].float().cpu().numpy(),
            T_wc=p["camera_poses"][0].float().cpu().numpy(),
        ))
    torch.cuda.empty_cache()
    return out


def gravity_align(views: list[ReconView]) -> np.ndarray:
    """4x4 rotation taking the reconstruction's world into a y-up world."""
    import open3d as o3d
    pts = []
    for v in views:
        pts.append(_backproject(v.depth, v.K, v.T_wc, stride=4))
    P = np.concatenate(pts)
    pcd = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(P)).voxel_down_sample(0.03)
    pcd.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=0.12, max_nn=30))
    N = np.asarray(pcd.normals)
    cam_up = -np.mean([v.T_wc[:3, 1] for v in views], axis=0)   # OpenCV camera y points down
    cam_up /= np.linalg.norm(cam_up)
    # Mean-shift on the sphere, starting from the cameras' up: floor and ceiling
    # normals (sign-flipped to agree) pull it onto the true vertical.
    cand = N * np.sign(N @ cam_up)[:, None]
    up = cam_up
    for ang in (40, 30, 20, 10, 5, 5):
        near = cand[cand @ up > np.cos(np.radians(ang))]
        if len(near) < 100:
            break
        m = near.mean(0)
        up = m / np.linalg.norm(m)
    # Rotation mapping `up` to +y (Rodrigues).
    y = np.array([0.0, 1.0, 0.0])
    v, c = np.cross(up, y), float(up @ y)
    Vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    R = np.eye(3) + Vx + Vx @ Vx / (1 + c)
    T = np.eye(4)
    T[:3, :3] = R
    return T


def _backproject(depth, K, T_wc, stride=1):
    h, w = depth.shape
    v, u = np.mgrid[0:h:stride, 0:w:stride]
    z = depth[v, u]
    ok = z > 0
    u, v, z = u[ok], v[ok], z[ok]
    x = (u - K[0, 2]) * z / K[0, 0]
    y = (v - K[1, 2]) * z / K[1, 1]
    p = np.stack([x, y, z, np.ones_like(z)], 1)
    return (p @ T_wc.T)[:, :3]


class ReconCapture(StrayCapture):
    """Duck-types StrayCapture so run_lidar() works unchanged on image-only input."""

    def __init__(self, views: list[ReconView], fps: float, min_conf_pct: float = 20.0):
        T_align = gravity_align(views)
        self.root = None
        self.views = views
        self.fps = fps
        self.frames = [Frame(i, i / fps, T_align @ v.T_wc, v.K) for i, v in enumerate(views)]
        # Per-view confidence threshold: drop the least confident pixels.
        self._conf_thr = [np.percentile(v.conf[v.depth > 0], min_conf_pct) if (v.depth > 0).any() else np.inf
                          for v in views]

    def depth(self, i: int) -> np.ndarray:
        return self.views[i].depth

    def confidence(self, i: int) -> np.ndarray:
        v = self.views[i]
        return np.where((v.depth > 0) & (v.conf >= self._conf_thr[i]), 2, 0).astype(np.uint8)

    def K_depth(self, i: int) -> np.ndarray:
        return self.views[i].K


def save_frames(frames: list[np.ndarray], folder: Path) -> list[Path]:
    import cv2
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, f in enumerate(frames):
        p = folder / f"{i:05d}.jpg"
        cv2.imwrite(str(p), cv2.cvtColor(f, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 95])
        paths.append(p)
    return paths
