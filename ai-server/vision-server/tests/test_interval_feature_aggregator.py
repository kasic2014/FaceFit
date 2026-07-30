from __future__ import annotations

import json
import unittest

from app.vision.interval_feature_aggregator import (
    aggregate_interval_features,
)
from app.vision.interval_models import (
    AnalysisInterval,
    IntervalAggregationConfig,
)
from app.vision.neutral_baseline_serializer import dumps_strict


SHOULDER = (
    "shoulder_tilt_deg",
    "shoulder_height_difference_norm",
    "shoulder_center_x",
    "shoulder_center_y",
    "shoulder_width_norm",
)
NOSE = (
    "nose_shoulder_offset_x_norm",
    "nose_shoulder_offset_y_norm",
)
FACE = (
    "face_shoulder_offset_x_norm",
    "face_shoulder_offset_y_norm",
)


def metric(name: str, value, available: bool = True):
    return {
        "metric_name": f"relative_{name}",
        "raw_value": value,
        "baseline_value": 0.0,
        "relative_value": value if available else None,
        "unit": "fixture",
        "available": available,
        "confidence": 0.9,
        "timestamp_ms": 0,
        "target_id": "TARGET_001",
        "failure_reason": None if available else "RAW_VALUE_UNAVAILABLE",
    }


def group(names, value, available=True):
    return {
        "available": available,
        "metrics": {
            name: metric(name, value, available) for name in names
        },
        "confidence": 0.9,
        "failure_reason": None if available else "RAW_VALUE_UNAVAILABLE",
    }


def frame(
    timestamp: int,
    *,
    value: float = 1.0,
    head: bool = True,
    shoulder: bool = True,
    nose: bool = True,
    face: bool = True,
    target_id="TARGET_001",
    frame_index=None,
):
    result = {
        "timestamp_ms": timestamp,
        "target_id": target_id,
        "head_pose": {
            "available": head,
            "yaw": metric("yaw_deg", value, head),
            "pitch": metric("pitch_deg", -value, head),
            "roll": metric("roll_deg", 0.0, head),
            "confidence": 0.9,
            "failure_reason": None if head else "RAW_VALUE_UNAVAILABLE",
        },
        "posture": {
            "available": shoulder,
            "shoulder": group(SHOULDER, value, shoulder),
            "nose_alignment": group(NOSE, value, nose),
            "face_alignment": group(FACE, value, face),
            "confidence": 0.9,
            "failure_reason": (
                None if shoulder else "RAW_VALUE_UNAVAILABLE"
            ),
        },
    }
    if frame_index is not None:
        result["frame_index"] = frame_index
    return result


