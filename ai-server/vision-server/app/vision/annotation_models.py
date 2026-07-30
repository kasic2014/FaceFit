"""Observable-only annotation and independent-rater models."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from app.vision.data_collection_models import _required_id


class AnnotationCategory(str, Enum):
    HEAD = "HEAD"
    UPPER_BODY = "UPPER_BODY"
    DATA_QUALITY = "DATA_QUALITY"


class AnnotationDirection(str, Enum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    UP = "UP"
    DOWN = "DOWN"


class AnnotationStatus(str, Enum):
    DRAFT = "DRAFT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    TEST_FIXTURE = "TEST_FIXTURE"


class AnnotationLayer(str, Enum):
    RATER_A_ORIGINAL = "RATER_A_ORIGINAL"
    RATER_B_ORIGINAL = "RATER_B_ORIGINAL"
    ADJUDICATED_RESULT = "ADJUDICATED_RESULT"


@dataclass(frozen=True)
class AnnotationLabelDefinition:
    label_id: str
    display_name: str
    description: str
    category: str
    requires_direction: bool
    allowed_directions: tuple[str, ...]
    observable_only: bool
    status: str

    def __post_init__(self) -> None:
        _required_id(self.label_id, "label_id")
        if not self.display_name.strip() or not self.description.strip():
            raise ValueError("label display_name and description are required")
        if self.category not in {item.value for item in AnnotationCategory}:
            raise ValueError("invalid annotation category")
        if self.status not in {item.value for item in AnnotationStatus}:
            raise ValueError("invalid annotation status")
        allowed = {item.value for item in AnnotationDirection}
        if not set(self.allowed_directions).issubset(allowed):
            raise ValueError("invalid allowed_directions")
        if self.requires_direction != bool(self.allowed_directions):
            raise ValueError("direction contract is inconsistent")
        if not self.observable_only:
            raise ValueError("labels must be directly observable")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["allowed_directions"] = list(self.allowed_directions)
        return value


@dataclass(frozen=True)
class AnnotationRubric:
    rubric_id: str
    version: str
    status: str
    label_ids: tuple[str, ...]
    interval_end_exclusive: bool
    inference_prohibited: bool

    def __post_init__(self) -> None:
        _required_id(self.rubric_id, "rubric_id")
        if self.status not in {item.value for item in AnnotationStatus}:
            raise ValueError("invalid rubric status")
        if not self.label_ids or len(set(self.label_ids)) != len(self.label_ids):
            raise ValueError("rubric label_ids must be unique and non-empty")
        if not self.interval_end_exclusive or not self.inference_prohibited:
            raise ValueError("rubric safety contracts must be enabled")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["label_ids"] = list(self.label_ids)
        return value


@dataclass(frozen=True)
class AnnotationEvent:
    event_id: str
    annotation_session_id: str
    answer_id: str
    rater_id: str
    label_id: str
    start_timestamp_ms: int
    end_timestamp_ms: int
    direction: str | None
    rater_confidence: float
    layer: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.event_id, "event_id"),
            (self.annotation_session_id, "annotation_session_id"),
            (self.answer_id, "answer_id"),
            (self.rater_id, "rater_id"),
            (self.label_id, "label_id"),
        ):
            _required_id(value, name)
        if (
            isinstance(self.start_timestamp_ms, bool)
            or isinstance(self.end_timestamp_ms, bool)
            or not isinstance(self.start_timestamp_ms, int)
            or not isinstance(self.end_timestamp_ms, int)
            or self.start_timestamp_ms < 0
            or self.end_timestamp_ms <= self.start_timestamp_ms
        ):
            raise ValueError("event must have a valid [start, end) interval")
        if self.direction is not None and self.direction not in {
            item.value for item in AnnotationDirection
        }:
            raise ValueError("invalid direction")
        if (
            isinstance(self.rater_confidence, bool)
            or not isinstance(self.rater_confidence, (int, float))
            or not math.isfinite(float(self.rater_confidence))
            or not 0.0 <= self.rater_confidence <= 1.0
        ):
            raise ValueError("rater_confidence must be finite within 0..1")
        if self.layer not in {item.value for item in AnnotationLayer}:
            raise ValueError("invalid annotation layer")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AnnotationRater:
    rater_id: str
    role: str
    trained_rubric_version: str
    status: str

    def __post_init__(self) -> None:
        _required_id(self.rater_id, "rater_id")
        if self.role not in {"INDEPENDENT_RATER", "ADJUDICATOR"}:
            raise ValueError("invalid rater role")
        if self.status not in {"ACTIVE", "TEST_FIXTURE"}:
            raise ValueError("invalid rater status")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AnnotationSession:
    annotation_session_id: str
    rater_id: str
    rubric_id: str
    rubric_version: str
    layer: str
    blinded_to_stage10_metrics: bool
    blinded_to_stage11_fixture_scores: bool
    blinded_to_other_raters: bool
    blinded_to_direct_identifiers: bool

    def __post_init__(self) -> None:
        for value, name in (
            (self.annotation_session_id, "annotation_session_id"),
            (self.rater_id, "rater_id"),
            (self.rubric_id, "rubric_id"),
        ):
            _required_id(value, name)
        if self.layer not in {item.value for item in AnnotationLayer}:
            raise ValueError("invalid annotation layer")
        if not all(
            (
                self.blinded_to_stage10_metrics,
                self.blinded_to_stage11_fixture_scores,
                self.blinded_to_direct_identifiers,
            )
        ):
            raise ValueError("all annotation layers must be blind to metrics and PII")
        if (
            self.layer != AnnotationLayer.ADJUDICATED_RESULT.value
            and not self.blinded_to_other_raters
        ):
            raise ValueError("original raters must be blind to other annotations")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EventAgreementResult:
    answer_id: str
    label_id: str
    rater_a_event_id: str | None
    rater_b_event_id: str | None
    temporal_iou: float | None
    match_status: str

    def __post_init__(self) -> None:
        if self.temporal_iou is not None and (
            not math.isfinite(self.temporal_iou)
            or not 0.0 <= self.temporal_iou <= 1.0
        ):
            raise ValueError("temporal_iou must be finite within 0..1")
        if self.match_status not in {
            "MATCHED",
            "NO_OVERLAP",
            "MISSING_RATER_A",
            "MISSING_RATER_B",
        }:
            raise ValueError("invalid match_status")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
