from __future__ import annotations

import json
import unittest
from dataclasses import replace

from app.vision.neutral_baseline_estimator import (
    estimate_session_neutral_baseline,
)
from app.vision.neutral_baseline_collector import collect_baseline_candidates
from app.vision.neutral_baseline_models import NeutralBaselineFrame
from app.vision.neutral_baseline_serializer import dumps_strict
from app.vision.relative_feature_models import RelativeFeatureFailureReason
from app.vision.relative_feature_normalizer import (
    normalize_relative_feature_frame,
)


def baseline_frame(index: int) -> NeutralBaselineFrame:
    return NeutralBaselineFrame(
        timestamp_ms=index * 200,
        target_id="TARGET_001",
        target_status="TARGET_TRACKED",
        candidate_count=1,
        target_confidence=0.95,
        head_pose={
            "available": True,
            "yaw_deg": 20.0,
            "pitch_deg": -2.0,
            "roll_deg": 1.0,
            "confidence": 0.9,
        },
        head_angular_velocity_deg_per_sec=1.0,
        head_jump_candidate=False,
        posture_raw={
            "available": True,
            "shoulders_available": True,
            "nose_alignment_available": True,
            "face_alignment_available": True,
            "shoulder_tilt_deg": 2.0,
            "shoulder_height_difference_norm": 0.01,
            "shoulder_center_x": 0.5,
            "shoulder_center_y": 0.7,
            "shoulder_width_norm": 0.4,
            "nose_shoulder_offset_x_norm": 0.01,
            "nose_shoulder_offset_y_norm": -0.8,
            "face_shoulder_offset_x_norm": 0.02,
            "face_shoulder_offset_y_norm": -0.7,
            "confidence": 0.95,
        },
        posture_temporal={
            "shoulder_center_velocity_norm_per_sec": 0.005,
            "shoulder_tilt_velocity_deg_per_sec": 0.5,
            "shoulder_width_change_rate_per_sec": 0.001,
        },
        posture_jump_candidate=False,
    )


def make_baseline():
    collection = collect_baseline_candidates(
        [baseline_frame(index) for index in range(10)],
        collection_start_ms=0,
        collection_end_ms=2_000,
    )
    return estimate_session_neutral_baseline(collection)


def head(**changes):
    return {
        "available": True,
        "yaw_deg": 25.0,
        "pitch_deg": -3.0,
        "roll_deg": 1.0,
        "confidence": 0.8,
        **changes,
    }


def posture(**changes):
    return {
        "available": True,
        "shoulders_available": True,
        "nose_alignment_available": True,
        "face_alignment_available": True,
        "shoulder_tilt_deg": 1.0,
        "shoulder_height_difference_norm": 0.02,
        "shoulder_center_x": 0.51,
        "shoulder_center_y": 0.69,
        "shoulder_width_norm": 0.42,
        "nose_shoulder_offset_x_norm": 0.03,
        "nose_shoulder_offset_y_norm": -0.8,
        "face_shoulder_offset_x_norm": 0.02,
        "face_shoulder_offset_y_norm": -0.6,
        "confidence": 0.9,
        **changes,
    }


