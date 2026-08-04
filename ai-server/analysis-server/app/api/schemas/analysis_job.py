"""Analysis job request and response contracts."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field, StrictBool, field_validator

from .common import ApiModel, ApiWarning


class Pipeline(str, Enum):
    STT_TRANSCRIPTION = "STT_TRANSCRIPTION"
    SPEECH_CHARACTERISTICS = "SPEECH_CHARACTERISTICS"
    STT_AND_SPEECH = "STT_AND_SPEECH"


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    SUCCEEDED_WITH_WARNINGS = "SUCCEEDED_WITH_WARNINGS"
    FAILED = "FAILED"


class AnalysisJobRequest(ApiModel):
    session_id: str = Field(alias="sessionId", pattern=r"^SES_\d{6}$")
    pipeline: Pipeline
    force_rebuild: StrictBool = Field(default=False, alias="forceRebuild")

    @field_validator("session_id")
    @classmethod
    def validate_session(cls, value: str) -> str:
        if len(value) != 10:
            raise ValueError("sessionId must match SES_ followed by six digits")
        return value


class AnalysisJobResponse(ApiModel):
    job_id: str = Field(alias="jobId")
    session_id: str = Field(alias="sessionId")
    pipeline: Pipeline
    status: JobStatus
    created_at: datetime = Field(alias="createdAt")
    queued_at: datetime = Field(alias="queuedAt")
    started_at: datetime | None = Field(default=None, alias="startedAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    updated_at: datetime = Field(alias="updatedAt")
    queue_wait_ms: int | None = Field(default=None, alias="queueWaitMs", ge=0)
    execution_duration_ms: int | None = Field(
        default=None, alias="executionDurationMs", ge=0
    )
    total_duration_ms: int | None = Field(default=None, alias="totalDurationMs", ge=0)
    result_available: bool = Field(alias="resultAvailable")
    warnings: list[ApiWarning] = Field(default_factory=list)
    error: dict[str, Any] | None = None
