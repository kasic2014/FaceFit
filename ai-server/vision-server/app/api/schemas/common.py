"""Common public response schemas."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.vision_api_config import SERVICE_NAME, SERVICE_VERSION
from app.vision.single_session_mvp_feedback import ANALYSIS_MODE


class ErrorCode(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    RESULT_NOT_READY = "RESULT_NOT_READY"
    UNSUPPORTED_ANALYSIS_MODE = "UNSUPPORTED_ANALYSIS_MODE"
    INPUT_ARTIFACTS_MISSING = "INPUT_ARTIFACTS_MISSING"
    FEEDBACK_BUILD_FAILED = "FEEDBACK_BUILD_FAILED"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    JOB_STORAGE_ERROR = "JOB_STORAGE_ERROR"
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: ErrorCode = Field(description="Stable machine-readable error code")
    message: str = Field(description="Sanitized user-facing error message")
    requestId: str = Field(
        pattern=(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
            r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
        ),
        description="Non-identifying request UUID",
    )
    details: list[dict[str, Any]] = Field(default_factory=list)


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["UP"] = "UP"
    service: Literal[SERVICE_NAME] = SERVICE_NAME
    version: Literal[SERVICE_VERSION] = SERVICE_VERSION


class ReadyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["READY"] = "READY"
    service: Literal[SERVICE_NAME] = SERVICE_NAME
    analysisMode: Literal[ANALYSIS_MODE] = ANALYSIS_MODE
    scoringAvailable: Literal[False] = False


class VisionWarning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
