from __future__ import annotations

import math
import unittest

from app.vision.temporal_landmark_metrics import *


class TemporalLandmarkMetricsTests(unittest.TestCase):
    def test_sanitize_rejects_non_finite_bool_and_text(self):
        for value in (math.nan, math.inf, -math.inf, True, "1", None):
            self.assertIsNone(sanitize_metric_number(value))
        self.assertEqual(sanitize_metric_number(2), 2.0)

    def test_point_displacement_and_missing(self):
        self.assertEqual(calculate_point_displacement({"x": 0, "y": 0}, {"x": 3, "y": 4}), 5)
        self.assertIsNone(calculate_point_displacement(None, {"x": 1, "y": 1}))

    def test_center_and_width(self):
        left, right = {"x": .2, "y": .4}, {"x": .6, "y": .4}
        self.assertEqual(calculate_center_point(left, right), {"x": .4, "y": .4})
        self.assertAlmostEqual(calculate_shoulder_width(left, right), .4)

    def test_frame_displacements_preserve_missing(self):
        values = [{"x": 0, "y": 0}, {"x": 1, "y": 0}, None, {"x": 2, "y": 0}]
        self.assertEqual(calculate_frame_to_frame_displacement(values), [None, 1, None, None])

    def test_median_and_mad_ignore_invalid(self):
        self.assertEqual(calculate_series_median([1, 2, 100, None]), 2)
        self.assertEqual(calculate_series_mad([1, 2, 100, None], 2), 1)
        self.assertIsNone(calculate_series_median([]))

    def test_detection_and_missing_segments(self):
        states, timestamps = [True, True, False, False, True], [0, 200, 400, 600, 800]
        self.assertEqual(len(build_detection_segments(states, timestamps)), 2)
        missing = build_missing_segments(states, timestamps)
        self.assertEqual(missing[0]["frame_count"], 2)
        self.assertAlmostEqual(calculate_longest_missing_duration(states, timestamps), .4)
        self.assertEqual(calculate_detection_ratio(states), .6)

    def test_segments_reject_length_and_timestamp_errors(self):
        with self.assertRaises(ValueError):
            build_missing_segments([True], [0, 1])
        with self.assertRaises(ValueError):
            build_missing_segments([True, False], [0, 0])

    def test_jump_uses_robust_distribution_and_candidate_schema(self):
        values = [{"x": x, "y": 0} for x in (0, .01, .02, .03, .04, .5)]
        result = detect_coordinate_jump_candidates(values, [0, 200, 400, 600, 800, 1000], "nose")
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(result["events"][0]["status"], "candidate")
        self.assertEqual(result["events"][0]["landmark_name"], "nose")

    def test_jump_insufficient_and_zero_motion_are_explicit(self):
        few = detect_coordinate_jump_candidates([{"x": 0, "y": 0}] * 3, [0, 1, 2], "nose")
        self.assertEqual(few["method"], "insufficient_data")
        still = detect_coordinate_jump_candidates([{"x": 0, "y": 0}] * 6, list(range(6)), "nose")
        self.assertEqual(still["method"], "zero_motion_insufficient_variation")


if __name__ == "__main__":
    unittest.main()
