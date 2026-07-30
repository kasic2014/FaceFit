"""File-independent interval aggregation of frame-level relative features."""

from __future__ import annotations

import math
import statistics
from collections import Counter
from typing import Any, Iterable

from app.vision.interval_event_aggregator import aggregate_interval_events
from app.vision.interval_models import (
    AnalysisInterval,
    HeadPoseIntervalSummary,
    IntervalAggregationConfig,
    IntervalAggregationFailureReason,
    IntervalAggregationResult,
    IntervalAvailabilitySummary,
    IntervalDataQuality,
    PostureIntervalSummary,
)
from app.vision.missing_duration_calculator import (
    calculate_longest_missing_duration_ms,
)
from app.vision.numeric_metric_aggregator import aggregate_numeric_metric


HEAD_METRICS = {
    "relative_yaw_deg": "yaw",
    "relative_pitch_deg": "pitch",
    "relative_roll_deg": "roll",
}
SHOULDER_METRICS = (
    "shoulder_tilt_deg",
    "shoulder_height_difference_norm",
    "shoulder_center_x",
    "shoulder_center_y",
    "shoulder_width_norm",
)
NOSE_METRICS = (
    "nose_shoulder_offset_x_norm",
    "nose_shoulder_offset_y_norm",
)
FACE_METRICS = (
    "face_shoulder_offset_x_norm",
    "face_shoulder_offset_y_norm",
)
POSTURE_TEMPORAL_METRICS = (
    "shoulder_center_displacement_norm",
    "shoulder_center_velocity_norm_per_sec",
    "shoulder_tilt_delta_deg",
    "shoulder_tilt_velocity_deg_per_sec",
    "shoulder_width_delta_norm",
    "shoulder_width_change_rate_per_sec",
)
HEAD_TEMPORAL_METRICS = (
    "yaw_velocity_deg_per_sec",
    "pitch_velocity_deg_per_sec",
    "roll_velocity_deg_per_sec",
)


class IntervalAggregationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict"):
        result = value.to_dict()
        if isinstance(result, dict):
            return result
    raise TypeError("Relative feature frames must be dicts or to_dict models")


