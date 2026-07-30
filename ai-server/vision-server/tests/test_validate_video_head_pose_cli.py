from __future__ import annotations

import unittest
from unittest import mock

from app.vision.head_pose_validator import HeadPoseValidationError
from scripts import validate_video_head_pose as cli


class ValidateVideoHeadPoseCliTests(unittest.TestCase):
    def test_defaults(self):
        args=cli.build_parser().parse_args(["--input","x.mp4"])
        self.assertEqual(args.analysis_fps,5.0)
        self.assertFalse(args.overwrite)

    def test_usage_is_two(self):
        self.assertEqual(cli.main([]),2)

    @mock.patch.object(cli.HeadPoseValidator,"validate",return_value={"status":"completed"})
    def test_success_flags(self, validate):
        self.assertEqual(cli.main(["--input","x.mp4","--overwrite","--no-diagnostic-overlay"]),0)
        self.assertTrue(validate.call_args.kwargs["overwrite"])
        self.assertFalse(validate.call_args.kwargs["generate_overlay"])

    @mock.patch.object(cli.HeadPoseValidator,"validate")
    def test_failure_is_one(self, validate):
        validate.side_effect=HeadPoseValidationError("BAD","failed")
        self.assertEqual(cli.main(["--input","x.mp4"]),1)


if __name__ == "__main__":
    unittest.main()
