from __future__ import annotations

from collections import Counter
import importlib.util
import json
from pathlib import Path
import re
import unittest

from support import ROOT, inventory, read


EXPECTED_SOURCE_IDS = {
    *(f"SRC_INT_{number:03d}" for number in range(1, 8)),
    *(f"SRC_PUB_{number:03d}" for number in range(1, 5)),
    *(f"SRC_HEAD_{number:03d}" for number in range(1, 6)),
    *(f"SRC_POSE_{number:03d}" for number in range(1, 5)),
}
EXPECTED_GAPS = {
    "KOREAN_SPEECH_RATE", "KOREAN_ARTICULATION_RATE", "KOREAN_PAUSE_DURATION",
    "KOREAN_FILLER_VALIDATION", "WEBCAM_HEAD_POSE_BEHAVIOR", "HEAD_POSE_VS_EYE_GAZE",
    "SEATED_SHOULDER_POSTURE", "SHOULDER_CENTER_MOVEMENT", "MICROPHONE_LOUDNESS_NORMALIZATION",
    "HUMAN_BEHAVIOR_RUBRIC", "INTER_RATER_RELIABILITY", "MULTI_SESSION_DISTRIBUTION",
    "THRESHOLD_SENSITIVITY", "AXIS_WEIGHT_VALIDATION", "BIAS_AND_FAIRNESS_VALIDATION",
}


