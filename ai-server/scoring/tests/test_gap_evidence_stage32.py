from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from support import ROOT, inventory, read


EXPECTED_STATUS = "scoring_gap_evidence_research_ready_with_access_limitations"
EXPECTED_GAPS = {
    "KOREAN_SPEECH_RATE", "KOREAN_ARTICULATION_RATE", "KOREAN_PAUSE_DURATION",
    "KOREAN_FILLER_VALIDATION", "WEBCAM_HEAD_POSE_BEHAVIOR", "HEAD_POSE_VS_EYE_GAZE",
    "SEATED_SHOULDER_POSTURE", "SHOULDER_CENTER_MOVEMENT", "MICROPHONE_LOUDNESS_NORMALIZATION",
    "HUMAN_BEHAVIOR_RUBRIC", "INTER_RATER_RELIABILITY", "MULTI_SESSION_DISTRIBUTION",
    "THRESHOLD_SENSITIVITY", "AXIS_WEIGHT_VALIDATION", "BIAS_AND_FAIRNESS_VALIDATION",
    "VALIDATION_DESIGN",
}


def _load_validator():
    path = ROOT / "scripts" / "validate_stage32_gap_research.py"
    spec = importlib.util.spec_from_file_location("validate_stage32_gap_research", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _put(payload: dict, dotted_path: str, value) -> None:
    target = payload
    components = dotted_path.split(".")
    for component in components[:-1]:
        target = target.setdefault(component, {})
    target[components[-1]] = value


class GapEvidenceStage32Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = _load_validator()
        cls.catalog = read("evidence/source-catalog-stage32-v1.json")
        cls.records = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((ROOT / "evidence" / "records").glob("GAP_*.json"))
        ]
        cls.matrix = read("mappings/metric-evidence-matrix-v1.json")
        cls.readiness = read("mappings/threshold-readiness-v1.json")
        cls.gaps = read("mappings/gap-source-mapping-v1.json")
        cls.rubric = read("docs/human-behavior-rubric-draft-v1.json")
        cls.pilot = read("docs/pilot-data-collection-spec-v1.json")
        cls.metric_ids = {row["metricId"] for row in inventory()["metrics"]}

    def test_catalog_and_common_records_cover_exact_acquired_eighteen(self):
        catalog_ids = [row["evidenceId"] for row in self.catalog["sources"]]
        record_ids = [row["evidenceId"] for row in self.records]
        self.assertEqual(18, self.catalog["sourceCount"])
        self.assertEqual(18, len(catalog_ids))
        self.assertEqual(18, len(set(catalog_ids)))
        self.assertEqual(set(catalog_ids), set(record_ids))

    def test_file_integrity_and_access_failures_are_explicit(self):
        by_id = {row["evidenceId"]: row for row in self.catalog["sources"]}
        self.assertEqual({"GAP_GAZE_001", "GAP_BODY_003"}, {
            evidence_id for evidence_id, row in by_id.items()
            if row["reviewStatus"] == "REVIEW_BLOCKED"
        })
        for evidence_id in ("GAP_GAZE_001", "GAP_BODY_003"):
            self.assertEqual("HTML_CHALLENGE_NOT_PDF", by_id[evidence_id]["fileIntegrity"])
        self.assertEqual(by_id["GAP_GAZE_001"]["fileSha256"], by_id["GAP_BODY_003"]["fileSha256"])

    def test_records_never_claim_numeric_behavior_thresholds(self):
        for record in self.records:
            with self.subTest(record=record["evidenceId"]):
                self.assertFalse(record["thresholdExists"])
                self.assertIsNone(record["thresholdValue"])
                self.assertFalse(record["thresholdAssessment"]["behaviorThresholdReported"])
                self.assertFalse(record["thresholdAssessment"]["productionThresholdUsable"])
                self.assertNotIn("THRESHOLD_CANDIDATE", record["intendedUses"])
                self.assertTrue(all(not row["numericThresholdSupported"] for row in record["faceFitMappings"]))

    def test_metric_mapping_covers_all_registry_metrics_without_promotion(self):
        rows = self.matrix["metrics"]
        self.assertEqual(18, self.matrix["metricCount"])
        self.assertEqual(self.metric_ids, {row["metricId"] for row in rows})
        self.assertFalse(self.matrix["productionApproved"])
        self.assertFalse(self.matrix["scoringAvailable"])
        self.assertIsNone(self.matrix["score"])
        for row in rows:
            self.assertEqual(row["stage31Readiness"], row["stage32Readiness"])
            self.assertFalse(row["readinessChanged"])
            self.assertEqual("NOT_READY", row["productionReadiness"])
            self.assertTrue(row["evidenceMappings"])
            self.assertTrue(all(not mapping["numericThresholdSupported"] for mapping in row["evidenceMappings"]))

    def test_threshold_readiness_is_unchanged_and_null(self):
        self.assertEqual(self.metric_ids, {row["metricId"] for row in self.readiness["metrics"]})
        self.assertFalse(self.readiness["thresholdProfileCreated"])
        self.assertFalse(self.readiness["scoreWeightsCreated"])
        for row in self.readiness["metrics"]:
            review = row["stage32Review"]
            self.assertEqual(review["priorReadiness"], review["currentReadiness"])
            self.assertFalse(review["changed"])
            self.assertFalse(review["thresholdExists"])
            self.assertIsNone(review["thresholdValue"])
            self.assertTrue(review["productionBlocking"])

    def test_gap_mapping_has_sixteen_open_production_blocks(self):
        rows = self.gaps["gaps"]
        self.assertEqual(EXPECTED_GAPS, {row["gapId"] for row in rows})
        self.assertEqual(16, self.gaps["gapCount"])
        self.assertEqual(0, self.gaps["resolvedGapCount"])
        self.assertTrue(all(row["productionBlocking"] for row in rows))
        self.assertTrue(all(not row["resolved"] for row in rows))
        self.assertTrue(all(not row["thresholdSupported"] for row in rows))
        self.assertTrue(all(set(row["affectedMetricIds"]) <= self.metric_ids for row in rows))

    def test_audio_standards_are_quality_only(self):
        row = next(row for row in self.gaps["gaps"] if row["gapId"] == "MICROPHONE_LOUDNESS_NORMALIZATION")
        self.assertEqual("QUALITY_ONLY", row["evidenceState"])
        for metric_id in ("SPEECH_RMS_DBFS", "SPEECH_PEAK_DBFS", "SPEECH_CLIPPING_SAMPLE_RATIO"):
            metric = next(item for item in self.matrix["metrics"] if item["metricId"] == metric_id)
            self.assertTrue(all(mapping["relation"] == "NOT_APPLICABLE" for mapping in metric["stage32EvidenceMappings"]))

    def test_head_pose_is_not_promoted_to_eye_gaze(self):
        row = next(row for row in self.gaps["gaps"] if row["gapId"] == "HEAD_POSE_VS_EYE_GAZE")
        self.assertEqual("METHOD_DEFINED", row["evidenceState"])
        text = json.dumps(self.records, ensure_ascii=False).lower()
        self.assertNotIn("head pose equals eye gaze", text)
        self.assertNotIn("head pose is eye contact", text)

    def test_rubric_has_observable_anchors_and_prohibited_inferences(self):
        self.assertFalse(self.rubric["productionApproved"])
        self.assertFalse(self.rubric["scoreGenerationAllowed"])
        self.assertTrue(self.rubric["pilotValidationRequired"])
        self.assertEqual({"GAZE_HEAD", "POSTURE", "SPEECH_DELIVERY"}, {row["axis"] for row in self.rubric["items"]})
        self.assertEqual(10, len(self.rubric["items"]))
        for item in self.rubric["items"]:
            self.assertEqual(item["itemId"], item["rubricItemId"])
            for field in (
                "observableBehavior", "operationalDefinition", "observationWindow",
                "inclusionRule", "exclusionRule", "examples", "counterExamples",
                "raterConfidence", "evidenceSources", "limitations",
            ):
                self.assertTrue(item[field])
            self.assertEqual({"LEVEL_1", "LEVEL_2", "LEVEL_3", "LEVEL_4"}, set(item["anchors"]))
            self.assertTrue(item["notObservableWhen"])
            self.assertTrue(item["insufficientDataWhen"])
            self.assertLessEqual(set(item["metricLinks"]), self.metric_ids)
        self.assertIn("HIRING_RECOMMENDATION", self.rubric["prohibitedInferences"])
        self.assertIn("JOB_FIT", self.rubric["prohibitedInferences"])

    def test_pilot_spec_keeps_parameters_and_gates_unapproved(self):
        self.assertEqual("DESIGN_ONLY_NOT_AUTHORIZED_FOR_COLLECTION", self.pilot["status"])
        self.assertEqual("TBD_BY_POWER_ANALYSIS", self.pilot["sampleDesign"]["targetSampleSize"])
        self.assertEqual("MINIMUM_NOT_YET_APPROVED", self.pilot["sampleDesign"]["minimumRaters"])
        self.assertEqual("PILOT_FEASIBILITY_TARGET", self.pilot["sampleDesign"]["feasibilityTarget"])
        self.assertTrue(all(row["status"] == "NOT_MET" for row in self.pilot["decisionGates"]))
        self.assertFalse(self.pilot["scoringAvailable"])
        self.assertIsNone(self.pilot["score"])

    def test_validator_returns_required_ready_state(self):
        report = self.validator.validate_artifacts()
        self.assertEqual([], report["errors"])
        self.assertEqual(EXPECTED_STATUS, report["status"])
        self.assertEqual(18, report["sourceCount"])
        self.assertEqual(16, report["gapCount"])
        self.assertEqual(2, report["accessBlockedCount"])
        self.assertFalse(report["scoringAvailable"])
        self.assertFalse(report["productionApproved"])
        self.assertEqual("NOT_AVAILABLE", report["scoreStatus"])
        self.assertEqual("THRESHOLD_EVIDENCE_NOT_APPROVED", report["reason"])
        self.assertIsNone(report["score"])

    def test_adapter_smoke_applies_quality_gate_and_fails_closed(self):
        inv = inventory()
        speech = {
            "answerId": "ANS_000001",
            "status": "COMPLETE",
            "input": {"durationMs": 30000, "sampleCount": 300},
            "speakingRate": {"answerDurationMs": 30000, "wordCount": 50},
            "pitch": {"totalFrameCount": 100, "voicedFrameCount": 80, "voicedFrameRatio": 0.8},
            "warnings": [],
        }
        for metric in inv["metrics"]:
            if metric["sourceService"] == "ANALYSIS":
                _put(speech, metric["sourcePath"], 1)
        aggregate = {
            "interval_id": "INT_ANSWER_001", "interval_type": "ANSWER", "duration_ms": 30000,
            "data_quality": {"total_frame_count": 100, "head_pose_availability_ratio": 1.0, "posture_availability_ratio": 1.0},
            "head_pose": {"availability": {"availability_ratio": 1.0}},
            "posture": {"shoulder_availability": {"availability_ratio": 1.0}},
            "errors": [],
        }
        for metric in inv["metrics"]:
            if metric["sourceService"] == "VISION":
                _put(aggregate, metric["sourcePath"], 1)
                parent_path = metric["sourcePath"].rsplit(".", 1)[0]
                parent = aggregate
                for component in parent_path.split("."):
                    parent = parent.setdefault(component, {})
                parent["count"] = 100
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            speech_dir = temp / "speech"
            speech_dir.mkdir()
            (speech_dir / "ANS_000001.json").write_text(json.dumps(speech), encoding="utf-8")
            vision_file = temp / "interval_aggregates.jsonl"
            vision_file.write_text(json.dumps(aggregate) + "\n", encoding="utf-8")
            report = self.validator.real_adapter_smoke(speech_dir, vision_file)
        self.assertEqual(10, report["speechMetricRowCount"])
        self.assertEqual(6, report["visionMetricRowCount"])
        self.assertEqual(16, report["qualityGateAppliedCount"])
        self.assertFalse(report["scoringAvailable"])
        self.assertFalse(report["productionApproved"])
        self.assertEqual("NOT_AVAILABLE", report["scoreStatus"])
        self.assertEqual("THRESHOLD_EVIDENCE_NOT_APPROVED", report["reason"])
        self.assertIsNone(report["score"])


if __name__ == "__main__":
    unittest.main()
