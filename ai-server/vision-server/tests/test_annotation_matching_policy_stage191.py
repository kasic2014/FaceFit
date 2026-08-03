from __future__ import annotations

import hashlib
import json
import math
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from app.vision import annotation_matching_policy as policy
from app.vision.pilot_video_intake import (
    PilotVideoIntakeError,
    load_strict_json,
)


VISION_ROOT = Path(__file__).resolve().parents[1]
STAGE19_DIR = (
    VISION_ROOT
    / "data"
    / "output"
    / "pilot_annotation_agreement"
    / "SES_000001"
)
RATER_DIR = (
    VISION_ROOT
    / "data"
    / "output"
    / "pilot_annotation"
    / "SES_000001"
)


def candidate_dict() -> dict:
    return policy.policy_candidate(
        rubric_id="RUBRIC_OBSERVABLE_001",
        rubric_version="1.0.0",
    ).to_dict()


def approved_decision() -> dict:
    return {
        "policy_id": policy.DEFAULT_POLICY_ID,
        "policy_version": policy.DEFAULT_POLICY_VERSION,
        "reviewer_id": "REVIEWER_001",
        "decision": "APPROVED",
        "scope": policy.DEFAULT_SCOPE,
        "selected_minimum_temporal_iou": 0.5,
        "selected_maximum_onset_difference_ms": 500,
        "selected_maximum_offset_difference_ms": 500,
        "reviewed_at": "2026-07-30T12:00:00+09:00",
        "rationale": "Approved by the designated human policy reviewer.",
    }


def write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )


class PolicySchemaTests(unittest.TestCase):
    def test_candidate_schema_round_trip_and_thresholds_are_null(self) -> None:
        value = candidate_dict()
        parsed = policy.MatchingPolicy.from_dict(value)
        self.assertEqual(parsed.to_dict(), value)
        self.assertEqual(parsed.policy_status, "REVIEW_REQUIRED")
        self.assertFalse(parsed.operational)
        self.assertIsNone(parsed.minimum_temporal_iou)
        self.assertIsNone(parsed.maximum_onset_difference_ms)
        self.assertIsNone(parsed.maximum_offset_difference_ms)

    def test_policy_schema_requires_exact_fields(self) -> None:
        value = candidate_dict()
        value["unexpected"] = True
        with self.assertRaisesRegex(policy.AgreementPolicyError, "fields"):
            policy.MatchingPolicy.from_dict(value)

    def test_strict_policy_json_rejects_duplicate_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text(
                '{"policy_id":"A","policy_id":"B"}',
                encoding="utf-8",
            )
            with self.assertRaises(PilotVideoIntakeError):
                load_strict_json(path)

    def test_semantic_version_is_validated(self) -> None:
        value = candidate_dict()
        value["policy_version"] = "version-one"
        with self.assertRaisesRegex(policy.AgreementPolicyError, "Semantic"):
            policy.MatchingPolicy.from_dict(value)

    def test_allowed_status_and_scope_are_validated(self) -> None:
        value = candidate_dict()
        value["policy_status"] = "AUTO_APPROVED"
        with self.assertRaisesRegex(policy.AgreementPolicyError, "status"):
            policy.MatchingPolicy.from_dict(value)
        value = candidate_dict()
        value["scope"] = "UNBOUNDED"
        with self.assertRaisesRegex(policy.AgreementPolicyError, "scope"):
            policy.MatchingPolicy.from_dict(value)

    def test_iou_range_is_validated(self) -> None:
        value = candidate_dict()
        value["policy_status"] = "DRAFT"
        value["minimum_temporal_iou"] = 1.01
        with self.assertRaisesRegex(policy.AgreementPolicyError, r"\[0, 1\]"):
            policy.MatchingPolicy.from_dict(value)
        value["minimum_temporal_iou"] = math.nan
        with self.assertRaises(PilotVideoIntakeError):
            policy.MatchingPolicy.from_dict(value)

    def test_negative_or_noninteger_millisecond_limits_are_blocked(self) -> None:
        value = candidate_dict()
        value["policy_status"] = "DRAFT"
        value["maximum_onset_difference_ms"] = -1
        with self.assertRaisesRegex(policy.AgreementPolicyError, "negative"):
            policy.MatchingPolicy.from_dict(value)
        value["maximum_onset_difference_ms"] = None
        value["maximum_offset_difference_ms"] = 10.5
        with self.assertRaisesRegex(policy.AgreementPolicyError, "integer"):
            policy.MatchingPolicy.from_dict(value)

    def test_review_required_policy_cannot_be_used_operationally(self) -> None:
        candidate = policy.policy_candidate(
            rubric_id="RUBRIC_OBSERVABLE_001",
            rubric_version="1.0.0",
        )
        with self.assertRaisesRegex(policy.AgreementPolicyError, "unapproved"):
            candidate.require_operational()

    def test_approved_policy_requires_all_thresholds(self) -> None:
        value = candidate_dict()
        value.update(
            {
                "policy_status": "APPROVED",
                "operational": True,
                "approved_by": "REVIEWER_001",
                "approved_at": "2026-07-30T12:00:00+09:00",
            }
        )
        with self.assertRaisesRegex(policy.AgreementPolicyError, "threshold"):
            policy.MatchingPolicy.from_dict(value)


class DecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candidate = policy.policy_candidate(
            rubric_id="RUBRIC_OBSERVABLE_001",
            rubric_version="1.0.0",
        )

    def test_decision_template_is_empty_and_pending(self) -> None:
        self.assertEqual(
            policy.decision_template(),
            {
                "policy_id": None,
                "policy_version": None,
                "reviewer_id": None,
                "decision": "REVIEW_PENDING",
                "scope": "PILOT_DEVELOPMENT_ONLY",
                "selected_minimum_temporal_iou": None,
                "selected_maximum_onset_difference_ms": None,
                "selected_maximum_offset_difference_ms": None,
                "reviewed_at": None,
                "rationale": None,
            },
        )

    def test_pending_template_remains_awaiting(self) -> None:
        decision = policy.validate_decision(
            policy.decision_template(),
            self.candidate,
        )
        self.assertEqual(
            policy.decision_status(decision["decision"]),
            policy.AWAITING_STATUS,
        )

    def test_final_decision_requires_matching_version_reviewer_and_time(self) -> None:
        value = approved_decision()
        value["policy_version"] = "1.0"
        with self.assertRaisesRegex(policy.AgreementPolicyError, "Semantic"):
            policy.validate_decision(value, self.candidate)
        value = approved_decision()
        value["reviewer_id"] = None
        with self.assertRaisesRegex(policy.AgreementPolicyError, "reviewer"):
            policy.validate_decision(value, self.candidate)
        value = approved_decision()
        value["reviewed_at"] = "not-a-time"
        with self.assertRaisesRegex(policy.AgreementPolicyError, "ISO"):
            policy.validate_decision(value, self.candidate)

    def test_final_decision_requires_matching_policy_and_scope(self) -> None:
        value = approved_decision()
        value["policy_id"] = "OTHER_POLICY"
        with self.assertRaisesRegex(policy.AgreementPolicyError, "policy_id"):
            policy.validate_decision(value, self.candidate)
        value = approved_decision()
        value["policy_version"] = "9.9.9"
        with self.assertRaisesRegex(
            policy.AgreementPolicyError,
            "does not match",
        ):
            policy.validate_decision(value, self.candidate)
        value = approved_decision()
        value["scope"] = "PRODUCTION"
        with self.assertRaisesRegex(policy.AgreementPolicyError, "scope"):
            policy.validate_decision(value, self.candidate)

    def test_approved_decision_requires_all_thresholds(self) -> None:
        value = approved_decision()
        value["selected_maximum_offset_difference_ms"] = None
        with self.assertRaisesRegex(policy.AgreementPolicyError, "threshold"):
            policy.validate_decision(value, self.candidate)

    def test_decision_status_mapping(self) -> None:
        self.assertEqual(
            policy.decision_status("REVISION_REQUIRED"),
            policy.REVISION_STATUS,
        )
        self.assertEqual(
            policy.decision_status("REJECTED"),
            policy.REJECTED_STATUS,
        )
        self.assertEqual(
            policy.decision_status("APPROVED"),
            policy.APPROVED_STATUS,
        )


