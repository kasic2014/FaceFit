"""Evidence metadata models without real paper values or approvals."""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from urllib.parse import urlparse


SYNTHETIC_FIXTURE_NOTICE = (
    "This value is synthetic test data and is not an approved "
    "Face-Fit evaluation threshold."
)


class EvidenceStatus(str, Enum):
    DRAFT = "DRAFT"
    TEST_FIXTURE = "TEST_FIXTURE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    APPROVED = "APPROVED"
    DEPRECATED = "DEPRECATED"
    REJECTED = "REJECTED"


class EvidenceSourceType(str, Enum):
    JOURNAL_ARTICLE = "JOURNAL_ARTICLE"
    CONFERENCE_PAPER = "CONFERENCE_PAPER"
    SYSTEMATIC_REVIEW = "SYSTEMATIC_REVIEW"
    META_ANALYSIS = "META_ANALYSIS"
    STANDARD = "STANDARD"
    GOVERNMENT_REPORT = "GOVERNMENT_REPORT"
    DATASET = "DATASET"
    TECHNICAL_REPORT = "TECHNICAL_REPORT"
    BOOK = "BOOK"
    OTHER = "OTHER"


class EvidenceStatisticType(str, Enum):
    POINT_ESTIMATE = "POINT_ESTIMATE"
    RANGE = "RANGE"
    MEAN = "MEAN"
    MEDIAN = "MEDIAN"
    STANDARD_DEVIATION = "STANDARD_DEVIATION"
    PERCENTILE = "PERCENTILE"
    CORRELATION = "CORRELATION"
    ODDS_RATIO = "ODDS_RATIO"
    EFFECT_SIZE = "EFFECT_SIZE"
    THRESHOLD = "THRESHOLD"
    CATEGORY_BOUNDARY = "CATEGORY_BOUNDARY"
    OTHER = "OTHER"


class EvidenceStrength(str, Enum):
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"
    VERY_LOW = "VERY_LOW"
    NOT_ASSESSED = "NOT_ASSESSED"


class EvidenceApplicability(str, Enum):
    DIRECT = "DIRECT"
    PARTIAL = "PARTIAL"
    INDIRECT = "INDIRECT"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class EvidenceConflictType(str, Enum):
    THRESHOLD_CONFLICT = "THRESHOLD_CONFLICT"
    UNIT_CONFLICT = "UNIT_CONFLICT"
    APPLICABILITY_CONFLICT = "APPLICABILITY_CONFLICT"
    POPULATION_CONFLICT = "POPULATION_CONFLICT"
    RECORDING_CONTEXT_CONFLICT = "RECORDING_CONTEXT_CONFLICT"
    STATISTIC_TYPE_CONFLICT = "STATISTIC_TYPE_CONFLICT"


class EvidenceConflictResolutionStatus(str, Enum):
    OPEN = "OPEN"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    RESOLVED = "RESOLVED"
    ACCEPTED_WITH_LIMITATION = "ACCEPTED_WITH_LIMITATION"
    REJECTED = "REJECTED"


