from __future__ import annotations

import unittest
from dataclasses import replace

from app.vision.neutral_baseline_collector import collect_baseline_candidates
from app.vision.neutral_baseline_estimator import (
    estimate_session_neutral_baseline,
)
from app.vision.neutral_baseline_models import (
    BaselineQualityWarning,
    NeutralBaselineConfig,
    NeutralBaselineFrame,
)


def frame(
    index: int,
    *,
    yaw: float = 20.0,
    tilt: float = 2.0,
    face: bool = True,
) -> NeutralBaselineFrame:
    value = index * 0.001
    return NeutralBaselineFrame(
        timestamp_ms=index * 200,
        target_id="TARGET_001",
        target_status="TARGET_TRACKED",
        candidate_count=1,
        target_confidence=0.95,
        head_pose={
            "available": True,
            "yaw_deg": yaw,
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
            "face_alignment_available": face,
            "shoulder_tilt_deg": tilt,
            "shoulder_height_difference_norm": 0.01,
            "shoulder_center_x": 0.5 + value,
            "shoulder_center_y": 0.7,
            "shoulder_width_norm": 0.4,
            "nose_shoulder_offset_x_norm": 0.01,
            "nose_shoulder_offset_y_norm": -0.8,
            "face_shoulder_offset_x_norm": 0.02 if face else None,
            "face_shoulder_offset_y_norm": -0.7 if face else None,
            "confidence": 0.95,
        },
        posture_temporal={
            "shoulder_center_velocity_norm_per_sec": 0.005,
            "shoulder_tilt_velocity_deg_per_sec": 0.5,
            "shoulder_width_change_rate_per_sec": 0.001,
        },
        posture_jump_candidate=False,
    )


def estimate(frames, config=NeutralBaselineConfig()):
    collection = collect_baseline_candidates(
        frames,
        collection_start_ms=0,
        collection_end_ms=2_000,
        config=config,
    )
    return estimate_session_neutral_baseline(collection, config)


class NeutralBaselineEstimatorTests(unittest.TestCase):
    def test_stable_fixture_keeps_absolute_twenty_degree_yaw(self):
        baseline = estimate([frame(index) for index in range(10)])
        self.assertTrue(baseline.available)
        self.assertEqual(baseline.head_pose.yaw_deg, 20.0)
        self.assertEqual(baseline.posture.shoulder_tilt_deg, 2.0)
        self.assertTrue(baseline.posture.face_alignment_available)
        self.assertGreaterEqual(baseline.quality_score, 0.0)
        self.assertLessEqual(baseline.quality_score, 1.0)
        self.assertIn(
            BaselineQualityWarning.COLLECTION_IS_NOT_NEUTRAL_GROUND_TRUTH.value,
            baseline.warnings,
        )

    def test_median_mad_removes_outlier(self):
        frames = [frame(index, yaw=20.0) for index in range(9)]
        frames.append(frame(9, yaw=100.0))
        baseline = estimate(frames)
        self.assertEqual(baseline.head_pose.yaw_deg, 20.0)
        diagnostic = baseline.head_pose.metric_diagnostics["yaw_deg"]
        self.assertEqual(diagnostic.outlier_count, 1)
        self.assertIn(
            BaselineQualityWarning.OUTLIERS_REMOVED.value,
            baseline.warnings,
        )

    def test_zero_mad_is_safe_and_deterministic(self):
        frames = [frame(index, tilt=2.0) for index in range(9)]
        frames.append(frame(9, tilt=2.1))
        baseline = estimate(frames)
        diagnostic = baseline.posture.metric_diagnostics[
            "shoulder_tilt_deg"
        ]
        self.assertEqual(diagnostic.mad, 0.0)
        self.assertEqual(diagnostic.used_count, 9)
        self.assertEqual(baseline.posture.shoulder_tilt_deg, 2.0)

    def test_face_alignment_is_independently_partial(self):
        baseline = estimate([frame(index, face=False) for index in range(10)])
        self.assertTrue(baseline.available)
        self.assertTrue(baseline.posture.available)
        self.assertTrue(baseline.posture.nose_alignment_available)
        self.assertFalse(baseline.posture.face_alignment_available)
        self.assertIsNone(baseline.posture.face_shoulder_offset_x_norm)

    def test_insufficient_frames_does_not_insert_zero_baseline(self):
        baseline = estimate([frame(index) for index in range(3)])
        self.assertFalse(baseline.available)
        self.assertIsNone(baseline.head_pose.yaw_deg)
        self.assertIsNone(baseline.posture.shoulder_tilt_deg)
        self.assertEqual(baseline.status, "FAILED")

    def test_head_and_posture_insufficiency_remain_independent(self):
        head_limited = [frame(index) for index in range(10)]
        for index in range(4):
            payload = dict(head_limited[index].head_pose)
            payload["available"] = False
            head_limited[index] = replace(
                head_limited[index],
                head_pose=payload,
            )
        head_baseline = estimate(head_limited)
        self.assertFalse(head_baseline.available)
        self.assertFalse(head_baseline.head_pose.available)
        self.assertTrue(head_baseline.posture.available)

        posture_limited = [frame(index) for index in range(10)]
        for index in range(3):
            payload = dict(posture_limited[index].posture_raw)
            payload["available"] = False
            posture_limited[index] = replace(
                posture_limited[index],
                posture_raw=payload,
            )
        posture_baseline = estimate(posture_limited)
        self.assertFalse(posture_baseline.available)
        self.assertTrue(posture_baseline.head_pose.available)
        self.assertFalse(posture_baseline.posture.available)

    def test_configuration_rejects_invalid_thresholds(self):
        with self.assertRaises(ValueError):
            NeutralBaselineConfig(minimum_head_pose_confidence=1.1)
        with self.assertRaises(ValueError):
            NeutralBaselineConfig(aggregation_method="MEAN")


if __name__ == "__main__":
    unittest.main()
