from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from app.vision.pilot_annotation_ready import (
    evaluate_stage17_annotation_gate,
    validate_decision_file_pair,
    validate_development_split,
)
from app.vision.pilot_manual_review import PilotManualReviewDecision
from app.vision.pilot_video_intake import (
    PilotVideoIntakeError,
    assert_no_forbidden_semantics,
    load_strict_json,
    write_strict_json,
)


ROOT = Path(__file__).resolve().parents[1]
STAGE15 = (
    ROOT / "data" / "output" / "pilot_video_intake_validation"
    / "SES_000001"
)
STAGE16 = (
    ROOT / "data" / "output" / "pilot_manual_review" / "SES_000001"
)
INCOMING = ROOT / "data" / "pilot" / "incoming"


class PilotAnnotationReadyStage17Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template = load_strict_json(
            STAGE16 / "manual_review_decision.template.json"
        )
        cls.decision_value = load_strict_json(
            STAGE16 / "manual_review_decision.json"
        )
        cls.split = load_strict_json(
            STAGE16 / "development_split_assignment.json"
        )
        cls.consent = load_strict_json(
            INCOMING / "PTC_000001_SES_000001.consent.json"
        )
        cls.metadata = load_strict_json(
            INCOMING / "PTC_000001_SES_000001.metadata.json"
        )
        cls.video = load_strict_json(STAGE15 / "video_metadata.json")
        cls.quality = load_strict_json(
            STAGE15 / "quality_check_results.json"
        )
        cls.intervals = load_strict_json(
            STAGE15 / "interval_validation.json"
        )
        cls.report = load_strict_json(STAGE15 / "validation_report.json")

    def _evaluate(self, **updates):
        values = {
            "decision": PilotManualReviewDecision.from_dict(
                self.decision_value
            ),
            "split_value": self.split,
            "consent_source": self.consent,
            "metadata_source": self.metadata,
            "video_metadata": self.video,
            "quality_results": self.quality,
            "interval_validation": self.intervals,
            "stage15_report": self.report,
        }
        values.update(updates)
        return evaluate_stage17_annotation_gate(**values)

    def test_actual_decision_strict_loading_and_values(self) -> None:
        decision = PilotManualReviewDecision.from_dict(
            self.decision_value
        )
        self.assertEqual(decision.reviewer_id, "REVIEWER_001")
        self.assertEqual(
            decision.reviewed_at, "2026-07-29T20:49:00+09:00"
        )
        self.assertEqual(decision.decision, "APPROVED_FOR_ANNOTATION")

    def test_pending_template_and_approval_are_separate(self) -> None:
        checks = validate_decision_file_pair(
            self.template, self.decision_value
        )
        self.assertTrue(all(checks.values()))
        self.assertEqual(self.template["decision"], "REVIEW_PENDING")

    def test_reviewer_and_reviewed_at_are_required(self) -> None:
        for field in ("reviewer_id", "reviewed_at"):
            value = copy.deepcopy(self.decision_value)
            value[field] = None
            with self.subTest(field=field), self.assertRaises(ValueError):
                PilotManualReviewDecision.from_dict(value)

    def test_gate_succeeds_with_approval_and_development_split(self) -> None:
        result = self._evaluate()
        self.assertEqual(
            result.final_status, "pilot_video_annotation_ready"
        )
        self.assertTrue(result.stage14_gate_result.eligible)
        self.assertEqual(
            result.stage14_gate_result.result_status, "PILOT_CANDIDATE"
        )
        self.assertFalse(result.stage14_gate_result.dataset_frozen)
        self.assertFalse(result.stage14_gate_result.operationally_approved)

    def test_consent_failure_blocks_gate(self) -> None:
        consent = copy.deepcopy(self.consent)
        consent["research_use_allowed"] = False
        result = self._evaluate(consent_source=consent)
        self.assertFalse(result.stage14_gate_result.eligible)
        self.assertIn(
            "CONSENT_INVALID",
            result.stage14_gate_result.failed_conditions,
        )

    def test_withdrawal_blocks_gate(self) -> None:
        metadata = copy.deepcopy(self.metadata)
        metadata["withdrawn"] = True
        result = self._evaluate(metadata_source=metadata)
        self.assertFalse(result.stage14_gate_result.eligible)
        self.assertIn(
            "WITHDRAWAL_BLOCK",
            result.stage14_gate_result.failed_conditions,
        )

    def test_development_split_has_no_entity_leakage(self) -> None:
        result = validate_development_split(self.split)
        self.assertTrue(result["valid"])
        self.assertTrue(result["fixture_only_collision_ignored"])
        self.assertEqual(result["split_name"], "DEVELOPMENT")

    def test_participant_session_and_answer_leakage_is_blocked(self) -> None:
        mutations = []
        participant = copy.deepcopy(self.split)
        participant["assignment"]["split"] = "HOLDOUT"
        mutations.append(participant)
        session = copy.deepcopy(self.split)
        session["linkage"]["sessions"][0]["split_name"] = "VALIDATION"
        mutations.append(session)
        answer = copy.deepcopy(self.split)
        answer["linkage"]["answers"][0]["split_name"] = "CALIBRATION"
        mutations.append(answer)
        for value in mutations:
            with self.subTest(value=value):
                self.assertFalse(validate_development_split(value)["valid"])
                result = self._evaluate(split_value=value)
                self.assertFalse(result.stage14_gate_result.eligible)

    def test_strict_json_rejects_non_finite_and_duplicate_keys(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "value.json"
            write_strict_json(path, {"status": "ready"})
            self.assertEqual(load_strict_json(path)["status"], "ready")
            path.write_text('{"a": 1, "a": 2}', encoding="utf-8")
            with self.assertRaises(PilotVideoIntakeError):
                load_strict_json(path)
            with self.assertRaises(PilotVideoIntakeError):
                write_strict_json(path, {"value": float("inf")})

    def test_outputs_have_no_prohibited_semantics(self) -> None:
        for name in (
            "manual_review_decision.json",
            "gate_reevaluation_status.json",
            "annotation_ready_manifest.json",
            "validation_report.json",
        ):
            assert_no_forbidden_semantics(load_strict_json(STAGE16 / name))


if __name__ == "__main__":
    unittest.main()
