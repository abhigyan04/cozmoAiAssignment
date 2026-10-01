"""Head-to-head: our LiDAR tier vs Polycam (iOS 7.0.3, free tier) on living and bedroom1.

Polycam's free tier exports a textured mesh (glTF) but not its floor-plan numbers,
so Polycam's dimensions are read off its own mesh with a deliberately simple,
neutral procedure (documented, no tuning against tape):
  - sample 300k points on the mesh, area-weighted, with face normals
  - floor / ceiling = lowest / highest strong horizontal plane (y is up in Polycam glTF)
  - per horizontal axis: wall points (normal along that axis, 0.3 m above floor to
    0.1 m below ceiling); walls = outermost histogram peaks with >= 15 % of the
    strongest peak; room extent = distance between them
Our numbers are the LiDAR-tier plan of the whole-flat scan, scored by scripts/benchmark.py.
A dimension is "beat or tie" when |our error| <= |Polycam error| + 1 cm.
"""
import json
import sys
from pathlib import Path

import numpy as np
import trimesh
from scipy.ndimage import gaussian_filter1d, maximum_filter1d

ROOT = Path(__file__).resolve().parents[1]
POLY = ROOT / "data" / "raw" / "iphone" / "polycam"
OURS = ROOT / "benchmark" / "results" / "iphone_lidar_flat.json"


def _peaks(v, frac=0.15):
    hist, e = np.histogram(v, bins=np.arange(v.min() - 0.05, v.max() + 0.05, 0.01))
    hs = gaussian_filter1d(hist.astype(float), 1.5)
    pk = np.nonzero((hs == maximum_filter1d(hs, 15)) & (hs > frac * hs.max()))[0]
    return e[pk] + 0.005


def polycam_dims(glb: Path) -> dict:
    s = trimesh.load(glb)
    m = s.dump(concatenate=True) if isinstance(s, trimesh.Scene) else s
    pts, fi = trimesh.sample.sample_surface(m, 300_000, seed=0)
    n = m.face_normals[fi]
    horiz = np.abs(n[:, 1]) > 0.9
    ys = _peaks(pts[horiz, 1])
    floor, ceil = ys.min(), ys.max()
    out = {"ceiling": float(ceil - floor)}
    for ax in (0, 2):
        sel = (np.abs(n[:, ax]) > 0.9) & (pts[:, 1] > floor + 0.3) & (pts[:, 1] < ceil - 0.1)
        p = _peaks(pts[sel, ax])
        out[f"ext{ax}"] = float(p.max() - p.min())
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ours = json.loads(OURS.read_text())
    gt_walls = {(w["room"], w["wall"]): w for w in ours["walls"]}
    gt_ceil = {c["room"]: c for c in ours["ceilings"]}
    md = ["# Head-to-head: our LiDAR tier vs Polycam", "",
          "Polycam for iOS **7.0.3** (free tier), iPhone 17 Pro LiDAR, same rooms, same evening. "
          "Exports: `data/raw/iphone/polycam/<room>/<room>.glb` (+ walkthrough video). "
          "Method and fairness notes: docstring of `scripts/head_to_head.py`.", "",
          "| room | dimension | tape m | ours m | ours err cm | Polycam m | Polycam err cm | beat or tie |",
          "|---|---|---|---|---|---|---|---|"]
    wins = total = 0
    for room in ("living", "bedroom1"):
        pc = polycam_dims(POLY / room / f"{room}.glb")
        # Opposite walls (A/C, B/D) share an axis: assign the two pairs to Polycam's two
        # axes jointly (same rule as the benchmark scorer uses for our plans).
        pair = {k: np.mean([gt_walls[(room, l)]["tape"] for l in k if (room, l) in gt_walls]) for k in ("AC", "BD")}
        a, b = pc["ext0"], pc["ext2"]
        if abs(a - pair["AC"]) + abs(b - pair["BD"]) <= abs(b - pair["AC"]) + abs(a - pair["BD"]):
            axis_of = {"A": a, "C": a, "B": b, "D": b}
        else:
            axis_of = {"A": b, "C": b, "B": a, "D": a}
        for lab in ("A", "B", "C", "D"):
            w = gt_walls.get((room, lab))
            if w is None:
                continue
            tape = w["tape"]
            theirs = axis_of[lab]
            e_o, e_p = 100 * (w["ours"] - tape), 100 * (theirs - tape)
            ok = abs(e_o) <= abs(e_p) + 1.0
            wins += ok
            total += 1
            md.append(f"| {room} | wall {lab} | {tape:.2f} | {w['ours']:.3f} | {e_o:+.1f} | {theirs:.3f} | {e_p:+.1f} | {'yes' if ok else 'no'} |")
        c = gt_ceil.get(room)
        if c:
            e_o, e_p = 100 * (c["ours"] - c["tape"]), 100 * (pc["ceiling"] - c["tape"])
            ok = abs(e_o) <= abs(e_p) + 1.0
            wins += ok
            total += 1
            md.append(f"| {room} | ceiling | {c['tape']:.2f} | {c['ours']:.3f} | {e_o:+.1f} | {pc['ceiling']:.3f} | {e_p:+.1f} | {'yes' if ok else 'no'} |")
    md += ["", f"**Beat or tie on {wins}/{total} shared dimensions ({100 * wins / max(total, 1):.0f} %); gate: ≥ 70 %.**"]
    (ROOT / "benchmark" / "HEAD_TO_HEAD.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
