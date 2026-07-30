from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np


VISION_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(VISION_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(VISION_SERVER_ROOT))

from app.vision import landmarker_factory
from app.vision import video_analyzer as analyzer_module


def raw_landmarks(count: int):
    return [
        SimpleNamespace(
            x=0.2 + index * 0.01,
            y=0.3 + index * 0.005,
            z=-0.1,
            visibility=0.95,
            presence=0.9,
        )
        for index in range(count)
    ]


def face_raw(detected=True):
    return SimpleNamespace(face_landmarks=[raw_landmarks(20)] if detected else [])


def pose_raw(detected=True, count=33):
    landmarks = [raw_landmarks(count)] if detected else []
    return SimpleNamespace(
        pose_landmarks=landmarks,
        pose_world_landmarks=landmarks,
    )


class FakeCapture:
    def __init__(self, count=6) -> None:
        self.frames = [
            np.full((48, 64, 3), index, dtype=np.uint8)
            for index in range(count)
        ]
        self.released = False

    def read(self):
        if not self.frames:
            return False, None
        return True, self.frames.pop(0)

    def release(self):
        self.released = True


class FakeLandmarker:
    def __init__(self, result=None, error=None) -> None:
        self.result = result
        self.error = error
        self.timestamps = []
        self.close_count = 0

    def detect_for_video(self, image, timestamp_ms):
        self.timestamps.append(timestamp_ms)
        if self.error:
            raise self.error
        return self.result

    def close(self):
        self.close_count += 1


class VideoAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.input_path = self.root / "input.mp4"
        self.input_path.write_bytes(b"video-input")
        self.input_hash = hashlib.sha256(b"video-input").hexdigest()
        self.output_root = self.root / "outputs"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _metadata(self):
        return {
            "source_filename": self.input_path.name,
            "source_relative_path": self.input_path.name,
            "extension": ".mp4",
            "file_size_bytes": self.input_path.stat().st_size,
            "sha256": self.input_hash,
            "width": 64,
            "height": 48,
            "original_fps": 10.0,
            "declared_frame_count": 6,
            "estimated_duration_sec": 0.6,
            "codec_fourcc": "mp4v",
            "capture_opened": True,
            "first_frame_decoded": True,
            "rotation_status": "not_applied",
            "warnings": [],
        }

    def _patches(self, capture):
        descriptor = lambda model_id: SimpleNamespace(
            model_id=model_id,
            variant="variant",
            local_path=Path(f"models/{model_id}.task"),
        )
        return (
            mock.patch.object(
                analyzer_module,
                "inspect_video_metadata",
                return_value=self._metadata(),
            ),
            mock.patch.object(
                analyzer_module,
                "open_video_capture",
                return_value=capture,
            ),
            mock.patch.object(
                analyzer_module,
                "get_model_descriptor",
                side_effect=descriptor,
            ),
            mock.patch.object(
                analyzer_module,
                "require_model_ready",
                return_value={"sha256": "a" * 64},
            ),
        )

    def _analyze(self, face=None, pose=None, **kwargs):
        face = face or FakeLandmarker(face_raw())
        pose = pose or FakeLandmarker(pose_raw())
        capture = FakeCapture()
        patches = self._patches(capture)
        with patches[0], patches[1], patches[2], patches[3]:
            with analyzer_module.VideoAnalyzer(
                lambda: face,
                lambda: pose,
            ) as analyzer:
                result = analyzer.analyze(
                    self.input_path,
                    5,
                    output_root=self.output_root,
                    generate_overlay=False,
                    **kwargs,
                )
        return result, face, pose, capture

    def test_models_created_once_and_detect_once_per_sample(self) -> None:
        face_factory = mock.Mock(return_value=FakeLandmarker(face_raw()))
        pose_factory = mock.Mock(return_value=FakeLandmarker(pose_raw()))
        capture = FakeCapture()
        patches = self._patches(capture)
        with patches[0], patches[1], patches[2], patches[3]:
            with analyzer_module.VideoAnalyzer(
                face_factory,
                pose_factory,
            ) as analyzer:
                result = analyzer.analyze(
                    self.input_path,
                    5,
                    output_root=self.output_root,
                    generate_overlay=False,
                )
        face_factory.assert_called_once()
        pose_factory.assert_called_once()
        self.assertEqual(result["sampling"]["sampled_frame_count"], 3)
        self.assertEqual(
            result["resources"]["face_detect_for_video_call_count"], 3
        )
        self.assertEqual(
            result["resources"]["pose_detect_for_video_call_count"], 3
        )

    def test_timestamps_forwarded_strictly(self) -> None:
        result, face, pose, _ = self._analyze()
        self.assertEqual(face.timestamps, [0, 200, 400])
        self.assertEqual(pose.timestamps, [0, 200, 400])
        self.assertTrue(result["sampling"]["timestamps_strictly_increasing"])

    def test_face_and_required_shoulders_detected(self) -> None:
        result, _, _, _ = self._analyze()
        summary = result["detection_summary"]
        self.assertEqual(summary["face_detected_ratio"], 1)
        self.assertEqual(summary["required_shoulders_available_ratio"], 1)
        self.assertEqual(
            summary["frame_status_counts"]["face_and_shoulders_detected"], 3
        )

    def test_face_zero_is_normal(self) -> None:
        result, _, _, _ = self._analyze(
            face=FakeLandmarker(face_raw(False))
        )
        counts = result["detection_summary"]["frame_status_counts"]
        self.assertEqual(counts["shoulders_detected_face_unavailable"], 3)
        self.assertEqual(result["status"], "completed")

    def test_pose_zero_is_normal(self) -> None:
        result, _, _, _ = self._analyze(
            pose=FakeLandmarker(pose_raw(False))
        )
        counts = result["detection_summary"]["frame_status_counts"]
        self.assertEqual(counts["face_detected_shoulders_unavailable"], 3)

    def test_required_landmark_incomplete(self) -> None:
        result, _, _, _ = self._analyze(
            pose=FakeLandmarker(pose_raw(True, 12))
        )
        self.assertEqual(
            result["detection_summary"]["required_shoulders_available_ratio"],
            0,
        )

    def test_all_inference_failure_fails_without_final_output(self) -> None:
        face = FakeLandmarker(error=RuntimeError("face"))
        pose = FakeLandmarker(error=RuntimeError("pose"))
        capture = FakeCapture()
        patches = self._patches(capture)
        with patches[0], patches[1], patches[2], patches[3]:
            with analyzer_module.VideoAnalyzer(
                lambda: face,
                lambda: pose,
            ) as analyzer:
                with self.assertRaises(analyzer_module.VideoAnalysisError) as raised:
                    analyzer.analyze(
                        self.input_path,
                        5,
                        output_root=self.output_root,
                        generate_overlay=False,
                    )
        self.assertEqual(raised.exception.code, "ALL_FRAME_INFERENCE_FAILED")
        self.assertEqual(list(self.output_root.glob("*/analysis.json")), [])

    def test_partial_inference_failure_is_partial_completed(self) -> None:
        result, _, _, _ = self._analyze(
            face=FakeLandmarker(error=RuntimeError("face"))
        )
        self.assertEqual(result["status"], "partial_completed")
        self.assertEqual(
            result["detection_summary"]["partial_failure_frame_count"], 3
        )

    def test_frames_jsonl_and_analysis_json_are_strict(self) -> None:
        result, _, _, _ = self._analyze()
        analysis_path = self.output_root / result["outputs"]["analysis_json"]
        json.loads(
            analysis_path.read_text("utf-8"),
            parse_constant=lambda value: self.fail(value),
        )
        frames_path = self.output_root / result["outputs"]["frames_jsonl"]
        rows = [
            json.loads(line, parse_constant=lambda value: self.fail(value))
            for line in frames_path.read_text("utf-8").splitlines()
        ]
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["required_pose_landmarks"]["nose"]["index"], 0)
        self.assertIn("left_ear", rows[0]["optional_pose_landmarks"])

    def test_default_sampled_frames_first_middle_last(self) -> None:
        result, _, _, _ = self._analyze()
        directory = self.output_root / result["outputs"]["sampled_frames_directory"]
        self.assertEqual(len(list(directory.glob("*.png"))), 3)

    def test_save_all_sampled_frames(self) -> None:
        result, _, _, _ = self._analyze(save_all_sampled_frames=True)
        self.assertEqual(result["outputs"]["saved_sampled_frame_count"], 3)

    def test_input_bytes_and_hash_preserved(self) -> None:
        before = self.input_path.read_bytes()
        result, _, _, _ = self._analyze()
        self.assertEqual(result["source"]["sha256"], self.input_hash)
        self.assertEqual(self.input_path.read_bytes(), before)

    def test_models_and_capture_closed_once(self) -> None:
        result, face, pose, capture = self._analyze()
        self.assertEqual(face.close_count, 1)
        self.assertEqual(pose.close_count, 1)
        self.assertTrue(capture.released)
        self.assertEqual(result["resources"]["face_model_close_count"], 1)
        self.assertEqual(result["resources"]["pose_model_close_count"], 1)

    def test_existing_output_is_blocked_before_model_creation(self) -> None:
        self.output_root.mkdir()
        (self.output_root / f"input_{self.input_hash[:8]}").mkdir()
        face_factory = mock.Mock(return_value=FakeLandmarker(face_raw()))
        pose_factory = mock.Mock(return_value=FakeLandmarker(pose_raw()))
        capture = FakeCapture()
        patches = self._patches(capture)
        with patches[0], patches[1], patches[2], patches[3]:
            with analyzer_module.VideoAnalyzer(
                face_factory,
                pose_factory,
            ) as analyzer:
                with self.assertRaises(analyzer_module.VideoAnalysisError) as raised:
                    analyzer.analyze(
                        self.input_path,
                        5,
                        output_root=self.output_root,
                        generate_overlay=False,
                    )
        self.assertEqual(raised.exception.code, "OUTPUT_ALREADY_EXISTS")
        face_factory.assert_not_called()
        pose_factory.assert_not_called()

    def test_duplicate_close_is_safe(self) -> None:
        analyzer = analyzer_module.VideoAnalyzer(
            lambda: FakeLandmarker(face_raw()),
            lambda: FakeLandmarker(pose_raw()),
        )
        analyzer.close()
        analyzer.close()


