"""Loader for Stray Scanner (iOS) LiDAR captures.

Folder layout: rgb.mp4, depth/NNNNNN.png (uint16 mm, 256x192),
confidence/NNNNNN.png (0/1/2), odometry.csv (ARKit camera->world pose
per frame), camera_matrix.csv (intrinsics at RGB resolution 1920x1440).
"""
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

RGB_W, RGB_H = 1920, 1440


@dataclass
class Frame:
    index: int
    timestamp: float
    T_wc: np.ndarray  # 4x4 camera->world; camera axes are OpenCV (x right, y down, z fwd), world is y-up
    K_rgb: np.ndarray  # 3x3 intrinsics at RGB resolution


class StrayCapture:
    def __init__(self, root: str | Path):
        root = Path(root)
        # Accept either the scan folder or a parent holding exactly one scan.
        if not (root / "odometry.csv").exists():
            subs = [p for p in root.iterdir() if (p / "odometry.csv").exists()]
            if len(subs) != 1:
                raise FileNotFoundError(f"no Stray scan found in {root}")
            root = subs[0]
        self.root = root
        self.frames = self._read_odometry()

    def _read_odometry(self) -> list[Frame]:
        rows = np.genfromtxt(self.root / "odometry.csv", delimiter=",",
                             skip_header=1, usecols=range(13))
        frames = []
        for r in rows:
            T = np.eye(4)
            T[:3, :3] = Rotation.from_quat(r[5:9]).as_matrix()  # qx qy qz qw
            T[:3, 3] = r[2:5]
            K = np.array([[r[9], 0, r[11]], [0, r[10], r[12]], [0, 0, 1]])
            frames.append(Frame(int(r[1]), float(r[0]), T, K))
        return frames

    def depth(self, i: int) -> np.ndarray:
        """Depth in metres, float32, at LiDAR resolution (192x256)."""
        d = cv2.imread(str(self.root / "depth" / f"{i:06d}.png"), cv2.IMREAD_UNCHANGED)
        return d.astype(np.float32) / 1000.0

    def confidence(self, i: int) -> np.ndarray:
        return cv2.imread(str(self.root / "confidence" / f"{i:06d}.png"), cv2.IMREAD_UNCHANGED)

    def K_depth(self, i: int) -> np.ndarray:
        """Intrinsics rescaled from RGB resolution to depth-map resolution."""
        h, w = 192, 256
        S = np.diag([w / RGB_W, h / RGB_H, 1.0])
        return S @ self.frames[i].K_rgb

    def points_world(self, i: int, min_conf: int = 2, max_depth: float = 5.0) -> np.ndarray:
        """Back-project frame i to world-frame 3D points (N,3)."""
        d, c, K = self.depth(i), self.confidence(i), self.K_depth(i)
        v, u = np.nonzero((c >= min_conf) & (d > 0.1) & (d < max_depth))
        z = d[v, u]
        x = (u - K[0, 2]) * z / K[0, 0]
        y = (v - K[1, 2]) * z / K[1, 1]
        # Stray exports poses for an OpenCV-convention camera (verified empirically:
        # this gives a sharp floor plane; the ARKit y-up/z-back flip smears it).
        p_cam = np.stack([x, y, z, np.ones_like(z)], axis=1)
        return (p_cam @ self.frames[i].T_wc.T)[:, :3]
