"""Non-operational pilot dataset release candidate gate."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.vision.consent_models import (
    ConsentPurpose,
    ConsentReference,
    evaluate_consent_gate,
)
from app.vision.dataset_manifest_models import DatasetSplitAssignment
from app.vision.manual_review_models import ManualReviewDecision
from app.vision.pilot_collection_models import DatasetReleaseCandidate


@dataclass(frozen=True)
class DatasetReleaseGateResult:
    release_candidate_id: str
    eligible: bool
    result_status: str
    failed_conditions: tuple[str, ...]
    dataset_frozen: bool
    operationally_approved: bool

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["failed_conditions"] = list(self.failed_conditions)
        return value


def evaluate_dataset_release_gate(
    candidate: DatasetReleaseCandidate,
    *,
    consent: ConsentReference | None,
    withdrawn: bool,
    file_hash_valid: bool,
    video_checks_passed: bool,
    baseline_available: bool,
    answer_intervals_valid: bool,
    manual_review: ManualReviewDecision | None,
    split_assignment: DatasetSplitAssignment | None,
    split_leakage_detected: bool,
) -> DatasetReleaseGateResult:
    failures: list[str] = []
    if consent is None or not all(
        evaluate_consent_gate(consent, purpose).allowed
        for purpose in (
            ConsentPurpose.VIDEO_COLLECTION.value,
            ConsentPurpose.AUTOMATED_ANALYSIS.value,
            ConsentPurpose.RESEARCH_USE.value,
        )
    ):
        failures.append("CONSENT_INVALID")
    if withdrawn:
        failures.append("WITHDRAWAL_BLOCK")
    if not file_hash_valid:
        failures.append("FILE_HASH_INVALID")
    if not video_checks_passed:
        failures.append("VIDEO_CHECKS_NOT_PASSED")
    if not baseline_available:
        failures.append("BASELINE_UNAVAILABLE")
    if not answer_intervals_valid:
        failures.append("ANSWER_INTERVALS_INVALID")
    if (
        manual_review is None
        or manual_review.decision != "APPROVED_FOR_ANNOTATION"
    ):
        failures.append("MANUAL_REVIEW_NOT_APPROVED")
    if split_assignment is None:
        failures.append("PARTICIPANT_SPLIT_MISSING")
    elif split_assignment.participant_id != candidate.participant_id:
        failures.append("PARTICIPANT_SPLIT_MISMATCH")
    if split_leakage_detected:
        failures.append("SPLIT_LEAKAGE")
    eligible = not failures
    return DatasetReleaseGateResult(
        candidate.release_candidate_id,
        eligible,
        "PILOT_CANDIDATE" if eligible else "REVIEW_REQUIRED",
        tuple(failures),
        False,
        False,
    )
