# Technical report — phone capture to dimensioned floor plan

*Abhigyan Gandhi · Cozmo AI take-home · Oct 2026. All numbers regenerate with
`python scripts/reproduce.py` (see README). Max 6 pages.*

## 1. Architecture: three front ends, one geometry back end

```
LiDAR  (Stray Scanner: ARKit poses + 256x192 depth) ──────────────┐
Video  keyframes ─ DINOv2 room-visit grouping ─ MapAnything/room ─┤──> depth + poses per frame
Photos one folder per room ─ MapAnything/room (EXIF focal) ───────┘          │
                                                                               ▼
 gravity-aligned world ─ floor/ceiling peaks ─ Manhattan yaw ─ drift correction (LiDAR)
 ─ 5 cm free-space map by ray casting ─ doorway cuts ─ room regions ─ rectilinear polygon
 ─ walls refined on raw 3D points ─ openings by ray hit/pass votes ─ per-room heights
 ─ stitch (shared frame for LiDAR; Manhattan layout snap for image tiers)
 ─ damage on wall planes ─ concealed-damage rules ─ scope ─ JSON + SVG, 95% CI on everything
```

The key design decision: **image-only tiers are converted into the same thing LiDAR
gives us** (metric depth + camera poses + intrinsics) by MapAnything (Meta, 2025,
Apache-2.0 weights), and wrapped in the LiDAR capture interface (`io/recon.py`). Every
tier then shares one back end, so improvements and bugs are shared too, and tier
differences are honest differences in the input, not in the code.

**Principles that survived contact with real data**
- *Height bands separate structure from furniture.* Walls are found in 1.1-2.1 m
  (above beds, tables, sofas); walls are *refined* just below the ceiling, where nothing
  but walls and door lintels exist. Indian homes have wardrobes and lofts to ~2.1 m,
  which broke the first version (section 7).
- *Rays, not points.* Free space and openings come from ray casting: a LiDAR ray that
  ends 15 cm beyond a wall plane passed through a hole; a wardrobe stops rays before the
  plane, so it cannot create a phantom opening; unobserved wall stays "unknown".
- *Measure on raw points, decide on grids.* Segmentation runs on a 5 cm grid; every
  reported length comes from the median of full-resolution 3D points on that surface.

## 2. Tiers and device matrix

| tier | input (protocol: docs/CAPTURE_PROTOCOL.md) | runs on | wall error on benchmark flat (mean abs) | honest accuracy claim |
|---|---|---|---|---|
| LiDAR | Stray Scanner recording, start/end at same corner, ceiling swept | iPhone 12 Pro or newer Pro/Pro Max (tested: iPhone 17 Pro; Cozmo sample) | 7.5 % (1-10 cm on correctly segmented walls, biased short ~4 cm) | ±8 cm per wall length (95 %) when the room is segmented correctly |
| video | one landscape walkthrough, 1x lens, 1080p+ | any iPhone 15+ / Android flagship (tested: iPhone 17 Pro, OnePlus 13) | 12.1-12.5 % | ±20 % per wall (95 %); room grouping can split/merge rooms |
| photo | 4-8 landscape stills per room, corner to corner | any phone with EXIF focal length (tested: iPhone 17 Pro, OnePlus 13) | 13.0 % (OnePlus), 13.4 % (iPhone) | ±20 % per wall (95 %), ±30 % without EXIF |

Intrinsics for image tiers: from EXIF 35 mm-equivalent focal (photo, `f_px = f35 · diag_px / 43.27`)
or container metadata (Android video writes `lens.focal_length`). Known intrinsics were the
single biggest accuracy lever: with model-estimated focal length, depth was 36 % short on the
Cozmo sample. Run times (RTX 4070 Laptop 8 GB): LiDAR 40-155 s, photo 40-70 s, video 2-4 min.

## 3. Drift handling

