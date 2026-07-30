from __future__ import annotations

import os
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

from app.vision import overlay_renderer as renderer


def face_result(detected: bool = True):
    faces = []
    if detected:
        faces = [
            {
                "face_index": 0,
                "landmarks": [
                    {"index": 0, "x": -0.2, "y": 0.5, "visibility": None},
                    {"index": 1, "x": 1.2, "y": 0.6, "visibility": None},
                ],
                "pixel_bounding_box": {
                    "clamped": {
                        "min_x": 0,
                        "min_y": 10,
                        "max_x": 39,
                        "max_y": 30,
                    }
                },
            }
        ]
    return {"face_count": len(faces), "faces": faces}


def pose_result(detected: bool = True, count: int = 33):
    landmarks = [
        {
            "index": index,
            "x": index / max(count - 1, 1),
            "y": 0.5,
            "visibility": 0.9,
        }
        for index in range(count)
    ]
    poses = []
    if detected:
        poses = [
            {
                "pose_index": 0,
                "landmarks": landmarks,
                "pixel_bounding_box": {
                    "clamped": {
                        "min_x": 0,
                        "min_y": 10,
                        "max_x": 39,
                        "max_y": 30,
                    }
                },
            }
        ]
    return {"pose_count": len(poses), "poses": poses}


class OverlayRendererTests(unittest.TestCase):
    def setUp(self) -> None:
        self.image = np.zeros((40, 40, 3), dtype=np.uint8)

    def test_overlay_clamp(self) -> None:
        self.assertEqual(
            renderer.normalized_to_clamped_pixel(-0.5, 1.5, 40, 40),
            (0, 39),
        )

    def test_face_overlay_created_without_mutating_input(self) -> None:
        original = self.image.copy()
        output, warnings = renderer.render_face_overlay(
            self.image,
            face_result(),
        )
        self.assertEqual(output.shape, self.image.shape)
        self.assertGreater(int(output.sum()), 0)
        np.testing.assert_array_equal(self.image, original)
        self.assertEqual(warnings, [])

    def test_pose_overlay_created(self) -> None:
        output, warnings = renderer.render_pose_overlay(
            self.image,
            pose_result(),
        )
        self.assertGreater(int(output.sum()), 0)
        self.assertEqual(warnings, [])

    def test_combined_overlay_created(self) -> None:
        output, warnings = renderer.render_combined_overlay(
            self.image,
            face_result(),
            pose_result(),
        )
        self.assertGreater(int(output.sum()), 0)
        self.assertEqual(warnings, [])

    def test_no_detection_overlays_still_created(self) -> None:
        face, _ = renderer.render_face_overlay(self.image, face_result(False))
        pose, _ = renderer.render_pose_overlay(self.image, pose_result(False))
        combined, _ = renderer.render_combined_overlay(
            self.image,
            face_result(False),
            pose_result(False),
        )
        self.assertGreater(int(face.sum()), 0)
        self.assertGreater(int(pose.sum()), 0)
        self.assertGreater(int(combined.sum()), 0)

    def test_low_visibility_pose_point_is_omitted(self) -> None:
        result = pose_result()
        for item in result["poses"][0]["landmarks"]:
            item["visibility"] = 0.0
        output, _ = renderer.render_pose_overlay(self.image, result)
        self.assertGreater(int(output.sum()), 0)  # bounding box and label remain

    def test_out_of_range_pose_connection_warns(self) -> None:
        _, warnings = renderer.render_pose_overlay(
            self.image,
            pose_result(count=2),
        )
        self.assertTrue(any("out of range" in warning for warning in warnings))

    def test_atomic_png_save(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "overlay.png"
            real_replace = os.replace
            with mock.patch.object(
                renderer.os,
                "replace",
                wraps=real_replace,
            ) as replace:
                renderer.save_png_atomic(self.image, path)
            replace.assert_called_once()
            self.assertIsNotNone(cv2.imread(str(path)))
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
