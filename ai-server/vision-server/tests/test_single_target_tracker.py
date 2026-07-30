from __future__ import annotations

import unittest

from app.vision.single_target_tracker import SingleTargetTracker
from app.vision.target_tracking_models import TargetStatus, TrackingConfiguration
from tests.test_target_candidate_matcher import candidate


class SingleTargetTrackerTests(unittest.TestCase):
    def setUp(self):
        self.tracker = SingleTargetTracker()
        self.tracker.initialize(candidate(), 0)

    def test_smooth_motion_tracks_same_id(self):
        row, _ = self.tracker.update(200, [candidate(x=.51)])
        self.assertEqual(row["target_status"], TargetStatus.TARGET_TRACKED.value)
        self.assertEqual(row["target_id"], "TARGET_001")

    def test_background_candidate_does_not_replace_target(self):
        row, _ = self.tracker.update(200, [candidate(0, .51), candidate(1, .85)])
        self.assertEqual(row["selected_candidate_index"], 0)
        self.assertEqual(row["target_id"], "TARGET_001")

    def test_single_missing_frame_is_temporarily_lost(self):
        row, events = self.tracker.update(200, [])
        self.assertEqual(row["target_status"], TargetStatus.TARGET_TEMPORARILY_LOST.value)
        self.assertEqual(events[0]["event_type"], "TARGET_TEMPORARILY_LOST")

    def test_reacquisition_retains_id(self):
        self.tracker.update(200, [])
        row, events = self.tracker.update(400, [candidate(x=.51)])
        self.assertEqual(row["target_status"], TargetStatus.TARGET_REACQUIRED.value)
        self.assertEqual(row["target_id"], "TARGET_001")
        self.assertTrue(row["reacquired"])

    def test_loss_timeout_does_not_switch_to_far_person(self):
        tracker = SingleTargetTracker(TrackingConfiguration(maximum_lost_duration_ms=500))
        tracker.initialize(candidate(), 0)
        tracker.update(200, [candidate(0, .95)])
        row, _ = tracker.update(800, [candidate(0, .95)])
        self.assertEqual(row["target_status"], TargetStatus.TARGET_LOST.value)
        self.assertIsNone(row["selected_candidate_index"])

    def test_ambiguous_margin_prevents_selection(self):
        row, events = self.tracker.update(200, [candidate(0, .51), candidate(1, .49)])
        self.assertEqual(row["target_status"], TargetStatus.MULTIPLE_PERSON_AMBIGUOUS.value)
        self.assertIsNone(row["selected_candidate_index"])
        self.assertEqual(events[0]["details"]["ambiguity_reason"], "CANDIDATE_SCORE_MARGIN_TOO_SMALL")

    def test_initial_selection_prefers_persistent_central_complete_candidate(self):
        tracker = SingleTargetTracker()
        frames = [
            (0, [candidate(0, .5), candidate(1, .85)]),
            (200, [candidate(0, .51), candidate(1, .2)]),
            (400, [candidate(0, .52), candidate(1, .9)]),
        ]
        self.assertEqual(tracker.select_initial_target(frames).candidate_index, 0)

    def test_no_candidates_stays_uninitialized(self):
        tracker = SingleTargetTracker()
        self.assertIsNone(tracker.select_initial_target([(0, [])]))


if __name__ == "__main__":
    unittest.main()
