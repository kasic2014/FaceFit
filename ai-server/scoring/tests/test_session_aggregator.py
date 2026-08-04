import unittest

from engine.session_aggregator import aggregate_session_scores


def row(score, duration, samples, status="SCORED"):
    return {"score": score, "scoreStatus": status, "answerDurationMs": duration, "validSampleCount": samples}


class SessionAggregatorTests(unittest.TestCase):
    def rule(self, method, **updates):
        value = {"method": method, "minimumScorableAnswerCount": 1, "minimumAnswerCoverageRatio": 0.5, "allowPartialScore": True}
        value.update(updates)
        return value

    def test_equal(self):
        self.assertEqual(aggregate_session_scores([row(100, 1, 1), row(0, 3, 9)], self.rule("EQUAL"), 2)["score"], 50)

    def test_duration_weighted(self):
        self.assertEqual(aggregate_session_scores([row(100, 1, 1), row(0, 3, 9)], self.rule("DURATION_WEIGHTED"), 2)["score"], 25)

    def test_valid_sample_weighted(self):
        self.assertEqual(aggregate_session_scores([row(100, 1, 1), row(0, 3, 9)], self.rule("VALID_SAMPLE_WEIGHTED"), 2)["score"], 10)

    def test_partial(self):
        result = aggregate_session_scores([row(100, 1, 1), row(None, 1, 1, "NOT_SCORABLE")], self.rule("EQUAL"), 2)
        self.assertEqual(result["scoreStatus"], "PARTIAL")
        self.assertEqual(result["answerCoverageRatio"], 0.5)

    def test_minimum_answer_count_and_coverage(self):
        rows = [row(100, 1, 1), row(None, 1, 1, "NOT_SCORABLE")]
        self.assertEqual(aggregate_session_scores(rows, self.rule("EQUAL", minimumScorableAnswerCount=2), 2)["scoreStatus"], "NOT_SCORABLE")
        self.assertEqual(aggregate_session_scores(rows, self.rule("EQUAL", minimumAnswerCoverageRatio=0.75), 2)["scoreStatus"], "NOT_SCORABLE")

    def test_variation_is_numeric_not_interpreted(self):
        result = aggregate_session_scores([row(0, 1, 1), row(100, 1, 1)], self.rule("EQUAL"), 2)
        self.assertEqual(result["scoreVariation"], 50)
        self.assertIn("not a psychological", result["limitations"][0])


if __name__ == "__main__":
    unittest.main()
