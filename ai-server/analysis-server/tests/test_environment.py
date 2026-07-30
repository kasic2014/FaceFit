"""Tests for the analysis server's minimum filesystem environment."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ANALYSIS_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(ANALYSIS_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_SERVER_ROOT))

from app.core.config import APP_PATHS  # noqa: E402


class EnvironmentTests(unittest.TestCase):
    def test_analysis_server_root_exists(self) -> None:
        self.assertTrue(APP_PATHS.root_dir.is_dir())
        self.assertEqual(APP_PATHS.root_dir, ANALYSIS_SERVER_ROOT)

    def test_audio_input_directory_exists(self) -> None:
        self.assertTrue(APP_PATHS.audio_input_dir.is_dir())

    def test_video_input_directory_exists(self) -> None:
        self.assertTrue(APP_PATHS.video_input_dir.is_dir())

    def test_output_directory_exists(self) -> None:
        self.assertTrue(APP_PATHS.output_dir.is_dir())

    def test_temp_directory_exists(self) -> None:
        self.assertTrue(APP_PATHS.temp_dir.is_dir())

    def test_log_directory_exists(self) -> None:
        self.assertTrue(APP_PATHS.log_dir.is_dir())

    def test_all_directories(self) -> None:
        expected = (
            APP_PATHS.root_dir,
            APP_PATHS.audio_input_dir,
            APP_PATHS.video_input_dir,
            APP_PATHS.output_dir,
            APP_PATHS.temp_dir,
            APP_PATHS.log_dir,
        )
        self.assertEqual(APP_PATHS.all_directories(), expected)

    def test_all_managed_directories_are_writable(self) -> None:
        for directory in APP_PATHS.all_directories():
            with self.subTest(directory=directory):
                test_file = directory / ".environment-write-test.tmp"
                created = False
                try:
                    with test_file.open("x", encoding="utf-8") as stream:
                        stream.write("unittest write test\n")
                    created = True
                    self.assertTrue(test_file.is_file())
                finally:
                    if created:
                        test_file.unlink(missing_ok=True)
                self.assertFalse(test_file.exists())

    def test_python_version_is_3_12(self) -> None:
        self.assertEqual(sys.version_info[:2], (3, 12))


if __name__ == "__main__":
    unittest.main()
