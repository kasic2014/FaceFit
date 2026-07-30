from __future__ import annotations

import unittest

from app.vision.interval_event_aggregator import aggregate_interval_events
from app.vision.interval_models import AnalysisInterval


class IntervalEventAggregatorTests(unittest.TestCase):
    def test_start_included_end_excluded_and_types_counted(self):
        interval = AnalysisInterval("A", 100, 300)
        head = [
            {
                "timestamp_ms": 100,
                "target_id": "TARGET_001",
                "event_type": "HEAD_JUMP",
            },
            {
                "timestamp_ms": 300,
                "target_id": "TARGET_001",
                "event_type": "HEAD_JUMP",
            },
        ]
        posture = [
            {
                "timestamp_ms": 200,
                "target_id": "TARGET_001",
                "event_type": "POSTURE_JUMP",
            },
            {
                "timestamp_ms": 250,
                "target_id": "TARGET_002",
                "event_type": "IGNORED",
            },
        ]
        result = aggregate_interval_events(
            interval,
            head_pose_events=head,
            posture_events=posture,
        )
        self.assertEqual(result.head_pose_jump_candidate_count, 1)
        self.assertEqual(result.posture_jump_candidate_count, 1)
        self.assertEqual(
            result.event_type_counts,
            {"HEAD_JUMP": 1, "POSTURE_JUMP": 1},
        )
        self.assertEqual(result.event_timestamps_ms, (100, 200))
        self.assertEqual(result.ignored_target_mismatch_count, 1)


if __name__ == "__main__":
    unittest.main()
