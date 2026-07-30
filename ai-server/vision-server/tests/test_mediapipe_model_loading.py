from __future__ import annotations

import io
import json
import math
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


VISION_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(VISION_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(VISION_SERVER_ROOT))

from app.vision import landmarker_factory as factory
from app.vision import model_registry as registry
from scripts import check_mediapipe_model_loading as loading


class FakeLandmarker:
    def __init__(self) -> None:
        self.close_count = 0

    def close(self) -> None:
        self.close_count += 1


def descriptor_for(directory: Path, model_id: str) -> registry.ModelDescriptor:
    return registry.ModelDescriptor(
        model_id=model_id,
        variant="test",
        source_url="https://storage.googleapis.com/test.task",
        local_path=directory / f"{model_id}.task",
        allowed_host=registry.ALLOWED_MODEL_HOST,
        minimum_size_bytes=1,
    )


class FactoryTests(unittest.TestCase):
    def test_face_factory_options_and_close(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            descriptor = descriptor_for(Path(directory), "face_landmarker")
            fake = FakeLandmarker()
            with (
                mock.patch.object(
                    factory,
                    "get_model_descriptor",
                    return_value=descriptor,
                ),
                mock.patch.object(
                    factory,
                    "require_model_ready",
                    return_value={"status": "ready"},
                ),
                mock.patch.object(
                    factory.vision.FaceLandmarker,
                    "create_from_options",
                    return_value=fake,
                ) as create,
            ):
                result = factory.create_face_landmarker_image_mode()
            options = create.call_args.args[0]
            self.assertEqual(options.running_mode, factory.vision.RunningMode.IMAGE)
            self.assertEqual(options.num_faces, 1)
            self.assertEqual(options.min_face_detection_confidence, 0.5)
            self.assertEqual(options.min_face_presence_confidence, 0.5)
            self.assertEqual(options.min_tracking_confidence, 0.5)
            self.assertFalse(options.output_face_blendshapes)
            self.assertFalse(options.output_facial_transformation_matrixes)
            self.assertEqual(
                options.base_options.model_asset_path,
                str(descriptor.local_path.resolve()),
            )
            result.close()
            self.assertEqual(fake.close_count, 1)

    def test_pose_factory_options_and_close(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            descriptor = descriptor_for(Path(directory), "pose_landmarker")
            fake = FakeLandmarker()
            with (
                mock.patch.object(
                    factory,
                    "get_model_descriptor",
                    return_value=descriptor,
                ),
                mock.patch.object(
                    factory,
                    "require_model_ready",
                    return_value={"status": "ready"},
                ),
                mock.patch.object(
                    factory.vision.PoseLandmarker,
                    "create_from_options",
                    return_value=fake,
                ) as create,
            ):
                result = factory.create_pose_landmarker_image_mode()
            options = create.call_args.args[0]
            self.assertEqual(options.running_mode, factory.vision.RunningMode.IMAGE)
            self.assertEqual(options.num_poses, 1)
            self.assertEqual(options.min_pose_detection_confidence, 0.5)
            self.assertEqual(options.min_pose_presence_confidence, 0.5)
            self.assertEqual(options.min_tracking_confidence, 0.5)
            self.assertFalse(options.output_segmentation_masks)
            self.assertEqual(
                options.base_options.model_asset_path,
                str(descriptor.local_path.resolve()),
            )
            result.close()
            self.assertEqual(fake.close_count, 1)

    def test_missing_model_blocks_factory(self) -> None:
        with (
            mock.patch.object(
                factory,
                "get_model_descriptor",
                return_value=descriptor_for(
                    VISION_SERVER_ROOT / "missing",
                    "face_landmarker",
                ),
            ),
            mock.patch.object(
                factory,
                "require_model_ready",
                side_effect=registry.ModelRegistryError(
                    "MODEL_NOT_FOUND",
                    "missing model",
                ),
            ),
        ):
            with self.assertRaises(factory.LandmarkerFactoryError) as raised:
                factory.create_face_landmarker_image_mode()
        self.assertEqual(raised.exception.code, "MODEL_NOT_FOUND")

    def test_checksum_mismatch_blocks_factory(self) -> None:
        with (
            mock.patch.object(
                factory,
                "get_model_descriptor",
                return_value=descriptor_for(
                    VISION_SERVER_ROOT / "mismatch",
                    "pose_landmarker",
                ),
            ),
            mock.patch.object(
                factory,
                "require_model_ready",
                side_effect=registry.ModelRegistryError(
                    "MODEL_CHECKSUM_MISMATCH",
                    "checksum mismatch",
                ),
            ),
        ):
            with self.assertRaises(factory.LandmarkerFactoryError) as raised:
                factory.create_pose_landmarker_image_mode()
        self.assertEqual(raised.exception.code, "MODEL_CHECKSUM_MISMATCH")

    def test_face_load_error_preserves_original_message(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            descriptor = descriptor_for(Path(directory), "face_landmarker")
            with (
                mock.patch.object(
                    factory,
                    "get_model_descriptor",
                    return_value=descriptor,
                ),
                mock.patch.object(
                    factory,
                    "require_model_ready",
                    return_value={"status": "ready"},
                ),
                mock.patch.object(
                    factory.vision.FaceLandmarker,
                    "create_from_options",
                    side_effect=RuntimeError("native load detail"),
                ),
            ):
                with self.assertRaises(factory.LandmarkerFactoryError) as raised:
                    factory.create_face_landmarker_image_mode()
        self.assertEqual(raised.exception.code, "FACE_MODEL_LOAD_FAILED")
        self.assertIn("native load detail", str(raised.exception))

    def test_pose_load_error_preserves_original_message(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            descriptor = descriptor_for(Path(directory), "pose_landmarker")
            with (
                mock.patch.object(
                    factory,
                    "get_model_descriptor",
                    return_value=descriptor,
                ),
                mock.patch.object(
                    factory,
                    "require_model_ready",
                    return_value={"status": "ready"},
                ),
                mock.patch.object(
                    factory.vision.PoseLandmarker,
                    "create_from_options",
                    side_effect=RuntimeError("native pose detail"),
                ),
            ):
                with self.assertRaises(factory.LandmarkerFactoryError) as raised:
                    factory.create_pose_landmarker_image_mode()
        self.assertEqual(raised.exception.code, "POSE_MODEL_LOAD_FAILED")
        self.assertIn("native pose detail", str(raised.exception))


class LoadingReportTests(unittest.TestCase):
    def _ready_state(self, descriptor):
        return {
            "status": "ready",
            "path": str(descriptor.local_path),
            "sha256": "a" * 64,
        }

    def test_face_and_pose_created_and_closed_once(self) -> None:
        face = FakeLandmarker()
        pose = FakeLandmarker()

        def descriptor(model_id):
            return descriptor_for(VISION_SERVER_ROOT / "models", model_id)

        with (
            mock.patch.object(loading, "get_model_descriptor", side_effect=descriptor),
            mock.patch.object(
                loading,
                "require_model_ready",
                side_effect=lambda value, path: self._ready_state(value),
            ),
        ):
            report = loading.check_model_loading(
                face_creator=lambda: face,
                pose_creator=lambda: pose,
            )
        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["face_model"]["status"], "loaded")
        self.assertEqual(report["pose_model"]["status"], "loaded")
        self.assertTrue(report["face_model"]["closed"])
        self.assertTrue(report["pose_model"]["closed"])
        self.assertEqual(face.close_count, 1)
        self.assertEqual(pose.close_count, 1)

    def test_loading_report_strict_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            registry.write_json_atomic(
                {
                    "schema_version": "1.0",
                    "status": "ready",
                    "load_time_sec": 0.0,
                },
                path,
            )
            parsed = json.loads(
                path.read_text("utf-8"),
                parse_constant=lambda value: self.fail(value),
            )
            self.assertEqual(parsed["status"], "ready")

    def test_loading_report_rejects_nan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            with self.assertRaises(ValueError):
                registry.write_json_atomic({"value": math.nan}, path)

    def test_loading_cli_success_zero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            with (
                mock.patch.object(
                    loading,
                    "check_model_loading",
                    return_value={"status": "ready"},
                ),
                mock.patch.object(loading, "REPORT_PATH", report_path),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(loading.main([]), 0)
            self.assertTrue(report_path.is_file())

    def test_loading_cli_failure_one(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            with (
                mock.patch.object(
                    loading,
                    "check_model_loading",
                    return_value={"status": "failed"},
                ),
                mock.patch.object(loading, "REPORT_PATH", report_path),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(loading.main([]), 1)

    def test_loading_cli_usage_error_two(self) -> None:
        with redirect_stderr(io.StringIO()):
            self.assertEqual(loading.main(["--unknown"]), 2)


class RealModelSmokeTests(unittest.TestCase):
    def _models_ready(self) -> bool:
        try:
            return all(
                registry.require_model_ready(descriptor)["status"] == "ready"
                for descriptor in registry.get_all_model_descriptors()
            )
        except registry.ModelRegistryError:
            return False

    def test_real_face_model_create_and_close_once_without_detect(self) -> None:
        if not self._models_ready():
            self.skipTest("Verified MediaPipe models are not installed.")
        landmarker = factory.create_face_landmarker_image_mode()
        landmarker.close()

    def test_real_pose_model_create_and_close_once_without_detect(self) -> None:
        if not self._models_ready():
            self.skipTest("Verified MediaPipe models are not installed.")
        landmarker = factory.create_pose_landmarker_image_mode()
        landmarker.close()


if __name__ == "__main__":
    unittest.main()
