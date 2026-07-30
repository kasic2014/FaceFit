"""Typed models and configuration for limited 2D shoulder posture metrics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


COORDINATE_SPACE = "IMAGE_NORMALIZED"
HORIZONTAL_SIGN_CONVENTION = (
    "SCREEN_LEFT_NEGATIVE_SCREEN_RIGHT_POSITIVE"
)
SHOULDER_SIGN_CONVENTION = (
    "SUBJECT_RIGHT_SHOULDER_LOWER_POSITIVE_"
    "SUBJECT_LEFT_SHOULDER_LOWER_NEGATIVE"
)


class PostureFailureReason(str, Enum):
    SHOULDERS_AVAILABLE = "SHOULDERS_AVAILABLE"
    LEFT_SHOULDER_MISSING = "LEFT_SHOULDER_MISSING"
    RIGHT_SHOULDER_MISSING = "RIGHT_SHOULDER_MISSING"
    BOTH_SHOULDERS_MISSING = "BOTH_SHOULDERS_MISSING"
    INVALID_SHOULDER_WIDTH = "INVALID_SHOULDER_WIDTH"
    NOSE_MISSING = "NOSE_MISSING"
    FACE_NOT_DETECTED = "FACE_NOT_DETECTED"
    TARGET_NOT_AVAILABLE = "TARGET_NOT_AVAILABLE"
    MULTIPLE_PERSON_DETECTED = "MULTIPLE_PERSON_DETECTED"
    NON_FINITE_COORDINATE = "NON_FINITE_COORDINATE"


@dataclass(frozen=True)
class PostureRawConfiguration:
    """Configuration values selected for 1280x720 interview-style imagery.

    The minimum normalized shoulder width rejects collapsed or identical
    landmarks.  The coordinate margin permits small MediaPipe excursions just
    outside the image while still assigning lower coordinate quality.
    """

    minimum_shoulder_width_norm: float = 0.02
    coordinate_margin: float = 0.10
    expected_shoulder_width_norm: float = 0.20
    jump_mad_multiplier: float = 6.0
    minimum_jump_samples: int = 5
    minimum_jump_tilt_deg: float = 2.0
    minimum_jump_displacement_norm: float = 0.01
    minimum_jump_width_norm: float = 0.01
    minimum_jump_offset_norm: float = 0.04
    target_quality_weight: float = 0.20
    shoulder_quality_weight: float = 0.25
    nose_quality_weight: float = 0.10
    face_quality_weight: float = 0.10
    coordinate_quality_weight: float = 0.10
    width_quality_weight: float = 0.15
    temporal_quality_weight: float = 0.10
    overlay_point_radius_px: int = 6
    overlay_line_thickness_px: int = 2
    statistics_minimum_sample_count: int = 1


@dataclass(frozen=True)
class ShoulderPostureRawResult:
    available: bool
    shoulders_available: bool
    nose_alignment_available: bool
    face_alignment_available: bool
    shoulder_tilt_deg: float | None
    shoulder_height_difference_norm: float | None
    shoulder_center_x: float | None
    shoulder_center_y: float | None
    shoulder_width_norm: float | None
    nose_shoulder_offset_x_norm: float | None
    nose_shoulder_offset_y_norm: float | None
    face_shoulder_offset_x_norm: float | None
    face_shoulder_offset_y_norm: float | None
    confidence: float
    coordinate_space: str
    horizontal_sign_convention: str
    shoulder_sign_convention: str
    failure_reason: str | None
    status_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ShoulderPostureTemporalResult:
    delta_time_seconds: float | None
    shoulder_center_displacement_norm: float | None
    shoulder_center_velocity_norm_per_sec: float | None
    shoulder_tilt_delta_deg: float | None
    shoulder_tilt_velocity_deg_per_sec: float | None
    shoulder_width_delta_norm: float | None
    shoulder_width_change_rate_per_sec: float | None
    nose_offset_x_delta_norm: float | None
    nose_offset_y_delta_norm: float | None
    face_offset_x_delta_norm: float | None
    face_offset_y_delta_norm: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PostureJumpEvent:
    timestamp_ms: int
    event_type: str
    target_id: str | None
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
