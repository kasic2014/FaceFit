from __future__ import annotations

import unittest
from unittest import mock

from scripts import validate_motion_video_landmarks as cli
from app.vision.temporal_landmark_validator import TemporalValidationError


class ValidateMotionVideoLandmarksCliTests(unittest.TestCase):
    def test_parser_defaults_to_five_fps(self):
        args = cli.build_parser().parse_args(["--input", "x.mp4"])
        self.assertEqual(args.analysis_fps, 5.0)
        self.assertFalse(args.overwrite)

    def test_usage_error_is_two(self):
        self.assertEqual(cli.main([]), 2)

    @mock.patch.object(cli.TemporalLandmarkValidator, "validate", return_value={"status": "completed"})
    def test_completed_is_zero(self, validate):
        self.assertEqual(cli.main(["--input", "x.mp4"]), 0)
        self.assertEqual(validate.call_args.args[1], 5.0)

    @mock.patch.object(cli.TemporalLandmarkValidator, "validate")
    def test_operational_error_is_one(self, validate):
        validate.side_effect = TemporalValidationError("BAD", "failed")
        self.assertEqual(cli.main(["--input", "x.mp4"]), 1)

    @mock.patch.object(cli.TemporalLandmarkValidator, "validate", return_value={"status": "completed"})
    def test_flags_are_forwarded(self, validate):
        result = cli.main(["--input", "x.mp4", "--reuse-video-analysis", "--overwrite", "--no-diagnostic-overlay"])
        self.assertEqual(result, 0)
        kwargs = validate.call_args.kwargs
        self.assertTrue(kwargs["reuse_video_analysis"])
        self.assertTrue(kwargs["overwrite"])
        self.assertFalse(kwargs["generate_diagnostic_overlay"])


if __name__ == "__main__":
    unittest.main()
