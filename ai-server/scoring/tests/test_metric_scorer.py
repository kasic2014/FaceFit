from copy import deepcopy
import unittest

from support import metric_input, profile
from engine.metric_scorer import score_metric


class MetricScorerTests(unittest.TestCase):
    def score(self, metric_id, value, mutate=None):
        row, rule = metric_input(metric_id, value)
        if mutate: mutate(rule)
        return score_metric(row, rule, profile()["scoreScale"])

    def test_piecewise_boundaries_and_interpolation(self):
        metric = "HEAD_RELATIVE_YAW_ABS_P95_DEG"
        self.assertEqual(self.score(metric, 0)["score"], 100)
        self.assertEqual(self.score(metric, 20)["score"], 60)
        self.assertEqual(self.score(metric, 10)["score"], 80)
        self.assertEqual(self.score(metric, 50)["score"], 0)

    def test_higher_and_lower_monotonic_shapes_use_anchors_only(self):
        metric = "HEAD_RELATIVE_YAW_ABS_P95_DEG"
        lower = [self.score(metric, value)["score"] for value in (0, 10, 20, 30, 50)]
        self.assertEqual(lower, sorted(lower, reverse=True))
        higher = [self.score(metric, value, lambda rule: rule.update(anchors=[{"value": 0, "score": 0}, {"value": 50, "score": 100}]))["score"] for value in (0, 10, 20, 30, 50)]
        self.assertEqual(higher, sorted(higher))

    def test_target_range_shape(self):
        scores = [self.score("SPEECH_WORDS_PER_MINUTE", value)["score"] for value in (40, 100, 160, 220)]
        self.assertEqual(scores, [0, 100, 100, 0])

    def test_clamp_and_nonclamp(self):
        self.assertEqual(self.score("HEAD_RELATIVE_YAW_ABS_P95_DEG", 100)["score"], 0)
        result = self.score("POSTURE_RELATIVE_SHOULDER_TILT_ABS_P95_DEG", 11)
        self.assertEqual(result["scoreStatus"], "NOT_SCORABLE")
        self.assertIsNone(result["score"])

    def test_band_inclusive_exclusive_boundaries(self):
        metric = "HEAD_RELATIVE_PITCH_ABS_P95_DEG"
        self.assertEqual(self.score(metric, 9.999)["score"], 100)
        self.assertEqual(self.score(metric, 10)["score"], 60)
        self.assertEqual(self.score(metric, 25)["score"], 60)
        self.assertEqual(self.score(metric, 25.001)["score"], 0)

    def test_band_unmatched(self):
        result = self.score("SPEECH_FILLER_CANDIDATES_PER_MINUTE", 1.5)
        self.assertEqual(result["scoreStatus"], "NOT_SCORABLE")
        self.assertIsNone(result["score"])

    def test_round_half_up(self):
        result = self.score("HEAD_RELATIVE_YAW_ABS_P95_DEG", 0.00125)
        self.assertEqual(result["score"], 100)
        row, rule = metric_input("HEAD_RELATIVE_YAW_ABS_P95_DEG", 1)
        rule["anchors"] = [{"value": 0, "score": 0}, {"value": 8, "score": 1}]
        self.assertEqual(score_metric(row, rule, {"minimum": 0, "maximum": 100, "decimalPlaces": 2})["score"], 0.13)

    def test_nan_and_infinity_blocked(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                result = self.score("HEAD_RELATIVE_YAW_ABS_P95_DEG", value)
                self.assertEqual(result["scoreStatus"], "NOT_SCORABLE")
                self.assertIsNone(result["score"])

    def test_quality_failure_is_not_zero(self):
        row, rule = metric_input("HEAD_RELATIVE_YAW_ABS_P95_DEG", 10, sampleCount=0)
        result = score_metric(row, rule, profile()["scoreScale"])
        self.assertEqual(result["scoreStatus"], "NOT_SCORABLE")
        self.assertIsNone(result["score"])


if __name__ == "__main__":
    unittest.main()
