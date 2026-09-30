"""Drift correction for a continuous multi-room capture.

VIO (ARKit) keeps gravity exact but slowly drifts in heading (yaw). Walls are
Manhattan, so the wall directions seen in any short time window must match the
global Manhattan frame; any mismatch is heading drift at that moment.

1. Plane-anchored yaw correction: estimate the Manhattan yaw of a sliding
   window (about 2 s of frames), take its deviation from the global yaw,
   smooth it (median over ~11 windows; single windows are noisy), and rotate
   each frame to cancel its drift. Positions are re-integrated from the
   corrected heading so the trajectory bends back too.
2. Loop closure: the capture protocol starts and ends aimed at the same room
   corner. We register the first and last seconds with ICP and spread the
   residual offset linearly over the trajectory, but only when the
   registration is well-conditioned (two search radii agree).
"""
import copy
from dataclasses import dataclass, field

import numpy as np
import open3d as o3d
from scipy.ndimage import maximum_filter, median_filter

from floorplan.io.stray import StrayCapture
from floorplan.geometry.structure import manhattan_yaw


@dataclass
class DriftReport:
    block_frames: list[int] = field(default_factory=list)
    block_drift_deg: list[float] = field(default_factory=list)
    max_abs_drift_deg: float = 0.0
    loop_closed: bool = False
    loop_fitness: float = 0.0
    loop_offset_m: float = 0.0          # residual start/end offset that was distributed
    loop_yaw_deg: float = 0.0


def wall_sharpness(P: np.ndarray, N: np.ndarray, yaw_deg: float) -> float:
    """Fraction of wall points within +-1 cm of their wall's peak position.

    Drift smears one wall into several slightly offset copies, so crisper walls
    (higher score) mean more consistent poses. Needs no ground truth, which is
    why it is used both for the on/off ablation and to guard the correction.
    """
    t = np.radians(yaw_deg)
    R = np.array([[np.cos(t), np.sin(t)], [-np.sin(t), np.cos(t)]])
    XZ, N2 = P[:, [0, 2]] @ R.T, N[:, [0, 2]] @ R.T
    vert = np.abs(N[:, 1]) < 0.2
    scores = []
    for ax in (0, 1):
        v = XZ[vert & (np.abs(N2[:, ax]) > 0.95), ax]
        h, _ = np.histogram(v, bins=np.arange(v.min(), v.max() + 0.01, 0.01))
        peak = (h == maximum_filter(h, size=21)) & (h > 30)       # one peak per wall
        near = maximum_filter(peak.astype(int), size=3) > 0         # peak bin +- 1 cm
        scores.append(h[near].sum() / len(v))
    return float(np.mean(scores))


def _Ry(deg: float) -> np.ndarray:
    """Rotation about world +y; applied to world points it lowers their yaw by `deg`."""
    t = np.radians(deg)
    c, s = np.cos(t), np.sin(t)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def _window_cloud(cap: StrayCapture, idx) -> o3d.geometry.PointCloud:
    pts = np.concatenate([cap.points_world(i) for i in idx])
    pc = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(pts)).voxel_down_sample(0.03)
    pc.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=0.1, max_nn=30))
    return pc


def _wrap45(d):
    return (np.asarray(d) + 45.0) % 90.0 - 45.0


def correct_drift(cap: StrayCapture, global_yaw: float, fps_hint: float = 45.0,
                  window_s: float = 2.0, loop: bool = True) -> tuple[StrayCapture, DriftReport]:
    rep = DriftReport()
    n = len(cap.frames)
    half = int(window_s * fps_hint / 2)
    step = max(half // 2, 10)

    # 1. Per-block heading drift relative to the global Manhattan frame.
    centers, drift = [], []
    for c in range(half, n - half, step):
        pc = _window_cloud(cap, range(c - half, c + half, 6))
        N = np.asarray(pc.normals)
        if (np.abs(N[:, 1]) < 0.2).sum() < 500:   # looking at floor/ceiling only: no heading info
            continue
        centers.append(c)
        drift.append(_wrap45(manhattan_yaw(N) - global_yaw))
    if len(drift) >= 3:
        d = median_filter(np.array(drift), size=11, mode="nearest")  # reject noisy windows
        per_frame = np.interp(np.arange(n), centers, d)
        # Anchor at the first frame: drift is what accumulates *after* the start,
        # so frame 0 stays put and the map is not rotated as a whole.
        per_frame -= per_frame[0]
    else:
        per_frame = np.zeros(n)
    rep.block_frames, rep.block_drift_deg = centers, [float(x) for x in drift]
    rep.max_abs_drift_deg = float(np.abs(per_frame).max())

    out = copy.copy(cap)
    out.frames = copy.deepcopy(cap.frames)
    p_prev_old = cap.frames[0].T_wc[:3, 3].copy()
    p_prev_new = p_prev_old.copy()
    for i, f in enumerate(out.frames):
        R = _Ry(per_frame[i])
        p_old = cap.frames[i].T_wc[:3, 3]
        p_new = p_prev_new + R @ (p_old - p_prev_old)   # re-integrate with corrected heading
        f.T_wc[:3, :3] = R @ cap.frames[i].T_wc[:3, :3]
        f.T_wc[:3, 3] = p_new
        p_prev_old, p_prev_new = p_old, p_new

    # 2. Loop closure between the first and last seconds of the capture.
    if loop and n > 4 * half:
        a = _window_cloud(out, range(0, 2 * half, 4))
        b = _window_cloud(out, range(n - 2 * half, n, 4))
        regs = [o3d.pipelines.registration.registration_icp(
                    b, a, thr, np.eye(4),
                    o3d.pipelines.registration.TransformationEstimationPointToPlane())
                for thr in (0.10, 0.25)]
        rep.loop_fitness = float(regs[0].fitness)
        # A view of one plane (e.g. only floor) lets ICP slide freely, and the answer then
        # depends on the search radius. Accept only if two radii agree (well-conditioned).
        Ts = [r.transformation for r in regs]
        yaw_gap = abs(np.degrees(np.arctan2(Ts[0][0, 2], Ts[0][0, 0]) - np.arctan2(Ts[1][0, 2], Ts[1][0, 0])))
        stable = yaw_gap < 0.5 and np.linalg.norm(Ts[0][:3, 3] - Ts[1][:3, 3]) < 0.03
        if stable and regs[0].fitness > 0.5 and regs[0].inlier_rmse < 0.05:
            T = Ts[0]                              # moves the end cloud onto the start cloud
            yaw_end = float(np.degrees(np.arctan2(T[0, 2], T[0, 0])))   # T's rotation is _Ry(yaw_end)
            origin = out.frames[0].T_wc[:3, 3].copy()
            # Express T as a rotation about the start point plus a shift, so a
            # fraction of it can be applied: T(p) = origin + R (p - origin) + shift.
            shift = T[:3, 3] - (np.eye(3) - _Ry(yaw_end)) @ origin
            shift[1] = 0.0                         # gravity axis is exact; don't touch height
            rep.loop_closed = True
            rep.loop_offset_m = float(np.linalg.norm(shift))
            rep.loop_yaw_deg = yaw_end
            for i, f in enumerate(out.frames):
                a_ = i / (n - 1)                   # 0 at start, 1 at end
                Ra = _Ry(yaw_end * a_)
                f.T_wc[:3, :3] = Ra @ f.T_wc[:3, :3]
                f.T_wc[:3, 3] = origin + Ra @ (f.T_wc[:3, 3] - origin) + a_ * shift
    return out, rep