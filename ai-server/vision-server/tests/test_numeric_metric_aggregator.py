from __future__ import annotations

import math
import unittest

from app.vision.interval_models import IntervalAggregationConfig
from app.vision.numeric_metric_aggregator import (
    aggregate_numeric_metric,
    linear_percentile,
)


class NumericMetricAggregatorTests(unittest.TestCase):
    def test_linear_percentile_contract(self):
        values = [1.0, 2.0, 3.0, 4.0]
        self.assertAlmostEqual(linear_percentile(values, 5), 1.15)
        self.assertAlmostEqual(linear_percentile(values, 25), 1.75)
        self.assertAlmostEqual(linear_percentile(values, 75), 3.25)
        self.assertAlmostEqual(linear_percentile(values, 95), 3.85)

    def test_all_common_and_absolute_statistics(self):
        summary = aggregate_numeric_metric([-4, -1, 2, 3])
        self.assertTrue(summary.available)
        self.assertEqual(summary.count, 4)
        self.assertEqual(summary.minimum, -4)
        self.assertEqual(summary.maximum, 3)
        self.assertEqual(summary.mean, 0)
        self.assertEqual(summary.median, 0.5)
        self.assertEqual(summary.mad, 2.0)
        self.assertAlmostEqual(
            summary.standard_deviation,
            math.sqrt(7.5),
        )
        self.assertAlmostEqual(summary.p05, -3.55)
        self.assertAlmostEqual(summary.p25, -1.75)
        self.assertAlmostEqual(summary.p75, 2.25)
        self.assertAlmostEqual(summary.p95, 2.85)
        self.assertEqual(summary.absolute_mean, 2.5)
        self.assertEqual(summary.absolute_median, 2.5)
        self.assertAlmostEqual(summary.absolute_p95, 3.85)

    def test_zero_values_have_null_statistics(self):
        summary = aggregate_numeric_metric([None, None])
        self.assertFalse(summary.available)
        self.assertEqual(summary.count, 0)
        self.assertIsNone(summary.mean)
        self.assertIsNone(summary.standard_deviation)
        self.assertEqual(summary.failure_reason, "NO_VALID_VALUES")

    def test_single_value_standard_deviation_is_zero(self):
        summary = aggregate_numeric_metric([7])
        self.assertTrue(summary.available)
        self.assertEqual(summary.count, 1)
        self.assertEqual(summary.standard_deviation, 0.0)
        self.assertEqual(summary.p05, 7.0)
        self.assertEqual(summary.absolute_p95, 7.0)

    def test_two_values_and_minimum_sample_count(self):
        summary = aggregate_numeric_metric(
            [1, 3],
            IntervalAggregationConfig(minimum_valid_sample_count=3),
        )
        self.assertFalse(summary.available)
        self.assertEqual(summary.count, 2)
        self.assertEqual(summary.mean, 2.0)
        self.assertEqual(summary.failure_reason, "INSUFFICIENT_VALID_SAMPLES")

    def test_non_finite_values_are_never_emitted(self):
        summary = aggregate_numeric_metric(
            [float("nan"), float("inf"), "bad"]
        )
        self.assertFalse(summary.available)
        self.assertEqual(summary.count, 0)
        self.assertEqual(summary.failure_reason, "NON_FINITE_VALUE")


if __name__ == "__main__":
    unittest.main()
