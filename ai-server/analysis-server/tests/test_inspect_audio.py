"""Unit tests for the FFprobe-backed audio inspection script."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import inspect_audio  # noqa: E402


def probe_payload(**stream: object) -> str:
    values = {"codec_name": "pcm_s16le", "sample_rate": "16000", "channels": 1,
              "sample_fmt": "s16", "bits_per_sample": 16}
    values.update(stream)
    return __import__("json").dumps({"format": {"duration": "30.0"}, "streams": [values]})


class InspectAudioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.audio = Path(self.temporary_directory.name) / "sample.wav"
        self.audio.touch()
        self.ffprobe = Path(self.temporary_directory.name) / "ffprobe.exe"
        self.ffprobe.touch()

    def completed(self, stdout: str | None = None, returncode: int = 0) -> MagicMock:
        response = MagicMock(returncode=returncode, stdout=stdout or probe_payload())
        return response

    def inspect(self, stdout: str | None = None, returncode: int = 0) -> dict:
        with patch.dict(os.environ, {"FFPROBE_PATH": str(self.ffprobe)}, clear=False), patch(
            "inspect_audio.subprocess.run", return_value=self.completed(stdout, returncode)
        ) as run:
            result = inspect_audio.inspect_audio(self.audio)
        self.run = run
        return result

    def test_valid_ffprobe_json(self) -> None:
        result = self.inspect()
        self.assertTrue(result["valid"])
        self.assertEqual(result["metadata"]["sample_rate"], 16000)

    def test_file_missing(self) -> None:
        self.assertIn("FILE_NOT_FOUND", inspect_audio.inspect_audio(self.audio.with_name("missing.wav"))["errors"])

    def test_non_wav_extension(self) -> None:
        other = self.audio.with_suffix(".mp3"); other.touch()
        self.assertIn("INVALID_EXTENSION", inspect_audio.inspect_audio(other)["errors"])

    def test_invalid_sample_rate(self) -> None:
        self.assertIn("INVALID_SAMPLE_RATE", self.inspect(probe_payload(sample_rate="44100"))["errors"])

    def test_stereo_channels(self) -> None:
        self.assertIn("INVALID_CHANNELS", self.inspect(probe_payload(channels=2))["errors"])

    def test_invalid_codec(self) -> None:
        self.assertIn("INVALID_CODEC", self.inspect(probe_payload(codec_name="mp3"))["errors"])

    def test_ffprobe_execution_file_missing(self) -> None:
        with patch.dict(os.environ, {"FFPROBE_PATH": str(self.ffprobe)}, clear=False), patch(
            "inspect_audio.subprocess.run", side_effect=FileNotFoundError
        ):
            self.assertIn("FFPROBE_EXECUTION_NOT_FOUND", inspect_audio.inspect_audio(self.audio)["errors"])

    def test_nonzero_exit(self) -> None:
        self.assertIn("FFPROBE_NONZERO_EXIT", self.inspect(returncode=1)["errors"])

    def test_invalid_json(self) -> None:
        self.assertIn("FFPROBE_INVALID_JSON", self.inspect("not json")["errors"])

    def test_missing_audio_stream(self) -> None:
        self.assertIn("AUDIO_STREAM_NOT_FOUND", self.inspect('{"format": {"duration": "30"}, "streams": []}')["errors"])

    def test_short_duration_warning(self) -> None:
        self.assertIn("DURATION_BELOW_RECOMMENDED", self.inspect('{"format":{"duration":"19"},"streams":[{"codec_name":"pcm_s16le","sample_rate":"16000","channels":1,"bits_per_sample":16}]}')["warnings"])

    def test_long_duration_warning(self) -> None:
        self.assertIn("DURATION_ABOVE_RECOMMENDED", self.inspect('{"format":{"duration":"61"},"streams":[{"codec_name":"pcm_s16le","sample_rate":"16000","channels":1,"bits_per_sample":16}]}')["warnings"])

    def test_errors_make_valid_false(self) -> None:
        self.assertFalse(self.inspect(probe_payload(channels=2))["valid"])

    def test_env_path_is_used(self) -> None:
        with patch.dict(os.environ, {"FFPROBE_PATH": str(self.ffprobe)}, clear=False), patch("inspect_audio.shutil.which") as which:
            path, error = inspect_audio.find_ffprobe()
        self.assertEqual(path, self.ffprobe); self.assertIsNone(error); which.assert_not_called()

    def test_missing_env_path(self) -> None:
        with patch.dict(os.environ, {"FFPROBE_PATH": str(self.ffprobe.with_name("none.exe"))}, clear=False):
            path, error = inspect_audio.find_ffprobe()
        self.assertIsNone(path); self.assertEqual(error, "FFPROBE_PATH_INVALID")

    def test_which_is_used_without_env(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("inspect_audio.shutil.which", return_value=str(self.ffprobe)):
            path, error = inspect_audio.find_ffprobe()
        self.assertEqual(path, self.ffprobe); self.assertIsNone(error)

    def test_missing_env_and_path(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("inspect_audio.shutil.which", return_value=None):
            path, error = inspect_audio.find_ffprobe()
        self.assertIsNone(path); self.assertEqual(error, "FFPROBE_NOT_FOUND")

    def test_resolved_path_passed_to_subprocess(self) -> None:
        self.inspect()
        self.assertEqual(self.run.call_args.args[0][0], str(self.ffprobe))


if __name__ == "__main__":
    unittest.main()
