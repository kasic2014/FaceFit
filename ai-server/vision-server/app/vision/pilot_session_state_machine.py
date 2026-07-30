"""Explicit Stage 14 pilot session state transitions."""

from __future__ import annotations

from app.vision.pilot_collection_models import PilotSessionStatus


ALLOWED_TRANSITIONS = {
    "PLANNED": {"READY", "EXCLUDED", "WITHDRAWN", "FAILED"},
    "READY": {"RECORDING", "EXCLUDED", "WITHDRAWN", "FAILED"},
    "RECORDING": {"RECORDED", "WITHDRAWN", "FAILED"},
    "RECORDED": {"VALIDATING", "EXCLUDED", "WITHDRAWN", "FAILED"},
    "VALIDATING": {"MANUAL_REVIEW", "EXCLUDED", "WITHDRAWN", "FAILED"},
    "MANUAL_REVIEW": {
        "ANNOTATION_READY", "PLANNED", "EXCLUDED", "WITHDRAWN", "FAILED"
    },
    "ANNOTATION_READY": {"EXCLUDED", "WITHDRAWN"},
    "EXCLUDED": set(),
    "WITHDRAWN": set(),
    "FAILED": set(),
}


def validate_session_transition(current: str, target: str) -> None:
    valid = {item.value for item in PilotSessionStatus}
    if current not in valid or target not in valid:
        raise ValueError("unknown pilot session status")
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"forbidden session transition: {current} -> {target}")
