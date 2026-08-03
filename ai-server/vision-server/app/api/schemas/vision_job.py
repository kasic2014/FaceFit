"""Vision Job request and response schemas."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.common import VisionWarning
from app.vision.single_session_mvp_feedback import ANALYSIS_MODE


class AnalysisMode(str, Enum):
    SINGLE_SESSION_BASELINE_RELATIVE_MVP = ANALYSIS_MODE


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    SUCCEEDED_WITH_LIMITATIONS = "SUCCEEDED_WITH_LIMITATIONS"
    FAILED = "FAILED"


class VisionJobCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sessionId: str = Field(
        pattern=r"^SES_\d{6}$",
        description="Pseudonymous Session ID in SES_ plus six digits format",
        examples=["SES_000001"],
    )
    analysisMode: AnalysisMode = Field(
        default=AnalysisMode.SINGLE_SESSION_BASELINE_RELATIVE_MVP,
        description="Only the single-Session baseline-relative MVP is supported",
    )
    forceRebuild: bool = Field(
        default=False,
        description=(
            "Rebuild only Stage 22 feedback through reusable service functions; "
            "the Stage 5-22 media pipeline is never rerun"
        ),
    )


class JobError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class VisionJobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jobId: str = Field(description="Non-identifying UUID Job ID")
    sessionId: str = Field(pattern=r"^SES_\d{6}$")
    analysisMode: AnalysisMode
    status: JobStatus
    createdAt: str
    startedAt: str | None
    completedAt: str | None
    resultAvailable: bool
    warnings: list[VisionWarning] = Field(default_factory=list)
    error: JobError | None
