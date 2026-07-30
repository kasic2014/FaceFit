"""Pre-recording checklist and Stage 13 consent integration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.vision.consent_models import (
    ConsentPurpose,
    ConsentReference,
    evaluate_consent_gate,
)
from app.vision.data_collection_models import _required_id


@dataclass(frozen=True)
class RecordingChecklist:
    checklist_id: str
    consent_status_granted: bool
    video_collection_allowed: bool
    automated_analysis_allowed: bool
    research_use_allowed: bool
    single_person_confirmed: bool
    face_in_frame: bool
    both_shoulders_in_frame: bool
    camera_fixed: bool
    lighting_checked: bool
    microphone_checked: bool
    storage_space_checked: bool
    baseline_ready: bool

    def __post_init__(self) -> None:
        _required_id(self.checklist_id, "checklist_id")
        if any(
            not isinstance(value, bool)
            for key, value in asdict(self).items() if key != "checklist_id"
        ):
            raise ValueError("checklist values must be boolean")

    @property
    def all_required_passed(self) -> bool:
        return all(
            value for key, value in asdict(self).items()
            if key != "checklist_id"
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["all_required_passed"] = self.all_required_passed
        return value


def recording_ready(
    checklist: RecordingChecklist,
    consent: ConsentReference | None,
) -> bool:
    if not checklist.all_required_passed:
        return False
    return all(
        evaluate_consent_gate(consent, purpose).allowed
        for purpose in (
            ConsentPurpose.VIDEO_COLLECTION.value,
            ConsentPurpose.AUTOMATED_ANALYSIS.value,
            ConsentPurpose.RESEARCH_USE.value,
        )
    )
