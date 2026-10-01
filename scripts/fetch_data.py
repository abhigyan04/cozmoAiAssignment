"""Download the benchmark raw data (location metadata already stripped) into data/raw/.

    python scripts/fetch_data.py

Contents (2.4 GB zip, extracted to data/raw/): iPhone 17 Pro (Stray Scanner LiDAR x3, video, photos, Polycam
glTF + video exports) and OnePlus 13 (videos, photos, repeat photo set). Cozmo's sample
LiDAR scans are not redistributed; place them next to the repo as ../single_room,
../single_scan_floor_only, ../single_scan_with_ceiling (see README).
"""
import sys
import zipfile
from pathlib import Path

DRIVE_FILE_ID = "1S1M1B_mQx73fF7FrRO4jQyMNStXVzag4"
ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data"          # the zip's top level is data/raw/...


def main() -> None:
    if DRIVE_FILE_ID.startswith("REPLACE"):
        sys.exit("Data link not set yet; see README.")
    import gdown   # handles Google Drive's large-file confirmation page

    DEST.mkdir(exist_ok=True)
    zip_path = DEST / "raw.zip"
    gdown.download(id=DRIVE_FILE_ID, output=str(zip_path), quiet=False)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(ROOT)
    zip_path.unlink()
    print("done:", DEST / "raw")


if __name__ == "__main__":
    main()
