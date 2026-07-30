from __future__ import annotations

import math
import unittest

from app.vision.posture_raw_models import PostureFailureReason
from app.vision.shoulder_posture_estimator import estimate_shoulder_posture


def point(x, y, visibility=0.9, presence=0.8):
    return {
        "x": x,
        "y": y,
        "visibility": visibility,
        "presence": presence,
    }


def estimate(left=None, right=None, nose=None, face=None, **kwargs):
    return estimate_shoulder_posture(
        left if left is not None else point(0.7, 0.7),
        right if right is not None else point(0.3, 0.7),
        nose if nose is not None else point(0.5, 0.3),
        face if face is not None else point(0.5, 0.35),
        target_id=kwargs.pop("target_id", "TARGET_001"),
        target_confidence=kwargs.pop("target_confidence", 0.9),
        **kwargs,
    )


class ShoulderPostureEstimatorTests(unittest.TestCase):
    def test_center_width_and_offsets(self):
        result = estimate()
        self.assertTrue(result.available)
        self.assertAlmostEqual(result.shoulder_center_x, 0.5)
        self.assertAlmostEqual(result.shoulder_center_y, 0.7)
        self.assertAlmostEqual(result.shoulder_width_norm, 0.4)
        self.assertAlmostEqual(result.nose_shoulder_offset_x_norm, 0.0)
        self.assertAlmostEqual(result.nose_shoulder_offset_y_norm, -1.0)
        self.assertLess(result.confidence, 1.0)
        self.assertGreater(result.confidence, 0.0)

    def test_subject_right_lower_is_positive(self):
        result = estimate(
            left=point(0.7, 0.6),
            right=point(0.3, 0.7),
        )
        self.assertGreater(result.shoulder_tilt_deg, 0)
        self.assertGreater(result.shoulder_height_difference_norm, 0)

    def test_subject_left_lower_is_negative(self):
        result = estimate(
            left=point(0.7, 0.7),
            right=point(0.3, 0.6),
        )
        self.assertLess(result.shoulder_tilt_deg, 0)
        self.assertLess(result.shoulder_height_difference_norm, 0)

    def test_equal_height_is_zero_degrees(self):
        self.assertAlmostEqual(estimate().shoulder_tilt_deg, 0.0)

    def test_screen_mirror_does_not_change_anatomical_sign(self):
        original = estimate(
            left=point(0.8, 0.6),
            right=point(0.2, 0.7),
        )
        mirrored = estimate(
            left=point(0.2, 0.6),
            right=point(0.8, 0.7),
        )
        self.assertAlmostEqual(original.shoulder_tilt_deg, mirrored.shoulder_tilt_deg)

    def test_nose_screen_direction_sign(self):
        left = estimate(nose=point(0.4, 0.3))
        right = estimate(nose=point(0.6, 0.3))
        self.assertLess(left.nose_shoulder_offset_x_norm, 0)
        self.assertGreater(right.nose_shoulder_offset_x_norm, 0)

    def test_face_missing_only_nulls_face_alignment(self):
        result = estimate(face={})
        self.assertTrue(result.available)
        self.assertTrue(result.nose_alignment_available)
        self.assertFalse(result.face_alignment_available)
        self.assertIsNone(result.face_shoulder_offset_x_norm)
        self.assertIsNotNone(result.nose_shoulder_offset_x_norm)
        self.assertEqual(
            result.failure_reason,
            PostureFailureReason.FACE_NOT_DETECTED.value,
        )

    def test_nose_missing_only_nulls_nose_alignment(self):
        result = estimate(nose={})
        self.assertTrue(result.available)
        self.assertFalse(result.nose_alignment_available)
        self.assertTrue(result.face_alignment_available)
        self.assertIsNone(result.nose_shoulder_offset_x_norm)
        self.assertIsNotNone(result.face_shoulder_offset_x_norm)

    def test_missing_shoulders_have_distinct_reasons(self):
        cases = (
            ({}, point(0.3, 0.7), PostureFailureReason.LEFT_SHOULDER_MISSING),
            (point(0.7, 0.7), {}, PostureFailureReason.RIGHT_SHOULDER_MISSING),
            ({}, {}, PostureFailureReason.BOTH_SHOULDERS_MISSING),
        )
        for left, right, reason in cases:
            result = estimate(left=left, right=right)
            self.assertFalse(result.available)
            self.assertEqual(result.failure_reason, reason.value)
            self.assertIsNone(result.shoulder_tilt_deg)

    def test_zero_and_tiny_width_are_rejected(self):
        for right in (point(0.7, 0.7), point(0.701, 0.701)):
            result = estimate(left=point(0.7, 0.7), right=right)
            self.assertFalse(result.available)
            self.assertEqual(
                result.failure_reason,
                PostureFailureReason.INVALID_SHOULDER_WIDTH.value,
            )

    def test_non_finite_is_rejected(self):
        for value in (math.nan, math.inf, -math.inf):
            result = estimate(left=point(value, 0.7))
            self.assertFalse(result.available)
            self.assertEqual(
                result.failure_reason,
                PostureFailureReason.NON_FINITE_COORDINATE.value,
            )

    def test_target_and_multiple_person_are_unavailable(self):
        missing = estimate(target_id=None)
        multiple = estimate(candidate_count=2)
        self.assertEqual(
            missing.failure_reason,
            PostureFailureReason.TARGET_NOT_AVAILABLE.value,
        )
        self.assertEqual(
            multiple.failure_reason,
            PostureFailureReason.MULTIPLE_PERSON_DETECTED.value,
        )


if __name__ == "__main__":
    unittest.main()