def _required(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _enum_value(value: str, enum_type: type[Enum], name: str) -> None:
    if value not in {item.value for item in enum_type}:
        raise ValueError(f"Invalid {name}: {value}")


def _finite_optional(value: float | None, name: str) -> None:
    if value is not None and (
        isinstance(value, bool) or not math.isfinite(float(value))
    ):
        raise ValueError(f"{name} must be finite")


@dataclass(frozen=True)
class ApplicabilityScope:
    population: str | None = None
    age_range: str | None = None
    recording_context: str | None = None
    camera_setup: str | None = None
    analysis_fps: float | None = None
    measurement_method: str | None = None
    body_region: str | None = None
    interview_context: bool | None = None
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.analysis_fps is not None and (
            isinstance(self.analysis_fps, bool)
            or not math.isfinite(float(self.analysis_fps))
            or self.analysis_fps <= 0
        ):
            raise ValueError("analysis_fps must be finite and positive")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceSource:
    source_id: str
    source_type: str
    title: str
    authors: tuple[str, ...]
    publication_year: int | None
    publisher: str | None
    journal_or_conference: str | None
    doi: str | None
    url: str | None
    language: str | None
    study_population: str | None
    sample_size: int | None
    peer_reviewed: bool | None
    access_date: str | None
    status: str
    notes: str | None

    def __post_init__(self) -> None:
        _required(self.source_id, "source_id")
        _required(self.title, "title")
        _enum_value(self.source_type, EvidenceSourceType, "source_type")
        _enum_value(self.status, EvidenceStatus, "status")
        if self.publication_year is not None:
            current_year = datetime.now().year
            if (
                isinstance(self.publication_year, bool)
                or not 1600 <= self.publication_year <= current_year + 1
            ):
                raise ValueError("publication_year is outside the valid range")
        if self.sample_size is not None and (
            isinstance(self.sample_size, bool) or self.sample_size < 0
        ):
            raise ValueError("sample_size must be non-negative")
        if self.doi is not None and not re.fullmatch(
            r"10\.\d{4,9}/\S+",
            self.doi,
        ):
            raise ValueError("doi format is invalid")
        if self.url is not None:
            parsed = urlparse(self.url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("url format is invalid")
        if self.access_date is not None:
            try:
                datetime.strptime(self.access_date, "%Y-%m-%d")
            except ValueError as exc:
                raise ValueError("access_date must use YYYY-MM-DD") from exc

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    source_id: str
    construct_name: str
    measurement_name: str
    statistic_type: str
    value: float | None
    lower_bound: float | None
    upper_bound: float | None
    unit: str | None
    population_scope: str | None
    context_scope: str | None
    extraction_location: str | None
    extraction_note: str | None
    evidence_strength: str
    applicability: str
    status: str
    applicability_scope: ApplicabilityScope | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.evidence_id, "evidence_id"),
            (self.source_id, "source_id"),
            (self.construct_name, "construct_name"),
            (self.measurement_name, "measurement_name"),
        ):
            _required(value, name)
        _enum_value(
            self.statistic_type,
            EvidenceStatisticType,
            "statistic_type",
        )
        _enum_value(
            self.evidence_strength,
            EvidenceStrength,
            "evidence_strength",
        )
        _enum_value(
            self.applicability,
            EvidenceApplicability,
            "applicability",
        )
        _enum_value(self.status, EvidenceStatus, "status")
        for value, name in (
            (self.value, "value"),
            (self.lower_bound, "lower_bound"),
            (self.upper_bound, "upper_bound"),
        ):
            _finite_optional(value, name)
        if (
            self.lower_bound is not None
            and self.upper_bound is not None
            and self.lower_bound > self.upper_bound
        ):
            raise ValueError("lower_bound must not exceed upper_bound")
        if (
            self.statistic_type == EvidenceStatisticType.RANGE.value
            and (
                self.lower_bound is None
                or self.upper_bound is None
            )
        ):
            raise ValueError("RANGE evidence requires both bounds")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["applicability_scope"] = (
            self.applicability_scope.to_dict()
            if self.applicability_scope is not None
            else None
        )
        return payload


@dataclass(frozen=True)
class EvidenceConflict:
    conflict_id: str
    metric_id: str
    evidence_ids: tuple[str, ...]
    conflict_type: str
    description: str
    resolution_status: str

    def __post_init__(self) -> None:
        _required(self.conflict_id, "conflict_id")
        _required(self.metric_id, "metric_id")
        _required(self.description, "description")
        _enum_value(
            self.conflict_type,
            EvidenceConflictType,
            "conflict_type",
        )
        _enum_value(
            self.resolution_status,
            EvidenceConflictResolutionStatus,
            "resolution_status",
        )
        if len(self.evidence_ids) < 2:
            raise ValueError("A conflict requires at least two evidence IDs")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
