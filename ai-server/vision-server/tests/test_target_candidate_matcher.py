from __future__ import annotations

import unittest

from app.vision.target_candidate_matcher import (
    calculate_bbox_iou, calculate_face_pose_consistency, calculate_tracking_match,
)
from app.vision.target_tracking_models import TargetCandidate


def candidate(index=0, x=.5, width=.4, face=True):
    box = {"min_x": x-.1, "min_y": .2, "max_x": x+.1, "max_y": .5} if face else None
    return TargetCandidate(
        index, index if face else None, index, box,
        {"x": x, "y": .35} if face else None,
        {"x": x, "y": .4}, {"x": x-width/2, "y": .7}, {"x": x+width/2, "y": .7},
        {"x": x, "y": .7}, width, .95, .1 if face else None,
    )


class TargetCandidateMatcherTests(unittest.TestCase):
    def test_iou_identical_and_disjoint(self):
        box = candidate().face_bounding_box
        self.assertEqual(calculate_bbox_iou(box, box), 1)
        self.assertEqual(calculate_bbox_iou(box, candidate(x=.9).face_bounding_box), 0)

    def test_same_candidate_has_low_cost(self):
        self.assertAlmostEqual(calculate_tracking_match(candidate(), candidate()).cost, 0)

    def test_large_motion_has_higher_cost(self):
        reference = candidate()
        self.assertGreater(
            calculate_tracking_match(reference, candidate(x=.8)).cost,
            calculate_tracking_match(reference, candidate(x=.52)).cost,
        )

    def test_small_bbox_change_retains_match(self):
        self.assertLess(calculate_tracking_match(candidate(), candidate(width=.38)).cost, .2)

    def test_missing_face_can_match_from_pose(self):
        result = calculate_tracking_match(candidate(), candidate(face=False, x=.51))
        self.assertLess(result.cost, .1)

    def test_face_pose_consistency_accepts_normal_geometry(self):
        item = candidate()
        self.assertIsNotNone(calculate_face_pose_consistency(
            item.face_center, item.face_bounding_box, item.nose, item.shoulder_center, item.shoulder_width
        ))

    def test_face_pose_consistency_rejects_face_below_shoulders(self):
        item = candidate()
        self.assertIsNone(calculate_face_pose_consistency(
            {"x": .5, "y": .9}, item.face_bounding_box, item.nose, item.shoulder_center, item.shoulder_width
        ))


if __name__ == "__main__":
    unittest.main()
