from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import cv2
import numpy as np


VISION_SERVER_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = VISION_SERVER_ROOT.parents[1]
if str(VISION_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(VISION_SERVER_ROOT))

from app.vision.static_image_analyzer import StaticImageAnalysisError
from scripts import analyze_static_image as cli


REQUIREMENTS_SHA256 = "8a18c111dc4e4d93e8e1c0e28615298a32819d78d78996303f1171b3fad6e925"
REQUIREMENTS_LOCK_SHA256 = "d05e1d8c452a61bf2638aace9bc320278eee5716ef15f8697d6c75ce8a2bc091"
FACE_MODEL_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"
POSE_MODEL_SHA256 = "4eaa5eb7a98365221087693fcc286334cf0858e2eb6e15b506aa4a7ecdcec4ad"
MANIFEST_SHA256 = "0e4b8be16652ebde7531090a27ca5ef5131e2939c6004cbd22f8a311ff581695"
SETUP_REPORT_SHA256 = "8d30234a346d6d2213c33ad3771a8932bf78760c2d61acf9f912da3bb1819690"
LOADING_REPORT_SHA256 = "ff5668185a41973c26e7ad7301302a6ec6a7f88b4b67c0aac98589feef9ae405"
ANALYSIS_TREE_SHA256 = "c56f1147556369f2ebdc50bbe682741d8a26d83aba8d5cd0e01c10d195692ecf"


class FakeAnalyzer:
    def __init__(self, result=None, error=None) -> None:
        self.result = result
        self.error = error
        self.calls = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.closed = True

    def analyze(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error:
            raise self.error
        return self.result


def tree_digest() -> str:
    analysis = WORKSPACE_ROOT / "ai-server" / "analysis-server"
    files = [
        path
        for path in analysis.rglob("*")
        if path.is_file()
        and ".venv" not in path.parts
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
        and not path.is_relative_to(
            analysis / "data" / "output" / "stt_preprocessing"
        )
        and not path.is_relative_to(
            analysis / "data" / "output" / "stt_transcription"
        )
        and not path.is_relative_to(
            analysis / "data" / "output" / "speech_characteristics"
        )
        and not path.is_relative_to(
            analysis / "data" / "output" / "analysis_api"
        )
        and not path.is_relative_to(
            analysis / "data" / "output" / "analysis_api_validation"
        )
        and not path.is_relative_to(
            analysis / "data" / "output" / "analysis_docker_validation"
        )
    ]
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.as_posix().casefold()):
        data = path.read_bytes()
        digest.update(path.relative_to(WORKSPACE_ROOT).as_posix().encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(data).digest())
        digest.update(b"\0")
    return digest.hexdigest()


