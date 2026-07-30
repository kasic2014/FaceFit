"""Stage 17 contracts for human-approved pilot annotation readiness."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.vision.consent_models import ConsentReference
from app.vision.dataset_manifest_models import DatasetSplitAssignment
from app.vision.dataset_release_gate import (
    DatasetReleaseGateResult,
    evaluate_dataset_release_gate,
)
from app.vision.manual_review_models import ManualReviewDecision
from app.vision.pilot_collection_models import DatasetReleaseCandidate
from app.vision.pilot_manual_review import PilotManualReviewDecision


EXPECTED_PARTICIPANT_ID = "PTC_000001"
EXPECTED_SESSION_ID = "SES_000001"
EXPECTED_ANSWER_IDS = (
    "ANS_000001",
    "ANS_000002",
    "ANS_000003",
    "ANS_000004",
)
EXPECTED_QUALITY_CHECKS = frozenset({
    "VIDEO_FILE_EXISTS",
    "VIDEO_HASH_VALID",
    "VIDEO_DECODABLE",
    "DURATION_VALID",
    "RESOLUTION_VALID",
    "SOURCE_FPS_VALID",
    "FACE_AVAILABLE",
    "BOTH_SHOULDERS_AVAILABLE",
    "SINGLE_TARGET_VALID",
    "BASELINE_AVAILABLE",
    "ANSWER_INTERVALS_VALID",
})


@dataclass(frozen=True)
class Stage17GateEvaluation:
    final_status: str
    condition_checks: dict[str, bool]
    split_validation: dict[str, Any]
    stage14_gate_result: DatasetReleaseGateResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_status": self.final_status,
            "condition_checks": dict(self.condition_checks),
            "split_validation": dict(self.split_validation),
            "stage14_gate_result": self.stage14_gate_result.to_dict(),
        }


def validate_decision_file_pair(
    template_value: dict[str, Any],
    decision_value: dict[str, Any],
) -> dict[str, bool]:
    """Validate that the pending template and completed decision stay separate."""
    template = PilotManualReviewDecision.from_dict(template_value)
    decision = PilotManualReviewDecision.from_dict(decision_value)
    checks = {
        "template_is_review_pending": template.decision == "REVIEW_PENDING",
        "decision_is_human_approval":
            decision.decision == "APPROVED_FOR_ANNOTATION",
        "participant_reference_matches":
            template.participant_id == decision.participant_id,
        "session_reference_matches":
            template.session_id == decision.session_id,
        "reviewer_present": bool(decision.reviewer_id),
        "reviewed_at_present": bool(decision.reviewed_at),
        "template_and_decision_differ": template_value != decision_value,
    }
    if not all(checks.values()):
        failed = ", ".join(key for key, value in checks.items() if not value)
        raise ValueError(f"manual review decision pair invalid: {failed}")
    return checks


def validate_development_split(
    split_value: dict[str, Any],
    *,
    participant_id: str = EXPECTED_PARTICIPANT_ID,
    session_id: str = EXPECTED_SESSION_ID,
    answer_ids: tuple[str, ...] = EXPECTED_ANSWER_IDS,
) -> dict[str, Any]:
    """Validate participant-level DEVELOPMENT linkage and leakage controls."""
    try:
        assignment_value = split_value["assignment"]
        linkage = split_value["linkage"]
        scan = split_value["existing_assignment_scan"]
        assignment = DatasetSplitAssignment(
            assignment_value["participant_id"],
            assignment_value["split"],
            assignment_value["seed"],
            assignment_value["assignment_method"],
        )
        participant = linkage["participant"]
        sessions = linkage["sessions"]
        answers = linkage["answers"]
    except (KeyError, TypeError) as exc:
        raise ValueError("invalid development split structure") from exc

    session_pairs = {
        (item.get("session_id"), item.get("split_name"))
        for item in sessions
        if isinstance(item, dict)
    }
    answer_pairs = {
        (item.get("answer_id"), item.get("split_name"))
        for item in answers
        if isinstance(item, dict)
    }
    expected_answer_pairs = {
        (answer_id, "DEVELOPMENT") for answer_id in answer_ids
    }
    checks = {
        "assignment_participant_matches":
            assignment.participant_id == participant_id,
        "assignment_is_development": assignment.split == "DEVELOPMENT",
        "participant_linkage_is_development": participant == {
            "participant_id": participant_id,
            "split_name": "DEVELOPMENT",
        },
        "session_linkage_is_development":
            session_pairs == {(session_id, "DEVELOPMENT")},
        "answer_linkage_is_development":
            answer_pairs == expected_answer_pairs
            and len(answers) == len(answer_ids),
        "leakage_not_detected": linkage.get("leakage_detected") is False,
        "no_other_split_memberships":
            linkage.get("other_split_memberships") == [],
        "deterministic_assignment": linkage.get("deterministic") is True,
        "no_operational_assignment_conflict":
            scan.get("operational_conflict") is False,
        "fixture_assignments_not_operational":
            scan.get("fixture_assignments_are_not_operational") is True,
    }
    return {
        "valid": all(checks.values()),
        "checks": checks,
        "participant_id": participant_id,
        "session_id": session_id,
        "answer_ids": list(answer_ids),
        "split_name": "DEVELOPMENT",
        "fixture_only_collision_ignored": bool(
            scan.get("fixture_only_collision_found")
        ),
    }


def _consent_reference(value: dict[str, Any]) -> ConsentReference:
    return ConsentReference(
        value["consent_reference_id"],
        value["participant_id"],
        value["consent_status"],
        value["schema_version"],
        value["video_collection_allowed"],
        value["automated_analysis_allowed"],
        value["research_use_allowed"],
        value["model_development_use_allowed"],
        value["withdrawn_at"],
    )


def _stage14_utc_timestamp(value: str | None) -> str:
    if not value:
        raise ValueError("completed review requires reviewed_at")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("reviewed_at must include a timezone")
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def evaluate_stage17_annotation_gate(
    *,
    decision: PilotManualReviewDecision,
    split_value: dict[str, Any],
    consent_source: dict[str, Any],
    metadata_source: dict[str, Any],
    video_metadata: dict[str, Any],
    quality_results: dict[str, Any],
    interval_validation: dict[str, Any],
    stage15_report: dict[str, Any],
) -> Stage17GateEvaluation:
    """Reexecute the Stage 14 release gate using preserved Stage 15 evidence."""
    split_validation = validate_development_split(split_value)
    assignment_value = split_value["assignment"]
    assignment = DatasetSplitAssignment(
        assignment_value["participant_id"],
        assignment_value["split"],
        assignment_value["seed"],
        assignment_value["assignment_method"],
    )
    consent = _consent_reference(consent_source)

    quality_checks = quality_results.get("checks", [])
    passed_types = {
        item.get("check_type")
        for item in quality_checks
        if isinstance(item, dict) and item.get("status") == "PASSED"
    }
    quality_all_passed = (
        len(quality_checks) == len(EXPECTED_QUALITY_CHECKS)
        and passed_types == EXPECTED_QUALITY_CHECKS
        and quality_results.get("summary", {}).get(
            "automatic_validation_passed"
        ) is True
    )
    answer_ids = tuple(
        item.get("answer_id")
        for item in interval_validation.get("answers", [])
        if isinstance(item, dict)
    )
    hash_valid = (
        video_metadata.get("hash_valid") is True
        and video_metadata.get("sha256") == metadata_source.get(
            "expected_sha256"
        )
        and video_metadata.get("sha256")
        == video_metadata.get("expected_sha256")
    )
    decode_valid = (
        video_metadata.get("decode", {}).get("full_decode_succeeded") is True
    )
    baseline_available = (
        stage15_report.get("baseline_summary", {}).get("available") is True
        and "BASELINE_AVAILABLE" in passed_types
    )
    answer_intervals_valid = (
        interval_validation.get("valid") is True
        and answer_ids == EXPECTED_ANSWER_IDS
        and "ANSWER_INTERVALS_VALID" in passed_types
    )
    consent_valid = (
        consent_source.get("consent_status") == "GRANTED"
        and consent_source.get("video_collection_allowed") is True
        and consent_source.get("automated_analysis_allowed") is True
        and consent_source.get("research_use_allowed") is True
        and consent_source.get("withdrawn_at") is None
        and consent_source.get("participant_id") == EXPECTED_PARTICIPANT_ID
        and metadata_source.get("consent_reference_id")
        == consent_source.get("consent_reference_id")
    )
    not_withdrawn = (
        metadata_source.get("withdrawn") is False
        and consent_source.get("withdrawn_at") is None
    )
    condition_checks = {
        "consent_granted_for_required_purposes": consent_valid,
        "withdrawal_absent": not_withdrawn,
        "video_sha256_matches": hash_valid,
        "video_full_decode_succeeded": decode_valid,
        "automatic_quality_checks_11_passed": quality_all_passed,
        "baseline_available": baseline_available,
        "four_answer_intervals_valid": answer_intervals_valid,
        "manual_review_approved":
            decision.decision == "APPROVED_FOR_ANNOTATION",
        "development_split_valid": split_validation["valid"],
    }

    manual_review = ManualReviewDecision(
        "REVIEW_SES_000001",
        EXPECTED_SESSION_ID,
        decision.reviewer_id or "",
        decision.decision,
        (),
        _stage14_utc_timestamp(decision.reviewed_at),
        decision.notes,
    )
    candidate = DatasetReleaseCandidate(
        "RELEASE_CANDIDATE_SES_000001",
        "ANNOTATION_READY_MANIFEST_SES_000001",
        EXPECTED_PARTICIPANT_ID,
        EXPECTED_SESSION_ID,
        answer_ids,
        "REVIEW_REQUIRED",
    )
    gate_result = evaluate_dataset_release_gate(
        candidate,
        consent=consent,
        withdrawn=not not_withdrawn,
        file_hash_valid=hash_valid,
        video_checks_passed=quality_all_passed and decode_valid,
        baseline_available=baseline_available,
        answer_intervals_valid=answer_intervals_valid,
        manual_review=manual_review,
        split_assignment=assignment if split_validation["valid"] else None,
        split_leakage_detected=not split_validation["valid"],
    )
    ready = all(condition_checks.values()) and gate_result.eligible
    return Stage17GateEvaluation(
        final_status=(
            "pilot_video_annotation_ready"
            if ready
            else "awaiting_human_manual_review_decision"
        ),
        condition_checks=condition_checks,
        split_validation=split_validation,
        stage14_gate_result=gate_result,
    )
