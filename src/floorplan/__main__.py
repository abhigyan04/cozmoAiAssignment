"""One command per capture:

    python -m floorplan run <capture> [--tier auto|lidar|video|photo] [--out DIR]

Writes DIR/plan.json and DIR/plan.svg.
"""
import argparse
import json
import sys
import time
from pathlib import Path

from floorplan.output.plan import build_plan
from floorplan.output.svg import render_svg


def detect_tier(path: Path) -> str:
    if path.is_file():
        return "video"
    if (path / "odometry.csv").exists() or any((p / "odometry.csv").exists() for p in path.iterdir() if p.is_dir()):
        return "lidar"
    return "photo"


def run(args) -> int:
    src = Path(args.capture)
    tier = args.tier if args.tier != "auto" else detect_tier(src)
    out = Path(args.out or Path("out") / src.stem)
    out.mkdir(parents=True, exist_ok=True)
    t = time.time()
    if tier == "lidar":
        from floorplan.io.stray import StrayCapture
        from floorplan.lidar import run_lidar
        res = run_lidar(StrayCapture(src), drift=args.drift)
    elif tier == "video":
        from floorplan.video import run_video
        res = run_video(src, drift=args.drift)
    elif tier == "photo":
        from floorplan.photo import run_photo
        res = run_photo(src)
    else:
        print(f"tier '{tier}' is not implemented yet", file=sys.stderr)
        return 2
    if not args.no_damage:
        from floorplan.damage import damage_for
        res.damage = damage_for(res)
    plan = build_plan(res, tier, str(src), time.time() - t)
    (out / "plan.json").write_text(json.dumps(plan, indent=2))
    (out / "plan.svg").write_text(render_svg(plan), encoding="utf-8")
    p = plan["property"]
    print(f"{tier}: {p['room_count']} rooms, {p['floor_area']['value']:.2f} m2, "
          f"{len(plan['openings'])} openings, {len(p['adjacency'])} connections "
          f"{len(plan['damage'])} damage regions, {len(plan['concealed_damage_flags'])} concealed flags "
          f"({plan['capture']['processing_seconds']}s) -> {out / 'plan.json'}, {out / 'plan.svg'}")
    for w in plan["quality"]["warnings"]:
        print("  warning:", w)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="floorplan")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="process one capture")
    r.add_argument("capture", help="Stray Scanner folder, video file, or folder of per-room photo folders")
    r.add_argument("--tier", default="auto", choices=["auto", "lidar", "video", "photo"])
    r.add_argument("--out", help="output folder (default: out/<capture name>)")
    r.add_argument("--drift", default="auto", choices=["auto", "on", "off"],
                   help="drift correction; auto = apply only if it sharpens the walls")
    r.add_argument("--no-damage", action="store_true", help="skip damage detection")
    args = ap.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
