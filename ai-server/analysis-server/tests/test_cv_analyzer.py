from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from fractions import Fraction

import numpy as np

from app.services.analysis_contracts import AnalyzerMediaFailure, AnalyzerUnavailable
from app.services.cv_analyzer import (
    FrameObservation,
    MediaPipeFrameObserver,
    sample_video_frames,
    score_observations,
)


def frame(**overrides) -> FrameObservation:
    values = {
        "face_count": 1,
        "face_area": 0.12,
        "face_center_x": 0.5,
        "face_center_y": 0.35,
        "yaw_proxy": 0.03,
        "pitch_proxy": 0.03,
        "roll_degrees": 2.0,
        "shoulder_tilt_degrees": 2.0,
        "shoulder_center_x": 0.5,
        "shoulder_center_y": 0.6,
        "head_shoulder_offset": 0.04,
    }
    values.update(overrides)
    return FrameObservation(**values)


class CvScoringTest(unittest.TestCase):
    def test_is_deterministic_bounded_and_labels_head_direction_proxy(self) -> None:
        samples = [frame() for _ in range(8)]
        first = score_observations(samples, min_usable_frames=5)
        second = score_observations(samples, min_usable_frames=5)
        self.assertEqual(first, second)
        self.assertEqual(first.gaze_score, 100.0)
        self.assertEqual(first.posture_score, 100.0)
        self.assertTrue(0 <= first.gaze_score <= 100)
        self.assertTrue(0 <= first.posture_score <= 100)
        self.assertIn("머리 방향", first.feedback[0])

    def test_poor_geometry_returns_lower_scores_and_actionable_feedback(self) -> None:
        samples = [
            frame(
                face_center_x=0.25 + index * 0.04,
                yaw_proxy=0.20,
                pitch_proxy=0.18,
                roll_degrees=22,
                shoulder_tilt_degrees=16,
                shoulder_center_x=0.27 + index * 0.03,
                head_shoulder_offset=0.32,
            )
            for index in range(6)
        ]
        result = score_observations(samples, min_usable_frames=5)
        self.assertLess(result.gaze_score, 30)
        self.assertLess(result.posture_score, 40)
        self.assertGreaterEqual(len(result.feedback), 3)

    def test_no_face_multiple_faces_bad_distance_and_too_few_frames_fail(self) -> None:
        invalid_cases = (
            [frame(face_count=0) for _ in range(6)],
            [frame() for _ in range(5)] + [frame(face_count=2)],
            [frame(face_area=0.005) for _ in range(6)],
            [frame() for _ in range(4)],
        )
        for samples in invalid_cases:
            with self.subTest(samples=len(samples)):
                with self.assertRaises(AnalyzerMediaFailure):
                    score_observations(samples, min_usable_frames=5)

    def test_missing_pose_on_most_frames_is_insufficient_not_a_fake_score(self) -> None:
        samples = [frame(shoulder_tilt_degrees=None) for _ in range(6)]
        with self.assertRaises(AnalyzerMediaFailure):
            score_observations(samples, min_usable_frames=5)

    def test_sequential_video_sampling_respects_hard_frame_cap(self) -> None:
        import av

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bounded.mp4"
            with av.open(str(path), mode="w") as container:
                stream = container.add_stream("mpeg4", rate=30)
                stream.width = 64
                stream.height = 64
                stream.pix_fmt = "yuv420p"
                for index in range(90):
                    pixels = np.full((64, 64, 3), index % 255, dtype=np.uint8)
                    video_frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
                    video_frame.pts = index
                    video_frame.time_base = Fraction(1, 30)
                    for packet in stream.encode(video_frame):
                        container.mux(packet)
                for packet in stream.encode():
                    container.mux(packet)
            sampled = list(sample_video_frames(
                path,
                sample_fps=10,
                max_frames=6,
                min_frames=5,
                max_duration_seconds=300,
            ))
        self.assertEqual(len(sampled), 6)

    def test_missing_or_tampered_models_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(AnalyzerUnavailable):
                MediaPipeFrameObserver(root / "face.task", root / "pose.task")

    def test_real_mediapipe_models_detect_no_face_in_synthetic_frame(self) -> None:
        model_root = Path("/app/models")
        if not model_root.is_dir():
            model_root = Path(__file__).resolve().parents[1] / "models"
        observer = MediaPipeFrameObserver(
            model_root / "face_landmarker.task",
            model_root / "pose_landmarker_full.task",
        )
        try:
            observation = observer.observe(np.zeros((256, 256, 3), dtype=np.uint8))
        finally:
            observer.close()
        self.assertEqual(observation.face_count, 0)


if __name__ == "__main__":
    unittest.main()
