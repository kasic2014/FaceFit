from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


VISION_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(VISION_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(VISION_SERVER_ROOT))

from app.vision import video_result_writer as writer


class VideoResultWriterTests(unittest.TestCase):
    def test_jsonl_is_strict_and_one_frame_per_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frames.jsonl"
            with writer.AtomicJsonlWriter(path) as output:
                output.write({"timestamp_ms": 0, "text": "한글"})
                output.write({"timestamp_ms": 200, "value": None})
            lines = path.read_text("utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0])["text"], "한글")
            self.assertIsNone(json.loads(lines[1])["value"])

    def test_nan_is_rejected_and_final_file_absent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frames.jsonl"
            with self.assertRaises(writer.VideoResultWriteError):
                with writer.AtomicJsonlWriter(path) as output:
                    output.write({"timestamp_ms": 0, "value": float("nan")})
            self.assertFalse(path.exists())
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_timestamp_must_increase(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frames.jsonl"
            with self.assertRaises(writer.VideoResultWriteError) as raised:
                with writer.AtomicJsonlWriter(path) as output:
                    output.write({"timestamp_ms": 100})
                    output.write({"timestamp_ms": 100})
            self.assertEqual(raised.exception.code, "FRAME_TIMESTAMP_NOT_INCREASING")

    def test_atomic_replace_is_used(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frames.jsonl"
            real_replace = os.replace
            with mock.patch.object(
                writer.os, "replace", wraps=real_replace
            ) as replace:
                with writer.AtomicJsonlWriter(path) as output:
                    output.write({"timestamp_ms": 0})
            replace.assert_called_once()

    def test_analysis_json_strict_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "analysis.json"
            writer.write_video_analysis_json(
                {"status": "completed", "ratio": None},
                path,
            )
            self.assertEqual(json.loads(path.read_text("utf-8"))["ratio"], None)


if __name__ == "__main__":
    unittest.main()
