"""Render plan.json as an SVG floor plan (rooms, dimensioned walls, openings)."""
from html import escape

PX = 100          # pixels per metre
MARGIN = 80
COLOURS = ["#e8f1fb", "#fdf1e3", "#eaf6ec", "#f7e9f3", "#fbf7de", "#e9f4f6", "#f3ece6", "#eeeefb"]


def render_svg(plan: dict) -> str:
    pts = [p for r in plan["rooms"] for p in r["polygon"]]
    W = max(p[0] for p in pts) * PX + 2 * MARGIN
    H = max(p[1] for p in pts) * PX + 2 * MARGIN
    X = lambda x: MARGIN + x * PX          # noqa: E731
    Y = lambda y: H - MARGIN - y * PX      # noqa: E731  (plan +y is up, SVG +y is down)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" '
           f'viewBox="0 0 {W:.0f} {H:.0f}" font-family="Helvetica, Arial, sans-serif">',
           f'<rect width="{W:.0f}" height="{H:.0f}" fill="white"/>']
    for i, r in enumerate(plan["rooms"]):
        poly = " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in r["polygon"])
        out.append(f'<polygon points="{poly}" fill="{COLOURS[i % len(COLOURS)]}" stroke="#222" stroke-width="4"/>')
    for r in plan["rooms"]:
        for w in r["walls"]:
            (x0, y0), (x1, y1) = w["start"], w["end"]
            L = w["length"]
            if L["value"] < 0.3:
                continue
            mx, my = (X(x0) + X(x1)) / 2, (Y(y0) + Y(y1)) / 2
            vertical = abs(x1 - x0) < abs(y1 - y0)
            rot = f' transform="rotate(-90 {mx:.1f} {my:.1f})"' if vertical else ""
            colour = "#1a4d8f" if w["located_on_3d_points"] else "#b03a2e"
            half = (L["ci95"][1] - L["ci95"][0]) / 2
            out.append(f'<text x="{mx:.1f}" y="{my - 8:.1f}" font-size="12" fill="{colour}" '
                       f'text-anchor="middle"{rot}>{L["value"]:.2f} ±{half * 100:.0f}cm</text>')
    for o in plan["openings"]:
        cx, cy = o["center"]
        horizontal_wall = o["walls"] and _wall_is_horizontal(plan, o["walls"][0])
        half = o["width"]["value"] / 2
        (ax, ay), (bx, by) = ((cx - half, cy), (cx + half, cy)) if horizontal_wall else ((cx, cy - half), (cx, cy + half))
        colour = {"door": "#c0392b", "window": "#2e86c1", "passage": "#7d3c98"}[o["kind"]]
        out.append(f'<line x1="{X(ax):.1f}" y1="{Y(ay):.1f}" x2="{X(bx):.1f}" y2="{Y(by):.1f}" '
                   f'stroke="white" stroke-width="8"/>')
        out.append(f'<line x1="{X(ax):.1f}" y1="{Y(ay):.1f}" x2="{X(bx):.1f}" y2="{Y(by):.1f}" '
                   f'stroke="{colour}" stroke-width="3" stroke-dasharray="{"6,3" if o["kind"] == "window" else "none"}"/>')
        out.append(f'<text x="{X(cx):.1f}" y="{Y(cy) + 18:.1f}" font-size="11" fill="{colour}" '
                   f'text-anchor="middle">{escape(o["kind"])} {o["width"]["value"]:.2f}</text>')
    for r in plan["rooms"]:
        xs = [p[0] for p in r["polygon"]]
        ys = [p[1] for p in r["polygon"]]
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        a = r["floor_area"]
        h = r["ceiling_height"]
        out.append(f'<text x="{X(cx):.1f}" y="{Y(cy):.1f}" font-size="16" font-weight="bold" '
                   f'text-anchor="middle">{escape(r["name"])}</text>')
        out.append(f'<text x="{X(cx):.1f}" y="{Y(cy) + 18:.1f}" font-size="12" text-anchor="middle">'
                   f'{a["value"]:.2f} ± {1.96 * a["sigma"]:.2f} m²</text>')
        if h:
            out.append(f'<text x="{X(cx):.1f}" y="{Y(cy) + 34:.1f}" font-size="12" text-anchor="middle">'
                       f'ceiling {h["value"]:.3f} m</text>')
    out.append(f'<text x="{MARGIN}" y="30" font-size="14">Tier: {escape(plan["capture"]["tier"])} · '
               f'total {plan["property"]["floor_area"]["value"]:.2f} m² · '
               f'blue = located on 3D points, red = grid-only (wider interval) · ±values are 95% intervals</text>')
    out.append("</svg>")
    return "\n".join(out)


def _wall_is_horizontal(plan: dict, wall_id: str) -> bool:
    for r in plan["rooms"]:
        for w in r["walls"]:
            if w["id"] == wall_id:
                return abs(w["end"][0] - w["start"][0]) > abs(w["end"][1] - w["start"][1])
    return True