class IntervalFeatureAggregatorTests(unittest.TestCase):
    def test_start_inclusive_end_exclusive_frame_filter(self):
        result = aggregate_interval_features(
            AnalysisInterval("A", 100, 300),
            [
                frame(0),
                frame(100, value=1),
                frame(200, value=3),
                frame(300, value=100),
                frame(400),
            ],
        )
        self.assertEqual(result.data_quality.total_frame_count, 2)
        self.assertEqual(result.head_pose.relative_yaw_deg.count, 2)
        self.assertEqual(result.head_pose.relative_yaw_deg.mean, 2.0)

    def test_partial_groups_remain_independent(self):
        result = aggregate_interval_features(
            AnalysisInterval("A", 0, 500),
            [
                frame(0),
                frame(100, head=False),
                frame(200, face=False),
                frame(300, head=False, face=False),
            ],
        )
        self.assertEqual(
            result.head_pose.availability.valid_frame_count,
            2,
        )
        self.assertEqual(
            result.posture.shoulder_availability.valid_frame_count,
            4,
        )
        self.assertEqual(
            result.posture.nose_alignment_availability.valid_frame_count,
            4,
        )
        self.assertEqual(
            result.posture.face_alignment_availability.valid_frame_count,
            2,
        )
        self.assertEqual(
            result.posture.relative_shoulder_tilt_deg.count,
            4,
        )
        self.assertEqual(
            result.posture.relative_face_shoulder_offset_x_norm.count,
            2,
        )
        self.assertIn("HEAD_POSE_PARTIAL", result.warnings)
        self.assertIn("FACE_ALIGNMENT_PARTIAL", result.warnings)
        self.assertNotIn("POSTURE_PARTIAL", result.warnings)

    def test_all_missing_never_creates_fake_zero_statistics(self):
        result = aggregate_interval_features(
            AnalysisInterval("A", 0, 500),
            [
                frame(
                    0,
                    head=False,
                    shoulder=False,
                    nose=False,
                    face=False,
                ),
                frame(
                    200,
                    head=False,
                    shoulder=False,
                    nose=False,
                    face=False,
                ),
            ],
        )
        self.assertEqual(result.failure_reason, "NO_VALID_HEAD_POSE_VALUES")
        self.assertIsNone(result.head_pose.relative_yaw_deg.mean)
        self.assertIsNone(
            result.posture.relative_shoulder_tilt_deg.median
        )
        self.assertEqual(result.head_pose.relative_yaw_deg.count, 0)

    def test_no_frames_has_explicit_failure_and_interval_duration(self):
        result = aggregate_interval_features(
            AnalysisInterval("A", 0, 1_000),
            [frame(2_000)],
        )
        self.assertEqual(result.failure_reason, "NO_FRAMES_IN_INTERVAL")
        self.assertEqual(result.data_quality.total_frame_count, 0)
        self.assertEqual(result.data_quality.quality_score, 0.0)
        self.assertEqual(
            result.head_pose.availability.longest_missing_duration_ms,
            1_000,
        )

    def test_target_mismatch_and_null_target_fail_interval(self):
        for target_id in ("TARGET_002", None):
            with self.subTest(target_id=target_id):
                result = aggregate_interval_features(
                    AnalysisInterval("A", 0, 500),
                    [frame(0), frame(200, target_id=target_id)],
                )
                self.assertEqual(
                    result.failure_reason,
                    "TARGET_ID_MISMATCH",
                )
                self.assertEqual(
                    result.head_pose.availability.valid_frame_count,
                    1,
                )
                self.assertIn(
                    "TARGET_ID_MISMATCH",
                    result.head_pose.availability.failure_reason_counts,
                )

    def test_duplicate_and_decreasing_timestamps_are_detected(self):
        duplicate = aggregate_interval_features(
            AnalysisInterval("A", 0, 500),
            [frame(0), frame(200), frame(200)],
        )
        self.assertEqual(duplicate.failure_reason, "DUPLICATE_TIMESTAMP")
        self.assertEqual(
            duplicate.data_quality.duplicate_timestamp_count,
            1,
        )
        decreasing = aggregate_interval_features(
            AnalysisInterval("A", 0, 500),
            [frame(0), frame(300), frame(200)],
        )
        self.assertEqual(
            decreasing.failure_reason,
            "NON_MONOTONIC_TIMESTAMP",
        )

    def test_duplicate_frame_index_is_detected(self):
        result = aggregate_interval_features(
            AnalysisInterval("A", 0, 500),
            [
                frame(0, frame_index=1),
                frame(200, frame_index=1),
            ],
        )
        self.assertEqual(result.failure_reason, "DUPLICATE_FRAME_INDEX")
        self.assertEqual(result.data_quality.duplicate_frame_count, 1)

    def test_existing_temporal_values_are_reused_without_recalculation(self):
        frames = [
            frame(0),
            frame(100, shoulder=False),
            frame(350),
        ]
        temporal = [
            {
                "timestamp_ms": 0,
                "target_id": "TARGET_001",
                "posture_temporal": {
                    "shoulder_center_velocity_norm_per_sec": 0.1,
                },
            },
            {
                "timestamp_ms": 100,
                "target_id": "TARGET_001",
                "posture_temporal": {
                    "shoulder_center_velocity_norm_per_sec": None,
                },
            },
            {
                "timestamp_ms": 350,
                "target_id": "TARGET_001",
                "posture_temporal": {
                    "shoulder_center_velocity_norm_per_sec": 0.3,
                },
            },
        ]
        result = aggregate_interval_features(
            AnalysisInterval("A", 0, 500),
            frames,
            temporal_frames=temporal,
        )
        summary = (
            result.posture.shoulder_center_velocity_norm_per_sec
        )
        self.assertIsNotNone(summary)
        self.assertEqual(summary.count, 2)
        self.assertAlmostEqual(summary.mean, 0.2)
        self.assertIsNone(result.head_pose.yaw_velocity_deg_per_sec)

    def test_non_finite_temporal_value_is_excluded(self):
        result = aggregate_interval_features(
            AnalysisInterval("A", 0, 500),
            [frame(0), frame(200)],
            temporal_frames=[
                {
                    "timestamp_ms": 0,
                    "target_id": "TARGET_001",
                    "posture_temporal": {
                        "shoulder_tilt_velocity_deg_per_sec": 1.0,
                    },
                },
                {
                    "timestamp_ms": 200,
                    "target_id": "TARGET_001",
                    "posture_temporal": {
                        "shoulder_tilt_velocity_deg_per_sec": float("nan"),
                    },
                },
            ],
        )
        summary = result.posture.shoulder_tilt_velocity_deg_per_sec
        self.assertIsNotNone(summary)
        self.assertEqual(summary.count, 1)
        self.assertEqual(summary.mean, 1.0)

    def test_events_and_strict_deterministic_serialization(self):
        result = aggregate_interval_features(
            AnalysisInterval("A", 0, 300),
            [frame(0), frame(200)],
            head_pose_events=[
                {
                    "timestamp_ms": 0,
                    "target_id": "TARGET_001",
                    "event_type": "HEAD_JUMP",
                },
                {
                    "timestamp_ms": 300,
                    "target_id": "TARGET_001",
                    "event_type": "EXCLUDED",
                },
            ],
            posture_events=[
                {
                    "timestamp_ms": 200,
                    "target_id": "TARGET_001",
                    "event_type": "POSTURE_JUMP",
                }
            ],
        )
        self.assertEqual(result.events.head_pose_jump_candidate_count, 1)
        self.assertEqual(result.events.posture_jump_candidate_count, 1)
        first = dumps_strict(result)
        self.assertEqual(first, dumps_strict(result))
        payload = json.loads(first)
        self.assertEqual(payload["interval_id"], "A")
        self.assertIsNone(
            payload["head_pose"]["yaw_velocity_deg_per_sec"]
        )

    def test_minimum_availability_is_data_quality_only(self):
        result = aggregate_interval_features(
            AnalysisInterval("A", 0, 500),
            [frame(0), frame(200, face=False)],
            config=IntervalAggregationConfig(
                minimum_availability_ratio=0.75
            ),
        )
        self.assertEqual(
            result.failure_reason,
            "INSUFFICIENT_VALID_SAMPLES",
        )
        self.assertEqual(
            result.posture.face_alignment_availability.availability_ratio,
            0.5,
        )


if __name__ == "__main__":
    unittest.main()
