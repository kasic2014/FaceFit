"""Robust median/MAD estimation of session-local neutral reference values."""

from __future__ import annotations

import math
import statistics
from typing import Any, Callable

from app.vision.neutral_baseline_models import (
    BaselineCandidateCollection,
    BaselineCollectionStatus,
    BaselineFailureReason,
    BaselineMetricDiagnostic,
    BaselineQualityWarning,
    HeadPoseBaseline,
    NeutralBaselineConfig,
    NeutralBaselineFrame,
    PostureBaseline,
    SessionNeutralBaseline,
)


def _robust_baseline_value(
    values: list[Any],
    *,
    metric_name: str,
    minimum_frames: int,
    config: NeutralBaselineConfig,
) -> tuple[float | None, BaselineMetricDiagnostic]:
    finite = []
    for value in values:
        if isinstance(value, bool) or value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            finite.append(number)
    initial_median = statistics.median(finite) if finite else None
    mad = (
        statistics.median(abs(value - initial_median) for value in finite)
        if finite
        else None
    )
    if len(finite) < config.minimum_outlier_filter_samples:
        used = list(finite)
    elif mad is None:
        used = []
    elif mad == 0.0:
        # Deterministic zero-MAD handling: retain the modal median plateau.
        used = [value for value in finite if value == initial_median]
    else:
        limit = config.mad_multiplier * mad
        used = [
            value for value in finite if abs(value - initial_median) <= limit
        ]
    value = statistics.median(used) if len(used) >= minimum_frames else None
    diagnostic = BaselineMetricDiagnostic(
        metric_name=metric_name,
        candidate_count=len(values),
        finite_count=len(finite),
        used_count=len(used),
        initial_median=initial_median,
        mad=mad,
        outlier_count=len(finite) - len(used),
        aggregation_method=config.aggregation_method,
        outlier_method=config.outlier_method,
    )
    return value, diagnostic


def _payload_values(
    frames: tuple[NeutralBaselineFrame, ...],
    payload_getter: Callable[[NeutralBaselineFrame], dict[str, Any]],
    field: str,
) -> list[Any]:
    return [payload_getter(frame).get(field) for frame in frames]


def _confidence(
    frames: tuple[NeutralBaselineFrame, ...],
    payload_getter: Callable[[NeutralBaselineFrame], dict[str, Any]],
) -> float:
    values = [
        float(payload_getter(frame)["confidence"])
        for frame in frames
        if payload_getter(frame).get("confidence") is not None
        and math.isfinite(float(payload_getter(frame)["confidence"]))
    ]
    return max(0.0, min(1.0, statistics.median(values))) if values else 0.0


def _group_failure(
    collection: BaselineCandidateCollection,
    *,
    group: str,
) -> str:
    counts = collection.rejection_reason_counts
    if counts.get(BaselineFailureReason.MULTIPLE_PERSON_DETECTED.value, 0):
        return BaselineFailureReason.MULTIPLE_PERSON_DETECTED.value
    if counts.get(BaselineFailureReason.TARGET_NOT_AVAILABLE.value, 0):
        return BaselineFailureReason.TARGET_NOT_AVAILABLE.value
    if group == "head" and counts.get(
        BaselineFailureReason.UNSTABLE_HEAD_MOTION.value,
        0,
    ):
        return BaselineFailureReason.UNSTABLE_HEAD_MOTION.value
    if group == "posture" and counts.get(
        BaselineFailureReason.UNSTABLE_SHOULDER_MOTION.value,
        0,
    ):
        return BaselineFailureReason.UNSTABLE_SHOULDER_MOTION.value
    if counts.get(BaselineFailureReason.LOW_CONFIDENCE.value, 0):
        return BaselineFailureReason.LOW_CONFIDENCE.value
    return BaselineFailureReason.INSUFFICIENT_FRAMES.value


