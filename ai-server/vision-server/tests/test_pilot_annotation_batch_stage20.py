import copy
import json
import math
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from app.vision.pilot_annotation_batch import (
    BATCH_STATUS,
    BLOCKING_REASONS,
    FINAL_STATUS,
    OUTPUT_NAMES,
    BatchRegistry,
    BatchSession,
    CurrentSessionSources,
    PilotBatchError,
    RaterAssignment,
    build_pilot_annotation_batch,
    intake_template,
    load_batch_registry,
    validate_split_integrity,
)
from app.vision.pilot_video_intake import load_strict_json, sha256_file


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = "2026-07-30T22:30:00+09:00"


def _session(
    participant_id="PTC_000001",
    session_id="SES_000001",
    split_name="DEVELOPMENT",
    answer_ids=None,
    data_context="REAL_PILOT",
):
    answer_ids = answer_ids or ["ANS_000001"]
    return BatchSession.from_dict(
        {
            "participant_id": participant_id,
            "session_id": session_id,
            "split_name": split_name,
            "consent_reference_id": "CONSENT_FIXTURE",
            "video_sha256": "a" * 64,
            "annotation_ready_manifest_reference": "fixture/ready.json",
            "answer_ids": answer_ids,
            "rater_a_assignment": f"ASG_{session_id}_RATER_A",
            "rater_b_assignment": f"ASG_{session_id}_RATER_B",
            "rater_a_status": "COMPLETED",
            "rater_b_status": "COMPLETED",
            "agreement_status": "NOT_CALCULATED",
            "adjudication_status": "NOT_STARTED",
            "eligible_for_threshold_evidence": False,
            "exclusion_reasons": ["FIXTURE_ONLY"],
            "data_context": data_context,
        }
    )