ARKit keeps gravity exact but drifts in heading. Since indoor walls are Manhattan, the wall
orientation seen in any 2 s window must equal the global one; the deviation *is* heading drift.
`geometry/drift.py`: (1) per-window Manhattan yaw, median-smoothed over 11 windows, anchored at
frame 0; every frame is rotated back and **positions are re-integrated** from corrected headings
(rotation-only scored 0.444 vs 0.471 with re-integration); (2) loop closure by ICP between the
first and last seconds (protocol: start and end at the same corner), accepted **only if two
search radii agree** — a floor-only view is degenerate for ICP and gave 3.5° vs 14.5° on the
sample, which is also why the protocol changed from "point at the floor" to "aim at a corner".
(3) A guard keeps the correction only if it measurably sharpens walls.

**Ablation** (`scripts/drift_ablation.py`; metric = share of wall points within 1 cm of their wall
plane, which needs no ground truth):

| capture | sharpness off → on | footprint off → on | heading drift found | kept by guard |
|---|---|---|---|---|
| Cozmo sample, multi-room (floor only) | 0.413 → **0.504** | 48.8 → 52.9 m² | 3.1° | yes |
| Cozmo sample, multi-room (with ceiling) | 0.401 → 0.413 | 48.4 → 46.6 m² | 3.2° | yes |
| benchmark flat, iPhone 17 Pro (tape 46.9 m²) | 0.339 → 0.319 | **37.2** → 35.6 m² | 13.3° (estimate) | **no** |

The last row is a guard success with ground truth behind it: on the furnished benchmark flat the
per-window yaw estimate was dominated by non-Manhattan clutter (13° of apparent drift is far more
than ARKit produces in 2 minutes), the "correction" blurred walls *and* moved the footprint
further from the tape, and the guard refused it. Loop closure was skipped on all three
captures (ICP radii disagreed), including the benchmark flat, which did start and end at a
corner; we did not have time to diagnose why, so loop closure is unproven on real data. Overlays:
`benchmark/ablation/drift_ablation_*.png`.

## 4. Error budget (LiDAR wall length, one wall)

| source | size | evidence |
|---|---|---|
| plane fit noise (median of 10³-10⁴ pts) | < 1 mm | MAD/√n |
| LiDAR range bias | ~1 cm | Apple spec; floor/ceiling peaks are 1-2 cm thick |
| heading drift over a room | 0.5-2 cm | ablation above |
| surface definition (tape at 1 m vs plane fit; skirting, plaster bulge) | 2-4 cm | systematic −4.4 cm mean on correctly segmented walls |
| tape ground truth | ~0.5 cm | two readings per wall |
| **observed RMS on correctly segmented walls** | **5.6 cm** (8 of 12 matched walls; range −9.9 to +0.5 cm) | benchmark |
| segmentation failure (furniture to 2.1 m, merged rooms) | 0.3-1.1 m | bedroom1, living (section 7) |

Image tiers: metric scale of the depth network dominates (~10 % per room, measured as the RMS
of per-room photo-tier errors), everything else is second order.

## 5. Calibration analysis

Every measurement carries σ and a 95 % interval; we checked coverage against tape.

| capture | walls inside reported 95 % CI | note |
|---|---|---|
| OnePlus photo | **12/16** | scale σ = 10 % calibrated here |
| iPhone photo | 12/16 | see the stability note below |
| LiDAR iPhone | 8/16 | all misses are segmentation failures; correct rooms are covered |
| OnePlus / iPhone video | 6/16, 2/16 | intervals inherited from photo tier, too narrow when visits are split |

Two calibration changes were made *because of* the benchmark and are disclosed: (a) LiDAR
per-wall systematic σ raised from 0.5 cm to 3 cm (the first version claimed ±1.4 cm and was
off by 5-13 cm, which is exactly "confident garbage"); (b) photo scale σ set to 10 %. What the
intervals do **not** cover is structural failure (wrong room, merged rooms). Those are reported
as separate counts (rooms matched, warnings in `quality`) rather than hidden in wide intervals.

