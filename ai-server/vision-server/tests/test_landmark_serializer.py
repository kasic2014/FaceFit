from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np


VISION_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(VISION_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(VISION_SERVER_ROOT))

from app.vision import landmark_serializer as serializer


def landmark(
    x=0.1,
    y=0.2,
    z=-0.3,
    *,
    visibility=None,
    presence=None,
):
    values = {"x": x, "y": y, "z": z}
    if visibility is not None:
        values["visibility"] = visibility
    if presence is not None:
        values["presence"] = presence
    return SimpleNamespace(**values)


class LandmarkSerializerTests(unittest.TestCase):
    def test_landmark_index_is_preserved(self) -> None:
        result = serializer.serialize_normalized_landmarks(
            [landmark(), landmark(0.3, 0.4, 0.5)]
        )
        self.assertEqual([item["index"] for item in result], [0, 1])

    def test_normalized_landmark_serialization(self) -> None:
        result = serializer.serialize_normalized_landmarks(
            [landmark(0.123456789, 0.4, -0.2, visibility=0.8, presence=0.7)]
        )[0]
        self.assertEqual(result["x"], 0.123456789)
        self.assertEqual(result["visibility"], 0.8)
        self.assertEqual(result["presence"], 0.7)

    def test_world_landmark_serialization(self) -> None:
        result = serializer.serialize_world_landmarks(
            [landmark(1.0, 2.0, 3.0)]
        )[0]
        self.assertEqual((result["x"], result["y"], result["z"]), (1.0, 2.0, 3.0))

    def test_missing_visibility_is_null(self) -> None:
        result = serializer.serialize_normalized_landmarks([landmark()])[0]
        self.assertIsNone(result["visibility"])

    def test_missing_presence_is_null(self) -> None:
        result = serializer.serialize_normalized_landmarks([landmark()])[0]
        self.assertIsNone(result["presence"])

    def test_numpy_scalar_becomes_python_float(self) -> None:
        result = serializer.serialize_normalized_landmarks(
            [landmark(np.float32(0.25), np.float64(0.5), np.int64(1))]
        )[0]
        self.assertIsInstance(result["x"], float)
        self.assertIsInstance(result["y"], float)
        self.assertIsInstance(result["z"], float)

    def test_nan_becomes_null_with_warning(self) -> None:
        warnings: list[str] = []
        value = serializer.sanitize_number(math.nan, warnings, "x")
        self.assertIsNone(value)
        self.assertEqual(len(warnings), 1)

    def test_infinity_becomes_null_with_warning(self) -> None:
        warnings: list[str] = []
        value = serializer.sanitize_number(math.inf, warnings, "x")
        self.assertIsNone(value)
        self.assertEqual(len(warnings), 1)

    def test_normalized_bbox_preserves_out_of_range_coordinates(self) -> None:
        points = serializer.serialize_normalized_landmarks(
            [landmark(-0.1, 0.2), landmark(1.2, 0.9)]
        )
        bbox = serializer.calculate_normalized_bbox(points)
        self.assertEqual(
            bbox,
            {"min_x": -0.1, "min_y": 0.2, "max_x": 1.2, "max_y": 0.9},
        )

    def test_pixel_bbox_keeps_raw_and_clamped_values(self) -> None:
        bbox = serializer.calculate_pixel_bbox(
            {"min_x": -0.1, "min_y": 0.2, "max_x": 1.2, "max_y": 0.9},
            100,
            50,
        )
        self.assertEqual(bbox["min_x"], -10)
        self.assertEqual(bbox["max_x"], 120)
        self.assertEqual(bbox["clamped"]["min_x"], 0)
        self.assertEqual(bbox["clamped"]["max_x"], 99)

    def test_empty_bbox_is_null(self) -> None:
        self.assertIsNone(serializer.calculate_normalized_bbox([]))
        self.assertIsNone(serializer.calculate_pixel_bbox(None, 10, 10))

    def test_face_zero_result(self) -> None:
        result = serializer.serialize_face_result(
            SimpleNamespace(face_landmarks=[]),
            100,
            100,
        )
        self.assertEqual(result["detection_status"], "no_face_detected")
        self.assertEqual(result["face_count"], 0)
        self.assertEqual(result["faces"], [])
        self.assertIsNone(result["error"])

    def test_face_one_and_landmark_count(self) -> None:
        result = serializer.serialize_face_result(
            SimpleNamespace(face_landmarks=[[landmark(), landmark()]]),
            100,
            100,
        )
        self.assertEqual(result["face_count"], 1)
        self.assertEqual(result["faces"][0]["face_index"], 0)
        self.assertEqual(result["faces"][0]["landmark_count"], 2)

    def test_pose_zero_result(self) -> None:
        result = serializer.serialize_pose_result(
            SimpleNamespace(pose_landmarks=[], pose_world_landmarks=[]),
            100,
            100,
        )
        self.assertEqual(result["detection_status"], "no_pose_detected")
        self.assertEqual(result["pose_count"], 0)
        self.assertEqual(result["poses"], [])

    def test_pose_one_landmark_and_world_landmark_counts(self) -> None:
        result = serializer.serialize_pose_result(
            SimpleNamespace(
                pose_landmarks=[[landmark(), landmark()]],
                pose_world_landmarks=[[landmark(1, 2, 3)]],
            ),
            100,
            100,
        )
        self.assertEqual(result["pose_count"], 1)
        self.assertEqual(result["poses"][0]["landmark_count"], 2)
        self.assertEqual(result["poses"][0]["world_landmark_count"], 1)
        self.assertEqual(result["poses"][0]["world_landmarks"][0]["x"], 1.0)

    def test_missing_pose_world_landmarks_becomes_empty(self) -> None:
        result = serializer.serialize_pose_result(
            SimpleNamespace(pose_landmarks=[[landmark()]], pose_world_landmarks=[]),
            100,
            100,
        )
        self.assertEqual(result["poses"][0]["world_landmarks"], [])
        self.assertEqual(result["poses"][0]["world_landmark_count"], 0)


if __name__ == "__main__":
    unittest.main()
