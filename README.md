# floorplan — phone capture to a dimensioned, stitched floor plan with damage

One command turns a phone capture of a property into `plan.json` (rooms, walls, openings,
ceiling heights, damage, concealed-damage flags, scope items, a 95% interval on every
measurement) and `plan.svg` (the rendered whole-property plan).

Three input tiers, one geometry back end:

| tier | input | how depth + poses are obtained |
|---|---|---|
| LiDAR | Stray Scanner folder (iPhone Pro) | ARKit poses + LiDAR depth, drift-corrected |
| video | one walkthrough clip | MapAnything (metric, feed-forward) per room visit |
| photo | one folder of 2-8 stills per room | MapAnything per room, EXIF focal length |

Capture instructions for non-engineers: [docs/CAPTURE_PROTOCOL.md](docs/CAPTURE_PROTOCOL.md).

## Setup on a clean machine (~10 min + downloads)

Requirements: Windows or Linux, NVIDIA GPU with >= 8 GB (tested: RTX 4070 Laptop 8 GB),
Python 3.11, [uv](https://docs.astral.sh/uv/) (or pip), git.

```bash
git clone <this repo> && cd cozmoAiAssignment
uv venv --python 3.11 .venv
# PyTorch with CUDA (pick the index matching your driver; cu128 tested)
uv pip install --python .venv/Scripts/python.exe torch torchvision --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv/Scripts/python.exe -e .
```
(Linux: use `.venv/bin/python`.)

Model weights are fetched automatically on first use and cached (no manual step):
MapAnything Apache-2.0 (`facebook/map-anything-apache`, Hugging Face, ~5 GB incl. DINOv2-g),
DINOv2-S (torch hub, 84 MB), CLIP ViT-B/32 (`openai/clip-vit-base-patch32`, ~600 MB).
The LiDAR tier needs no network and no model.

## One command per capture

```bash
python -m floorplan run <capture> [--tier auto|lidar|video|photo] [--out DIR] [--drift auto|on|off] [--no-damage]
```

* `<capture>` = a Stray Scanner folder, a video file, or a folder containing one subfolder per room.
  The tier is auto-detected.
* Output: `DIR/plan.json` (schema: [docs/plan.schema.md](docs/plan.schema.md)) and `DIR/plan.svg`.

Typical run times on an RTX 4070 Laptop: LiDAR 40-90 s, photo (4 rooms) ~1-2 min, video (2.5 min clip) ~2-4 min.

## Reproducing every reported number

```bash
python scripts/fetch_data.py                 # benchmark raw data (location metadata stripped)
python scripts/reproduce.py                  # runs every capture + scores against tape -> benchmark/results/
```
Ground truth (tape): [benchmark/ground_truth.csv](benchmark/ground_truth.csv), sketch [benchmark/flat_sketch.jpg](benchmark/flat_sketch.jpg).
Fix loop before/after: [docs/FIX_LOOP.md](docs/FIX_LOOP.md) (before = git tag `fixloop-before`).

## Repository map

| path | what |
|---|---|
| `src/floorplan/io/` | capture loaders: Stray Scanner, video keyframes, MapAnything wrapper |
| `src/floorplan/geometry/` | floor/ceiling, Manhattan frame, free-space map, rooms, walls, openings, drift, stitching |
| `src/floorplan/lidar.py`, `photo.py`, `video.py` | the three tiers |
| `src/floorplan/damage.py` | damage regions, concealed-damage rules, scope items |
| `src/floorplan/output/` | JSON + SVG |
| `scripts/` | benchmark scorer, drift ablation, privacy stripping, inspection tools |
| `docs/` | capture protocol, technical report, compliance matrix, fix loop |

## Third-party models and data (disclosure)
MapAnything (Meta, Apache-2.0 weights), DINOv2 (Meta, Apache-2.0), CLIP (OpenAI, MIT),
Stray Scanner sample captures (provided by Cozmo). No external API is called at run time.
