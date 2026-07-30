from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from app.vision.posture_raw_validator import (
    POSTURE_CSV_FIELDS,
    _frame_face_geometry,
    _selected_candidate,
    _write_csv,
)


def raw():
    return {
        "available": True,
        "shoulders_available": True,
        "nose_alignment_available": True,
        "face_alignment_available": False,
        "shoulder_tilt_deg": 1.0,
        "shoulder_height_difference_norm": 0.02,
        "shoulder_center_x": 0.5,
        "shoulder_center_y": 0.7,
        "shoulder_width_norm": 0.4,
        "nose_shoulder_offset_x_norm": 0.0,
        "nose_shoulder_offset_y_norm": -1.0,
        "face_shoulder_offset_x_norm": None,
        "face_shoulder_offset_y_norm": None,
        "confidence": 0.8,
        "coordinate_space": "IMAGE_NORMALIZED",
        "horizontal_sign_convention": (
            "SCREEN_LEFT_NEGATIVE_SCREEN_RIGHT_POSITIVE"
        ),
        "shoulder_sign_convention": (
            "SUBJECT_RIGHT_SHOULDER_LOWER_POSITIVE_"
            "SUBJECT_LEFT_SHOULDER_LOWER_NEGATIVE"
        ),
        "failure_reason": "FACE_NOT_DETECTED",
        "status_codes": ["SHOULDERS_AVAILABLE", "FACE_NOT_DETECTED"],
    }


def temporal():
    return {
        "delta_time_seconds": None,
        "shoulder_center_displacement_norm": None,
        "shoulder_center_velocity_norm_per_sec": None,
        "shoulder_tilt_delta_deg": None,
        "shoulder_tilt_velocity_deg_per_sec": None,
        "shoulder_width_delta_norm": None,
        "shoulder_width_change_rate_per_sec": None,
        "nose_offset_x_delta_norm": None,
        "nose_offset_y_delta_norm": None,
        "face_offset_x_delta_norm": None,
        "face_offset_y_delta_norm": None,
    }


class PostureRawValidatorTests(unittest.TestCase):
    def test_selected_candidate_uses_selected_index(self):
        target = {
            "selected_candidate_index": 1,
            "candidates": [
                {"candidate_index": 0, "name": "background"},
                {"candidate_index": 1, "name": "target"},
            ],
        }
        self.assertEqual(_selected_candidate(target)["name"], "target")

    def test_missing_selected_candidate_is_not_substituted(self):
        target = {
            "selected_candidate_index": 4,
            "candidates": [{"candidate_index": 0}],
        }
        self.assertIsNone(_selected_candidate(target))

    def test_face_box_is_normalized_and_geometry_matched(self):
        frame = {
            "frame_width": 1000,
            "frame_height": 500,
            "face_bounding_box": {
                "min_x": 400,
                "max_x": 600,
                "min_y": 100,
                "max_y": 300,
            },
        }
        candidate = {
            "nose": {"x": 0.5, "y": 0.4},
            "shoulder_center": {"x": 0.5, "y": 0.8},
            "shoulder_width": 0.4,
        }
        box, center = _frame_face_geometry(frame, candidate)
        self.assertEqual(
            box,
            {"min_x": 0.4, "min_y": 0.2, "max_x": 0.6, "max_y": 0.6},
        )
        self.assertAlmostEqual(center["x"], 0.5)
        self.assertAlmostEqual(center["y"], 0.4)

    def test_csv_preserves_prefix_bom_and_nulls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prefix = root / "prefix.csv"
            with prefix.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=["sample_index", "timestamp_ms", "nose_x"],
                )
                writer.writeheader()
                writer.writerow(
                    {"sample_index": 0, "timestamp_ms": 0, "nose_x": 0.5}
                )
            row = {
                "timestamp_ms": 0,
                "target_id": "TARGET_001",
                "candidate_count": 1,
                "selected_candidate_index": 0,
                "posture_raw": raw(),
                "posture_temporal": temporal(),
                "posture_jump_candidates": [],
                "head_pose_reference": {
                    "available": False,
                    "yaw_deg": None,
                    "pitch_deg": None,
                    "roll_deg": None,
                },
            }
            output = root / "posture.csv"
            _write_csv(output, prefix, [row])
            data = output.read_bytes()
            self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
            with output.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                result = list(reader)
                self.assertEqual(
                    reader.fieldnames[:3],
                    ["sample_index", "timestamp_ms", "nose_x"],
                )
                self.assertEqual(reader.fieldnames[3:], POSTURE_CSV_FIELDS)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["face_shoulder_offset_x_norm"], "")
            self.assertEqual(result[0]["raw_yaw_deg_reference"], "")

    def test_json_serialization_rejects_non_finite(self):
        with self.assertRaises(ValueError):
            json.dumps({"bad": float("nan")}, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
