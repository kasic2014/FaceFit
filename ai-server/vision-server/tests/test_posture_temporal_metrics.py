from __future__ import annotations

import unittest

from app.vision.posture_raw_models import PostureRawConfiguration
from app.vision.posture_temporal_metrics import (
    calculate_numeric_summary,
    calculate_posture_temporal_results,
    detect_posture_jump_candidates,
)


def row(timestamp, available=True, x=0.5, tilt=0.0, width=0.4):
    return {
        "timestamp_ms": timestamp,
        "target_id": "TARGET_001",
        "posture_raw": {
            "available": available,
            "shoulder_center_x": x if available else None,
            "shoulder_center_y": 0.7 if available else None,
            "shoulder_tilt_deg": tilt if available else None,
            "shoulder_width_norm": width if available else None,
            "nose_alignment_available": available,
            "face_alignment_available": available,
            "nose_shoulder_offset_x_norm": x - 0.5 if available else None,
            "nose_shoulder_offset_y_norm": -1.0 if available else None,
            "face_shoulder_offset_x_norm": x - 0.5 if available else None,
            "face_shoulder_offset_y_norm": -0.9 if available else None,
        },
    }


class PostureTemporalMetricsTests(unittest.TestCase):
    def test_summary_and_empty(self):
        summary = calculate_numeric_summary([1, 2, 3, None])
        self.assertEqual(summary["median"], 2)
        self.assertAlmostEqual(summary["standard_deviation"], 0.81649658)
        self.assertIsNone(calculate_numeric_summary([])["mean"])

    def test_uses_real_timestamp_difference(self):
        rows = [row(0), row(500, x=0.6, tilt=2.0, width=0.42)]
        result = calculate_posture_temporal_results(rows)[1]
        self.assertEqual(result.delta_time_seconds, 0.5)
        self.assertAlmostEqual(result.shoulder_center_displacement_norm, 0.1)
        self.assertAlmostEqual(result.shoulder_center_velocity_norm_per_sec, 0.2)
        self.assertAlmostEqual(result.shoulder_tilt_velocity_deg_per_sec, 4.0)
        self.assertAlmostEqual(result.shoulder_width_change_rate_per_sec, 0.04)

    def test_missing_frame_resets_delta(self):
        results = calculate_posture_temporal_results(
            [row(0), row(200, available=False), row(400, x=0.9)]
        )
        self.assertIsNone(results[1].delta_time_seconds)
        self.assertIsNone(results[2].delta_time_seconds)
        self.assertIsNone(results[2].shoulder_center_displacement_norm)

    def test_non_positive_timestamp_delta_is_null(self):
        results = calculate_posture_temporal_results([row(100), row(100, x=0.6)])
        self.assertIsNone(results[1].delta_time_seconds)

    def test_face_delta_does_not_bridge_face_missing(self):
        rows = [row(0), row(200), row(400)]
        rows[1]["posture_raw"]["face_alignment_available"] = False
        rows[1]["posture_raw"]["face_shoulder_offset_x_norm"] = None
        rows[1]["posture_raw"]["face_shoulder_offset_y_norm"] = None
        results = calculate_posture_temporal_results(rows)
        self.assertIsNone(results[1].face_offset_x_delta_norm)
        self.assertIsNone(results[2].face_offset_x_delta_norm)
        self.assertIsNotNone(results[2].nose_offset_x_delta_norm)

    def test_large_change_is_diagnostic_candidate(self):
        rows = [
            row(index * 200, tilt=value)
            for index, value in enumerate((0, 0.1, 0.2, 0.3, 0.4, 10, 10.1))
        ]
        temporal = calculate_posture_temporal_results(rows)
        for item, result in zip(rows, temporal):
            item["posture_temporal"] = result.to_dict()
        events, diagnostics = detect_posture_jump_candidates(
            rows,
            PostureRawConfiguration(minimum_jump_tilt_deg=1.0),
        )
        tilt_events = [
            event
            for event in events
            if event["event_type"] == "SHOULDER_TILT_JUMP_CANDIDATE"
        ]
        self.assertEqual(len(tilt_events), 1)
        self.assertEqual(tilt_events[0]["details"]["status"], "candidate")
        self.assertIn("threshold", diagnostics["shoulder_tilt_deg"])


if __name__ == "__main__":
    unittest.main()
