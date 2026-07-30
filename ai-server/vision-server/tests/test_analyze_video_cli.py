from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


VISION_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(VISION_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(VISION_SERVER_ROOT))

from app.vision.video_analyzer import VideoAnalysisError
from scripts import analyze_video as cli


class FakeAnalyzer:
    def __init__(self, result=None, error=None) -> None:
        self.result = result
        self.error = error
        self.calls = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.closed = True

    def analyze(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error:
            raise self.error
        return self.result


class AnalyzeVideoCliTests(unittest.TestCase):
    def test_completed_exit_zero(self) -> None:
        fake = FakeAnalyzer({"status": "completed"})
        with (
            mock.patch.object(cli, "VideoAnalyzer", return_value=fake),
            redirect_stdout(io.StringIO()),
        ):
            code = cli.main(["--input", "video.mp4"])
        self.assertEqual(code, 0)
        self.assertTrue(fake.closed)

    def test_warning_and_partial_are_success(self) -> None:
        for status in ("completed_with_warnings", "partial_completed"):
            fake = FakeAnalyzer({"status": status})
            with (
                self.subTest(status=status),
                mock.patch.object(cli, "VideoAnalyzer", return_value=fake),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(cli.main(["--input", "video.mp4"]), 0)

    def test_analysis_failure_exit_one(self) -> None:
        fake = FakeAnalyzer(error=VideoAnalysisError("FAIL", "failed"))
        with (
            mock.patch.object(cli, "VideoAnalyzer", return_value=fake),
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(cli.main(["--input", "video.mp4"]), 1)

    def test_usage_error_exit_two(self) -> None:
        with redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main([]), 2)
            self.assertEqual(
                cli.main(
                    [
                        "--input",
                        "video.mp4",
                        "--no-overlay",
                        "--require-overlay",
                    ]
                ),
                2,
            )

    def test_options_forwarded(self) -> None:
        fake = FakeAnalyzer({"status": "completed"})
        with (
            mock.patch.object(cli, "VideoAnalyzer", return_value=fake),
            redirect_stdout(io.StringIO()),
        ):
            cli.main(
                [
                    "--input",
                    "video.mp4",
                    "--analysis-fps",
                    "7",
                    "--output-root",
                    "out",
                    "--overwrite",
                    "--save-all-sampled-frames",
                ]
            )
        args, kwargs = fake.calls[0]
        self.assertEqual(args, ("video.mp4", 7.0))
        self.assertEqual(kwargs["output_root"], "out")
        self.assertTrue(kwargs["overwrite"])
        self.assertTrue(kwargs["save_all_sampled_frames"])


if __name__ == "__main__":
    unittest.main()
