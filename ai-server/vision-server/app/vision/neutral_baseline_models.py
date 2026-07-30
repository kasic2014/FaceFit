"""Typed models for session-local neutral baseline collection.

A baseline is a session reference captured under one camera setup.  It is not
an absolute normal posture and its quality value is not an interview score.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class BaselineCollectionStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    COLLECTING = "COLLECTING"
    SUFFICIENT = "SUFFICIENT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class BaselineFailureReason(str, Enum):
    INSUFFICIENT_FRAMES = "INSUFFICIENT_FRAMES"
    UNSTABLE_HEAD_MOTION = "UNSTABLE_HEAD_MOTION"
    UNSTABLE_SHOULDER_MOTION = "UNSTABLE_SHOULDER_MOTION"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    FACE_ALIGNMENT_UNAVAILABLE = "FACE_ALIGNMENT_UNAVAILABLE"
    MULTIPLE_PERSON_DETECTED = "MULTIPLE_PERSON_DETECTED"
    TARGET_NOT_AVAILABLE = "TARGET_NOT_AVAILABLE"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    NON_FINITE_VALUE = "NON_FINITE_VALUE"


class BaselineQualityWarning(str, Enum):
    HEAD_POSE_PARTIAL = "HEAD_POSE_PARTIAL"
    POSTURE_PARTIAL = "POSTURE_PARTIAL"
    FACE_ALIGNMENT_UNAVAILABLE = "FACE_ALIGNMENT_UNAVAILABLE"
    OUTLIERS_REMOVED = "OUTLIERS_REMOVED"
    COLLECTION_IS_NOT_NEUTRAL_GROUND_TRUTH = (
        "COLLECTION_IS_NOT_NEUTRAL_GROUND_TRUTH"
    )


@dataclass(frozen=True)
class NeutralBaselineConfig:
    """Collection-quality thresholds, never posture evaluation thresholds."""

    collection_duration_ms: int = 2_000
    minimum_candidate_frames: int = 8
    minimum_head_pose_frames: int = 7
    minimum_posture_frames: int = 8
    minimum_nose_alignment_frames: int = 8
    minimum_face_alignment_frames: int = 7
    minimum_head_pose_confidence: float = 0.65
    minimum_posture_confidence: float = 0.80
    maximum_head_angular_velocity_deg_per_sec: float = 45.0
    maximum_shoulder_center_velocity_norm_per_sec: float = 0.15
    maximum_shoulder_tilt_velocity_deg_per_sec: float = 30.0
    maximum_shoulder_width_change_rate_per_sec: float = 0.10
    aggregation_method: str = "MEDIAN"
    outlier_method: str = "MAD"
    mad_multiplier: float = 3.5
    minimum_outlier_filter_samples: int = 5

    def __post_init__(self) -> None:
        integer_fields = (
            self.collection_duration_ms,
            self.minimum_candidate_frames,
            self.minimum_head_pose_frames,
            self.minimum_posture_frames,
            self.minimum_nose_alignment_frames,
            self.minimum_face_alignment_frames,
            self.minimum_outlier_filter_samples,
        )
        if any(value <= 0 for value in integer_fields):
            raise ValueError("Baseline duration and frame counts must be positive")
        confidence_fields = (
            self.minimum_head_pose_confidence,
            self.minimum_posture_confidence,
        )
        if any(value < 0.0 or value > 1.0 for value in confidence_fields):
            raise ValueError("Baseline confidence thresholds must be within 0..1")
        velocity_fields = (
            self.maximum_head_angular_velocity_deg_per_sec,
            self.maximum_shoulder_center_velocity_norm_per_sec,
            self.maximum_shoulder_tilt_velocity_deg_per_sec,
            self.maximum_shoulder_width_change_rate_per_sec,
            self.mad_multiplier,
        )
        if any(value <= 0.0 for value in velocity_fields):
            raise ValueError("Baseline velocity and MAD thresholds must be positive")
        if self.aggregation_method != "MEDIAN" or self.outlier_method != "MAD":
            raise ValueError("Only MEDIAN aggregation with MAD outliers is supported")


@dataclass(frozen=True)
class NeutralBaselineFrame:
    timestamp_ms: int
    target_id: str | None
    target_status: str | None
    candidate_count: int
    target_confidence: float
    head_pose: dict[str, Any]
    head_angular_velocity_deg_per_sec: float | None
    head_jump_candidate: bool
    posture_raw: dict[str, Any]
    posture_temporal: dict[str, Any]
    posture_jump_candidate: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BaselineCandidateDecision:
    timestamp_ms: int
    common_available: bool
    head_pose_candidate: bool
    shoulder_candidate: bool
    nose_alignment_candidate: bool
    face_alignment_candidate: bool
    common_reasons: tuple[str, ...]
    head_pose_reasons: tuple[str, ...]
    shoulder_reasons: tuple[str, ...]
    nose_alignment_reasons: tuple[str, ...]
    face_alignment_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BaselineCandidateCollection:
    collection_start_ms: int
    collection_end_ms: int
    total_frame_count: int
    common_frame_count: int
    head_pose_frames: tuple[NeutralBaselineFrame, ...]
    shoulder_frames: tuple[NeutralBaselineFrame, ...]
    nose_alignment_frames: tuple[NeutralBaselineFrame, ...]
    face_alignment_frames: tuple[NeutralBaselineFrame, ...]
    decisions: tuple[BaselineCandidateDecision, ...]
    rejection_reason_counts: dict[str, int]


@dataclass(frozen=True)
class BaselineMetricDiagnostic:
    metric_name: str
    candidate_count: int
    finite_count: int
    used_count: int
    initial_median: float | None
    mad: float | None
    outlier_count: int
    aggregation_method: str
    outlier_method: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HeadPoseBaseline:
    available: bool
    yaw_deg: float | None
    pitch_deg: float | None
    roll_deg: float | None
    candidate_frame_count: int
    used_frame_count: int
    confidence: float
    failure_reason: str | None
    metric_diagnostics: dict[str, BaselineMetricDiagnostic]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["metric_diagnostics"] = {
            key: value.to_dict()
            for key, value in self.metric_diagnostics.items()
        }
        return payload


@dataclass(frozen=True)
class PostureBaseline:
    available: bool
    shoulder_tilt_deg: float | None
    shoulder_height_difference_norm: float | None
    shoulder_center_x: float | None
    shoulder_center_y: float | None
    shoulder_width_norm: float | None
    nose_alignment_available: bool
    nose_shoulder_offset_x_norm: float | None
    nose_shoulder_offset_y_norm: float | None
    face_alignment_available: bool
    face_shoulder_offset_x_norm: float | None
    face_shoulder_offset_y_norm: float | None
    candidate_frame_count: int
    used_frame_count: int
    nose_candidate_frame_count: int
    nose_used_frame_count: int
    face_candidate_frame_count: int
    face_used_frame_count: int
    confidence: float
    failure_reason: str | None
    face_alignment_failure_reason: str | None
    metric_diagnostics: dict[str, BaselineMetricDiagnostic]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["metric_diagnostics"] = {
            key: value.to_dict()
            for key, value in self.metric_diagnostics.items()
        }
        return payload


@dataclass(frozen=True)
class SessionNeutralBaseline:
    available: bool
    target_id: str
    collection_start_ms: int
    collection_end_ms: int
    head_pose: HeadPoseBaseline
    posture: PostureBaseline
    quality_score: float
    quality_components: dict[str, float]
    status: str
    warnings: tuple[str, ...]
    failure_reason: str | None
    aggregation_method: str
    outlier_method: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["head_pose"] = self.head_pose.to_dict()
        payload["posture"] = self.posture.to_dict()
        return payload
