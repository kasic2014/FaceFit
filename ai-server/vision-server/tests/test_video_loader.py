from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cv2
import numpy as np


VISION_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(VISION_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(VISION_SERVER_ROOT))

from app.vision import video_loader as loader


class FakeCapture:
    def __init__(self, *, opened=True, properties=None, frames=None) -> None:
        self.opened = opened
        self.properties = properties or {}
        self.frames = list(frames or [])
        self.released = False

    def isOpened(self):
        return self.opened

    def get(self, key):
        return self.properties.get(key, 0)

    def read(self):
        if not self.frames:
            return False, None
        return True, self.frames.pop(0)

    def release(self):
        self.released = True


class VideoLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _file(self, name="video.mp4", data=b"video") -> Path:
        path = self.root / name
        path.write_bytes(data)
        return path

    def test_all_supported_extensions(self) -> None:
        for extension in (".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"):
            with self.subTest(extension=extension):
                self.assertEqual(
                    loader.validate_video_path(self._file(f"x{extension}")).suffix,
                    extension,
                )

    def test_unsupported_extension(self) -> None:
        with self.assertRaises(loader.VideoInputError) as raised:
            loader.validate_video_path(self._file("x.txt"))
        self.assertEqual(raised.exception.code, "VIDEO_EXTENSION_UNSUPPORTED")

    def test_missing_file(self) -> None:
        with self.assertRaises(loader.VideoInputError) as raised:
            loader.validate_video_path(self.root / "missing.mp4")
        self.assertEqual(raised.exception.code, "VIDEO_NOT_FOUND")

    def test_directory_is_not_regular_file(self) -> None:
        path = self.root / "folder.mp4"
        path.mkdir()
        with self.assertRaises(loader.VideoInputError) as raised:
            loader.validate_video_path(path)
        self.assertEqual(raised.exception.code, "VIDEO_NOT_REGULAR_FILE")

    def test_empty_file(self) -> None:
        with self.assertRaises(loader.VideoInputError) as raised:
            loader.validate_video_path(self._file(data=b""))
        self.assertEqual(raised.exception.code, "VIDEO_FILE_EMPTY")

    def test_capture_open_failure(self) -> None:
        path = self._file()
        fake = FakeCapture(opened=False)
        with mock.patch.object(loader.cv2, "VideoCapture", return_value=fake):
            with self.assertRaises(loader.VideoInputError) as raised:
                loader.open_video_capture(path)
        self.assertEqual(raised.exception.code, "VIDEO_CAPTURE_OPEN_FAILED")
        self.assertTrue(fake.released)

    def test_metadata_and_first_frame(self) -> None:
        path = self._file()
        frame = np.zeros((48, 64, 3), dtype=np.uint8)
        properties = {
            cv2.CAP_PROP_FRAME_WIDTH: 64,
            cv2.CAP_PROP_FRAME_HEIGHT: 48,
            cv2.CAP_PROP_FPS: 10,
            cv2.CAP_PROP_FRAME_COUNT: 30,
            cv2.CAP_PROP_FOURCC: cv2.VideoWriter_fourcc(*"mp4v"),
        }
        fake = FakeCapture(properties=properties, frames=[frame])
        with mock.patch.object(loader, "open_video_capture", return_value=fake):
            result = loader.inspect_video_metadata(path)
        self.assertEqual(result["width"], 64)
        self.assertEqual(result["height"], 48)
        self.assertEqual(result["original_fps"], 10)
        self.assertEqual(result["declared_frame_count"], 30)
        self.assertEqual(result["estimated_duration_sec"], 3)
        self.assertEqual(result["codec_fourcc"], "mp4v")
        self.assertTrue(result["first_frame_decoded"])
        self.assertTrue(fake.released)

    def test_invalid_width_height_and_fps(self) -> None:
        path = self._file()
        base = {
            cv2.CAP_PROP_FRAME_WIDTH: 64,
            cv2.CAP_PROP_FRAME_HEIGHT: 48,
            cv2.CAP_PROP_FPS: 10,
        }
        for key, code in (
            (cv2.CAP_PROP_FRAME_WIDTH, "VIDEO_WIDTH_INVALID"),
            (cv2.CAP_PROP_FRAME_HEIGHT, "VIDEO_HEIGHT_INVALID"),
            (cv2.CAP_PROP_FPS, "VIDEO_FPS_INVALID"),
        ):
            properties = dict(base)
            properties[key] = 0
            fake = FakeCapture(
                properties=properties,
                frames=[np.zeros((48, 64, 3), np.uint8)],
            )
            with self.subTest(code=code), mock.patch.object(
                loader, "open_video_capture", return_value=fake
            ):
                with self.assertRaises(loader.VideoInputError) as raised:
                    loader.inspect_video_metadata(path)
                self.assertEqual(raised.exception.code, code)

    def test_undecodable_video(self) -> None:
        path = self._file()
        fake = FakeCapture(
            properties={
                cv2.CAP_PROP_FRAME_WIDTH: 64,
                cv2.CAP_PROP_FRAME_HEIGHT: 48,
                cv2.CAP_PROP_FPS: 10,
            }
        )
        with mock.patch.object(loader, "open_video_capture", return_value=fake):
            with self.assertRaises(loader.VideoInputError) as raised:
                loader.inspect_video_metadata(path)
        self.assertEqual(raised.exception.code, "VIDEO_DECODE_FAILED")

    def test_sha256(self) -> None:
        path = self._file(data=b"abc")
        self.assertEqual(
            loader.calculate_video_sha256(path),
            hashlib.sha256(b"abc").hexdigest(),
        )

    def test_safe_video_id_is_traversal_free(self) -> None:
        value = loader.create_safe_video_id("../../한글 video.mp4", "ab" * 32)
        self.assertNotIn("..", value)
        self.assertNotIn("/", value)
        self.assertTrue(value.endswith("_abababab"))

    def test_declared_frame_count_unavailable_warns(self) -> None:
        path = self._file()
        fake = FakeCapture(
            properties={
                cv2.CAP_PROP_FRAME_WIDTH: 64,
                cv2.CAP_PROP_FRAME_HEIGHT: 48,
                cv2.CAP_PROP_FPS: 10,
                cv2.CAP_PROP_FRAME_COUNT: 0,
            },
            frames=[np.zeros((48, 64, 3), np.uint8)],
        )
        with mock.patch.object(loader, "open_video_capture", return_value=fake):
            result = loader.inspect_video_metadata(path)
        self.assertIsNone(result["estimated_duration_sec"])
        self.assertTrue(any("frame count" in item for item in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
