from __future__ import annotations

import unittest

from app.vision.interval_feature_aggregator import (
    IntervalAggregationError,
    validate_analysis_intervals,
)
from app.vision.interval_models import (
    AnalysisInterval,
    IntervalAggregationConfig,
)


class IntervalModelsTests(unittest.TestCase):
    def test_valid_interval_and_boundaries(self):
        interval = AnalysisInterval("ANSWER_001", 100, 300)
        self.assertEqual(interval.duration_ms, 200)
        self.assertTrue(interval.contains(100))
        self.assertTrue(interval.contains(299))
        self.assertFalse(interval.contains(99))
        self.assertFalse(interval.contains(300))
        self.assertFalse(interval.contains(301))

    def test_invalid_timestamp_ranges_and_id(self):
        invalid = (
            ("", 0, 1),
            ("A", -1, 1),
            ("A", 1, 1),
            ("A", 2, 1),
        )
        for interval_id, start, end in invalid:
            with self.subTest(interval_id=interval_id, start=start, end=end):
                with self.assertRaises(ValueError):
                    AnalysisInterval(interval_id, start, end)

    def test_invalid_type_and_boolean_timestamp(self):
        with self.assertRaises(ValueError):
            AnalysisInterval("A", True, 10)
        with self.assertRaises(ValueError):
            AnalysisInterval("A", 0, 10, "INVALID")

    def test_duplicate_interval_id_is_rejected(self):
        intervals = (
            AnalysisInterval("A", 0, 10),
            AnalysisInterval("A", 10, 20),
        )
        with self.assertRaises(IntervalAggregationError) as context:
            validate_analysis_intervals(intervals)
        self.assertEqual(context.exception.code, "DUPLICATE_INTERVAL_ID")

    def test_overlap_is_rejected_but_touching_boundaries_are_valid(self):
        validate_analysis_intervals(
            (
                AnalysisInterval("A", 0, 10),
                AnalysisInterval("B", 10, 20),
            )
        )
        with self.assertRaises(IntervalAggregationError) as context:
            validate_analysis_intervals(
                (
                    AnalysisInterval("A", 0, 11),
                    AnalysisInterval("B", 10, 20),
                )
            )
        self.assertEqual(context.exception.code, "OVERLAPPING_INTERVAL")

    def test_overlap_can_only_be_enabled_explicitly(self):
        result = validate_analysis_intervals(
            (
                AnalysisInterval("A", 0, 11),
                AnalysisInterval("B", 10, 20),
            ),
            IntervalAggregationConfig(reject_overlapping_intervals=False),
        )
        self.assertEqual(len(result), 2)

    def test_configuration_contract(self):
        with self.assertRaises(ValueError):
            IntervalAggregationConfig(interval_end_exclusive=False)
        with self.assertRaises(ValueError):
            IntervalAggregationConfig(minimum_valid_sample_count=0)
        with self.assertRaises(ValueError):
            IntervalAggregationConfig(minimum_availability_ratio=1.1)


if __name__ == "__main__":
    unittest.main()
