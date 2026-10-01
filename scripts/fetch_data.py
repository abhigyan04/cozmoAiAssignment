"""Download the benchmark raw data (location metadata already stripped) into data/raw/.

    python scripts/fetch_data.py

Contents: iPhone 17 Pro (Stray Scanner LiDAR x3, video, photos, Polycam export) and
OnePlus 13 (video, photos, repeat photo set). Cozmo's sample LiDAR scans are not
redistributed; place them next to the repo as ../single_room etc. (see README).
"""
import sys
import urllib.request
import zipfile
from pathlib import Path

URL = "REPLACE_WITH_GOOGLE_DRIVE_DIRECT_DOWNLOAD_LINK"
DEST = Path(__file__).resolve().parents[1] / "data"


def main() -> None:
    if URL.startswith("REPLACE"):
        sys.exit("Data URL not set yet; see README.")
    DEST.mkdir(exist_ok=True)
    zip_path = DEST / "raw.zip"
    print(f"downloading {URL} -> {zip_path}")
    urllib.request.urlretrieve(URL, zip_path)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(DEST)
    zip_path.unlink()
    print("done:", DEST / "raw")


if __name__ == "__main__":
    main()
