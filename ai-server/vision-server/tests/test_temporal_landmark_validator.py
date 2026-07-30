from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.vision.temporal_landmark_validator import (
    CSV_FIELDS, TemporalValidationError, build_frame_metrics, load_strict_frames,
)


def frame(timestamp=0, face=True, pose=True):
    point = lambda index, x: {"index": index, "x": x, "y": .5, "z": 0, "visibility": .9, "presence": .8}
    return {
        "sample_index": timestamp // 200, "source_frame_index": timestamp // 20,
        "timestamp_ms": timestamp, "timestamp_sec": timestamp / 1000,
        "frame_width": 100, "frame_height": 100, "frame_status": "face_and_shoulders_detected",
        "face_bounding_box": {"min_x": 20, "max_x": 40, "min_y": 20, "max_y": 40} if face else None,
        "required_pose_landmarks": {"nose": point(0, .5), "left_shoulder": point(11, .7), "right_shoulder": point(12, .3)} if pose else {},
        "optional_pose_landmarks": {"left_ear": point(7, .6), "right_ear": point(8, .4)} if pose else {},
        "warnings": [],
    }


class TemporalValidatorTests(unittest.TestCase):
    def test_strict_frames_valid(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "frames.jsonl"
            path.write_text("\n".join(json.dumps(frame(t)) for t in (0, 200)), encoding="utf-8")
            self.assertEqual(len(load_strict_frames(path)), 2)

    def test_strict_frames_reject_empty_blank_nan_and_duplicate_timestamp(self):
        cases = ("", "{}\n\n", '{"timestamp_ms":NaN}', '{"timestamp_ms":0}\n{"timestamp_ms":0}')
        for content in cases:
            with self.subTest(content=content), tempfile.TemporaryDirectory() as root:
                path = Path(root) / "frames.jsonl"
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(TemporalValidationError):
                    load_strict_frames(path)

    def test_frame_metrics_required_availability_and_no_interpolation(self):
        metrics, series = build_frame_metrics([frame(0), frame(200, face=False, pose=False), frame(400)])
        self.assertTrue(metrics[0]["availability"]["face_and_shoulders"])
        self.assertFalse(metrics[1]["availability"]["face_and_shoulders"])
        self.assertIsNone(series["nose"][1])
        self.assertIsNone(metrics[2]["displacements"]["nose"])

    def test_face_bbox_center_is_normalized(self):
        metrics, _ = build_frame_metrics([frame()])
        self.assertAlmostEqual(metrics[0]["derived"]["face_bbox_center"]["x"], .3)
        self.assertAlmostEqual(metrics[0]["derived"]["face_bbox_center"]["y"], .3)
        self.assertEqual(metrics[0]["derived"]["face_bounding_box"], {"min_x": .2, "max_x": .4, "min_y": .2, "max_y": .4})

    def test_exact_csv_field_order_has_no_forbidden_features(self):
        self.assertEqual(CSV_FIELDS[0], "sample_index")
        self.assertEqual(CSV_FIELDS[-1], "warnings")
        joined = " ".join(CSV_FIELDS)
        for forbidden in ("gaze", "iris", "yaw", "pitch", "roll", "tilt", "posture"):
            self.assertNotIn(forbidden, joined)


if __name__ == "__main__":
    unittest.main()
