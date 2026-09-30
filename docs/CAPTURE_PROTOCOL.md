# Capture Protocol (one page)

Follow this literally. Any iPhone 15 or newer works for **Photos** and **Video**.
**LiDAR** needs an iPhone Pro / Pro Max (12 Pro or newer).

## 0. Before you start (2 min)
- Turn on **every light**. Open curtains. Open **all interior doors fully**.
- Camera: use the **1x** lens (not 0.5x, not 2x). No Portrait, Cinematic or Action mode.
- Stand back, don't film a wall from closer than ~0.5 m.
- Mirrors and glass: capture them like any wall; do not film your reflection up close.

## 1. Photos tier (native Camera app, ~1 min per room)
For **each room**, take **4 to 8** photos, **landscape**, 1x lens:
1. Stand in each corner and aim at the **opposite corner** (4 photos). Every photo must show
   the line where wall meets **floor** and where wall meets **ceiling**.
2. From **each doorway** of this room, take 1 photo looking **into this room**.
3. Hallway / connector counts as a room.

Hand-off: one folder per room, named by the room: `photos/living/`, `photos/bedroom1/`, `photos/hall/` …
JPEG or HEIC both fine.

## 2. Video tier (native Camera app, ~30 s per room)
One **continuous** clip through the whole property, **landscape**, 1080p or 4K, 30 fps.
1. Start in the entrance, aimed at a **room corner** (two walls + floor in view), hold **2 s**.
2. Walk **slowly** (half normal speed). In each room, turn a full circle at **chest height**,
   then sweep once **up to the ceiling line** and once **down to the floor line**.
3. Pass through doorways **slowly, filming the door frame**.
4. **End where you started**, aimed at the **same corner** for 2 s.

Hand-off: the single `.MOV` file.

## 3. LiDAR tier (Stray Scanner, free on the App Store, ~30–40 s per room)
1. Install **Stray Scanner**. Open it, press record.
2. Same walk as the video (section 2), including **start and end at the same spot**.
   Hold the phone at **chest height**, screen facing you, and **tilt up to see the ceiling in
   every room**. Ceiling height is not measured if the ceiling is not seen.
3. Keep going: no pausing the app, no putting the phone in a pocket.
4. Stop recording. In Stray Scanner, tap the recording → **Share → Save to Files / AirDrop**.

Hand-off: the recording folder (contains `rgb.mp4`, `depth/`, `odometry.csv`, …), zipped is fine.

## 4. Avoid
- Fast turns (> ¼ turn per second), running, covering the camera with fingers.
- Starting the recording inside a closet or facing a blank wall.
- People walking through the shot; pets.
- Closing doors behind you during the walk.

## 5. Running the pipeline
```
python -m floorplan run <capture path> --tier {photo|video|lidar} --out out/<name>
```
Output: `plan.json` (published schema) and `plan.svg` (rendered plan).
