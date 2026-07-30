"""Fixture-only threshold contracts and deterministic band validation."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from app.vision.evidence_models import (
    EvidenceStatus,
    _enum_value,
    _finite_optional,
    _required,
)
from app.vision.evidence_profile_models import (
    EvidenceDomain,
    validate_iso_datetime,
    validate_semver,
)


class ThresholdComparisonMode(str, Enum):
    LOWER_IS_BETTER = "LOWER_IS_BETTER"
    HIGHER_IS_BETTER = "HIGHER_IS_BETTER"
    TARGET_RANGE = "TARGET_RANGE"
    SYMMETRIC_ABSOLUTE = "SYMMETRIC_ABSOLUTE"
    CATEGORICAL = "CATEGORICAL"
    CUSTOM = "CUSTOM"


@dataclass(frozen=True)
class ThresholdBand:
    band_id: str
    label: str
    lower_bound: float | None
    upper_bound: float | None
    lower_inclusive: bool
    upper_inclusive: bool
    output_value: float | None

    def __post_init__(self) -> None:
        _required(self.band_id, "band_id")
        _required(self.label, "label")
        _finite_optional(self.lower_bound, "lower_bound")
        _finite_optional(self.upper_bound, "upper_bound")
        _finite_optional(self.output_value, "output_value")
        if self.lower_bound is None and self.upper_bound is None:
            raise ValueError("A band cannot be unbounded on both sides")
        if (
            self.lower_bound is not None
            and self.upper_bound is not None
            and self.lower_bound > self.upper_bound
        ):
            raise ValueError("lower_bound must not exceed upper_bound")

    def contains(self, value: float) -> bool:
        if not math.isfinite(value):
            return False
        lower_ok = (
            True
            if self.lower_bound is None
            else value > self.lower_bound
            or (self.lower_inclusive and value == self.lower_bound)
        )
        upper_ok = (
            True
            if self.upper_bound is None
            else value < self.upper_bound
            or (self.upper_inclusive and value == self.upper_bound)
        )
        return lower_ok and upper_ok

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_threshold_bands(
    bands: tuple[ThresholdBand, ...],
    *,
    allow_gaps: bool = False,
) -> None:
    if not bands:
        raise ValueError("At least one threshold band is required")
    ids = [band.band_id for band in bands]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate threshold band ID")
    ordered = sorted(
        bands,
        key=lambda band: (
            float("-inf")
            if band.lower_bound is None
            else band.lower_bound,
            band.band_id,
        ),
    )
    if not allow_gaps:
        if ordered[0].lower_bound is not None:
            raise ValueError("Threshold bands leave a lower range gap")
        if ordered[-1].upper_bound is not None:
            raise ValueError("Threshold bands leave an upper range gap")
    for previous, current in zip(ordered, ordered[1:]):
        if previous.upper_bound is None:
            raise ValueError("Threshold bands overlap after an unbounded band")
        if current.lower_bound is None:
            raise ValueError("Only the first band may be lower-unbounded")
        if previous.upper_bound > current.lower_bound:
            raise ValueError("Threshold bands overlap")
        if previous.upper_bound < current.lower_bound and not allow_gaps:
            raise ValueError("Threshold bands contain a range gap")
        if previous.upper_bound == current.lower_bound:
            if previous.upper_inclusive and current.lower_inclusive:
                raise ValueError("Threshold bands overlap at a boundary")
            if (
                not previous.upper_inclusive
                and not current.lower_inclusive
                and not allow_gaps
            ):
                raise ValueError("Threshold bands leave a boundary gap")


@dataclass(frozen=True)
class MetricThresholdRule:
    rule_id: str
    metric_id: str
    evidence_profile_id: str
    evidence_profile_version: str
    comparison_mode: str
    bands: tuple[ThresholdBand, ...]
    unit: str
    minimum_data_quality: float | None
    minimum_availability_ratio: float | None
    minimum_sample_count: int | None
    maximum_longest_missing_duration_ms: int | None
    required_target_continuity: float | None
    status: str
    rationale: str
    allow_band_gaps: bool = False

    def __post_init__(self) -> None:
        for value, name in (
            (self.rule_id, "rule_id"),
            (self.metric_id, "metric_id"),
            (self.evidence_profile_id, "evidence_profile_id"),
            (self.unit, "unit"),
            (self.rationale, "rationale"),
        ):
            _required(value, name)
        validate_semver(self.evidence_profile_version)
        _enum_value(
            self.comparison_mode,
            ThresholdComparisonMode,
            "comparison_mode",
        )
        _enum_value(self.status, EvidenceStatus, "status")
        for value, name in (
            (self.minimum_data_quality, "minimum_data_quality"),
            (self.minimum_availability_ratio, "minimum_availability_ratio"),
            (self.required_target_continuity, "required_target_continuity"),
        ):
            if value is not None and not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be within 0..1")
        for value, name in (
            (self.minimum_sample_count, "minimum_sample_count"),
            (
                self.maximum_longest_missing_duration_ms,
                "maximum_longest_missing_duration_ms",
            ),
        ):
            if value is not None and (
                isinstance(value, bool) or value < 0
            ):
                raise ValueError(f"{name} must be non-negative")
        validate_threshold_bands(
            self.bands,
            allow_gaps=self.allow_band_gaps,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["bands"] = [band.to_dict() for band in self.bands]
        return payload


@dataclass(frozen=True)
class ThresholdProfile:
    threshold_profile_id: str
    version: str
    name: str
    domain: str
    evidence_profile_id: str
    evidence_profile_version: str
    rules: tuple[MetricThresholdRule, ...]
    status: str
    created_at: str
    supersedes_version: str | None

    def __post_init__(self) -> None:
        for value, name in (
            (self.threshold_profile_id, "threshold_profile_id"),
            (self.name, "name"),
            (self.evidence_profile_id, "evidence_profile_id"),
        ):
            _required(value, name)
        validate_semver(self.version)
        validate_semver(self.evidence_profile_version)
        _enum_value(self.domain, EvidenceDomain, "domain")
        _enum_value(self.status, EvidenceStatus, "status")
        validate_iso_datetime(self.created_at, "created_at")
        if not self.rules:
            raise ValueError("ThresholdProfile requires rules")
        ids = [rule.rule_id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate threshold rule ID")
        for rule in self.rules:
            if (
                rule.evidence_profile_id != self.evidence_profile_id
                or rule.evidence_profile_version
                != self.evidence_profile_version
            ):
                raise ValueError(
                    "Rule evidence profile reference does not match profile"
                )
        if self.supersedes_version is not None:
            validate_semver(self.supersedes_version)
            if self.supersedes_version == self.version:
                raise ValueError("supersedes_version cannot reference itself")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["rules"] = [rule.to_dict() for rule in self.rules]
        return payload
