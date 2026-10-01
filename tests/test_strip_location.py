import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "strip_location.py"
spec = importlib.util.spec_from_file_location("strip_location", MODULE_PATH)
strip_location = importlib.util.module_from_spec(spec)
spec.loader.exec_module(strip_location)


class StripLocationRegressionTests(unittest.TestCase):
    def test_main_skips_temp_artifacts_and_unwritable_audio_streams(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            real_video = tmp_path / "capture.mp4"
            real_video.write_bytes(b"real")
            stale_tmp = tmp_path / "capture.tmp.mp4"
            stale_tmp.write_bytes(b"stale")

            class FakeStream:
                def __init__(self, index, kind, codec_context=None):
                    self.index = index
                    self.type = kind
                    self.codec_context = codec_context

            class FakeContainer:
                def __init__(self):
                    self.metadata = {"com.apple.quicktime.location.ISO6709": "+12.34+/"}
                    self.streams = [FakeStream(0, "audio", None), FakeStream(1, "video", object())]

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def demux(self, streams):
                    return iter(())

                def add_stream_from_template(self, stream):
                    raise ValueError("template stream of type audio has no codec context")

            def fake_open(path, mode="r", *args, **kwargs):
                if Path(path).name.endswith(".tmp.mp4"):
                    raise AssertionError("temporary artifacts should be ignored")
                return FakeContainer()

            original_open = strip_location.av.open
            original_strip_video = strip_location.strip_video
            try:
                strip_location.av.open = fake_open
                calls = []

                def fake_strip_video(path: Path) -> bool:
                    calls.append(path.name)
                    return False

                strip_location.strip_video = fake_strip_video
                strip_location.main(str(tmp_path))
            finally:
                strip_location.av.open = original_open
                strip_location.strip_video = original_strip_video

            self.assertEqual(calls, ["capture.mp4"])


if __name__ == "__main__":
    unittest.main()
