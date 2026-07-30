"""Typed models for non-evaluative answer-interval feature aggregation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class IntervalType(str, Enum):
    ANSWER = "ANSWER"
    QUESTION = "QUESTION"
    BASELINE = "BASELINE"
    PREPARATION = "PREPARATION"
    OTHER = "OTHER"


class IntervalAggregationFailureReason(str, Enum):
    INVALID_INTERVAL = "INVALID_INTERVAL"
    DUPLICATE_INTERVAL_ID = "DUPLICATE_INTERVAL_ID"
    OVERLAPPING_INTERVAL = "OVERLAPPING_INTERVAL"
    NO_FRAMES_IN_INTERVAL = "NO_FRAMES_IN_INTERVAL"
    TARGET_ID_MISMATCH = "TARGET_ID_MISMATCH"
    NO_VALID_HEAD_POSE_VALUES = "NO_VALID_HEAD_POSE_VALUES"
    NO_VALID_POSTURE_VALUES = "NO_VALID_POSTURE_VALUES"
    NO_VALID_NOSE_ALIGNMENT_VALUES = "NO_VALID_NOSE_ALIGNMENT_VALUES"
    NO_VALID_FACE_ALIGNMENT_VALUES = "NO_VALID_FACE_ALIGNMENT_VALUES"
    NON_MONOTONIC_TIMESTAMP = "NON_MONOTONIC_TIMESTAMP"
    DUPLICATE_TIMESTAMP = "DUPLICATE_TIMESTAMP"
    DUPLICATE_FRAME_INDEX = "DUPLICATE_FRAME_INDEX"
    NON_FINITE_VALUE = "NON_FINITE_VALUE"
    INSUFFICIENT_VALID_SAMPLES = "INSUFFICIENT_VALID_SAMPLES"
    NO_VALID_VALUES = "NO_VALID_VALUES"


@dataclass(frozen=True)
class IntervalAggregationConfig:
    """Data aggregation settings, never posture evaluation settings."""

    interval_end_exclusive: bool = True
    minimum_valid_sample_count: int = 1
    minimum_availability_ratio: float = 0.0
    calculate_percentiles: bool = True
    percentile_values: tuple[float, ...] = (5.0, 25.0, 75.0, 95.0)
    include_absolute_statistics: bool = True
    reject_overlapping_intervals: bool = True

    def __post_init__(self) -> None:
        if not self.interval_end_exclusive:
            raise ValueError("Stage 10 requires an exclusive interval end")
        if (
            isinstance(self.minimum_valid_sample_count, bool)
            or self.minimum_valid_sample_count <= 0
        ):
            raise ValueError("minimum_valid_sample_count must be positive")
        if not 0.0 <= self.minimum_availability_ratio <= 1.0:
            raise ValueError("minimum_availability_ratio must be within 0..1")
        if tuple(self.percentile_values) != (5.0, 25.0, 75.0, 95.0):
            raise ValueError("Stage 10 exposes the fixed p05/p25/p75/p95 set")


@dataclass(frozen=True)
class AnalysisInterval:
    interval_id: str
    start_timestamp_ms: int
    end_timestamp_ms: int
    interval_type: str = IntervalType.ANSWER.value

    def __post_init__(self) -> None:
        if not isinstance(self.interval_id, str) or not self.interval_id.strip():
            raise ValueError(
                IntervalAggregationFailureReason.INVALID_INTERVAL.value
            )
        timestamps = (self.start_timestamp_ms, self.end_timestamp_ms)
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in timestamps
        ):
            raise ValueError(
                IntervalAggregationFailureReason.INVALID_INTERVAL.value
            )
        if self.start_timestamp_ms < 0:
            raise ValueError(
                IntervalAggregationFailureReason.INVALID_INTERVAL.value
            )
        if self.end_timestamp_ms <= self.start_timestamp_ms:
            raise ValueError(
                IntervalAggregationFailureReason.INVALID_INTERVAL.value
            )
        if self.interval_type not in {item.value for item in IntervalType}:
            raise ValueError(
                IntervalAggregationFailureReason.INVALID_INTERVAL.value
            )

    @property
    def duration_ms(self) -> int:
        return self.end_timestamp_ms - self.start_timestamp_ms

    def contains(self, timestamp_ms: int) -> bool:
        return (
            self.start_timestamp_ms
            <= timestamp_ms
            < self.end_timestamp_ms
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class IntervalAvailabilitySummary:
    available: bool
    total_frame_count: int
    valid_frame_count: int
    invalid_frame_count: int
    availability_ratio: float
    longest_missing_duration_ms: int
    failure_reason_counts: dict[str, int]
    failure_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NumericMetricSummary:
    available: bool
    count: int
    minimum: float | None
    maximum: float | None
    mean: float | None
    median: float | None
    mad: float | None
    standard_deviation: float | None
    p05: float | None
    p25: float | None
    p75: float | None
    p95: float | None
    absolute_mean: float | None
    absolute_median: float | None
    absolute_p95: float | None
    failure_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HeadPoseIntervalSummary:
    availability: IntervalAvailabilitySummary
    relative_yaw_deg: NumericMetricSummary
    relative_pitch_deg: NumericMetricSummary
    relative_roll_deg: NumericMetricSummary
    yaw_velocity_deg_per_sec: NumericMetricSummary | None
    pitch_velocity_deg_per_sec: NumericMetricSummary | None
    roll_velocity_deg_per_sec: NumericMetricSummary | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "availability": self.availability.to_dict(),
            "relative_yaw_deg": self.relative_yaw_deg.to_dict(),
            "relative_pitch_deg": self.relative_pitch_deg.to_dict(),
            "relative_roll_deg": self.relative_roll_deg.to_dict(),
            "yaw_velocity_deg_per_sec": (
                self.yaw_velocity_deg_per_sec.to_dict()
                if self.yaw_velocity_deg_per_sec is not None
                else None
            ),
            "pitch_velocity_deg_per_sec": (
                self.pitch_velocity_deg_per_sec.to_dict()
                if self.pitch_velocity_deg_per_sec is not None
                else None
            ),
            "roll_velocity_deg_per_sec": (
                self.roll_velocity_deg_per_sec.to_dict()
                if self.roll_velocity_deg_per_sec is not None
                else None
            ),
        }


@dataclass(frozen=True)
class PostureIntervalSummary:
    shoulder_availability: IntervalAvailabilitySummary
    nose_alignment_availability: IntervalAvailabilitySummary
    face_alignment_availability: IntervalAvailabilitySummary
    relative_shoulder_tilt_deg: NumericMetricSummary
    relative_shoulder_height_difference_norm: NumericMetricSummary
    relative_shoulder_center_x: NumericMetricSummary
    relative_shoulder_center_y: NumericMetricSummary
    relative_shoulder_width_norm: NumericMetricSummary
    relative_nose_shoulder_offset_x_norm: NumericMetricSummary
    relative_nose_shoulder_offset_y_norm: NumericMetricSummary
    relative_face_shoulder_offset_x_norm: NumericMetricSummary
    relative_face_shoulder_offset_y_norm: NumericMetricSummary
    shoulder_center_displacement_norm: NumericMetricSummary | None
    shoulder_center_velocity_norm_per_sec: NumericMetricSummary | None
    shoulder_tilt_delta_deg: NumericMetricSummary | None
    shoulder_tilt_velocity_deg_per_sec: NumericMetricSummary | None
    shoulder_width_delta_norm: NumericMetricSummary | None
    shoulder_width_change_rate_per_sec: NumericMetricSummary | None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for field in (
            "shoulder_availability",
            "nose_alignment_availability",
            "face_alignment_availability",
        ):
            payload[field] = getattr(self, field).to_dict()
        metric_fields = (
            "relative_shoulder_tilt_deg",
            "relative_shoulder_height_difference_norm",
            "relative_shoulder_center_x",
            "relative_shoulder_center_y",
            "relative_shoulder_width_norm",
            "relative_nose_shoulder_offset_x_norm",
            "relative_nose_shoulder_offset_y_norm",
            "relative_face_shoulder_offset_x_norm",
            "relative_face_shoulder_offset_y_norm",
            "shoulder_center_displacement_norm",
            "shoulder_center_velocity_norm_per_sec",
            "shoulder_tilt_delta_deg",
            "shoulder_tilt_velocity_deg_per_sec",
            "shoulder_width_delta_norm",
            "shoulder_width_change_rate_per_sec",
        )
        for field in metric_fields:
            value = getattr(self, field)
            payload[field] = value.to_dict() if value is not None else None
        return payload


@dataclass(frozen=True)
class IntervalEventSummary:
    head_pose_jump_candidate_count: int
    posture_jump_candidate_count: int
    event_type_counts: dict[str, int]
    event_timestamps_ms: tuple[int, ...]
    ignored_target_mismatch_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class IntervalDataQuality:
    available: bool
    total_frame_count: int
    head_pose_availability_ratio: float
    posture_availability_ratio: float
    nose_alignment_availability_ratio: float
    face_alignment_availability_ratio: float
    target_continuity_ratio: float
    timestamp_monotonic: bool
    duplicate_frame_count: int
    duplicate_timestamp_count: int
    quality_score: float
    warnings: tuple[str, ...]
    failure_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class IntervalAggregationResult:
    interval_id: str
    interval_type: str
    start_timestamp_ms: int
    end_timestamp_ms: int
    duration_ms: int
    target_id: str
    data_quality: IntervalDataQuality
    head_pose: HeadPoseIntervalSummary
    posture: PostureIntervalSummary
    events: IntervalEventSummary
    warnings: tuple[str, ...]
    failure_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "interval_id": self.interval_id,
            "interval_type": self.interval_type,
            "start_timestamp_ms": self.start_timestamp_ms,
            "end_timestamp_ms": self.end_timestamp_ms,
            "duration_ms": self.duration_ms,
            "target_id": self.target_id,
            "data_quality": self.data_quality.to_dict(),
            "head_pose": self.head_pose.to_dict(),
            "posture": self.posture.to_dict(),
            "events": self.events.to_dict(),
            "warnings": list(self.warnings),
            "failure_reason": self.failure_reason,
        }
