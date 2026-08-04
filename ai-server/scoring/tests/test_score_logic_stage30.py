from copy import deepcopy
import json
from pathlib import Path
import random
import tempfile
import unittest

from support import ROOT, inventory, payload, profile
from adapters.speech_metric_adapter import adapt_speech_answer
from adapters.vision_metric_adapter import adapt_vision_answer
from engine.profile_validator import profile_hash
from engine.scoring_errors import ScoringError
from engine.scoring_service import disabled_result, score_payload
from engine.strict_json_writer import strict_json_bytes, write_json_atomic


class Stage30Tests(unittest.TestCase):
    def setUp(self):
        self.inventory = inventory(); self.profile = profile(); self.payload = payload()

    def test_disabled_contract(self):
        self.assertEqual(disabled_result("SES_000001"), {"sessionId":"SES_000001","scoringMode":"DISABLED","scoringAvailable":False,"scoreStatus":"NOT_AVAILABLE","score":None,"reason":"THRESHOLD_EVIDENCE_NOT_APPROVED"})

    def test_experimental_requires_explicit_opt_in(self):
        with self.assertRaises(ScoringError) as caught:
            score_payload(self.payload, self.profile, self.inventory)
        self.assertEqual(caught.exception.code, "EXPERIMENTAL_SCORING_NOT_EXPLICITLY_ENABLED")

    def test_real_session_synthetic_scoring_is_blocked(self):
        candidate = deepcopy(self.payload); candidate["sessionId"] = "SES_000001"
        for row in candidate["metricInputs"]: row["sessionId"] = "SES_000001"
        with self.assertRaises(ScoringError):
            score_payload(candidate, self.profile, self.inventory, allow_experimental=True)

    def test_production_fails_closed(self):
        with self.assertRaises(ScoringError) as caught:
            score_payload(self.payload, self.profile, self.inventory, mode="PRODUCTION")
        self.assertEqual(caught.exception.code, "SCORING_PROFILE_NOT_APPROVED")

    def test_duplicate_metric_input_is_rejected(self):
        candidate = deepcopy(self.payload)
        candidate["metricInputs"].append(deepcopy(candidate["metricInputs"][0]))
        with self.assertRaises(ScoringError) as caught:
            score_payload(candidate, self.profile, self.inventory, allow_experimental=True)
        self.assertEqual(caught.exception.code, "SCORING_INPUT_INVALID")

    def test_synthetic_result_has_provenance_and_no_overall(self):
        result = score_payload(self.payload, self.profile, self.inventory, allow_experimental=True)
        self.assertTrue(result["scoringAvailable"])
        self.assertEqual(result["profileHash"], profile_hash(self.profile))
        self.assertEqual(result["evidenceIds"], ["EVIDENCE_TEST_FIXTURE_ONLY"])
        self.assertFalse(result["overallScoreAvailable"])
        self.assertIsNone(result["overallScore"])
        self.assertEqual([row["answerId"] for row in result["answers"]], ["ANS_900001", "ANS_900002", "ANS_900003", "ANS_900004"])

    def test_same_input_same_result(self):
        first = score_payload(self.payload, self.profile, self.inventory, allow_experimental=True)
        second = score_payload(deepcopy(self.payload), deepcopy(self.profile), deepcopy(self.inventory), allow_experimental=True)
        self.assertEqual(first, second)

    def test_scores_and_coverages_remain_bounded_fixed_seed(self):
        random.seed(3001)
        base = deepcopy(self.payload)
        for _ in range(50):
            candidate = deepcopy(base)
            for row in candidate["metricInputs"]:
                if row["metricId"] == "HEAD_RELATIVE_YAW_ABS_P95_DEG": row["value"] = random.uniform(0, 50)
            result = score_payload(candidate, self.profile, self.inventory, allow_experimental=True)
            for answer in result["answers"]:
                for metric in answer["metricScores"]:
                    if metric["score"] is not None: self.assertTrue(0 <= metric["score"] <= 100)
                for axis in answer["axisScores"].values(): self.assertTrue(0 <= axis["coverageRatio"] <= 1)

    def test_strict_json_blocks_nonfinite_sensitive_and_absolute_path(self):
        for bad in ({"x": float("nan")}, {"participantId":"PTC_1"}, {"x":"C:\\private\\file.wav"}):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError): strict_json_bytes(bad)

    def test_atomic_writer_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            write_json_atomic(path, {"score": None, "status": "NOT_SCORABLE"})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"score": None, "status": "NOT_SCORABLE"})

    def test_speech_adapter_uses_registered_paths_without_transcript(self):
        answer = {"answerId":"ANS_900001","status":"COMPLETE","input":{"durationMs":30000,"sampleCount":480000},"speakingRate":{"wordCount":50,"wordsPerMinute":100,"articulationWordsPerMinute":150},"timestampPauses":{"totalInterWordGapMs":1000,"p90InterWordGapMs":200},"fillerCandidateSummary":{"fillerCandidatesPerMinute":2},"volume":{"rmsDbfs":-30,"peakDbfs":-2,"clippingSampleRatio":0},"pitch":{"voicedFrameCount":100,"totalFrameCount":200,"voicedFrameRatio":0.5,"f0RangeHz":80},"warnings":[]}
        rows = adapt_speech_answer("SES_900001", answer, self.inventory)
        self.assertEqual(len(rows), 10)
        self.assertNotIn("transcriptText", json.dumps(rows))
        self.assertEqual(next(row for row in rows if row["metricId"] == "SPEECH_WORDS_PER_MINUTE")["value"], 100)

    def test_vision_adapter_excludes_quality_metrics(self):
        aggregate = {"duration_ms":30000,"head_pose":{"relative_yaw_deg":{"absolute_p95":5,"count":100},"relative_pitch_deg":{"absolute_p95":4,"count":100},"relative_roll_deg":{"absolute_p95":3,"count":100},"availability":{"available":True,"availability_ratio":1}},"posture":{"relative_shoulder_tilt_deg":{"absolute_p95":2,"count":100},"shoulder_center_velocity_norm_per_sec":{"p95":0.1,"count":100},"relative_nose_shoulder_offset_x_norm":{"absolute_p95":0.05,"count":100},"shoulder_availability":{"available":True,"availability_ratio":1}},"data_quality":{"total_frame_count":100,"head_pose_availability_ratio":1,"posture_availability_ratio":1},"errors":[]}
        rows = adapt_vision_answer("SES_900001", "ANS_900001", aggregate, self.inventory)
        self.assertEqual(len(rows), 6)
        self.assertFalse(any(row["metricId"].startswith("QUALITY_") for row in rows))


if __name__ == "__main__":
    unittest.main()