def _load_validator():
    path = ROOT / "scripts" / "validate_evidence_mapping.py"
    spec = importlib.util.spec_from_file_location("validate_evidence_mapping", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class EvidenceMappingStage31Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = read("evidence/source-catalog-v1.json")
        cls.records = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((ROOT / "evidence" / "records").glob("SRC_*.json"))
        ]
        cls.matrix = read("mappings/metric-evidence-matrix-v1.json")
        cls.readiness = read("mappings/threshold-readiness-v1.json")
        cls.summary = read("mappings/evidence-use-summary-v1.json")
        cls.schema = read("contracts/evidence-record.schema.json")
        cls.metric_ids = {metric["metricId"] for metric in inventory()["metrics"]}
        cls.validator = _load_validator()
        cls.gaps = cls.validator.load_gaps()

    def test_source_catalog_has_exact_fixed_twenty(self):
        sources = self.catalog["sources"]
        ids = [source["evidenceId"] for source in sources]
        self.assertEqual(20, self.catalog["sourceCount"])
        self.assertEqual(20, len(sources))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(EXPECTED_SOURCE_IDS, set(ids))

    def test_source_catalog_identity_and_categories(self):
        valid_categories = {"EMPLOYMENT_INTERVIEW", "PUBLIC_SPEAKING", "HEAD_POSE_MEASUREMENT", "POSE_MEASUREMENT"}
        doi_pattern = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
        for source in self.catalog["sources"]:
            with self.subTest(source=source["evidenceId"]):
                self.assertTrue(source["title"])
                self.assertIn(source["category"], valid_categories)
                self.assertTrue(source["officialUrl"].startswith("https://"))
                if source["doi"] is not None:
                    self.assertRegex(source["doi"], doi_pattern)

    def test_record_files_have_exact_ids_and_schema_fields(self):
        ids = [record["evidenceId"] for record in self.records]
        self.assertEqual(20, len(self.records))
        self.assertEqual(EXPECTED_SOURCE_IDS, set(ids))
        self.assertEqual(len(ids), len(set(ids)))
        required = set(self.schema["required"])
        allowed = set(self.schema["properties"])
        for record in self.records:
            with self.subTest(record=record["evidenceId"]):
                self.assertEqual(required, set(record))
                self.assertEqual(allowed, set(record))
                self.assertTrue(record["authors"])
                self.assertTrue(record["limitations"])

    def test_access_depth_and_extraction_locations_are_honest(self):
        full_levels = {"FULL_TEXT_PDF", "AUTHOR_ACCEPTED_MANUSCRIPT", "OFFICIAL_HTML_FULL_TEXT"}
        for record in self.records:
            with self.subTest(record=record["evidenceId"]):
                depth = record["access"]["reviewDepth"]
                if depth == "FULL_TEXT_REVIEWED":
                    self.assertIn(record["access"]["accessLevel"], full_levels)
                    self.assertTrue(record["extractionLocations"])
                else:
                    self.assertTrue(all(location["page"] is None for location in record["extractionLocations"]))
                for location in record["extractionLocations"]:
                    self.assertTrue(location["description"])
                    self.assertTrue(any(location[key] is not None for key in ("page", "section", "table", "figure")))

    def test_measurements_do_not_convert_statistics_to_behavior_boundaries(self):
        for record in self.records:
            with self.subTest(record=record["evidenceId"]):
                self.assertFalse(record["thresholdExists"])
                self.assertIsNone(record["thresholdValue"])
                self.assertFalse(record["thresholdAssessment"]["behaviorThresholdReported"])
                self.assertFalse(record["thresholdAssessment"]["productionThresholdUsable"])
                self.assertNotIn("THRESHOLD_CANDIDATE", record["intendedUses"])
                for measurement in record["measurements"]:
                    self.assertFalse(measurement["behaviorBoundaryReported"])
                    self.assertNotEqual("BEHAVIOR_THRESHOLD", measurement["measurementType"])

    def test_matrix_has_exact_registry_metrics(self):
        rows = self.matrix["metrics"]
        ids = [row["metricId"] for row in rows]
        self.assertEqual(18, self.matrix["metricCount"])
        self.assertEqual(18, len(rows))
        self.assertEqual(self.metric_ids, set(ids))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(row["evidenceMappings"] for row in rows))

    def test_mapping_relations_enforce_semantic_conditions(self):
        relations = {"DIRECT", "PROXY", "UNIT_CONVERSION", "DERIVED", "NOT_APPLICABLE"}
        for row in self.matrix["metrics"]:
            for mapping in row["evidenceMappings"]:
                with self.subTest(metric=row["metricId"]):
                    self.assertIn(mapping["relation"], relations)
                    self.assertIn(mapping["evidenceId"], EXPECTED_SOURCE_IDS)
                    self.assertFalse(mapping["numericThresholdSupported"])
                    if mapping["relation"] == "DIRECT":
                        self.assertTrue(mapping["definitionMatch"])
                        self.assertTrue(mapping["unitMatch"])
                        self.assertTrue(mapping["calculationMatch"])
                    if mapping["relation"] in {"PROXY", "NOT_APPLICABLE"}:
                        self.assertTrue(mapping["reason"])
                    if mapping["relation"] == "UNIT_CONVERSION":
                        self.assertTrue(mapping["conversion"])

    def test_numeric_threshold_readiness_stays_not_ready(self):
        self.assertFalse(self.matrix["productionApproved"])
        for row in self.matrix["metrics"]:
            self.assertEqual("NOT_READY", row["numericThresholdReadiness"])
            self.assertEqual("NOT_READY", row["productionReadiness"])

    def test_quality_and_clipping_metrics_cannot_be_behavior_scores(self):
        matrix = {row["metricId"]: row for row in self.matrix["metrics"]}
        for metric_id in ("QUALITY_HEAD_AVAILABILITY_RATIO", "QUALITY_POSTURE_AVAILABILITY_RATIO"):
            self.assertEqual("NOT_APPLICABLE", matrix[metric_id]["directionReadiness"])
            self.assertLessEqual(set(matrix[metric_id]["supportedUses"]), {"QUALITY_GATE", "MEASUREMENT_LIMITATION"})
        self.assertEqual(["QUALITY_GATE"], matrix["SPEECH_CLIPPING_SAMPLE_RATIO"]["supportedUses"])

    def test_head_pose_and_eye_contact_are_not_equated(self):
        text = json.dumps(self.matrix, ensure_ascii=False).lower()
        self.assertNotIn("head pose is eye", text)
        self.assertNotIn("head pose equals eye", text)
        head_rows = [row for row in self.matrix["metrics"] if row["metricId"].startswith("HEAD_RELATIVE_")]
        self.assertTrue(all(row["bestAvailableRelation"] == "PROXY" for row in head_rows))

    def test_shoulder_joint_angle_is_not_shoulder_line_tilt(self):
        pose_records = [record for record in self.records if record["evidenceId"].startswith("SRC_POSE_")]
        text = json.dumps(pose_records, ensure_ascii=False).lower()
        self.assertIn("shoulder joint angle", text)
        self.assertIn("shoulder-line tilt", text)
        tilt = next(row for row in self.matrix["metrics"] if row["metricId"] == "POSTURE_RELATIVE_SHOULDER_TILT_ABS_P95_DEG")
        self.assertEqual("DERIVED", tilt["bestAvailableRelation"])

    def test_algorithm_error_and_model_values_are_not_scoring_inputs(self):
        measurement_types = Counter(
            measurement["measurementType"]
            for record in self.records
            for measurement in record["measurements"]
        )
        self.assertGreater(measurement_types["ALGORITHM_ERROR"], 0)
        self.assertEqual(0, measurement_types["BEHAVIOR_THRESHOLD"])
        self.assertFalse(self.readiness["scoreWeightsCreated"])
        self.assertFalse(self.readiness["thresholdProfileCreated"])

    def test_filler_and_f0_protections(self):
        readiness = {row["metricId"]: row for row in self.readiness["metrics"]}
        self.assertEqual("NOT_READY", readiness["SPEECH_FILLER_CANDIDATES_PER_MINUTE"]["readiness"])
        self.assertEqual("EXCLUDED_FROM_SCORING", readiness["SPEECH_F0_RANGE_HZ"]["readiness"])
        f0 = next(row for row in self.matrix["metrics"] if row["metricId"] == "SPEECH_F0_RANGE_HZ")
        text = json.dumps(f0, ensure_ascii=False).lower()
        for forbidden in ("confidence", "emotion", "personality", "gender"):
            self.assertNotIn(forbidden, text)

    def test_threshold_readiness_uses_only_allowed_states(self):
        allowed = {"NOT_READY", "DIRECTION_ONLY", "METRIC_DEFINITION_ONLY", "QUALITY_GATE_ONLY", "MEASUREMENT_LIMITATION_ONLY", "EXCLUDED_FROM_SCORING"}
        ids = [row["metricId"] for row in self.readiness["metrics"]]
        self.assertEqual(self.metric_ids, set(ids))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(row["readiness"] in allowed for row in self.readiness["metrics"]))
        self.assertFalse(self.readiness["productionApproved"])

    def test_gap_register_has_all_required_research_fields(self):
        ids = [gap["gapId"] for gap in self.gaps]
        self.assertEqual(EXPECTED_GAPS, set(ids))
        self.assertEqual(len(ids), len(set(ids)))
        for gap in self.gaps:
            with self.subTest(gap=gap["gapId"]):
                self.assertTrue(gap["affectedMetricIds"])
                self.assertLessEqual(set(gap["affectedMetricIds"]), self.metric_ids)
                self.assertTrue(gap["searchKeywordsKo"])
                self.assertTrue(gap["searchKeywordsEn"])
                self.assertTrue(gap["requiredPilotData"])
                self.assertTrue(gap["blockingProductionScoring"])

    def test_summary_is_derived_from_records(self):
        self.assertEqual(self.validator.build_summary(self.records), self.summary)
        self.assertEqual(20, self.summary["evidenceTotal"])
        self.assertEqual(0, self.summary["intendedUses"]["THRESHOLD_CANDIDATE"])
        self.assertEqual(20, self.summary["adoptionStatuses"]["REJECTED_FOR_THRESHOLD"])

    def test_privacy_paths_and_source_files_are_blocked(self):
        report = self.validator.validate()
        self.assertFalse(report["errors"])
        tracked_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [
                ROOT / "evidence" / "source-catalog-v1.json",
                *sorted((ROOT / "evidence" / "records").glob("SRC_*.json")),
                *sorted((ROOT / "mappings").glob("*.json")),
            ]
        )
        self.assertNotRegex(tracked_text, r"\b[A-Za-z]:[\\/]")
        self.assertNotIn('"participantId"', tracked_text)
        self.assertNotIn('"transcriptText"', tracked_text)

    def test_validator_reports_access_limited_ready_state(self):
        report = self.validator.validate()
        self.assertEqual("scoring_evidence_mapping_ready_with_access_limitations", report["status"])
        self.assertEqual(20, report["sourceCount"])
        self.assertEqual(18, report["metricCount"])
        self.assertEqual(15, report["gapCount"])
        self.assertEqual([], report["errors"])


if __name__ == "__main__":
    unittest.main()
