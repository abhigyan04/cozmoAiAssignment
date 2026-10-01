# Compliance matrix

Status: ✅ met · ⚠️ partially met / met with stated deviation · ❌ not met (reason given)

## Part 1 — capture

| requirement | file | artifact | status |
|---|---|---|---|
| Capture route (Route 2: stock-app protocol a non-engineer follows) | docs/CAPTURE_PROTOCOL.md | one-page protocol: install, walk, duration, avoid, hand-off | ✅ |
| Photo tier, 2-8 stills per room, no depth/poses, folder per room | src/floorplan/photo.py | `python -m floorplan run <photos dir>` | ✅ |
| Video tier, handheld walkthrough | src/floorplan/video.py | `python -m floorplan run <clip>` | ✅ |
| LiDAR tier, depth + poses + intrinsics | src/floorplan/lidar.py, io/stray.py | `python -m floorplan run <stray folder>` | ✅ |
| Same output contract from all tiers, intervals widen with thinner input | output/plan.py, uncertainty.py | identical JSON schema; scale σ 0 / 10 % / 10 % (+5 % without focal) | ✅ |
| Device matrix: tier × hardware × honest accuracy | docs/TECHNICAL_REPORT.md §2 | table | ✅ |

## Part 2 — output contract and gates

| requirement | file | artifact | status |
|---|---|---|---|
| Per-room plan: walls, ceiling height, floor area, openings | output/plan.py | `rooms[].walls`, `ceiling_height`, `floor_area`, `openings[]` | ✅ |
| Stitched multi-room plan, correct adjacency | geometry/stitch.py, photo.stitch | `property.adjacency`, `plan.svg` | ⚠️ LiDAR shared frame; image tiers layout-snapped, adjacency partly wrong |
| Per-surface damage regions with class and metric extent | damage.py | `damage[]` (surface, class, width/height with CI, area) | ⚠️ crack found (partial extent), small stain missed |
| Concealed-damage flags with the rule that fired | damage.concealed_flags | `concealed_damage_flags[].rule` | ✅ |
| Scope line items keyed to surfaces | damage.scope_items | `scope_items[].surface` | ✅ |
| Confidence interval on every measurement | output/plan.py `measure()` | `{value, sigma, ci95}` | ✅ |
| One command per capture, JSON to published schema, rendered plan | __main__.py, docs/plan.schema.md | `plan.json`, `plan.svg` | ✅ |
| Benchmark: multi-room capture, 3+ rooms + connector | data/raw/*, benchmark/ground_truth.csv | living, bedroom1, bedroom2, hall | ✅ |
| Benchmark: furnished room with staged damage, two classes | bedroom1 (crack 1.1 m, water stain 10 cm) | closeups + all tiers | ✅ |
| Same rooms at all three tiers incl. multi-room, photo as per-room folders | data/raw/iphone/{lidar,video,photos} | iPhone 17 Pro, all three tiers | ✅ |
| One room captured twice at the same tier | bedroom1: LiDAR a/b, OnePlus photos ×2 | benchmark/REPORT.md repeatability | ✅ |
| Tape ground truth on everything, raw data submitted | benchmark/ground_truth.csv, scripts/fetch_data.py | tape (laser not available) | ⚠️ tape, not laser |
| Gate: openings ≤ 2 cm on ≥ 85 % | benchmark/REPORT.md | 0-1 of 5-13 | ❌ weakest result (report §7) |
| Gate: ceiling ≤ 1.5 cm per room, repeat spread ≤ 1 cm | benchmark/REPORT.md | LiDAR bedroom2 +0.5 cm; others fail | ❌ partially (1/3 rooms) |
| Gate: repeatability ≤ 1 cm or 0.5 % per wall | benchmark/REPORT.md | photo 0.9 / 6.7 cm; LiDAR 2.9 / 1.9 cm | ❌ (repeatable-but-biased on LiDAR, stated) |
| Gate: drift accountability + ablation on/off | geometry/drift.py, scripts/drift_ablation.py, benchmark/ablation/ | sharpness + footprint on/off, guard | ✅ |
| Gate: photo-tier whole-property stitch, no overlaps, footprint ±8 % | photo.stitch | no overlaps; footprint −13.8 % (OnePlus), −22.7 % (iPhone) | ❌ footprint outside ±8 % |
| Gate: photo walls ±8 % with calibrated intervals | benchmark/REPORT.md | 8/16 (OnePlus), 11/16 (iPhone) | ❌ partially; intervals cover 12/16 on both |
| Gate: video walls ±3 % | benchmark/REPORT.md | 0/16 (OnePlus), 2/16 (iPhone) | ❌ (fix loop §6) |
| Calibration scored at every tier | docs/TECHNICAL_REPORT.md §5 | CI coverage table | ✅ |

## Part 3 — head-to-head

| requirement | file | artifact | status |
|---|---|---|---|
| LiDAR output vs one consumer app on 2 rooms, app + version named, export submitted | benchmark/HEAD_TO_HEAD.md, scripts/head_to_head.py, data/raw/iphone/polycam | Polycam iOS 7.0.3, glTF export, 10 dimensions | ❌ 4/10 beat-or-tie (gate 70 %); free tier gives mesh only, read by neutral procedure |

## Part 4 — fix loop

| requirement | file | artifact | status |
|---|---|---|---|
| Worst gate with failing number, root cause + evidence, fix + predicted number | docs/FIX_LOOP.md §1-3 | declaration committed before the fix (tag `fixloop-before`) | ✅ |
| Fix shipped, before and after regenerable, readable diff | docs/FIX_LOOP.md §4-5 | `git diff fixloop-before -- src/floorplan/video.py src/floorplan/photo.py` | ✅ (movement short of gate, explained) |

## Part 5 — process evidence

| requirement | file | artifact | status |
|---|---|---|---|
| Commit as you work | git history | ~25 incremental commits over 2 days | ✅ |

## Deliverables

| # | deliverable | location | status |
|---|---|---|---|
| 1 | Compliance matrix | docs/COMPLIANCE_MATRIX.md | ✅ |
| 2 | Capture route + device matrix | docs/CAPTURE_PROTOCOL.md, TECHNICAL_REPORT.md §2 | ✅ |
| 3 | Repo, README, one command per capture | README.md | ✅ |
| 4 | Reproduction bundle | scripts/reproduce.py, benchmark/plans (cached), scripts/fetch_data.py | ✅ |
| 5 | Benchmark report (gates all tiers, repeatability, head-to-head, timing) | benchmark/REPORT.md, benchmark/HEAD_TO_HEAD.md | ✅ |
| 6 | Fix loop bundle | docs/FIX_LOOP.md, benchmark/results/fixloop_* | ✅ |
| 7 | Technical report ≤ 6 pages | docs/TECHNICAL_REPORT.md | ✅ |
| 8 | Raw benchmark data (sensor logs, ground truth, app exports), location stripped | scripts/fetch_data.py → Google Drive | ⏳ upload pending |
| — | Mirrors, glass, wet-look, low light covered | TECHNICAL_REPORT.md §7 | ⚠️ documented; glass/mirror only partly handled |
