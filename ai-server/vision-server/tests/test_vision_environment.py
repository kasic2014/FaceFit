from __future__ import annotations

import io
import json
import math
import os
import subprocess
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


VISION_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(VISION_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(VISION_SERVER_ROOT))

from app.core import config
from scripts import check_vision_environment as check


class PythonEnvironmentTests(unittest.TestCase):
    def test_python_312_logic(self) -> None:
        self.assertTrue(check.is_python_312(types.SimpleNamespace(major=3, minor=12)))
        self.assertFalse(check.is_python_312(types.SimpleNamespace(major=3, minor=14)))

    def test_running_python_is_312(self) -> None:
        self.assertTrue(check.is_python_312())

    def test_expected_virtual_environment_path_is_accepted(self) -> None:
        self.assertTrue(
            check.is_expected_virtual_environment(
                prefix=check.EXPECTED_VENV_ROOT,
                base_prefix=check.EXPECTED_VENV_ROOT.parent / "base",
                executable=check.EXPECTED_VENV_ROOT / "Scripts" / "python.exe",
            )
        )

    def test_non_virtual_environment_is_detected(self) -> None:
        same_path = check.EXPECTED_VENV_ROOT.parent / "base"
        self.assertFalse(
            check.is_expected_virtual_environment(
                prefix=same_path,
                base_prefix=same_path,
                executable=same_path / "python.exe",
            )
        )

    def test_running_environment_is_vision_server_venv(self) -> None:
        self.assertTrue(check.is_expected_virtual_environment())

    def test_python_executable_is_inside_vision_environment(self) -> None:
        self.assertEqual(
            Path(sys.executable).resolve(),
            (VISION_SERVER_ROOT / ".venv" / "Scripts" / "python.exe").resolve(),
        )


class InstalledPackageTests(unittest.TestCase):
    def test_mediapipe_import_and_version(self) -> None:
        import mediapipe

        self.assertIsInstance(mediapipe.__version__, str)
        self.assertTrue(mediapipe.__version__)

    def test_numpy_import_and_version(self) -> None:
        import numpy

        self.assertIsInstance(numpy.__version__, str)
        self.assertTrue(numpy.__version__)

    def test_opencv_import_and_version(self) -> None:
        import cv2

        self.assertIsInstance(cv2.__version__, str)
        self.assertTrue(cv2.__version__)

    def test_exactly_one_opencv_distribution_is_installed(self) -> None:
        distribution, version = check._opencv_distribution()
        self.assertEqual(distribution, "opencv-contrib-python")
        self.assertIsInstance(version, str)


class MediaPipeApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import mediapipe as mp
        from mediapipe.tasks import python as tasks_python
        from mediapipe.tasks.python import vision

        cls.api = check.inspect_mediapipe_api(mp, tasks_python, vision)

    def test_tasks_api_exists(self) -> None:
        self.assertTrue(self.api["tasks"])

    def test_base_options_exists(self) -> None:
        self.assertTrue(self.api["BaseOptions"])

    def test_face_landmarker_exists(self) -> None:
        self.assertTrue(self.api["FaceLandmarker"])

    def test_face_landmarker_options_exists(self) -> None:
        self.assertTrue(self.api["FaceLandmarkerOptions"])

    def test_pose_landmarker_exists(self) -> None:
        self.assertTrue(self.api["PoseLandmarker"])

    def test_pose_landmarker_options_exists(self) -> None:
        self.assertTrue(self.api["PoseLandmarkerOptions"])

    def test_running_mode_exists(self) -> None:
        self.assertTrue(self.api["RunningMode"])

    def test_mp_image_api_exists(self) -> None:
        self.assertTrue(self.api["Image"])

    def test_missing_api_is_detected(self) -> None:
        empty = types.SimpleNamespace()
        result = check.inspect_mediapipe_api(empty, empty, empty)
        self.assertFalse(any(result.values()))


class ConfigurationTests(unittest.TestCase):
    def test_vision_server_root_is_correct(self) -> None:
        self.assertEqual(config.VISION_SERVER_ROOT, VISION_SERVER_ROOT)

    def test_default_model_paths_are_configured(self) -> None:
        self.assertEqual(
            config.FACE_LANDMARKER_MODEL_PATH,
            (VISION_SERVER_ROOT / "models" / "face_landmarker.task").resolve(),
        )
        self.assertEqual(
            config.POSE_LANDMARKER_MODEL_PATH,
            (VISION_SERVER_ROOT / "models" / "pose_landmarker_full.task").resolve(),
        )

    def test_relative_model_environment_path_is_root_relative(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"FACE_LANDMARKER_MODEL_PATH": "models/custom-face.task"},
        ):
            actual = config.resolve_model_path(
                "FACE_LANDMARKER_MODEL_PATH",
                "models/face_landmarker.task",
            )
        self.assertEqual(
            actual,
            (VISION_SERVER_ROOT / "models" / "custom-face.task").resolve(),
        )

    def test_absolute_model_environment_path_is_preserved(self) -> None:
        absolute = (VISION_SERVER_ROOT / "outside" / "pose.task").resolve()
        with mock.patch.dict(
            os.environ,
            {"POSE_LANDMARKER_MODEL_PATH": str(absolute)},
        ):
            actual = config.resolve_model_path(
                "POSE_LANDMARKER_MODEL_PATH",
                "models/pose_landmarker.task",
            )
        self.assertEqual(actual, absolute)