def _estimate_head_pose(
    collection: BaselineCandidateCollection,
    config: NeutralBaselineConfig,
) -> HeadPoseBaseline:
    frames = collection.head_pose_frames
    diagnostics: dict[str, BaselineMetricDiagnostic] = {}
    values: dict[str, float | None] = {}
    for field in ("yaw_deg", "pitch_deg", "roll_deg"):
        values[field], diagnostics[field] = _robust_baseline_value(
            _payload_values(frames, lambda frame: frame.head_pose, field),
            metric_name=field,
            minimum_frames=config.minimum_head_pose_frames,
            config=config,
        )
    available = all(values[field] is not None for field in values)
    used = min(
        (diagnostic.used_count for diagnostic in diagnostics.values()),
        default=0,
    )
    return HeadPoseBaseline(
        available=available,
        yaw_deg=values["yaw_deg"] if available else None,
        pitch_deg=values["pitch_deg"] if available else None,
        roll_deg=values["roll_deg"] if available else None,
        candidate_frame_count=len(frames),
        used_frame_count=used,
        confidence=_confidence(frames, lambda frame: frame.head_pose),
        failure_reason=None if available else _group_failure(
            collection,
            group="head",
        ),
        metric_diagnostics=diagnostics,
    )


def _estimate_posture(
    collection: BaselineCandidateCollection,
    config: NeutralBaselineConfig,
) -> PostureBaseline:
    getter = lambda frame: frame.posture_raw
    core_fields = (
        "shoulder_tilt_deg",
        "shoulder_height_difference_norm",
        "shoulder_center_x",
        "shoulder_center_y",
        "shoulder_width_norm",
    )
    nose_fields = (
        "nose_shoulder_offset_x_norm",
        "nose_shoulder_offset_y_norm",
    )
    face_fields = (
        "face_shoulder_offset_x_norm",
        "face_shoulder_offset_y_norm",
    )
    diagnostics: dict[str, BaselineMetricDiagnostic] = {}
    values: dict[str, float | None] = {}
    for field in core_fields:
        values[field], diagnostics[field] = _robust_baseline_value(
            _payload_values(collection.shoulder_frames, getter, field),
            metric_name=field,
            minimum_frames=config.minimum_posture_frames,
            config=config,
        )
    for field in nose_fields:
        values[field], diagnostics[field] = _robust_baseline_value(
            _payload_values(collection.nose_alignment_frames, getter, field),
            metric_name=field,
            minimum_frames=config.minimum_nose_alignment_frames,
            config=config,
        )
    for field in face_fields:
        values[field], diagnostics[field] = _robust_baseline_value(
            _payload_values(collection.face_alignment_frames, getter, field),
            metric_name=field,
            minimum_frames=config.minimum_face_alignment_frames,
            config=config,
        )
    available = all(values[field] is not None for field in core_fields)
    nose_available = all(values[field] is not None for field in nose_fields)
    face_available = all(values[field] is not None for field in face_fields)
    core_used = min(
        (diagnostics[field].used_count for field in core_fields),
        default=0,
    )
    nose_used = min(
        (diagnostics[field].used_count for field in nose_fields),
        default=0,
    )
    face_used = min(
        (diagnostics[field].used_count for field in face_fields),
        default=0,
    )
    return PostureBaseline(
        available=available,
        shoulder_tilt_deg=values["shoulder_tilt_deg"] if available else None,
        shoulder_height_difference_norm=(
            values["shoulder_height_difference_norm"] if available else None
        ),
        shoulder_center_x=values["shoulder_center_x"] if available else None,
        shoulder_center_y=values["shoulder_center_y"] if available else None,
        shoulder_width_norm=(
            values["shoulder_width_norm"] if available else None
        ),
        nose_alignment_available=nose_available,
        nose_shoulder_offset_x_norm=(
            values["nose_shoulder_offset_x_norm"] if nose_available else None
        ),
        nose_shoulder_offset_y_norm=(
            values["nose_shoulder_offset_y_norm"] if nose_available else None
        ),
        face_alignment_available=face_available,
        face_shoulder_offset_x_norm=(
            values["face_shoulder_offset_x_norm"] if face_available else None
        ),
        face_shoulder_offset_y_norm=(
            values["face_shoulder_offset_y_norm"] if face_available else None
        ),
        candidate_frame_count=len(collection.shoulder_frames),
        used_frame_count=core_used,
        nose_candidate_frame_count=len(collection.nose_alignment_frames),
        nose_used_frame_count=nose_used,
        face_candidate_frame_count=len(collection.face_alignment_frames),
        face_used_frame_count=face_used,
        confidence=_confidence(collection.shoulder_frames, getter),
        failure_reason=None if available else _group_failure(
            collection,
            group="posture",
        ),
        face_alignment_failure_reason=(
            None
            if face_available
            else BaselineFailureReason.FACE_ALIGNMENT_UNAVAILABLE.value
        ),
        metric_diagnostics=diagnostics,
    )


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _median_stability(
    frames: tuple[NeutralBaselineFrame, ...],
    getter: Callable[[NeutralBaselineFrame], float | None],
    limit: float,
) -> float:
    values = [
        abs(float(value))
        for frame in frames
        if (value := getter(frame)) is not None
        and math.isfinite(float(value))
    ]
    if not values:
        return 1.0
    return _clamp(1.0 - statistics.median(values) / limit)


