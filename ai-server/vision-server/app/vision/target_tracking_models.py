"""Data models for session-scoped single-target tracking."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class TargetStatus(str, Enum):
    UNINITIALIZED = "UNINITIALIZED"
    TARGET_INITIALIZED = "TARGET_INITIALIZED"
    TARGET_TRACKED = "TARGET_TRACKED"
    TARGET_TEMPORARILY_LOST = "TARGET_TEMPORARILY_LOST"
    MULTIPLE_PERSON_AMBIGUOUS = "MULTIPLE_PERSON_AMBIGUOUS"
    TARGET_REACQUIRED = "TARGET_REACQUIRED"
    TARGET_LOST = "TARGET_LOST"


@dataclass(frozen=True)
class TargetCandidate:
    candidate_index: int
    face_index: int | None
    pose_index: int
    face_bounding_box: dict[str, float] | None
    face_center: dict[str, float] | None
    nose: dict[str, float] | None
    left_shoulder: dict[str, float] | None
    right_shoulder: dict[str, float] | None
    shoulder_center: dict[str, float] | None
    shoulder_width: float | None
    detection_confidence: float
    face_pose_consistency: float | None

    @property
    def initialization_ready(self) -> bool:
        return all((
            self.face_bounding_box,
            self.face_center,
            self.nose,
            self.left_shoulder,
            self.right_shoulder,
            self.shoulder_center,
            self.shoulder_width,
        ))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MatchResult:
    candidate_index: int
    cost: float
    confidence: float
    components: dict[str, float | None]


@dataclass(frozen=True)
class TrackingConfiguration:
    initialization_window_ms: int = 1_000
    maximum_lost_duration_ms: int = 2_000
    match_cost_threshold: float = 0.38
    ambiguity_margin_threshold: float = 0.035
    switch_risk_cost_threshold: float = 0.24
    maximum_candidates: int = 4