def _finite(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def validate_analysis_intervals(
    intervals: Iterable[AnalysisInterval],
    config: IntervalAggregationConfig = IntervalAggregationConfig(),
) -> tuple[AnalysisInterval, ...]:
    values = tuple(intervals)
    seen: set[str] = set()
    for interval in values:
        if interval.interval_id in seen:
            raise IntervalAggregationError(
                IntervalAggregationFailureReason.DUPLICATE_INTERVAL_ID.value,
                f"Duplicate interval_id: {interval.interval_id}",
            )
        seen.add(interval.interval_id)
    if config.reject_overlapping_intervals:
        ordered = sorted(
            values,
            key=lambda item: (
                item.start_timestamp_ms,
                item.end_timestamp_ms,
                item.interval_id,
            ),
        )
        for previous, current in zip(ordered, ordered[1:]):
            if current.start_timestamp_ms < previous.end_timestamp_ms:
                raise IntervalAggregationError(
                    IntervalAggregationFailureReason.OVERLAPPING_INTERVAL.value,
                    (
                        f"Intervals overlap: {previous.interval_id} and "
                        f"{current.interval_id}"
                    ),
                )
    return values


def _group_payload(
    frame: dict[str, Any],
    group: str,
) -> dict[str, Any]:
    if group == "head":
        return frame.get("head_pose") or {}
    return (frame.get("posture") or {}).get(group) or {}


def _metric_payload(
    frame: dict[str, Any],
    group: str,
    metric: str,
) -> dict[str, Any]:
    payload = _group_payload(frame, group)
    if group == "head":
        return payload.get(metric) or {}
    return (payload.get("metrics") or {}).get(metric) or {}


def _group_state(
    frame: dict[str, Any],
    *,
    group: str,
    required_metrics: Iterable[str],
    target_id: str,
    no_values_reason: str,
) -> tuple[bool, str | None]:
    if frame.get("target_id") != target_id:
        return (
            False,
            IntervalAggregationFailureReason.TARGET_ID_MISMATCH.value,
        )
    payload = _group_payload(frame, group)
    if not payload.get("available"):
        return False, payload.get("failure_reason") or no_values_reason
    for metric in required_metrics:
        item = _metric_payload(frame, group, metric)
        if not item.get("available"):
            return False, item.get("failure_reason") or no_values_reason
        if not _finite(item.get("relative_value")):
            return (
                False,
                IntervalAggregationFailureReason.NON_FINITE_VALUE.value,
            )
    return True, None


def _availability_summary(
    interval: AnalysisInterval,
    frames: list[dict[str, Any]],
    *,
    group: str,
    required_metrics: Iterable[str],
    target_id: str,
    no_values_reason: str,
    config: IntervalAggregationConfig,
) -> tuple[IntervalAvailabilitySummary, list[bool]]:
    states: list[bool] = []
    reasons: Counter[str] = Counter()
    for frame in frames:
        available, reason = _group_state(
            frame,
            group=group,
            required_metrics=required_metrics,
            target_id=target_id,
            no_values_reason=no_values_reason,
        )
        states.append(available)
        if not available and reason:
            reasons[reason] += 1
    total = len(frames)
    valid = sum(states)
    ratio = valid / total if total else 0.0
    if not total:
        failure = (
            IntervalAggregationFailureReason.NO_FRAMES_IN_INTERVAL.value
        )
    elif not valid:
        failure = no_values_reason
    elif ratio < config.minimum_availability_ratio:
        failure = (
            IntervalAggregationFailureReason
            .INSUFFICIENT_VALID_SAMPLES.value
        )
    else:
        failure = None
    timestamps = [
        int(frame["timestamp_ms"])
        for frame in frames
        if isinstance(frame.get("timestamp_ms"), int)
        and not isinstance(frame.get("timestamp_ms"), bool)
    ]
    return (
        IntervalAvailabilitySummary(
            available=failure is None,
            total_frame_count=total,
            valid_frame_count=valid,
            invalid_frame_count=total - valid,
            availability_ratio=ratio,
            longest_missing_duration_ms=(
                calculate_longest_missing_duration_ms(
                    interval,
                    timestamps,
                    states,
                )
            ),
            failure_reason_counts=dict(sorted(reasons.items())),
            failure_reason=failure,
        ),
        states,
    )


def _relative_values(
    frames: list[dict[str, Any]],
    *,
    group: str,
    metric: str,
    target_id: str,
) -> list[Any]:
    result: list[Any] = []
    for frame in frames:
        if frame.get("target_id") != target_id:
            continue
        item = _metric_payload(frame, group, metric)
        result.append(
            item.get("relative_value") if item.get("available") else None
        )
    return result


def _temporal_index(
    temporal_frames: Iterable[Any],
) -> dict[tuple[int, str], dict[str, Any]]:
    result: dict[tuple[int, str], dict[str, Any]] = {}
    for value in temporal_frames:
        row = _payload(value)
        timestamp = row.get("timestamp_ms")
        target_id = row.get("target_id")
        if (
            isinstance(timestamp, int)
            and not isinstance(timestamp, bool)
            and isinstance(target_id, str)
        ):
            result.setdefault((timestamp, target_id), row)
    return result


def _temporal_summary(
    frames: list[dict[str, Any]],
    temporal: dict[tuple[int, str], dict[str, Any]],
    *,
    section: str,
    metric: str,
    target_id: str,
    config: IntervalAggregationConfig,
):
    values: list[Any] = []
    source_present = False
    for frame in frames:
        if frame.get("target_id") != target_id:
            continue
        row = temporal.get((frame.get("timestamp_ms"), target_id), {})
        payload = row.get(section) or {}
        if metric in payload:
            source_present = True
            values.append(payload.get(metric))
        elif row:
            values.append(None)
    return (
        aggregate_numeric_metric(values, config)
        if source_present
        else None
    )


def _duplicate_count(values: list[Any]) -> int:
    usable = [
        value
        for value in values
        if value is not None and not isinstance(value, bool)
    ]
    return len(usable) - len(set(usable))


def aggregate_interval_features(
    interval: AnalysisInterval,
    relative_frames: Iterable[Any],
    *,
    temporal_frames: Iterable[Any] = (),
    head_pose_events: Iterable[dict[str, Any]] = (),
    posture_events: Iterable[dict[str, Any]] = (),
    config: IntervalAggregationConfig = IntervalAggregationConfig(),
    target_id: str = "TARGET_001",
) -> IntervalAggregationResult:
    frames = [
        frame
        for value in relative_frames
        if (
            (frame := _payload(value))
            and isinstance(frame.get("timestamp_ms"), int)
            and not isinstance(frame.get("timestamp_ms"), bool)
            and interval.contains(frame["timestamp_ms"])
        )
    ]
    timestamps = [int(frame["timestamp_ms"]) for frame in frames]
    timestamp_monotonic = all(
        current > previous
        for previous, current in zip(timestamps, timestamps[1:])
    )
    duplicate_timestamps = _duplicate_count(timestamps)
    frame_indices = [
        frame.get("frame_index", frame.get("sample_index"))
        for frame in frames
    ]
    duplicate_frames = _duplicate_count(frame_indices)
    frame_index_available = bool(frames) and all(
        value is not None for value in frame_indices
    )
    matching_target_count = sum(
        frame.get("target_id") == target_id for frame in frames
    )
    target_continuity = (
        matching_target_count / len(frames) if frames else 0.0
    )

    head_availability, _ = _availability_summary(
        interval,
        frames,
        group="head",
        required_metrics=HEAD_METRICS.values(),
        target_id=target_id,
        no_values_reason=(
            IntervalAggregationFailureReason
            .NO_VALID_HEAD_POSE_VALUES.value
        ),
        config=config,
    )
    shoulder_availability, _ = _availability_summary(
        interval,
        frames,
        group="shoulder",
        required_metrics=SHOULDER_METRICS,
        target_id=target_id,
        no_values_reason=(
            IntervalAggregationFailureReason.NO_VALID_POSTURE_VALUES.value
        ),
        config=config,
    )
    nose_availability, _ = _availability_summary(
        interval,
        frames,
        group="nose_alignment",
        required_metrics=NOSE_METRICS,
        target_id=target_id,
        no_values_reason=(
            IntervalAggregationFailureReason
            .NO_VALID_NOSE_ALIGNMENT_VALUES.value
        ),
        config=config,
    )
    face_availability, _ = _availability_summary(
        interval,
        frames,
        group="face_alignment",
        required_metrics=FACE_METRICS,
        target_id=target_id,
        no_values_reason=(
            IntervalAggregationFailureReason
            .NO_VALID_FACE_ALIGNMENT_VALUES.value
        ),
        config=config,
    )

    temporal = _temporal_index(temporal_frames)
    head_summaries = {
        public: aggregate_numeric_metric(
            _relative_values(
                frames,
                group="head",
                metric=source,
                target_id=target_id,
            ),
            config,
        )
        for public, source in HEAD_METRICS.items()
    }
    head_velocity = {
        metric: _temporal_summary(
            frames,
            temporal,
            section="head_pose_temporal",
            metric=metric,
            target_id=target_id,
            config=config,
        )
        for metric in HEAD_TEMPORAL_METRICS
    }
    head = HeadPoseIntervalSummary(
        availability=head_availability,
        relative_yaw_deg=head_summaries["relative_yaw_deg"],
        relative_pitch_deg=head_summaries["relative_pitch_deg"],
        relative_roll_deg=head_summaries["relative_roll_deg"],
        yaw_velocity_deg_per_sec=head_velocity[
            "yaw_velocity_deg_per_sec"
        ],
        pitch_velocity_deg_per_sec=head_velocity[
            "pitch_velocity_deg_per_sec"
        ],
        roll_velocity_deg_per_sec=head_velocity[
            "roll_velocity_deg_per_sec"
        ],
    )

    shoulder_summaries = {
        metric: aggregate_numeric_metric(
            _relative_values(
                frames,
                group="shoulder",
                metric=metric,
                target_id=target_id,
            ),
            config,
        )
        for metric in SHOULDER_METRICS
    }
    nose_summaries = {
        metric: aggregate_numeric_metric(
            _relative_values(
                frames,
                group="nose_alignment",
                metric=metric,
                target_id=target_id,
            ),
            config,
        )
        for metric in NOSE_METRICS
    }
    face_summaries = {
        metric: aggregate_numeric_metric(
            _relative_values(
                frames,
                group="face_alignment",
                metric=metric,
                target_id=target_id,
            ),
            config,
        )
        for metric in FACE_METRICS
    }
    posture_temporal = {
        metric: _temporal_summary(
            frames,
            temporal,
            section="posture_temporal",
            metric=metric,
            target_id=target_id,
            config=config,
        )
        for metric in POSTURE_TEMPORAL_METRICS
    }
    posture = PostureIntervalSummary(
        shoulder_availability=shoulder_availability,
        nose_alignment_availability=nose_availability,
        face_alignment_availability=face_availability,
        relative_shoulder_tilt_deg=shoulder_summaries[
            "shoulder_tilt_deg"
        ],
        relative_shoulder_height_difference_norm=shoulder_summaries[
            "shoulder_height_difference_norm"
        ],
        relative_shoulder_center_x=shoulder_summaries[
            "shoulder_center_x"
        ],
        relative_shoulder_center_y=shoulder_summaries[
            "shoulder_center_y"
        ],
        relative_shoulder_width_norm=shoulder_summaries[
            "shoulder_width_norm"
        ],
        relative_nose_shoulder_offset_x_norm=nose_summaries[
            "nose_shoulder_offset_x_norm"
        ],
        relative_nose_shoulder_offset_y_norm=nose_summaries[
            "nose_shoulder_offset_y_norm"
        ],
        relative_face_shoulder_offset_x_norm=face_summaries[
            "face_shoulder_offset_x_norm"
        ],
        relative_face_shoulder_offset_y_norm=face_summaries[
            "face_shoulder_offset_y_norm"
        ],
        shoulder_center_displacement_norm=posture_temporal[
            "shoulder_center_displacement_norm"
        ],
        shoulder_center_velocity_norm_per_sec=posture_temporal[
            "shoulder_center_velocity_norm_per_sec"
        ],
        shoulder_tilt_delta_deg=posture_temporal[
            "shoulder_tilt_delta_deg"
        ],
        shoulder_tilt_velocity_deg_per_sec=posture_temporal[
            "shoulder_tilt_velocity_deg_per_sec"
        ],
        shoulder_width_delta_norm=posture_temporal[
            "shoulder_width_delta_norm"
        ],
        shoulder_width_change_rate_per_sec=posture_temporal[
            "shoulder_width_change_rate_per_sec"
        ],
    )
    events = aggregate_interval_events(
        interval,
        head_pose_events=head_pose_events,
        posture_events=posture_events,
        target_id=target_id,
    )

    warnings: list[str] = []
    if frames and not frame_index_available:
        warnings.append("FRAME_INDEX_UNAVAILABLE")
    group_summaries = (
        ("HEAD_POSE_PARTIAL", head_availability),
        ("POSTURE_PARTIAL", shoulder_availability),
        ("NOSE_ALIGNMENT_PARTIAL", nose_availability),
        ("FACE_ALIGNMENT_PARTIAL", face_availability),
    )
    warnings.extend(
        name
        for name, summary in group_summaries
        if summary.invalid_frame_count > 0
    )
    if events.ignored_target_mismatch_count:
        warnings.append("EVENT_TARGET_MISMATCH_IGNORED")

    ratios = (
        head_availability.availability_ratio,
        shoulder_availability.availability_ratio,
        nose_availability.availability_ratio,
        face_availability.availability_ratio,
    )
    structural_failure = None
    if not frames:
        structural_failure = (
            IntervalAggregationFailureReason.NO_FRAMES_IN_INTERVAL.value
        )
    elif matching_target_count != len(frames):
        structural_failure = (
            IntervalAggregationFailureReason.TARGET_ID_MISMATCH.value
        )
    elif duplicate_timestamps:
        structural_failure = (
            IntervalAggregationFailureReason.DUPLICATE_TIMESTAMP.value
        )
    elif not timestamp_monotonic:
        structural_failure = (
            IntervalAggregationFailureReason
            .NON_MONOTONIC_TIMESTAMP.value
        )
    elif duplicate_frames:
        structural_failure = (
            IntervalAggregationFailureReason.DUPLICATE_FRAME_INDEX.value
        )
    elif config.minimum_availability_ratio > 0.0 and any(
        ratio < config.minimum_availability_ratio for ratio in ratios
    ):
        structural_failure = (
            IntervalAggregationFailureReason
            .INSUFFICIENT_VALID_SAMPLES.value
        )
    elif not any(
        summary.valid_frame_count
        for summary in (
            head_availability,
            shoulder_availability,
            nose_availability,
            face_availability,
        )
    ):
        structural_failure = (
            IntervalAggregationFailureReason
            .NO_VALID_HEAD_POSE_VALUES.value
        )

    timestamp_integrity = 1.0 if timestamp_monotonic else 0.0
    duplicate_integrity = (
        1.0 if duplicate_timestamps == 0 and duplicate_frames == 0 else 0.0
    )
    quality_components = (
        *ratios,
        target_continuity,
        timestamp_integrity,
        duplicate_integrity,
    )
    quality_score = (
        max(0.0, min(1.0, statistics.fmean(quality_components)))
        if frames and quality_components
        else 0.0
    )
    quality = IntervalDataQuality(
        available=structural_failure is None,
        total_frame_count=len(frames),
        head_pose_availability_ratio=ratios[0],
        posture_availability_ratio=ratios[1],
        nose_alignment_availability_ratio=ratios[2],
        face_alignment_availability_ratio=ratios[3],
        target_continuity_ratio=target_continuity,
        timestamp_monotonic=timestamp_monotonic,
        duplicate_frame_count=duplicate_frames,
        duplicate_timestamp_count=duplicate_timestamps,
        quality_score=quality_score,
        warnings=tuple(dict.fromkeys(warnings)),
        failure_reason=structural_failure,
    )
    return IntervalAggregationResult(
        interval_id=interval.interval_id,
        interval_type=interval.interval_type,
        start_timestamp_ms=interval.start_timestamp_ms,
        end_timestamp_ms=interval.end_timestamp_ms,
        duration_ms=interval.duration_ms,
        target_id=target_id,
        data_quality=quality,
        head_pose=head,
        posture=posture,
        events=events,
        warnings=quality.warnings,
        failure_reason=structural_failure,
    )


def aggregate_intervals(
    intervals: Iterable[AnalysisInterval],
    relative_frames: Iterable[Any],
    *,
    temporal_frames: Iterable[Any] = (),
    head_pose_events: Iterable[dict[str, Any]] = (),
    posture_events: Iterable[dict[str, Any]] = (),
    config: IntervalAggregationConfig = IntervalAggregationConfig(),
    target_id: str = "TARGET_001",
) -> tuple[IntervalAggregationResult, ...]:
    checked = validate_analysis_intervals(intervals, config)
    frames = tuple(relative_frames)
    temporal = tuple(temporal_frames)
    head_events = tuple(head_pose_events)
    posture_event_values = tuple(posture_events)
    return tuple(
        aggregate_interval_features(
            interval,
            frames,
            temporal_frames=temporal,
            head_pose_events=head_events,
            posture_events=posture_event_values,
            config=config,
            target_id=target_id,
        )
        for interval in checked
    )