def _quality_components(
    collection: BaselineCandidateCollection,
    head: HeadPoseBaseline,
    posture: PostureBaseline,
    config: NeutralBaselineConfig,
) -> dict[str, float]:
    total = collection.total_frame_count
    denominator = max(1, total)
    head_retention = (
        head.used_frame_count / head.candidate_frame_count
        if head.candidate_frame_count
        else 0.0
    )
    posture_retention = (
        posture.used_frame_count / posture.candidate_frame_count
        if posture.candidate_frame_count
        else 0.0
    )
    return {
        "target_continuity": _clamp(collection.common_frame_count / denominator),
        "head_candidate_coverage": _clamp(
            head.candidate_frame_count / denominator
        ),
        "posture_candidate_coverage": _clamp(
            posture.candidate_frame_count / denominator
        ),
        "head_used_retention": _clamp(head_retention),
        "posture_used_retention": _clamp(posture_retention),
        "head_confidence": _clamp(head.confidence),
        "posture_confidence": _clamp(posture.confidence),
        "head_motion_stability": _median_stability(
            collection.head_pose_frames,
            lambda frame: frame.head_angular_velocity_deg_per_sec,
            config.maximum_head_angular_velocity_deg_per_sec,
        ),
        "shoulder_center_stability": _median_stability(
            collection.shoulder_frames,
            lambda frame: frame.posture_temporal.get(
                "shoulder_center_velocity_norm_per_sec"
            ),
            config.maximum_shoulder_center_velocity_norm_per_sec,
        ),
        "shoulder_tilt_stability": _median_stability(
            collection.shoulder_frames,
            lambda frame: frame.posture_temporal.get(
                "shoulder_tilt_velocity_deg_per_sec"
            ),
            config.maximum_shoulder_tilt_velocity_deg_per_sec,
        ),
    }


def estimate_session_neutral_baseline(
    collection: BaselineCandidateCollection,
    config: NeutralBaselineConfig = NeutralBaselineConfig(),
) -> SessionNeutralBaseline:
    head = _estimate_head_pose(collection, config)
    posture = _estimate_posture(collection, config)
    enough_common = (
        collection.common_frame_count >= config.minimum_candidate_frames
    )
    available = enough_common and head.available and posture.available
    components = _quality_components(collection, head, posture, config)
    quality = (
        statistics.fmean(components.values()) if components else 0.0
    )
    warnings: list[str] = [
        BaselineQualityWarning.COLLECTION_IS_NOT_NEUTRAL_GROUND_TRUTH.value
    ]
    if not head.available:
        warnings.append(BaselineQualityWarning.HEAD_POSE_PARTIAL.value)
    if not posture.available or not posture.nose_alignment_available:
        warnings.append(BaselineQualityWarning.POSTURE_PARTIAL.value)
    if not posture.face_alignment_available:
        warnings.append(
            BaselineQualityWarning.FACE_ALIGNMENT_UNAVAILABLE.value
        )
    if any(
        diagnostic.outlier_count
        for diagnostic in (
            *head.metric_diagnostics.values(),
            *posture.metric_diagnostics.values(),
        )
    ):
        warnings.append(BaselineQualityWarning.OUTLIERS_REMOVED.value)
    failure = None
    if not available:
        if not enough_common:
            failure = _group_failure(collection, group="posture")
        elif not head.available:
            failure = head.failure_reason
        else:
            failure = posture.failure_reason
    return SessionNeutralBaseline(
        available=available,
        target_id="TARGET_001",
        collection_start_ms=collection.collection_start_ms,
        collection_end_ms=collection.collection_end_ms,
        head_pose=head,
        posture=posture,
        quality_score=_clamp(quality),
        quality_components=components,
        status=(
            BaselineCollectionStatus.COMPLETED.value
            if available
            else BaselineCollectionStatus.FAILED.value
        ),
        warnings=tuple(dict.fromkeys(warnings)),
        failure_reason=failure,
        aggregation_method=config.aggregation_method,
        outlier_method=config.outlier_method,
    )