class TieBreakerTests(unittest.TestCase):
    def test_deterministic_tie_breaker_uses_all_contract_keys(self) -> None:
        base = {
            "temporal_iou": 0.5,
            "overlap_duration_ms": 100,
            "onset_difference_ms": 20,
            "offset_difference_ms": 20,
            "rater_a_event_id": "A2",
            "rater_b_event_id": "B2",
        }
        values = [
            {**base, "rater_a_event_id": "A2"},
            {**base, "rater_a_event_id": "A1"},
            {**base, "offset_difference_ms": 10},
            {**base, "onset_difference_ms": 10},
            {**base, "overlap_duration_ms": 110},
            {**base, "temporal_iou": 0.6},
        ]
        ranked = policy.rank_candidates_deterministically(reversed(values))
        self.assertEqual(
            [
                (
                    item["temporal_iou"],
                    item["overlap_duration_ms"],
                    item["onset_difference_ms"],
                    item["offset_difference_ms"],
                    item["rater_a_event_id"],
                )
                for item in ranked
            ],
            [
                (0.6, 100, 20, 20, "A2"),
                (0.5, 110, 20, 20, "A2"),
                (0.5, 100, 10, 20, "A2"),
                (0.5, 100, 20, 10, "A2"),
                (0.5, 100, 20, 20, "A1"),
                (0.5, 100, 20, 20, "A2"),
            ],
        )


