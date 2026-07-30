"""Stage 16 manual-review contracts without automated human approval."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Iterable

from app.vision.dataset_manifest_models import DatasetSplitAssignment


class ManualReviewDecisionValue(str, Enum):
    REVIEW_PENDING = "REVIEW_PENDING"
    APPROVED_FOR_ANNOTATION = "APPROVED_FOR_ANNOTATION"
    RECORDING_REQUIRED = "RECORDING_REQUIRED"
    EXCLUDED = "EXCLUDED"


class ManualReviewReason(str, Enum):
    HEAD_POSE_FAILURE_WITH_USABLE_VIDEO = "HEAD_POSE_FAILURE_WITH_USABLE_VIDEO"
    TEMPORARY_FACE_OCCLUSION = "TEMPORARY_FACE_OCCLUSION"
    EXCESSIVE_HEAD_ROTATION = "EXCESSIVE_HEAD_ROTATION"
    CAMERA_MOVEMENT = "CAMERA_MOVEMENT"
    PROLONGED_ANALYSIS_FAILURE = "PROLONGED_ANALYSIS_FAILURE"
    VIDEO_USABLE_FOR_OBSERVABLE_ANNOTATION = (
        "VIDEO_USABLE_FOR_OBSERVABLE_ANNOTATION"
    )
    VIDEO_NOT_USABLE_FOR_ANNOTATION = "VIDEO_NOT_USABLE_FOR_ANNOTATION"
    OTHER = "OTHER"


@dataclass(frozen=True)
class PilotManualReviewDecision:
    participant_id: str
    session_id: str
    reviewer_id: str | None
    decision: str
    reason_codes: tuple[str, ...]
    reviewed_at: str | None
    notes: str | None

    def __post_init__(self) -> None:
        if self.participant_id != "PTC_000001":
            raise ValueError("manual review participant mismatch")
        if self.session_id != "SES_000001":
            raise ValueError("manual review session mismatch")
        allowed_decisions = {item.value for item in ManualReviewDecisionValue}
        if self.decision not in allowed_decisions:
            raise ValueError("invalid manual review decision")
        allowed_reasons = {item.value for item in ManualReviewReason}
        if any(item not in allowed_reasons for item in self.reason_codes):
            raise ValueError("invalid manual review reason")
        if self.decision == ManualReviewDecisionValue.REVIEW_PENDING.value:
            if self.reviewer_id is not None or self.reviewed_at is not None:
                raise ValueError("pending review cannot identify a completed reviewer")
            if self.reason_codes:
                raise ValueError("pending review cannot contain completed reasons")
            return
        if not isinstance(self.reviewer_id, str) or not self.reviewer_id.strip():
            raise ValueError("completed review requires reviewer_id")
        if not isinstance(self.reviewed_at, str):
            raise ValueError("completed review requires reviewed_at")
        try:
            timestamp = datetime.fromisoformat(
                self.reviewed_at.replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise ValueError("reviewed_at must be ISO-8601") from exc
        if timestamp.tzinfo is None:
            raise ValueError("reviewed_at must include a timezone")
        if not self.reason_codes:
            raise ValueError("completed review requires reason_codes")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PilotManualReviewDecision":
        required = {
            "participant_id", "session_id", "reviewer_id", "decision",
            "reason_codes", "reviewed_at", "notes",
        }
        missing = required - set(value)
        if missing:
            raise ValueError(
                f"manual review fields missing: {', '.join(sorted(missing))}"
            )
        extra = set(value) - required
        if extra:
            raise ValueError(
                f"manual review fields not allowed: {', '.join(sorted(extra))}"
            )
        if not isinstance(value["reason_codes"], list):
            raise ValueError("reason_codes must be a list")
        return cls(
            participant_id=value["participant_id"],
            session_id=value["session_id"],
            reviewer_id=value["reviewer_id"],
            decision=value["decision"],
            reason_codes=tuple(value["reason_codes"]),
            reviewed_at=value["reviewed_at"],
            notes=value["notes"],
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def validate_frame_timestamp(timestamp_ms: int, duration_ms: int) -> None:
    if isinstance(timestamp_ms, bool) or not isinstance(timestamp_ms, int):
        raise ValueError("frame timestamp must be an integer")
    if timestamp_ms < 0 or timestamp_ms >= duration_ms:
        raise ValueError("frame timestamp is outside the video")


def context_frame_timestamps(
    candidate_timestamp_ms: int,
    *,
    duration_ms: int,
    offsets_ms: tuple[int, ...] = (-500, 0, 500),
) -> tuple[int, ...]:
    values = tuple(candidate_timestamp_ms + offset for offset in offsets_ms)
    for value in values:
        validate_frame_timestamp(value, duration_ms)
    return values


def interval_for_timestamp(
    timestamp_ms: int, answers: Iterable[dict[str, Any]]
) -> dict[str, Any] | None:
    for answer in answers:
        if (
            answer["start_timestamp_ms"]
            <= timestamp_ms
            < answer["end_timestamp_ms"]
        ):
            return answer
    return None


def _spread(values: list[int], limit: int) -> list[int]:
    ordered = sorted(set(values))
    if len(ordered) <= limit:
        return ordered
    if limit == 1:
        return [ordered[len(ordered) // 2]]
    indices = [
        round(index * (len(ordered) - 1) / (limit - 1))
        for index in range(limit)
    ]
    return [ordered[index] for index in indices]


def select_representative_candidates(
    *,
    answer: dict[str, Any],
    missing_segments: Iterable[dict[str, Any]],
    head_jump_timestamps: Iterable[int],
    posture_jump_timestamps: Iterable[int],
    maximum_candidates: int = 5,
) -> list[dict[str, Any]]:
    start = answer["start_timestamp_ms"]
    end = answer["end_timestamp_ms"]
    candidates: list[dict[str, Any]] = []
    overlapping = [
        item for item in missing_segments
        if item["end_timestamp_ms"] >= start
        and item["start_timestamp_ms"] < end
    ]
    if overlapping:
        longest = max(
            overlapping,
            key=lambda item: (
                item["duration_sec"],
                -item["start_timestamp_ms"],
            ),
        )
        midpoint = (
            longest["start_timestamp_ms"] + longest["end_timestamp_ms"]
        ) // 2
        midpoint = min(max(midpoint, start + 500), end - 501)
        candidates.append({
            "timestamp_ms": midpoint,
            "candidate_type": "HEAD_POSE_LONGEST_MISSING_SEGMENT",
            "source_start_timestamp_ms": longest["start_timestamp_ms"],
            "source_end_timestamp_ms": longest["end_timestamp_ms"],
        })
    head = [
        value for value in head_jump_timestamps
        if start + 500 <= value < end - 500
    ]
    posture = [
        value for value in posture_jump_timestamps
        if start + 500 <= value < end - 500
    ]
    for value in _spread(head, 2):
        candidates.append({
            "timestamp_ms": value,
            "candidate_type": "HEAD_POSE_RAW_JUMP_CANDIDATE",
        })
    for value in _spread(posture, 2):
        candidates.append({
            "timestamp_ms": value,
            "candidate_type": "POSTURE_RAW_JUMP_CANDIDATE",
        })
    unique: list[dict[str, Any]] = []
    seen: set[int] = set()
    for item in candidates:
        if item["timestamp_ms"] not in seen:
            unique.append(item)
            seen.add(item["timestamp_ms"])
    if not unique:
        unique.append({
            "timestamp_ms": (start + end) // 2,
            "candidate_type": "ANSWER_INTERVAL_REPRESENTATIVE",
        })
    return unique[:maximum_candidates]


def create_development_split_assignment(
    *,
    participant_id: str,
    session_id: str,
    answer_ids: Iterable[str],
    operational_assignments: Iterable[DatasetSplitAssignment] = (),
) -> tuple[DatasetSplitAssignment, dict[str, Any]]:
    prior = {
        item.split for item in operational_assignments
        if item.participant_id == participant_id
    }
    if prior and prior != {"DEVELOPMENT"}:
        raise ValueError("existing operational split assignment conflicts")
    assignment = DatasetSplitAssignment(
        participant_id=participant_id,
        split="DEVELOPMENT",
        seed=160001,
        assignment_method="PARTICIPANT_LEVEL_DETERMINISTIC",
    )
    answers = tuple(answer_ids)
    if not answers or len(set(answers)) != len(answers):
        raise ValueError("answer_ids must be unique and non-empty")
    linkage = {
        "participant": {
            "participant_id": participant_id,
            "split_name": "DEVELOPMENT",
        },
        "sessions": [
            {"session_id": session_id, "split_name": "DEVELOPMENT"}
        ],
        "answers": [
            {"answer_id": item, "split_name": "DEVELOPMENT"}
            for item in answers
        ],
        "leakage_detected": False,
        "other_split_memberships": [],
        "deterministic": True,
    }
    return assignment, linkage


def map_gate_status(
    decision: PilotManualReviewDecision | None,
    *,
    split_valid: bool,
    automatic_quality_passed: bool,
) -> str:
    if (
        decision is None
        or decision.decision == ManualReviewDecisionValue.REVIEW_PENDING.value
    ):
        return "awaiting_human_manual_review_decision"
    if decision.decision == ManualReviewDecisionValue.RECORDING_REQUIRED.value:
        return "pilot_video_recording_required"
    if decision.decision == ManualReviewDecisionValue.EXCLUDED.value:
        return "pilot_video_excluded"
    if not split_valid or not automatic_quality_passed:
        return "awaiting_human_manual_review_decision"
    return "pilot_video_annotation_ready"
