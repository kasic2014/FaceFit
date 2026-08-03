import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from app.vision.annotation_policy_approval import (
    AGREEMENT_POLICY_STATUS,
    APPROVED_STRATEGY,
    NEW_OUTPUTS,
    SNAPSHOT_CONFLICT,
    TIE_BREAKER_STATUS,
    PolicyApprovalError,
    build_policy_approval_package,
    execution_gate,
    load_approved_decision,
    validate_approved_decision,
    validate_snapshot,
    validate_stage192_inputs,
)
from app.vision.annotation_policy_revision import V2_ORDER, decision_template
from app.vision.pilot_video_intake import load_strict_json, sha256_file


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_REVISION = (
    PROJECT_ROOT
    / "data"
    / "output"
    / "pilot_annotation_agreement_policy"
    / "SES_000001"
    / "revision_0_2_0"
)
RATER_PATHS = [
    PROJECT_ROOT
    / "data"
    / "output"
    / "pilot_annotation"
    / "SES_000001"
    / rater
    / "annotation_events.json"
    for rater in ("rater_a", "rater_b")
]


def _approved_decision_fixture():
    return {
        "policy_id": "ANNOTATION_AGREEMENT_MATCHING_001",
        "candidate_version": "0.2.0",
        "reviewer_id": "TEST_POLICY_REVIEWER",
        "decision": "APPROVE_DETERMINISTIC_MULTI_CRITERIA_V2",
        "selected_tie_breaker_strategy": "DETERMINISTIC_MULTI_CRITERIA_V2",
        "threshold_decision": "DEFERRED",
        "scope": "PILOT_DEVELOPMENT_ONLY",
        "reviewed_at": "2026-07-30T12:00:00+09:00",
        "rationale": "Fixture-only governance decision for contract validation.",
    }