class PackageTests(unittest.TestCase):
    def test_missing_decision_generates_six_nonoperational_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "SES_000001"
            report = policy.build_policy_review_package(
                stage19_dir=STAGE19_DIR,
                output_dir=output,
            )
            self.assertEqual(
                report["current_status"],
                policy.AWAITING_STATUS,
            )
            self.assertFalse(report["decision_file_present"])
            self.assertFalse(report["policy_operational"])
            self.assertFalse(report["agreement_recalculated"])
            self.assertEqual(
                sorted(path.name for path in output.iterdir()),
                sorted(policy.OUTPUT_NAMES),
            )
            candidates = load_strict_json(
                output / "agreement_policy_candidates.json"
            )
            candidate = candidates["candidates"][0]
            self.assertIsNone(candidate["minimum_temporal_iou"])
            self.assertIsNone(candidate["maximum_onset_difference_ms"])
            self.assertIsNone(candidate["maximum_offset_difference_ms"])
            self.assertFalse(
                candidates["thresholds_derived_from_current_raters"]
            )

    def test_review_packet_reports_stage13_tie_breaker_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            policy.build_policy_review_package(
                stage19_dir=STAGE19_DIR,
                output_dir=output,
            )
            packet = load_strict_json(
                output / "agreement_policy_review_packet.json"
            )
            contract = packet["stage13_contract_review"]
            self.assertFalse(contract["tie_breaker_contract_aligned"])
            self.assertFalse(contract["candidate_rule_applied"])
            self.assertEqual(
                contract["conflict_code"],
                "TIE_BREAKER_CONTRACT_REVIEW_REQUIRED",
            )
            self.assertFalse(packet["agreement_recalculated"])
            self.assertFalse(packet["kappa_recalculated"])

    def test_stage19_and_rater_hashes_are_immutable(self) -> None:
        protected = [
            *STAGE19_DIR.iterdir(),
            RATER_DIR / "rater_a" / "annotation_events.json",
            RATER_DIR / "rater_b" / "annotation_events.json",
        ]
        protected = sorted(
            path for path in protected if path.is_file()
        )
        before = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in protected
        }
        with tempfile.TemporaryDirectory() as directory:
            policy.build_policy_review_package(
                stage19_dir=STAGE19_DIR,
                output_dir=Path(directory) / "out",
            )
        after = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in protected
        }
        self.assertEqual(before, after)

    def test_strict_json_and_no_nonfinite_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            policy.build_policy_review_package(
                stage19_dir=STAGE19_DIR,
                output_dir=output,
            )
            for path in output.glob("*.json"):
                value = json.loads(
                    path.read_text("utf-8"),
                    parse_constant=lambda item: self.fail(item),
                )
                self.assertIsInstance(value, dict)
            self.assertEqual(list(output.glob("*.tmp")), [])

    def test_approved_decision_creates_one_immutable_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            policy.build_policy_review_package(
                stage19_dir=STAGE19_DIR,
                output_dir=output,
            )
            decision_path = output / "agreement_policy_decision.json"
            write_json(decision_path, approved_decision())
            report = policy.build_policy_review_package(
                stage19_dir=STAGE19_DIR,
                output_dir=output,
            )
            self.assertEqual(
                report["current_status"],
                policy.APPROVED_STATUS,
            )
            self.assertEqual(report["policy_status"], "APPROVED")
            snapshot_path = (
                output / "approved_agreement_policy_snapshot.json"
            )
            snapshot = load_strict_json(snapshot_path)
            self.assertEqual(snapshot["policy_status"], "APPROVED")
            self.assertTrue(snapshot["operational"])
            before = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
            repeated = policy.build_policy_review_package(
                stage19_dir=STAGE19_DIR,
                output_dir=output,
            )
            after = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
            self.assertEqual(
                repeated["current_status"],
                policy.VALIDATION_FAILED_STATUS,
            )
            self.assertEqual(before, after)

    def test_invalid_decision_is_validation_failed_without_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            policy.build_policy_review_package(
                stage19_dir=STAGE19_DIR,
                output_dir=output,
            )
            value = approved_decision()
            value["selected_minimum_temporal_iou"] = 2
            write_json(output / "agreement_policy_decision.json", value)
            report = policy.build_policy_review_package(
                stage19_dir=STAGE19_DIR,
                output_dir=output,
            )
            self.assertEqual(
                report["current_status"],
                policy.VALIDATION_FAILED_STATUS,
            )
            self.assertFalse(
                (output / "approved_agreement_policy_snapshot.json").exists()
            )

    def test_revision_and_rejection_decisions_do_not_create_snapshot(self) -> None:
        for decision, expected in (
            ("REVISION_REQUIRED", policy.REVISION_STATUS),
            ("REJECTED", policy.REJECTED_STATUS),
        ):
            with (
                self.subTest(decision=decision),
                tempfile.TemporaryDirectory() as directory,
            ):
                output = Path(directory) / "out"
                policy.build_policy_review_package(
                    stage19_dir=STAGE19_DIR,
                    output_dir=output,
                )
                value = approved_decision()
                value["decision"] = decision
                value["selected_minimum_temporal_iou"] = None
                value["selected_maximum_onset_difference_ms"] = None
                value["selected_maximum_offset_difference_ms"] = None
                write_json(output / "agreement_policy_decision.json", value)
                report = policy.build_policy_review_package(
                    stage19_dir=STAGE19_DIR,
                    output_dir=output,
                )
                self.assertEqual(report["current_status"], expected)
                expected_policy_status = (
                    "REJECTED"
                    if decision == "REJECTED"
                    else "REVIEW_REQUIRED"
                )
                self.assertEqual(
                    report["policy_status"],
                    expected_policy_status,
                )
                self.assertFalse(
                    (
                        output
                        / "approved_agreement_policy_snapshot.json"
                    ).exists()
                )

    def test_nonfinite_decision_json_is_validation_failed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            policy.build_policy_review_package(
                stage19_dir=STAGE19_DIR,
                output_dir=output,
            )
            (output / "agreement_policy_decision.json").write_text(
                json.dumps(approved_decision()).replace("0.5", "NaN"),
                encoding="utf-8",
            )
            report = policy.build_policy_review_package(
                stage19_dir=STAGE19_DIR,
                output_dir=output,
            )
            self.assertEqual(
                report["current_status"],
                policy.VALIDATION_FAILED_STATUS,
            )


if __name__ == "__main__":
    unittest.main()
