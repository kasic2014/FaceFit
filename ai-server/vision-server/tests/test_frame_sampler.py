from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np


VISION_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(VISION_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(VISION_SERVER_ROOT))

from app.vision import frame_sampler as sampler


class FakeCapture:
    def __init__(self, count: int) -> None:
        self.frames = [
            np.full((8, 10, 3), index, dtype=np.uint8) for index in range(count)
        ]

    def read(self):
        if not self.frames:
            return False, None
        return True, self.frames.pop(0)


class FrameSamplerTests(unittest.TestCase):
    def test_10fps_to_5fps(self) -> None:
        instance = sampler.FrameSampler(FakeCapture(30), 10, 5)
        frames = list(instance)
        self.assertEqual(len(frames), 15)
        self.assertEqual([item.source_frame_index for item in frames], list(range(0, 30, 2)))
        self.assertEqual(frames[-1].timestamp_ms, 2800)

    def test_30fps_to_5fps(self) -> None:
        instance = sampler.FrameSampler(FakeCapture(30), 30, 5)
        frames = list(instance)
        self.assertEqual([item.source_frame_index for item in frames], [0, 6, 12, 18, 24])

    def test_target_above_source_does_not_oversample(self) -> None:
        instance = sampler.FrameSampler(FakeCapture(5), 2, 5)
        frames = list(instance)
        self.assertEqual(len(frames), 5)
        self.assertEqual(instance.effective_analysis_fps, 2)
        self.assertEqual(instance.duplicate_frame_count, 0)

    def test_timestamps_are_integer_and_strict(self) -> None:
        instance = sampler.FrameSampler(FakeCapture(20), 29.97, 15)
        frames = list(instance)
        timestamps = [item.timestamp_ms for item in frames]
        self.assertTrue(all(isinstance(value, int) for value in timestamps))
        self.assertEqual(timestamps, sorted(set(timestamps)))
        self.assertTrue(instance.timestamps_strictly_increasing)

    def test_deterministic_results(self) -> None:
        first = list(sampler.FrameSampler(FakeCapture(31), 30, 7))
        second = list(sampler.FrameSampler(FakeCapture(31), 30, 7))
        self.assertEqual(
            [(item.source_frame_index, item.timestamp_ms) for item in first],
            [(item.source_frame_index, item.timestamp_ms) for item in second],
        )

    def test_summary_counts(self) -> None:
        instance = sampler.FrameSampler(FakeCapture(10), 10, 5)
        list(instance)
        result = instance.summary()
        self.assertEqual(result["decoded_frame_count"], 10)
        self.assertEqual(result["sampled_frame_count"], 5)
        self.assertEqual(result["skipped_frame_count"], 5)
        self.assertEqual(result["duplicate_timestamp_count"], 0)

    def test_fps_boundaries(self) -> None:
        self.assertEqual(sampler.validate_analysis_fps(1), 1)
        self.assertEqual(sampler.validate_analysis_fps(15), 15)

    def test_fps_out_of_range(self) -> None:
        for value in (0, 0.9, 15.1, float("nan"), float("inf")):
            with self.subTest(value=value):
                with self.assertRaises(sampler.FrameSamplingError):
                    sampler.validate_analysis_fps(value)

    def test_invalid_original_fps(self) -> None:
        with self.assertRaises(sampler.FrameSamplingError) as raised:
            sampler.FrameSampler(FakeCapture(1), 0, 5)
        self.assertEqual(raised.exception.code, "VIDEO_FPS_INVALID")

    def test_sample_dimensions(self) -> None:
        frame = next(iter(sampler.FrameSampler(FakeCapture(1), 10, 5)))
        self.assertEqual((frame.width, frame.height), (10, 8))


if __name__ == "__main__":
    unittest.main()
