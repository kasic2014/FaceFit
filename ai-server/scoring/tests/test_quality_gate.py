import unittest

from engine.quality_gate import evaluate_quality


class QualityGateTests(unittest.TestCase):
    def setUp(self):
        self.gate = {"minimumSampleCount": 10, "minimumAvailabilityRatio": 0.8, "maximumMissingRatio": 0.2, "minimumAnswerDurationMs": 1000, "minimumWordCount": 5, "minimumVoicedFrameRatio": 0.4, "timestampValidityRequired": True}
        self.quality = {"sampleCount": 10, "availabilityRatio": 0.8, "missingRatio": 0.2, "answerDurationMs": 1000, "wordCount": 5, "voicedFrameRatio": 0.4, "timestampValid": True}

    def test_all_exact_boundaries_pass(self):
        self.assertTrue(evaluate_quality(self.quality, self.gate)["passed"])

    def test_each_failure_code(self):
        cases = {
            "sampleCount": (9, "INSUFFICIENT_DATA"), "availabilityRatio": (0.79, "LOW_AVAILABILITY"),
            "missingRatio": (0.21, "HIGH_MISSING_RATIO"), "answerDurationMs": (999, "ANSWER_TOO_SHORT"),
            "wordCount": (4, "INSUFFICIENT_WORDS"), "voicedFrameRatio": (0.39, "INSUFFICIENT_VOICED_FRAMES"),
            "timestampValid": (False, "INVALID_TIMESTAMP"),
        }
        for field, (value, code) in cases.items():
            with self.subTest(field=field):
                row = dict(self.quality); row[field] = value
                self.assertIn(code, evaluate_quality(row, self.gate)["failureReasons"])

    def test_missing_values_fail_not_zero(self):
        row = dict(self.quality); row["sampleCount"] = None
        result = evaluate_quality(row, self.gate)
        self.assertFalse(result["passed"])
        self.assertEqual(result["qualityStatus"], "INSUFFICIENT_DATA")


if __name__ == "__main__":
    unittest.main()
