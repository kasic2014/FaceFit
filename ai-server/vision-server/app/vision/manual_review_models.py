"""Restricted manual review decisions without trait or score fields."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.vision.data_collection_models import _required_id
from app.vision.pilot_collection_models import PilotExclusionReason, _timestamp


@dataclass(frozen=True)
class ManualReviewDecision:
    review_id: str
    pilot_session_id: str
    reviewer_id: str
    decision: str
    reason_codes: tuple[str, ...]
    reviewed_at: str
    notes: str | None

    def __post_init__(self) -> None:
        for value, name in (
            (self.review_id, "review_id"),
            (self.pilot_session_id, "pilot_session_id"),
            (self.reviewer_id, "reviewer_id"),
        ):
            _required_id(value, name)
        if self.decision not in {
            "APPROVED_FOR_ANNOTATION",
            "RECORDING_REQUIRED",
            "EXCLUDED",
            "REVIEW_PENDING",
        }:
            raise ValueError("invalid manual review decision")
        valid_reasons = {item.value for item in PilotExclusionReason}
        if any(reason not in valid_reasons for reason in self.reason_codes):
            raise ValueError("invalid manual review reason code")
        if self.decision in {"RECORDING_REQUIRED", "EXCLUDED"} and not (
            self.reason_codes
        ):
            raise ValueError("decision requires an operational reason code")
        _timestamp(self.reviewed_at, "reviewed_at")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value
