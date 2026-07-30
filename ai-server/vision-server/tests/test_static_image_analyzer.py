from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import cv2
import numpy as np


VISION_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(VISION_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(VISION_SERVER_ROOT))

from app.vision import model_registry
from app.vision import static_image_analyzer as static
from app.vision.landmarker_factory import LandmarkerFactoryError


def point(x=0.4, y=0.5, z=0.0):
    return SimpleNamespace(
        x=x,
        y=y,
        z=z,
        visibility=0.9,
        presence=0.8,
    )


def face_raw(detected: bool):
    return SimpleNamespace(face_landmarks=[[point(), point(0.6, 0.7)]] if detected else [])


def pose_raw(detected: bool):
    return SimpleNamespace(
        pose_landmarks=[[point() for _ in range(33)]] if detected else [],
        pose_world_landmarks=[[point(0.1, 0.2, 0.3) for _ in range(33)]]
        if detected
        else [],
    )


class FakeLandmarker:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.detect_count = 0
        self.close_count = 0

    def detect(self, image):
        self.detect_count += 1
        if self.error:
            raise self.error
        return self.result

    def close(self) -> None:
        self.close_count += 1


def write_image(path: Path, value: int = 0) -> str:
    image = np.full((64, 80, 3), value, dtype=np.uint8)
    success, encoded = cv2.imencode(path.suffix, image)
    if not success:
        raise AssertionError("Test image encoding failed")
    path.write_bytes(encoded.tobytes())
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextmanager
def analyzer_context(
    root: Path,
    face: FakeLandmarker,
    pose: FakeLandmarker,
):
    face_descriptor = model_registry.ModelDescriptor(
        "face_landmarker",
        "float16_latest",
        "https://storage.googleapis.com/face.task",
        root / "face.task",
        model_registry.ALLOWED_MODEL_HOST,
        1,
    )
    pose_descriptor = model_registry.ModelDescriptor(
        "pose_landmarker",
        "full_float16_latest",
        "https://storage.googleapis.com/pose.task",
        root / "pose.task",
        model_registry.ALLOWED_MODEL_HOST,
        1,
    )

    def descriptor(model_id: str):
        return face_descriptor if model_id == "face_landmarker" else pose_descriptor

    def ready(value):
        return {
            "status": "ready",
            "sha256": "f" * 64 if value.model_id == "face_landmarker" else "p" * 64,
        }

    face_factory = mock.Mock(return_value=face)
    pose_factory = mock.Mock(return_value=pose)
    with (
        mock.patch.object(static, "get_model_descriptor", side_effect=descriptor),
        mock.patch.object(static, "require_model_ready", side_effect=ready),
    ):
        analyzer = static.StaticImageAnalyzer(face_factory, pose_factory)
        try:
            yield analyzer, face_factory, pose_factory
        finally:
            analyzer.close()


class StaticImageAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.input_path = self.root / "input.png"
        self.input_hash = write_image(self.input_path)
        self.output_root = self.root / "output"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _analyze(self, face_detected=False, pose_detected=False, **kwargs):
        face = FakeLandmarker(face_raw(face_detected))
        pose = FakeLandmarker(pose_raw(pose_detected))
        with analyzer_context(self.root, face, pose) as (analyzer, _, _):
            result = analyzer.analyze(
                self.input_path,
                output_root=self.output_root,
                **kwargs,
            )
        return result, face, pose

    def test_both_detected_completed(self) -> None:
        result, _, _ = self._analyze(True, True)
        self.assertEqual(result["status"], "completed")

    def test_both_no_detection(self) -> None:
        result, _, _ = self._analyze(False, False)
        self.assertEqual(result["status"], "completed_with_no_detections")
        self.assertEqual(result["face_result"]["face_count"], 0)
        self.assertEqual(result["pose_result"]["pose_count"], 0)

    def test_face_only_detection(self) -> None:
        result, _, _ = self._analyze(True, False)
        self.assertEqual(result["status"], "completed_with_no_pose")

    def test_pose_only_detection(self) -> None:
        result, _, _ = self._analyze(False, True)
        self.assertEqual(result["status"], "completed_with_no_face")

    def test_face_failure_pose_success_partial(self) -> None:
        face = FakeLandmarker(error=RuntimeError("face failed"))
        pose = FakeLandmarker(pose_raw(True))
        with analyzer_context(self.root, face, pose) as (analyzer, _, _):
            result = analyzer.analyze(
                self.input_path,
                output_root=self.output_root,
            )
        self.assertEqual(result["status"], "partial_completed")
        self.assertEqual(
            result["face_result"]["error"]["code"],
            "FACE_INFERENCE_FAILED",
        )
        self.assertEqual(result["pose_result"]["pose_count"], 1)

    def test_face_success_pose_failure_partial(self) -> None:
        face = FakeLandmarker(face_raw(True))
        pose = FakeLandmarker(error=RuntimeError("pose failed"))
        with analyzer_context(self.root, face, pose) as (analyzer, _, _):
            result = analyzer.analyze(
                self.input_path,
                output_root=self.output_root,
            )
        self.assertEqual(result["status"], "partial_completed")
        self.assertEqual(
            result["pose_result"]["error"]["code"],
            "POSE_INFERENCE_FAILED",
        )

    def test_both_fail_status_failed(self) -> None:
        face = FakeLandmarker(error=RuntimeError("face failed"))
        pose = FakeLandmarker(error=RuntimeError("pose failed"))
        with analyzer_context(self.root, face, pose) as (analyzer, _, _):
            result = analyzer.analyze(
                self.input_path,
                output_root=self.output_root,
            )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["errors"]), 2)

    def test_detect_called_exactly_once_per_model(self) -> None:
        _, face, pose = self._analyze()
        self.assertEqual(face.detect_count, 1)
        self.assertEqual(pose.detect_count, 1)

    def test_models_created_once_and_reused(self) -> None:
        second_input = self.root / "second.png"
        write_image(second_input, 10)
        face = FakeLandmarker(face_raw(False))
        pose = FakeLandmarker(pose_raw(False))
        with analyzer_context(self.root, face, pose) as (
            analyzer,
            face_factory,
            pose_factory,
        ):
            analyzer.analyze(self.input_path, output_root=self.output_root)
            analyzer.analyze(second_input, output_root=self.output_root)
            face_factory.assert_called_once()
            pose_factory.assert_called_once()
            self.assertEqual(face.detect_count, 2)
            self.assertEqual(pose.detect_count, 2)

    def test_models_closed_once(self) -> None:
        face = FakeLandmarker(face_raw(False))
        pose = FakeLandmarker(pose_raw(False))
        with analyzer_context(self.root, face, pose) as (analyzer, _, _):
            analyzer.analyze(self.input_path, output_root=self.output_root)
        self.assertEqual(face.close_count, 1)
        self.assertEqual(pose.close_count, 1)

    def test_duplicate_close_is_safe(self) -> None:
        face = FakeLandmarker(face_raw(False))
        pose = FakeLandmarker(pose_raw(False))
        with analyzer_context(self.root, face, pose) as (analyzer, _, _):
            analyzer.close()
            analyzer.close()
        self.assertEqual(face.close_count, 1)
        self.assertEqual(pose.close_count, 1)

    def test_pose_factory_failure_closes_face(self) -> None:
        face = FakeLandmarker(face_raw(False))
        with self.assertRaises(static.StaticImageAnalysisError) as raised:
            static.StaticImageAnalyzer(
                lambda: face,
                lambda: (_ for _ in ()).throw(
                    LandmarkerFactoryError("MODEL_NOT_FOUND", "pose missing")
                ),
            )
        self.assertEqual(raised.exception.code, "POSE_MODEL_NOT_READY")
        self.assertEqual(face.close_count, 1)

    def test_input_hash_and_bytes_preserved(self) -> None:
        before = self.input_path.read_bytes()
        result, _, _ = self._analyze()
        self.assertEqual(result["source"]["sha256"], self.input_hash)
        self.assertEqual(self.input_path.read_bytes(), before)

    def test_model_hashes_preserved_in_result(self) -> None:
        result, _, _ = self._analyze()
        self.assertEqual(result["models"]["face"]["sha256"], "f" * 64)
        self.assertEqual(result["models"]["pose"]["sha256"], "p" * 64)

    def test_analysis_json_is_strict_and_has_no_object_repr(self) -> None:
        result, _, _ = self._analyze(True, True)
        analysis_path = self.output_root / result["outputs"]["analysis_json"]
        parsed = json.loads(
            analysis_path.read_text("utf-8"),
            parse_constant=lambda value: self.fail(value),
        )
        self.assertEqual(parsed["status"], "completed")
        self.assertNotIn("namespace(", analysis_path.read_text("utf-8"))

    def test_three_overlays_are_created(self) -> None:
        result, _, _ = self._analyze()
        for key in ("face_overlay", "pose_overlay", "combined_overlay"):
            self.assertIsNotNone(result["outputs"][key])
            self.assertTrue((self.output_root / result["outputs"][key]).is_file())

    def test_no_overlays_writes_json_only(self) -> None:
        result, _, _ = self._analyze(generate_overlays=False)
        self.assertIsNone(result["outputs"]["face_overlay"])
        self.assertIsNone(result["outputs"]["pose_overlay"])
        self.assertIsNone(result["outputs"]["combined_overlay"])
        self.assertEqual(result["timing"]["overlay_render_sec"], 0.0)
        analysis_path = self.output_root / result["outputs"]["analysis_json"]
        self.assertEqual(
            sorted(path.name for path in analysis_path.parent.iterdir()),
            ["analysis.json"],
        )

    def test_existing_output_is_blocked_before_detect(self) -> None:
        face = FakeLandmarker(face_raw(False))
        pose = FakeLandmarker(pose_raw(False))
        with analyzer_context(self.root, face, pose) as (analyzer, _, _):
            analyzer.analyze(self.input_path, output_root=self.output_root)
            with self.assertRaises(static.StaticImageAnalysisError) as raised:
                analyzer.analyze(self.input_path, output_root=self.output_root)
        self.assertEqual(raised.exception.code, "OUTPUT_ALREADY_EXISTS")
        self.assertEqual(face.detect_count, 1)
        self.assertEqual(pose.detect_count, 1)

    def test_overwrite_replaces_outputs(self) -> None:
        face = FakeLandmarker(face_raw(False))
        pose = FakeLandmarker(pose_raw(False))
        with analyzer_context(self.root, face, pose) as (analyzer, _, _):
            first = analyzer.analyze(self.input_path, output_root=self.output_root)
            second = analyzer.analyze(
                self.input_path,
                output_root=self.output_root,
                overwrite=True,
                generate_overlays=False,
            )
        output_directory = (
            self.output_root / second["outputs"]["analysis_json"]
        ).parent
        self.assertTrue((output_directory / "analysis.json").is_file())
        self.assertFalse((output_directory / "face_overlay.png").exists())
        self.assertEqual(first["source"]["sha256"], second["source"]["sha256"])

    def test_invalid_input_fails_without_detect(self) -> None:
        face = FakeLandmarker(face_raw(False))
        pose = FakeLandmarker(pose_raw(False))
        with analyzer_context(self.root, face, pose) as (analyzer, _, _):
            with self.assertRaises(static.StaticImageAnalysisError) as raised:
                analyzer.analyze(
                    self.root / "missing.png",
                    output_root=self.output_root,
                )
        self.assertEqual(raised.exception.code, "IMAGE_NOT_FOUND")
        self.assertEqual(face.detect_count, 0)
        self.assertEqual(pose.detect_count, 0)

    def test_closed_analyzer_rejects_analysis(self) -> None:
        face = FakeLandmarker(face_raw(False))
        pose = FakeLandmarker(pose_raw(False))
        with analyzer_context(self.root, face, pose) as (analyzer, _, _):
            analyzer.close()
            with self.assertRaises(static.StaticImageAnalysisError) as raised:
                analyzer.analyze(self.input_path, output_root=self.output_root)
        self.assertEqual(raised.exception.code, "STATIC_IMAGE_ANALYSIS_FAILED")


if __name__ == "__main__":
    unittest.main()