class DirectoryTests(unittest.TestCase):
    def test_input_images_directory_exists(self) -> None:
        self.assertTrue(config.INPUT_IMAGES_DIR.is_dir())

    def test_input_videos_directory_exists(self) -> None:
        self.assertTrue(config.INPUT_VIDEOS_DIR.is_dir())

    def test_output_directory_exists(self) -> None:
        self.assertTrue(config.OUTPUT_DIR.is_dir())

    def test_directories_are_readable_writable_and_deletable(self) -> None:
        for path in (
            config.MODELS_DIR,
            config.INPUT_IMAGES_DIR,
            config.INPUT_VIDEOS_DIR,
            config.OUTPUT_DIR,
        ):
            with self.subTest(path=path):
                result = check.check_directory(path)
                self.assertTrue(result["readable"])
                self.assertTrue(result["writable"])
                self.assertTrue(result["deletable"])

    def test_missing_directory_is_reported(self) -> None:
        missing = VISION_SERVER_ROOT / "does-not-exist"
        result = check.check_directory(missing)
        self.assertFalse(result["exists"])
        self.assertFalse(result["readable"])


class ReportTests(unittest.TestCase):
    def test_strict_json_round_trip(self) -> None:
        report = check.collect_environment_report(
            lambda: {"returncode": 0, "ok": True, "output": "ok"}
        )
        encoded = json.dumps(report, allow_nan=False)
        decoded = json.loads(
            encoded,
            parse_constant=lambda value: self.fail(f"non-finite: {value}"),
        )
        self.assertEqual(decoded["schema_version"], "1.0")

    def test_allow_nan_false_rejects_non_finite_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "report.json"
            with self.assertRaises(ValueError):
                check.write_report({"value": math.nan}, destination)
            self.assertFalse(destination.exists())

    def test_atomic_report_save_uses_os_replace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "report.json"
            real_replace = os.replace
            with mock.patch.object(
                check.os,
                "replace",
                wraps=real_replace,
            ) as replace:
                check.write_report({"status": "ready"}, destination)
            replace.assert_called_once()
            self.assertEqual(json.loads(destination.read_text("utf-8"))["status"], "ready")
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_ready_report_has_no_errors(self) -> None:
        report = check.collect_environment_report(
            lambda: {"returncode": 0, "ok": True, "output": "ok"}
        )
        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["errors"], [])

    def test_missing_required_api_produces_failed_status(self) -> None:
        missing_api = {name: False for name in check.inspect_mediapipe_api(
            types.SimpleNamespace(),
            types.SimpleNamespace(),
            types.SimpleNamespace(),
        )}
        with mock.patch.object(check, "inspect_mediapipe_api", return_value=missing_api):
            report = check.collect_environment_report(
                lambda: {"returncode": 0, "ok": True, "output": "ok"}
            )
        self.assertEqual(report["status"], "failed")
        self.assertTrue(any("APIs are missing" in error for error in report["errors"]))

    def test_pip_check_failure_is_recorded(self) -> None:
        report = check.collect_environment_report(
            lambda: {
                "returncode": 1,
                "ok": False,
                "output": "broken dependency",
            }
        )
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["pip_check"]["output"], "broken dependency")
        self.assertTrue(any("pip check failed" in error for error in report["errors"]))

    def test_report_contains_required_top_level_fields(self) -> None:
        report = check.collect_environment_report(
            lambda: {"returncode": 0, "ok": True, "output": "ok"}
        )
        self.assertEqual(
            set(report),
            {
                "schema_version",
                "status",
                "platform",
                "python",
                "virtual_environment",
                "packages",
                "mediapipe_api",
                "directories",
                "pip_check",
                "warnings",
                "errors",
            },
        )


class CliTests(unittest.TestCase):
    def test_cli_success_exit_code_zero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            with (
                mock.patch.object(
                    check,
                    "collect_environment_report",
                    return_value={"status": "ready"},
                ),
                mock.patch.object(check, "REPORT_PATH", report_path),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(check.main([]), 0)
            self.assertTrue(report_path.is_file())

    def test_environment_error_exit_code_one(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            with (
                mock.patch.object(
                    check,
                    "collect_environment_report",
                    return_value={"status": "failed"},
                ),
                mock.patch.object(check, "REPORT_PATH", report_path),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(check.main([]), 1)

    def test_cli_usage_error_exit_code_two(self) -> None:
        with redirect_stderr(io.StringIO()):
            self.assertEqual(check.main(["--unexpected"]), 2)

    def test_real_cli_exits_zero(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(check.__file__)],
            cwd=VISION_SERVER_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
