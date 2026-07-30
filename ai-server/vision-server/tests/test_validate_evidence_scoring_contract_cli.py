from __future__ import annotations

import unittest
from unittest import mock

from app.vision.evidence_scoring_contract_validator import (
    EvidenceScoringContractValidationError,
)
from scripts import validate_evidence_scoring_contract as cli


class ValidateEvidenceScoringContractCliTests(unittest.TestCase):
    def test_defaults_are_fixture_only(self):
        args = cli.build_parser().parse_args([])
        self.assertTrue(args.input.endswith("interval_aggregates.jsonl"))
        self.assertIn("fixtures", args.fixture_directory)
        self.assertFalse(args.overwrite)

    @mock.patch.object(
        cli.EvidenceScoringContractValidator,
        "validate",
        return_value={"status": "completed"},
    )
    def test_success_forwards_paths_and_overwrite(self, validate):
        self.assertEqual(
            cli.main(
                [
                    "--input",
                    "interval_aggregates.jsonl",
                    "--fixture-directory",
                    "fixtures",
                    "--output-root",
                    "output",
                    "--overwrite",
                ]
            ),
            0,
        )
        self.assertTrue(validate.call_args.kwargs["overwrite"])
        self.assertEqual(
            validate.call_args.kwargs["fixture_directory"],
            "fixtures",
        )

    @mock.patch.object(cli.EvidenceScoringContractValidator, "validate")
    def test_validation_failure_returns_one(self, validate):
        validate.side_effect = EvidenceScoringContractValidationError(
            "BAD",
            "failed",
        )
        self.assertEqual(cli.main([]), 1)


if __name__ == "__main__":
    unittest.main()