class AnnotationPolicyApprovalStage193Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.revision = Path(self.temp.name) / "revision_0_2_0"
        self.revision.mkdir()
        for source in SOURCE_REVISION.iterdir():
            if source.is_file() and source.name not in NEW_OUTPUTS:
                shutil.copy2(source, self.revision / source.name)
        self._write_decision(
            _approved_decision_fixture(),
            self.revision / "agreement_policy_revision_decision.json",
        )

    def tearDown(self):
        self.temp.cleanup()

    def _write_decision(self, value, path=None):
        path = path or self.revision / "decision.json"
        path.write_text(
            json.dumps(value, ensure_ascii=False, allow_nan=False),
            encoding="utf-8",
        )
        return path

    def test_actual_decision_strict_loading(self):
        path = self._write_decision(_approved_decision_fixture())
        loaded = load_approved_decision(path)
        self.assertEqual(
            "APPROVE_DETERMINISTIC_MULTI_CRITERIA_V2", loaded["decision"]
        )
        self.assertEqual(APPROVED_STRATEGY, loaded["selected_tie_breaker_strategy"])

    def test_review_pending_template_is_unchanged(self):
        template_path = (
            self.revision / "agreement_policy_revision_decision.template.json"
        )
        before = sha256_file(template_path)
        build_policy_approval_package(self.revision)
        self.assertEqual(before, sha256_file(template_path))
        self.assertEqual(decision_template(), load_strict_json(template_path))

    def test_reviewer_id_is_required(self):
        value = _approved_decision_fixture()
        value["reviewer_id"] = None
        with self.assertRaises(PolicyApprovalError):
            validate_approved_decision(value)

    def test_reviewed_at_requires_timezone(self):
        value = _approved_decision_fixture()
        value["reviewed_at"] = "2026-07-30T21:38:00"
        with self.assertRaisesRegex(PolicyApprovalError, "timezone"):
            validate_approved_decision(value)

    def test_decision_and_strategy_mismatch_is_blocked(self):
        value = _approved_decision_fixture()
        value["selected_tie_breaker_strategy"] = "LEGACY_STAGE13"
        with self.assertRaises(PolicyApprovalError):
            validate_approved_decision(value)

    def test_threshold_decision_must_remain_deferred(self):
        value = _approved_decision_fixture()
        value["threshold_decision"] = "REJECTED"
        with self.assertRaises(PolicyApprovalError):
            validate_approved_decision(value)

    def test_threshold_numeric_field_insertion_is_blocked(self):
        value = _approved_decision_fixture()
        value["minimum_temporal_iou"] = 0.6666
        with self.assertRaises(PolicyApprovalError):
            validate_approved_decision(value)

    def test_v2_ordering_rules_are_fixed(self):
        report = build_policy_approval_package(self.revision)
        snapshot = load_strict_json(
            self.revision / "approved_tie_breaker_policy_snapshot.json"
        )
        self.assertEqual(list(V2_ORDER), snapshot["ordering_rules"])
        self.assertTrue(report["checks"]["v2_ordering_fixed"])

    def test_snapshot_is_idempotent_and_immutable(self):
        build_policy_approval_package(self.revision)
        snapshot_path = self.revision / "approved_tie_breaker_policy_snapshot.json"
        before = sha256_file(snapshot_path)
        build_policy_approval_package(self.revision)
        self.assertEqual(before, sha256_file(snapshot_path))
        validate_snapshot(load_strict_json(snapshot_path))

    def test_same_version_snapshot_conflict_is_blocked(self):
        build_policy_approval_package(self.revision)
        snapshot_path = self.revision / "approved_tie_breaker_policy_snapshot.json"
        value = load_strict_json(snapshot_path)
        value["approval_rationale"] = "Different content for the same version."
        snapshot_path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        with self.assertRaises(PolicyApprovalError) as context:
            build_policy_approval_package(self.revision)
        self.assertEqual(SNAPSHOT_CONFLICT, context.exception.code)

    def test_tie_breaker_approval_is_separate_from_execution(self):
        gate = execution_gate()
        self.assertTrue(gate["tie_breaker_approved"])
        self.assertFalse(gate["thresholds_approved"])
        self.assertFalse(gate["official_matching_eligible"])
        self.assertFalse(gate["agreement_calculation_eligible"])
        self.assertFalse(gate["kappa_calculation_eligible"])

    def test_no_matching_agreement_or_kappa_is_executed(self):
        report = build_policy_approval_package(self.revision)
        checks = report["checks"]
        self.assertFalse(checks["official_matching_executed"])
        self.assertFalse(checks["agreement_calculated"])
        self.assertFalse(checks["kappa_calculated"])
        self.assertFalse(checks["real_rater_annotation_loaded"])

    def test_final_policy_statuses_are_separate(self):
        report = build_policy_approval_package(self.revision)
        self.assertEqual(TIE_BREAKER_STATUS, report["tie_breaker_policy_status"])
        self.assertEqual(
            AGREEMENT_POLICY_STATUS, report["agreement_policy_status"]
        )
        snapshot = load_strict_json(
            self.revision / "approved_tie_breaker_policy_snapshot.json"
        )
        self.assertEqual("PARTIALLY_APPROVED", snapshot["policy_status"])
        self.assertFalse(snapshot["operational"])
        self.assertEqual("DEFERRED", snapshot["threshold_status"])

    def test_stage192_and_rater_hashes_remain_unchanged(self):
        protected = [
            path
            for path in SOURCE_REVISION.iterdir()
            if path.is_file() and path.name not in NEW_OUTPUTS
        ] + RATER_PATHS
        before = {path: sha256_file(path) for path in protected}
        build_policy_approval_package(
            self.revision, rater_annotation_paths=RATER_PATHS
        )
        after = {path: sha256_file(path) for path in protected}
        self.assertEqual(before, after)

    def test_source_candidate_thresholds_must_be_null(self):
        candidate_path = self.revision / "agreement_policy_candidate_0_2_0.json"
        candidate = load_strict_json(candidate_path)
        candidate["temporal_thresholds"]["minimum_temporal_iou"] = 0.6666
        candidate_path.write_text(
            json.dumps(candidate, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        with self.assertRaises(PolicyApprovalError):
            validate_stage192_inputs(self.revision)

    def test_all_json_outputs_are_strict_and_finite(self):
        build_policy_approval_package(self.revision)
        json_outputs = [
            self.revision / name for name in NEW_OUTPUTS if name.endswith(".json")
        ]
        for path in json_outputs:
            value = load_strict_json(path)
            json.dumps(value, allow_nan=False)

    def test_nonfinite_and_duplicate_decision_json_are_blocked(self):
        path = self.revision / "bad.json"
        path.write_text('{"reviewer_id":NaN}', encoding="utf-8")
        with self.assertRaises(PolicyApprovalError):
            load_approved_decision(path)
        path.write_text(
            '{"policy_id":"a","policy_id":"b"}', encoding="utf-8"
        )
        with self.assertRaises(PolicyApprovalError):
            load_approved_decision(path)

    def test_all_five_outputs_are_created(self):
        build_policy_approval_package(self.revision)
        self.assertEqual(
            set(NEW_OUTPUTS),
            {path.name for path in self.revision.iterdir() if path.name in NEW_OUTPUTS},
        )


if __name__ == "__main__":
    unittest.main()
