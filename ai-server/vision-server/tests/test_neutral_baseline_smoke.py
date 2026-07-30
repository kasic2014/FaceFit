from __future__ import annotations

import unittest

from app.vision.neutral_baseline_smoke import (
    NeutralBaselineSmokeError,
    build_baseline_frames,
)


def rows(timestamp: int):
    target = {
        "timestamp_ms": timestamp,
        "target_id": "TARGET_001",
        "target_status": "TARGET_TRACKED",
        "candidate_count": 1,
        "target_confidence": 0.9,
    }
    head = {
        "timestamp_ms": timestamp,
        "target_id": "TARGET_001",
        "head_pose": {
            "available": True,
            "yaw_deg": timestamp / 100.0,
            "pitch_deg": 0.0,
            "roll_deg": 0.0,
            "confidence": 0.9,
        },
        "angular_jump_axes": [],
    }
    posture = {
        "timestamp_ms": timestamp,
        "target_id": "TARGET_001",
        "posture_raw": {"available": True, "confidence": 0.9},
        "posture_temporal": {},
        "posture_jump_candidates": [],
    }
    return target, head, posture


class NeutralBaselineSmokeTests(unittest.TestCase):
    def test_exact_linkage_and_real_dt_head_velocity(self):
        first = rows(0)
        second = rows(200)
        built = build_baseline_frames(
            [first[0], second[0]],
            [first[1], second[1]],
            [first[2], second[2]],
        )
        self.assertIsNone(built[0].head_angular_velocity_deg_per_sec)
        self.assertEqual(built[1].head_angular_velocity_deg_per_sec, 10.0)

    def test_missing_frame_resets_head_velocity(self):
        first = rows(0)
        missing = rows(200)
        last = rows(400)
        missing[1]["head_pose"]["available"] = False
        built = build_baseline_frames(
            [first[0], missing[0], last[0]],
            [first[1], missing[1], last[1]],
            [first[2], missing[2], last[2]],
        )
        self.assertIsNone(built[2].head_angular_velocity_deg_per_sec)

    def test_alignment_mismatch_fails(self):
        first = rows(0)
        with self.assertRaises(NeutralBaselineSmokeError) as context:
            build_baseline_frames([first[0]], [], [first[2]])
        self.assertEqual(
            context.exception.code,
            "STAGE_OUTPUT_ALIGNMENT_MISMATCH",
        )


if __name__ == "__main__":
    unittest.main()
