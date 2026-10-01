"""Build the output JSON (schema: docs/plan.schema.json) from a pipeline result.

Every measurement is {"value", "sigma", "ci95": [lo, hi]} in metres (or m2).
Coordinates are in the plan frame: walls axis-aligned, origin at the
lower-left corner of the whole property, +x right, +y up on the page.
"""
import numpy as np

SCHEMA_VERSION = "1.0"
Z95 = 1.96


def measure(value, sigma, digits: int = 3):
    if value is None:
        return None
    s = float(sigma)
    return {"value": round(float(value), digits), "sigma": round(s, digits + 1),
            "ci95": [round(float(value) - Z95 * s, digits), round(float(value) + Z95 * s, digits)]}


def build_plan(res, tier: str, source: str, timing_s: float, warnings: list[str] | None = None) -> dict:
    warnings = list(warnings or [])
    if not res.polys:
        warnings.append("no room could be segmented from this capture")
    origin = np.vstack([rp.vertices for rp in res.polys]).min(0) if res.polys else np.zeros(2)
    to_plan = lambda v: [round(float(v[0] - origin[0]), 3), round(float(v[1] - origin[1]), 3)]  # noqa: E731

    rooms = []
    for ri, rp in enumerate(res.polys):
        rid = f"R{ri + 1}"
        walls = []
        K = len(rp.walls)
        for k, w in enumerate(rp.walls):
            walls.append({
                "id": f"{rid}-W{k + 1}",
                "start": to_plan(rp.vertices[k]),
                "end": to_plan(rp.vertices[(k + 1) % K]),
                "length": measure(rp.lengths[k], rp.length_sigmas[k]),
                "located_on_3d_points": w.refined,
            })
        h = res.heights[ri]
        if h.height is None:
            warnings.append(f"{rid}: ceiling not observed, height not reported")
        elif len(h.levels) > 1:
            warnings.append(f"{rid}: {len(h.levels)} ceiling levels (false ceiling?); "
                            f"ceiling_height is the dominant one")
        perim = float(sum(rp.lengths))
        perim_sigma = float(np.sqrt(sum(s**2 for s in rp.length_sigmas)))
        rooms.append({
            "id": rid,
            "name": res.names[ri] if getattr(res, "names", None) else rid,
            "polygon": [to_plan(v) for v in rp.vertices],
            "floor_area": measure(rp.area, rp.area_sigma),
            "perimeter": measure(perim, perim_sigma),
            "ceiling_height": measure(h.height, h.sigma) if h.height is not None else None,
            "ceiling_levels": [{"height": lv, "share": sh} for lv, sh in h.levels],
            "walls": walls,
            "surfaces": [f"{rid}-FLOOR", f"{rid}-CEILING"] + [w["id"] for w in walls],
        })

    openings = []
    for oi, s in enumerate(res.shared):
        d = s.detections[0]
        openings.append({
            "id": f"O{oi + 1}",
            "kind": s.kind,
            "rooms": [f"R{r + 1}" for r in s.rooms],
            "walls": [f"R{x.room + 1}-W{x.wall + 1}" for x in s.detections],
            "center": to_plan(s.center),
            "width": measure(s.width, s.width_sigma),
            "sill_height": round(d.bottom, 2),
            "head_height": round(d.top, 2),
            "seen_from_both_sides": len(s.detections) == 2,
        })

    adjacency = [{"rooms": [f"R{a + 1}" for a in e["rooms"]],
                  "via": None if e["opening"] is None else f"O{e['opening'] + 1}"} for e in res.edges]

    total = sum(r["floor_area"]["value"] for r in rooms) if rooms else 0.0
    total_sigma = float(np.sqrt(sum(r["floor_area"]["sigma"] ** 2 for r in rooms)))
    return {
        "schema_version": SCHEMA_VERSION,
        "capture": {"tier": tier, "source": source, "processing_seconds": round(timing_s, 1)},
        "property": {
            "floor_area": measure(total, total_sigma),
            "room_count": len(rooms),
            "adjacency": adjacency,
        },
        "rooms": rooms,
        "openings": openings,
        "damage": [],
        "concealed_damage_flags": [],
        "scope_items": [],
        "quality": {
            "wall_sharpness": round(res.sharpness, 3) if np.isfinite(res.sharpness) else None,
            "drift_correction_applied": res.drift_applied,
            "max_heading_drift_deg": round(res.drift.max_abs_drift_deg, 2) if res.drift else None,
            "loop_closure_applied": bool(res.drift and res.drift.loop_closed),
            "warnings": warnings,
        },
    }
