from __future__ import annotations

import unittest

from app.vision.interval_models import AnalysisInterval
from app.vision.missing_duration_calculator import (
    calculate_longest_missing_duration_ms,
)


class MissingDurationCalculatorTests(unittest.TestCase):
    def setUp(self):
        self.interval = AnalysisInterval("A", 0, 1_000)

    def test_middle_missing_uses_irregular_timestamp_differences(self):
        duration = calculate_longest_missing_duration_ms(
            self.interval,
            [0, 100, 350, 900],
            [True, False, False, True],
        )
        self.assertEqual(duration, 800)

    def test_leading_missing_starts_at_interval_boundary(self):
        duration = calculate_longest_missing_duration_ms(
            self.interval,
            [100, 500, 900],
            [False, True, True],
        )
        self.assertEqual(duration, 500)

    def test_trailing_missing_ends_at_interval_boundary(self):
        duration = calculate_longest_missing_duration_ms(
            self.interval,
            [0, 600, 800],
            [True, False, False],
        )
        self.assertEqual(duration, 400)

    def test_whole_interval_missing(self):
        duration = calculate_longest_missing_duration_ms(
            self.interval,
            [100, 400, 900],
            [False, False, False],
        )
        self.assertEqual(duration, 1_000)

    def test_no_frames_is_whole_interval_unobserved(self):
        self.assertEqual(
            calculate_longest_missing_duration_ms(
                self.interval,
                [],
                [],
            ),
            1_000,
        )


if __name__ == "__main__":
    unittest.main()
