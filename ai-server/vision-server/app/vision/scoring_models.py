"""Fixture scoring result and provenance contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class MetricScoreStatus(str, Enum):
    NOT_EVALUATED = "NOT_EVALUATED"
    SCORED_TEST_FIXTURE = "SCORED_TEST_FIXTURE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    METRIC_UNAVAILABLE = "METRIC_UNAVAILABLE"
    EVIDENCE_NOT_APPROVED = "EVIDENCE_NOT_APPROVED"
    THRESHOLD_NOT_APPROVED = "THRESHOLD_NOT_APPROVED"
    UNIT_MISMATCH = "UNIT_MISMATCH"
    PROFILE_VERSION_MISMATCH = "PROFILE_VERSION_MISMATCH"
    NO_MATCHING_BAND = "NO_MATCHING_BAND"
    INVALID_RULE = "INVALID_RULE"


@dataclass(frozen=True)
class ScoreProvenance:
    source_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    mapping_ids: tuple[str, ...]
    evidence_profile_id: str
    evidence_profile_version: str
    threshold_profile_id: str
    threshold_profile_version: str
    scoring_policy_id: str
    scoring_policy_version: str
    rule_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MetricScoreResult:
    available: bool
    metric_id: str
    input_value: float | None
    input_unit: str
    threshold_profile_id: str
    threshold_profile_version: str
    scoring_policy_id: str
    scoring_policy_version: str
    rule_id: str
    matched_band_id: str | None
    test_fixture_score: float | None
    status: str
    warnings: tuple[str, ...]
    failure_reason: str | None
    provenance: ScoreProvenance | None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["provenance"] = (
            self.provenance.to_dict()
            if self.provenance is not None
            else None
        )
        return payload