class AnalyzeStaticImageCliTests(unittest.TestCase):
    def test_normal_no_detection_exit_zero(self) -> None:
        fake = FakeAnalyzer({"status": "completed_with_no_detections"})
        with (
            mock.patch.object(cli, "StaticImageAnalyzer", return_value=fake),
            redirect_stdout(io.StringIO()),
        ):
            code = cli.main(["--input", "blank.png"])
        self.assertEqual(code, 0)
        self.assertTrue(fake.closed)

    def test_completed_exit_zero(self) -> None:
        fake = FakeAnalyzer({"status": "completed"})
        with (
            mock.patch.object(cli, "StaticImageAnalyzer", return_value=fake),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(cli.main(["--input", "person.png"]), 0)

    def test_partial_analysis_exit_one(self) -> None:
        fake = FakeAnalyzer({"status": "partial_completed"})
        with (
            mock.patch.object(cli, "StaticImageAnalyzer", return_value=fake),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(cli.main(["--input", "partial.png"]), 1)

    def test_analysis_error_exit_one(self) -> None:
        fake = FakeAnalyzer(
            error=StaticImageAnalysisError("IMAGE_NOT_FOUND", "missing")
        )
        with (
            mock.patch.object(cli, "StaticImageAnalyzer", return_value=fake),
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(cli.main(["--input", "missing.png"]), 1)

    def test_cli_usage_error_two(self) -> None:
        with redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main([]), 2)

    def test_overwrite_and_no_overlays_forwarded(self) -> None:
        fake = FakeAnalyzer({"status": "completed_with_no_detections"})
        with (
            mock.patch.object(cli, "StaticImageAnalyzer", return_value=fake),
            redirect_stdout(io.StringIO()),
        ):
            code = cli.main(
                [
                    "--input",
                    "blank.png",
                    "--output-root",
                    "outputs",
                    "--overwrite",
                    "--no-overlays",
                ]
            )
        self.assertEqual(code, 0)
        _, kwargs = fake.calls[0]
        self.assertTrue(kwargs["overwrite"])
        self.assertFalse(kwargs["generate_overlays"])
        self.assertEqual(kwargs["output_root"], "outputs")


class RealBlankImageSmokeTests(unittest.TestCase):
    def test_actual_models_blank_image_no_detection_exit_zero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "blank.png"
            output_root = root / "outputs"
            image = np.full((256, 256, 3), 127, dtype=np.uint8)
            success, encoded = cv2.imencode(".png", image)
            self.assertTrue(success)
            input_path.write_bytes(encoded.tobytes())
            before = hashlib.sha256(input_path.read_bytes()).hexdigest()
            with redirect_stdout(io.StringIO()):
                code = cli.main(
                    [
                        "--input",
                        str(input_path),
                        "--output-root",
                        str(output_root),
                    ]
                )
            self.assertEqual(code, 0)
            analysis_files = list(output_root.glob("*/analysis.json"))
            self.assertEqual(len(analysis_files), 1)
            result = json.loads(
                analysis_files[0].read_text("utf-8"),
                parse_constant=lambda value: self.fail(value),
            )
            self.assertEqual(result["status"], "completed_with_no_detections")
            self.assertEqual(result["face_result"]["face_count"], 0)
            self.assertEqual(result["pose_result"]["pose_count"], 0)
            self.assertEqual(
                hashlib.sha256(input_path.read_bytes()).hexdigest(),
                before,
            )
            for filename in (
                "face_overlay.png",
                "pose_overlay.png",
                "combined_overlay.png",
            ):
                self.assertTrue((analysis_files[0].parent / filename).is_file())


class ProtectionTests(unittest.TestCase):
    def _sha(self, relative: str) -> str:
        return hashlib.sha256((VISION_SERVER_ROOT / relative).read_bytes()).hexdigest()

    def test_requirements_unchanged(self) -> None:
        self.assertEqual(self._sha("requirements.txt"), REQUIREMENTS_SHA256)

    def test_requirements_lock_unchanged(self) -> None:
        self.assertEqual(self._sha("requirements-lock.txt"), REQUIREMENTS_LOCK_SHA256)

    def test_face_model_unchanged(self) -> None:
        self.assertEqual(
            self._sha("models/face_landmarker.task"),
            FACE_MODEL_SHA256,
        )

    def test_pose_model_unchanged(self) -> None:
        self.assertEqual(
            self._sha("models/pose_landmarker_full.task"),
            POSE_MODEL_SHA256,
        )

    def test_model_manifest_unchanged(self) -> None:
        self.assertEqual(
            self._sha("models/model_manifest.json"),
            MANIFEST_SHA256,
        )

    def test_model_reports_unchanged(self) -> None:
        self.assertEqual(
            self._sha("model_setup_report.json"),
            SETUP_REPORT_SHA256,
        )
        self.assertEqual(
            self._sha("model_loading_report.json"),
            LOADING_REPORT_SHA256,
        )

    def test_analysis_server_tree_unchanged(self) -> None:
        self.assertEqual(tree_digest(), ANALYSIS_TREE_SHA256)


if __name__ == "__main__":
    unittest.main()