class PilotAnnotationBatchStage20Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.temp_root = Path(self.temp.name)
        self.sources = CurrentSessionSources.from_vision_root(PROJECT_ROOT)

    def tearDown(self):
        self.temp.cleanup()

    def _build(self, name="batch"):
        destination = self.temp_root / name
        report = build_pilot_annotation_batch(
            self.sources,
            destination,
            created_at=CREATED_AT,
        )
        return destination, report

    def _modified_source(self, field, mutate):
        source = getattr(self.sources, field)
        value = load_strict_json(source)
        mutate(value)
        target = self.temp_root / f"{field}.json"
        target.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        return replace(self.sources, **{field: target})

    def test_actual_batch_builds_all_strict_outputs(self):
        destination, report = self._build()
        self.assertTrue(report["valid"])
        self.assertEqual(set(OUTPUT_NAMES), {item.name for item in destination.iterdir()})
        for name in OUTPUT_NAMES:
            if name.endswith(".json"):
                load_strict_json(destination / name)
        registry = load_batch_registry(destination / "pilot_batch_registry.json")
        self.assertEqual(BATCH_STATUS, registry.batch_status)
        self.assertEqual(1, registry.participant_count)
        self.assertEqual(1, registry.session_count)
        self.assertEqual(4, registry.answer_count)

    def test_batch_schema_rejects_extra_and_missing_fields(self):
        destination, _ = self._build()
        source = load_strict_json(destination / "pilot_batch_registry.json")
        for mutation in (
            lambda value: value.update({"unexpected": True}),
            lambda value: value.pop("purpose"),
        ):
            candidate = copy.deepcopy(source)
            mutation(candidate)
            with self.assertRaises(PilotBatchError):
                BatchRegistry.from_dict(candidate)

    def test_session_reference_mismatch_is_blocked(self):
        sources = self._modified_source(
            "annotation_ready_manifest",
            lambda value: value.update({"session_id": "SES_999999"}),
        )
        with self.assertRaisesRegex(PilotBatchError, "Session reference mismatch"):
            build_pilot_annotation_batch(
                sources, self.temp_root / "bad-reference", created_at=CREATED_AT
            )

    def test_answer_reference_mismatch_is_blocked(self):
        def mutate(value):
            value["answers"][0]["answer_id"] = "ANS_999999"

        sources = self._modified_source("interval_validation", mutate)
        with self.assertRaisesRegex(PilotBatchError, "Answer references"):
            build_pilot_annotation_batch(
                sources, self.temp_root / "bad-answer", created_at=CREATED_AT
            )

    def test_participant_split_leakage_is_blocked(self):
        sessions = [
            _session(),
            _session(
                session_id="SES_000002",
                split_name="VALIDATION",
                answer_ids=["ANS_000002"],
            ),
        ]
        with self.assertRaisesRegex(PilotBatchError, "participant split leakage"):
            validate_split_integrity(sessions)

    def test_session_split_leakage_is_blocked(self):
        sessions = [
            _session(),
            _session(
                participant_id="PTC_000002",
                split_name="VALIDATION",
                answer_ids=["ANS_000002"],
            ),
        ]
        with self.assertRaisesRegex(PilotBatchError, "session split leakage"):
            validate_split_integrity(sessions)

    def test_answer_split_leakage_is_blocked(self):
        sessions = [
            _session(),
            _session(
                participant_id="PTC_000002",
                session_id="SES_000002",
                split_name="VALIDATION",
                answer_ids=["ANS_000001"],
            ),
        ]
        with self.assertRaisesRegex(PilotBatchError, "answer split leakage"):
            validate_split_integrity(sessions)

    def test_fixture_assignment_is_excluded_from_operational_split(self):
        report = validate_split_integrity(
            [
                _session(),
                _session(
                    split_name="CALIBRATION",
                    data_context="FIXTURE_ONLY",
                ),
            ]
        )
        self.assertEqual(1, report["fixture_session_count_excluded"])
        self.assertEqual(
            "DEVELOPMENT",
            report["participant_split_assignments"]["PTC_000001"],
        )
        self.assertTrue(report["fixture_assignments_are_not_operational"])

    def test_rater_assignment_ids_must_be_isolated(self):
        value = _session().to_dict()
        value["rater_b_assignment"] = value["rater_a_assignment"]
        with self.assertRaisesRegex(PilotBatchError, "isolated"):
            BatchSession.from_dict(value)

    def test_completed_rater_assignment_preserves_unverified_identity(self):
        assignment = RaterAssignment.from_dict(
            {
                "assignment_id": "ASG_SES_000001_RATER_A",
                "participant_id": "PTC_000001",
                "session_id": "SES_000001",
                "rater_role": "RATER_A",
                "rater_identity_context": "RATER_IDENTITY_UNVERIFIED",
                "assignment_status": "COMPLETED",
                "assigned_at": None,
                "completed_at": CREATED_AT,
                "annotation_file_reference": "fixture/annotation.json",
                "annotation_sha256": "b" * 64,
                "blind_flags_valid": True,
            }
        )
        self.assertEqual(
            "RATER_IDENTITY_UNVERIFIED", assignment.rater_identity_context
        )

    def test_no_actual_entities_or_events_are_generated(self):
        destination, _ = self._build()
        sessions = load_strict_json(destination / "pilot_batch_sessions.json")
        validation = load_strict_json(destination / "validation_report.json")
        self.assertFalse(sessions["actual_participant_created"])
        self.assertFalse(sessions["actual_session_created"])
        self.assertFalse(
            validation["checks"]["actual_annotation_event_created"]
        )

    def test_unapproved_minimum_criteria_remain_null(self):
        destination, _ = self._build()
        readiness = load_strict_json(
            destination / "threshold_evidence_readiness.json"
        )
        self.assertEqual(
            {
                "minimum_participant_count": None,
                "minimum_session_count": None,
                "minimum_event_count": None,
            },
            readiness["approved_minimum_criteria"],
        )

    def test_one_participant_is_not_evidence_ready(self):
        destination, _ = self._build()
        readiness = load_strict_json(
            destination / "threshold_evidence_readiness.json"
        )
        status = load_strict_json(destination / "batch_status.json")
        self.assertEqual(
            "EVIDENCE_INSUFFICIENT",
            readiness["threshold_evidence_readiness"],
        )
        self.assertFalse(readiness["ready_for_review"])
        self.assertEqual(list(BLOCKING_REASONS), readiness["blocking_reasons"])
        self.assertEqual(FINAL_STATUS, status["current_status"])
        self.assertEqual(
            "awaiting_additional_pilot_sessions", status["collection_status"]
        )

    def test_thresholds_agreement_and_kappa_are_not_created(self):
        destination, _ = self._build()
        readiness = load_strict_json(
            destination / "threshold_evidence_readiness.json"
        )
        self.assertEqual(
            {
                "minimum_temporal_iou": None,
                "maximum_onset_difference_ms": None,
                "maximum_offset_difference_ms": None,
            },
            readiness["threshold_policy"],
        )
        self.assertFalse(readiness["agreement_calculated"])
        self.assertFalse(readiness["kappa_calculated"])

    def test_batch_is_not_frozen(self):
        destination, _ = self._build()
        status = load_strict_json(destination / "batch_status.json")
        registry = load_strict_json(destination / "pilot_batch_registry.json")
        self.assertFalse(status["dataset_frozen"])
        self.assertNotEqual("FROZEN", registry["batch_status"])
        self.assertFalse(registry["operational"])

    def test_intake_template_is_empty(self):
        template = intake_template()
        self.assertIsNone(template["participant_id"])
        self.assertIsNone(template["session_id"])
        self.assertIsNone(template["video_reference"])
        self.assertEqual([], template["answer_ids"])
        self.assertEqual([], template["rater_assignments"])
        self.assertNotIn("events", template)

    def test_protected_stage_and_rater_hashes_are_unchanged(self):
        before = {
            name: sha256_file(path)
            for name, path in self.sources.named_paths().items()
        }
        self._build()
        after = {
            name: sha256_file(path)
            for name, path in self.sources.named_paths().items()
        }
        self.assertEqual(before, after)

    def test_nan_and_infinity_are_rejected(self):
        destination, _ = self._build()
        registry = load_strict_json(destination / "pilot_batch_registry.json")
        for invalid in (math.nan, math.inf, -math.inf):
            candidate = copy.deepcopy(registry)
            candidate["rater_assignment_summary"]["invalid"] = invalid
            with self.assertRaises(ValueError):
                BatchRegistry.from_dict(candidate)

    def test_existing_destination_is_not_overwritten(self):
        destination, _ = self._build()
        registry_sha = sha256_file(destination / "pilot_batch_registry.json")
        with self.assertRaisesRegex(PilotBatchError, "refusing to overwrite"):
            build_pilot_annotation_batch(
                self.sources, destination, created_at=CREATED_AT
            )
        self.assertEqual(
            registry_sha, sha256_file(destination / "pilot_batch_registry.json")
        )


if __name__ == "__main__":
    unittest.main()
