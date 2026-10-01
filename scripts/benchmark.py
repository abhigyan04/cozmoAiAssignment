"""Score a plan.json against tape ground truth (benchmark/ground_truth.csv).

Matching (documented in the report, overridable with --map rooms.json):
  rooms     photo tier: by folder name. Other tiers: Hungarian assignment on
            room extents (short side, long side) vs tape.
  walls     GT walls A/C and B/D are opposite pairs. Each pair is compared with
            the room's extent along the matching axis (rectangle model), so a
            room scores 2 axes x 2 walls.
  openings  per room and kind (door/window), each GT opening is matched to the
            unused detection with the closest width; > 15 cm off counts as a
            miss. Unmatched detections in matched rooms are phantoms.
  ceiling   per-room dominant ceiling height vs tape (centre).
Every error is also checked against the reported 95% interval (calibration).
"""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

GATES = {  # tier -> wall relative tolerance
    "lidar": None, "video": 0.03, "photo": 0.08,
}


def load_gt(path: Path) -> dict:
    gt = defaultdict(lambda: {"walls": {}, "ceiling": [], "openings": []})
    for r in csv.DictReader(open(path)):
        room, item, label, v = r["room"], r["item"], r["label"], r["value_m"]
        if not v:
            continue
        v = float(v)
        if item == "wall":
            gt[room]["walls"][label] = v
        elif item == "ceiling":
            gt[room]["ceiling"].append(v)
        elif item in ("door", "window"):
            gt[room]["openings"].append({"kind": item, "label": label, "width": v})
    return dict(gt)


def room_extent(room: dict) -> tuple[np.ndarray, np.ndarray]:
    """(extent along x, extent along y) and their 1-sigma, from the polygon and wall sigmas."""
    P = np.array(room["polygon"])
    ext = np.ptp(P, 0)
    sig = []
    for ax in (0, 1):
        # the extent along ax is the length of the walls that run along ax
        s = [w["length"]["sigma"] for w in room["walls"]
             if abs(w["end"][ax] - w["start"][ax]) > abs(w["end"][1 - ax] - w["start"][1 - ax])]
        sig.append(float(np.median(s)) if s else 0.05)
    return ext, np.array(sig)


def gt_axes(g: dict) -> list[float]:
    w = g["walls"]
    pairs = [[w[k] for k in ("A", "C") if k in w], [w[k] for k in ("B", "D") if k in w]]
    return [float(np.mean(p)) for p in pairs if p]


def match_rooms(plan: dict, gt: dict, tier: str, override: dict | None) -> dict:
    if override:
        return override
    names = {r["id"]: r["name"] for r in plan["rooms"]}
    if tier == "photo":
        return {rid: n for rid, n in names.items() if n in gt}
    ids, gts = [r["id"] for r in plan["rooms"]], [k for k in gt if len(gt_axes(gt[k])) == 2]
    C = np.zeros((len(ids), len(gts)))
    for i, r in enumerate(plan["rooms"]):
        e = np.sort(room_extent(r)[0])
        for j, k in enumerate(gts):
            C[i, j] = np.abs(e - np.sort(gt_axes(gt[k]))).sum()
    ri, gj = linear_sum_assignment(C)
    return {ids[i]: gts[j] for i, j in zip(ri, gj) if C[i, j] < 2.0}


