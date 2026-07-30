from __future__ import annotations

import unittest
from unittest import mock

from app.vision.interval_aggregation_validator import (
    IntervalAggregationValidationError,
)
from scripts import validate_interval_aggregation as cli


class ValidateIntervalAggregationCliTests(unittest.TestCase):
    def test_defaults(self):
        args = cli.build_parser().parse_args(["--input", "x.mp4"])
        self.assertIsNone(args.intervals_json)
        self.assertFalse(args.overwrite)

    def test_usage_is_two(self):
        self.assertEqual(cli.main([]), 2)

    @mock.patch.object(
        cli.IntervalAggregationValidator,
        "validate",
        return_value={"status": "completed"},
    )
    def test_success_forwards_overwrite(self, validate):
        self.assertEqual(
            cli.main(["--input", "x.mp4", "--overwrite"]),
            0,
        )
        self.assertTrue(validate.call_args.kwargs["overwrite"])

    @mock.patch.object(cli.IntervalAggregationValidator, "validate")
    def test_failure_is_one(self, validate):
        validate.side_effect = IntervalAggregationValidationError(
            "BAD",
            "failed",
        )
        self.assertEqual(cli.main(["--input", "x.mp4"]), 1)


if __name__ == "__main__":
    unittest.main()
