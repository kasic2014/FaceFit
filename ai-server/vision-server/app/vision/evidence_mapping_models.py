"""Explicit paper-concept to Face-Fit metric mapping models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from app.vision.evidence_models import (
    EvidenceApplicability,
    EvidenceStatus,
    _enum_value,
    _required,
)


class EvidenceMappingType(str, Enum):
    DIRECT = "DIRECT"
    UNIT_CONVERSION = "UNIT_CONVERSION"
    PROXY = "PROXY"
    DERIVED = "DERIVED"
    COMPOSITE = "COMPOSITE"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class EvidenceMetricMapping:
    mapping_id: str
    evidence_id: str
    facefit_metric_id: str
    mapping_type: str
    applicability: str
    source_unit: str | None
    target_unit: str
    conversion_rule: str | None
    transformation: str | None
    rationale: str
    limitations: tuple[str, ...]
    review_status: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.mapping_id, "mapping_id"),
            (self.evidence_id, "evidence_id"),
            (self.facefit_metric_id, "facefit_metric_id"),
            (self.target_unit, "target_unit"),
            (self.rationale, "rationale"),
        ):
            _required(value, name)
        _enum_value(
            self.mapping_type,
            EvidenceMappingType,
            "mapping_type",
        )
        _enum_value(
            self.applicability,
            EvidenceApplicability,
            "applicability",
        )
        _enum_value(self.review_status, EvidenceStatus, "review_status")
        if (
            self.source_unit is not None
            and self.source_unit != self.target_unit
            and not self.conversion_rule
        ):
            raise ValueError(
                "Unit mismatch requires an explicit conversion_rule"
            )
        if (
            self.mapping_type == EvidenceMappingType.UNIT_CONVERSION.value
            and not self.conversion_rule
        ):
            raise ValueError("UNIT_CONVERSION requires conversion_rule")
        if (
            self.mapping_type == EvidenceMappingType.DIRECT.value
            and self.source_unit is not None
            and self.source_unit != self.target_unit
        ):
            raise ValueError("DIRECT mapping requires identical units")
        if (
            self.mapping_type == EvidenceMappingType.PROXY.value
            and not self.limitations
        ):
            raise ValueError("PROXY mapping requires explicit limitations")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
