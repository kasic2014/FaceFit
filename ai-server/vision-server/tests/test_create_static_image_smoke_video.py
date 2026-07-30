from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

import cv2
import numpy as np


VISION_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(VISION_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(VISION_SERVER_ROOT))

from scripts import create_static_image_smoke_video as smoke


class CreateStaticImageSmokeVideoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.image_path = self.root / "source.jpg"
        success, encoded = cv2.imencode(
            ".jpg",
            np.full((120, 80, 3), 127, dtype=np.uint8),
        )
        self.assertTrue(success)
        self.image_path.write_bytes(encoded.tobytes())
        self.image_hash = hashlib.sha256(self.image_path.read_bytes()).hexdigest()
        self.output_path = self.root / "generated" / "smoke.mp4"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_creates_three_second_ten_fps_video(self) -> None:
        result = smoke.create_smoke_video(
            self.image_path,
            output_path=self.output_path,
        )
        self.assertEqual(result["frame_count"], 30)
        self.assertAlmostEqual(result["fps"], 10, places=2)
        self.assertAlmostEqual(result["duration_sec"], 3, places=1)
        self.assertTrue(self.output_path.is_file())

    def test_manifest_contract(self) -> None:
        result = smoke.create_smoke_video(
            self.image_path,
            output_path=self.output_path,
        )
        manifest_path = self.output_path.with_suffix(".manifest.json")
        parsed = json.loads(manifest_path.read_text("utf-8"))
        self.assertEqual(parsed, result)
        self.assertTrue(parsed["synthetic_static_video"])
        self.assertTrue(parsed["not_valid_for_temporal_motion_validation"])
        self.assertEqual(parsed["purpose"], "video_pipeline_smoke_test")

    def test_source_image_hash_and_bytes_preserved(self) -> None:
        before = self.image_path.read_bytes()
        result = smoke.create_smoke_video(
            self.image_path,
            output_path=self.output_path,
        )
        self.assertEqual(result["source_image_sha256"], self.image_hash)
        self.assertEqual(self.image_path.read_bytes(), before)

    def test_aspect_ratio_is_preserved(self) -> None:
        result = smoke.create_smoke_video(
            self.image_path,
            output_path=self.output_path,
            max_height=60,
        )
        self.assertEqual((result["width"], result["height"]), (40, 60))

    def test_existing_output_requires_overwrite(self) -> None:
        smoke.create_smoke_video(self.image_path, output_path=self.output_path)
        with self.assertRaises(smoke.SmokeVideoError) as raised:
            smoke.create_smoke_video(self.image_path, output_path=self.output_path)
        self.assertEqual(raised.exception.code, "SMOKE_VIDEO_OUTPUT_EXISTS")

    def test_cli_exit_codes(self) -> None:
        with redirect_stderr(StringIO()):
            self.assertEqual(smoke.main([]), 2)
        with redirect_stdout(StringIO()):
            self.assertEqual(
                smoke.main(
                    [
                        "--input",
                        str(self.image_path),
                        "--output",
                        str(self.output_path),
                    ]
                ),
                0,
            )
        with redirect_stderr(StringIO()):
            self.assertEqual(
                smoke.main(
                    [
                        "--input",
                        str(self.root / "missing.jpg"),
                        "--output",
                        str(self.root / "other.mp4"),
                    ]
                ),
                1,
            )


if __name__ == "__main__":
    unittest.main()
