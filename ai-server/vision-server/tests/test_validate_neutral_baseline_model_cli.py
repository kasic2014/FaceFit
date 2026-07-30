from __future__ import annotations

import unittest
from unittest import mock

from app.vision.neutral_baseline_smoke import NeutralBaselineSmokeError
from scripts import validate_neutral_baseline_model as cli


class ValidateNeutralBaselineModelCliTests(unittest.TestCase):
    def test_defaults(self):
        args = cli.build_parser().parse_args(["--input", "x.mp4"])
        self.assertEqual(args.collection_start_ms, 0)
        self.assertIsNone(args.collection_end_ms)
        self.assertFalse(args.overwrite)

    def test_usage_is_two(self):
        self.assertEqual(cli.main([]), 2)

    @mock.patch.object(
        cli.NeutralBaselineSmokeValidator,
        "validate",
        return_value={"status": "completed"},
    )
    def test_success_flags(self, validate):
        self.assertEqual(
            cli.main(
                [
                    "--input",
                    "x.mp4",
                    "--collection-start-ms",
                    "200",
                    "--collection-end-ms",
                    "2200",
                    "--overwrite",
                ]
            ),
            0,
        )
        self.assertEqual(validate.call_args.kwargs["collection_start_ms"], 200)
        self.assertEqual(validate.call_args.kwargs["collection_end_ms"], 2200)
        self.assertTrue(validate.call_args.kwargs["overwrite"])

    @mock.patch.object(cli.NeutralBaselineSmokeValidator, "validate")
    def test_failure_is_one(self, validate):
        validate.side_effect = NeutralBaselineSmokeError("BAD", "failed")
        self.assertEqual(cli.main(["--input", "x.mp4"]), 1)


if __name__ == "__main__":
    unittest.main()
