"""Purpose-specific consent gate contracts for Stage 13."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from app.vision.data_collection_models import PARTICIPANT_RE, _required_id


class ConsentStatus(str, Enum):
    NOT_REQUESTED = "NOT_REQUESTED"
    PENDING = "PENDING"
    GRANTED = "GRANTED"
    PARTIALLY_GRANTED = "PARTIALLY_GRANTED"
    WITHDRAWN = "WITHDRAWN"
    EXPIRED = "EXPIRED"
    INVALID = "INVALID"


class ConsentPurpose(str, Enum):
    VIDEO_COLLECTION = "VIDEO_COLLECTION"
    AUTOMATED_ANALYSIS = "AUTOMATED_ANALYSIS"
    RESEARCH_USE = "RESEARCH_USE"
    MODEL_DEVELOPMENT = "MODEL_DEVELOPMENT"


@dataclass(frozen=True)
class ConsentReference:
    consent_reference_id: str
    participant_id: str
    status: str
    document_version: str
    video_collection_allowed: bool
    automated_analysis_allowed: bool
    research_use_allowed: bool
    model_development_use_allowed: bool
    withdrawn_at: str | None = None

    def __post_init__(self) -> None:
        _required_id(self.consent_reference_id, "consent_reference_id")
        if not PARTICIPANT_RE.fullmatch(self.participant_id):
            raise ValueError("invalid participant_id")
        if self.status not in {item.value for item in ConsentStatus}:
            raise ValueError(f"Invalid consent status: {self.status}")
        if not self.document_version.strip():
            raise ValueError("document_version must not be empty")
        if self.status == ConsentStatus.WITHDRAWN.value and not self.withdrawn_at:
            raise ValueError("withdrawn consent requires withdrawn_at")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConsentGateResult:
    allowed: bool
    purpose: str
    reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_PURPOSE_FIELDS = {
    ConsentPurpose.VIDEO_COLLECTION.value: "video_collection_allowed",
    ConsentPurpose.AUTOMATED_ANALYSIS.value: "automated_analysis_allowed",
    ConsentPurpose.RESEARCH_USE.value: "research_use_allowed",
    ConsentPurpose.MODEL_DEVELOPMENT.value: "model_development_use_allowed",
}


def evaluate_consent_gate(
    consent: ConsentReference | None,
    purpose: str,
) -> ConsentGateResult:
    if purpose not in _PURPOSE_FIELDS:
        raise ValueError(f"Invalid consent purpose: {purpose}")
    if consent is None:
        return ConsentGateResult(False, purpose, "CONSENT_NOT_FOUND")
    if consent.status == ConsentStatus.WITHDRAWN.value:
        return ConsentGateResult(False, purpose, "CONSENT_WITHDRAWN")
    if consent.status not in {
        ConsentStatus.GRANTED.value,
        ConsentStatus.PARTIALLY_GRANTED.value,
    }:
        return ConsentGateResult(False, purpose, f"CONSENT_{consent.status}")
    if not getattr(consent, _PURPOSE_FIELDS[purpose]):
        return ConsentGateResult(False, purpose, "PURPOSE_NOT_AUTHORIZED")
    return ConsentGateResult(True, purpose, None)
