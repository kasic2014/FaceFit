"""Models and explicit constants for approximate PnP head pose."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


NOSE_TIP_INDEX = 1
CHIN_INDEX = 152
RIGHT_EYE_OUTER_INDEX = 33
LEFT_EYE_OUTER_INDEX = 263
RIGHT_MOUTH_CORNER_INDEX = 61
LEFT_MOUTH_CORNER_INDEX = 291

HEAD_POSE_LANDMARK_INDICES = (
    NOSE_TIP_INDEX,
    CHIN_INDEX,
    RIGHT_EYE_OUTER_INDEX,
    LEFT_EYE_OUTER_INDEX,
    RIGHT_MOUTH_CORNER_INDEX,
    LEFT_MOUTH_CORNER_INDEX,
)

# Arbitrary template units. Y is positive downward to align with image pixels.
HEAD_POSE_MODEL_POINTS = (
    (0.0, 0.0, 0.0),
    (0.0, 330.0, -65.0),
    (-225.0, -170.0, -135.0),
    (225.0, -170.0, -135.0),
    (-150.0, 150.0, -125.0),
    (150.0, 150.0, -125.0),
)


class HeadPoseFailureReason(str, Enum):
    FACE_NOT_DETECTED = "FACE_NOT_DETECTED"
    TARGET_NOT_AVAILABLE = "TARGET_NOT_AVAILABLE"
    MULTIPLE_PERSON_DETECTED = "MULTIPLE_PERSON_DETECTED"
    REQUIRED_LANDMARK_MISSING = "REQUIRED_LANDMARK_MISSING"
    INVALID_LANDMARK_COORDINATE = "INVALID_LANDMARK_COORDINATE"
    SOLVEPNP_FAILED = "SOLVEPNP_FAILED"
    ROTATION_CONVERSION_FAILED = "ROTATION_CONVERSION_FAILED"
    NON_FINITE_RESULT = "NON_FINITE_RESULT"
    REPROJECTION_ERROR_TOO_HIGH = "REPROJECTION_ERROR_TOO_HIGH"


@dataclass(frozen=True)
class HeadPoseConfiguration:
    max_reprojection_error_px: float = 25.0
    focal_length_width_multiplier: float = 1.0
    jump_mad_multiplier: float = 6.0
    jump_fallback_threshold_deg: float = 20.0
    minimum_jump_deltas: int = 5
    target_confidence_weight: float = 0.25
    reprojection_weight: float = 0.35
    bbox_size_weight: float = 0.15
    temporal_continuity_weight: float = 0.25


@dataclass(frozen=True)
class HeadPoseResult:
    available: bool
    yaw_deg: float | None
    pitch_deg: float | None
    roll_deg: float | None
    confidence: float
    estimation_method: str
    failure_reason: str | None
    solvepnp_success: bool
    reprojection_error: float | None
    landmark_count: int
    camera_matrix_source: str
    target_id: str | None
    nose_pixel: tuple[float, float] | None = None
    axis_points: dict[str, tuple[float, float]] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
