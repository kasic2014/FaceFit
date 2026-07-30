import copy
import json
import tempfile
import unittest
from pathlib import Path

from app.vision.annotation_agreement import compare_event_sets
from app.vision.annotation_models import AnnotationEvent
from app.vision.annotation_policy_revision import (
    APPROVED_STATUS,
    AWAITING_STATUS,
    MATCHING_POLICY_VERSION,
    PolicyRevisionError,
    TieBreakerPolicy,
    build_policy_revision_package,
    compatibility_fixture_results,
    decision_template,
    load_decision,
    match_fixture_events,
    unresolved_tie_breaker_policy,
    validate_decision,
)
from app.vision.pilot_video_intake import load_strict_json, sha256_file


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STAGE191_DIR = (
    PROJECT_ROOT
    / "data"
    / "output"
    / "pilot_annotation_agreement_policy"
    / "SES_000001"
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


def _event(
    event_id: str,
    start: int,
    end: int,
    rater_id: str,
    layer: str,
) -> AnnotationEvent:
    return AnnotationEvent(
        event_id=event_id,
        annotation_session_id="ANN_FIXTURE",
        answer_id="ANS_FIXTURE",
        rater_id=rater_id,
        label_id="LBL_FIXTURE",
        start_timestamp_ms=start,
        end_timestamp_ms=end,
        direction=None,
        rater_confidence=1.0,
        layer=layer,
    )


class AnnotationPolicyRevisionStage192Tests(unittest.TestCase):
    def test_default_policy_is_unresolved_nonoperational(self):
        policy = unresolved_tie_breaker_policy()
        self.assertEqual("UNRESOLVED", policy.strategy)
        self.assertEqual("REVIEW_REQUIRED", policy.status)
        self.assertFalse(policy.operational)
        self.assertEqual((), policy.ordering_rules)

    def test_strategy_enum_rejects_unknown_value(self):
        value = unresolved_tie_breaker_policy().to_dict()
        value["strategy"] = "CURRENT_RESULT_OPTIMIZED"
        with self.assertRaises(PolicyRevisionError):
            TieBreakerPolicy.from_dict(value)

    def test_legacy_fixture_match_reproduces_stage13(self):
        a_events = [_event("EVT_A", 0, 100, "RATER_A", "RATER_A_ORIGINAL")]
        b_events = [
            _event("EVT_B_001", 0, 50, "RATER_B", "RATER_B_ORIGINAL"),
            _event("EVT_B_002", 0, 200, "RATER_B", "RATER_B_ORIGINAL"),
        ]
        stage13 = compare_event_sets(a_events, b_events)
        fixture_dicts_a = [
            {
                "event_id": item.event_id,
                "answer_id": item.answer_id,
                "label_id": item.label_id,
                "direction": item.direction,
                "start_timestamp_ms": item.start_timestamp_ms,
                "end_timestamp_ms": item.end_timestamp_ms,
            }
            for item in a_events
        ]
        fixture_dicts_b = [
            {
                "event_id": item.event_id,
                "answer_id": item.answer_id,
                "label_id": item.label_id,
                "direction": item.direction,
                "start_timestamp_ms": item.start_timestamp_ms,
                "end_timestamp_ms": item.end_timestamp_ms,
            }
            for item in b_events
        ]
        legacy = match_fixture_events(
            fixture_dicts_a, fixture_dicts_b, "LEGACY_STAGE13"
        )
        self.assertEqual(stage13[0].rater_b_event_id, legacy[0]["rater_b_event_id"])
        self.assertEqual("EVT_B_001", legacy[0]["rater_b_event_id"])

    def test_v2_uses_multicriteria_after_equal_iou(self):
        fixtures = compatibility_fixture_results()["metric_fixture_comparisons"]
        by_id = {item["fixture_id"]: item for item in fixtures}
        overlap = by_id["same_iou_different_overlap"]
        onset = by_id["same_iou_overlap_different_onset"]
        lexical = by_id["all_metrics_same_event_id_only"]
        self.assertEqual("EVT_B_002", overlap["v2_selected_event_id"])
        self.assertEqual("EVT_B_002", onset["v2_selected_event_id"])
        self.assertEqual("EVT_B_001", lexical["v2_selected_event_id"])
        self.assertTrue(overlap["strategies_differ"])
        self.assertTrue(onset["strategies_differ"])

    def test_fixture_matching_is_input_order_invariant_and_one_to_one(self):
        result = compatibility_fixture_results()
        self.assertTrue(all(result["input_order_invariant"].values()))
        self.assertTrue(all(result["one_to_one_duplicate_prevented"].values()))
        self.assertTrue(result["all_checks_passed"])
        self.assertFalse(result["real_rater_annotation_loaded"])

    def test_fixture_matcher_rejects_real_answer_namespace(self):
        event = {
            "event_id": "EVT_A_001",
            "answer_id": "ANS_000001",
            "label_id": "LBL_FIXTURE",
            "direction": None,
            "start_timestamp_ms": 0,
            "end_timestamp_ms": 100,
        }
        with self.assertRaises(PolicyRevisionError):
            match_fixture_events([event], [], "LEGACY_STAGE13")

    def test_decision_template_has_no_threshold_approval_option(self):
        template = decision_template()
        self.assertEqual("DEFERRED", template["threshold_decision"])
        self.assertEqual("REVIEW_PENDING", template["decision"])
        self.assertIsNone(template["selected_tie_breaker_strategy"])
        self.assertNotIn("APPROVED", {"DEFERRED", "REVISION_REQUIRED", "REJECTED"})

    def test_final_decision_requires_reviewer_and_reviewed_at(self):
        decision = decision_template()
        decision.update(
            {
                "decision": "APPROVE_LEGACY_STAGE13",
                "selected_tie_breaker_strategy": "LEGACY_STAGE13",
                "rationale": "Reviewed against compatibility fixtures.",
            }
        )
        with self.assertRaises(PolicyRevisionError):
            validate_decision(decision)
        decision["reviewer_id"] = "REVIEWER_001"
        with self.assertRaises(PolicyRevisionError):
            validate_decision(decision)

    def test_approval_cannot_approve_thresholds(self):
        decision = decision_template()
        decision.update(
            {
                "reviewer_id": "REVIEWER_001",
                "decision": "APPROVE_LEGACY_STAGE13",
                "selected_tie_breaker_strategy": "LEGACY_STAGE13",
                "threshold_decision": "REVISION_REQUIRED",
                "reviewed_at": "2026-07-30T12:00:00+09:00",
                "rationale": "Thresholds require a separate review.",
            }
        )
        with self.assertRaises(PolicyRevisionError):
            validate_decision(decision)

    def test_semantic_version_is_strict(self):
        decision = decision_template()
        decision["candidate_version"] = "version-0.2"
        with self.assertRaises(PolicyRevisionError):
            validate_decision(decision)
        self.assertEqual(MATCHING_POLICY_VERSION, decision_template()["candidate_version"])

    def test_strict_json_rejects_duplicate_key_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as temp:
            duplicate = Path(temp) / "duplicate.json"
            duplicate.write_text(
                '{"policy_id":"a","policy_id":"b"}', encoding="utf-8"
            )
            with self.assertRaises(ValueError):
                load_decision(duplicate)
            nonfinite = Path(temp) / "nonfinite.json"
            nonfinite.write_text('{"value":NaN}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_strict_json(nonfinite)

    def test_missing_decision_builds_awaiting_package_without_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "revision_0_2_0"
            before = [sha256_file(path) for path in RATER_PATHS]
            report = build_policy_revision_package(
                STAGE191_DIR, output, rater_annotation_paths=RATER_PATHS
            )
            self.assertEqual(AWAITING_STATUS, report["current_status"])
            self.assertFalse(
                (output / "approved_tie_breaker_policy_snapshot.json").exists()
            )
            self.assertEqual(before, [sha256_file(path) for path in RATER_PATHS])
            candidate = load_strict_json(
                output / "agreement_policy_candidate_0_2_0.json"
            )
            self.assertEqual("0.2.0", candidate["policy_version"])
            self.assertTrue(
                all(
                    value is None
                    for value in candidate["temporal_thresholds"].values()
                )
            )

    def test_valid_human_approval_creates_snapshot_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            decision_path = root / "decision.json"
            decision = decision_template()
            decision.update(
                {
                    "reviewer_id": "REVIEWER_001",
                    "decision": "APPROVE_DETERMINISTIC_MULTI_CRITERIA_V2",
                    "selected_tie_breaker_strategy": (
                        "DETERMINISTIC_MULTI_CRITERIA_V2"
                    ),
                    "reviewed_at": "2026-07-30T12:00:00+09:00",
                    "rationale": "Human governance decision for this fixture.",
                }
            )
            decision_path.write_text(
                json.dumps(decision, allow_nan=False), encoding="utf-8"
            )
            output = root / "revision_0_2_0"
            report = build_policy_revision_package(
                STAGE191_DIR, output, decision_path=decision_path
            )
            self.assertEqual(APPROVED_STATUS, report["current_status"])
            snapshot = load_strict_json(
                output / "approved_tie_breaker_policy_snapshot.json"
            )
            self.assertEqual(
                "DETERMINISTIC_MULTI_CRITERIA_V2", snapshot["strategy"]
            )

    def test_same_version_overwrite_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "revision_0_2_0"
            build_policy_revision_package(STAGE191_DIR, output)
            with self.assertRaises(PolicyRevisionError):
                build_policy_revision_package(STAGE191_DIR, output)

    def test_invalid_decision_produces_validation_failed_status(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            decision_path = root / "decision.json"
            decision_path.write_text(
                json.dumps(
                    {
                        **decision_template(),
                        "decision": "APPROVE_LEGACY_STAGE13",
                        "selected_tie_breaker_strategy": "LEGACY_STAGE13",
                    }
                ),
                encoding="utf-8",
            )
            report = build_policy_revision_package(
                STAGE191_DIR,
                root / "revision_0_2_0",
                decision_path=decision_path,
            )
            self.assertEqual(
                "agreement_policy_validation_failed", report["current_status"]
            )
            self.assertFalse(report["valid"])

    def test_stage191_candidate_and_rater_hashes_are_preserved(self):
        previous = STAGE191_DIR / "agreement_policy_candidates.json"
        protected = [previous, *RATER_PATHS]
        before = {path: sha256_file(path) for path in protected}
        with tempfile.TemporaryDirectory() as temp:
            build_policy_revision_package(
                STAGE191_DIR,
                Path(temp) / "revision_0_2_0",
                rater_annotation_paths=RATER_PATHS,
            )
        after = {path: sha256_file(path) for path in protected}
        self.assertEqual(before, after)

    def test_pending_decision_cannot_smuggle_selection_or_metadata(self):
        decision = copy.deepcopy(decision_template())
        decision["selected_tie_breaker_strategy"] = "LEGACY_STAGE13"
        with self.assertRaises(PolicyRevisionError):
            validate_decision(decision)
        decision = copy.deepcopy(decision_template())
        decision["reviewer_id"] = "REVIEWER_001"
        with self.assertRaises(PolicyRevisionError):
            validate_decision(decision)


if __name__ == "__main__":
    unittest.main()
