from __future__ import annotations

import unittest

import numpy as np

from app.vision.posture_overlay_renderer import render_posture_overlay_frame


class PostureOverlayRendererTests(unittest.TestCase):
    def test_render_does_not_mutate_input(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        original = frame.copy()
        row = {
            "timestamp_ms": 0,
            "target_id": "TARGET_001",
            "landmarks": {
                "left_shoulder": {"x": 0.7, "y": 0.7},
                "right_shoulder": {"x": 0.3, "y": 0.71},
                "nose": {"x": 0.5, "y": 0.3},
                "face_center": {"x": 0.5, "y": 0.35},
                "face_bounding_box": {
                    "min_x": 0.4,
                    "max_x": 0.6,
                    "min_y": 0.2,
                    "max_y": 0.5,
                },
            },
            "posture_raw": {
                "available": True,
                "shoulders_available": True,
                "shoulder_center_x": 0.5,
                "shoulder_center_y": 0.705,
                "shoulder_tilt_deg": 1.4,
                "shoulder_height_difference_norm": 0.02,
                "shoulder_width_norm": 0.4,
                "nose_shoulder_offset_x_norm": 0.0,
                "nose_shoulder_offset_y_norm": -1.0,
                "confidence": 0.9,
                "failure_reason": None,
            },
            "posture_jump_candidates": ["SHOULDER_TILT_JUMP_CANDIDATE"],
        }
        rendered = render_posture_overlay_frame(frame, row)
        self.assertTrue(np.array_equal(frame, original))
        self.assertFalse(np.array_equal(rendered, original))


if __name__ == "__main__":
    unittest.main()
