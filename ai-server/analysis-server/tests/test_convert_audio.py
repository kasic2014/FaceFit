"""Mock-only unit tests for the audio conversion command."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import convert_audio  # noqa: E402


class ConvertAudioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.input_file = self.directory / "recording.m4a"
        self.input_file.touch()
        self.output_file = self.directory / "speech.wav"
        self.ffmpeg = self.directory / "ffmpeg.exe"
        self.ffmpeg.touch()

    def run_conversion(self, *, overwrite: bool = False, returncode: int = 0, create_output: bool = True, inspection: dict | None = None) -> tuple[dict, MagicMock]:
        def fake_run(*args: object, **kwargs: object) -> MagicMock:
            if create_output:
                self.output_file.touch()
            return MagicMock(returncode=returncode, stderr="")

        valid_inspection = inspection or {"valid": True, "errors": [], "warnings": []}
        with patch.dict(os.environ, {"FFMPEG_PATH": str(self.ffmpeg)}, clear=False), patch(
            "convert_audio.subprocess.run", side_effect=fake_run
        ) as run, patch("convert_audio.inspect_audio", return_value=valid_inspection):
            result = convert_audio.convert_audio(self.input_file, self.output_file, overwrite)
        return result, run

    def test_normal_conversion(self) -> None:
        result, _ = self.run_conversion()
        self.assertTrue(result["success"])

    def test_input_file_missing(self) -> None:
        result = convert_audio.convert_audio(self.directory / "missing.mp3", self.output_file)
        self.assertIn("INPUT_FILE_NOT_FOUND", result["errors"])

    def test_input_is_directory(self) -> None:
        result = convert_audio.convert_audio(self.directory, self.output_file)
        self.assertIn("INPUT_NOT_FILE", result["errors"])

    def test_unsupported_input_extension(self) -> None:
        source = self.directory / "recording.txt"; source.touch()
        self.assertIn("UNSUPPORTED_INPUT_FORMAT", convert_audio.convert_audio(source, self.output_file)["errors"])

    def test_invalid_output_extension(self) -> None:
        self.assertIn("INVALID_OUTPUT_EXTENSION", convert_audio.convert_audio(self.input_file, self.directory / "out.mp3")["errors"])

    def test_identical_paths(self) -> None:
        same = self.directory / "same.wav"; same.touch()
        self.assertIn("INPUT_OUTPUT_SAME_PATH", convert_audio.convert_audio(same, same)["errors"])

    def test_existing_output_without_overwrite(self) -> None:
        self.output_file.touch()
        self.assertIn("OUTPUT_ALREADY_EXISTS", convert_audio.convert_audio(self.input_file, self.output_file)["errors"])

    def test_overwrite_uses_y_flag(self) -> None:
        self.output_file.touch()
        result, run = self.run_conversion(overwrite=True)
        self.assertTrue(result["success"]); self.assertIn("-y", run.call_args.args[0])

    def test_env_path_used(self) -> None:
        with patch.dict(os.environ, {"FFMPEG_PATH": str(self.ffmpeg)}, clear=False), patch("convert_audio.shutil.which") as which:
            path, error = convert_audio.find_ffmpeg()
        self.assertEqual(path, self.ffmpeg); self.assertIsNone(error); which.assert_not_called()

    def test_invalid_env_path(self) -> None:
        with patch.dict(os.environ, {"FFMPEG_PATH": str(self.directory / "no.exe")}, clear=False):
            path, error = convert_audio.find_ffmpeg()
        self.assertIsNone(path); self.assertEqual(error, "FFMPEG_PATH_INVALID")

    def test_which_used_without_env(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("convert_audio.shutil.which", return_value=str(self.ffmpeg)):
            path, error = convert_audio.find_ffmpeg()
        self.assertEqual(path, self.ffmpeg); self.assertIsNone(error)

    def test_ffmpeg_not_found(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("convert_audio.shutil.which", return_value=None):
            path, error = convert_audio.find_ffmpeg()
        self.assertIsNone(path); self.assertEqual(error, "FFMPEG_NOT_FOUND")

    def test_timeout(self) -> None:
        with patch.dict(os.environ, {"FFMPEG_PATH": str(self.ffmpeg)}, clear=False), patch("convert_audio.subprocess.run", side_effect=__import__("subprocess").TimeoutExpired("ffmpeg", 1)):
            result = convert_audio.convert_audio(self.input_file, self.output_file)
        self.assertIn("FFMPEG_TIMEOUT", result["errors"])

    def test_nonzero_exit(self) -> None:
        result, _ = self.run_conversion(returncode=1, create_output=False)
        self.assertIn("FFMPEG_NONZERO_EXIT", result["errors"])

    def test_output_not_created(self) -> None:
        result, _ = self.run_conversion(create_output=False)
        self.assertIn("OUTPUT_NOT_CREATED", result["errors"])

    def test_inspection_failure(self) -> None:
        result, _ = self.run_conversion(inspection={"valid": False, "errors": ["INVALID_CODEC"], "warnings": []})
        self.assertIn("OUTPUT_VALIDATION_FAILED", result["errors"])

    def test_ffmpeg_contract_options(self) -> None:
        _, run = self.run_conversion()
        command = run.call_args.args[0]
        self.assertIn("pcm_s16le", command); self.assertIn("16000", command); self.assertIn("-ac", command)
        self.assertEqual(command[command.index("-ac") + 1], "1")

    def test_shell_true_is_not_used(self) -> None:
        _, run = self.run_conversion()
        self.assertNotIn("shell", run.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
