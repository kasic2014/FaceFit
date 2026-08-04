import unittest

from support import ROOT
from engine.axis_aggregator import aggregate_axis


def row(metric_id, score, weight, status="SCORED"):
    return {"metricId": metric_id, "axis": "GAZE_HEAD", "score": score, "weight": weight, "scoreStatus": status}


class AxisAggregatorTests(unittest.TestCase):
    def rule(self, **updates):
        value = {"axis": "GAZE_HEAD", "minimumCoverageRatio": 0.5, "renormalizeAvailableWeights": True, "allowPartialScore": True, "requiredMetricIds": []}
        value.update(updates)
        return value

    def test_weighted_average_and_full_coverage(self):
        result = aggregate_axis([row("A", 100, 0.25), row("B", 50, 0.75)], self.rule(), 2)
        self.assertEqual(result["score"], 62.5)
        self.assertEqual(result["scoreStatus"], "SCORED")
        self.assertEqual(result["coverageRatio"], 1)

    def test_partial_renormalization(self):
        result = aggregate_axis([row("A", 100, 0.5), row("B", None, 0.5, "NOT_SCORABLE")], self.rule(), 2)
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["scoreStatus"], "PARTIAL")
        self.assertEqual(result["coverageRatio"], 0.5)

    def test_no_renormalization_is_not_scorable(self):
        result = aggregate_axis([row("A", 100, 0.5), row("B", None, 0.5, "NOT_SCORABLE")], self.rule(renormalizeAvailableWeights=False), 2)
        self.assertEqual(result["scoreStatus"], "NOT_SCORABLE")
        self.assertIsNone(result["score"])

    def test_coverage_below_minimum(self):
        result = aggregate_axis([row("A", 100, 0.4), row("B", None, 0.6, "NOT_SCORABLE")], self.rule(minimumCoverageRatio=0.5), 2)
        self.assertEqual(result["scoreStatus"], "NOT_SCORABLE")

    def test_required_metric_missing(self):
        result = aggregate_axis([row("A", 100, 0.5), row("B", None, 0.5, "NOT_SCORABLE")], self.rule(requiredMetricIds=["B"]), 2)
        self.assertEqual(result["scoreStatus"], "NOT_SCORABLE")
        self.assertEqual(result["missingRequiredMetricIds"], ["B"])

    def test_weighted_score_stays_within_input_range(self):
        for left in range(0, 101, 10):
            for right in range(0, 101, 10):
                score = aggregate_axis([row("A", left, 0.3), row("B", right, 0.7)], self.rule(), 4)["score"]
                self.assertGreaterEqual(score, min(left, right))
                self.assertLessEqual(score, max(left, right))

    def test_unsupported_unweighted_metric_does_not_change_coverage(self):
        rows = [row("A", 100, 1), {"metricId": "UNKNOWN", "axis": "GAZE_HEAD", "score": None, "weight": None, "scoreStatus": "UNSUPPORTED"}]
        result = aggregate_axis(rows, self.rule(), 2)
        self.assertEqual(result["coverageRatio"], 1)
        self.assertEqual(result["score"], 100)


if __name__ == "__main__":
    unittest.main()