def score(plan: dict, gt: dict, mapping: dict) -> dict:
    tier = plan["capture"]["tier"]
    rows, walls, ceil, opens = [], [], [], {"tp": [], "miss": 0, "phantom": 0}
    by_id = {r["id"]: r for r in plan["rooms"]}
    for rid, name in mapping.items():
        r, g = by_id[rid], gt[name]
        ext, sig = room_extent(r)
        # Assign plan axes to GT axis pairs by closest total error.
        A = gt_axes(g)
        order = (0, 1) if abs(ext[0] - A[0]) + abs(ext[1] - A[1]) <= abs(ext[0] - A[1]) + abs(ext[1] - A[0]) else (1, 0)
        pairs = [("A", "C"), ("B", "D")]
        for ax, pair in zip(order, pairs):
            for lab in pair:
                if lab in g["walls"]:
                    t = g["walls"][lab]
                    err = ext[ax] - t
                    walls.append({"room": name, "wall": lab, "tape": t, "ours": round(float(ext[ax]), 3),
                                  "err_cm": round(100 * err, 1), "rel": err / t, "ci95_cm": round(196 * sig[ax], 1),
                                  "inside_ci": abs(err) <= 1.96 * sig[ax]})
        if g["ceiling"] and r["ceiling_height"]:
            t = float(np.mean(g["ceiling"]))
            m = r["ceiling_height"]
            ceil.append({"room": name, "tape": t, "ours": m["value"], "err_cm": round(100 * (m["value"] - t), 1),
                         "inside_ci": m["ci95"][0] <= t <= m["ci95"][1]})
        dets = [o for o in plan["openings"] if rid in o["rooms"] and o["kind"] in ("door", "window")]
        used = set()
        for go in g["openings"]:
            cand = [(abs(o["width"]["value"] - go["width"]), k) for k, o in enumerate(dets)
                    if k not in used and o["kind"] == go["kind"]]
            if cand and min(cand)[0] <= 0.15:
                d, k = min(cand)
                used.add(k)
                o = dets[k]
                opens["tp"].append({"room": name, "label": go["label"], "kind": go["kind"], "tape": go["width"],
                                    "ours": o["width"]["value"], "err_cm": round(100 * (o["width"]["value"] - go["width"]), 1),
                                    "inside_ci": o["width"]["ci95"][0] <= go["width"] <= o["width"]["ci95"][1]})
            else:
                opens["miss"] += 1
        opens["phantom"] += len(dets) - len(used)

    rel = np.array([abs(w["rel"]) for w in walls]) if walls else np.array([np.nan])
    tol = GATES.get(tier)
    n_open = len(opens["tp"]) + opens["miss"] + opens["phantom"]
    ok_open = sum(abs(o["err_cm"]) <= 2.0 for o in opens["tp"])
    summary = {
        "tier": tier,
        "rooms_matched": f"{len(mapping)}/{len(gt)}",
        "wall_mean_abs_err_pct": round(100 * float(np.nanmean(rel)), 2),
        "wall_max_abs_err_pct": round(100 * float(np.nanmax(rel)), 2),
        "wall_gate": None if tol is None else f"{sum(rel <= tol)}/{len(rel)} within +-{100 * tol:.0f}%",
        "wall_inside_ci95": f"{sum(w['inside_ci'] for w in walls)}/{len(walls)}",
        "ceiling_within_1.5cm": f"{sum(abs(c['err_cm']) <= 1.5 for c in ceil)}/{len(ceil)}",
        "openings_within_2cm": f"{ok_open}/{n_open} (missed {opens['miss']}, phantom {opens['phantom']})",
    }
    return {"summary": summary, "walls": walls, "ceilings": ceil, "openings": opens, "mapping": mapping}


def to_markdown(res: dict) -> str:
    s = res["summary"]
    out = [f"### {s['tier']} tier", "", "| metric | value |", "|---|---|"]
    out += [f"| {k} | {v} |" for k, v in s.items() if k != "tier"]
    out += ["", "| room | wall | tape m | ours m | err cm | 95% CI ± cm | inside CI |", "|---|---|---|---|---|---|---|"]
    out += [f"| {w['room']} | {w['wall']} | {w['tape']:.2f} | {w['ours']:.3f} | {w['err_cm']:+.1f} | {w['ci95_cm']:.1f} | "
            f"{'yes' if w['inside_ci'] else '**no**'} |" for w in res["walls"]]
    if res["ceilings"]:
        out += ["", "| room | ceiling tape | ours | err cm | inside CI |", "|---|---|---|---|---|"]
        out += [f"| {c['room']} | {c['tape']:.2f} | {c['ours']:.3f} | {c['err_cm']:+.1f} | {'yes' if c['inside_ci'] else '**no**'} |"
                for c in res["ceilings"]]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--gt", default="benchmark/ground_truth.csv")
    ap.add_argument("--map", help="optional JSON {plan room id: gt room name}")
    ap.add_argument("--out", help="write <out>.json and <out>.md")
    a = ap.parse_args()
    plan = json.load(open(a.plan))
    gt = load_gt(Path(a.gt))
    mapping = match_rooms(plan, gt, plan["capture"]["tier"], json.load(open(a.map)) if a.map else None)
    res = score(plan, gt, mapping)
    md = to_markdown(res)
    print(md)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out + ".json").write_text(json.dumps(res, indent=2, default=float))
        Path(a.out + ".md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
