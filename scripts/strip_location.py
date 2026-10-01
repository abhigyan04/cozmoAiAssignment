"""Remove GPS/location metadata from captures before they are shared.

Phones embed the home's coordinates in photo EXIF and video containers. The
benchmark raw data is a deliverable, so we strip location while keeping what
the pipeline needs (focal length, lens, orientation):

  JPEG: the EXIF GPS block is deleted and EXIF re-inserted without re-encoding
        the image (pixels are byte-identical).
  MP4/MOV: streams are remuxed without re-encoding; every container/stream tag
        is copied except location ones.

Usage: python scripts/strip_location.py <folder>   (edits files in place)
"""
import sys
from pathlib import Path

import av
import piexif

LOCATION_KEYS = ("location", "gps", "xyz")


def _dump_without_gps(exif: dict) -> bytes:
    exif["GPS"] = {}
    for _ in range(20):
        try:
            return piexif.dump(exif)
        except ValueError as e:
            # Some phones store UNDEFINED-type tags (e.g. SceneType 41729) as plain ints,
            # which piexif refuses to write back. Convert that tag to bytes and retry.
            tag = int(str(e).splitlines()[-1].split(" in ")[0].strip())
            ifd = next(k for k in ("0th", "Exif", "1st") if tag in exif.get(k, {}))
            v = exif[ifd][tag]
            exif[ifd][tag] = bytes([v]) if isinstance(v, int) else bytes(v)
    raise ValueError("could not rewrite EXIF")


def strip_jpeg(p: Path) -> bool:
    exif = piexif.load(str(p))
    if not exif.get("GPS"):
        return False
    piexif.insert(_dump_without_gps(exif), str(p))
    return True


def strip_video(p: Path) -> bool:
    if not p.exists() or ".tmp" in p.name:
        return False
    try:
        with av.open(str(p)) as src:
            meta = dict(src.metadata)
            if not any(k for k in meta if any(s in k.lower() for s in LOCATION_KEYS)):
                return False
            tmp = p.with_suffix(".tmp" + p.suffix)
            with av.open(str(tmp), "w", options={"movflags": "use_metadata_tags"}) as dst:
                for k, v in meta.items():
                    if not any(s in k.lower() for s in LOCATION_KEYS):
                        dst.metadata[k] = v
                mapping = {}
                for s in src.streams:
                    if s.type not in ("video", "audio"):
                        continue
                    if s.type == "audio" and getattr(s, "codec_context", None) is None:
                        continue
                    try:
                        mapping[s.index] = dst.add_stream_from_template(s)
                    except ValueError:
                        continue
                for packet in src.demux(list(src.streams)):
                    if packet.dts is None or packet.stream.index not in mapping:
                        continue
                    packet.stream = mapping[packet.stream.index]
                    dst.mux(packet)
        tmp.replace(p)
        return True
    except FileNotFoundError:
        return False


def strip_heic(p: Path) -> bool:
    """HEIC has no lossless metadata-only edit in Python: decode and re-encode losslessly
    (decoded pixels identical), with the EXIF minus its GPS block."""
    import pillow_heif
    heif = pillow_heif.open_heif(str(p))
    exif = heif.info.get("exif")
    if not exif:
        return False
    d = piexif.load(exif)
    if not d.get("GPS"):
        return False
    img = heif.to_pillow()
    pillow_heif.from_pillow(img).save(str(p), quality=-1, exif=_dump_without_gps(d))
    return True


def main(root: str) -> None:
    n = 0
    for p in sorted(Path(root).rglob("*")):
        if not p.is_file() or ".tmp" in p.name:
            continue
        ext = p.suffix.lower()
        if ext in (".jpg", ".jpeg"):
            n += strip_jpeg(p)
        elif ext in (".heic", ".heif"):
            n += strip_heic(p)
        elif ext in (".mp4", ".mov"):
            n += strip_video(p)
    print(f"stripped location from {n} files under {root}")


if __name__ == "__main__":
    main(sys.argv[1])
