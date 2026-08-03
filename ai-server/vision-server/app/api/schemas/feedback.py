"""Stage 22 feedback response schema exposed without internal identifiers."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.vision.single_session_mvp_feedback import (
    ANALYSIS_MODE,
    RESULT_INPUT_FAILED,
    RESULT_LIMITED,
    RESULT_READY,
    RESULT_UNAVAILABLE,
)


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    sessionId: str = Field(
        pattern=r"^SES_\d{6}$",
        description="Pseudonymous Session ID in SES_ plus six digits format",
    )
    status: Literal[
        RESULT_READY,
        RESULT_LIMITED,
        RESULT_UNAVAILABLE,
        RESULT_INPUT_FAILED,
    ]
    analysisMode: Literal[ANALYSIS_MODE]
    scores: None = Field(
        default=None,
        description=(
            "Scoring is unavailable for the single-Session Vision MVP and "
            "this value is always null"
        ),
    )
    scoringUnavailableReasons: list[str] = Field(
        description="Reasons that Vision scores are intentionally unavailable"
    )
    measurementSummary: dict[str, Any]
    answers: list[dict[str, Any]]
    warnings: list[Any]
    limitations: list[Any]
    disclaimer: str
