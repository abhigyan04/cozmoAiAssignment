"""Keyframes from a handheld walkthrough video.

We want frames that are sharp and spread evenly along the walk. Motion blur is
the main enemy of handheld video, so within each time slot we keep the frame
with the highest Laplacian variance (a standard focus/sharpness measure).
"""
from pathlib import Path

import av
import cv2
import numpy as np


def sharpness(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def extract_keyframes(video: str | Path, per_second: float = 2.0, max_side: int = 1024,
                      max_frames: int | None = None) -> tuple[list[np.ndarray], list[float]]:
    """Return (RGB frames, timestamps): the sharpest frame in every 1/per_second slot.

    Frames are downscaled so the long side is max_side; the reconstruction model
    works at ~518 px anyway, so this only saves memory.
    """
    frames, times = [], []
    best, best_s, slot = None, -1.0, 0
    with av.open(str(video)) as c:
        stream = c.streams.video[0]
        stream.thread_type = "AUTO"
        for f in c.decode(stream):
            if f.time is None:
                continue
            k = int(f.time * per_second)
            if k != slot and best is not None:
                frames.append(best[0])
                times.append(best[1])
                best, best_s = None, -1.0
            slot = k
            img = f.to_ndarray(format="rgb24")
            # Phones store portrait video as landscape pixels plus a rotation flag.
            rot = int(getattr(f, "rotation", 0) or 0) % 360
            if rot:
                img = np.ascontiguousarray(np.rot90(img, k=rot // 90))
            h, w = img.shape[:2]
            s = max_side / max(h, w)
            if s < 1:
                img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
            sh = sharpness(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY))
            if sh > best_s:
                best, best_s = (img, float(f.time)), sh
        if best is not None:
            frames.append(best[0])
            times.append(best[1])
    if max_frames and len(frames) > max_frames:
        idx = np.linspace(0, len(frames) - 1, max_frames).round().astype(int)
        frames, times = [frames[i] for i in idx], [times[i] for i in idx]
    return frames, times
