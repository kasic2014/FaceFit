"""Independent candidate-group selection for session neutral baselines."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import replace
from typing import Any, Iterable

from app.vision.neutral_baseline_models import (
    BaselineCandidateCollection,
    BaselineCandidateDecision,
    BaselineFailureReason,
    NeutralBaselineConfig,
    NeutralBaselineFrame,
)


VALID_TARGET_STATUSES = {
    "TARGET_INITIALIZED",
    "TARGET_TRACKED",
    "TARGET_REACQUIRED",
}


def _finite(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _finite_fields(payload: dict[str, Any], fields: tuple[str, ...]) -> bool:
    return all(_finite(payload.get(field)) for field in fields)


def evaluate_baseline_candidate(
    frame: NeutralBaselineFrame,
    config: NeutralBaselineConfig = NeutralBaselineConfig(),
) -> BaselineCandidateDecision:
    """Evaluate Head Pose, shoulder, nose, and face groups independently."""

    common_reasons: list[str] = []
    if (
        isinstance(frame.timestamp_ms, bool)
        or not isinstance(frame.timestamp_ms, int)
        or frame.timestamp_ms < 0
    ):
        common_reasons.append(BaselineFailureReason.INVALID_TIMESTAMP.value)
    if frame.candidate_count >= 2:
        common_reasons.append(
            BaselineFailureReason.MULTIPLE_PERSON_DETECTED.value
        )
    if (
        frame.target_id != "TARGET_001"
        or frame.target_status not in VALID_TARGET_STATUSES
    ):
        common_reasons.append(BaselineFailureReason.TARGET_NOT_AVAILABLE.value)
    common_available = not common_reasons

    head_reasons: list[str] = []
    head = frame.head_pose
    if not head.get("available") or head.get("failure_reason") == "FACE_NOT_DETECTED":
        head_reasons.append(BaselineFailureReason.INSUFFICIENT_FRAMES.value)
    if not _finite_fields(head, ("yaw_deg", "pitch_deg", "roll_deg")):
        head_reasons.append(BaselineFailureReason.NON_FINITE_VALUE.value)
    if (
        not _finite(head.get("confidence"))
        or float(head["confidence"]) < config.minimum_head_pose_confidence
    ):
        head_reasons.append(BaselineFailureReason.LOW_CONFIDENCE.value)
    velocity = frame.head_angular_velocity_deg_per_sec
    if velocity is not None:
        if not _finite(velocity):
            head_reasons.append(BaselineFailureReason.NON_FINITE_VALUE.value)
        elif abs(float(velocity)) > config.maximum_head_angular_velocity_deg_per_sec:
            head_reasons.append(
                BaselineFailureReason.UNSTABLE_HEAD_MOTION.value
            )
    if frame.head_jump_candidate:
        head_reasons.append(BaselineFailureReason.UNSTABLE_HEAD_MOTION.value)

    posture = frame.posture_raw
    temporal = frame.posture_temporal
    shoulder_reasons: list[str] = []
    if not posture.get("available") or not posture.get("shoulders_available"):
        shoulder_reasons.append(BaselineFailureReason.INSUFFICIENT_FRAMES.value)
    shoulder_fields = (
        "shoulder_tilt_deg",
        "shoulder_height_difference_norm",
        "shoulder_center_x",
        "shoulder_center_y",
        "shoulder_width_norm",
    )
    if not _finite_fields(posture, shoulder_fields):
        shoulder_reasons.append(BaselineFailureReason.NON_FINITE_VALUE.value)
    elif float(posture["shoulder_width_norm"]) <= 0.0:
        shoulder_reasons.append(BaselineFailureReason.NON_FINITE_VALUE.value)
    if (
        not _finite(posture.get("confidence"))
        or float(posture["confidence"]) < config.minimum_posture_confidence
    ):
        shoulder_reasons.append(BaselineFailureReason.LOW_CONFIDENCE.value)
    velocity_limits = (
        (
            "shoulder_center_velocity_norm_per_sec",
            config.maximum_shoulder_center_velocity_norm_per_sec,
        ),
        (
            "shoulder_tilt_velocity_deg_per_sec",
            config.maximum_shoulder_tilt_velocity_deg_per_sec,
        ),
        (
            "shoulder_width_change_rate_per_sec",
            config.maximum_shoulder_width_change_rate_per_sec,
        ),
    )
    for field, limit in velocity_limits:
        value = temporal.get(field)
        if value is None:
            continue
        if not _finite(value):
            shoulder_reasons.append(BaselineFailureReason.NON_FINITE_VALUE.value)
        elif abs(float(value)) > limit:
            shoulder_reasons.append(
                BaselineFailureReason.UNSTABLE_SHOULDER_MOTION.value
            )
    if frame.posture_jump_candidate:
        shoulder_reasons.append(
            BaselineFailureReason.UNSTABLE_SHOULDER_MOTION.value
        )

    nose_reasons = list(shoulder_reasons)
    if not posture.get("nose_alignment_available") or not _finite_fields(
        posture,
        (
            "nose_shoulder_offset_x_norm",
            "nose_shoulder_offset_y_norm",
        ),
    ):
        nose_reasons.append(BaselineFailureReason.NON_FINITE_VALUE.value)

    face_reasons = list(shoulder_reasons)
    if (
        not posture.get("face_alignment_available")
        or posture.get("failure_reason") == "FACE_NOT_DETECTED"
    ):
        face_reasons.append(
            BaselineFailureReason.FACE_ALIGNMENT_UNAVAILABLE.value
        )
    if not _finite_fields(
        posture,
        (
            "face_shoulder_offset_x_norm",
            "face_shoulder_offset_y_norm",
        ),
    ):
        face_reasons.append(
            BaselineFailureReason.FACE_ALIGNMENT_UNAVAILABLE.value
        )

    def unique(values: list[str]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(values))

    common = unique(common_reasons)
    head_result = unique([*common_reasons, *head_reasons])
    shoulder_result = unique([*common_reasons, *shoulder_reasons])
    nose_result = unique([*common_reasons, *nose_reasons])
    face_result = unique([*common_reasons, *face_reasons])
    return BaselineCandidateDecision(
        timestamp_ms=frame.timestamp_ms,
        common_available=common_available,
        head_pose_candidate=not head_result,
        shoulder_candidate=not shoulder_result,
        nose_alignment_candidate=not nose_result,
        face_alignment_candidate=not face_result,
        common_reasons=common,
        head_pose_reasons=head_result,
        shoulder_reasons=shoulder_result,
        nose_alignment_reasons=nose_result,
        face_alignment_reasons=face_result,
    )


def collect_baseline_candidates(
    frames: Iterable[NeutralBaselineFrame],
    *,
    collection_start_ms: int,
    collection_end_ms: int | None = None,
    config: NeutralBaselineConfig = NeutralBaselineConfig(),
) -> BaselineCandidateCollection:
    if (
        isinstance(collection_start_ms, bool)
        or not isinstance(collection_start_ms, int)
        or collection_start_ms < 0
    ):
        raise ValueError("collection_start_ms must be a non-negative integer")
    end = (
        collection_start_ms + config.collection_duration_ms
        if collection_end_ms is None
        else collection_end_ms
    )
    if isinstance(end, bool) or not isinstance(end, int) or end < collection_start_ms:
        raise ValueError("collection_end_ms must be >= collection_start_ms")

    selected = [
        frame
        for frame in frames
        if isinstance(frame.timestamp_ms, int)
        and not isinstance(frame.timestamp_ms, bool)
        and collection_start_ms <= frame.timestamp_ms <= end
    ]
    decisions: list[BaselineCandidateDecision] = []
    previous_timestamp: int | None = None
    for frame in selected:
        decision = evaluate_baseline_candidate(frame, config)
        if (
            previous_timestamp is not None
            and frame.timestamp_ms <= previous_timestamp
        ):
            reason = BaselineFailureReason.INVALID_TIMESTAMP.value
            decision = replace(
                decision,
                common_available=False,
                head_pose_candidate=False,
                shoulder_candidate=False,
                nose_alignment_candidate=False,
                face_alignment_candidate=False,
                common_reasons=tuple(
                    dict.fromkeys((*decision.common_reasons, reason))
                ),
                head_pose_reasons=tuple(
                    dict.fromkeys((*decision.head_pose_reasons, reason))
                ),
                shoulder_reasons=tuple(
                    dict.fromkeys((*decision.shoulder_reasons, reason))
                ),
                nose_alignment_reasons=tuple(
                    dict.fromkeys((*decision.nose_alignment_reasons, reason))
                ),
                face_alignment_reasons=tuple(
                    dict.fromkeys((*decision.face_alignment_reasons, reason))
                ),
            )
        decisions.append(decision)
        previous_timestamp = frame.timestamp_ms

    head = tuple(
        frame
        for frame, decision in zip(selected, decisions)
        if decision.head_pose_candidate
    )
    shoulder = tuple(
        frame
        for frame, decision in zip(selected, decisions)
        if decision.shoulder_candidate
    )
    nose = tuple(
        frame
        for frame, decision in zip(selected, decisions)
        if decision.nose_alignment_candidate
    )
    face = tuple(
        frame
        for frame, decision in zip(selected, decisions)
        if decision.face_alignment_candidate
    )
    reasons = Counter(
        reason
        for decision in decisions
        for reason in set(
            (
                *decision.common_reasons,
                *decision.head_pose_reasons,
                *decision.shoulder_reasons,
                *decision.nose_alignment_reasons,
                *decision.face_alignment_reasons,
            )
        )
    )
    return BaselineCandidateCollection(
        collection_start_ms=collection_start_ms,
        collection_end_ms=end,
        total_frame_count=len(selected),
        common_frame_count=sum(
            decision.common_available for decision in decisions
        ),
        head_pose_frames=head,
        shoulder_frames=shoulder,
        nose_alignment_frames=nose,
        face_alignment_frames=face,
        decisions=tuple(decisions),
        rejection_reason_counts=dict(reasons),
    )
