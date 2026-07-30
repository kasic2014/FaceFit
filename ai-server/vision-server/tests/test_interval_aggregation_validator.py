from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.vision.interval_aggregation_validator import (
    IntervalAggregationValidationError,
    default_smoke_intervals,
    load_strict_jsonl,
    parse_interval_definitions,
)


class IntervalAggregationValidatorTests(unittest.TestCase):
    def test_default_intervals_touch_without_overlap(self):
        intervals = default_smoke_intervals(38_977)
        self.assertEqual(len(intervals), 4)
        self.assertEqual(intervals[0].start_timestamp_ms, 0)
        self.assertEqual(intervals[-1].end_timestamp_ms, 38_977)
        self.assertEqual(intervals[0].interval_type, "OTHER")
        for previous, current in zip(intervals, intervals[1:]):
            self.assertEqual(
                previous.end_timestamp_ms,
                current.start_timestamp_ms,
            )

    def test_strict_jsonl_rejects_nan_and_blank_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "x.jsonl"
            path.write_text('{"x":NaN}\n', encoding="utf-8")
            with self.assertRaises(IntervalAggregationValidationError):
                load_strict_jsonl(path)
            path.write_text('{"x":1}\n\n', encoding="utf-8")
            with self.assertRaises(IntervalAggregationValidationError):
                load_strict_jsonl(path)

    def test_parse_interval_definitions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "intervals.json"
            path.write_text(
                (
                    '{"intervals":[{"interval_id":"A",'
                    '"start_timestamp_ms":0,"end_timestamp_ms":10,'
                    '"interval_type":"ANSWER"}]}'
                ),
                encoding="utf-8",
            )
            result = parse_interval_definitions(path)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].interval_id, "A")


if __name__ == "__main__":
    unittest.main()
