"""Subtract a session baseline while preserving raw and baseline values."""

from __future__ import annotations

import math
from typing import Any

from app.vision.neutral_baseline_models import SessionNeutralBaseline
from app.vision.relative_feature_models import (
    RelativeFeatureFailureReason,
    RelativeFeatureFrame,
    RelativeFeatureGroup,
    RelativeHeadPoseResult,
    RelativeMetricValue,
    RelativePostureResult,
)


def _finite(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _confidence(value: Any) -> float:
    return max(0.0, min(1.0, float(value))) if _finite(value) else 0.0


def _metric(
    *,
    metric_name: str,
    raw_value: Any,
    baseline_value: Any,
    unit: str,
    timestamp_ms: int,
    target_id: str,
    confidence: float,
    raw_available: bool,
    baseline_available: bool,
    baseline_failure_reason: str = (
        RelativeFeatureFailureReason.BASELINE_UNAVAILABLE.value
    ),
    common_failure_reason: str | None = None,
) -> RelativeMetricValue:
    failure = common_failure_reason
    raw_number = float(raw_value) if _finite(raw_value) else None
    baseline_number = (
        float(baseline_value) if _finite(baseline_value) else None
    )
    if failure is None and (not raw_available or raw_value is None):
        failure = RelativeFeatureFailureReason.RAW_VALUE_UNAVAILABLE.value
    if failure is None and raw_value is not None and raw_number is None:
        failure = RelativeFeatureFailureReason.NON_FINITE_RAW_VALUE.value
    if failure is None and (not baseline_available or baseline_value is None):
        failure = baseline_failure_reason
    if (
        failure is None
        and baseline_value is not None
        and baseline_number is None
    ):
        failure = RelativeFeatureFailureReason.NON_FINITE_BASELINE_VALUE.value
    available = (
        failure is None
        and raw_number is not None
        and baseline_number is not None
    )
    return RelativeMetricValue(
        metric_name=metric_name,
        raw_value=raw_number,
        baseline_value=baseline_number,
        relative_value=(
            raw_number - baseline_number if available else None
        ),
        unit=unit,
        available=available,
        confidence=_confidence(confidence),
        timestamp_ms=timestamp_ms,
        target_id=target_id,
        failure_reason=None if available else failure,
    )


def _common_failure(
    timestamp_ms: Any,
    target_id: str | None,
    baseline: SessionNeutralBaseline,
) -> tuple[int, str, str | None]:
    if (
        isinstance(timestamp_ms, bool)
        or not isinstance(timestamp_ms, int)
        or timestamp_ms < 0
    ):
        return (
            -1 if not isinstance(timestamp_ms, int) else timestamp_ms,
            target_id or "",
            RelativeFeatureFailureReason.INVALID_TIMESTAMP.value,
        )
    if target_id != "TARGET_001" or target_id != baseline.target_id:
        return (
            timestamp_ms,
            target_id or "",
            RelativeFeatureFailureReason.TARGET_MISMATCH.value,
        )
    return timestamp_ms, target_id, None


def _first_failure(metrics: dict[str, RelativeMetricValue]) -> str | None:
    return next(
        (
            metric.failure_reason
            for metric in metrics.values()
            if not metric.available
        ),
        None,
    )


def normalize_relative_feature_frame(
    *,
    timestamp_ms: int,
    target_id: str | None,
    raw_head_pose: dict[str, Any],
    raw_posture: dict[str, Any],
    baseline: SessionNeutralBaseline,
) -> RelativeFeatureFrame:
    timestamp, resolved_target, common_failure = _common_failure(
        timestamp_ms,
        target_id,
        baseline,
    )
    head_confidence = min(
        _confidence(raw_head_pose.get("confidence")),
        _confidence(baseline.head_pose.confidence),
    )
    head_metrics: dict[str, RelativeMetricValue] = {}
    for public_name, raw_field, baseline_field in (
        ("yaw", "yaw_deg", "yaw_deg"),
        ("pitch", "pitch_deg", "pitch_deg"),
        ("roll", "roll_deg", "roll_deg"),
    ):
        head_metrics[public_name] = _metric(
            metric_name=f"relative_{public_name}_deg",
            raw_value=raw_head_pose.get(raw_field),
            baseline_value=getattr(baseline.head_pose, baseline_field),
            unit="degree",
            timestamp_ms=timestamp,
            target_id=resolved_target,
            confidence=head_confidence,
            raw_available=bool(raw_head_pose.get("available")),
            baseline_available=baseline.head_pose.available,
            common_failure_reason=common_failure,
        )
    head_available = all(metric.available for metric in head_metrics.values())
    relative_head = RelativeHeadPoseResult(
        available=head_available,
        yaw=head_metrics["yaw"],
        pitch=head_metrics["pitch"],
        roll=head_metrics["roll"],
        confidence=head_confidence,
        failure_reason=None if head_available else _first_failure(head_metrics),
    )

    posture_confidence = min(
        _confidence(raw_posture.get("confidence")),
        _confidence(baseline.posture.confidence),
    )

    def group(
        specifications: tuple[tuple[str, str, str, str], ...],
        *,
        raw_available: bool,
        baseline_available: bool,
        baseline_failure_reason: str = (
            RelativeFeatureFailureReason.BASELINE_UNAVAILABLE.value
        ),
    ) -> RelativeFeatureGroup:
        metrics = {
            key: _metric(
                metric_name=f"relative_{key}",
                raw_value=raw_posture.get(raw_field),
                baseline_value=getattr(baseline.posture, baseline_field),
                unit=unit,
                timestamp_ms=timestamp,
                target_id=resolved_target,
                confidence=posture_confidence,
                raw_available=raw_available,
                baseline_available=baseline_available,
                baseline_failure_reason=baseline_failure_reason,
                common_failure_reason=common_failure,
            )
            for key, raw_field, baseline_field, unit in specifications
        }
        available = all(metric.available for metric in metrics.values())
        return RelativeFeatureGroup(
            available=available,
            metrics=metrics,
            confidence=posture_confidence,
            failure_reason=None if available else _first_failure(metrics),
        )

    shoulder = group(
        (
            ("shoulder_tilt_deg", "shoulder_tilt_deg", "shoulder_tilt_deg", "degree"),
            (
                "shoulder_height_difference_norm",
                "shoulder_height_difference_norm",
                "shoulder_height_difference_norm",
                "normalized_ratio",
            ),
            ("shoulder_center_x", "shoulder_center_x", "shoulder_center_x", "image_normalized"),
            ("shoulder_center_y", "shoulder_center_y", "shoulder_center_y", "image_normalized"),
            ("shoulder_width_norm", "shoulder_width_norm", "shoulder_width_norm", "image_normalized"),
        ),
        raw_available=bool(
            raw_posture.get("available")
            and raw_posture.get("shoulders_available")
        ),
        baseline_available=baseline.posture.available,
    )
    nose = group(
        (
            (
                "nose_shoulder_offset_x_norm",
                "nose_shoulder_offset_x_norm",
                "nose_shoulder_offset_x_norm",
                "shoulder_width_normalized",
            ),
            (
                "nose_shoulder_offset_y_norm",
                "nose_shoulder_offset_y_norm",
                "nose_shoulder_offset_y_norm",
                "shoulder_width_normalized",
            ),
        ),
        raw_available=bool(raw_posture.get("nose_alignment_available")),
        baseline_available=baseline.posture.nose_alignment_available,
    )
    face = group(
        (
            (
                "face_shoulder_offset_x_norm",
                "face_shoulder_offset_x_norm",
                "face_shoulder_offset_x_norm",
                "shoulder_width_normalized",
            ),
            (
                "face_shoulder_offset_y_norm",
                "face_shoulder_offset_y_norm",
                "face_shoulder_offset_y_norm",
                "shoulder_width_normalized",
            ),
        ),
        raw_available=bool(raw_posture.get("face_alignment_available")),
        baseline_available=baseline.posture.face_alignment_available,
        baseline_failure_reason=(
            RelativeFeatureFailureReason
            .FACE_ALIGNMENT_BASELINE_UNAVAILABLE.value
        ),
    )
    posture_available = shoulder.available
    relative_posture = RelativePostureResult(
        available=posture_available,
        shoulder=shoulder,
        nose_alignment=nose,
        face_alignment=face,
        confidence=posture_confidence,
        failure_reason=(
            None if posture_available else shoulder.failure_reason
        ),
    )
    return RelativeFeatureFrame(
        timestamp_ms=timestamp,
        target_id=resolved_target,
        head_pose=relative_head,
        posture=relative_posture,
    )
