"""Raw/baseline/relative feature models for later interval aggregation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class RelativeFeatureFailureReason(str, Enum):
    RAW_VALUE_UNAVAILABLE = "RAW_VALUE_UNAVAILABLE"
    BASELINE_UNAVAILABLE = "BASELINE_UNAVAILABLE"
    FACE_ALIGNMENT_BASELINE_UNAVAILABLE = (
        "FACE_ALIGNMENT_BASELINE_UNAVAILABLE"
    )
    TARGET_MISMATCH = "TARGET_MISMATCH"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    NON_FINITE_RAW_VALUE = "NON_FINITE_RAW_VALUE"
    NON_FINITE_BASELINE_VALUE = "NON_FINITE_BASELINE_VALUE"


@dataclass(frozen=True)
class RelativeMetricValue:
    metric_name: str
    raw_value: float | None
    baseline_value: float | None
    relative_value: float | None
    unit: str
    available: bool
    confidence: float
    timestamp_ms: int
    target_id: str
    failure_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RelativeFeatureGroup:
    available: bool
    metrics: dict[str, RelativeMetricValue]
    confidence: float
    failure_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "metrics": {
                key: value.to_dict() for key, value in self.metrics.items()
            },
            "confidence": self.confidence,
            "failure_reason": self.failure_reason,
        }


@dataclass(frozen=True)
class RelativeHeadPoseResult:
    available: bool
    yaw: RelativeMetricValue
    pitch: RelativeMetricValue
    roll: RelativeMetricValue
    confidence: float
    failure_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "yaw": self.yaw.to_dict(),
            "pitch": self.pitch.to_dict(),
            "roll": self.roll.to_dict(),
            "confidence": self.confidence,
            "failure_reason": self.failure_reason,
        }


@dataclass(frozen=True)
class RelativePostureResult:
    available: bool
    shoulder: RelativeFeatureGroup
    nose_alignment: RelativeFeatureGroup
    face_alignment: RelativeFeatureGroup
    confidence: float
    failure_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "shoulder": self.shoulder.to_dict(),
            "nose_alignment": self.nose_alignment.to_dict(),
            "face_alignment": self.face_alignment.to_dict(),
            "confidence": self.confidence,
            "failure_reason": self.failure_reason,
        }


@dataclass(frozen=True)
class RelativeFeatureFrame:
    timestamp_ms: int
    target_id: str
    head_pose: RelativeHeadPoseResult
    posture: RelativePostureResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_ms": self.timestamp_ms,
            "target_id": self.target_id,
            "head_pose": self.head_pose.to_dict(),
            "posture": self.posture.to_dict(),
        }


@dataclass(frozen=True)
class AnalysisInterval:
    start_timestamp_ms: int
    end_timestamp_ms: int
    interval_id: str

    def __post_init__(self) -> None:
        if (
            self.start_timestamp_ms < 0
            or self.end_timestamp_ms < self.start_timestamp_ms
        ):
            raise ValueError("Invalid analysis interval timestamps")
        if not self.interval_id:
            raise ValueError("interval_id must not be empty")