**Run-to-run stability (disclosed).** Re-running every capture on the final, GPS-stripped data
reproduced all numbers exactly except the iPhone photo tier, whose HEIC files had been re-encoded
by the stripping step (imperceptible pixel changes): walls within ±8 % went 7/16 → 11/16,
footprint −32 % → −23 %. The photo tier is therefore sensitive to tiny input perturbations at the
level of ~±4 walls out of 16; the reported number is the post-strip one because that is what
`reproduce.py` regenerates from the shipped data. LiDAR and video were bit-stable.

**Ground-truth correction (disclosed).** The living-room ceiling was first taped at 2.50 m.
LiDAR (2.685 m) and the photo tier (2.704 m) independently disagreed by ~19 cm, so it was
re-measured: 2.63 / 2.61 m. Only this one value changed; the original is in git history.

## 6. The fix loop (full declaration: docs/FIX_LOOP.md)

*Worst gate:* video tier stitch / wall lengths: **0 of 4 rooms, footprint −95.5 %**.
*Root cause:* one reconstruction across a whole multi-room walk is not consistent (wall
sharpness 0.26 vs 0.4-0.5 for LiDAR, 16° heading drift, camera height wandering 0.66 m, while the
same model on the same rooms from per-room photos recovers all four rooms — the control).
*Fix:* split the walk into room visits (DINOv2 embeddings, agglomerative clustering with a
time-adjacency constraint, merge visits that look alike), reconstruct per room, stitch.
*Predicted:* footprint within ±15 %, mean wall error ~12 %, ≥3/4 rooms, ±3 % gate still failing.
*Result:* **footprint −8.0 %, mean wall error 12.1 %, 2/4 rooms, gate 0/16** — correct root cause,
meaningful movement, room prediction wrong (blank walls look alike across rooms) and the gate
short because image-only metric scale (~10 %) is untouched; the next fix is a metric anchor
(ARCore/ARKit poses or a known-size reference). Before = git tag `fixloop-before`.

## 7. Known failure modes (and what covers them)

| condition | effect | mitigation / status |
|---|---|---|
| wardrobes and lofts up to 2.1 m | wardrobe face taken as a wall (bedroom1: −1.03 m) | (a) walls refined just below the ceiling (bedroom2 −5..−13 → −1..−10 cm); (b) a wall that does not reach the ceiling while the room's ceiling continues past it is pushed to the visible ceiling-reaching wall ≤ 0.6 m behind (bedroom2 −16.7 → −1.5 cm on one axis); bedroom1's loft runs to the ceiling, so it is correctly *not* moved: **open**. Evidence for the next fix: the ceiling continues 0.98 m past that wall in the flat scan, matching the 1.03 m deficit |
| bed covering the floor | bed top (0.6 m) taken as the room's floor → bedroom1 ceiling 2.05 m | room floor searched within ±10 cm of the flat-wide floor; ceilings ≥ 2.2 m preferred: bedroom1 −62.2 → −0.7 cm, ceilings within 1.5 cm 1/3 → 2/3, repeat spread 0.4 cm |
| mirrors | LiDAR rays reflect: phantom opening behind the mirror | openings report `seen_from_both_sides`; a mirror is never seen from the other side |
| glass (windows, glass doors) | rays pass or return noise | windows detected as pass-through holes; window widths unreliable (0/≈10 within 2 cm) |
| wet-look / glossy floors | specular LiDAR dropouts | confidence-2 depth only; floor found as a histogram peak, robust to holes |
| low light | blur in video, ARKit tracking loss | sharpest-frame keyframing; protocol: all lights on |
| false ceilings | no single ceiling height | all levels reported (`ceiling_levels`) with a warning |
| ceiling never filmed | no height; photo/video walls fell back to free-space outlines (−15-25 %) | warning; wall-top reference height (fix loop) |
| floor barely seen (bed covers it) | floor detected on the ceiling | floor must lie below the cameras (fixed) |
| narrow corridors in photos | hall length unseen (2.55 vs 5.65 m) | protocol: photograph each end of a corridor; **open** |
| blank walls | damage false positives, video room confusion | texture gate + CLIP negatives (posters, curtains, doors) |
| openings at cm accuracy | vote edges biased ~10 cm narrow (frame, open leaf, grazing rays) | LiDAR edges snapped to jamb planes: doors −10.7/−7.8/−13.7 → +3.3/−3.8/−6.8 cm (mean 10.7 → 4.6 cm); still 0/3 within 2 cm, gate **not met**; jamb snapping made image-only doors worse (depth too smooth at edges), so it is LiDAR-only; windows (grilles, curtains) mostly missed |

