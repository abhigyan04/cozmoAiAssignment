# Fix loop declaration

*Written before the fix was implemented (see commit history: this file lands in the
same commit as the "before" run, ahead of any fix code).*

## 1. Worst gate, with the failing number

**Video tier, whole-property stitch / wall lengths** on the benchmark flat
(OnePlus 13, `flat_tour_new.mp4`, 147 s, protocol-compliant re-shoot).

| metric (gate: walls within ±3%) | before |
|---|---|
| rooms recovered | **0 of 4** matched (1 room, 2.09 m²) |
| footprint | **2.09 m² vs 46.86 m² tape (−95.5%)** |
| walls within ±3% | **0 / 16** |
| walls inside reported 95% CI | 0 / 16 |

Regenerate: `python -m floorplan run data/raw/oneplus/video/flat_tour_new.mp4 --out out/fixloop_before_video`
then `python scripts/benchmark.py out/fixloop_before_video/plan.json`.

## 2. Root-cause hypothesis and evidence

**Hypothesis:** one reconstruction spanning the whole multi-room walk is not
geometrically consistent, so the shared LiDAR back end (which assumes one
consistent point cloud) sees smeared walls and segments almost nothing.
The per-frame depth is fine; the *relative poses across rooms* are not.

Evidence:
- **Wall sharpness** (share of wall points within 1 cm of their wall plane):
  0.26 for video vs 0.40-0.50 for LiDAR captures. Walls are smeared, not missing.
- **Heading drift** measured by the plane-anchored estimator: up to **16°**
  across the walk (LiDAR captures: ~3°).
- **Camera height** above the fitted floor varies by 0.66 m (p5-p95) for a person
  walking with a phone at chest height (expected < ~0.2 m). The floor itself is
  level (1.4° tilt), so this is pose error, not a levelling bug.
- Chunked inference made it worse: camera path 100-121 m for a ~35 m walk.
- **Control:** the *same model* on the *same rooms* given per-room photo sets
  (photo tier) recovers all 4 rooms, footprint −13.8%, 8/16 walls within ±8%.
  Same depth network, same intrinsics source, so the difference is the
  cross-room consistency, which is the hypothesis.

## 3. The fix and the predicted number

**Fix:** reconstruct the video *per room*, not as one piece.
1. Segment the walk into room visits: consecutive keyframes are grouped by
   visual similarity with a temporal-contiguity constraint; visits that look
   alike (same room re-entered) are merged.
2. Each room's keyframes go through the photo tier's per-room pipeline
   (MapAnything with known intrinsics, near-ceiling wall planes).
3. Rooms are placed with the photo tier's layout stitch.

**Prediction:** rooms recovered 4/4 (at least 3/4); footprint within ±15%;
mean absolute wall error ~12% (photo-tier level). **The ±3% video gate will
still fail** (predicted ~3/16 walls within ±3%): the remaining error is
per-room metric scale (~10%), which this fix does not address. Expected
outcome: meaningful movement short of the gate.