class RelativeFeatureNormalizerTests(unittest.TestCase):
    def test_raw_minus_baseline_preserves_positive_negative_and_zero(self):
        result = normalize_relative_feature_frame(
            timestamp_ms=3_000,
            target_id="TARGET_001",
            raw_head_pose=head(),
            raw_posture=posture(),
            baseline=make_baseline(),
        )
        self.assertEqual(result.head_pose.yaw.raw_value, 25.0)
        self.assertEqual(result.head_pose.yaw.baseline_value, 20.0)
        self.assertEqual(result.head_pose.yaw.relative_value, 5.0)
        self.assertEqual(result.head_pose.pitch.relative_value, -1.0)
        self.assertEqual(result.head_pose.roll.relative_value, 0.0)
        tilt = result.posture.shoulder.metrics["shoulder_tilt_deg"]
        self.assertEqual(tilt.relative_value, -1.0)

    def test_missing_raw_value_is_null_with_failure_reason(self):
        result = normalize_relative_feature_frame(
            timestamp_ms=3_000,
            target_id="TARGET_001",
            raw_head_pose=head(yaw_deg=None),
            raw_posture=posture(),
            baseline=make_baseline(),
        )
        self.assertIsNone(result.head_pose.yaw.relative_value)
        self.assertEqual(
            result.head_pose.yaw.failure_reason,
            RelativeFeatureFailureReason.RAW_VALUE_UNAVAILABLE.value,
        )

    def test_non_finite_raw_is_not_serialized_as_a_number(self):
        result = normalize_relative_feature_frame(
            timestamp_ms=3_000,
            target_id="TARGET_001",
            raw_head_pose=head(yaw_deg=float("nan"), confidence=float("nan")),
            raw_posture=posture(),
            baseline=make_baseline(),
        )
        self.assertEqual(result.head_pose.confidence, 0.0)
        self.assertEqual(
            result.head_pose.yaw.failure_reason,
            RelativeFeatureFailureReason.NON_FINITE_RAW_VALUE.value,
        )

    def test_unavailable_face_baseline_does_not_hide_shoulder_result(self):
        base = make_baseline()
        partial = replace(
            base,
            posture=replace(
                base.posture,
                face_alignment_available=False,
                face_shoulder_offset_x_norm=None,
                face_shoulder_offset_y_norm=None,
            ),
        )
        result = normalize_relative_feature_frame(
            timestamp_ms=3_000,
            target_id="TARGET_001",
            raw_head_pose=head(),
            raw_posture=posture(),
            baseline=partial,
        )
        self.assertTrue(result.posture.available)
        self.assertFalse(result.posture.face_alignment.available)
        self.assertEqual(
            result.posture.face_alignment.failure_reason,
            RelativeFeatureFailureReason
            .FACE_ALIGNMENT_BASELINE_UNAVAILABLE.value,
        )

    def test_missing_and_non_finite_baselines_are_distinct(self):
        base = make_baseline()
        missing = replace(
            base,
            head_pose=replace(
                base.head_pose,
                available=False,
                yaw_deg=None,
            ),
        )
        missing_result = normalize_relative_feature_frame(
            timestamp_ms=3_000,
            target_id="TARGET_001",
            raw_head_pose=head(),
            raw_posture=posture(),
            baseline=missing,
        )
        self.assertEqual(
            missing_result.head_pose.yaw.failure_reason,
            RelativeFeatureFailureReason.BASELINE_UNAVAILABLE.value,
        )

        non_finite = replace(
            base,
            head_pose=replace(base.head_pose, yaw_deg=float("nan")),
        )
        non_finite_result = normalize_relative_feature_frame(
            timestamp_ms=3_000,
            target_id="TARGET_001",
            raw_head_pose=head(),
            raw_posture=posture(),
            baseline=non_finite,
        )
        self.assertEqual(
            non_finite_result.head_pose.yaw.failure_reason,
            RelativeFeatureFailureReason.NON_FINITE_BASELINE_VALUE.value,
        )

    def test_target_and_timestamp_failures_apply_to_all_metrics(self):
        target_failure = normalize_relative_feature_frame(
            timestamp_ms=3_000,
            target_id="TARGET_002",
            raw_head_pose=head(),
            raw_posture=posture(),
            baseline=make_baseline(),
        )
        self.assertEqual(
            target_failure.head_pose.yaw.failure_reason,
            RelativeFeatureFailureReason.TARGET_MISMATCH.value,
        )
        time_failure = normalize_relative_feature_frame(
            timestamp_ms=-1,
            target_id="TARGET_001",
            raw_head_pose=head(),
            raw_posture=posture(),
            baseline=make_baseline(),
        )
        self.assertEqual(
            time_failure.posture.shoulder.failure_reason,
            RelativeFeatureFailureReason.INVALID_TIMESTAMP.value,
        )

    def test_strict_serialization_is_deterministic_and_rejects_nan(self):
        result = normalize_relative_feature_frame(
            timestamp_ms=3_000,
            target_id="TARGET_001",
            raw_head_pose=head(),
            raw_posture=posture(),
            baseline=make_baseline(),
        )
        first = dumps_strict(result)
        self.assertEqual(first, dumps_strict(result))
        self.assertEqual(json.loads(first)["head_pose"]["yaw"]["relative_value"], 5.0)
        with self.assertRaises(ValueError):
            dumps_strict({"invalid": float("nan")})


if __name__ == "__main__":
    unittest.main()