## 7b. Day-2 improvements (each diagnosed on the benchmark, each a commit)

| change | why (evidence) | effect (iPhone LiDAR, tape) |
|---|---|---|
| door edges snapped to jamb planes | all 3 doors 8-14 cm narrow: vote edges sit inside the frame | mean door error 10.7 → 4.6 cm |
| room floor near flat-wide floor; ceiling ≥ 2.2 m | bedroom1 "ceiling" 2.05 m was really ceiling minus bed top | ceilings 1/3 → 2/3 within 1.5 cm; repeat spread 0.4 cm (gate met) |
| wardrobe-front walls pushed to ceiling-reaching wall (guarded) | wardrobe fronts stop at 2.1 m; the ceiling continues past them | mean wall error 8.2 → 7.5 %; walls in CI 6 → 8/16; Polycam 4 → 5/10 |

An unguarded version of the last change moved walls by up to 1.5 m on the Cozmo sample scans,
where nothing can be verified; it was capped at 0.6 m (wardrobe depth) and restricted to
visible walls. One reverted change: jamb snapping on the photo tier made doors worse.

## 8. Damage

Damage is searched only on wall pixels (3D point within 3 cm of a measured wall plane), as dark
soft blobs (stains) and thin dark ridges (cracks), gated against busy texture (curtains hang
within 3 cm of the window wall), classified zero-shot by CLIP against damage and non-damage
prompts, then measured in metres on that surface and merged across frames.

| capture | staged crack (1.1 m, bedroom1) | staged stain (10 cm, bedroom1) | detections elsewhere (false positives) |
|---|---|---|---|
| LiDAR bedroom1 scan a / b | found: 0.12 m / 0.61 m of extent (1.85-2.50 m high) | missed | 0 |
| LiDAR whole flat | not found | missed | 2 (bedroom2) |
| photo iPhone / OnePlus | not found | missed | 1 / 1 |
| video iPhone / OnePlus | not found | missed | 1 (a "mould" that also fires rule R3) / 0 |

Damage is the least mature part: the staged crack is found only in close LiDAR room scans, the
small stain never, and roughly one false positive per capture remains (one of which triggers a
concealed-damage flag, so flags inherit detector errors). Next step: a small segmenter trained
on public crack/stain data, evaluated on these staged regions. Concealed-damage
rules R1-R5 (stain near ceiling → leak above; near floor → rising damp/pipe; mould → hidden
growth; crack > 1 m → structural; stain > 0.25 m² → saturated substrate) fire with the rule
name in the JSON; scope items are keyed to surface IDs (`R1-W2`).

## 9. Head-to-head vs a consumer app (benchmark/HEAD_TO_HEAD.md)

Polycam for iOS 7.0.3 (free tier) on the same iPhone 17 Pro, living and bedroom1. The free
tier exports a mesh but not its plan numbers, so Polycam's dimensions are read off its own
mesh by a simple neutral procedure (outermost wall planes, floor/ceiling peaks; no tuning).
**Result: beat or tie on 5/10 shared dimensions (50 %), gate ≥ 70 % not met.** Where our rooms
are segmented correctly we win (living long walls −0.8/−2.8 cm vs Polycam +4.0/+2.0 cm); we lose
on segmentation (living merged with the passage, bedroom1 cut at the wardrobe) and on the living
ceiling (+4.4 vs −1.0 cm); we now win bedroom1's ceiling (−0.7 vs −3.0 cm). Polycam's mesh is also cut by bedroom1's wardrobes
(3.67 × 3.03 m vs 4.14 × 3.70 m tape), so furnished rooms are hard for both; our measurement
step is competitive, our segmentation is the gap. Caveat: Polycam's own app may report
different numbers than our reading of its mesh.
