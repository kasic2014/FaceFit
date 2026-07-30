from __future__ import annotations

import unittest

from app.vision.target_tracking_validator import build_target_candidates


def landmark(index, x, y, confidence=.95):
    return {"index": index, "x": x, "y": y, "z": 0, "visibility": confidence, "presence": confidence}


class TargetTrackingValidatorTests(unittest.TestCase):
    def test_builds_multiple_paired_candidates(self):
        faces = {"faces": [
            {"face_index": 0, "normalized_bounding_box": {"min_x": .35, "min_y": .2, "max_x": .55, "max_y": .5}},
            {"face_index": 1, "normalized_bounding_box": {"min_x": .7, "min_y": .2, "max_x": .9, "max_y": .5}},
        ]}
        poses = {"poses": [
            {"pose_index": 0, "landmarks": [landmark(0,.45,.4),landmark(11,.25,.7),landmark(12,.65,.7)]},
            {"pose_index": 1, "landmarks": [landmark(0,.8,.4),landmark(11,.7,.7),landmark(12,.9,.7)]},
        ]}
        result = build_target_candidates(faces, poses)
        self.assertEqual(len(result), 2)
        self.assertEqual({item.face_index for item in result}, {0, 1})

    def test_incomplete_pose_is_not_initialization_ready(self):
        result = build_target_candidates(
            {"faces": []},
            {"poses": [{"pose_index": 0, "landmarks": [landmark(0,.5,.4)]}]},
        )
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0].initialization_ready)

    def test_face_pose_mismatch_is_not_forced(self):
        faces = {"faces": [{"face_index": 0, "normalized_bounding_box": {"min_x": .8, "min_y": .8, "max_x": .9, "max_y": .9}}]}
        poses = {"poses": [{"pose_index": 0, "landmarks": [landmark(0,.5,.4),landmark(11,.3,.7),landmark(12,.7,.7)]}]}
        self.assertIsNone(build_target_candidates(faces, poses)[0].face_index)


if __name__ == "__main__":
    unittest.main()
