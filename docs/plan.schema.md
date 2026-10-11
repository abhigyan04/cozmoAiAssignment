# plan.json schema (v1.0)

Units: metres, m², degrees. Every measured quantity is a **measurement** object:
`{"value": float, "sigma": float (1σ), "ci95": [lo, hi]}`.
Coordinates: plan frame, walls axis-aligned, origin at the lower-left of the whole property, +x right, +y up.

```jsonc
{
  "schema_version": "1.0",
  "capture": { "tier": "lidar|video|photo", "source": "<path>", "processing_seconds": float },
  "property": {
    "floor_area": measurement,               // sum of rooms
    "room_count": int,
    "adjacency": [ { "rooms": ["R1", "R3"], "via": "O4" | null } ]   // null: connected, opening not measured
  },
  "rooms": [ {
    "id": "R1", "name": "living | R1",       // photo tier: folder name
    "polygon": [[x, y], ...],                 // corners, counter-clockwise
    "floor_area": measurement, "perimeter": measurement,
    "ceiling_height": measurement | null,     // null = ceiling not observed (see quality.warnings)
    "ceiling_levels": [ { "height": float, "share": float } ],   // false ceilings: every level >= 15 %
    "walls": [ { "id": "R1-W1", "start": [x, y], "end": [x, y], "length": measurement,
                 "located_on_3d_points": bool } ],              // false = grid-only, wider interval
    "surfaces": ["R1-FLOOR", "R1-CEILING", "R1-W1", ...]
  } ],
  "openings": [ {
    "id": "O1", "kind": "door|window|passage", "rooms": ["R1"] | ["R1", "R2"],
    "walls": ["R1-W2", "R2-W4"], "center": [x, y], "width": measurement,
    "sill_height": float, "head_height": float,
    "seen_from_both_sides": bool              // false for exterior openings, and for mirrors (phantoms)
  } ],
  "damage_summary": {                         // property-level triage score
    "score": 0-100, "severity": "none|low|moderate|high",
    "basis": [ { "damage": "D1", "contribution": float } | { "flag": "R1 ..." } ],
    "note": str                               // what was observed; unobserved surfaces are not scored
  },
  "damage": [ {
    "id": "D1", "surface": "R1-W2", "class": "crack|water_stain|mould|peeling_paint",
    "width": measurement, "height": measurement, "area_m2": float,
    "height_from_floor": [lo, hi], "confidence": float, "seen_in_frames": int
  } ],
  "concealed_damage_flags": [ { "damage": "D1", "rule": "R1 ...", "flag": "<what may be hidden and where to look>" } ],
  "scope_items": [ { "surface": "R1-W2", "damage": "D1", "description": str, "quantity": float, "unit": "m|m2" } ],
  "quality": {
    "wall_sharpness": float | null,           // LiDAR/video pose consistency (share of wall points within 1 cm)
    "drift_correction_applied": bool, "max_heading_drift_deg": float | null,
    "loop_closure_applied": bool,
    "warnings": [str]
  }
}
```

Damage score: each region contributes severity(class) × confidence × size factor
(mould 1.0, water stain 0.8, crack 0.6, peeling paint 0.4; size saturates at 0.5 m² or 1 m crack length,
floor 0.2); combined as 100 × (1 − Π(1 − cᵢ)); +10 per concealed-damage flag; capped at 100.
Severity: 0 none, < 25 low, < 60 moderate, else high. A triage number, not a payout figure.

Concealed-damage rules: R1 stain/mould within 30 cm of ceiling · R2 within 30 cm of floor ·
R3 visible mould · R4 crack longer than 1 m · R5 water stain larger than 0.25 m².
