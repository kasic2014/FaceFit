from __future__ import annotations

import unittest

from app.vision.head_pose_metrics import (
    calculate_angular_deltas, calculate_axis_summary,
    calculate_reprojection_summary, detect_angular_jump_candidates,
)
from app.vision.head_pose_models import HeadPoseConfiguration


def row(timestamp, yaw=None, pitch=None, roll=None):
    return {"timestamp_ms":timestamp,"target_id":"TARGET_001","head_pose":{
        "available":yaw is not None,"yaw_deg":yaw,"pitch_deg":pitch,"roll_deg":roll,"confidence":.8,
    }}


class HeadPoseMetricsTests(unittest.TestCase):
    def test_summary_and_empty(self):
        summary = calculate_axis_summary([1,2,3,None])
        self.assertEqual(summary["median"],2)
        self.assertAlmostEqual(summary["standard_deviation"],.81649658)
        self.assertIsNone(calculate_axis_summary([])["mean"])
        self.assertEqual(calculate_reprojection_summary([])["count"],0)

    def test_deltas_do_not_bridge_missing(self):
        deltas = calculate_angular_deltas([row(0,0,0,0),row(200,1,2,3),row(400),row(600,10,10,10)])
        self.assertEqual(deltas[1],{"yaw_delta_deg":1,"pitch_delta_deg":2,"roll_delta_deg":3})
        self.assertIsNone(deltas[2]["yaw_delta_deg"])
        self.assertIsNone(deltas[3]["yaw_delta_deg"])

    def test_jump_is_diagnostic(self):
        rows = [row(i*200,value,0,0) for i,value in enumerate((0,1,2,3,4,40,41))]
        events, diagnostics = detect_angular_jump_candidates(rows,HeadPoseConfiguration(jump_fallback_threshold_deg=20))
        yaw_events = [event for event in events if event["details"]["axis"]=="yaw"]
        self.assertEqual(len(yaw_events),1)
        self.assertEqual(yaw_events[0]["details"]["status"],"candidate")
        self.assertIn("threshold_deg",diagnostics["yaw"])

    def test_insufficient_data(self):
        events, diagnostics = detect_angular_jump_candidates([row(0,0,0,0),row(200,1,1,1)])
        self.assertEqual(events,[])
        self.assertEqual(diagnostics["yaw"]["method"],"insufficient_data")


if __name__ == "__main__":
    unittest.main()