class VideoFactoryTests(unittest.TestCase):
    def test_face_video_factory_options(self) -> None:
        created = object()
        with (
            mock.patch.object(
                landmarker_factory,
                "_verified_model_path",
                return_value="face.task",
            ),
            mock.patch.object(
                landmarker_factory.vision.FaceLandmarker,
                "create_from_options",
                return_value=created,
            ) as factory,
        ):
            self.assertIs(
                landmarker_factory.create_face_landmarker_video_mode(),
                created,
            )
        options = factory.call_args.args[0]
        self.assertEqual(options.running_mode, landmarker_factory.vision.RunningMode.VIDEO)
        self.assertEqual(options.num_faces, 1)
        self.assertFalse(options.output_face_blendshapes)

    def test_pose_video_factory_options(self) -> None:
        created = object()
        with (
            mock.patch.object(
                landmarker_factory,
                "_verified_model_path",
                return_value="pose.task",
            ),
            mock.patch.object(
                landmarker_factory.vision.PoseLandmarker,
                "create_from_options",
                return_value=created,
            ) as factory,
        ):
            self.assertIs(
                landmarker_factory.create_pose_landmarker_video_mode(),
                created,
            )
        options = factory.call_args.args[0]
        self.assertEqual(options.running_mode, landmarker_factory.vision.RunningMode.VIDEO)
        self.assertEqual(options.num_poses, 1)
        self.assertFalse(options.output_segmentation_masks)


if __name__ == "__main__":
    unittest.main()
