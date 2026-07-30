from __future__ import annotations

import math
import unittest
from unittest import mock

import cv2
import numpy as np

from app.vision.head_pose_estimator import create_approximate_camera_matrix, estimate_head_pose
from app.vision.head_pose_models import (
    HEAD_POSE_LANDMARK_INDICES, HEAD_POSE_MODEL_POINTS,
    HeadPoseConfiguration, HeadPoseFailureReason,
)


def fixture_landmarks(yaw=0.0, pitch=0.0, roll=0.0, width=1280, height=720):
    x, y, z = map(math.radians, (pitch, -yaw, -roll))
    rx = np.array(((1,0,0),(0,math.cos(x),-math.sin(x)),(0,math.sin(x),math.cos(x))))
    ry = np.array(((math.cos(y),0,math.sin(y)),(0,1,0),(-math.sin(y),0,math.cos(y))))
    rz = np.array(((math.cos(z),-math.sin(z),0),(math.sin(z),math.cos(z),0),(0,0,1)))
    rotation, _ = cv2.Rodrigues(rz @ ry @ rx)
    points, _ = cv2.projectPoints(
        np.asarray(HEAD_POSE_MODEL_POINTS, np.float64), rotation,
        np.array(((0.0,), (0.0,), (1800.0,))),
        create_approximate_camera_matrix(width, height), np.zeros((4,1)),
    )
    return [
        {"index": index, "x": point[0] / width, "y": point[1] / height, "z": 0.0}
        for index, point in zip(HEAD_POSE_LANDMARK_INDICES, points.reshape(-1,2))
    ]


class HeadPoseEstimatorTests(unittest.TestCase):
    def test_camera_matrix(self):
        matrix = create_approximate_camera_matrix(1280, 720)
        self.assertEqual((matrix[0,0], matrix[1,1], matrix[0,2], matrix[1,2]), (1280,1280,640,360))

    def test_camera_matrix_rejects_invalid_values(self):
        for values in ((0,720,1),(1280,-1,1),(math.nan,720,1),(1280,720,math.inf)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                create_approximate_camera_matrix(*values)

    def test_frontal_fixture(self):
        result = estimate_head_pose(fixture_landmarks(), 1280, 720, target_available=True, target_id="TARGET_001", target_confidence=1)
        self.assertTrue(result.available)
        for value in (result.yaw_deg, result.pitch_deg, result.roll_deg):
            self.assertAlmostEqual(value, 0, delta=.1)

    def test_direction_fixtures_follow_public_signs(self):
        for axis, value in (("yaw",25),("yaw",-25),("pitch",20),("pitch",-20),("roll",15),("roll",-15)):
            with self.subTest(axis=axis, value=value):
                result = estimate_head_pose(fixture_landmarks(**{axis:value}), 1280, 720, target_available=True, target_id="TARGET_001", target_confidence=1)
                self.assertTrue(result.available)
                self.assertAlmostEqual(getattr(result, f"{axis}_deg"), value, delta=.2)

    def test_target_unavailable_is_null_not_zero(self):
        result = estimate_head_pose(fixture_landmarks(), 1280, 720, target_available=False, target_id=None)
        self.assertFalse(result.available)
        self.assertIsNone(result.yaw_deg)
        self.assertEqual(result.failure_reason, HeadPoseFailureReason.TARGET_NOT_AVAILABLE.value)

    def test_missing_face_and_landmark(self):
        face = estimate_head_pose([],1280,720,target_available=True,target_id="TARGET_001")
        missing = estimate_head_pose(fixture_landmarks()[:-1],1280,720,target_available=True,target_id="TARGET_001")
        self.assertEqual(face.failure_reason, HeadPoseFailureReason.FACE_NOT_DETECTED.value)
        self.assertEqual(missing.failure_reason, HeadPoseFailureReason.REQUIRED_LANDMARK_MISSING.value)

    def test_invalid_coordinates(self):
        for value in (-.1,1.1,math.nan,math.inf):
            points = fixture_landmarks()
            points[0]["x"] = value
            result = estimate_head_pose(points,1280,720,target_available=True,target_id="TARGET_001")
            self.assertEqual(result.failure_reason, HeadPoseFailureReason.INVALID_LANDMARK_COORDINATE.value)

    @mock.patch("app.vision.head_pose_estimator.cv2.solvePnP", return_value=(False,None,None))
    def test_solvepnp_failure_is_coded(self, _):
        result = estimate_head_pose(fixture_landmarks(),1280,720,target_available=True,target_id="TARGET_001")
        self.assertEqual(result.failure_reason, HeadPoseFailureReason.SOLVEPNP_FAILED.value)

    def test_reprojection_threshold(self):
        points = fixture_landmarks()
        points[-1]["x"] += .05
        result = estimate_head_pose(
            points,1280,720,target_available=True,target_id="TARGET_001",
            configuration=HeadPoseConfiguration(max_reprojection_error_px=.01),
        )
        self.assertEqual(result.failure_reason, HeadPoseFailureReason.REPROJECTION_ERROR_TOO_HIGH.value)

    def test_confidence_and_diagnostics(self):
        result = estimate_head_pose(fixture_landmarks(),1280,720,target_available=True,target_id="TARGET_001",target_confidence=.8)
        self.assertTrue(0 <= result.confidence <= 1)
        self.assertEqual(result.landmark_count, 6)
        self.assertIsNotNone(result.axis_points)


if __name__ == "__main__":
    unittest.main()
