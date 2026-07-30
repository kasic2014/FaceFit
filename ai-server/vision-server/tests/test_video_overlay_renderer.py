from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np


VISION_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(VISION_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(VISION_SERVER_ROOT))

from app.vision import video_overlay_renderer as renderer


def frame_result():
    pose = [
        {"index": index, "x": 0.1 + index * 0.03, "y": 0.5}
        for index in range(13)
    ]
    return {
        "timestamp_ms": 200,
        "source_frame_index": 2,
        "face_detection_status": "detected",
        "required_pose_landmarks_available": True,
        "face_landmarks": [{"index": 0, "x": 0.5, "y": 0.3}],
        "face_bounding_box": {
            "clamped": {"min_x": 10, "min_y": 10, "max_x": 30, "max_y": 30}
        },
        "pose_landmarks": pose,
    }


class FakeWriter:
    def __init__(self, opened=True):
        self.opened = opened
        self.frames = []
        self.released = False

    def isOpened(self):
        return self.opened

    def write(self, frame):
        self.frames.append(frame.copy())

    def release(self):
        self.released = True


class VideoOverlayRendererTests(unittest.TestCase):
    def test_render_does_not_mutate_input(self) -> None:
        source = np.zeros((80, 100, 3), dtype=np.uint8)
        original = source.copy()
        output = renderer.render_video_overlay_frame(source, frame_result())
        self.assertGreater(int(output.sum()), 0)
        np.testing.assert_array_equal(source, original)

    def test_only_service_pose_indices_are_displayed(self) -> None:
        self.assertEqual(renderer.DISPLAY_POSE_INDICES, {0, 7, 8, 11, 12})

    def test_writer_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            renderer.cv2, "VideoWriter", return_value=FakeWriter(False)
        ):
            output = renderer.VideoOverlayWriter(
                Path(directory) / "overlay.mp4", 5, 100, 80
            )
            self.assertFalse(output.available)
            self.assertFalse((Path(directory) / "overlay.mp4").exists())

    def test_writer_creates_output(self) -> None:
        fake = FakeWriter()
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            renderer.cv2, "VideoWriter", return_value=fake
        ):
            path = Path(directory) / "overlay.mp4"
            output = renderer.VideoOverlayWriter(path, 5, 100, 80)
            output.write(np.zeros((80, 100, 3), dtype=np.uint8))
            output.close()
            self.assertTrue(path.is_file())
            self.assertEqual(len(fake.frames), 1)
            self.assertTrue(fake.released)

    def test_sampled_frame_png(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frame.png"
            renderer.save_sampled_frame_png(
                np.zeros((20, 30, 3), dtype=np.uint8),
                path,
            )
            self.assertTrue(path.is_file())


if __name__ == "__main__":
    unittest.main()
