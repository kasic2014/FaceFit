from __future__ import annotations

import sys
import unittest
from pathlib import Path


VISION_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(VISION_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(VISION_SERVER_ROOT))

from app.vision import video_landmark_constants as constants


def landmark(index: int, *, missing=False):
    return {
        "index": index,
        "x": None if missing else index / 20,
        "y": 0.5,
        "z": 0.0,
        "visibility": 0.9,
        "presence": 0.8,
    }


class VideoLandmarkConstantsTests(unittest.TestCase):
    def test_canonical_indices(self) -> None:
        self.assertEqual(constants.POSE_NOSE_INDEX, 0)
        self.assertEqual(constants.POSE_LEFT_EAR_INDEX, 7)
        self.assertEqual(constants.POSE_RIGHT_EAR_INDEX, 8)
        self.assertEqual(constants.POSE_LEFT_SHOULDER_INDEX, 11)
        self.assertEqual(constants.POSE_RIGHT_SHOULDER_INDEX, 12)

    def test_required_scope_only(self) -> None:
        required = constants.get_required_pose_landmark_indices()
        self.assertEqual(
            required,
            {"nose": 0, "left_shoulder": 11, "right_shoulder": 12},
        )
        for excluded in ("chin", "wrist", "pelvis", "knee", "ankle"):
            self.assertNotIn(excluded, required)

    def test_optional_scope(self) -> None:
        self.assertEqual(
            constants.get_optional_pose_landmark_indices(),
            {"left_ear": 7, "right_ear": 8},
        )

    def test_extract_required(self) -> None:
        values = [landmark(index) for index in range(13)]
        result = constants.extract_required_pose_landmarks(values)
        self.assertEqual(result["nose"]["index"], 0)
        self.assertEqual(result["left_shoulder"]["index"], 11)
        self.assertEqual(result["right_shoulder"]["index"], 12)

    def test_missing_required_is_detected(self) -> None:
        values = [landmark(index) for index in range(12)]
        result = constants.extract_required_pose_landmarks(values)
        self.assertFalse(constants.validate_required_pose_landmarks(result))

    def test_non_finite_was_sanitized_to_missing(self) -> None:
        values = [landmark(index) for index in range(13)]
        values[11] = landmark(11, missing=True)
        self.assertFalse(
            constants.validate_required_pose_landmarks(
                constants.extract_required_pose_landmarks(values)
            )
        )

    def test_optional_missing_does_not_change_required(self) -> None:
        values = [landmark(index) for index in (0, 11, 12)]
        required = constants.extract_required_pose_landmarks(values)
        optional = constants.extract_optional_pose_landmarks(values)
        self.assertTrue(constants.validate_required_pose_landmarks(required))
        self.assertIsNone(optional["left_ear"])
        self.assertIsNone(optional["right_ear"])


if __name__ == "__main__":
    unittest.main()
