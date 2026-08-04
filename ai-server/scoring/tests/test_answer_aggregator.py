import unittest

from support import profile
from engine.answer_aggregator import aggregate_answer


class AnswerAggregatorTests(unittest.TestCase):
    def axes(self):
        return [
            {"axis":"GAZE_HEAD","scoreStatus":"SCORED","score":100},
            {"axis":"POSTURE","scoreStatus":"SCORED","score":50},
            {"axis":"SPEECH_DELIVERY","scoreStatus":"SCORED","score":0},
        ]

    def test_overall_is_disabled_by_default(self):
        result = aggregate_answer("ANS_900001", self.axes(), profile())
        self.assertFalse(result["overallScoreAvailable"])
        self.assertIsNone(result["overallScore"])

    def test_explicit_overall_uses_axis_weights(self):
        candidate = profile()
        candidate["answerAggregation"]["overallEnabled"] = True
        candidate["overallRule"] = {"enabled":True,"requiredAxes":["GAZE_HEAD","POSTURE","SPEECH_DELIVERY"],"axisWeights":{"GAZE_HEAD":0.5,"POSTURE":0.25,"SPEECH_DELIVERY":0.25},"minimumAxisCoverageRatio":1}
        result = aggregate_answer("ANS_900001", self.axes(), candidate)
        self.assertTrue(result["overallScoreAvailable"])
        self.assertEqual(result["overallScore"], 62.5)


if __name__ == "__main__":
    unittest.main()
